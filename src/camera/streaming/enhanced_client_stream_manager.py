"""
Enhanced Client Stream Manager with Per-Client Quality Adaptation

Manages individual client streams with progressive quality and fps adaptation
based on each client's network performance. Implements time-windowed metrics
for responsive adaptation without affecting other clients.
"""

import time
import threading
import uuid
from typing import Dict, Any, Generator, Optional, Set, List
from dataclasses import dataclass, field

from .shared_frame_queue import SharedFrameQueue, QueuedFrame
from .time_window_metrics import TimeWindowMetrics


@dataclass
class ClientAdaptiveMetrics:
    """
    Enhanced client metrics with per-client adaptive quality tracking
    
    Combines basic performance metrics with progressive quality adaptation
    and time-windowed performance measurement.
    """
    client_id: str
    connection_start_time: float
    last_activity: float
    
    # Basic counters
    frames_delivered: int = 0
    frames_skipped: int = 0
    bytes_delivered: int = 0
    
    # Progressive quality settings
    current_quality: int = 85  # Progressive: 30→40→50→60→70→80→85
    current_fps: int = 30      # Progressive: 2→5→10→15→20→25→30
    
    # Adaptation state
    consecutive_good_windows: int = 0
    consecutive_poor_windows: int = 0
    last_adaptation_time: float = field(default_factory=time.time)
    
    # Time-windowed metrics for this client
    window_metrics: TimeWindowMetrics = field(default_factory=TimeWindowMetrics)
    
    def __post_init__(self):
        """Initialize timing and quality fields"""
        if not hasattr(self, 'last_activity'):
            self.last_activity = self.connection_start_time
        if not hasattr(self, 'last_adaptation_time'):
            self.last_adaptation_time = time.time()
    
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
    
    def update_activity(self, bytes_sent: int = 0, delivery_time: float = 0.0):
        """
        Update activity with performance metrics
        
        Args:
            bytes_sent: Bytes delivered to client
            delivery_time: Time taken to deliver frame
        """
        current_time = time.time()
        self.last_activity = current_time
        
        if bytes_sent > 0:
            self.bytes_delivered += bytes_sent
            self.frames_delivered += 1

            # Calculate delivery ratio for time window per frame
            delivery_ratio = 1.0
            self.window_metrics.add_sample("delivery_ratio_fast", delivery_ratio)
            self.window_metrics.add_sample("delivery_ratio_stable", delivery_ratio)

            if delivery_time > 0:
                self.window_metrics.add_sample("delivery_time", delivery_time)
    
    def record_skip(self):
        """Record a skipped frame with performance impact"""
        self.frames_skipped += 1
        
        # Record poor delivery ratio when skipping per frame
        delivery_ratio = 0.0
        self.window_metrics.add_sample("delivery_ratio_fast", delivery_ratio)
        self.window_metrics.add_sample("delivery_ratio_stable", delivery_ratio)
    
    def adapt_quality_progressive(self, min_quality: int = 30, max_quality: int = 85) -> bool:
        """
        Perform progressive quality adaptation based on time-windowed metrics
        
        Args:
            min_quality: Minimum quality threshold
            max_quality: Maximum quality threshold
            
        Returns:
            bool: True if quality was changed
        """
        current_time = time.time()
        
        # Don't adapt too frequently (minimum 2 seconds between adaptations)
        if current_time - self.last_adaptation_time < 2.0:
            return False
        
        # Get performance assessment from time windows
        assessment = self.window_metrics.get_unified_assessment()
        
        if not assessment.get("available", False):
            return False  # Not enough data yet
        
        old_quality = self.current_quality
        
        # Progressive degradation
        if assessment["should_degrade"]:
            self.consecutive_good_windows = 0
            self.consecutive_poor_windows += 1
            
            # Progressive quality reduction (faster for emergency)
            if assessment["reason"] == "emergency_delivery_ratio":
                reduction = 20  # Large emergency reduction
            elif assessment["confidence"] > 0.8:
                reduction = 10  # Standard reduction
            else:
                reduction = 5   # Conservative reduction
            
            new_quality = max(self.current_quality - reduction, min_quality)
            
            if new_quality != self.current_quality:
                self.current_quality = new_quality
                self.last_adaptation_time = current_time
                # Clear old metrics to avoid stale data delaying next adaptation
                self.window_metrics.clear_all_windows()
                print(f"📉 Client {self.client_id}: Quality reduced to {self.current_quality}% ({assessment['reason']})")
                return True
        
        # Progressive recovery
        elif assessment["should_recover"]:
            self.consecutive_poor_windows = 0
            self.consecutive_good_windows += 1
            
            # Require fewer good windows for recovery (1-2 instead of 3)
            required_good_windows = 1 if assessment["confidence"] > 0.8 else 2
            
            if self.consecutive_good_windows >= required_good_windows:
                # Progressive quality increase (larger steps when confident)
                if assessment["confidence"] > 0.8:
                    increase = 10  # Confident recovery
                else:
                    increase = 5   # Conservative recovery
                
                new_quality = min(self.current_quality + increase, max_quality)
                
                if new_quality != self.current_quality:
                    self.current_quality = new_quality
                    self.consecutive_good_windows = 0  # Reset for next increment
                    self.last_adaptation_time = current_time
                    # Clear old metrics to start fresh after recovery
                    self.window_metrics.clear_all_windows()
                    print(f"📈 Client {self.client_id}: Quality increased to {self.current_quality}% (confidence: {assessment['confidence']:.1%})")
                    return True
        
        return False
    
    def adapt_fps_progressive(self, min_fps: int = 2, max_fps: int = 30) -> bool:
        """
        Perform progressive FPS adaptation based on time-windowed metrics
        
        Args:
            min_fps: Minimum FPS threshold
            max_fps: Maximum FPS threshold
            
        Returns:
            bool: True if FPS was changed
        """
        current_time = time.time()
        
        # Don't adapt too frequently
        if current_time - self.last_adaptation_time < 2.0:
            return False
        
        assessment = self.window_metrics.get_unified_assessment()
        
        if not assessment.get("available", False):
            return False
        
        old_fps = self.current_fps
        
        # Progressive FPS degradation
        if assessment["should_degrade"]:
            if assessment["reason"] == "emergency_delivery_ratio":
                reduction = 10  # Emergency FPS reduction
            elif assessment["confidence"] > 0.8:
                reduction = 4   # Standard reduction
            else:
                reduction = 2   # Conservative reduction
            
            new_fps = max(self.current_fps - reduction, min_fps)
            
            if new_fps != self.current_fps:
                self.current_fps = new_fps
                self.last_adaptation_time = current_time
                # Clear old metrics after degradation
                self.window_metrics.clear_all_windows()
                print(f"📉 Client {self.client_id}: FPS reduced to {self.current_fps} ({assessment['reason']})")
                return True
        
        # Progressive FPS recovery
        elif assessment["should_recover"]:
            required_good_windows = 1 if assessment["confidence"] > 0.8 else 2
            
            if self.consecutive_good_windows >= required_good_windows:
                if assessment["confidence"] > 0.8:
                    increase = 4  # Confident recovery
                else:
                    increase = 2  # Conservative recovery
                
                new_fps = min(self.current_fps + increase, max_fps)
                
                if new_fps != self.current_fps:
                    self.current_fps = new_fps
                    self.last_adaptation_time = current_time
                    # Clear old metrics after recovery
                    self.window_metrics.clear_all_windows()
                    print(f"📈 Client {self.client_id}: FPS increased to {self.current_fps} (confidence: {assessment['confidence']:.1%})")
                    return True
        
        return False
    
    def get_adaptation_status(self) -> Dict[str, Any]:
        """Get current adaptation status for this client"""
        assessment = self.window_metrics.get_unified_assessment()
        
        return {
            "client_id": self.client_id,
            "current_quality": self.current_quality,
            "current_fps": self.current_fps,
            "consecutive_good_windows": self.consecutive_good_windows,
            "consecutive_poor_windows": self.consecutive_poor_windows,
            "time_since_last_adaptation": time.time() - self.last_adaptation_time,
            "performance_assessment": assessment,
            "delivery_efficiency": self.delivery_efficiency,
            "window_metrics_status": self.window_metrics.get_comprehensive_status()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        base_dict = {
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
            "is_active": self.is_active,
            
            # Enhanced adaptive metrics
            "current_quality": self.current_quality,
            "current_fps": self.current_fps,
            "consecutive_good_windows": self.consecutive_good_windows,
            "consecutive_poor_windows": self.consecutive_poor_windows,
            "time_since_last_adaptation": time.time() - self.last_adaptation_time
        }
        
        return base_dict


class EnhancedClientStreamManager:
    """
    Enhanced client stream manager with per-client quality adaptation
    
    Provides independent progressive quality and FPS adaptation for each client
    based on their individual network performance using time-windowed metrics.
    """
    
    def __init__(self, shared_queue: SharedFrameQueue, max_frame_age: float = 5.0):
        """
        Initialize enhanced client stream manager
        
        Args:
            shared_queue: SharedFrameQueue instance to consume from
            max_frame_age: Maximum acceptable frame age in seconds
        """
        self.shared_queue = shared_queue
        self.max_frame_age = max_frame_age
        
        # Client management with enhanced metrics
        self.clients: Dict[str, ClientAdaptiveMetrics] = {}
        self.active_streams: Set[str] = set()
        self._lock = threading.RLock()
        
        # Cleanup management
        self.last_cleanup_time = time.time()
        self.cleanup_interval = 60.0
        
        # Adaptation management
        self.last_adaptation_check = time.time()
        self.adaptation_interval = 3.0  # Check for adaptations every 3 seconds
        
        # Performance tracking
        self.total_clients_created = 0
        self.total_clients_cleaned = 0
        self.total_adaptations = 0
        
        print("🌊 EnhancedClientStreamManager initialized with per-client adaptation")
    
    def create_adaptive_client_stream(self, client_id: Optional[str] = None, 
                                    initial_fps: int = 30, initial_quality: int = 85) -> Generator[bytes, None, None]:
        """
        Create a new adaptive client stream with progressive quality adjustment
        
        Args:
            client_id: Unique client identifier (auto-generated if None)
            initial_fps: Initial target frame rate
            initial_quality: Initial quality level
            
        Yields:
            bytes: MJPEG frame data with client-specific quality
        """
        # Generate client ID if not provided
        if client_id is None:
            client_id = f"client_{uuid.uuid4().hex[:8]}"
        
        # Register client with adaptive metrics
        current_time = time.time()
        with self._lock:
            self.clients[client_id] = ClientAdaptiveMetrics(
                client_id=client_id,
                connection_start_time=current_time,
                last_activity=current_time,
                current_fps=initial_fps,
                current_quality=initial_quality
            )
            self.active_streams.add(client_id)
            self.total_clients_created += 1
        
        print(f"👤 Adaptive client stream created: {client_id} (fps: {initial_fps}, quality: {initial_quality}%)")
        
        try:
            last_frame_time = 0.0
            last_adaptation_check = 0.0
            
            while client_id in self.active_streams:
                try:
                    current_time = time.time()
                    
                    # Get current client metrics
                    with self._lock:
                        if client_id not in self.clients:
                            break
                        client_metrics = self.clients[client_id]
                        current_fps = client_metrics.current_fps
                        current_quality = client_metrics.current_quality
                    
                    # Calculate frame interval based on current adaptive FPS
                    frame_interval = 1.0 / max(current_fps, 1)
                    
                    # Rate limiting based on adaptive FPS
                    if current_time - last_frame_time < frame_interval:
                        time.sleep(0.01)
                        continue
                    
                    # Periodic adaptation check
                    if current_time - last_adaptation_check > self.adaptation_interval:
                        self._perform_client_adaptation(client_id)
                        last_adaptation_check = current_time
                    
                    # Get frame from shared queue
                    frame_start_time = time.time()
                    queued_frame = self.shared_queue.get_frame(max_age=self.max_frame_age)
                    
                    if queued_frame:
                        # TODO: Apply client-specific quality to frame
                        # For now, use the frame as-is but track delivery performance
                        
                        # Create MJPEG frame with headers
                        mjpeg_frame = (
                            b'--frame\r\n'
                            b'Content-Type: image/jpeg\r\n\r\n' + 
                            queued_frame.data + 
                            b'\r\n'
                        )
                        
                        # Calculate delivery time
                        delivery_time = time.time() - frame_start_time
                        
                        # Update client metrics with performance data
                        with self._lock:
                            if client_id in self.clients:
                                self.clients[client_id].update_activity(len(mjpeg_frame), delivery_time)
                        
                        # Yield frame to client
                        yield mjpeg_frame
                        last_frame_time = current_time
                        
                    else:
                        # No frame available - record skip and performance impact
                        with self._lock:
                            if client_id in self.clients:
                                self.clients[client_id].record_skip()
                        
                        time.sleep(0.01)
                    
                    # Periodic cleanup
                    if current_time - self.last_cleanup_time > self.cleanup_interval:
                        self._cleanup_inactive_clients()
                        self.last_cleanup_time = current_time
                
                except Exception as e:
                    print(f"❌ Error in adaptive client stream {client_id}: {e}")
                    break
        
        finally:
            # Clean up client when stream ends
            self._cleanup_client(client_id)
            print(f"🔚 Adaptive client stream ended: {client_id}")
    
    def _perform_client_adaptation(self, client_id: str):
        """
        Perform progressive adaptation for a specific client
        
        Args:
            client_id: Client to adapt
        """
        with self._lock:
            if client_id not in self.clients:
                return
            
            client_metrics = self.clients[client_id]
            
            # Perform progressive quality adaptation
            quality_changed = client_metrics.adapt_quality_progressive()
            fps_changed = client_metrics.adapt_fps_progressive()
            
            if quality_changed or fps_changed:
                self.total_adaptations += 1
    
    def get_client_adaptation_status(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get adaptation status for a specific client"""
        with self._lock:
            if client_id in self.clients:
                return self.clients[client_id].get_adaptation_status()
        return None
    
    def get_all_adaptation_status(self) -> Dict[str, Dict[str, Any]]:
        """Get adaptation status for all clients"""
        with self._lock:
            return {
                client_id: metrics.get_adaptation_status()
                for client_id, metrics in self.clients.items()
                if metrics.is_active
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
                print(f"🎯 Client {client_id}: Quality manually set to {quality}%")
                return True
        return False
    
    def force_client_fps(self, client_id: str, fps: int) -> bool:
        """
        Force a specific FPS for a client
        
        Args:
            client_id: Target client
            fps: FPS value (2-30)
            
        Returns:
            bool: True if successful
        """
        with self._lock:
            if client_id in self.clients:
                self.clients[client_id].current_fps = max(2, min(fps, 30))
                print(f"🎯 Client {client_id}: FPS manually set to {fps}")
                return True
        return False
    
    def get_enhanced_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary with adaptation metrics"""
        current_time = time.time()
        
        with self._lock:
            active_clients = [m for m in self.clients.values() if m.is_active]
            
            if not active_clients:
                return {
                    "active_clients": 0,
                    "total_adaptations": self.total_adaptations,
                    "adaptation_rate": 0.0,
                    "average_quality": 85,
                    "average_fps": 30,
                    "quality_range": [85, 85],
                    "fps_range": [30, 30]
                }
            
            # Calculate adaptation metrics
            qualities = [m.current_quality for m in active_clients]
            fps_values = [m.current_fps for m in active_clients]
            efficiencies = [m.delivery_efficiency for m in active_clients]
            
            return {
                "active_clients": len(active_clients),
                "total_clients_created": self.total_clients_created,
                "total_adaptations": self.total_adaptations,
                "adaptation_rate": self.total_adaptations / (current_time - (self.clients[list(self.clients.keys())[0]].connection_start_time if self.clients else current_time)),
                
                # Quality metrics
                "average_quality": sum(qualities) / len(qualities),
                "min_quality": min(qualities),
                "max_quality": max(qualities),
                "quality_range": [min(qualities), max(qualities)],
                
                # FPS metrics
                "average_fps": sum(fps_values) / len(fps_values),
                "min_fps": min(fps_values),
                "max_fps": max(fps_values),
                "fps_range": [min(fps_values), max(fps_values)],
                
                # Performance metrics
                "average_delivery_efficiency": sum(efficiencies) / len(efficiencies),
                "min_delivery_efficiency": min(efficiencies),
                "max_delivery_efficiency": max(efficiencies),
                
                # Health indicators
                "all_clients_healthy": all(e > 0.8 for e in efficiencies),
                "quality_variance": max(qualities) - min(qualities),
                "fps_variance": max(fps_values) - min(fps_values),
                "has_adapted_clients": any(q < 85 or f < 30 for q, f in zip(qualities, fps_values))
            }
    
    # Include all methods from original ClientStreamManager for compatibility
    def disconnect_client(self, client_id: str) -> bool:
        """Disconnect a specific client"""
        with self._lock:
            if client_id in self.active_streams:
                self.active_streams.remove(client_id)
                print(f"🔌 Client disconnected: {client_id}")
                return True
        return False
    
    def get_client_metrics(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get metrics for a specific client"""
        with self._lock:
            if client_id in self.clients:
                return self.clients[client_id].to_dict()
        return None
    
    def _cleanup_client(self, client_id: str):
        """Clean up a specific client"""
        with self._lock:
            self.active_streams.discard(client_id)
    
    def _cleanup_inactive_clients(self):
        """Remove metrics for inactive clients"""
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
                print(f"🧹 Cleaned up {len(inactive_clients)} inactive adaptive clients")
