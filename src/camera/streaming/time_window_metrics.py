"""
Time-Windowed Metrics System

Provides time-based performance measurement windows for adaptive streaming.
Replaces cumulative metrics with recent performance tracking for more responsive
and accurate network condition assessment.
"""

import time
import threading
from typing import Dict, List, Optional, Tuple, Any
from collections import deque
from dataclasses import dataclass
from enum import Enum


class MetricType(Enum):
    """Types of metrics tracked in time windows"""
    DELIVERY_RATIO = "delivery_ratio"
    DELIVERY_TIME = "delivery_time" 
    FRAME_RATE = "frame_rate"
    QUALITY_LEVEL = "quality_level"
    BYTES_DELIVERED = "bytes_delivered"


@dataclass
class MetricSample:
    """A single metric sample with timestamp"""
    timestamp: float
    value: float
    metadata: Optional[Dict[str, Any]] = None
    
    def age(self) -> float:
        """Get sample age in seconds"""
        return time.time() - self.timestamp
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class TimeWindow:
    """
    Time-based sliding window for metric collection
    
    Maintains samples within a specified time window and provides
    statistical analysis with exponential decay weighting.
    """
    
    def __init__(self, window_duration: float, decay_factor: float = 0.9):
        """
        Initialize time window
        
        Args:
            window_duration: Window duration in seconds
            decay_factor: Exponential decay factor (0.0-1.0, higher = less decay)
        """
        self.window_duration = window_duration
        self.decay_factor = decay_factor
        self.samples: deque[MetricSample] = deque()
        self._lock = threading.RLock()
        
    def add_sample(self, value: float, metadata: Optional[Dict[str, Any]] = None):
        """
        Add a new sample to the window
        
        Args:
            value: Metric value
            metadata: Additional sample metadata
        """
        current_time = time.time()
        sample = MetricSample(current_time, value, metadata or {})
        
        with self._lock:
            self.samples.append(sample)
            self._cleanup_old_samples()
    
    def _cleanup_old_samples(self):
        """Remove samples older than window duration"""
        current_time = time.time()
        cutoff_time = current_time - self.window_duration
        
        while self.samples and self.samples[0].timestamp < cutoff_time:
            self.samples.popleft()
    
    def get_samples(self, max_age: Optional[float] = None) -> List[MetricSample]:
        """
        Get all samples within window (or max_age if specified)
        
        Args:
            max_age: Maximum sample age in seconds (uses window_duration if None)
            
        Returns:
            List of samples within time limit
        """
        with self._lock:
            self._cleanup_old_samples()
            
            if max_age is None:
                return list(self.samples)
            
            current_time = time.time()
            cutoff_time = current_time - max_age
            return [s for s in self.samples if s.timestamp >= cutoff_time]
    
    def get_weighted_average(self, max_age: Optional[float] = None) -> float:
        """
        Get exponentially weighted average of samples
        
        Args:
            max_age: Maximum sample age to consider
            
        Returns:
            Weighted average value
        """
        samples = self.get_samples(max_age)
        if not samples:
            return 0.0
        
        current_time = time.time()
        total_weight = 0.0
        weighted_sum = 0.0
        
        for sample in samples:
            # Calculate exponential decay weight based on age
            age = current_time - sample.timestamp
            weight = self.decay_factor ** (age / self.window_duration)
            
            weighted_sum += sample.value * weight
            total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def get_recent_average(self, duration: float) -> float:
        """
        Get simple average of samples within recent duration
        
        Args:
            duration: Recent duration in seconds
            
        Returns:
            Simple average of recent samples
        """
        samples = self.get_samples(duration)
        if not samples:
            return 0.0
        
        return sum(s.value for s in samples) / len(samples)
    
    def get_trend(self, split_duration: Optional[float] = None) -> Tuple[str, float]:
        """
        Analyze trend direction and magnitude
        
        Args:
            split_duration: Duration to split window for comparison (uses half window if None)
            
        Returns:
            Tuple of (trend_direction, change_magnitude)
        """
        if split_duration is None:
            split_duration = self.window_duration / 2
        
        recent_avg = self.get_recent_average(split_duration)
        older_avg = self.get_recent_average(self.window_duration) - recent_avg
        
        if abs(recent_avg - older_avg) < 0.01:  # Minimal change threshold
            return "stable", 0.0
        
        change = recent_avg - older_avg
        if change > 0:
            return "improving", change
        else:
            return "degrading", abs(change)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive window statistics
        
        Returns:
            Dictionary of statistics
        """
        samples = self.get_samples()
        if not samples:
            return {
                "sample_count": 0,
                "weighted_average": 0.0,
                "simple_average": 0.0,
                "min_value": 0.0,
                "max_value": 0.0,
                "trend": "unknown",
                "trend_magnitude": 0.0
            }
        
        values = [s.value for s in samples]
        trend, magnitude = self.get_trend()
        
        return {
            "sample_count": len(samples),
            "weighted_average": self.get_weighted_average(),
            "simple_average": sum(values) / len(values),
            "min_value": min(values),
            "max_value": max(values),
            "std_dev": self._calculate_std_dev(values),
            "trend": trend,
            "trend_magnitude": magnitude,
            "window_duration": self.window_duration,
            "oldest_sample_age": samples[0].age() if samples else 0.0,
            "newest_sample_age": samples[-1].age() if samples else 0.0
        }
    
    def _calculate_std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation of values"""
        if len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5
    
    def clear(self):
        """Clear all samples from window"""
        with self._lock:
            self.samples.clear()
    
    def is_empty(self) -> bool:
        """Check if window has any samples"""
        with self._lock:
            self._cleanup_old_samples()
            return len(self.samples) == 0
    
    def __len__(self) -> int:
        """Get number of samples in window"""
        with self._lock:
            self._cleanup_old_samples()
            return len(self.samples)


class TimeWindowMetrics:
    """
    Multi-metric time window collection for comprehensive performance tracking
    
    Manages multiple TimeWindow instances for different metrics with
    unified analysis and decision making capabilities.
    """
    
    def __init__(self):
        """Initialize time window metrics collection"""
        self.windows: Dict[str, TimeWindow] = {}
        self._lock = threading.RLock()
        
        # Create standard windows for adaptive streaming
        self.create_window("delivery_ratio_fast", 10.0, 0.95)  # Fast degradation detection
        self.create_window("delivery_ratio_stable", 30.0, 0.9)  # Stable recovery assessment
        self.create_window("delivery_time", 15.0, 0.92)
        self.create_window("frame_rate", 20.0, 0.88)
        self.create_window("quality_level", 25.0, 0.85)
        
    def create_window(self, name: str, duration: float, decay_factor: float = 0.9) -> TimeWindow:
        """
        Create a new time window
        
        Args:
            name: Window identifier
            duration: Window duration in seconds
            decay_factor: Exponential decay factor
            
        Returns:
            Created TimeWindow instance
        """
        with self._lock:
            window = TimeWindow(duration, decay_factor)
            self.windows[name] = window
            return window
    
    def add_sample(self, window_name: str, value: float, metadata: Optional[Dict[str, Any]] = None):
        """
        Add sample to specified window
        
        Args:
            window_name: Target window name
            value: Metric value
            metadata: Sample metadata
        """
        with self._lock:
            if window_name in self.windows:
                self.windows[window_name].add_sample(value, metadata or {})
    
    def get_window(self, name: str) -> Optional[TimeWindow]:
        """Get window by name"""
        return self.windows.get(name)
    
    def get_delivery_ratio_assessment(self) -> Dict[str, Any]:
        """
        Get comprehensive delivery ratio assessment using both windows
        
        Returns:
            Assessment with degradation and recovery recommendations
        """
        fast_window = self.windows.get("delivery_ratio_fast")
        stable_window = self.windows.get("delivery_ratio_stable")
        
        if not fast_window or not stable_window:
            return {"available": False, "reason": "windows_not_ready"}
        
        # Fast window for degradation detection (responsive)
        fast_avg = fast_window.get_weighted_average()
        fast_trend, fast_magnitude = fast_window.get_trend()
        
        # Stable window for recovery assessment (conservative)
        stable_avg = stable_window.get_weighted_average()
        stable_trend, stable_magnitude = stable_window.get_trend()
        
        # Decision logic
        should_degrade = False
        should_recover = False
        confidence = 0.0
        reason = "stable"
        
        # Degradation triggers (use fast window)
        if fast_avg < 0.10:  # Emergency
            should_degrade = True
            confidence = 0.95
            reason = "emergency_delivery_ratio"
        elif fast_avg < 0.50:  # Poor performance
            should_degrade = True
            confidence = 0.85
            reason = "poor_delivery_ratio"
        elif fast_trend == "degrading" and fast_magnitude > 0.2:  # Rapid degradation
            should_degrade = True
            confidence = 0.75
            reason = "rapid_degradation"
        
        # Recovery triggers (use stable window for conservative recovery)
        elif stable_avg > 0.85:  # Excellent performance
            if stable_trend in ["stable", "improving"]:
                should_recover = True
                confidence = 0.80
                reason = "excellent_stable_performance"
        elif stable_avg > 0.75 and stable_trend == "improving":  # Good improving
            should_recover = True
            confidence = 0.70
            reason = "good_improving_performance"
        
        return {
            "available": True,
            "should_degrade": should_degrade,
            "should_recover": should_recover,
            "confidence": confidence,
            "reason": reason,
            "fast_window": {
                "average": fast_avg,
                "trend": fast_trend,
                "magnitude": fast_magnitude,
                "sample_count": len(fast_window)
            },
            "stable_window": {
                "average": stable_avg,
                "trend": stable_trend,
                "magnitude": stable_magnitude,
                "sample_count": len(stable_window)
            }
        }
    
    def get_delivery_time_assessment(self) -> Dict[str, Any]:
        """Get delivery time performance assessment"""
        window = self.windows.get("delivery_time")
        if not window or window.is_empty():
            return {"available": False, "reason": "no_delivery_time_data"}
        
        avg_time = window.get_weighted_average()
        trend, magnitude = window.get_trend()
        stats = window.get_statistics()
        
        # Assessment thresholds
        if avg_time > 3.0:
            condition = "critical"
            should_degrade = True
            confidence = 0.90
        elif avg_time > 1.5:
            condition = "poor"
            should_degrade = True
            confidence = 0.75
        elif avg_time > 0.8:
            condition = "fair"
            should_degrade = False
            confidence = 0.60
        elif avg_time < 0.3:
            condition = "excellent"
            should_degrade = False
            confidence = 0.85
        else:
            condition = "good"
            should_degrade = False
            confidence = 0.70
        
        return {
            "available": True,
            "condition": condition,
            "should_degrade": should_degrade,
            "confidence": confidence,
            "average_time": avg_time,
            "trend": trend,
            "magnitude": magnitude,
            "statistics": stats
        }
    
    def get_unified_assessment(self) -> Dict[str, Any]:
        """
        Get unified performance assessment combining all metrics
        
        Returns:
            Comprehensive assessment with weighted decision
        """
        delivery_assessment = self.get_delivery_ratio_assessment()
        time_assessment = self.get_delivery_time_assessment()
        
        if not delivery_assessment.get("available", False):
            return {"available": False, "reason": "insufficient_data"}
        
        # Primary decision based on delivery ratio (most reliable metric)
        primary_decision = delivery_assessment
        
        # Secondary confirmation from delivery time if available
        secondary_support = 0.0
        if time_assessment.get("available", False):
            if primary_decision["should_degrade"] and time_assessment["should_degrade"]:
                secondary_support = 0.2  # Boost confidence
            elif primary_decision["should_recover"] and not time_assessment["should_degrade"]:
                secondary_support = 0.1  # Mild boost
            elif primary_decision["should_degrade"] and not time_assessment["should_degrade"]:
                secondary_support = -0.1  # Reduce confidence
        
        # Final decision with combined confidence
        final_confidence = min(primary_decision["confidence"] + secondary_support, 1.0)
        
        return {
            "available": True,
            "should_degrade": primary_decision["should_degrade"],
            "should_recover": primary_decision["should_recover"],
            "confidence": final_confidence,
            "reason": primary_decision["reason"],
            "delivery_ratio_support": delivery_assessment,
            "delivery_time_support": time_assessment,
            "decision_basis": "delivery_ratio_primary"
        }
    
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all windows"""
        status = {
            "windows": {},
            "unified_assessment": self.get_unified_assessment()
        }
        
        with self._lock:
            for name, window in self.windows.items():
                status["windows"][name] = window.get_statistics()
        
        return status
    
    def clear_all_windows(self):
        """Clear all samples from all windows"""
        with self._lock:
            for window in self.windows.values():
                window.clear()
    
    def reset_window(self, name: str):
        """Reset specific window"""
        with self._lock:
            if name in self.windows:
                self.windows[name].clear()
