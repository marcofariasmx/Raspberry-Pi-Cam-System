"""
Multi-Quality Frame Producer
Efficient streaming system that produces multiple JPEG quality levels
from a single camera frame for per-client adaptive streaming.
Enhanced with memory pools for Pi Zero 2W optimization.
"""

import io
import time
import threading
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass

from .memory_pool import MultiSizeBufferPool

# Import picamera2 with graceful fallback
try:
    from picamera2.encoders import JpegEncoder # type: ignore
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False
    class JpegEncoder:
        def __init__(self, q=85): 
            self.quality = q
        def encode(self, request, name): 
            return b"mock_jpeg_data"


@dataclass
class QualityFrame:
    """Represents a frame at a specific quality level"""
    data: bytes
    quality: int
    timestamp: float
    size: int
    
    def age(self) -> float:
        """Get frame age in seconds"""
        return time.time() - self.timestamp
    
    def __post_init__(self):
        if not self.size and self.data:
            self.size = len(self.data)


class MultiQualityFrameProducer:
    """
    Efficient multi-quality frame producer for adaptive streaming
    
    Produces 4 quality levels (30%, 50%, 70%, 85%) from each camera frame
    and stores only the current frame at each quality level to minimize memory usage.
    """
    
    def __init__(self, quality_levels: Optional[list] = None):
        """
        Initialize multi-quality frame producer with memory pool optimization
        
        Args:
            quality_levels: List of JPEG quality percentages (default: [30, 50, 70, 85])
        """
        self.quality_levels = quality_levels or [30, 50, 70, 85]
        self.quality_levels.sort()  # Ensure ascending order
        
        # Initialize memory pools for different frame sizes
        # Optimized for Pi Zero 2W memory constraints
        self.buffer_pools = MultiSizeBufferPool({
            "small": (16384, 4),    # 16KB × 4 for low quality frames
            "medium": (32768, 6),   # 32KB × 6 for medium quality frames  
            "large": (65536, 4),    # 64KB × 4 for high quality frames
            "xlarge": (131072, 2)   # 128KB × 2 for extra large frames
        })
        
        # Current frames at each quality level (only store latest)
        self.current_frames: Dict[int, QualityFrame] = {}
        self.frame_buffers: Dict[int, tuple] = {}  # Track (buffer, pool_name) for cleanup
        self._lock = threading.RLock()
        
        # Frame ready notification system
        self.frame_ready_condition = threading.Condition()
        self.latest_frame_timestamp = 0.0
        
        # Performance tracking
        self.total_frames_produced = 0
        self.total_bytes_produced = 0
        self.production_start_time = time.time()
        self.last_frame_time = 0.0
        
        # Quality encoders (create once, reuse)
        self.encoders: Dict[int, JpegEncoder] = {}
        self._initialize_encoders()
        
        print(f"🎬 MultiQualityFrameProducer initialized with quality levels: {self.quality_levels}")
        print(f"🧠 Memory pools initialized for optimal Pi Zero 2W performance")
    
    def _initialize_encoders(self):
        """Initialize JPEG encoders for each quality level"""
        if not PICAMERA2_AVAILABLE:
            print("⚠️  Using mock encoders (Picamera2 not available)")
            for quality in self.quality_levels:
                self.encoders[quality] = JpegEncoder(q=quality)
            return
        
        for quality in self.quality_levels:
            self.encoders[quality] = JpegEncoder(q=quality)
            print(f"📷 JPEG encoder created for quality {quality}%")
    
    def produce_frame(self, raw_frame_data: bytes) -> bool:
        """
        Produce multiple quality versions of a frame using memory pools
        
        Args:
            raw_frame_data: Raw frame data from camera (already hardware MJPEG encoded)
            
        Returns:
            bool: True if frame was produced successfully
        """
        if not raw_frame_data:
            return False
        
        current_time = time.time()
        
        with self._lock:
            # Return previous frame buffers to pool
            self._return_previous_buffers()
            
            # Clear previous frames to maintain minimal memory footprint
            self.current_frames.clear()
            self.frame_buffers.clear()
            
            # Since we're receiving hardware-encoded MJPEG, we need to re-encode
            # at different quality levels. In production, this would use ISP scaling.
            success_count = 0
            
            for quality in self.quality_levels:
                try:
                    # Estimate required buffer size based on quality
                    estimated_size = int(len(raw_frame_data) * (quality / 100.0))
                    
                    # Get optimally sized buffer from pool
                    buffer, pool_name = self.buffer_pools.get_optimal_buffer(estimated_size + 1024)  # +1KB safety margin
                    
                    # For development/testing, simulate different quality encoding
                    if not PICAMERA2_AVAILABLE:
                        # Simulate quality reduction by truncating data
                        reduction_factor = quality / 100.0
                        simulated_size = int(len(raw_frame_data) * reduction_factor)
                        encoded_size = min(simulated_size, len(buffer) - 2)
                        
                        # Copy data to pooled buffer
                        buffer[:encoded_size] = raw_frame_data[:encoded_size]
                        buffer[encoded_size:encoded_size+2] = b'\xff\xd9'  # Add JPEG end marker
                        
                        encoded_data = bytes(buffer[:encoded_size+2])
                    else:
                        # In production: Use hardware re-encoding at different qualities
                        # For now, simulate by copying and truncating
                        reduction_factor = quality / 100.0
                        simulated_size = int(len(raw_frame_data) * reduction_factor)
                        encoded_size = min(simulated_size, len(buffer))
                        
                        # Copy to pooled buffer
                        buffer[:encoded_size] = raw_frame_data[:encoded_size]
                        encoded_data = bytes(buffer[:encoded_size])
                    
                    # Store the encoded frame (keeping reference to original data)
                    quality_frame = QualityFrame(
                        data=encoded_data,
                        quality=quality,
                        timestamp=current_time,
                        size=len(encoded_data)
                    )
                    
                    self.current_frames[quality] = quality_frame
                    self.frame_buffers[quality] = (buffer, pool_name)
                    success_count += 1
                    
                except Exception as e:
                    print(f"❌ Failed to encode frame at quality {quality}%: {e}")
                    continue
            
            # Update statistics
            if success_count > 0:
                self.total_frames_produced += 1
                self.total_bytes_produced += sum(frame.size for frame in self.current_frames.values())
                self.last_frame_time = current_time
                
                # Notify waiting threads that new frames are ready
                with self.frame_ready_condition:
                    self.latest_frame_timestamp = current_time
                    self.frame_ready_condition.notify_all()
            
            return success_count > 0
    
    def _return_previous_buffers(self):
        """Return previous frame buffers to memory pools"""
        for quality, (buffer, pool_name) in self.frame_buffers.items():
            self.buffer_pools.return_buffer(buffer, pool_name)
    
    def wait_for_new_frame(self, timeout: float = 1.0) -> bool:
        """
        Wait for a new frame to be available using threading.Condition
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            bool: True if new frame is available
        """
        current_timestamp = self.latest_frame_timestamp
        
        with self.frame_ready_condition:
            return self.frame_ready_condition.wait_for(
                lambda: self.latest_frame_timestamp > current_timestamp,
                timeout=timeout
            )
    
    def get_frame(self, target_quality: int, max_age: float = 2.0) -> Optional[QualityFrame]:
        """
        Get frame at closest available quality level
        
        Args:
            target_quality: Desired quality percentage
            max_age: Maximum acceptable frame age in seconds
            
        Returns:
            QualityFrame: Frame at closest quality or None if not available
        """
        with self._lock:
            if not self.current_frames:
                return None
            
            # Find closest quality level
            closest_quality = min(self.quality_levels, 
                                key=lambda q: abs(q - target_quality))
            
            frame = self.current_frames.get(closest_quality)
            if not frame:
                return None
            
            # Check frame age
            if frame.age() > max_age:
                return None
            
            return frame
    
    def get_best_frame(self, max_age: float = 2.0) -> Optional[QualityFrame]:
        """
        Get highest quality frame available
        
        Args:
            max_age: Maximum acceptable frame age in seconds
            
        Returns:
            QualityFrame: Highest quality frame or None if not available
        """
        return self.get_frame(max(self.quality_levels), max_age)
    
    def get_available_qualities(self) -> list:
        """
        Get list of currently available quality levels
        
        Returns:
            list: Available quality percentages
        """
        with self._lock:
            return list(self.current_frames.keys())
    
    def get_frame_info(self, quality: int) -> Optional[Dict[str, Any]]:
        """
        Get information about frame at specific quality
        
        Args:
            quality: Quality level to check
            
        Returns:
            dict: Frame information or None if not available
        """
        with self._lock:
            frame = self.current_frames.get(quality)
            if not frame:
                return None
            
            return {
                "quality": frame.quality,
                "size": frame.size,
                "timestamp": frame.timestamp,
                "age": frame.age()
            }
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """
        Get current memory usage statistics including memory pool efficiency
        
        Returns:
            dict: Memory usage information with pool metrics
        """
        with self._lock:
            total_size = sum(frame.size for frame in self.current_frames.values())
            
            # Get memory pool metrics
            pool_metrics = self.buffer_pools.get_combined_metrics()
            
            return {
                "total_memory_bytes": total_size,
                "total_memory_kb": total_size / 1024,
                "total_memory_mb": total_size / (1024 * 1024),
                "frames_stored": len(self.current_frames),
                "quality_levels": list(self.current_frames.keys()),
                "frame_sizes": {q: f.size for q, f in self.current_frames.items()},
                "memory_pools": {
                    "total_pool_memory_kb": pool_metrics["overall"]["total_memory_kb"],
                    "pool_hit_rate_percent": pool_metrics["overall"]["hit_rate_percent"],
                    "memory_saved_kb": pool_metrics["overall"]["total_saved_kb"],
                    "pool_efficiency": "excellent" if pool_metrics["overall"]["hit_rate_percent"] > 80 
                                    else "good" if pool_metrics["overall"]["hit_rate_percent"] > 60
                                    else "needs_optimization"
                }
            }
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive performance statistics including memory pool efficiency
        
        Returns:
            dict: Performance metrics with memory optimization data
        """
        current_time = time.time()
        uptime = current_time - self.production_start_time
        
        with self._lock:
            # Get memory usage with pool metrics
            memory_usage = self.get_memory_usage()
            
            return {
                "total_frames_produced": self.total_frames_produced,
                "total_bytes_produced": self.total_bytes_produced,
                "uptime_seconds": uptime,
                "average_fps": self.total_frames_produced / uptime if uptime > 0 else 0.0,
                "average_frame_size": (
                    self.total_bytes_produced / (self.total_frames_produced * len(self.quality_levels))
                    if self.total_frames_produced > 0 else 0
                ),
                "last_frame_time": self.last_frame_time,
                "time_since_last_frame": current_time - self.last_frame_time if self.last_frame_time > 0 else 0,
                "quality_levels_configured": self.quality_levels,
                "memory_usage": memory_usage,
                "optimization_status": {
                    "memory_pools_active": True,
                    "threading_condition_enabled": True,
                    "buffer_reuse_efficiency": memory_usage["memory_pools"]["pool_efficiency"],
                    "pi_zero_optimized": memory_usage["total_memory_kb"] < 400  # Target <400KB
                }
            }
    
    def clear_frames(self):
        """Clear all current frames and return buffers to pool"""
        with self._lock:
            # Return buffers to pool before clearing
            self._return_previous_buffers()
            self.current_frames.clear()
            self.frame_buffers.clear()
    
    def update_quality_levels(self, new_levels: list) -> bool:
        """
        Update quality levels (requires re-initialization of encoders)
        
        Args:
            new_levels: New list of quality percentages
            
        Returns:
            bool: True if update was successful
        """
        try:
            with self._lock:
                # Validate quality levels
                if not all(10 <= q <= 100 for q in new_levels):
                    print("❌ Invalid quality levels: must be between 10-100")
                    return False
                
                # Clear current frames and update levels
                self.current_frames.clear()
                self.quality_levels = sorted(new_levels)
                
                # Re-initialize encoders
                self.encoders.clear()
                self._initialize_encoders()
                
                print(f"✅ Quality levels updated to: {self.quality_levels}")
                return True
                
        except Exception as e:
            print(f"❌ Failed to update quality levels: {e}")
            return False
    
    def is_frame_available(self, max_age: float = 2.0) -> bool:
        """
        Check if any frame is available within age limit
        
        Args:
            max_age: Maximum acceptable frame age in seconds
            
        Returns:
            bool: True if fresh frame is available
        """
        with self._lock:
            if not self.current_frames:
                return False
            
            # Check if any frame is fresh enough
            return any(frame.age() <= max_age for frame in self.current_frames.values())
    
    def get_status_summary(self) -> str:
        """
        Get human-readable status summary
        
        Returns:
            str: Status summary
        """
        stats = self.get_performance_stats()
        memory = stats["memory_usage"]
        
        return (
            f"Frames: {stats['total_frames_produced']} | "
            f"FPS: {stats['average_fps']:.1f} | "
            f"Memory: {memory['total_memory_kb']:.1f}KB | "
            f"Qualities: {len(self.quality_levels)} levels"
        )