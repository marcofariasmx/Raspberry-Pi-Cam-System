"""
Shared Frame Queue for Multi-Client Streaming

Thread-safe frame queue that enables multiple clients to consume frames
independently without blocking the camera frame production.
"""

import time
import threading
from collections import deque
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from uuid import uuid4


@dataclass
class FrameMetadata:
    """
    Metadata for frames in the queue
    
    Tracks frame information for performance monitoring and debugging.
    """
    frame_id: str
    timestamp: float
    quality_level: int
    size: int
    producer_info: str = "camera"
    
    def age(self) -> float:
        """Get frame age in seconds"""
        return time.time() - self.timestamp
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "quality_level": self.quality_level,
            "size": self.size,
            "producer_info": self.producer_info,
            "age": self.age()
        }


@dataclass
class QueuedFrame:
    """
    A frame with its metadata in the queue
    """
    data: bytes
    metadata: FrameMetadata
    
    def __post_init__(self):
        """Update metadata size based on actual data"""
        if self.data:
            self.metadata.size = len(self.data)


class SharedFrameQueue:
    """
    Thread-safe frame queue for multi-client streaming
    
    Provides non-blocking frame production with automatic overflow management.
    Multiple clients can consume frames independently without affecting each other.
    """
    
    def __init__(self, max_size: int = 10):
        """
        Initialize shared frame queue
        
        Args:
            max_size: Maximum number of frames in queue (auto-overflow when exceeded)
        """
        self.max_size = max_size
        self._queue = deque(maxlen=max_size)
        self._lock = threading.RLock()
        
        # Performance tracking
        self.total_frames_added = 0
        self.total_frames_consumed = 0
        self.overflow_count = 0
        self.last_frame_time = 0.0
        
        # Queue statistics
        self.peak_size = 0
        self.creation_time = time.time()
        
        # Frame tracking for diagnostics
        self._frame_id_counter = 0
        self.last_overflow_time = 0.0
    
    def put_frame(self, frame_data: bytes, quality_level: int = 85, producer_info: str = "camera") -> bool:
        """
        Add frame to queue (non-blocking)
        
        Args:
            frame_data: Raw frame bytes
            quality_level: JPEG quality level used for this frame
            producer_info: Information about frame producer
            
        Returns:
            bool: True if frame was added, False if queue is full (shouldn't happen with deque)
        """
        if not frame_data:
            return False
        
        current_time = time.time()
        
        with self._lock:
            # Check if we're about to overflow (before adding)
            was_at_capacity = len(self._queue) >= self.max_size
            
            # Create frame metadata
            self._frame_id_counter += 1
            metadata = FrameMetadata(
                frame_id=f"frame_{self._frame_id_counter}",
                timestamp=current_time,
                quality_level=quality_level,
                size=len(frame_data),
                producer_info=producer_info
            )
            
            # Add frame (deque automatically removes oldest if at maxlen)
            queued_frame = QueuedFrame(frame_data, metadata)
            self._queue.append(queued_frame)
            
            # Update statistics
            self.total_frames_added += 1
            self.last_frame_time = current_time
            self.peak_size = max(self.peak_size, len(self._queue))
            
            # Track overflow
            if was_at_capacity:
                self.overflow_count += 1
                self.last_overflow_time = current_time
            
            return True
    
    def get_frame(self, max_age: float = 5.0) -> Optional[QueuedFrame]:
        """
        Get latest frame from queue (non-blocking)
        
        Args:
            max_age: Maximum acceptable frame age in seconds
            
        Returns:
            QueuedFrame: Latest frame or None if no suitable frame available
        """
        with self._lock:
            if not self._queue:
                return None
            
            # Get the latest frame (most recent)
            latest_frame = self._queue[-1]
            
            # Check if frame is too old
            if latest_frame.metadata.age() > max_age:
                return None
            
            # Update consumption statistics
            self.total_frames_consumed += 1
            
            return latest_frame
    
    def get_oldest_frame(self, max_age: float = 5.0) -> Optional[QueuedFrame]:
        """
        Get oldest frame from queue and remove it (FIFO)
        
        Args:
            max_age: Maximum acceptable frame age in seconds
            
        Returns:
            QueuedFrame: Oldest frame or None if no suitable frame available
        """
        with self._lock:
            if not self._queue:
                return None
            
            # Get the oldest frame
            oldest_frame = self._queue.popleft()
            
            # Check if frame is too old
            if oldest_frame.metadata.age() > max_age:
                return None
            
            # Update consumption statistics
            self.total_frames_consumed += 1
            
            return oldest_frame
    
    def peek_latest_frame(self) -> Optional[FrameMetadata]:
        """
        Peek at latest frame metadata without consuming
        
        Returns:
            FrameMetadata: Metadata of latest frame or None if queue empty
        """
        with self._lock:
            if not self._queue:
                return None
            return self._queue[-1].metadata
    
    def get_queue_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive queue performance metrics
        
        Returns:
            dict: Queue performance metrics
        """
        current_time = time.time()
        
        with self._lock:
            queue_size = len(self._queue)
            
            # Calculate rates
            elapsed_time = current_time - self.creation_time
            add_rate = self.total_frames_added / elapsed_time if elapsed_time > 0 else 0.0
            consume_rate = self.total_frames_consumed / elapsed_time if elapsed_time > 0 else 0.0
            
            # Calculate overflow rate (key metric for adaptation)
            overflow_rate = self.overflow_count / self.total_frames_added if self.total_frames_added > 0 else 0.0
            
            # Queue pressure analysis
            utilization = queue_size / self.max_size if self.max_size > 0 else 0.0
            
            # Time since last activity
            time_since_last_frame = current_time - self.last_frame_time if self.last_frame_time > 0 else 0.0
            time_since_last_overflow = current_time - self.last_overflow_time if self.last_overflow_time > 0 else float('inf')
            
            return {
                # Core metrics
                "queue_size": queue_size,
                "max_size": self.max_size,
                "utilization": utilization,
                "overflow_rate": overflow_rate,  # PRIMARY METRIC for adaptation
                
                # Frame statistics
                "total_frames_added": self.total_frames_added,
                "total_frames_consumed": self.total_frames_consumed,
                "overflow_count": self.overflow_count,
                "peak_size": self.peak_size,
                
                # Rate statistics
                "add_rate": add_rate,
                "consume_rate": consume_rate,
                "net_rate": add_rate - consume_rate,
                
                # Timing information
                "uptime": elapsed_time,
                "time_since_last_frame": time_since_last_frame,
                "time_since_last_overflow": time_since_last_overflow,
                "last_frame_time": self.last_frame_time,
                
                # Queue health indicators
                "is_healthy": overflow_rate < 0.3,  # Less than 30% overflow
                "is_under_pressure": overflow_rate > 0.7,  # More than 70% overflow
                "is_critical": overflow_rate > 0.9,  # More than 90% overflow
                "has_recent_activity": time_since_last_frame < 5.0
            }
    
    def get_frame_history(self, count: int = 5) -> List[Dict[str, Any]]:
        """
        Get metadata for recent frames in queue
        
        Args:
            count: Maximum number of frames to return
            
        Returns:
            List[Dict]: List of frame metadata dictionaries
        """
        with self._lock:
            frames = list(self._queue)[-count:] if count > 0 else list(self._queue)
            return [frame.metadata.to_dict() for frame in frames]
    
    def clear(self):
        """Clear all frames from queue"""
        with self._lock:
            self._queue.clear()
    
    def resize(self, new_max_size: int):
        """
        Resize the queue (may trigger overflow)
        
        Args:
            new_max_size: New maximum queue size
        """
        with self._lock:
            old_size = self.max_size
            self.max_size = new_max_size
            
            # Create new deque with new size
            new_queue = deque(self._queue, maxlen=new_max_size)
            
            # Track overflow if we had to drop frames
            dropped_frames = len(self._queue) - len(new_queue)
            if dropped_frames > 0:
                self.overflow_count += dropped_frames
                self.last_overflow_time = time.time()
            
            self._queue = new_queue
            
            print(f"📏 Queue resized from {old_size} to {new_max_size} (dropped {dropped_frames} frames)")
    
    def get_status_summary(self) -> str:
        """
        Get human-readable status summary
        
        Returns:
            str: Status summary
        """
        metrics = self.get_queue_metrics()
        
        status_parts = [
            f"Queue: {metrics['queue_size']}/{metrics['max_size']}",
            f"Overflow: {metrics['overflow_rate']:.1%}",
            f"Rates: +{metrics['add_rate']:.1f} -{metrics['consume_rate']:.1f} fps"
        ]
        
        if metrics['is_critical']:
            status_parts.append("🚨 CRITICAL")
        elif metrics['is_under_pressure']:
            status_parts.append("⚠️ PRESSURE")
        elif metrics['is_healthy']:
            status_parts.append("✅ HEALTHY")
        
        return " | ".join(status_parts)
    
    def __len__(self) -> int:
        """Get current queue size"""
        return len(self._queue)
    
    def __bool__(self) -> bool:
        """Check if queue has frames"""
        return len(self._queue) > 0
