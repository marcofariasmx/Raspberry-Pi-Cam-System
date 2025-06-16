"""
Queue Metrics Collector for Performance Analysis

Collects and analyzes queue performance metrics to provide insights
for quality adaptation and system monitoring.
"""

import time
import threading
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass

from .shared_frame_queue import SharedFrameQueue
from .client_stream_manager import ClientStreamManager


class QueuePressureLevel(Enum):
    """Queue pressure levels for adaptation decisions"""
    HEALTHY = "healthy"
    MODERATE = "moderate" 
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AdaptationRecommendation:
    """
    Recommendation for quality adaptation based on queue metrics
    """
    action: str  # "maintain", "degrade", "recover"
    priority: str  # "low", "normal", "high", "critical"
    frame_rate_adjustment: int  # Suggested fps change (+/-)
    quality_adjustment: int  # Suggested quality change (+/-)
    reason: str  # Explanation for recommendation
    confidence: float  # Confidence level (0.0 to 1.0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "action": self.action,
            "priority": self.priority,
            "frame_rate_adjustment": self.frame_rate_adjustment,
            "quality_adjustment": self.quality_adjustment,
            "reason": self.reason,
            "confidence": self.confidence
        }


class QueueMetricsCollector:
    """
    Collects and analyzes queue performance metrics
    
    Provides comprehensive analysis of queue performance for adaptation decisions.
    """
    
    def __init__(self, shared_queue: SharedFrameQueue, client_manager: Optional[ClientStreamManager] = None):
        """
        Initialize queue metrics collector
        
        Args:
            shared_queue: SharedFrameQueue to monitor
            client_manager: Optional ClientStreamManager for client metrics
        """
        self.shared_queue = shared_queue
        self.client_manager = client_manager
        
        # Analysis history for trend detection
        self.metrics_history: List[Dict[str, Any]] = []
        self.max_history_length = 20  # Keep last 20 samples
        
        # Adaptation thresholds
        self.overflow_thresholds = {
            "healthy": 0.3,      # < 30% overflow
            "moderate": 0.7,     # 30-70% overflow  
            "high": 0.9,         # 70-90% overflow
            "critical": 0.9      # > 90% overflow
        }
        
        # Performance tracking
        self.last_analysis_time = time.time()
        self.analysis_count = 0
        
        print("📊 QueueMetricsCollector initialized")
    
    def calculate_overflow_rate(self) -> float:
        """
        Calculate current queue overflow rate (primary adaptation metric)
        
        Returns:
            float: Overflow rate (0.0 to 1.0+)
        """
        queue_metrics = self.shared_queue.get_queue_metrics()
        return queue_metrics.get("overflow_rate", 0.0)
    
    def get_throughput_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive throughput metrics
        
        Returns:
            dict: Throughput analysis
        """
        queue_metrics = self.shared_queue.get_queue_metrics()
        
        # Base queue metrics
        throughput = {
            "add_rate": queue_metrics.get("add_rate", 0.0),
            "consume_rate": queue_metrics.get("consume_rate", 0.0),
            "net_rate": queue_metrics.get("net_rate", 0.0),
            "queue_utilization": queue_metrics.get("utilization", 0.0),
            "overflow_rate": queue_metrics.get("overflow_rate", 0.0)
        }
        
        # Add client metrics if available
        if self.client_manager:
            client_summary = self.client_manager.get_performance_summary()
            throughput.update({
                "active_clients": client_summary.get("active_clients", 0),
                "total_consumption_rate": client_summary.get("total_consumption_rate", 0.0),
                "average_delivery_efficiency": client_summary.get("average_delivery_efficiency", 1.0),
                "client_performance_variance": client_summary.get("performance_variance", 0.0)
            })
        
        return throughput
    
    def analyze_queue_pressure(self) -> QueuePressureLevel:
        """
        Analyze current queue pressure level
        
        Returns:
            QueuePressureLevel: Current pressure level
        """
        overflow_rate = self.calculate_overflow_rate()
        
        if overflow_rate > self.overflow_thresholds["critical"]:
            return QueuePressureLevel.CRITICAL
        elif overflow_rate > self.overflow_thresholds["high"]:
            return QueuePressureLevel.HIGH
        elif overflow_rate > self.overflow_thresholds["moderate"]:
            return QueuePressureLevel.MODERATE
        else:
            return QueuePressureLevel.HEALTHY
    
    def get_client_distribution_stats(self) -> Dict[str, Any]:
        """
        Get statistics about client performance distribution
        
        Returns:
            dict: Client distribution analysis
        """
        if not self.client_manager:
            return {"error": "No client manager available"}
        
        client_summary = self.client_manager.get_performance_summary()
        
        return {
            "active_clients": client_summary.get("active_clients", 0),
            "consumption_rates": {
                "total": client_summary.get("total_consumption_rate", 0.0),
                "average": client_summary.get("average_consumption_rate", 0.0),
                "min": client_summary.get("min_consumption_rate", 0.0),
                "max": client_summary.get("max_consumption_rate", 0.0),
                "variance": client_summary.get("performance_variance", 0.0)
            },
            "delivery_efficiency": {
                "average": client_summary.get("average_delivery_efficiency", 1.0),
                "min": client_summary.get("min_delivery_efficiency", 1.0),
                "max": client_summary.get("max_delivery_efficiency", 1.0)
            },
            "health_indicators": {
                "all_clients_healthy": client_summary.get("all_clients_healthy", True),
                "has_slow_clients": client_summary.get("has_slow_clients", False)
            }
        }
    
    def record_metrics_sample(self):
        """
        Record current metrics sample for trend analysis
        """
        current_time = time.time()
        
        # Collect comprehensive metrics
        sample = {
            "timestamp": current_time,
            "queue_metrics": self.shared_queue.get_queue_metrics(),
            "throughput_metrics": self.get_throughput_metrics(),
            "pressure_level": self.analyze_queue_pressure().value,
            "client_stats": self.get_client_distribution_stats()
        }
        
        # Add to history
        self.metrics_history.append(sample)
        
        # Trim history if too long
        if len(self.metrics_history) > self.max_history_length:
            self.metrics_history.pop(0)
        
        self.analysis_count += 1
        self.last_analysis_time = current_time
    
    def get_trend_analysis(self, lookback_samples: int = 5) -> Dict[str, Any]:
        """
        Analyze trends in recent metrics
        
        Args:
            lookback_samples: Number of recent samples to analyze
            
        Returns:
            dict: Trend analysis
        """
        if len(self.metrics_history) < 2:
            return {"error": "Insufficient data for trend analysis"}
        
        # Get recent samples
        recent_samples = self.metrics_history[-lookback_samples:] if lookback_samples > 0 else self.metrics_history
        
        if len(recent_samples) < 2:
            return {"error": "Insufficient recent data"}
        
        # Extract key metrics for trend analysis
        overflow_rates = [s["queue_metrics"]["overflow_rate"] for s in recent_samples]
        consumption_rates = [s["throughput_metrics"]["consume_rate"] for s in recent_samples]
        queue_utilizations = [s["queue_metrics"]["utilization"] for s in recent_samples]
        
        # Calculate trends
        def calculate_trend(values: List[float]) -> str:
            if len(values) < 2:
                return "stable"
            
            # Simple trend detection
            first_half = values[:len(values)//2]
            second_half = values[len(values)//2:]
            
            first_avg = sum(first_half) / len(first_half)
            second_avg = sum(second_half) / len(second_half)
            
            change_ratio = (second_avg - first_avg) / (first_avg + 0.001)  # Avoid division by zero
            
            if change_ratio > 0.1:
                return "increasing"
            elif change_ratio < -0.1:
                return "decreasing"
            else:
                return "stable"
        
        return {
            "sample_count": len(recent_samples),
            "time_span": recent_samples[-1]["timestamp"] - recent_samples[0]["timestamp"],
            "overflow_rate_trend": calculate_trend(overflow_rates),
            "consumption_rate_trend": calculate_trend(consumption_rates),
            "queue_utilization_trend": calculate_trend(queue_utilizations),
            "current_overflow_rate": overflow_rates[-1],
            "average_overflow_rate": sum(overflow_rates) / len(overflow_rates),
            "overflow_rate_stability": max(overflow_rates) - min(overflow_rates) < 0.2
        }
    
    def generate_adaptation_recommendation(self) -> AdaptationRecommendation:
        """
        Generate adaptation recommendation based on current metrics and trends
        
        Returns:
            AdaptationRecommendation: Recommended adaptation action
        """
        # Record current sample
        self.record_metrics_sample()
        
        # Get current metrics
        overflow_rate = self.calculate_overflow_rate()
        pressure_level = self.analyze_queue_pressure()
        trend_analysis = self.get_trend_analysis()
        
        # Determine recommendation based on pressure level and trends
        if pressure_level == QueuePressureLevel.CRITICAL:
            # Emergency degradation
            return AdaptationRecommendation(
                action="degrade",
                priority="critical",
                frame_rate_adjustment=-10,  # Large reduction
                quality_adjustment=-20,     # Large quality reduction
                reason=f"Critical queue pressure: {overflow_rate:.1%} overflow rate",
                confidence=0.95
            )
        
        elif pressure_level == QueuePressureLevel.HIGH:
            # Significant degradation
            frame_rate_adj = -6
            quality_adj = -15
            
            # Adjust based on trend
            if trend_analysis.get("overflow_rate_trend") == "increasing":
                frame_rate_adj -= 2  # More aggressive if trend is worsening
                quality_adj -= 5
            
            return AdaptationRecommendation(
                action="degrade",
                priority="high",
                frame_rate_adjustment=frame_rate_adj,
                quality_adjustment=quality_adj,
                reason=f"High queue pressure: {overflow_rate:.1%} overflow rate",
                confidence=0.9
            )
        
        elif pressure_level == QueuePressureLevel.MODERATE:
            # Moderate degradation
            return AdaptationRecommendation(
                action="degrade",
                priority="normal",
                frame_rate_adjustment=-3,
                quality_adjustment=-10,
                reason=f"Moderate queue pressure: {overflow_rate:.1%} overflow rate",
                confidence=0.8
            )
        
        else:
            # Healthy - consider recovery
            trend = trend_analysis.get("overflow_rate_trend", "stable")
            stability = trend_analysis.get("overflow_rate_stability", True)
            
            if trend == "decreasing" and stability and overflow_rate < 0.1:
                # Good conditions for recovery
                return AdaptationRecommendation(
                    action="recover",
                    priority="low",
                    frame_rate_adjustment=2,
                    quality_adjustment=5,
                    reason=f"Healthy queue performance: {overflow_rate:.1%} overflow rate, decreasing trend",
                    confidence=0.85
                )
            else:
                # Maintain current settings
                return AdaptationRecommendation(
                    action="maintain",
                    priority="low",
                    frame_rate_adjustment=0,
                    quality_adjustment=0,
                    reason=f"Stable queue performance: {overflow_rate:.1%} overflow rate",
                    confidence=0.9
                )
    
    def get_comprehensive_analysis(self) -> Dict[str, Any]:
        """
        Get comprehensive queue performance analysis
        
        Returns:
            dict: Complete analysis including metrics, trends, and recommendations
        """
        # Generate fresh recommendation (which also records metrics)
        recommendation = self.generate_adaptation_recommendation()
        
        return {
            "timestamp": time.time(),
            "analysis_count": self.analysis_count,
            
            # Current state
            "current_metrics": {
                "overflow_rate": self.calculate_overflow_rate(),
                "pressure_level": self.analyze_queue_pressure().value,
                "queue_metrics": self.shared_queue.get_queue_metrics(),
                "throughput_metrics": self.get_throughput_metrics(),
                "client_distribution": self.get_client_distribution_stats()
            },
            
            # Trend analysis
            "trend_analysis": self.get_trend_analysis(),
            
            # Recommendation
            "recommendation": recommendation.to_dict(),
            
            # History summary
            "history": {
                "samples_collected": len(self.metrics_history),
                "time_span": (
                    self.metrics_history[-1]["timestamp"] - self.metrics_history[0]["timestamp"]
                    if len(self.metrics_history) >= 2 else 0.0
                )
            }
        }
    
    def get_performance_health_score(self) -> float:
        """
        Calculate overall performance health score (0.0 to 1.0)
        
        Returns:
            float: Health score where 1.0 is perfect, 0.0 is critical
        """
        overflow_rate = self.calculate_overflow_rate()
        throughput_metrics = self.get_throughput_metrics()
        
        # Score components (each 0.0 to 1.0)
        overflow_score = max(0.0, 1.0 - (overflow_rate / 0.5))  # 0% overflow = 1.0, 50%+ overflow = 0.0
        utilization_score = 1.0 - abs(0.5 - throughput_metrics.get("queue_utilization", 0.5))  # 50% utilization is optimal
        efficiency_score = throughput_metrics.get("average_delivery_efficiency", 1.0)
        
        # Weighted average
        health_score = (
            overflow_score * 0.5 +      # Overflow rate is most important
            efficiency_score * 0.3 +    # Delivery efficiency is important
            utilization_score * 0.2     # Queue utilization optimization
        )
        
        return max(0.0, min(1.0, health_score))
    
    def reset_metrics_history(self):
        """Reset metrics history and counters"""
        self.metrics_history.clear()
        self.analysis_count = 0
        self.last_analysis_time = time.time()
        print("📊 Queue metrics history reset")
    
    def get_status_summary(self) -> str:
        """
        Get human-readable status summary
        
        Returns:
            str: Status summary
        """
        overflow_rate = self.calculate_overflow_rate()
        pressure_level = self.analyze_queue_pressure()
        health_score = self.get_performance_health_score()
        
        return f"Overflow: {overflow_rate:.1%} | Pressure: {pressure_level.value} | Health: {health_score:.1%}"
