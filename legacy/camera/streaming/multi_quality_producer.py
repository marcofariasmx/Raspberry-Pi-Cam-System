"""
Multi-Quality Frame Producer
Efficient streaming system that produces multiple JPEG quality levels
from a single camera frame for per-client adaptive streaming.
"""

import io
import time
import threading
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass

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
        Initialize multi-quality frame producer
        
        Args:
            quality_levels: List of JPEG quality percentages (default: [30, 50, 70, 85])
        """
        self.quality_levels = quality_levels or [30, 50, 70, 85]
        self.quality_levels.sort()  # Ensure ascending order
        
        # Current frames at each quality level (only store latest)
        self.current_frames: Dict[int, QualityFrame] = {}
        self._lock = threading.RLock()
        
        # Performance tracking
        self.total_frames_produced = 0
        self.total_bytes_produced = 0
        self.production_start_time = time.time()
        self.last_frame_time = 0.0
        
        # Quality encoders (create once, reuse)
        self.encoders: Dict[int, JpegEncoder] = {}
        self._initialize_encoders()
        
        print(f"🎬 MultiQualityFrameProducer initialized with quality levels: {self.quality_levels}")
    
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
        Produce multiple quality versions of a frame
        
        Args:
            raw_frame_data: Raw frame data from camera
            
        Returns:
            bool: True if frame was produced successfully
        """
        if not raw_frame_data:
            return False
        
        current_time = time.time()
        
        with self._lock:
            # Clear previous frames to maintain minimal memory footprint
            self.current_frames.clear()
            
            # Encode frame at each quality level
            for quality in self.quality_levels:
                try:
                    # For development/testing, simulate different quality encoding
                    if not PICAMERA2_AVAILABLE:
                        # Simulate quality reduction by truncating data
                        reduction_factor = quality / 100.0
                        simulated_size = int(len(raw_frame_data) * reduction_factor)
                        encoded_data = raw_frame_data[:simulated_size] + b'\xff\xd9'  # Add JPEG end marker
                    else:
                        # Use actual Picamera2 encoder
                        # Note: This is a simplified version - real implementation would need
                        # proper integration with Picamera2's encoding pipeline
                        encoded_data = raw_frame_data  # Placeholder for actual encoding
                    
                    # Store the encoded frame
                    quality_frame = QualityFrame(
                        data=encoded_data,
                        quality=quality,
                        timestamp=current_time,
                        size=len(encoded_data)
                    )
                    
                    self.current_frames[quality] = quality_frame
                    
                except Exception as e:
                    print(f"❌ Failed to encode frame at quality {quality}%: {e}")
                    continue
            
            # Update statistics
            self.total_frames_produced += 1
            self.total_bytes_produced += sum(frame.size for frame in self.current_frames.values())
            self.last_frame_time = current_time
            
            return len(self.current_frames) > 0
    
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
        Get current memory usage statistics
        
        Returns:
            dict: Memory usage information
        """
        with self._lock:
            total_size = sum(frame.size for frame in self.current_frames.values())
            
            return {
                "total_memory_bytes": total_size,
                "total_memory_kb": total_size / 1024,
                "total_memory_mb": total_size / (1024 * 1024),
                "frames_stored": len(self.current_frames),
                "quality_levels": list(self.current_frames.keys()),
                "frame_sizes": {q: f.size for q, f in self.current_frames.items()}
            }
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics
        
        Returns:
            dict: Performance metrics
        """
        current_time = time.time()
        uptime = current_time - self.production_start_time
        
        with self._lock:
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
                "memory_usage": self.get_memory_usage()
            }
    
    def clear_frames(self):
        """Clear all current frames"""
        with self._lock:
            self.current_frames.clear()
    
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