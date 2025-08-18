"""
Efficient Streaming System
Coordinates multi-quality frame production with per-client adaptive streaming
for optimal performance on Raspberry Pi with minimal memory usage.
"""

import time
import threading
from typing import Dict, Optional, Any, Generator

from .multi_quality_producer import MultiQualityFrameProducer
from .simple_client_manager import SimpleClientManager
from .network_performance_tracker import NetworkPerformanceTracker


class EfficientStreamingSystem:
    """
    Efficient streaming system for Raspberry Pi
    
    Coordinates multi-quality frame production with per-client adaptive streaming.
    Designed for minimal memory usage (<500KB) and maximum quality per client.
    """
    
    def __init__(self, quality_levels: Optional[list] = None):
        """
        Initialize efficient streaming system
        
        Args:
            quality_levels: JPEG quality levels to produce (default: [30, 50, 70, 85])
        """
        self.quality_levels = quality_levels or [30, 50, 70, 85]
        
        # Core components
        self.frame_producer = MultiQualityFrameProducer(self.quality_levels)
        self.client_manager = SimpleClientManager(self.frame_producer)
        self.network_tracker = NetworkPerformanceTracker(max_samples=10)
        
        # System state
        self.is_running = False
        self.is_streaming = False
        self._lock = threading.RLock()
        
        # Performance tracking
        self.start_time = time.time()
        self.total_frames_processed = 0
        
        print(f"🚀 EfficientStreamingSystem initialized with quality levels: {self.quality_levels}")
    
    def start_streaming(self) -> bool:
        """
        Start the streaming system
        
        Returns:
            bool: True if streaming started successfully
        """
        with self._lock:
            if self.is_streaming:
                print("⚠️  Streaming system already running")
                return True
            
            try:
                self.is_running = True
                self.is_streaming = True
                self.start_time = time.time()
                
                print("🎬 Efficient streaming system started")
                return True
                
            except Exception as e:
                print(f"❌ Failed to start streaming system: {e}")
                self.is_running = False
                self.is_streaming = False
                return False
    
    def stop_streaming(self) -> bool:
        """
        Stop the streaming system
        
        Returns:
            bool: True if streaming stopped successfully
        """
        with self._lock:
            if not self.is_streaming:
                return True
            
            try:
                self.is_running = False
                self.is_streaming = False
                
                # Clear any buffered frames
                self.frame_producer.clear_frames()
                
                print("🛑 Efficient streaming system stopped")
                return True
                
            except Exception as e:
                print(f"❌ Error stopping streaming system: {e}")
                return False
    
    def process_frame(self, raw_frame_data: bytes) -> bool:
        """
        Process a new frame from the camera
        
        Args:
            raw_frame_data: Raw frame data from camera
            
        Returns:
            bool: True if frame was processed successfully
        """
        if not self.is_streaming or not raw_frame_data:
            return False
        
        # Produce multiple quality versions
        success = self.frame_producer.produce_frame(raw_frame_data)
        
        if success:
            self.total_frames_processed += 1
            
            # Update network tracking with system metrics
            active_clients = len(self.client_manager.get_active_clients())
            if active_clients > 0:
                # Use average frame size for tracking
                memory_usage = self.frame_producer.get_memory_usage()
                avg_frame_size = memory_usage["total_memory_bytes"] // len(self.quality_levels)
                
                # Record a sample with estimated delivery performance
                self.network_tracker.record_delivery(
                    delivery_time=0.1,  # Placeholder - real delivery times come from clients
                    frame_size=avg_frame_size,
                    client_count=active_clients
                )
        
        return success
    
    def create_client_stream(self, client_id: Optional[str] = None, 
                           initial_quality: int = 85, 
                           target_fps: int = 30) -> Generator[bytes, None, None]:
        """
        Create a new client stream
        
        Args:
            client_id: Unique client identifier (auto-generated if None)
            initial_quality: Starting quality level (default: 85%)
            target_fps: Target frame rate (default: 30 fps)
            
        Yields:
            bytes: MJPEG frame data
        """
        if not self.is_streaming:
            print("❌ Cannot create client stream: streaming system not running")
            return
        
        try:
            # Create client stream with network tracking integration
            stream = self.client_manager.create_client_stream(
                client_id=client_id,
                initial_quality=initial_quality,
                target_fps=target_fps
            )
            
            # Yield frames with network performance tracking
            for frame_data in stream:
                if not self.is_streaming:
                    break
                
                # Track frame delivery performance
                frame_start_time = time.time()
                yield frame_data
                delivery_time = time.time() - frame_start_time
                
                # Record delivery performance for adaptation
                self.network_tracker.record_delivery(
                    delivery_time=delivery_time,
                    frame_size=len(frame_data),
                    client_count=len(self.client_manager.get_active_clients())
                )
                
        except Exception as e:
            print(f"❌ Error in client stream: {e}")
    
    def disconnect_client(self, client_id: str) -> bool:
        """
        Disconnect a specific client
        
        Args:
            client_id: Client to disconnect
            
        Returns:
            bool: True if client was disconnected
        """
        return self.client_manager.disconnect_client(client_id)
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        Get comprehensive system status
        
        Returns:
            dict: System status and performance metrics
        """
        current_time = time.time()
        uptime = current_time - self.start_time
        
        # Get component metrics
        frame_producer_stats = self.frame_producer.get_performance_stats()
        client_manager_stats = self.client_manager.get_performance_summary()
        network_stats = self.network_tracker.get_performance_metrics()
        
        return {
            "system": {
                "is_running": self.is_running,
                "is_streaming": self.is_streaming,
                "uptime": uptime,
                "total_frames_processed": self.total_frames_processed,
                "average_fps": self.total_frames_processed / uptime if uptime > 0 else 0.0
            },
            "frame_producer": frame_producer_stats,
            "client_manager": client_manager_stats,
            "network_performance": network_stats,
            "memory_usage": frame_producer_stats.get("memory_usage", {}),
            "quality_levels": self.quality_levels
        }
    
    def get_client_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific client
        
        Args:
            client_id: Client to query
            
        Returns:
            dict: Client information or None if not found
        """
        return self.client_manager.get_client_info(client_id)
    
    def get_all_clients_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all clients
        
        Returns:
            dict: Dictionary of client information
        """
        return self.client_manager.get_all_clients_info()
    
    def get_active_clients(self) -> list:
        """
        Get list of active client IDs
        
        Returns:
            list: Active client IDs
        """
        return self.client_manager.get_active_clients()
    
    def force_client_quality(self, client_id: str, quality: int) -> bool:
        """
        Force a specific quality for a client
        
        Args:
            client_id: Target client
            quality: Quality percentage (30-85)
            
        Returns:
            bool: True if successful
        """
        return self.client_manager.force_client_quality(client_id, quality)
    
    def get_network_status(self) -> Dict[str, Any]:
        """
        Get current network performance status
        
        Returns:
            dict: Network status information
        """
        return {
            "status": self.network_tracker.get_current_status(),
            "trend": self.network_tracker.get_trend(),
            "metrics": self.network_tracker.get_performance_metrics(),
            "bandwidth_estimate": self.network_tracker.get_bandwidth_estimate(),
            "client_load_factor": self.network_tracker.get_client_load_factor()
        }
    
    def get_quality_recommendation(self, client_id: str) -> Optional[tuple]:
        """
        Get quality recommendation for a specific client
        
        Args:
            client_id: Client to get recommendation for
            
        Returns:
            tuple: (recommended_quality, reason) or None if client not found
        """
        client_info = self.client_manager.get_client_info(client_id)
        if not client_info:
            return None
        
        current_quality = client_info["current_quality"]
        return self.network_tracker.get_quality_recommendation(current_quality)
    
    def update_quality_levels(self, new_levels: list) -> bool:
        """
        Update available quality levels
        
        Args:
            new_levels: New list of quality percentages
            
        Returns:
            bool: True if update was successful
        """
        if self.frame_producer.update_quality_levels(new_levels):
            self.quality_levels = new_levels
            return True
        return False
    
    def clear_performance_data(self):
        """Clear all performance tracking data"""
        self.network_tracker.clear_samples()
        self.total_frames_processed = 0
        self.start_time = time.time()
        print("🧹 Performance data cleared")
    
    def get_memory_efficiency_report(self) -> Dict[str, Any]:
        """
        Get memory efficiency analysis
        
        Returns:
            dict: Memory efficiency report
        """
        memory_usage = self.frame_producer.get_memory_usage()
        client_count = len(self.get_active_clients())
        
        # Calculate memory per client
        memory_per_client = (
            memory_usage["total_memory_kb"] / client_count 
            if client_count > 0 else memory_usage["total_memory_kb"]
        )
        
        # Efficiency metrics
        target_memory_kb = 400  # Target: <400KB total memory usage
        efficiency_rating = min(target_memory_kb / memory_usage["total_memory_kb"], 1.0) if memory_usage["total_memory_kb"] > 0 else 1.0
        
        return {
            "total_memory_usage": memory_usage,
            "active_clients": client_count,
            "memory_per_client_kb": memory_per_client,
            "target_memory_kb": target_memory_kb,
            "efficiency_rating": efficiency_rating,
            "is_efficient": memory_usage["total_memory_kb"] <= target_memory_kb,
            "recommendations": self._get_memory_recommendations(memory_usage, client_count)
        }
    
    def _get_memory_recommendations(self, memory_usage: Dict, client_count: int) -> list:
        """Get memory optimization recommendations"""
        recommendations = []
        
        if memory_usage["total_memory_kb"] > 400:
            recommendations.append("Consider reducing quality levels count")
        
        if client_count > 5:
            recommendations.append("High client count may increase memory pressure")
        
        if memory_usage["total_memory_kb"] > 500:
            recommendations.append("Memory usage approaching Pi Zero 2W limits")
        
        if not recommendations:
            recommendations.append("Memory usage is optimal")
        
        return recommendations
    
    def get_status_summary(self) -> str:
        """
        Get human-readable status summary
        
        Returns:
            str: Concise status summary
        """
        system_status = self.get_system_status()
        memory_usage = system_status["memory_usage"]
        client_count = len(self.get_active_clients())
        
        return (
            f"🎬 Streaming: {'ON' if self.is_streaming else 'OFF'} | "
            f"Clients: {client_count} | "
            f"Memory: {memory_usage['total_memory_kb']:.1f}KB | "
            f"FPS: {system_status['system']['average_fps']:.1f} | "
            f"Network: {self.network_tracker.get_current_status()}"
        )