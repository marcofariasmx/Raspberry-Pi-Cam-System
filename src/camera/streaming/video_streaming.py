"""
Video Streaming and Frame Management

Handles MJPEG video streaming with adaptive frame broadcasting,
network performance tracking, and delivery optimization.
"""

import io
import time
from typing import Optional


class StreamOutput(io.BufferedIOBase):
    """
    Adaptive latest frame broadcast system with network performance tracking
    
    Enhanced to support adaptive streaming by monitoring frame delivery performance
    and providing metrics for quality/frame rate adjustment decisions.
    
    This class handles:
    - Latest frame storage and broadcasting
    - Network performance monitoring
    - Frame delivery timing analysis
    - Adaptive streaming metrics collection
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
        """
        Write new frame data with performance tracking
        
        Args:
            buf: Frame data buffer
            
        Returns:
            int: Number of bytes written
        """
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
        
        return len(buf) if buf else 0
    
    def get_latest_frame(self):
        """
        Get the most recent frame with delivery tracking
        
        Returns:
            bytes: Latest frame data or None if no frame available
        """
        if self.frame_ready:
            self.frames_delivered += 1
            return self.latest_frame
        return None
    
    def record_delivery_time(self, delivery_time: float):
        """
        Record frame delivery time for performance monitoring
        
        Args:
            delivery_time: Time taken to deliver frame (seconds)
        """
        self.delivery_times.append(delivery_time)
        
        # Keep only recent samples
        if len(self.delivery_times) > self.max_delivery_samples:
            self.delivery_times.pop(0)
        
        # Track slow deliveries (>4 seconds indicates network issues)
        if delivery_time > 4.0:
            self.slow_deliveries += 1
    
    def get_average_frame_interval(self) -> float:
        """
        Get average time between frames (for adaptive frame rate)
        
        Returns:
            float: Average frame interval in seconds (~30fps = 0.033)
        """
        if not self.frame_intervals:
            return 0.033  # Default ~30fps
        return sum(self.frame_intervals) / len(self.frame_intervals)
    
    def get_average_delivery_time(self) -> float:
        """
        Get average frame delivery time
        
        Returns:
            float: Average delivery time in seconds
        """
        if not self.delivery_times:
            return 0.0
        return sum(self.delivery_times) / len(self.delivery_times)
    
    def is_network_slow(self, threshold: float = 1.0) -> bool:
        """
        Check if network performance indicates slow conditions
        
        Args:
            threshold: Delivery time threshold in seconds
            
        Returns:
            bool: True if network appears slow
        """
        avg_delivery = self.get_average_delivery_time()
        return avg_delivery > threshold or self.slow_deliveries > 3
    
    def get_performance_metrics(self) -> dict:
        """
        Get comprehensive performance metrics
        
        Returns:
            dict: Performance metrics including frame counts, timing, and network status
        """
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
    
    def get_frame_count(self) -> int:
        """
        Get total frames written (for monitoring)
        
        Returns:
            int: Total number of frames written
        """
        return self.frames_written
    
    @property
    def max_frames(self) -> int:
        """
        Return 1 for compatibility with status reporting
        
        Returns:
            int: Always returns 1 (latest frame only)
        """
        return 1
    
    def get_buffer_status(self) -> dict:
        """
        Get current buffer status information
        
        Returns:
            dict: Buffer status including frame availability and timing
        """
        current_time = time.time()
        time_since_last_frame = current_time - self.last_frame_time if self.last_frame_time else 0
        
        return {
            "frame_ready": self.frame_ready,
            "latest_frame_size": len(self.latest_frame) if self.latest_frame else 0,
            "time_since_last_frame": time_since_last_frame,
            "frame_age": time_since_last_frame,
            "frames_in_buffer": 1 if self.frame_ready else 0
        }
    
    def is_frame_stale(self, max_age: float = 5.0) -> bool:
        """
        Check if the current frame is stale (too old)
        
        Args:
            max_age: Maximum frame age in seconds
            
        Returns:
            bool: True if frame is older than max_age
        """
        if not self.last_frame_time:
            return True
        
        age = time.time() - self.last_frame_time
        return age > max_age
    
    def mark_frame_dropped(self):
        """Mark a frame as dropped (for statistics)"""
        self.frames_dropped += 1
    
    def get_delivery_stats(self) -> dict:
        """
        Get detailed delivery statistics
        
        Returns:
            dict: Delivery performance statistics
        """
        total_attempts = self.frames_delivered + self.frames_dropped
        success_rate = (self.frames_delivered / total_attempts) if total_attempts > 0 else 0.0
        
        return {
            "total_delivery_attempts": total_attempts,
            "successful_deliveries": self.frames_delivered,
            "dropped_frames": self.frames_dropped,
            "success_rate": success_rate,
            "slow_deliveries": self.slow_deliveries,
            "average_delivery_time": self.get_average_delivery_time(),
            "samples_collected": len(self.delivery_times)
        }


class FrameGenerator:
    """
    Generates frames for MJPEG streaming with adaptive frame rate control
    
    Handles the streaming response generation with configurable frame rates
    and performance monitoring.
    """
    
    def __init__(self, stream_output: StreamOutput, target_frame_rate: int = 30):
        self.stream_output = stream_output
        self.target_frame_rate = target_frame_rate
        self.frames_sent = 0
        self.frames_dropped = 0
        self.is_active = False
    
    def generate_frames(self):
        """
        Generate frames for MJPEG streaming with adaptive frame rate
        
        Yields:
            bytes: MJPEG frame data with appropriate headers
        """
        print(f"🎬 Starting frame generation (target: {self.target_frame_rate} fps)")
        self.is_active = True
        
        while self.is_active and self.stream_output:
            try:
                frame_start_time = time.time()
                
                # Get the latest available frame
                frame = self.stream_output.get_latest_frame()
                
                if frame:
                    # Calculate adaptive frame rate delay
                    target_interval = 1.0 / max(self.target_frame_rate, 1)
                    
                    # Yield frame with MJPEG headers
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                    
                    self.frames_sent += 1
                    
                    # Record delivery time for performance monitoring
                    delivery_time = time.time() - frame_start_time
                    self.stream_output.record_delivery_time(delivery_time)
                    
                    # Adaptive delay based on current frame rate setting
                    time.sleep(target_interval)
                else:
                    # No frame available - brief pause
                    self.frames_dropped += 1
                    self.stream_output.mark_frame_dropped()
                    time.sleep(0.01)
                        
            except Exception as e:
                print(f"❌ Frame generation error: {e}")
                break
        
        self.is_active = False
        print("🔚 Frame generation ended")
    
    def stop(self):
        """Stop frame generation"""
        self.is_active = False
    
    def update_frame_rate(self, new_frame_rate: int):
        """
        Update target frame rate
        
        Args:
            new_frame_rate: New target frame rate in fps
        """
        self.target_frame_rate = max(1, min(new_frame_rate, 60))  # Clamp between 1-60 fps
        print(f"📊 Frame rate updated to {self.target_frame_rate} fps")
    
    def get_generation_stats(self) -> dict:
        """
        Get frame generation statistics
        
        Returns:
            dict: Generation statistics
        """
        total_attempts = self.frames_sent + self.frames_dropped
        success_rate = (self.frames_sent / total_attempts) if total_attempts > 0 else 0.0
        
        return {
            "is_active": self.is_active,
            "target_frame_rate": self.target_frame_rate,
            "frames_sent": self.frames_sent,
            "frames_dropped": self.frames_dropped,
            "total_attempts": total_attempts,
            "success_rate": success_rate
        }
