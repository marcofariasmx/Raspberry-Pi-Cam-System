"""
Optimized Stream Output for Picamera2
Uses official threading.Condition pattern for efficient multi-client streaming
with integration to EfficientStreamingSystem for per-client quality adaptation.
"""

import io
import time
import threading
from typing import Optional, Dict, Any


class OptimizedStreamingOutput(io.BufferedIOBase):
    """
    Official Picamera2 streaming output pattern optimized for our efficient system
    
    Uses threading.Condition for synchronization as recommended by Raspberry Pi Foundation.
    Integrates with EfficientStreamingSystem for multi-quality processing.
    """
    
    def __init__(self, efficient_streaming_system):
        """
        Initialize optimized streaming output
        
        Args:
            efficient_streaming_system: EfficientStreamingSystem instance to feed frames to
        """
        # Official Picamera2 pattern
        self.frame = None
        self.condition = threading.Condition()
        
        # Integration with our efficient system
        self.efficient_streaming = efficient_streaming_system
        
        # Performance tracking
        self.frame_count = 0
        self.total_bytes = 0
        self.start_time = time.time()
        self.last_frame_time = 0.0
        
        # Memory monitoring for Pi Zero 2W
        self.max_frame_size = 0
        self.avg_frame_size = 0
        
        print("📹 OptimizedStreamingOutput initialized with threading.Condition pattern")
    
    def write(self, buf):
        """
        Official Picamera2 write method using threading.Condition
        
        Args:
            buf: MJPEG frame buffer from camera (already hardware encoded)
        """
        if not buf:
            return 0
        
        current_time = time.time()
        frame_size = len(buf)
        
        # Update the frame using official pattern
        with self.condition:
            self.frame = buf
            self.condition.notify_all()  # Notify all waiting clients
        
        # Feed to our efficient streaming system for multi-quality processing
        if self.efficient_streaming:
            self.efficient_streaming.process_frame(buf)
        
        # Update performance metrics
        self.frame_count += 1
        self.total_bytes += frame_size
        self.last_frame_time = current_time
        
        # Update memory tracking
        self.max_frame_size = max(self.max_frame_size, frame_size)
        self.avg_frame_size = self.total_bytes / self.frame_count
        
        # Log progress periodically (every 100 frames)
        if self.frame_count % 100 == 0:
            fps = self.frame_count / (current_time - self.start_time)
            print(f"📸 Processed {self.frame_count} frames from camera "
                  f"(FPS: {fps:.1f}, Size: {frame_size/1024:.1f}KB)")
        
        return frame_size
    
    def read_frame(self, timeout: float = 1.0) -> Optional[bytes]:
        """
        Read the latest frame using threading.Condition (thread-safe)
        
        Args:
            timeout: Maximum time to wait for a frame
            
        Returns:
            bytes: Latest MJPEG frame or None if timeout
        """
        with self.condition:
            if self.condition.wait(timeout):
                return self.frame
        return None
    
    def get_latest_frame(self) -> Optional[bytes]:
        """
        Get latest frame without waiting (non-blocking)
        
        Returns:
            bytes: Latest frame or None if no frame available
        """
        with self.condition:
            return self.frame
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get streaming performance metrics
        
        Returns:
            dict: Performance statistics
        """
        current_time = time.time()
        uptime = current_time - self.start_time
        
        return {
            "frames_processed": self.frame_count,
            "total_bytes": self.total_bytes,
            "uptime_seconds": uptime,
            "average_fps": self.frame_count / uptime if uptime > 0 else 0.0,
            "average_frame_size_kb": self.avg_frame_size / 1024 if self.avg_frame_size > 0 else 0,
            "max_frame_size_kb": self.max_frame_size / 1024,
            "last_frame_time": self.last_frame_time,
            "time_since_last_frame": current_time - self.last_frame_time if self.last_frame_time > 0 else 0,
            "memory_efficiency": {
                "avg_frame_size": self.avg_frame_size,
                "max_frame_size": self.max_frame_size,
                "memory_pressure": "low" if self.max_frame_size < 100000 else "high"  # <100KB = low
            }
        }
    
    def clear_metrics(self):
        """Clear performance metrics"""
        self.frame_count = 0
        self.total_bytes = 0
        self.start_time = time.time()
        self.max_frame_size = 0
        self.avg_frame_size = 0
        print("🧹 OptimizedStreamingOutput metrics cleared")
    
    def is_active(self) -> bool:
        """
        Check if stream is actively receiving frames
        
        Returns:
            bool: True if received frame in last 5 seconds
        """
        if self.last_frame_time == 0:
            return False
        return (time.time() - self.last_frame_time) < 5.0
    
    def get_status_summary(self) -> str:
        """
        Get human-readable status summary
        
        Returns:
            str: Status summary
        """
        metrics = self.get_performance_metrics()
        
        return (
            f"Frames: {metrics['frames_processed']} | "
            f"FPS: {metrics['average_fps']:.1f} | "
            f"Avg Size: {metrics['average_frame_size_kb']:.1f}KB | "
            f"Active: {'Yes' if self.is_active() else 'No'}"
        )


class LegacyCompatibilityWrapper:
    """
    Wrapper to maintain compatibility with any legacy code expecting the old interface
    """
    
    def __init__(self, optimized_output: OptimizedStreamingOutput):
        self.optimized_output = optimized_output
    
    def get_performance_metrics(self):
        """Legacy method compatibility"""
        return self.optimized_output.get_performance_metrics()
    
    def reset_performance_counters(self):
        """Legacy method compatibility"""
        self.optimized_output.clear_metrics()