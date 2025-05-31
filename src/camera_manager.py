"""
Camera management for Raspberry Pi Camera Web App
Handles Picamera2 operations with dual-stream configuration for simultaneous
video streaming and high-resolution photo capture

Enhanced with adaptive streaming system that automatically adjusts frame rate
and quality based on network conditions to prevent buffering issues.
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
    """Adaptive latest frame broadcast system with network performance tracking
    
    Enhanced to support adaptive streaming by monitoring frame delivery performance
    and providing metrics for quality/frame rate adjustment decisions.
    """
    
    def __init__(self):
        # Frame storage (universal optimization)
        self.latest_frame = None
        self.frame_ready = False
        self.frames_written = 0
        
        # Network performance tracking for adaptive streaming
        self.frames_delivered = 0
        self.frames_dropped = 0
        self.last_frame_time = time.time()
        self.frame_intervals = []  # Track recent frame intervals
        self.max_interval_samples = 10  # Keep last 10 intervals for average
        
        # Performance metrics
        self.delivery_times = []  # Track frame delivery times
        self.max_delivery_samples = 20
        self.slow_deliveries = 0
        self.last_performance_check = time.time()
    
    def write(self, buf):
        """Write new frame data with performance tracking"""
        current_time = time.time()
        
        # Track frame intervals for adaptive frame rate
        if self.last_frame_time > 0:
            interval = current_time - self.last_frame_time
            self.frame_intervals.append(interval)
            
            # Keep only recent samples
            if len(self.frame_intervals) > self.max_interval_samples:
                self.frame_intervals.pop(0)
        
        # Store frame and update metrics
        self.latest_frame = buf
        self.frame_ready = True
        self.frames_written += 1
        self.last_frame_time = current_time
    
    def get_latest_frame(self):
        """Get the most recent frame with delivery tracking"""
        if self.frame_ready:
            self.frames_delivered += 1
            return self.latest_frame
        return None
    
    def record_delivery_time(self, delivery_time: float):
        """Record frame delivery time for performance monitoring"""
        self.delivery_times.append(delivery_time)
        
        # Keep only recent samples
        if len(self.delivery_times) > self.max_delivery_samples:
            self.delivery_times.pop(0)
        
        # Track slow deliveries (>4 seconds indicates network issues)
        if delivery_time > 4.0:
            self.slow_deliveries += 1
    
    def get_average_frame_interval(self) -> float:
        """Get average time between frames (for adaptive frame rate)"""
        if not self.frame_intervals:
            return 0.033  # Default ~30fps
        return sum(self.frame_intervals) / len(self.frame_intervals)
    
    def get_average_delivery_time(self) -> float:
        """Get average frame delivery time"""
        if not self.delivery_times:
            return 0.0
        return sum(self.delivery_times) / len(self.delivery_times)
    
    def is_network_slow(self, threshold: float = 1.0) -> bool:
        """Check if network performance indicates slow conditions"""
        avg_delivery = self.get_average_delivery_time()
        return avg_delivery > threshold or self.slow_deliveries > 3
    
    def get_performance_metrics(self) -> dict:
        """Get comprehensive performance metrics"""
        return {
            "frames_written": self.frames_written,
            "frames_delivered": self.frames_delivered,
            "frames_dropped": self.frames_dropped,
            "average_frame_interval": self.get_average_frame_interval(),
            "average_delivery_time": self.get_average_delivery_time(),
            "slow_deliveries": self.slow_deliveries,
            "network_slow": self.is_network_slow()
        }
    
    def reset_performance_counters(self):
        """Reset performance counters for fresh measurement"""
        self.frames_delivered = 0
        self.frames_dropped = 0
        self.slow_deliveries = 0
        self.delivery_times.clear()
    
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
    
    Enhanced with adaptive streaming that automatically adjusts frame rate and
    quality based on network conditions to maintain real-time performance.
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
        
        # Adaptive streaming state
        self.current_frame_rate = config.max_frame_rate
        self.current_quality = config.stream_quality
        self.max_quality = config.stream_quality  # Remember user's preferred quality
        self.last_adaptation_time = time.time()
        self.adaptation_lock = threading.Lock()
        
        # Network monitoring
        self.network_check_thread: Optional[threading.Thread] = None
        self.network_monitoring = False
        
        # Performance tracking
        self.total_frames_sent = 0
        self.total_frames_dropped = 0
        
        # Recovery tracking for gradual adaptation
        self.consecutive_good_periods = 0
        self.min_consecutive_good_for_recovery = 3
        
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
    
    def _update_encoder_quality(self, new_quality: int) -> bool:
        """Update JPEG encoder quality during streaming"""
        if not self.is_streaming or not self.camera_device or not PICAMERA2_AVAILABLE:
            return False
        
        try:
            # Stop current recording
            self.camera_device.stop_recording()
            
            # Create new encoder with updated quality
            self.jpeg_encoder = JpegEncoder(q=new_quality)
            
            # Start recording again with new encoder
            self.camera_device.start_recording(
                self.jpeg_encoder,
                FileOutput(self.stream_output)
            )
            
            self.current_quality = new_quality
            print(f"🔄 Quality adjusted to {new_quality}%")
            return True
            
        except Exception as e:
            print(f"❌ Failed to update encoder quality: {e}")
            return False
    
    def _monitor_network_performance(self):
        """Background thread to monitor network performance and adapt streaming"""
        print("🔍 Network monitoring started")
        
        while self.network_monitoring and self.is_streaming:
            try:
                time.sleep(self.config.network_check_interval)
                
                if not self.stream_output:
                    continue
                
                # Get performance metrics
                metrics = self.stream_output.get_performance_metrics()
                
                with self.adaptation_lock:
                    # Check if adaptation is needed
                    current_time = time.time()
                    time_since_last_adaptation = current_time - self.last_adaptation_time
                    
                    # Only adapt every few seconds to avoid oscillation
                    if time_since_last_adaptation < self.config.network_check_interval:
                        continue
                    
                    if self.config.adaptive_streaming:
                        self._adapt_frame_rate(metrics)
                    
                    if self.config.adaptive_quality:
                        self._adapt_quality(metrics)
                    
                    self.last_adaptation_time = current_time
                
            except Exception as e:
                print(f"⚠️  Network monitoring error: {e}")
                time.sleep(1)  # Brief pause on error
        
        print("🔚 Network monitoring stopped")
    
    def _adapt_frame_rate(self, metrics: dict):
        """Adapt frame rate based on network performance"""
        network_slow = metrics.get("network_slow", False)
        avg_delivery = metrics.get("average_delivery_time", 0.0)
        
        if network_slow or avg_delivery > self.config.network_timeout_threshold:
            # Network is slow - reduce frame rate and reset good period counter
            self.consecutive_good_periods = 0
            if self.current_frame_rate > self.config.min_frame_rate:
                new_frame_rate = max(
                    self.current_frame_rate - 5,
                    self.config.min_frame_rate
                )
                self.current_frame_rate = new_frame_rate
                print(f"📉 Frame rate reduced to {new_frame_rate} fps (network slow)")
        
        elif avg_delivery < 2.0:
            # Network performance is good - track consecutive good periods
            self.consecutive_good_periods += 1
            
            # Only attempt recovery after several consecutive good periods
            if (self.consecutive_good_periods >= self.min_consecutive_good_for_recovery and 
                self.current_frame_rate < self.config.max_frame_rate):
                new_frame_rate = min(
                self.current_frame_rate + 2,
                self.config.max_frame_rate
            )
                self.current_frame_rate = new_frame_rate
                # Reset counter after successful recovery attempt
                self.consecutive_good_periods = 0
                print(f"📈 Frame rate increased to {new_frame_rate} fps (network consistently good)")
        
        else:
            # Neutral performance - reset consecutive counter but don't change settings
            self.consecutive_good_periods = 0
    
    def _adapt_quality(self, metrics: dict):
        """Adapt JPEG quality based on network performance"""
        network_slow = metrics.get("network_slow", False)
        avg_delivery = metrics.get("average_delivery_time", 0.0)
        
        if network_slow or avg_delivery > self.config.network_timeout_threshold:
            # Network is slow - reduce quality
            if self.current_quality > self.config.min_stream_quality:
                new_quality = max(
                    self.current_quality - self.config.quality_step_size,
                    self.config.min_stream_quality
                )
                
                if self._update_encoder_quality(new_quality):
                    print(f"📉 Quality reduced to {new_quality}% (network slow)")
        
        elif avg_delivery < 2.0:
            # Network performance is good - track consecutive good periods
            self.consecutive_good_periods += 1
            
            # Only attempt recovery after several consecutive good periods
            if (self.consecutive_good_periods >= self.min_consecutive_good_for_recovery and 
                self.current_quality < self.max_quality):
                new_quality = min(
                    self.current_quality + self.config.quality_step_size,
                    self.max_quality
                )
                
                if self._update_encoder_quality(new_quality):
                    print(f"📈 Quality increased to {new_quality}% (network good)")
    
    def setup_streaming(self) -> bool:
        """Setup MJPEG streaming from lores stream with adaptive capabilities"""
        if not self.camera_device:
            if not self.init_camera():
                return False
        
        if not PICAMERA2_AVAILABLE:
            print("⚠️  Streaming not available without Picamera2")
            return False
        
        try:
            print("🎥 Setting up adaptive video streaming...")
            
            # Create streaming output with performance tracking
            self.stream_output = StreamOutput()
            
            # Initialize quality (respect user's setting as maximum)
            if self.config.low_resource_mode:
                # Lower quality for better performance on Pi Zero 2W
                quality = min(self.config.stream_quality, 70)
            else:
                quality = self.config.stream_quality
            
            self.current_quality = quality
            self.max_quality = self.config.stream_quality
            self.jpeg_encoder = JpegEncoder(q=quality)
            
            # Start recording from lores stream for streaming
            self.camera_device.start_recording(
                self.jpeg_encoder,
                FileOutput(self.stream_output)
            )
            
            self.is_streaming = True
            
            # Start network monitoring if adaptive streaming is enabled
            if self.config.adaptive_streaming or self.config.adaptive_quality:
                self.network_monitoring = True
                self.network_check_thread = threading.Thread(
                    target=self._monitor_network_performance,
                    daemon=True
                )
                self.network_check_thread.start()
            
            print(f"✅ Adaptive video streaming started")
            print(f"   🎯 Quality: {quality}% (max: {self.max_quality}%)")
            print(f"   📊 Frame rate: {self.current_frame_rate} fps")
            print(f"   🔄 Adaptive streaming: {self.config.adaptive_streaming}")
            print(f"   🎨 Adaptive quality: {self.config.adaptive_quality}")
            
            return True
            
        except Exception as e:
            print(f"❌ Streaming setup failed: {e}")
            return False
    
    def stop_streaming(self) -> bool:
        """Stop video streaming and network monitoring"""
        if not self.is_streaming or not self.camera_device:
            return True
        
        try:
            print("🛑 Stopping adaptive video stream...")
            
            # Stop network monitoring
            self.network_monitoring = False
            if self.network_check_thread and self.network_check_thread.is_alive():
                self.network_check_thread.join(timeout=2)
            
            # Stop camera recording
            self.camera_device.stop_recording()
            self.is_streaming = False
            
            # Reset adaptive parameters
            self.current_frame_rate = self.config.max_frame_rate
            self.current_quality = self.config.stream_quality
            
            print("✅ Adaptive video streaming stopped")
            return True
            
        except Exception as e:
            print(f"❌ Error stopping stream: {e}")
            return False
    
    def generate_frames(self):
        """Generate frames for MJPEG streaming with adaptive frame rate"""
        print(f"🎬 Starting adaptive frame generation (target: {self.current_frame_rate} fps)")
        
        while self.is_streaming and self.stream_output:
            try:
                frame_start_time = time.time()
                
                # Get the latest available frame
                frame = self.stream_output.get_latest_frame()
                
                if frame:
                    # Calculate adaptive frame rate delay
                    target_interval = 1.0 / max(self.current_frame_rate, 1)
                    
                    # Yield frame
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                    
                    self.total_frames_sent += 1
                    
                    # Record delivery time for performance monitoring
                    delivery_time = time.time() - frame_start_time
                    self.stream_output.record_delivery_time(delivery_time)
                    
                    # Adaptive delay based on current frame rate setting
                    time.sleep(target_interval)
                else:
                    # No frame available - brief pause
                    self.total_frames_dropped += 1
                    time.sleep(0.01)
                        
            except Exception as e:
                print(f"❌ Adaptive streaming error: {e}")
                break
        
        print("🔚 Adaptive frame generation ended")
    
    def get_status(self) -> dict:
        """Get camera status information with adaptive streaming metrics"""
        status = {
            "available": self.camera_device is not None,
            "streaming": self.is_streaming,
            "module": self.camera_module,
            "resolution": self.sensor_resolution,
            "buffer_count": self.recommended_buffer_count,
            "picamera2_available": PICAMERA2_AVAILABLE,
            "low_resource_mode": self.config.low_resource_mode,
            
            # Adaptive streaming status
            "adaptive_streaming": self.config.adaptive_streaming,
            "adaptive_quality": self.config.adaptive_quality,
            "current_frame_rate": self.current_frame_rate,
            "current_quality": self.current_quality,
            "max_quality": self.max_quality,
            "target_frame_rate_range": f"{self.config.min_frame_rate}-{self.config.max_frame_rate}",
            "quality_range": f"{self.config.min_stream_quality}-{self.max_quality}",
            
            # Performance metrics
            "total_frames_sent": self.total_frames_sent,
            "total_frames_dropped": self.total_frames_dropped
        }
        
        # Add streaming statistics if available
        if self.stream_output:
            performance_metrics = self.stream_output.get_performance_metrics()
            status.update({
                "frames_written": performance_metrics["frames_written"],
                "frames_delivered": performance_metrics["frames_delivered"],
                "network_slow": performance_metrics["network_slow"],
                "average_delivery_time": round(performance_metrics["average_delivery_time"], 3),
                "streaming_mode": "adaptive_latest_frame_broadcast"
            })
        
        return status
    
    def get_streaming_stats(self) -> dict:
        """Get detailed streaming performance statistics"""
        if not self.stream_output:
            return {"error": "No active stream"}
        
        metrics = self.stream_output.get_performance_metrics()
        
        return {
            "performance": metrics,
            "adaptation": {
                "current_frame_rate": self.current_frame_rate,
                "current_quality": self.current_quality,
                "max_quality": self.max_quality,
                "frames_sent": self.total_frames_sent,
                "frames_dropped": self.total_frames_dropped,
                "drop_rate": self.total_frames_dropped / max(self.total_frames_sent + self.total_frames_dropped, 1)
            },
            "configuration": {
                "adaptive_streaming": self.config.adaptive_streaming,
                "adaptive_quality": self.config.adaptive_quality,
                "frame_rate_range": [self.config.min_frame_rate, self.config.max_frame_rate],
                "quality_range": [self.config.min_stream_quality, self.max_quality],
                "network_check_interval": self.config.network_check_interval,
                "network_timeout_threshold": self.config.network_timeout_threshold
            }
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
