"""
Streaming Statistics and Metrics

Handles collection, aggregation, and reporting of streaming performance
statistics for monitoring and analysis.
"""

import time
from typing import Dict, Any, List, Optional
from datetime import datetime


class StreamingStats:
    """
    Collects and manages streaming performance statistics
    
    Provides comprehensive metrics about streaming performance,
    adaptive changes, and system behavior over time.
    """
    
    def __init__(self):
        # Performance counters
        self.total_frames_sent = 0
        self.total_frames_dropped = 0
        self.total_adaptations = 0
        
        # Session tracking
        self.session_start_time = time.time()
        self.last_reset_time = time.time()
        
        # Adaptation history
        self.adaptation_history: List[Dict[str, Any]] = []
        self.max_history_entries = 50
        
        # Quality/frame rate tracking
        self.quality_changes = 0
        self.frame_rate_changes = 0
        self.min_quality_reached = 100
        self.max_quality_reached = 0
        self.min_frame_rate_reached = 60
        self.max_frame_rate_reached = 0
        
        # Network condition tracking
        self.slow_network_periods = 0
        self.stable_network_periods = 0
        self.network_condition_changes = 0
        self.last_network_condition = "unknown"
        
        # Performance samples
        self.delivery_time_samples: List[float] = []
        self.frame_interval_samples: List[float] = []
        self.max_samples = 100
    
    def record_frame_sent(self):
        """Record a successfully sent frame"""
        self.total_frames_sent += 1
    
    def record_frame_dropped(self):
        """Record a dropped frame"""
        self.total_frames_dropped += 1
    
    def record_adaptation(self, adaptation_result: Dict[str, Any], metrics: Dict[str, Any]):
        """
        Record an adaptation event
        
        Args:
            adaptation_result: Results from quality adapter
            metrics: Current performance metrics
        """
        self.total_adaptations += 1
        
        # Track specific changes
        if adaptation_result.get("quality_changed", False):
            self.quality_changes += 1
        
        if adaptation_result.get("frame_rate_changed", False):
            self.frame_rate_changes += 1
        
        # Update quality/frame rate ranges
        current_quality = adaptation_result.get("current_quality", 0)
        current_frame_rate = adaptation_result.get("current_frame_rate", 0)
        
        if current_quality > 0:
            self.min_quality_reached = min(self.min_quality_reached, current_quality)
            self.max_quality_reached = max(self.max_quality_reached, current_quality)
        
        if current_frame_rate > 0:
            self.min_frame_rate_reached = min(self.min_frame_rate_reached, current_frame_rate)
            self.max_frame_rate_reached = max(self.max_frame_rate_reached, current_frame_rate)
        
        # Store adaptation history
        adaptation_event = {
            "timestamp": time.time(),
            "adaptation_result": adaptation_result.copy(),
            "metrics": {
                "network_slow": metrics.get("network_slow", False),
                "average_delivery_time": metrics.get("average_delivery_time", 0.0),
                "frames_delivered": metrics.get("frames_delivered", 0),
                "frames_dropped": metrics.get("frames_dropped", 0),
                "intended_delivery_efficiency": adaptation_result.get("intended_delivery_efficiency", 1.0)
            }
        }
        
        self.adaptation_history.append(adaptation_event)
        
        # Keep history within limits
        if len(self.adaptation_history) > self.max_history_entries:
            self.adaptation_history.pop(0)
    
    def record_network_condition(self, condition: str):
        """
        Record network condition change
        
        Args:
            condition: Network condition (slow, stable, etc.)
        """
        if condition != self.last_network_condition:
            self.network_condition_changes += 1
            self.last_network_condition = condition
        
        if condition == "slow":
            self.slow_network_periods += 1
        elif condition == "stable":
            self.stable_network_periods += 1
    
    def record_delivery_time(self, delivery_time: float):
        """
        Record frame delivery time sample
        
        Args:
            delivery_time: Time taken to deliver frame (seconds)
        """
        self.delivery_time_samples.append(delivery_time)
        
        # Keep only recent samples
        if len(self.delivery_time_samples) > self.max_samples:
            self.delivery_time_samples.pop(0)
    
    def record_frame_interval(self, interval: float):
        """
        Record frame interval sample
        
        Args:
            interval: Time between frames (seconds)
        """
        self.frame_interval_samples.append(interval)
        
        # Keep only recent samples
        if len(self.frame_interval_samples) > self.max_samples:
            self.frame_interval_samples.pop(0)
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive streaming statistics
        
        Returns:
            dict: Complete statistics report
        """
        current_time = time.time()
        session_duration = current_time - self.session_start_time
        time_since_reset = current_time - self.last_reset_time
        
        # Calculate rates
        total_frames = self.total_frames_sent + self.total_frames_dropped
        success_rate = (self.total_frames_sent / total_frames) if total_frames > 0 else 0.0
        
        # Calculate average delivery time
        avg_delivery_time = (
            sum(self.delivery_time_samples) / len(self.delivery_time_samples)
            if self.delivery_time_samples else 0.0
        )
        
        # Calculate average frame rate
        avg_frame_interval = (
            sum(self.frame_interval_samples) / len(self.frame_interval_samples)
            if self.frame_interval_samples else 0.033
        )
        avg_frame_rate = 1.0 / avg_frame_interval if avg_frame_interval > 0 else 30.0
        
        return {
            "session": {
                "start_time": datetime.fromtimestamp(self.session_start_time).isoformat(),
                "duration_seconds": session_duration,
                "duration_minutes": session_duration / 60.0,
                "time_since_reset": time_since_reset
            },
            "frames": {
                "total_sent": self.total_frames_sent,
                "total_dropped": self.total_frames_dropped,
                "total_attempted": total_frames,
                "success_rate": success_rate,
                "drop_rate": 1.0 - success_rate,
                "frames_per_second": self.total_frames_sent / session_duration if session_duration > 0 else 0.0
            },
            "adaptations": {
                "total_adaptations": self.total_adaptations,
                "quality_changes": self.quality_changes,
                "frame_rate_changes": self.frame_rate_changes,
                "adaptations_per_hour": self.total_adaptations / (session_duration / 3600) if session_duration > 0 else 0.0
            },
            "quality_range": {
                "min_quality": self.min_quality_reached if self.min_quality_reached < 100 else None,
                "max_quality": self.max_quality_reached if self.max_quality_reached > 0 else None,
                "quality_span": self.max_quality_reached - self.min_quality_reached if self.max_quality_reached > 0 else 0
            },
            "frame_rate_range": {
                "min_frame_rate": self.min_frame_rate_reached if self.min_frame_rate_reached < 60 else None,
                "max_frame_rate": self.max_frame_rate_reached if self.max_frame_rate_reached > 0 else None,
                "frame_rate_span": self.max_frame_rate_reached - self.min_frame_rate_reached if self.max_frame_rate_reached > 0 else 0
            },
            "network": {
                "slow_periods": self.slow_network_periods,
                "stable_periods": self.stable_network_periods,
                "condition_changes": self.network_condition_changes,
                "current_condition": self.last_network_condition
            },
            "performance": {
                "average_delivery_time": avg_delivery_time,
                "average_frame_rate": avg_frame_rate,
                "delivery_samples": len(self.delivery_time_samples),
                "frame_interval_samples": len(self.frame_interval_samples)
            }
        }
    
    def get_recent_adaptations(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent adaptation events
        
        Args:
            count: Number of recent adaptations to return
            
        Returns:
            list: Recent adaptation events
        """
        return self.adaptation_history[-count:] if self.adaptation_history else []
    
    def get_adaptation_summary(self) -> Dict[str, Any]:
        """
        Get a summary of adaptation patterns
        
        Returns:
            dict: Adaptation pattern summary
        """
        if not self.adaptation_history:
            return {"adaptations": 0, "patterns": "no_data"}
        
        recent_adaptations = self.adaptation_history[-10:]
        
        # Analyze adaptation patterns
        quality_increases = sum(1 for a in recent_adaptations 
                              if a["adaptation_result"].get("quality_changed", False) 
                              and "increased" in str(a))
        
        quality_decreases = sum(1 for a in recent_adaptations 
                              if a["adaptation_result"].get("quality_changed", False) 
                              and "reduced" in str(a))
        
        frame_rate_increases = sum(1 for a in recent_adaptations 
                                 if a["adaptation_result"].get("frame_rate_changed", False) 
                                 and "increased" in str(a))
        
        frame_rate_decreases = sum(1 for a in recent_adaptations 
                                 if a["adaptation_result"].get("frame_rate_changed", False) 
                                 and "reduced" in str(a))
        
        # Determine pattern
        if quality_decreases > quality_increases and frame_rate_decreases > frame_rate_increases:
            pattern = "degrading_performance"
        elif quality_increases > quality_decreases and frame_rate_increases > frame_rate_decreases:
            pattern = "improving_performance"
        elif abs(quality_increases - quality_decreases) <= 1 and abs(frame_rate_increases - frame_rate_decreases) <= 1:
            pattern = "stable_with_minor_adjustments"
        else:
            pattern = "mixed_adaptations"
        
        return {
            "total_adaptations": len(self.adaptation_history),
            "recent_adaptations": len(recent_adaptations),
            "pattern": pattern,
            "quality_changes": {
                "increases": quality_increases,
                "decreases": quality_decreases
            },
            "frame_rate_changes": {
                "increases": frame_rate_increases,
                "decreases": frame_rate_decreases
            }
        }
    
    def get_performance_trends(self) -> Dict[str, Any]:
        """
        Get performance trends analysis
        
        Returns:
            dict: Performance trends
        """
        if len(self.delivery_time_samples) < 5:
            return {"trend": "insufficient_data"}
        
        # Calculate trend over recent samples
        recent_samples = self.delivery_time_samples[-10:]
        older_samples = self.delivery_time_samples[-20:-10] if len(self.delivery_time_samples) >= 20 else []
        
        recent_avg = sum(recent_samples) / len(recent_samples)
        older_avg = sum(older_samples) / len(older_samples) if older_samples else recent_avg
        
        # Determine trend
        difference = recent_avg - older_avg
        if abs(difference) < 0.1:
            trend = "stable"
        elif difference > 0.1:
            trend = "degrading"
        else:
            trend = "improving"
        
        # Calculate frame rate trend
        frame_rate_trend = "stable"
        if self.frame_interval_samples:
            recent_intervals = self.frame_interval_samples[-10:]
            older_intervals = self.frame_interval_samples[-20:-10] if len(self.frame_interval_samples) >= 20 else []
            
            if older_intervals:
                recent_fps = 1.0 / (sum(recent_intervals) / len(recent_intervals))
                older_fps = 1.0 / (sum(older_intervals) / len(older_intervals))
                fps_difference = recent_fps - older_fps
                
                if abs(fps_difference) < 1.0:
                    frame_rate_trend = "stable"
                elif fps_difference > 1.0:
                    frame_rate_trend = "improving"
                else:
                    frame_rate_trend = "degrading"
        
        return {
            "delivery_time_trend": trend,
            "frame_rate_trend": frame_rate_trend,
            "recent_avg_delivery": recent_avg,
            "older_avg_delivery": older_avg,
            "delivery_time_change": difference,
            "samples_analyzed": len(recent_samples)
        }
    
    def reset_stats(self):
        """Reset all statistics to start fresh"""
        self.total_frames_sent = 0
        self.total_frames_dropped = 0
        self.total_adaptations = 0
        
        self.last_reset_time = time.time()
        
        self.adaptation_history.clear()
        
        self.quality_changes = 0
        self.frame_rate_changes = 0
        self.min_quality_reached = 100
        self.max_quality_reached = 0
        self.min_frame_rate_reached = 60
        self.max_frame_rate_reached = 0
        
        self.slow_network_periods = 0
        self.stable_network_periods = 0
        self.network_condition_changes = 0
        self.last_network_condition = "unknown"
        
        self.delivery_time_samples.clear()
        self.frame_interval_samples.clear()
        
        print("📊 Streaming statistics reset")
    
    def export_stats_summary(self) -> str:
        """
        Export statistics summary as formatted string
        
        Returns:
            str: Formatted statistics summary
        """
        stats = self.get_comprehensive_stats()
        
        summary = []
        summary.append("📊 Streaming Statistics Summary")
        summary.append("=" * 40)
        
        # Session info
        session = stats["session"]
        summary.append(f"Session Duration: {session['duration_minutes']:.1f} minutes")
        summary.append(f"Started: {session['start_time']}")
        
        # Frame statistics
        frames = stats["frames"]
        summary.append(f"\nFrame Statistics:")
        summary.append(f"  Sent: {frames['total_sent']}")
        summary.append(f"  Dropped: {frames['total_dropped']}")
        summary.append(f"  Success Rate: {frames['success_rate']:.1%}")
        summary.append(f"  Average FPS: {frames['frames_per_second']:.1f}")
        
        # Adaptation statistics
        adaptations = stats["adaptations"]
        summary.append(f"\nAdaptations:")
        summary.append(f"  Total: {adaptations['total_adaptations']}")
        summary.append(f"  Quality Changes: {adaptations['quality_changes']}")
        summary.append(f"  Frame Rate Changes: {adaptations['frame_rate_changes']}")
        
        # Performance
        performance = stats["performance"]
        summary.append(f"\nPerformance:")
        summary.append(f"  Avg Delivery Time: {performance['average_delivery_time']:.3f}s")
        summary.append(f"  Avg Frame Rate: {performance['average_frame_rate']:.1f} fps")
        
        return "\n".join(summary)
