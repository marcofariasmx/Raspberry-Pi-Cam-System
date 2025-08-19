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
        def __init__(self, q=85):
            self.quality = q
    
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
        
        print("📷 Initializing camera...")
        self._init_camera()
    
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
            
            # Create streaming configuration for the specified resolution and framerate
            stream_config = self.camera.create_video_configuration(
                main={"size": (self.config.stream_width, self.config.stream_height)},
                controls={
                    "FrameRate": self.config.stream_fps
                }
            )
            
            # Apply camera transforms if configured
            if self.config.camera_hflip or self.config.camera_vflip:
                stream_config["transform"] = Transform(
                    hflip=self.config.camera_hflip,
                    vflip=self.config.camera_vflip
                )
            
            # Configure camera with our settings
            self.camera.configure(stream_config)
            
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
                    encoder = MJPEGEncoder(q=self.config.jpeg_quality)
                    self.camera.start_recording(encoder, FileOutput(self.output))
                    self.streaming = True
                    print("🎬 MJPEG video streaming started (hardware accelerated)")
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