"""
Simple Client Manager
Manages individual client streams with per-client quality adaptation
based on real-time network performance measurement.
"""

import time
import uuid
import threading
from typing import Dict, Generator, Optional, Any
from dataclasses import dataclass, field

from .multi_quality_producer import MultiQualityFrameProducer, QualityFrame


@dataclass
class ClientState:
    """Simple client state tracking for adaptive streaming"""
    client_id: str
    connection_start: float
    last_activity: float
    
    # Current adaptive settings
    current_quality: int = 85  # Start with highest quality
    target_fps: int = 30       # Target frame rate
    
    # Simple performance tracking (last 5 deliveries)
    delivery_times: list = field(default_factory=list)
    frames_delivered: int = 0
    frames_skipped: int = 0
    
    # Adaptation state
    last_adaptation: float = field(default_factory=time.time)
    consecutive_good: int = 0
    consecutive_poor: int = 0
    
    def __post_init__(self):
        if not hasattr(self, 'last_activity'):
            self.last_activity = self.connection_start
        if not hasattr(self, 'last_adaptation'):
            self.last_adaptation = time.time()
    
    @property
    def average_delivery_time(self) -> float:
        """Get average delivery time from recent samples"""
        if not self.delivery_times:
            return 0.0
        return sum(self.delivery_times) / len(self.delivery_times)
    
    @property
    def is_active(self) -> bool:
        """Check if client is recently active (last 30 seconds)"""
        return (time.time() - self.last_activity) < 30.0
    
    @property
    def uptime(self) -> float:
        """Get client connection uptime in seconds"""
        return time.time() - self.connection_start
    
    def record_delivery(self, delivery_time: float):
        """Record a successful frame delivery"""
        self.frames_delivered += 1
        self.last_activity = time.time()
        
        # Keep only last 5 delivery times for simple average
        self.delivery_times.append(delivery_time)
        if len(self.delivery_times) > 5:
            self.delivery_times.pop(0)
    
    def record_skip(self):
        """Record a skipped frame"""
        self.frames_skipped += 1
    
    def should_adapt_quality(self) -> tuple[bool, str]:
        """
        Simple quality adaptation logic based on average delivery time
        
        Returns:
            tuple: (should_adapt, direction) where direction is 'up', 'down', or 'stable'
        """
        current_time = time.time()
        
        # Don't adapt too frequently (minimum 3 seconds between adaptations)
        if current_time - self.last_adaptation < 3.0:
            return False, 'stable'
        
        # Need at least 3 delivery samples
        if len(self.delivery_times) < 3:
            return False, 'stable'
        
        avg_delivery = self.average_delivery_time
        
        # Simple thresholds for quality adaptation
        if avg_delivery > 2.0:  # Slow delivery (>2 seconds)
            self.consecutive_poor += 1
            self.consecutive_good = 0
            if self.consecutive_poor >= 2:  # 2 consecutive poor periods
                return True, 'down'
        elif avg_delivery < 0.5:  # Fast delivery (<0.5 seconds)
            self.consecutive_good += 1
            self.consecutive_poor = 0
            if self.consecutive_good >= 3:  # 3 consecutive good periods
                return True, 'up'
        else:
            # Reset counters for stable performance
            self.consecutive_good = 0
            self.consecutive_poor = 0
        
        return False, 'stable'
    
    def adapt_quality(self, direction: str, min_quality: int = 30, max_quality: int = 85) -> bool:
        """
        Adapt quality based on direction
        
        Args:
            direction: 'up' or 'down'
            min_quality: Minimum quality level
            max_quality: Maximum quality level
            
        Returns:
            bool: True if quality was changed
        """
        old_quality = self.current_quality
        
        if direction == 'down' and self.current_quality > min_quality:
            # Degrade quality (10% steps)
            self.current_quality = max(self.current_quality - 15, min_quality)
            self.consecutive_poor = 0  # Reset counter
            
        elif direction == 'up' and self.current_quality < max_quality:
            # Improve quality (10% steps)
            self.current_quality = min(self.current_quality + 10, max_quality)
            self.consecutive_good = 0  # Reset counter
        
        if self.current_quality != old_quality:
            self.last_adaptation = time.time()
            # Clear delivery history to start fresh after adaptation
            self.delivery_times.clear()
            return True
        
        return False


class SimpleClientManager:
    """
    Simple client manager for efficient multi-client streaming
    
    Manages individual client connections with per-client quality adaptation
    based on real-time network performance measurement.
    """
    
    def __init__(self, frame_producer: MultiQualityFrameProducer):
        """
        Initialize simple client manager
        
        Args:
            frame_producer: MultiQualityFrameProducer instance
        """
        self.frame_producer = frame_producer
        
        # Client management
        self.clients: Dict[str, ClientState] = {}
        self.active_streams: set = set()
        self._lock = threading.RLock()
        
        # Performance tracking
        self.total_clients_created = 0
        self.total_frames_served = 0
        self.last_cleanup_time = time.time()
        
        print("🌊 SimpleClientManager initialized")
    
    def create_client_stream(self, client_id: Optional[str] = None, 
                           initial_quality: int = 85, target_fps: int = 30) -> Generator[bytes, None, None]:
        """
        Create a new client stream with adaptive quality
        
        Args:
            client_id: Unique client identifier (auto-generated if None)
            initial_quality: Starting quality level
            target_fps: Target frame rate
            
        Yields:
            bytes: MJPEG frame data
        """
        # Generate client ID if not provided
        if client_id is None:
            client_id = f"client_{uuid.uuid4().hex[:8]}"
        
        # Register client
        current_time = time.time()
        with self._lock:
            self.clients[client_id] = ClientState(
                client_id=client_id,
                connection_start=current_time,
                last_activity=current_time,
                current_quality=initial_quality,
                target_fps=target_fps
            )
            self.active_streams.add(client_id)
            self.total_clients_created += 1
        
        print(f"👤 Client stream created: {client_id} (quality: {initial_quality}%, fps: {target_fps})")
        
        try:
            last_frame_time = 0.0
            frame_interval = 1.0 / max(target_fps, 1)
            
            while client_id in self.active_streams:
                try:
                    current_time = time.time()
                    
                    # Rate limiting based on target FPS
                    if current_time - last_frame_time < frame_interval:
                        time.sleep(0.01)
                        continue
                    
                    # Get current client state
                    with self._lock:
                        if client_id not in self.clients:
                            break
                        client_state = self.clients[client_id]
                        target_quality = client_state.current_quality
                    
                    # Get frame at target quality
                    frame_start_time = time.time()
                    quality_frame = self.frame_producer.get_frame(target_quality, max_age=2.0)
                    
                    if quality_frame:
                        # Create MJPEG frame
                        mjpeg_frame = (
                            b'--frame\r\n'
                            b'Content-Type: image/jpeg\r\n' +
                            f'Content-Length: {len(quality_frame.data)}\r\n\r\n'.encode() +
                            quality_frame.data + b'\r\n'
                        )
                        
                        # Calculate delivery time and yield frame
                        delivery_time = time.time() - frame_start_time
                        
                        # Update client state
                        with self._lock:
                            if client_id in self.clients:
                                self.clients[client_id].record_delivery(delivery_time)
                                self.total_frames_served += 1
                        
                        yield mjpeg_frame
                        last_frame_time = current_time
                        
                        # Check for quality adaptation
                        self._check_client_adaptation(client_id)
                        
                    else:
                        # No frame available
                        with self._lock:
                            if client_id in self.clients:
                                self.clients[client_id].record_skip()
                        time.sleep(0.01)
                    
                    # Periodic cleanup
                    if current_time - self.last_cleanup_time > 60.0:
                        self._cleanup_inactive_clients()
                        self.last_cleanup_time = current_time
                
                except Exception as e:
                    print(f"❌ Error in client stream {client_id}: {e}")
                    break
        
        finally:
            self._disconnect_client(client_id)
            print(f"🔚 Client stream ended: {client_id}")
    
    def _check_client_adaptation(self, client_id: str):
        """Check and perform quality adaptation for a client"""
        with self._lock:
            if client_id not in self.clients:
                return
            
            client_state = self.clients[client_id]
            should_adapt, direction = client_state.should_adapt_quality()
            
            if should_adapt:
                old_quality = client_state.current_quality
                if client_state.adapt_quality(direction):
                    new_quality = client_state.current_quality
                    print(f"📊 Client {client_id}: Quality {old_quality}% → {new_quality}% "
                          f"(avg delivery: {client_state.average_delivery_time:.2f}s)")
    
    def _disconnect_client(self, client_id: str):
        """Disconnect and clean up a client"""
        with self._lock:
            self.active_streams.discard(client_id)
            # Keep client state for a while for statistics
    
    def _cleanup_inactive_clients(self):
        """Remove inactive clients from memory"""
        current_time = time.time()
        inactive_threshold = 300.0  # 5 minutes
        
        with self._lock:
            inactive_clients = [
                client_id for client_id, state in self.clients.items()
                if (current_time - state.last_activity) > inactive_threshold
                and client_id not in self.active_streams
            ]
            
            for client_id in inactive_clients:
                del self.clients[client_id]
            
            if inactive_clients:
                print(f"🧹 Cleaned up {len(inactive_clients)} inactive clients")
    
    def disconnect_client(self, client_id: str) -> bool:
        """
        Manually disconnect a client
        
        Args:
            client_id: Client to disconnect
            
        Returns:
            bool: True if client was disconnected
        """
        with self._lock:
            if client_id in self.active_streams:
                self.active_streams.remove(client_id)
                print(f"🔌 Client manually disconnected: {client_id}")
                return True
        return False
    
    def get_client_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific client
        
        Args:
            client_id: Client to query
            
        Returns:
            dict: Client information or None if not found
        """
        with self._lock:
            if client_id not in self.clients:
                return None
            
            state = self.clients[client_id]
            return {
                "client_id": client_id,
                "connection_start": state.connection_start,
                "uptime": state.uptime,
                "last_activity": state.last_activity,
                "is_active": state.is_active,
                "current_quality": state.current_quality,
                "target_fps": state.target_fps,
                "frames_delivered": state.frames_delivered,
                "frames_skipped": state.frames_skipped,
                "average_delivery_time": state.average_delivery_time,
                "consecutive_good": state.consecutive_good,
                "consecutive_poor": state.consecutive_poor,
                "delivery_efficiency": (
                    state.frames_delivered / (state.frames_delivered + state.frames_skipped)
                    if (state.frames_delivered + state.frames_skipped) > 0 else 1.0
                )
            }
    
    def get_all_clients_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all clients
        
        Returns:
            dict: Dictionary of client information
        """
        with self._lock:
            return {
                client_id: self.get_client_info(client_id)
                for client_id in self.clients.keys()
                if self.get_client_info(client_id) is not None
            }
    
    def get_active_clients(self) -> list:
        """
        Get list of active client IDs
        
        Returns:
            list: Active client IDs
        """
        with self._lock:
            return list(self.active_streams)
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get performance summary for all clients
        
        Returns:
            dict: Performance summary
        """
        with self._lock:
            active_clients = [
                self.clients[cid] for cid in self.active_streams 
                if cid in self.clients
            ]
            
            if not active_clients:
                return {
                    "active_clients": 0,
                    "total_clients_created": self.total_clients_created,
                    "total_frames_served": self.total_frames_served
                }
            
            qualities = [c.current_quality for c in active_clients]
            delivery_times = [c.average_delivery_time for c in active_clients if c.delivery_times]
            
            return {
                "active_clients": len(active_clients),
                "total_clients_created": self.total_clients_created,
                "total_frames_served": self.total_frames_served,
                "quality_stats": {
                    "min_quality": min(qualities) if qualities else 0,
                    "max_quality": max(qualities) if qualities else 0,
                    "avg_quality": sum(qualities) / len(qualities) if qualities else 0,
                },
                "performance_stats": {
                    "avg_delivery_time": sum(delivery_times) / len(delivery_times) if delivery_times else 0,
                    "clients_with_data": len(delivery_times),
                },
                "adaptation_stats": {
                    "clients_adapting_down": sum(1 for c in active_clients if c.consecutive_poor > 0),
                    "clients_adapting_up": sum(1 for c in active_clients if c.consecutive_good > 0),
                }
            }
    
    def force_client_quality(self, client_id: str, quality: int) -> bool:
        """
        Force a specific quality for a client
        
        Args:
            client_id: Target client
            quality: Quality percentage (30-85)
            
        Returns:
            bool: True if successful
        """
        with self._lock:
            if client_id in self.clients:
                self.clients[client_id].current_quality = max(30, min(quality, 85))
                self.clients[client_id].last_adaptation = time.time()
                self.clients[client_id].delivery_times.clear()  # Reset adaptation history
                print(f"🎯 Client {client_id}: Quality manually set to {quality}%")
                return True
        return False
    
    def get_status_summary(self) -> str:
        """
        Get human-readable status summary
        
        Returns:
            str: Status summary
        """
        summary = self.get_performance_summary()
        
        return (
            f"Active: {summary['active_clients']} | "
            f"Total Served: {summary['total_frames_served']} | "
            f"Quality Range: {summary['quality_stats']['min_quality']}-{summary['quality_stats']['max_quality']}%"
        )