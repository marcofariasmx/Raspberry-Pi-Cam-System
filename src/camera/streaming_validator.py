"""
Streaming Validator - Stream Health Verification and Validation

Validates streaming health, detects frozen frames, verifies stream quality,
and provides diagnostics for streaming issues.
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from src.config import AppConfig


class StreamHealth(Enum):
    """Stream health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class StreamMetrics:
    """Stream performance metrics"""
    frames_generated: int = 0
    frames_delivered: int = 0
    frames_dropped: int = 0
    frame_rate: float = 0.0
    quality_level: int = 0
    network_slow: bool = False
    last_frame_time: Optional[float] = None
    average_delivery_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class StreamingValidator:
    """
    Stream health validation and monitoring
    
    Provides:
    - Frame generation validation
    - Frozen frame detection
    - Stream quality assessment
    - Performance metrics validation
    - Automatic health reporting
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        
        # Component references
        self.camera_manager = None
        
        # Validation settings
        self.frame_timeout_seconds = 15.0  # Time before considering stream stale
        self.frozen_frame_threshold = 30.0  # Time before considering frames frozen
        self.min_acceptable_frame_rate = 1.0  # Minimum FPS to consider healthy
        self.max_acceptable_drop_rate = 0.3  # Maximum drop rate (30%)
        
        # Metrics tracking
        self.metrics_history: List[StreamMetrics] = []
        self.max_history_length = 20
        self.validation_lock = threading.RLock()
        
        # Health status
        self.current_health = StreamHealth.UNKNOWN
        self.last_validation_time: Optional[float] = None
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3
        
        # Frame tracking for frozen detection
        self.last_frame_count = 0
        self.last_frame_check_time = time.time()
        self.frame_progression_history: List[Dict[str, Any]] = []
        
        print("🔍 StreamingValidator initialized")
    
    def set_camera_manager(self, camera_manager):
        """Set camera manager reference"""
        self.camera_manager = camera_manager
    
    def validate_stream_health(self) -> Dict[str, Any]:
        """
        Perform comprehensive stream health validation
        
        Returns:
            Dict containing detailed health assessment
        """
        with self.validation_lock:
            self.last_validation_time = time.time()
            
            if not self.camera_manager:
                return self._create_health_report(
                    StreamHealth.UNKNOWN,
                    "Camera manager not available",
                    {}
                )
            
            # Check if streaming is active
            if not self.camera_manager.is_streaming:
                return self._create_health_report(
                    StreamHealth.OFFLINE,
                    "Streaming is not active",
                    {}
                )
            
            try:
                # Get current streaming metrics
                metrics = self._collect_current_metrics()
                
                # Validate frame generation
                frame_health = self._validate_frame_generation(metrics)
                
                # Validate stream performance
                performance_health = self._validate_stream_performance(metrics)
                
                # Validate network conditions
                network_health = self._validate_network_conditions(metrics)
                
                # Determine overall health
                overall_health = self._determine_overall_health(
                    frame_health, performance_health, network_health
                )
                
                # Store metrics
                self._store_metrics(metrics)
                
                # Update health status
                self.current_health = overall_health
                
                # Reset failure counter on success
                if overall_health in [StreamHealth.HEALTHY, StreamHealth.DEGRADED]:
                    self.consecutive_failures = 0
                else:
                    self.consecutive_failures += 1
                
                return self._create_health_report(
                    overall_health,
                    self._get_health_message(overall_health),
                    {
                        "frame_health": frame_health.value,
                        "performance_health": performance_health.value,
                        "network_health": network_health.value,
                        "metrics": self._metrics_to_dict(metrics),
                        "consecutive_failures": self.consecutive_failures
                    }
                )
                
            except Exception as e:
                self.consecutive_failures += 1
                return self._create_health_report(
                    StreamHealth.CRITICAL,
                    f"Validation failed: {str(e)}",
                    {"error": str(e), "consecutive_failures": self.consecutive_failures}
                )
    
    def _collect_current_metrics(self) -> StreamMetrics:
        """Collect current streaming metrics"""
        try:
            # Get streaming stats from camera manager
            if not self.camera_manager:
                return StreamMetrics()
            stats = self.camera_manager.get_streaming_stats()
            
            performance = stats.get("performance", {})
            adaptation = stats.get("adaptation", {})
            
            return StreamMetrics(
                frames_generated=performance.get("frames_written", 0),
                frames_delivered=performance.get("frames_delivered", 0),
                frames_dropped=performance.get("frames_dropped", 0),
                frame_rate=adaptation.get("current_frame_rate", 0),
                quality_level=adaptation.get("current_quality", 0),
                network_slow=performance.get("network_slow", False),
                last_frame_time=time.time(),
                average_delivery_time=performance.get("average_delivery_time", 0.0)
            )
            
        except Exception as e:
            print(f"❌ Failed to collect metrics: {e}")
            return StreamMetrics()
    
    def _validate_frame_generation(self, metrics: StreamMetrics) -> StreamHealth:
        """Validate frame generation health"""
        try:
            current_time = time.time()
            
            # Check if frames are being generated
            if metrics.frames_generated == 0:
                return StreamHealth.CRITICAL
            
            # Check for frozen frames by comparing frame counts
            if hasattr(self, '_last_metrics') and self._last_metrics:
                time_diff = (metrics.timestamp - self._last_metrics.timestamp).total_seconds()
                frame_diff = metrics.frames_generated - self._last_metrics.frames_generated
                
                if time_diff > 5.0 and frame_diff == 0:  # No new frames in 5+ seconds
                    return StreamHealth.CRITICAL
            
            # Check frame rate
            if metrics.frame_rate < self.min_acceptable_frame_rate:
                return StreamHealth.DEGRADED
            
            # Check for excessive frame drops
            if metrics.frames_generated > 0:
                drop_rate = metrics.frames_dropped / max(metrics.frames_generated, 1)
                if drop_rate > self.max_acceptable_drop_rate:
                    return StreamHealth.DEGRADED
            
            return StreamHealth.HEALTHY
            
        except Exception as e:
            print(f"❌ Frame generation validation failed: {e}")
            return StreamHealth.UNKNOWN
    
    def _validate_stream_performance(self, metrics: StreamMetrics) -> StreamHealth:
        """Validate stream performance health"""
        try:
            # Check delivery performance
            if metrics.average_delivery_time > 5.0:  # >5 seconds is critical
                return StreamHealth.CRITICAL
            elif metrics.average_delivery_time > 2.0:  # >2 seconds is degraded
                return StreamHealth.DEGRADED
            
            # Check frame delivery ratio
            if metrics.frames_generated > 0:
                delivery_ratio = metrics.frames_delivered / max(metrics.frames_generated, 1)
                if delivery_ratio < 0.5:  # Less than 50% delivery
                    return StreamHealth.CRITICAL
                elif delivery_ratio < 0.8:  # Less than 80% delivery
                    return StreamHealth.DEGRADED
            
            return StreamHealth.HEALTHY
            
        except Exception as e:
            print(f"❌ Performance validation failed: {e}")
            return StreamHealth.UNKNOWN
    
    def _validate_network_conditions(self, metrics: StreamMetrics) -> StreamHealth:
        """Validate network conditions"""
        try:
            # Check network slow flag
            if metrics.network_slow:
                return StreamHealth.DEGRADED
            
            # Check for high delivery times indicating network issues
            if metrics.average_delivery_time > 3.0:
                return StreamHealth.DEGRADED
            
            return StreamHealth.HEALTHY
            
        except Exception as e:
            print(f"❌ Network validation failed: {e}")
            return StreamHealth.UNKNOWN
    
    def _determine_overall_health(self, frame_health: StreamHealth, 
                                 performance_health: StreamHealth, 
                                 network_health: StreamHealth) -> StreamHealth:
        """Determine overall stream health from individual components"""
        healths = [frame_health, performance_health, network_health]
        
        # If any component is critical, overall is critical
        if StreamHealth.CRITICAL in healths:
            return StreamHealth.CRITICAL
        
        # If any component is degraded, overall is degraded
        if StreamHealth.DEGRADED in healths:
            return StreamHealth.DEGRADED
        
        # If any component is unknown, overall is unknown
        if StreamHealth.UNKNOWN in healths:
            return StreamHealth.UNKNOWN
        
        # All components healthy
        return StreamHealth.HEALTHY
    
    def _get_health_message(self, health: StreamHealth) -> str:
        """Get descriptive message for health status"""
        messages = {
            StreamHealth.HEALTHY: "Stream is operating normally",
            StreamHealth.DEGRADED: "Stream performance is degraded",
            StreamHealth.CRITICAL: "Stream has critical issues",
            StreamHealth.OFFLINE: "Stream is not active",
            StreamHealth.UNKNOWN: "Stream health cannot be determined"
        }
        return messages.get(health, "Unknown health status")
    
    def _store_metrics(self, metrics: StreamMetrics):
        """Store metrics in history"""
        self.metrics_history.append(metrics)
        
        # Keep only recent metrics
        if len(self.metrics_history) > self.max_history_length:
            self.metrics_history.pop(0)
        
        # Store for comparison
        self._last_metrics = metrics
    
    def _metrics_to_dict(self, metrics: StreamMetrics) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        return {
            "frames_generated": metrics.frames_generated,
            "frames_delivered": metrics.frames_delivered,
            "frames_dropped": metrics.frames_dropped,
            "frame_rate": metrics.frame_rate,
            "quality_level": metrics.quality_level,
            "network_slow": metrics.network_slow,
            "average_delivery_time": metrics.average_delivery_time,
            "timestamp": metrics.timestamp.isoformat() if metrics.timestamp else None
        }
    
    def _create_health_report(self, health: StreamHealth, message: str, 
                             details: Dict[str, Any]) -> Dict[str, Any]:
        """Create standardized health report"""
        return {
            "health_status": health.value,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "validation_time": self.last_validation_time,
            "consecutive_failures": self.consecutive_failures,
            "details": details
        }
    
    def detect_frozen_frames(self) -> Dict[str, Any]:
        """
        Detect if frames are frozen or stale
        
        Returns:
            Dict containing frozen frame detection results
        """
        try:
            if not self.camera_manager or not self.camera_manager.is_streaming:
                return {
                    "frozen": False,
                    "reason": "Streaming not active",
                    "timestamp": datetime.now().isoformat()
                }
            
            current_time = time.time()
            
            # Get current frame count
            stats = self.camera_manager.get_streaming_stats()
            current_frame_count = stats.get("adaptation", {}).get("frames_sent", 0)
            
            # Track frame progression
            progression_entry = {
                "time": current_time,
                "frame_count": current_frame_count,
                "timestamp": datetime.now().isoformat()
            }
            
            self.frame_progression_history.append(progression_entry)
            
            # Keep only recent history
            cutoff_time = current_time - self.frozen_frame_threshold
            self.frame_progression_history = [
                entry for entry in self.frame_progression_history
                if entry["time"] > cutoff_time
            ]
            
            # Check for frozen frames
            if len(self.frame_progression_history) >= 2:
                # Check if frame count has changed over time
                oldest_entry = self.frame_progression_history[0]
                latest_entry = self.frame_progression_history[-1]
                
                time_span = latest_entry["time"] - oldest_entry["time"]
                frame_progression = latest_entry["frame_count"] - oldest_entry["frame_count"]
                
                if time_span > 10.0 and frame_progression == 0:  # No progression in 10+ seconds
                    return {
                        "frozen": True,
                        "reason": f"No frame progression detected in {time_span:.1f} seconds",
                        "time_span": time_span,
                        "frame_count": current_frame_count,
                        "timestamp": datetime.now().isoformat()
                    }
            
            return {
                "frozen": False,
                "reason": "Frames progressing normally",
                "frame_count": current_frame_count,
                "progression_history_length": len(self.frame_progression_history),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "frozen": None,
                "reason": f"Detection failed: {str(e)}",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def get_performance_trends(self) -> Dict[str, Any]:
        """Get performance trends from metrics history"""
        if not self.metrics_history:
            return {"error": "No metrics history available"}
        
        try:
            # Calculate trends
            frame_rates = [m.frame_rate for m in self.metrics_history if m.frame_rate > 0]
            delivery_times = [m.average_delivery_time for m in self.metrics_history if m.average_delivery_time > 0]
            drop_rates = []
            
            for m in self.metrics_history:
                if m.frames_generated > 0:
                    drop_rates.append(m.frames_dropped / m.frames_generated)
            
            return {
                "frame_rate": {
                    "current": frame_rates[-1] if frame_rates else 0,
                    "average": sum(frame_rates) / len(frame_rates) if frame_rates else 0,
                    "min": min(frame_rates) if frame_rates else 0,
                    "max": max(frame_rates) if frame_rates else 0,
                    "samples": len(frame_rates)
                },
                "delivery_time": {
                    "current": delivery_times[-1] if delivery_times else 0,
                    "average": sum(delivery_times) / len(delivery_times) if delivery_times else 0,
                    "min": min(delivery_times) if delivery_times else 0,
                    "max": max(delivery_times) if delivery_times else 0,
                    "samples": len(delivery_times)
                },
                "drop_rate": {
                    "current": drop_rates[-1] if drop_rates else 0,
                    "average": sum(drop_rates) / len(drop_rates) if drop_rates else 0,
                    "min": min(drop_rates) if drop_rates else 0,
                    "max": max(drop_rates) if drop_rates else 0,
                    "samples": len(drop_rates)
                },
                "health_status": self.current_health.value,
                "metrics_count": len(self.metrics_history),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"Trend analysis failed: {str(e)}"}
    
    def validate_stream_quality(self) -> Dict[str, Any]:
        """Validate overall stream quality"""
        try:
            # Get current health
            health_report = self.validate_stream_health()
            
            # Get frozen frame status
            frozen_status = self.detect_frozen_frames()
            
            # Get performance trends
            trends = self.get_performance_trends()
            
            # Determine quality score (0-100)
            quality_score = self._calculate_quality_score(health_report, frozen_status, trends)
            
            return {
                "quality_score": quality_score,
                "health_report": health_report,
                "frozen_frame_status": frozen_status,
                "performance_trends": trends,
                "validation_timestamp": datetime.now().isoformat(),
                "recommendations": self._get_quality_recommendations(quality_score, health_report)
            }
            
        except Exception as e:
            return {
                "error": f"Quality validation failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _calculate_quality_score(self, health_report: Dict[str, Any], 
                                frozen_status: Dict[str, Any], 
                                trends: Dict[str, Any]) -> int:
        """Calculate overall quality score (0-100)"""
        try:
            score = 100
            
            # Health status penalties
            health = health_report.get("health_status", "unknown")
            if health == "critical":
                score -= 50
            elif health == "degraded":
                score -= 25
            elif health == "offline":
                score = 0
            elif health == "unknown":
                score -= 15
            
            # Frozen frame penalties
            if frozen_status.get("frozen"):
                score -= 40
            
            # Performance trend penalties
            if "error" not in trends:
                frame_rate = trends.get("frame_rate", {})
                delivery_time = trends.get("delivery_time", {})
                drop_rate = trends.get("drop_rate", {})
                
                # Frame rate score
                current_fps = frame_rate.get("current", 0)
                if current_fps < 1:
                    score -= 20
                elif current_fps < 5:
                    score -= 10
                
                # Delivery time score
                current_delivery = delivery_time.get("current", 0)
                if current_delivery > 5:
                    score -= 20
                elif current_delivery > 2:
                    score -= 10
                
                # Drop rate score
                current_drops = drop_rate.get("current", 0)
                if current_drops > 0.5:
                    score -= 15
                elif current_drops > 0.2:
                    score -= 8
            
            # Consecutive failures penalty
            failures = health_report.get("consecutive_failures", 0)
            if failures > 0:
                score -= failures * 5
            
            return max(0, min(100, score))
            
        except Exception as e:
            print(f"❌ Quality score calculation failed: {e}")
            return 0
    
    def _get_quality_recommendations(self, quality_score: int, 
                                   health_report: Dict[str, Any]) -> List[str]:
        """Get recommendations based on quality assessment"""
        recommendations = []
        
        if quality_score < 30:
            recommendations.append("Consider restarting the camera system")
            recommendations.append("Check camera hardware connections")
            recommendations.append("Verify network connectivity")
        elif quality_score < 60:
            recommendations.append("Monitor system performance")
            recommendations.append("Check for network congestion")
            recommendations.append("Consider reducing stream quality")
        elif quality_score < 80:
            recommendations.append("System is functioning but may benefit from optimization")
            recommendations.append("Monitor trends for degradation")
        
        # Specific recommendations based on health status
        health_status = health_report.get("health_status", "unknown")
        if health_status == "critical":
            recommendations.append("Immediate attention required - critical issues detected")
        elif health_status == "degraded":
            recommendations.append("Performance degradation detected - investigate causes")
        
        return recommendations
    
    def reset_validation_state(self):
        """Reset validation state and metrics"""
        with self.validation_lock:
            self.metrics_history.clear()
            self.frame_progression_history.clear()
            self.current_health = StreamHealth.UNKNOWN
            self.consecutive_failures = 0
            self.last_validation_time = None
            print("🔍 StreamingValidator state reset")
    
    def get_validator_status(self) -> Dict[str, Any]:
        """Get validator status and configuration"""
        return {
            "current_health": self.current_health.value,
            "last_validation_time": self.last_validation_time,
            "consecutive_failures": self.consecutive_failures,
            "metrics_history_length": len(self.metrics_history),
            "frame_progression_history_length": len(self.frame_progression_history),
            "configuration": {
                "frame_timeout_seconds": self.frame_timeout_seconds,
                "frozen_frame_threshold": self.frozen_frame_threshold,
                "min_acceptable_frame_rate": self.min_acceptable_frame_rate,
                "max_acceptable_drop_rate": self.max_acceptable_drop_rate,
                "max_consecutive_failures": self.max_consecutive_failures
            },
            "timestamp": datetime.now().isoformat()
        }
