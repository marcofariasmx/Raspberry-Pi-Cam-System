"""
Camera Management Module for Raspberry Pi Streaming

This module provides camera initialization, configuration, and MJPEG streaming
functionality for Raspberry Pi camera modules. It handles both hardware camera
access via Picamera2 and development mode fallbacks for testing without hardware.

Key Features:
- Automatic camera detection and initialization
- MJPEG streaming with configurable quality and resolution
- Development mode with mock camera for testing
- Thread-safe camera operations
- Graceful error handling and cleanup

The module supports various Raspberry Pi camera modules and automatically
configures optimal settings based on the provided configuration.
"""

import io
import time
import threading
import asyncio
import json
from threading import Condition
from typing import Generator, Optional, Any

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput
    from libcamera import controls, Transform
    import io
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False
    print("⚠️  Picamera2 not available - running in development mode")
    
    # Mock classes for development mode
    class Picamera2:
        def create_video_configuration(self, **kwargs):
            return {}
        def configure(self, config):
            pass
        def start_recording(self, encoder, output):
            pass
        def stop_recording(self):
            pass
        def close(self):
            pass
    
    class H264Encoder:
        def __init__(self, bitrate=None):
            self.bitrate = bitrate
    
    class FileOutput:
        def __init__(self, file):
            self.file = file
    
    class Transform:
        def __init__(self, hflip=False, vflip=False):
            self.hflip = hflip
            self.vflip = vflip

from src.config import Config


class StreamingOutput(io.BufferedIOBase):
    """Simple H.264 Annex B streaming output for WebSocket clients."""
    
    def __init__(self, websocket_manager, loop=None):
        super().__init__()
        self.websocket_manager = websocket_manager
        self.loop = loop
        self.frame_count = 0
        self.frame = None
        self.condition = Condition()
    
    def write(self, buf):
        """Send raw H.264 Annex B stream directly to WebSocket clients."""
        # Don't store frame data - we just need to notify condition waiters
        with self.condition:
            self.condition.notify_all()
        
        if self.websocket_manager and buf and self.loop:
            try:
                # Send raw H.264 data in Annex B format directly
                # Properly handle the Future to prevent memory leaks
                future = asyncio.run_coroutine_threadsafe(
                    self.websocket_manager.broadcast_binary(buf), 
                    self.loop
                )
                # Don't wait for result, but ensure we don't leak futures
                future.add_done_callback(lambda f: f.exception())
                
                self.frame_count += 1
                if self.frame_count % 60 == 0:
                    # Add basic memory monitoring
                    import psutil
                    import os
                    process = psutil.Process(os.getpid())
                    memory_mb = process.memory_info().rss / 1024 / 1024
                    print(f"📺 H.264 frames sent: {self.frame_count}, Memory: {memory_mb:.1f}MB")
                    
            except Exception as e:
                if self.frame_count % 100 == 0:
                    print(f"⚠️ WebSocket broadcast error (frame {self.frame_count}): {e}")
                
        return len(buf)




class Camera:
    """
    Camera management class for Raspberry Pi streaming applications.
    
    This class handles camera initialization, configuration, and streaming operations.
    It provides a simple interface for H.264 video streaming with automatic hardware
    detection and graceful fallbacks for development environments.
    
    The camera supports:
    - Hardware-accelerated H.264 encoding for WebCodecs
    - Configurable resolution, framerate, and bitrate
    - Camera transforms (horizontal/vertical flip)
    - Thread-safe streaming operations
    - Automatic resource cleanup
    
    In development environments without camera hardware, the class operates in
    mock mode for testing purposes.
    """
    
    def __init__(self, config: Config):
        """
        Initialize camera instance with provided configuration.
        
        Sets up the camera hardware (if available) and prepares for streaming
        operations. The initialization process includes camera detection,
        configuration validation, and setup of streaming parameters.
        
        Args:
            config: Configuration instance containing camera and stream settings
        """
        self.config = config
        self.camera: Optional[Picamera2] = None
        self.h264_output: Optional[StreamingOutput] = None
        self.h264_streaming = False
        self.websocket_manager = None
        self._streaming_task = None
        self._lock = threading.Lock()
        self._use_lores_stream = False
        self._sensor_info = None
        
        print("📷 Initializing camera...")
        self._init_camera()
    
    def _detect_sensor(self) -> dict:
        """
        Detect camera sensor type and capabilities.
        
        Returns:
            dict: Sensor information including model, native resolution, and capabilities
        """
        if not self.camera:
            return {"model": "unknown", "native_resolution": (1920, 1080), "aspect_ratio": (16, 9)}
        
        try:
            # Get camera properties
            camera_properties = self.camera.camera_properties
            sensor_modes = self.camera.sensor_modes
            
            # Extract sensor model from camera properties
            sensor_model = camera_properties.get('Model', 'Unknown')
            
            # Find the highest resolution mode (usually the first one)
            max_resolution = (1920, 1080)  # Default fallback
            if sensor_modes:
                max_mode = max(sensor_modes, key=lambda mode: mode['size'][0] * mode['size'][1])
                max_resolution = max_mode['size']
            
            # Calculate aspect ratio
            width, height = max_resolution
            aspect_ratio = (width // self._gcd(width, height), height // self._gcd(width, height))
            
            sensor_info = {
                "model": sensor_model,
                "native_resolution": max_resolution,
                "aspect_ratio": aspect_ratio,
                "sensor_modes": sensor_modes[:5] if sensor_modes else []  # Top 5 modes for debugging
            }
            
            print(f"📷 Detected sensor: {sensor_model}")
            print(f"📷 Native resolution: {max_resolution[0]}x{max_resolution[1]} (aspect {aspect_ratio[0]}:{aspect_ratio[1]})")
            print(f"📷 Available modes: {len(sensor_modes) if sensor_modes else 0}")
            
            self._sensor_info = sensor_info
            return sensor_info
            
        except Exception as e:
            print(f"⚠️  Sensor detection failed: {e}")
            return {"model": "unknown", "native_resolution": (1920, 1080), "aspect_ratio": (16, 9)}
    
    def _gcd(self, a: int, b: int) -> int:
        """Calculate greatest common divisor."""
        while b:
            a, b = b, a % b
        return a
    
    def _get_optimal_configuration(self, sensor_info: dict) -> tuple:
        """
        Determine optimal camera configuration to prevent cropping.
        
        Args:
            sensor_info: Sensor detection information
            
        Returns:
            tuple: (main_resolution, use_lores_stream)
        """
        desired_width = self.config.stream_width
        desired_height = self.config.stream_height
        desired_aspect = desired_width / desired_height
        
        native_width, native_height = sensor_info["native_resolution"]
        native_aspect = native_width / native_height
        
        print(f"📷 Desired: {desired_width}x{desired_height} (aspect {desired_aspect:.2f})")
        print(f"📷 Native: {native_width}x{native_height} (aspect {native_aspect:.2f})")
        
        # Check if aspect ratios are close (within 5% tolerance)
        aspect_diff = abs(desired_aspect - native_aspect) / native_aspect
        
        if aspect_diff < 0.05:
            # Aspect ratios match, can use single main stream
            print("📷 Aspect ratios match - using single main stream")
            return (desired_width, desired_height), False
        else:
            # Aspect ratios don't match, use main+lores to prevent cropping
            print(f"📷 Aspect ratio mismatch ({aspect_diff*100:.1f}% difference) - using main+lores streams")
            
            # Use native resolution for main stream to capture full sensor
            # Use lores stream for desired output resolution
            return (native_width, native_height), True
    
    def _configure_camera(self):
        """
        Single point of camera configuration with all current settings.
        
        Configures the camera with current resolution, FPS, and transforms.
        This method is called during initialization and when settings change.
        """
        video_config = self.camera.create_video_configuration(
            main={"size": (self.config.stream_width, self.config.stream_height), "format": "YUV420"},
            controls={
                "FrameRate": self.config.stream_fps,
                "AeEnable": True,
                "AwbEnable": True
            },
            transform=Transform(
                hflip=self.config.camera_hflip,
                vflip=self.config.camera_vflip
            )
        )
        
        self.camera.configure(video_config)
        print(f"📷 Camera configured: {self.config.stream_width}x{self.config.stream_height} @ {self.config.stream_fps}fps, HFLIP={self.config.camera_hflip}, VFLIP={self.config.camera_vflip}")
    
    def _log_crop_info(self):
        """Log camera crop and configuration information for debugging."""
        try:
            if self.camera:
                # Get current configuration
                config = self.camera.camera_configuration()
                print(f"📷 Final configuration:")
                if 'main' in config:
                    print(f"   Main stream: {config['main']}")
                if 'lores' in config:
                    print(f"   Lores stream: {config['lores']}")
                
                # Get crop information
                crop_info = self.camera.camera_controls.get('ScalerCrop')
                if crop_info:
                    crop_rect = crop_info[2]  # (x, y, width, height)
                    print(f"📷 Sensor crop: x={crop_rect[0]}, y={crop_rect[1]}, w={crop_rect[2]}, h={crop_rect[3]}")
                    
                    # Calculate crop percentage
                    if self._sensor_info:
                        native_w, native_h = self._sensor_info["native_resolution"]
                        crop_w, crop_h = crop_rect[2], crop_rect[3]
                        crop_percent_w = (crop_w / native_w) * 100
                        crop_percent_h = (crop_h / native_h) * 100
                        print(f"📷 Crop usage: {crop_percent_w:.1f}% width, {crop_percent_h:.1f}% height")
        except Exception as e:
            print(f"⚠️  Could not log crop info: {e}")
    
    def _init_camera(self) -> bool:
        """
        Initialize and configure the camera hardware.
        
        Attempts to detect and configure the camera hardware with the specified
        settings. In development environments without camera hardware, this
        method enables mock mode for testing.
        
        The initialization process:
        1. Detects available camera hardware
        2. Configures camera with specified resolution and framerate
        3. Applies camera transforms if requested
        4. Starts the camera for streaming operations
        
        Returns:
            bool: True if camera was successfully initialized, False otherwise
        """
        if not PICAMERA2_AVAILABLE:
            print("📷 Mock camera initialized (development mode)")
            return True
        
        try:
            self.camera = Picamera2()
            
            # Detect sensor and get optimal configuration
            sensor_info = self._detect_sensor()
            main_resolution, use_lores = self._get_optimal_configuration(sensor_info)
            
            # Always use single main stream to avoid memory issues
            print(f"📷 Using single main stream configuration - {self.config.stream_width}x{self.config.stream_height}")
            if use_lores:
                print(f"⚠️  Would benefit from main+lores to avoid cropping, but using single stream for memory efficiency")
            
            # Configure camera once with H.264-ready settings
            self._configure_camera()
            self._use_lores_stream = False
            
            # Add crop debugging information
            self._log_crop_info()
            
            print(f"📷 Camera ready - {self.config.stream_width}x{self.config.stream_height} @ {self.config.stream_fps}fps")
            return True
            
        except Exception as e:
            print(f"❌ Camera initialization failed: {e}")
            self.camera = None
            return False
    
    
    def start_websocket_h264_streaming(self, websocket_manager) -> bool:
        """
        Start H.264 video streaming to WebSocket clients.
        
        Simple approach: H.264 data goes directly from camera to WebSocket clients
        without complex buffering or NAL unit parsing.
        
        Args:
            websocket_manager: Connection manager for WebSocket clients
        
        Returns:
            bool: True if H.264 streaming was started successfully, False otherwise
        """
        with self._lock:
            if self.h264_streaming:
                return True
            
            if not PICAMERA2_AVAILABLE:
                self.h264_streaming = True
                self.websocket_manager = websocket_manager
                print("🎬 Mock WebSocket H.264 streaming started")
                return True
            
            if not self.camera:
                return False
            
            try:
                # Store websocket manager for streaming
                self.websocket_manager = websocket_manager
                
                # Reconfigure camera with current settings
                self._configure_camera()
                
                # Create ultra-low latency H.264 encoder
                # picamera2 H264Encoder supported parameters: bitrate, repeat, iperiod
                # Hardware encoder defaults to baseline profile automatically for low latency
                idr_interval = max(self.config.stream_fps // 5, 6)  # IDR every 0.2 seconds
                encoder = H264Encoder(
                    bitrate=self.config.h264_bitrate,
                    repeat=True,  # Repeat SPS/PPS before every IDR frame  
                    iperiod=idr_interval  # Very frequent keyframes for low latency
                )
                
                # Create streaming output with event loop and wrap with FileOutput
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                streaming_output = StreamingOutput(websocket_manager, loop)
                self.h264_output = FileOutput(streaming_output)
                
                # Start recording - H.264 data goes via FileOutput to StreamingOutput to WebSocket clients
                self.camera.start_recording(encoder, self.h264_output)
                self.h264_streaming = True
                
                print(f"🎬 WebSocket H.264 streaming started with SPS/PPS repetition")
                print(f"   Resolution: {self.config.stream_width}x{self.config.stream_height} @ {self.config.stream_fps}fps")
                print(f"   Bitrate: {self.config.h264_bitrate//1000000}Mbps")
                print(f"   IDR frames: every {idr_interval} frames ({idr_interval/self.config.stream_fps:.1f}s intervals)")
                return True
                
            except Exception as e:
                print(f"❌ Failed to start WebSocket H.264 streaming: {e}")
                return False
    
    def stop_h264_streaming(self) -> bool:
        """
        Stop H.264 video streaming to WebSocket clients.
        
        Safely stops the H.264 streaming session and releases resources.
        This method is thread-safe and can be called multiple times safely.
        
        Returns:
            bool: True if H.264 streaming was stopped successfully
        """
        with self._lock:
            if not self.h264_streaming:
                return True
            
            try:
                if PICAMERA2_AVAILABLE and self.camera:
                    self.camera.stop_recording()
                
                self.h264_streaming = False
                self.h264_output = None
                self.websocket_manager = None
                print("🛑 Simple WebSocket H.264 streaming stopped")
                return True
            except Exception as e:
                print(f"⚠️  Error stopping WebSocket H.264 stream: {e}")
                self.h264_streaming = False
                return True
    
    def is_h264_streaming(self) -> bool:
        """
        Check if camera is currently streaming H.264 to WebSocket clients.
        
        Returns:
            bool: True if H.264 streaming is active
        """
        return self.h264_streaming
    
    def is_available(self) -> bool:
        """
        Check if camera is available for streaming operations.
        
        Returns True if either:
        - Camera hardware is properly initialized and available
        - Running in development mode (mock camera available)
        
        Returns:
            bool: True if camera is available for streaming
        """
        return self.camera is not None or not PICAMERA2_AVAILABLE
    
    
    def cleanup(self):
        """
        Cleanup camera resources and stop all operations.
        
        Properly shuts down the camera hardware, stops streaming operations,
        and releases all system resources. This method should be called
        when the application is shutting down or the camera is no longer needed.
        
        The cleanup process:
        1. Stops any active streaming operations
        2. Closes camera hardware connections
        3. Releases system resources
        4. Logs cleanup status
        """
        self.stop_h264_streaming()
        
        if self.camera:
            try:
                if PICAMERA2_AVAILABLE:
                    self.camera.close()
                print("📷 Camera cleanup completed")
            except Exception as e:
                print(f"⚠️  Camera cleanup error: {e}")
            finally:
                self.camera = None
                self.h264_output = None