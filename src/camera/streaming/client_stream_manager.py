"""
Client Stream Manager for Multi-Client Support

Manages individual client streams consuming from a shared frame queue.
Each client gets independent frame delivery without blocking others.
"""

import time
import threading
import uuid
from typing import Dict, Any, Generator, Optional, Set, List
from dataclasses import dataclass

from .shared_frame_queue import SharedFrameQueue, QueuedFrame


@dataclass
class ClientMetrics:
    """
    Performance tracking for individual clients
    """
    client_id: str
    connection_start_time: float
    last_activity: float
    frames_delivered: int = 0
    frames_skipped: int = 0
    bytes_delivered: int = 0
    
    def __post_init__(self):
        """Initialize timing fields"""
        if not hasattr(self, 'last_activity'):
            self.last_activity = self.connection_start_time
    
    @property
    def uptime(self) -> float:
        """Get client connection uptime in seconds"""
        return time.time() - self.connection_start_time
    
    @property
    def consumption_rate(self) -> float:
        """Get frames per second consumption rate"""
        if self.uptime <= 0:
            return 0.0
        return self.frames_delivered / self.uptime
    
    @property
    def delivery_efficiency(self) -> float:
        """Get delivery efficiency (delivered / (delivered + skipped))"""
        total_attempts = self.frames_delivered + self.frames_skipped
        if total_attempts == 0:
            return 1.0
        return self.frames_delivered / total_attempts
    
    @property
    def throughput_mbps(self) -> float:
        """Get throughput in megabits per second"""
        if self.uptime <= 0:
            return 0.0
        return (self.bytes_delivered * 8) / (self.uptime * 1_000_000)
    
    @property
    def is_active(self) -> bool:
        """Check if client is recently active (last activity within 30 seconds)"""
        return (time.time() - self.last_activity) < 30.0
    
    def update_activity(self, bytes_sent: int = 0):
        """Update last activity timestamp and bytes delivered"""
        self.last_activity = time.time()
        if bytes_sent > 0:
            self.bytes_delivered += bytes_sent
            self.frames_delivered += 1
    
    def record_skip(self):
        """Record a skipped frame"""
        self.frames_skipped += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "client_id": self.client_id,
            "connection_start_time": self.connection_start_time,
            "last_activity": self.last_activity,
            "uptime": self.uptime,
            "frames_delivered": self.frames_delivered,
            "frames_skipped": self.frames_skipped,
            "bytes_delivered": self.bytes_delivered,
            "consumption_rate": self.consumption_rate,
            "delivery_efficiency": self.delivery_efficiency,
            "throughput_mbps": self.throughput_mbps,
            "is_active": self.is_active
        }


class ClientStreamManager:
    """
    Manages individual client streams from shared frame queue
    
    Provides independent frame delivery to multiple clients without
    blocking frame production or affecting other clients.
    """
    
    def __init__(self, shared_queue: SharedFrameQueue, max_frame_age: float = 5.0):
        """
        Initialize client stream manager
        
        Args:
            shared_queue: SharedFrameQueue instance to consume from
            max_frame_age: Maximum acceptable frame age in seconds
        """
        self.shared_queue = shared_queue
        self.max_frame_age = max_frame_age
        
        # Client management
        self.clients: Dict[str, ClientMetrics] = {}
        self.active_streams: Set[str] = set()
        self._lock = threading.RLock()
        
        # Cleanup management
        self.last_cleanup_time = time.time()
        self.cleanup_interval = 60.0  # Cleanup every minute
        
        # Performance tracking
        self.total_clients_created = 0
        self.total_clients_cleaned = 0
        
        print("🌊 ClientStreamManager initialized")
    
    def create_client_stream(self, client_id: Optional[str] = None, target_fps: int = 30) -> Generator[bytes, None, None]:
        """
        Create a new client stream that yields MJPEG frames
        
        Args:
            client_id: Unique client identifier (auto-generated if None)
            target_fps: Target frame rate for this client
            
        Yields:
            bytes: MJPEG frame data with appropriate headers
        """
        # Generate client ID if not provided
        if client_id is None:
            client_id = f"client_{uuid.uuid4().hex[:8]}"
        
        # Register client and its queue
        current_time = time.time()
        with self._lock:
            self.clients[client_id] = ClientMetrics(
                client_id=client_id,
                connection_start_time=current_time,
                last_activity=current_time
            )
            self.active_streams.add(client_id)
            self.total_clients_created += 1
            # Initialize queue entry
            if self.shared_queue:
                self.shared_queue.add_client(client_id)
        
        print(f"👤 Client stream created: {client_id} (target: {target_fps} fps)")
        
        try:
            # Calculate frame interval for target fps
            frame_interval = 1.0 / max(target_fps, 1)
            last_frame_time = 0.0
            
            while client_id in self.active_streams:
                try:
                    current_time = time.time()
                    
                    # Rate limiting - only send frames at target rate
                    if current_time - last_frame_time < frame_interval:
                        time.sleep(0.01)  # Brief pause
                        continue
                    
                    # Get frame from shared queue
                    queued_frame = self.shared_queue.get_frame(client_id, max_age=self.max_frame_age)
                    
                    if queued_frame:
                        # Create MJPEG frame with headers
                        mjpeg_frame = (
                            b'--frame\r\n'
                            b'Content-Type: image/jpeg\r\n\r\n' + 
                            queued_frame.data + 
                            b'\r\n'
                        )
                        
                        # Update client metrics
                        with self._lock:
                            if client_id in self.clients:
                                self.clients[client_id].update_activity(len(mjpeg_frame))
                        
                        # Yield frame to client
                        yield mjpeg_frame
                        last_frame_time = current_time
                        
                    else:
                        # No frame available - record skip and brief pause
                        with self._lock:
                            if client_id in self.clients:
                                self.clients[client_id].record_skip()
                        
                        time.sleep(0.01)  # Brief pause when no frames available
                    
                    # Periodic cleanup of inactive clients
                    if current_time - self.last_cleanup_time > self.cleanup_interval:
                        self._cleanup_inactive_clients()
                        self.last_cleanup_time = current_time
                
                except Exception as e:
                    print(f"❌ Error in client stream {client_id}: {e}")
                    break
        
        finally:
            # Deregister client when stream ends
            with self._lock:
                self.active_streams.discard(client_id)
                self.clients.pop(client_id, None)
                if self.shared_queue:
                    self.shared_queue.remove_client(client_id)
            # Log closure at same level as with
            print(f"👋 Client stream closed: {client_id}")
        
        # Explicit stop yields
        return
    
    def disconnect_client(self, client_id: str) -> bool:
        """
        Disconnect a specific client
        
        Args:
            client_id: Client identifier to disconnect
            
        Returns:
            bool: True if client was found and disconnected
        """
        with self._lock:
            if client_id in self.active_streams:
                self.active_streams.remove(client_id)
                print(f"🔌 Client disconnected: {client_id}")
                return True
        return False
    
    def get_client_metrics(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metrics for a specific client
        
        Args:
            client_id: Client identifier
            
        Returns:
            dict: Client metrics or None if not found
        """
        with self._lock:
            if client_id in self.clients:
                return self.clients[client_id].to_dict()
        return None
    
    def get_all_client_metrics(self) -> Dict[str, Dict[str, Any]]:
        """
        Get metrics for all clients
        
        Returns:
            dict: Dictionary mapping client_id to metrics
        """
        with self._lock:
            return {
                client_id: metrics.to_dict() 
                for client_id, metrics in self.clients.items()
            }
    
    def get_active_client_count(self) -> int:
        """
        Get number of active client streams
        
        Returns:
            int: Number of active clients
        """
        with self._lock:
            return len(self.active_streams)
    
    def get_total_consumption_rate(self) -> float:
        """
        Get total consumption rate across all clients
        
        Returns:
            float: Total frames per second being consumed
        """
        with self._lock:
            return sum(
                metrics.consumption_rate 
                for metrics in self.clients.values() 
                if metrics.is_active
            )
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive performance summary
        
        Returns:
            dict: Performance summary across all clients
        """
        current_time = time.time()
        
        with self._lock:
            active_clients = [m for m in self.clients.values() if m.is_active]
            
            if not active_clients:
                return {
                    "active_clients": 0,
                    "total_consumption_rate": 0.0,
                    "average_delivery_efficiency": 1.0,
                    "total_throughput_mbps": 0.0,
                    "queue_metrics": self.shared_queue.get_queue_metrics()
                }
            
            # Calculate aggregated metrics
            total_consumption_rate = sum(m.consumption_rate for m in active_clients)
            avg_delivery_efficiency = sum(m.delivery_efficiency for m in active_clients) / len(active_clients)
            total_throughput = sum(m.throughput_mbps for m in active_clients)
            
            # Find client performance ranges
            consumption_rates = [m.consumption_rate for m in active_clients]
            efficiencies = [m.delivery_efficiency for m in active_clients]
            
            return {
                "active_clients": len(active_clients),
                "total_clients_created": self.total_clients_created,
                "total_clients_cleaned": self.total_clients_cleaned,
                
                # Consumption metrics
                "total_consumption_rate": total_consumption_rate,
                "average_consumption_rate": total_consumption_rate / len(active_clients),
                "min_consumption_rate": min(consumption_rates),
                "max_consumption_rate": max(consumption_rates),
                
                # Efficiency metrics
                "average_delivery_efficiency": avg_delivery_efficiency,
                "min_delivery_efficiency": min(efficiencies),
                "max_delivery_efficiency": max(efficiencies),
                
                # Throughput metrics
                "total_throughput_mbps": total_throughput,
                "average_throughput_mbps": total_throughput / len(active_clients),
                
                # Queue metrics
                "queue_metrics": self.shared_queue.get_queue_metrics(),
                
                # Health indicators
                "all_clients_healthy": all(e > 0.8 for e in efficiencies),
                "has_slow_clients": any(r < 10.0 for r in consumption_rates),
                "performance_variance": max(consumption_rates) - min(consumption_rates) if consumption_rates else 0.0
            }
    
    def _cleanup_client(self, client_id: str):
        """
        Clean up a specific client
        
        Args:
            client_id: Client identifier to clean up
        """
        with self._lock:
            # Remove from active streams
            self.active_streams.discard(client_id)
            
            # Keep client metrics for a while for analysis
            # (They'll be cleaned up by periodic cleanup)
    
    def _cleanup_inactive_clients(self):
        """
        Remove metrics for clients that have been inactive for too long
        """
        current_time = time.time()
        inactive_threshold = 300.0  # 5 minutes
        
        with self._lock:
            inactive_clients = [
                client_id for client_id, metrics in self.clients.items()
                if (current_time - metrics.last_activity) > inactive_threshold
                and client_id not in self.active_streams
            ]
            
            for client_id in inactive_clients:
                del self.clients[client_id]
                self.total_clients_cleaned += 1
            
            if inactive_clients:
                print(f"🧹 Cleaned up {len(inactive_clients)} inactive clients")
    
    def force_cleanup_all_inactive(self):
        """
        Force cleanup of all inactive clients
        """
        with self._lock:
            # Find all inactive clients
            inactive_clients = [
                client_id for client_id, metrics in self.clients.items()
                if not metrics.is_active and client_id not in self.active_streams
            ]
            
            # Remove them
            for client_id in inactive_clients:
                del self.clients[client_id]
                self.total_clients_cleaned += 1
            
            print(f"🧹 Force cleaned {len(inactive_clients)} inactive clients")
    
    def disconnect_all_clients(self):
        """
        Disconnect all active clients
        """
        with self._lock:
            disconnected_count = len(self.active_streams)
            self.active_streams.clear()
            print(f"🔌 Disconnected all {disconnected_count} clients")
    
    def get_client_list(self) -> List[Dict[str, Any]]:
        """
        Get list of all clients with their status
        
        Returns:
            List[Dict]: List of client information
        """
        current_time = time.time()
        
        with self._lock:
            client_list = []
            
            for client_id, metrics in self.clients.items():
                client_info = metrics.to_dict()
                client_info.update({
                    "is_streaming": client_id in self.active_streams,
                    "time_since_last_activity": current_time - metrics.last_activity
                })
                client_list.append(client_info)
            
            # Sort by last activity (most recent first)
            client_list.sort(key=lambda x: x["last_activity"], reverse=True)
            
            return client_list
    
    def get_status_summary(self) -> str:
        """
        Get human-readable status summary
        
        Returns:
            str: Status summary
        """
        performance = self.get_performance_summary()
        
        active_count = performance["active_clients"]
        consumption_rate = performance["total_consumption_rate"]
        efficiency = performance["average_delivery_efficiency"]
        queue_status = self.shared_queue.get_status_summary()
        
        return f"Clients: {active_count} | Rate: {consumption_rate:.1f} fps | Efficiency: {efficiency:.1%} | {queue_status}"
