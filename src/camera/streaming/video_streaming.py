"""
Video Streaming and Frame Management

Handles MJPEG video streaming with adaptive frame broadcasting,
network performance tracking, and delivery optimization.

Enhanced with queue-based multi-client architecture while maintaining
backward compatibility with legacy single-client streaming.
"""

import io
import time
from typing import Optional, Generator, TYPE_CHECKING

# Import new queue-based components
try:
    from .shared_frame_queue import SharedFrameQueue, FrameMetadata
    from .client_stream_manager import ClientStreamManager
    QUEUE_COMPONENTS_AVAILABLE = True
except ImportError:
    QUEUE_COMPONENTS_AVAILABLE = False
    # Define fallback classes to ensure names are bound
    SharedFrameQueue = None
    FrameMetadata = None
    ClientStreamManager = None
    print("⚠️ Queue components not available - using legacy streaming mode")

# Type checking imports
if TYPE_CHECKING:
    from .shared_frame_queue import SharedFrameQueue as SharedFrameQueueType
    from .client_stream_manager import ClientStreamManager as ClientStreamManagerType
else:
    SharedFrameQueueType = object
    ClientStreamManagerType = object


class StreamOutput(io.BufferedIOBase):
    """
    Adaptive latest frame broadcast system with network performance tracking
    
    Enhanced to support adaptive streaming by monitoring frame delivery performance
    and providing metrics for quality/frame rate adjustment decisions.
    
    Now supports both legacy single-client mode and new queue-based multi-client mode.
    
    This class handles:
    - Latest frame storage and broadcasting (legacy mode)
    - Queue-based multi-client streaming (new mode)
    - Network performance monitoring
    - Frame delivery timing analysis
    - Adaptive streaming metrics collection
    """
    
    def __init__(self, use_queue: bool = True, queue_size: int = 10):
        # Frame storage (universal optimization for legacy compatibility)
        self.latest_frame = None
        self.frame_ready = False
        self.frames_written = 0
        
        # Queue-based streaming (new architecture)
        self.use_queue = use_queue and QUEUE_COMPONENTS_AVAILABLE
        if self.use_queue and SharedFrameQueue is not None and ClientStreamManager is not None:
            self.shared_queue = SharedFrameQueue(max_size=queue_size)
            self.client_manager = ClientStreamManager(self.shared_queue)
            print(f"🔄 StreamOutput using queue-based architecture (size: {queue_size})")
        else:
            self.shared_queue = None
            self.client_manager = None
            self.use_queue = False  # Ensure queue mode is disabled if components unavailable
            print("📺 StreamOutput using legacy latest-frame architecture")
        
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
        if not buf:
            return 0
            
        current_time = time.time()
        
        # Track frame intervals for adaptive frame rate
        if self.last_frame_time > 0:
            interval = current_time - self.last_frame_time
            self.frame_intervals.append(interval)
            
            # Keep only recent samples
            if len(self.frame_intervals) > self.max_interval_samples:
                self.frame_intervals.pop(0)
        
        # Store frame for legacy mode (always maintain for backward compatibility)
        self.latest_frame = buf
        self.frame_ready = True
        self.frames_written += 1
        self.last_frame_time = current_time
        
        # Also put frame in queue if queue mode is active
        if self.use_queue and self.shared_queue:
            # Get current quality level from frame metadata if available
            quality_level = getattr(self, '_current_quality', 85)
            self.shared_queue.put_frame(buf, quality_level, "camera")
        
        return len(buf)
    
    def set_current_quality(self, quality: int):
        """Set current quality level for frame metadata"""
        self._current_quality = quality
    
    def get_latest_frame(self):
        """
        Get the most recent frame with delivery tracking (legacy mode)
        
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
        base_metrics = {
            "frames_written": self.frames_written,
            "frames_delivered": self.frames_delivered,
            "frames_dropped": self.frames_dropped,
            "average_frame_interval": self.get_average_frame_interval(),
            "average_delivery_time": self.get_average_delivery_time(),
            "slow_deliveries": self.slow_deliveries,
            "network_slow": self.is_network_slow(),
            "streaming_mode": "queue-based" if self.use_queue else "legacy"
        }
        
        # Add queue metrics if available
        if self.use_queue and self.shared_queue:
            queue_metrics = self.shared_queue.get_queue_metrics()
            base_metrics.update({
                "queue_overflow_rate": queue_metrics.get("overflow_rate", 0.0),
                "queue_utilization": queue_metrics.get("utilization", 0.0),
                "queue_size": queue_metrics.get("queue_size", 0),
                "queue_health": {
                    "is_healthy": queue_metrics.get("is_healthy", True),
                    "is_under_pressure": queue_metrics.get("is_under_pressure", False),
                    "is_critical": queue_metrics.get("is_critical", False)
                }
            })
        
        # Add client metrics if available
        if self.use_queue and self.client_manager:
            client_summary = self.client_manager.get_performance_summary()
            base_metrics.update({
                "active_clients": client_summary.get("active_clients", 0),
                "total_consumption_rate": client_summary.get("total_consumption_rate", 0.0),
                "average_delivery_efficiency": client_summary.get("average_delivery_efficiency", 1.0)
            })
        
        return base_metrics
    
    def reset_performance_counters(self):
        """Reset performance counters for fresh measurement"""
        self.frames_delivered = 0
        self.frames_dropped = 0
        self.slow_deliveries = 0
        self.delivery_times.clear()
        
        # Reset queue metrics if available
        if self.use_queue and self.shared_queue:
            # Note: We don't reset the queue itself as it contains active frames
            pass
    
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
        Return buffer size for compatibility with status reporting
        
        Returns:
            int: Buffer size (1 for legacy, queue size for queue mode)
        """
        if self.use_queue and self.shared_queue:
            return self.shared_queue.max_size
        return 1
    
    def get_buffer_status(self) -> dict:
        """
        Get current buffer status information
        
        Returns:
            dict: Buffer status including frame availability and timing
        """
        current_time = time.time()
        time_since_last_frame = current_time - self.last_frame_time if self.last_frame_time else 0
        
        base_status = {
            "frame_ready": self.frame_ready,
            "latest_frame_size": len(self.latest_frame) if self.latest_frame else 0,
            "time_since_last_frame": time_since_last_frame,
            "frame_age": time_since_last_frame,
            "frames_in_buffer": 1 if self.frame_ready else 0,
            "streaming_mode": "queue-based" if self.use_queue else "legacy"
        }
        
        # Add queue status if available
        if self.use_queue and self.shared_queue:
            queue_metrics = self.shared_queue.get_queue_metrics()
            base_status.update({
                "queue_size": queue_metrics.get("queue_size", 0),
                "queue_max_size": queue_metrics.get("max_size", 0),
                "queue_utilization": queue_metrics.get("utilization", 0.0),
                "frames_in_buffer": queue_metrics.get("queue_size", 0)
            })
        
        return base_status
    
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
    
    # Queue-based architecture methods
    def get_client_manager(self) -> Optional['ClientStreamManagerType']:
        """Get the client stream manager for multi-client support"""
        return self.client_manager
    
    def get_shared_queue(self) -> Optional['SharedFrameQueueType']:
        """Get the shared frame queue"""
        return self.shared_queue
    
    def create_client_stream(self, client_id: Optional[str] = None, target_fps: int = 30) -> Optional[Generator[bytes, None, None]]:
        """
        Create a new client stream (queue-based mode only)
        
        Args:
            client_id: Unique client identifier (auto-generated if None)
            target_fps: Target frame rate for this client
            
        Returns:
            Generator: Frame generator for the client, or None if not in queue mode
        """
        if not self.use_queue or not self.client_manager:
            return None
        return self.client_manager.create_client_stream(client_id, target_fps)
    
    def get_queue_metrics(self) -> dict:
        """Get queue performance metrics"""
        if not self.use_queue or not self.shared_queue:
            return {"error": "Queue mode not active"}
        return self.shared_queue.get_queue_metrics()
    
    def get_client_metrics(self) -> dict:
        """Get client performance metrics"""
        if not self.use_queue or not self.client_manager:
            return {"error": "Queue mode not active"}
        return self.client_manager.get_performance_summary()
    
    def is_queue_mode_active(self) -> bool:
        """Check if queue mode is active"""
        return self.use_queue and self.shared_queue is not None
    
    def get_active_client_count(self) -> int:
        """Get number of active clients"""
        if not self.use_queue or not self.client_manager:
            return 0
        return self.client_manager.get_active_client_count()
    
    def disconnect_all_clients(self):
        """Disconnect all active clients (queue mode only)"""
        if self.use_queue and self.client_manager:
            self.client_manager.disconnect_all_clients()


class FrameGenerator:
    """
    Generates frames for MJPEG streaming with adaptive frame rate control
    
    Handles the streaming response generation with configurable frame rates
    and performance monitoring. Supports both legacy and queue-based modes.
    """
    
    def __init__(self, stream_output: StreamOutput, target_frame_rate: int = 30):
        self.stream_output = stream_output
        self.target_frame_rate = target_frame_rate
        self.frames_sent = 0
        self.frames_dropped = 0
        self.is_active = False
        
        # Detect streaming mode
        self.queue_mode = stream_output.is_queue_mode_active()
        mode_str = "queue-based" if self.queue_mode else "legacy"
        print(f"🎬 FrameGenerator initialized ({mode_str} mode)")
    
    def generate_frames(self, client_id: Optional[str] = None):
        """
        Generate frames for MJPEG streaming with adaptive frame rate
        
        Args:
            client_id: Client identifier for queue mode (ignored in legacy mode)
        
        Yields:
            bytes: MJPEG frame data with appropriate headers
        """
        # Identify which session is generating frames
        print(f"🎬 Starting frame generation for '{client_id or 'global'}' (target: {self.target_frame_rate} fps)")
        self.is_active = True
        
        # Use queue-based streaming if available and client_id provided
        if self.queue_mode and client_id:
            client_stream = self.stream_output.create_client_stream(client_id, self.target_frame_rate)
            if client_stream:
                print(f"👤 Using queue-based client stream for '{client_id}'")
                try:
                    for frame in client_stream:
                        if not self.is_active:
                            break
                        yield frame
                        self.frames_sent += 1
                except Exception as e:
                    print(f"❌ Queue-based frame generation error: {e}")
                finally:
                    print(f"🔚 Queue-based frame generation ended for client: {client_id}")
                    self.is_active = False
                return
        
        # Fall back to legacy mode for this client
        print(f"📺 Using legacy frame generation mode for '{client_id or 'global'}'")
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
        print(f"🔚 Legacy frame generation ended for '{client_id or 'global'}'")
    
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
            "success_rate": success_rate,
            "streaming_mode": "queue-based" if self.queue_mode else "legacy"
        }


# Utility function for creating appropriate StreamOutput
def create_stream_output(enable_queue: bool = True, queue_size: int = 10) -> StreamOutput:
    """
    Create a StreamOutput instance with appropriate configuration
    
    Args:
        enable_queue: Whether to enable queue-based streaming
        queue_size: Size of the frame queue
        
    Returns:
        StreamOutput: Configured stream output instance
    """
    return StreamOutput(use_queue=enable_queue, queue_size=queue_size)
