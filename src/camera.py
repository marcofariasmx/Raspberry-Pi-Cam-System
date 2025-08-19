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
from threading import Condition
from typing import Generator, Optional

try:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder, MJPEGEncoder
    from picamera2.outputs import FileOutput
    from libcamera import controls, Transform
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
    
    class JpegEncoder:
        def __init__(self, q=85):
            self.quality = q
    
    class MJPEGEncoder:
        def __init__(self, bitrate=None):
            self.bitrate = bitrate
    
    class FileOutput:
        def __init__(self, output):
            self.output = output
    
    class Transform:
        def __init__(self, hflip=False, vflip=False):
            self.hflip = hflip
            self.vflip = vflip

from src.config import Config


class StreamingOutput(io.BufferedIOBase):
    """
    Thread-safe output buffer for Picamera2 MJPEG streaming.
    
    This class implements the proper Picamera2 streaming pattern using
    condition variables for synchronization between frame capture and
    HTTP streaming threads.
    """
    
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        """Write frame data and notify waiting threads."""
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


class Camera:
    """
    Camera management class for Raspberry Pi streaming applications.
    
    This class handles camera initialization, configuration, and streaming operations.
    It provides a simple interface for MJPEG video streaming with automatic hardware
    detection and graceful fallbacks for development environments.
    
    The camera supports:
    - Hardware-accelerated JPEG encoding when available
    - Configurable resolution, framerate, and quality
    - Camera transforms (horizontal/vertical flip)
    - Thread-safe streaming operations
    - Automatic resource cleanup
    
    In development environments without camera hardware, the class operates in
    mock mode, generating synthetic MJPEG frames for testing purposes.
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
        self.output: Optional[StreamingOutput] = None
        self.streaming = False
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
            # Initialize mock output for development mode
            self.output = StreamingOutput()
            print("📷 Mock camera initialized (development mode)")
            return True
        
        try:
            self.camera = Picamera2()
            
            # Detect sensor and get optimal configuration
            sensor_info = self._detect_sensor()
            main_resolution, use_lores = self._get_optimal_configuration(sensor_info)

            main_resolution = main_resolution/2
            
            # Always use single main stream to avoid memory issues
            print(f"📷 Using single main stream configuration - {self.config.stream_width}x{self.config.stream_height}")
            if use_lores:
                print(f"⚠️  Would benefit from main+lores to avoid cropping, but using single stream for memory efficiency")
            
            stream_config = self.camera.create_video_configuration(
                main={"size": (self.config.stream_width, self.config.stream_height)},
                controls={
                    "FrameRate": self.config.stream_fps
                }
            )
            self._use_lores_stream = False
            
            # Apply camera transforms if configured
            if self.config.camera_hflip or self.config.camera_vflip:
                stream_config["transform"] = Transform(
                    hflip=self.config.camera_hflip,
                    vflip=self.config.camera_vflip
                )
            
            # Configure camera with our settings
            self.camera.configure(stream_config)
            
            # Add crop debugging information
            self._log_crop_info()
            
            # Create streaming output buffer
            self.output = StreamingOutput()
            
            print(f"📷 Camera ready - {self.config.stream_width}x{self.config.stream_height} @ {self.config.stream_fps}fps, quality {self.config.jpeg_quality}%")
            return True
            
        except Exception as e:
            print(f"❌ Camera initialization failed: {e}")
            self.camera = None
            return False
    
    def start_streaming(self) -> bool:
        """
        Start video streaming operations.
        
        Enables the camera streaming mode, allowing frame generation for
        MJPEG streaming. This method is thread-safe and can be called
        multiple times safely.
        
        Returns:
            bool: True if streaming was started successfully, False otherwise
        """
        with self._lock:
            if self.streaming:
                return True
            
            if not PICAMERA2_AVAILABLE:
                self.streaming = True
                print("🎬 Mock video streaming started")
                return True
            
            if not self.camera or not self.output:
                return False
            
            try:
                # Try MJPEGEncoder first for optimized streaming
                try:
                    # MJPEG Bitrate Quality Reference Guide:
                    # =====================================
                    # 
                    # RESOLUTION-BASED TYPICAL BITRATES:
                    # - 320x240@15fps:   0.5-2 Mbps (webcam quality)
                    # - 640x480@15fps:   1-5 Mbps (standard definition)  
                    # - 640x480@30fps:   2-10 Mbps (smooth SD)
                    # - 1280x720@30fps:  5-25 Mbps (HD ready)
                    # - 1920x1080@30fps: 10-50 Mbps (Full HD)
                    # - 4K@30fps:        50-500 Mbps (professional)
                    #
                    # QUALITY GUIDELINES BY BITRATE:
                    # - 0.5-1 Mbps:   Basic/low quality (visible compression)
                    # - 1-3 Mbps:     Good quality (web streaming)
                    # - 3-8 Mbps:     High quality (security cameras)  
                    # - 8-15 Mbps:    Very high quality (broadcast)
                    # - 15-50 Mbps:   Professional quality (minimal compression)
                    # - 50+ Mbps:     Archival/production quality
                    #
                    # HARDWARE LIMITS:
                    # - Pi 4B: ~15-20 Mbps practical limit
                    # - Pi 5: 50+ Mbps with software encoding
                    # - USB bandwidth: ~25 Mbps for USB 2.0
                    #
                    # MINIMUM/MAXIMUM VALUES:
                    # - Minimum: ~100 Kbps (0.1 Mbps) - extremely low quality
                    # - Maximum: ~500 Mbps - professional 4K applications
                    # - Typical range: 1-50 Mbps for most applications
                    
                    # Use configured MJPEG bitrate
                    bitrate = self.config.mjpeg_bitrate
                    print(f"🎬 Using MJPEG bitrate: {bitrate//1000000}Mbps")
                    
                    encoder = MJPEGEncoder(bitrate=bitrate)
                    self.camera.start_recording(encoder, FileOutput(self.output))
                    self.streaming = True
                    print(f"🎬 MJPEG video streaming started (hardware accelerated)")
                    return True
                except RuntimeError as mjpeg_error:
                    if "Hardware MJPEG not available" in str(mjpeg_error):
                        print("⚠️  Hardware MJPEG not available, falling back to JPEG encoder")
                        # Fallback to JpegEncoder
                        encoder = JpegEncoder(q=self.config.jpeg_quality)
                        self.camera.start_recording(encoder, FileOutput(self.output))
                        self.streaming = True
                        print("🎬 Video streaming started (software JPEG)")
                        return True
                    else:
                        raise mjpeg_error
            except Exception as e:
                print(f"❌ Failed to start streaming: {e}")
                return False
    
    def stop_streaming(self) -> bool:
        """
        Stop video streaming operations.
        
        Disables camera streaming mode and stops frame generation.
        This method is thread-safe and can be called multiple times safely.
        
        Returns:
            bool: True if streaming was stopped successfully
        """
        with self._lock:
            if not self.streaming:
                return True
            
            try:
                if PICAMERA2_AVAILABLE and self.camera:
                    self.camera.stop_recording()
                self.streaming = False
                print("🛑 Video streaming stopped")
                return True
            except Exception as e:
                print(f"⚠️  Error stopping stream: {e}")
                self.streaming = False
                return True
    
    def generate_frames(self) -> Generator[bytes, None, None]:
        """
        Generate MJPEG video frames for streaming.
        
        This generator uses the proper Picamera2 streaming approach with
        condition variables to wait for new frames from the camera recording.
        Each frame is properly formatted with MJPEG boundaries and headers
        for browser compatibility.
        
        In development mode, generates synthetic frames for testing.
        In production mode, waits for frames from the camera recording.
        
        The generator runs until streaming is stopped and handles errors
        gracefully by terminating the stream.
        
        Yields:
            bytes: MJPEG frame data with proper boundaries and headers
        """
        if not self.output:
            return
            
        if not PICAMERA2_AVAILABLE:
            # Mock frame generator for development
            while self.streaming:
                mock_frame = (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n'
                    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00'
                    b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
                    b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
                    b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342'
                    b'\xff\xc0\x00\x11\x08\x02X\x03 \x03\x01"\x00\x02\x11\x01\x03\x11\x01'
                    b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00'
                    b'\xff\xd9\r\n'
                )
                yield mock_frame
                time.sleep(1.0 / self.config.stream_fps)
            return
        
        # Real Picamera2 streaming using condition variables
        try:
            while self.streaming:
                with self.output.condition:
                    self.output.condition.wait()
                    frame = self.output.frame
                    if frame is None:
                        continue
                        
                # Format as MJPEG with proper boundaries
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n'
                    b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n' +
                    frame + b'\r\n'
                )
                
        except Exception as e:
            print(f"❌ Frame streaming error: {e}")
    
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
    
    def is_streaming(self) -> bool:
        """
        Check if camera is currently streaming.
        
        Returns:
            bool: True if camera is actively streaming
        """
        return self.streaming
    
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
        self.stop_streaming()
        
        if self.camera:
            try:
                if PICAMERA2_AVAILABLE:
                    self.camera.close()
                print("📷 Camera cleanup completed")
            except Exception as e:
                print(f"⚠️  Camera cleanup error: {e}")
            finally:
                self.camera = None
                self.output = None