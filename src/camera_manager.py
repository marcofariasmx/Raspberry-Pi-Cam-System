"""
Camera management for Raspberry Pi Camera Web App
Handles Picamera2 operations with dual-stream configuration for simultaneous
video streaming and high-resolution photo capture
"""

import io
import os
import time
import threading
from datetime import datetime
from typing import Optional, Tuple

from config import AppConfig

# Import picamera2 - graceful handling for development environments
try:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput
    from libcamera import Transform
    PICAMERA2_AVAILABLE = True
    print("✅ Picamera2 imported successfully")
except ImportError as e:
    print(f"⚠️  Picamera2 not available: {e}")
    PICAMERA2_AVAILABLE = False
    # Mock classes for development
    class Picamera2:
        def __init__(self): pass
        @property
        def sensor_resolution(self): return (1920, 1080)
        def close(self): pass
        def configure(self, config): pass
        def start(self): pass
        def stop(self): pass
        def capture_request(self): return MockRequest()
        def start_recording(self, encoder, output): pass
        def stop_recording(self): pass
        def create_video_configuration(self, **kwargs): return {}
    
    class MockRequest:
        def save(self, stream, filename): pass
        def release(self): pass
    
    class Transform:
        def __init__(self, **kwargs): pass


class StreamOutput(io.BufferedIOBase):
    """Custom output class for MJPEG streaming with thread-safe frame management"""
    
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()
        self.frame_count = 0
    
    def write(self, buf):
        """Write new frame data - called by picamera2 encoder"""
        with self.condition:
            self.frame = buf
            self.frame_count += 1
            self.condition.notify_all()
    
    def get_latest_frame(self):
        """Get the most recent frame for streaming"""
        with self.condition:
            return self.frame


class CameraManager:
    """
    Manages Raspberry Pi camera operations using Picamera2
    Supports simultaneous video streaming and high-resolution photo capture
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.camera_device: Optional[Picamera2] = None
        self.sensor_resolution: Optional[Tuple[int, int]] = None
        self.camera_module: str = "unknown"
        self.recommended_buffer_count: int = 2
        
        # Streaming state
        self.is_streaming = False
        self.stream_output: Optional[StreamOutput] = None
        self.jpeg_encoder: Optional[JpegEncoder] = None
        
        # Initialize camera on creation
        self._detect_camera_capabilities()
    
    def _detect_camera_capabilities(self) -> bool:
        """Auto-detect camera module and adapt settings"""
        if not PICAMERA2_AVAILABLE:
            print("⚠️  Picamera2 not available - using mock configuration")
            self.sensor_resolution = (
                self.config.camera_fallback_width,
                self.config.camera_fallback_height
            )
            self.camera_module = "mock"
            self.recommended_buffer_count = 2
            return False
        
        try:
            # Temporary camera instance for detection
            temp_camera = Picamera2()
            self.sensor_resolution = temp_camera.sensor_resolution
            temp_camera.close()
            
            # Detect module type based on resolution
            width, height = self.sensor_resolution
            total_pixels = width * height
            
            if total_pixels >= 12000000:  # 12MP+ (Module 3)
                self.camera_module = "module3"
                self.recommended_buffer_count = 2  # More conservative for high res
                print(f"📷 Camera Module 3 detected: {width}x{height}")
            elif total_pixels >= 8000000:  # 8MP+ (Module 2)
                self.camera_module = "module2"
                self.recommended_buffer_count = 3  # Can handle more buffers
                print(f"📷 Camera Module 2 detected: {width}x{height}")
            else:
                self.camera_module = "other"
                self.recommended_buffer_count = 2
                print(f"📷 Camera detected: {width}x{height}")
            
            return True
            
        except Exception as e:
            print(f"⚠️  Camera detection failed: {e}")
            # Fallback to configured resolution
            self.sensor_resolution = (
                self.config.camera_fallback_width,
                self.config.camera_fallback_height
            )
            self.camera_module = "fallback"
            self.recommended_buffer_count = 2
            return False
    
    def _get_optimal_config(self) -> dict:
        """Get camera configuration optimized for detected module"""
        # Main stream - full resolution for photo capture
        if self.config.camera_auto_detect and self.sensor_resolution:
            main_size = self.sensor_resolution
        else:
            main_size = (
                self.config.camera_fallback_width,
                self.config.camera_fallback_height
            )
        
        # Lores stream - consistent across modules for video streaming
        lores_size = (self.config.stream_width, self.config.stream_height)
        
        # Buffer count - adaptive based on module capabilities
        if self.config.buffer_count_auto:
            buffer_count = self.recommended_buffer_count
        else:
            buffer_count = self.config.buffer_count_fallback
        
        return {
            "main_stream": {
                "size": main_size,
                "format": self.config.main_stream_format
            },
            "lores_stream": {
                "size": lores_size,
                "format": self.config.lores_stream_format
            },
            "buffer_count": buffer_count,
            "transform": Transform(
                hflip=self.config.camera_hflip,
                vflip=self.config.camera_vflip
            ) if PICAMERA2_AVAILABLE else None
        }
    
    def init_camera(self) -> bool:
        """Initialize camera with dual-stream configuration"""
        if not PICAMERA2_AVAILABLE:
            print("⚠️  Picamera2 not available - camera initialization skipped")
            return False
        
        try:
            print("🚀 Initializing camera...")
            
            # Get optimal configuration for this camera module
            config = self._get_optimal_config()
            
            print(f"📐 Main stream: {config['main_stream']['size']} ({config['main_stream']['format']})")
            print(f"📺 Lores stream: {config['lores_stream']['size']} ({config['lores_stream']['format']})")
            print(f"🧠 Buffer count: {config['buffer_count']}")
            
            # Create camera instance
            self.camera_device = Picamera2()
            
            # Create dual-stream video configuration
            video_config = self.camera_device.create_video_configuration(
                main=config["main_stream"],
                lores=config["lores_stream"],
                encode="lores",  # Stream the lower resolution
                buffer_count=config["buffer_count"],
                transform=config["transform"]
            )
            
            # Configure and start camera
            self.camera_device.configure(video_config)
            self.camera_device.start()
            
            # Wait for camera to stabilize
            time.sleep(2)
            
            print("✅ Camera initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ Camera initialization failed: {e}")
            return self._try_minimal_config()
    
    def _try_minimal_config(self) -> bool:
        """Last resort minimal configuration"""
        if not PICAMERA2_AVAILABLE:
            return False
        
        try:
            print("🔄 Trying minimal camera configuration...")
            
            self.camera_device = Picamera2()
            
            # Absolute minimal config that should work on any Pi camera
            minimal_config = self.camera_device.create_video_configuration(
                main={"size": (1920, 1080), "format": "RGB888"},
                lores={"size": (640, 480)},
                encode="lores",
                buffer_count=2
            )
            
            self.camera_device.configure(minimal_config)
            self.camera_device.start()
            time.sleep(2)
            
            print("✅ Minimal camera configuration successful")
            return True
            
        except Exception as e:
            print(f"❌ Even minimal config failed: {e}")
            return False
    
    def capture_photo(self) -> Tuple[bool, str, str]:
        """
        Capture high-resolution still photo without interrupting video stream
        Returns: (success, message, filename)
        """
        if not self.camera_device:
            if not self.init_camera():
                return False, "Camera initialization failed", ""
        
        try:
            print("📸 Capturing high-resolution photo...")
            
            # Ensure photos directory exists
            os.makedirs(self.config.photos_dir, exist_ok=True)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"photo_{timestamp}.jpg"
            filepath = os.path.join(self.config.photos_dir, filename)
            
            # Use picamera2's proper capture method for simultaneous operation
            # This captures from the main (full resolution) stream while lores continues streaming
            request = self.camera_device.capture_request()
            request.save("main", filepath)  # Save from main stream (full resolution)
            request.release()  # Critical: release the request to free memory
            
            print(f"✅ Photo saved: {filename}")
            return True, "Photo captured successfully", filename
            
        except Exception as e:
            print(f"❌ Photo capture failed: {e}")
            return False, f"Capture failed: {str(e)}", ""
    
    def setup_streaming(self) -> bool:
        """Setup MJPEG streaming from lores stream"""
        if not self.camera_device:
            if not self.init_camera():
                return False
        
        if not PICAMERA2_AVAILABLE:
            print("⚠️  Streaming not available without Picamera2")
            return False
        
        try:
            print("🎥 Setting up video streaming...")
            
            # Create streaming output
            self.stream_output = StreamOutput()
            self.jpeg_encoder = JpegEncoder(q=self.config.stream_quality)
            
            # Start recording from lores stream for streaming
            self.camera_device.start_recording(
                self.jpeg_encoder,
                FileOutput(self.stream_output)
            )
            
            self.is_streaming = True
            print("✅ Video streaming started")
            return True
            
        except Exception as e:
            print(f"❌ Streaming setup failed: {e}")
            return False
    
    def stop_streaming(self) -> bool:
        """Stop video streaming"""
        if not self.is_streaming or not self.camera_device:
            return True
        
        try:
            print("🛑 Stopping video stream...")
            self.camera_device.stop_recording()
            self.is_streaming = False
            print("✅ Video streaming stopped")
            return True
            
        except Exception as e:
            print(f"❌ Error stopping stream: {e}")
            return False
    
    def generate_frames(self):
        """Generate frames for MJPEG streaming"""
        while self.is_streaming and self.stream_output:
            try:
                with self.stream_output.condition:
                    # Wait for new frame with timeout
                    if self.stream_output.condition.wait(timeout=1.0):
                        frame = self.stream_output.frame
                        
                        if frame:
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                    else:
                        # Timeout - check if we should continue
                        if not self.is_streaming:
                            break
                        
            except Exception as e:
                print(f"❌ Streaming error: {e}")
                break
        
        print("🔚 Stream generator ended")
    
    def get_status(self) -> dict:
        """Get camera status information"""
        return {
            "available": self.camera_device is not None,
            "streaming": self.is_streaming,
            "module": self.camera_module,
            "resolution": self.sensor_resolution,
            "buffer_count": self.recommended_buffer_count,
            "picamera2_available": PICAMERA2_AVAILABLE
        }
    
    def cleanup(self):
        """Clean up camera resources"""
        try:
            if self.is_streaming:
                self.stop_streaming()
            
            if self.camera_device:
                self.camera_device.stop()
                self.camera_device.close()
                self.camera_device = None
                print("🔒 Camera resources released")
                
        except Exception as e:
            print(f"⚠️  Error during cleanup: {e}")
