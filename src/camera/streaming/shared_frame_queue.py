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
    
    def __init__(self, max_size: int = 10, session_ttl: float = 300.0):
        """
        Initialize shared frame queue with per-client queues
        Args:
            max_size: Maximum number of frames per client queue
            session_ttl: Time in seconds to expire inactive clients
        """
        self.max_size = max_size
        # Per-client frame deques
        self.client_queues: Dict[str, deque] = {}
        # Last access timestamps for TTL
        self.client_last_seen: Dict[str, float] = {}
        self.session_ttl = session_ttl
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
            # Clean up expired client queues
            expired = [cid for cid, ts in self.client_last_seen.items() if current_time - ts > self.session_ttl]
            for cid in expired:
                self.client_queues.pop(cid, None)
                self.client_last_seen.pop(cid, None)
            
            # Append frame to each active client queue
            for client_id, queue in self.client_queues.items():
                # Create metadata per frame
                self._frame_id_counter += 1
                metadata = FrameMetadata(
                    frame_id=f"frame_{self._frame_id_counter}",
                    timestamp=current_time,
                    quality_level=quality_level,
                    size=len(frame_data),
                    producer_info=producer_info
                )
                queued_frame = QueuedFrame(frame_data, metadata)
                if len(queue) >= self.max_size:
                    queue.popleft()
                queue.append(queued_frame)
                # Update last seen timestamp
                self.client_last_seen[client_id] = current_time
            return True
    
    def get_frame(self, client_id: str, max_age: float = 5.0) -> Optional[QueuedFrame]:
        """
        Get latest frame from queue (non-blocking)
        
        Args:
            client_id: ID of the client requesting the frame
            max_age: Maximum acceptable frame age in seconds
            
        Returns:
            QueuedFrame: Latest frame or None if no suitable frame available
        """
        with self._lock:
            queue = self.client_queues.get(client_id)
            if not queue:
                return None
            while queue:
                frame = queue.popleft()
                if frame.metadata.age() <= max_age:
                    return frame
            return None
    
    def get_oldest_frame(self, client_id: str, max_age: float = 5.0) -> Optional[QueuedFrame]:
        """
        Get oldest frame from queue and remove it (FIFO)
        
        Args:
            client_id: ID of the client requesting the frame
            max_age: Maximum acceptable frame age in seconds
            
        Returns:
            QueuedFrame: Oldest frame or None if no suitable frame available
        """
        with self._lock:
            queue = self.client_queues.get(client_id)
            if not queue:
                return None
            while queue:
                frame = queue.popleft()
                if frame.metadata.age() <= max_age:
                    return frame
            return None
    
    def peek_latest_frame(self, client_id: str) -> Optional[FrameMetadata]:
        """
        Peek at latest frame metadata without consuming
        
        Args:
            client_id: ID of the client requesting the metadata
            
        Returns:
            FrameMetadata: Metadata of latest frame or None if queue empty
        """
        with self._lock:
            queue = self.client_queues.get(client_id)
            if not queue:
                return None
            return queue[-1].metadata
    
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
    
    def add_client(self, client_id: str):
        """Initialize a new queue for the client"""
        with self._lock:
            self.client_queues[client_id] = deque(maxlen=self.max_size)
            self.client_last_seen[client_id] = time.time()
    
    def remove_client(self, client_id: str):
        """Remove client's queue"""
        with self._lock:
            self.client_queues.pop(client_id, None)
            self.client_last_seen.pop(client_id, None)
    
    def get_shared_queue(self):
        """Return underlying shared frame queue structure"""
        return self  # In per-client model, queue itself holds client_queues
