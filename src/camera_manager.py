"""
Camera management for Raspberry Pi Camera Web App
Handles Picamera2 operations with dual-stream configuration for simultaneous
video streaming and high-resolution photo capture

Optimized with ultra-simple latest frame broadcast system for multiple concurrent clients.
LOW_RESOURCE_MODE now only affects camera-level settings, while streaming optimizations
are universal.
"""

import io
import os
import time
import threading
from datetime import datetime
from typing import Optional, Tuple

from src.config import AppConfig

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
    """Ultra-simple latest frame broadcast system for multiple concurrent clients
    
    This approach provides optimal performance for all Pi models by using a single
    frame storage that gets overwritten with the latest data. No synchronization
    needed - clients read at their own pace. This universal optimization eliminates
    the need for complex buffer management.
    """
    
    def __init__(self):
        # Ultra-simple: just store the latest frame (universal optimization)
        self.latest_frame = None
        self.frame_ready = False
        self.frames_written = 0  # Keep for monitoring
    
    def write(self, buf):
        """Write new frame data - simply overwrite latest frame"""
        # Just overwrite with the latest frame (zero synchronization needed)
        self.latest_frame = buf
        self.frame_ready = True
        self.frames_written += 1
    
    def get_latest_frame(self):
        """Get the most recent frame immediately (no waiting)"""
        return self.latest_frame if self.frame_ready else None
    
    def get_frame_count(self):
        """Get total frames written (for monitoring)"""
        return self.frames_written
    
    @property
    def max_frames(self):
        """Return 1 for compatibility with status reporting"""
        return 1


class CameraManager:
    """
    Manages Raspberry Pi camera operations using Picamera2
    Supports simultaneous video streaming and high-resolution photo capture
    
    Uses universal latest frame broadcast for unlimited concurrent clients.
    LOW_RESOURCE_MODE now only affects camera-level optimizations:
    - Camera buffer count (1 vs 2-3)
    - JPEG quality capping (70% vs full)
    - Format preferences (YUV420 vs RGB888)
    - Lazy camera initialization
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
        
        # Lazy initialization - only for low resource mode
        if not config.low_resource_mode:
            # For normal systems, detect capabilities early
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
                self.recommended_buffer_count = 2 if self.config.low_resource_mode else 2
                print(f"📷 Camera Module 3 detected: {width}x{height}")
            elif total_pixels >= 8000000:  # 8MP+ (Module 2)
                self.camera_module = "module2"
                self.recommended_buffer_count = 2 if self.config.low_resource_mode else 3
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
        """Get camera configuration optimized for detected module and resource mode"""
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
        
        # Camera buffer count optimization (Picamera2 hardware level - different from StreamOutput)
        # These buffers are for camera pipeline smoothness, not frame storage
        # StreamOutput always uses 1 frame, but camera needs 1-3 pipeline buffers
        if self.config.low_resource_mode:
            buffer_count = 1  # Single buffer for Pi Zero 2W
        elif self.config.buffer_count_auto:
            buffer_count = self.recommended_buffer_count
        else:
            buffer_count = self.config.buffer_count_fallback
        
        # Format optimization for low resource mode (still valuable)
        if self.config.low_resource_mode:
            # Prefer YUV420 for better performance on Pi Zero 2W
            main_format = "YUV420" if self.config.main_stream_format == "RGB888" else self.config.main_stream_format
            lores_format = "YUV420"
        else:
            main_format = self.config.main_stream_format
            lores_format = self.config.lores_stream_format
        
        return {
            "main_stream": {
                "size": main_size,
                "format": main_format
            },
            "lores_stream": {
                "size": lores_size,
                "format": lores_format
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
            
            # Lazy detection for low resource mode (still valuable)
            if self.config.low_resource_mode and not self.sensor_resolution:
                self._detect_camera_capabilities()
            
            # Get optimal configuration for this camera module
            config = self._get_optimal_config()
            
            print(f"📐 Main stream: {config['main_stream']['size']} ({config['main_stream']['format']})")
            print(f"📺 Lores stream: {config['lores_stream']['size']} ({config['lores_stream']['format']})")
            print(f"🧠 Buffer count: {config['buffer_count']}")
            print(f"⚡ Low resource mode: {self.config.low_resource_mode} (camera-level optimizations)")
            
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
                buffer_count=1 if self.config.low_resource_mode else 2
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
            try:
                request.save("main", filepath)  # Save from main stream (full resolution)
            finally:
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
            
            # Create streaming output with universal latest frame system
            self.stream_output = StreamOutput()
            
            # JPEG quality optimization (still valuable for Pi Zero 2W)
            if self.config.low_resource_mode:
                # Lower quality for better performance on Pi Zero 2W
                quality = min(self.config.stream_quality, 70)
            else:
                quality = self.config.stream_quality
            
            self.jpeg_encoder = JpegEncoder(q=quality)
            
            # Start recording from lores stream for streaming
            self.camera_device.start_recording(
                self.jpeg_encoder,
                FileOutput(self.stream_output)
            )
            
            self.is_streaming = True
            print(f"✅ Video streaming started (quality: {quality}, universal broadcast mode)")
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
        """Generate frames for MJPEG streaming with universal broadcast system"""
        while self.is_streaming and self.stream_output:
            try:
                # Simply get the latest available frame (no synchronization needed)
                frame = self.stream_output.get_latest_frame()
                
                if frame:
                    # Zero-copy frame delivery
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                
                # Small sleep to prevent CPU spinning and limit frame rate
                # This allows clients to consume at their own pace
                time.sleep(0.033)  # ~30 FPS maximum rate
                        
            except Exception as e:
                print(f"❌ Streaming error: {e}")
                break
        
        print("🔚 Stream generator ended")
    
    def get_status(self) -> dict:
        """Get camera status information"""
        status = {
            "available": self.camera_device is not None,
            "streaming": self.is_streaming,
            "module": self.camera_module,
            "resolution": self.sensor_resolution,
            "buffer_count": self.recommended_buffer_count,
            "picamera2_available": PICAMERA2_AVAILABLE,
            "low_resource_mode": self.config.low_resource_mode
        }
        
        # Add streaming statistics if available
        if self.stream_output:
            status["frames_written"] = self.stream_output.get_frame_count()
            status["max_buffer_frames"] = self.stream_output.max_frames
            status["streaming_mode"] = "universal_latest_frame_broadcast"
        
        return status
    
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
