"""
Network Performance Monitoring

Handles background monitoring of network conditions and streaming performance
to support adaptive streaming quality adjustments.
"""

import time
import threading
from typing import Optional, Callable, Dict, Any
from src.config import AppConfig
from ..camera_exceptions import NetworkPerformanceError


class NetworkMonitor:
    """
    Background network performance monitoring for adaptive streaming
    
    Monitors streaming performance metrics and triggers adaptation
    callbacks when network conditions change.
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        
        # Monitoring state
        self.is_monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # References to other components
        self.stream_output = None
        self.quality_adapter = None
        self.adaptation_callback: Optional[Callable] = None
        
        # Performance tracking
        self.monitoring_cycles = 0
        self.adaptations_triggered = 0
        self.last_adaptation_time = 0.0
        
        # Network condition history
        self.network_history = []
        self.max_history_length = 10
    
    def set_components(self, stream_output, quality_adapter):
        """
        Set references to stream output and quality adapter
        
        Args:
            stream_output: StreamOutput instance for metrics
            quality_adapter: QualityAdapter instance for adaptations
        """
        self.stream_output = stream_output
        self.quality_adapter = quality_adapter
    
    def set_adaptation_callback(self, callback: Callable):
        """
        Set callback function to be called when adaptation occurs
        
        Args:
            callback: Function to call with adaptation results
        """
        self.adaptation_callback = callback
    
    def start_monitoring(self) -> bool:
        """
        Start background network monitoring
        
        Returns:
            bool: True if monitoring started successfully
        """
        if self.is_monitoring:
            print("⚠️  Network monitoring is already running")
            return True
        
        if not self.stream_output:
            print("❌ Cannot start monitoring: no stream output configured")
            return False
        
        try:
            self.is_monitoring = True
            self.monitor_thread = threading.Thread(
                target=self._monitoring_loop,
                daemon=True,
                name="NetworkMonitor"
            )
            self.monitor_thread.start()
            
            print("🔍 Network monitoring started")
            return True
            
        except Exception as e:
            print(f"❌ Failed to start network monitoring: {e}")
            self.is_monitoring = False
            return False
    
    def stop_monitoring(self) -> bool:
        """
        Stop background network monitoring
        
        Returns:
            bool: True if monitoring stopped successfully
        """
        if not self.is_monitoring:
            return True
        
        try:
            self.is_monitoring = False
            
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=3.0)
                if self.monitor_thread.is_alive():
                    print("⚠️  Network monitoring thread did not stop gracefully")
                    return False
            
            print("🔚 Network monitoring stopped")
            return True
            
        except Exception as e:
            print(f"❌ Error stopping network monitoring: {e}")
            return False
    
    def _monitoring_loop(self):
        """Main monitoring loop running in background thread"""
        print("🔍 Network monitoring loop started")
        
        while self.is_monitoring:
            try:
                time.sleep(self.config.network_check_interval)
                
                if not self.stream_output:
                    continue
                
                self.monitoring_cycles += 1
                
                # Get performance metrics
                metrics = self.stream_output.get_performance_metrics()
                
                # Store network condition in history
                self._update_network_history(metrics)
                
                # Perform adaptation if quality adapter is available
                if self.quality_adapter and (self.config.adaptive_streaming or self.config.adaptive_quality):
                    adaptation_result = self.quality_adapter.perform_adaptation(metrics)
                    
                    if adaptation_result.get("adapted", False):
                        self.adaptations_triggered += 1
                        self.last_adaptation_time = time.time()
                        
                        # Call adaptation callback if set
                        if self.adaptation_callback:
                            try:
                                self.adaptation_callback(adaptation_result, metrics)
                            except Exception as e:
                                print(f"⚠️  Adaptation callback error: {e}")
                        
                        print(f"🔄 Adaptation triggered: {adaptation_result}")
                
            except Exception as e:
                print(f"⚠️  Network monitoring error: {e}")
                time.sleep(1)  # Brief pause on error
        
        print("🔚 Network monitoring loop ended")
    
    def _update_network_history(self, metrics: Dict[str, Any]):
        """
        Update network condition history
        
        Args:
            metrics: Current performance metrics
        """
        condition = {
            "timestamp": time.time(),
            "network_slow": metrics.get("network_slow", False),
            "average_delivery_time": metrics.get("average_delivery_time", 0.0),
            "frames_delivered": metrics.get("frames_delivered", 0),
            "frames_dropped": metrics.get("frames_dropped", 0)
        }
        
        self.network_history.append(condition)
        
        # Keep only recent history
        if len(self.network_history) > self.max_history_length:
            self.network_history.pop(0)
    
    def get_network_trend(self) -> Dict[str, Any]:
        """
        Analyze network performance trend from history
        
        Returns:
            dict: Network trend analysis
        """
        if len(self.network_history) < 2:
            return {"trend": "insufficient_data", "confidence": 0.0}
        
        recent_conditions = self.network_history[-5:]  # Last 5 checks
        slow_count = sum(1 for c in recent_conditions if c["network_slow"])
        
        # Calculate average delivery time trend
        if len(recent_conditions) >= 2:
            recent_avg = sum(c["average_delivery_time"] for c in recent_conditions[-3:]) / 3
            older_avg = sum(c["average_delivery_time"] for c in recent_conditions[:2]) / 2
            delivery_trend = recent_avg - older_avg
        else:
            delivery_trend = 0.0
        
        # Determine overall trend
        if slow_count >= 3:
            trend = "degrading"
            confidence = min(slow_count / 5.0, 1.0)
        elif slow_count == 0 and delivery_trend < -0.5:
            trend = "improving"
            confidence = 0.8
        elif slow_count <= 1 and delivery_trend < 0.1:
            trend = "stable"
            confidence = 0.7
        else:
            trend = "unstable"
            confidence = 0.5
        
        return {
            "trend": trend,
            "confidence": confidence,
            "slow_periods": slow_count,
            "total_periods": len(recent_conditions),
            "delivery_trend": delivery_trend,
            "current_avg_delivery": recent_conditions[-1]["average_delivery_time"] if recent_conditions else 0.0
        }
    
    def get_monitoring_stats(self) -> Dict[str, Any]:
        """
        Get monitoring statistics
        
        Returns:
            dict: Monitoring performance statistics
        """
        uptime = time.time() - self.last_adaptation_time if self.last_adaptation_time > 0 else 0
        
        return {
            "is_monitoring": self.is_monitoring,
            "monitoring_cycles": self.monitoring_cycles,
            "adaptations_triggered": self.adaptations_triggered,
            "last_adaptation_time": self.last_adaptation_time,
            "time_since_last_adaptation": uptime,
            "network_history_length": len(self.network_history),
            "check_interval": self.config.network_check_interval,
            "adaptive_streaming_enabled": self.config.adaptive_streaming,
            "adaptive_quality_enabled": self.config.adaptive_quality
        }
    
    def force_network_check(self) -> Optional[Dict[str, Any]]:
        """
        Force an immediate network performance check
        
        Returns:
            dict: Check results or None if not available
        """
        if not self.stream_output:
            return None
        
        try:
            metrics = self.stream_output.get_performance_metrics()
            self._update_network_history(metrics)
            
            # Perform adaptation if available
            adaptation_result = None
            if self.quality_adapter:
                adaptation_result = self.quality_adapter.perform_adaptation(metrics)
                
                if adaptation_result.get("adapted", False):
                    self.adaptations_triggered += 1
                    self.last_adaptation_time = time.time()
            
            return {
                "metrics": metrics,
                "adaptation_result": adaptation_result,
                "network_trend": self.get_network_trend(),
                "forced_check": True,
                "timestamp": time.time()
            }
            
        except Exception as e:
            print(f"❌ Forced network check failed: {e}")
            return None
    
    def reset_monitoring_stats(self):
        """Reset monitoring statistics"""
        self.monitoring_cycles = 0
        self.adaptations_triggered = 0
        self.last_adaptation_time = 0.0
        self.network_history.clear()
        
        if self.stream_output:
            self.stream_output.reset_performance_counters()
        
        print("🔄 Monitoring statistics reset")
    
    def get_current_network_status(self) -> Dict[str, Any]:
        """
        Get current network status summary
        
        Returns:
            dict: Current network status
        """
        if not self.stream_output:
            return {"status": "unavailable", "reason": "no_stream_output"}
        
        try:
            metrics = self.stream_output.get_performance_metrics()
            trend = self.get_network_trend()
            
            # Determine overall status
            if metrics.get("network_slow", False):
                status = "poor"
            elif trend["trend"] == "improving":
                status = "improving"
            elif trend["trend"] == "degrading":
                status = "degrading"
            elif metrics.get("average_delivery_time", 0) < 1.0:
                status = "good"
            else:
                status = "fair"
            
            return {
                "status": status,
                "network_slow": metrics.get("network_slow", False),
                "average_delivery_time": metrics.get("average_delivery_time", 0.0),
                "trend": trend["trend"],
                "trend_confidence": trend["confidence"],
                "frames_delivered": metrics.get("frames_delivered", 0),
                "frames_dropped": metrics.get("frames_dropped", 0),
                "slow_deliveries": metrics.get("slow_deliveries", 0),
                "monitoring_active": self.is_monitoring
            }
            
        except Exception as e:
            return {"status": "error", "reason": str(e)}
    
    def is_network_stable(self, stability_threshold: int = 3) -> bool:
        """
        Check if network has been stable for a minimum number of checks
        
        Args:
            stability_threshold: Minimum number of stable checks required
            
        Returns:
            bool: True if network appears stable
        """
        if len(self.network_history) < stability_threshold:
            return False
        
        recent_checks = self.network_history[-stability_threshold:]
        slow_count = sum(1 for check in recent_checks if check["network_slow"])
        
        # Consider stable if no more than 1 slow period in recent checks
        return slow_count <= 1
    
    def get_adaptation_recommendations(self) -> Dict[str, Any]:
        """
        Get recommendations for manual adaptation
        
        Returns:
            dict: Adaptation recommendations
        """
        if not self.stream_output or not self.quality_adapter:
            return {"available": False, "reason": "components_not_ready"}
        
        try:
            metrics = self.stream_output.get_performance_metrics()
            recommendations = self.quality_adapter.get_recommended_settings(metrics)
            trend = self.get_network_trend()
            
            return {
                "available": True,
                "recommendations": recommendations,
                "current_metrics": metrics,
                "network_trend": trend,
                "manual_override_suggested": trend["trend"] == "unstable"
            }
            
        except Exception as e:
            return {"available": False, "reason": str(e)}
