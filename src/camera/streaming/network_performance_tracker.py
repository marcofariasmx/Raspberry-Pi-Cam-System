"""
Network Performance Tracker
Simple, efficient network performance monitoring for adaptive streaming
without complex statistical analysis or time windows.
"""

import time
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class NetworkSample:
    """Simple network performance sample"""
    timestamp: float
    delivery_time: float
    frame_size: int
    client_count: int
    
    @property
    def age(self) -> float:
        """Get sample age in seconds"""
        return time.time() - self.timestamp
    
    @property
    def throughput_kbps(self) -> float:
        """Calculate throughput in KB/s"""
        if self.delivery_time <= 0:
            return 0.0
        return (self.frame_size / 1024) / self.delivery_time


class NetworkPerformanceTracker:
    """
    Simple network performance tracker for adaptive streaming
    
    Tracks basic network metrics without complex statistical analysis.
    Focuses on recent performance for fast adaptation decisions.
    """
    
    def __init__(self, max_samples: int = 10):
        """
        Initialize network performance tracker
        
        Args:
            max_samples: Maximum number of samples to keep (default: 10)
        """
        self.max_samples = max_samples
        
        # Simple sample storage (recent samples only)
        self.samples: List[NetworkSample] = []
        self._lock = threading.RLock()
        
        # Performance counters
        self.total_samples = 0
        self.start_time = time.time()
        
        # Current network status
        self.current_status = "unknown"
        self.last_assessment_time = 0.0
        
        print(f"📊 NetworkPerformanceTracker initialized (max samples: {max_samples})")
    
    def record_delivery(self, delivery_time: float, frame_size: int, client_count: int = 1):
        """
        Record a frame delivery performance sample
        
        Args:
            delivery_time: Time taken to deliver frame in seconds
            frame_size: Size of delivered frame in bytes
            client_count: Number of active clients
        """
        current_time = time.time()
        
        sample = NetworkSample(
            timestamp=current_time,
            delivery_time=delivery_time,
            frame_size=frame_size,
            client_count=client_count
        )
        
        with self._lock:
            self.samples.append(sample)
            self.total_samples += 1
            
            # Keep only recent samples
            if len(self.samples) > self.max_samples:
                self.samples.pop(0)
            
            # Update current status
            self._update_current_status()
    
    def _update_current_status(self):
        """Update current network status based on recent samples"""
        if len(self.samples) < 3:
            self.current_status = "insufficient_data"
            return
        
        # Simple assessment based on recent delivery times
        recent_times = [s.delivery_time for s in self.samples[-3:]]
        avg_time = sum(recent_times) / len(recent_times)
        
        if avg_time > 3.0:
            self.current_status = "poor"
        elif avg_time > 1.5:
            self.current_status = "fair"
        elif avg_time > 0.8:
            self.current_status = "good"
        else:
            self.current_status = "excellent"
        
        self.last_assessment_time = time.time()
    
    def get_current_status(self) -> str:
        """
        Get current network status
        
        Returns:
            str: Network status ('excellent', 'good', 'fair', 'poor', 'insufficient_data')
        """
        with self._lock:
            return self.current_status
    
    def get_average_delivery_time(self, sample_count: Optional[int] = None) -> float:
        """
        Get average delivery time from recent samples
        
        Args:
            sample_count: Number of recent samples to consider (default: all)
            
        Returns:
            float: Average delivery time in seconds
        """
        with self._lock:
            if not self.samples:
                return 0.0
            
            if sample_count is None:
                relevant_samples = self.samples
            else:
                relevant_samples = self.samples[-sample_count:]
            
            if not relevant_samples:
                return 0.0
            
            return sum(s.delivery_time for s in relevant_samples) / len(relevant_samples)
    
    def get_average_throughput(self, sample_count: Optional[int] = None) -> float:
        """
        Get average throughput from recent samples
        
        Args:
            sample_count: Number of recent samples to consider (default: all)
            
        Returns:
            float: Average throughput in KB/s
        """
        with self._lock:
            if not self.samples:
                return 0.0
            
            if sample_count is None:
                relevant_samples = self.samples
            else:
                relevant_samples = self.samples[-sample_count:]
            
            if not relevant_samples:
                return 0.0
            
            return sum(s.throughput_kbps for s in relevant_samples) / len(relevant_samples)
    
    def is_network_slow(self, threshold: float = 2.0) -> bool:
        """
        Check if network is currently slow
        
        Args:
            threshold: Delivery time threshold in seconds (default: 2.0)
            
        Returns:
            bool: True if network appears slow
        """
        avg_time = self.get_average_delivery_time(sample_count=3)
        return avg_time > threshold
    
    def is_network_fast(self, threshold: float = 0.5) -> bool:
        """
        Check if network is currently fast
        
        Args:
            threshold: Delivery time threshold in seconds (default: 0.5)
            
        Returns:
            bool: True if network appears fast
        """
        avg_time = self.get_average_delivery_time(sample_count=3)
        return avg_time < threshold and len(self.samples) >= 3
    
    def get_trend(self) -> str:
        """
        Get simple trend assessment
        
        Returns:
            str: Trend direction ('improving', 'degrading', 'stable', 'unknown')
        """
        with self._lock:
            if len(self.samples) < 6:
                return "unknown"
            
            # Compare first half vs second half of recent samples
            half_point = len(self.samples) // 2
            older_avg = sum(s.delivery_time for s in self.samples[:half_point]) / half_point
            newer_avg = sum(s.delivery_time for s in self.samples[half_point:]) / (len(self.samples) - half_point)
            
            # Simple threshold for trend detection
            if abs(newer_avg - older_avg) < 0.3:  # Minimal change
                return "stable"
            elif newer_avg < older_avg:
                return "improving"
            else:
                return "degrading"
    
    def get_quality_recommendation(self, current_quality: int) -> tuple[int, str]:
        """
        Get quality recommendation based on current network performance
        
        Args:
            current_quality: Current quality percentage
            
        Returns:
            tuple: (recommended_quality, reason)
        """
        with self._lock:
            if len(self.samples) < 3:
                return current_quality, "insufficient_data"
            
            status = self.current_status
            avg_time = self.get_average_delivery_time(sample_count=3)
            
            # Simple quality recommendation logic
            if status == "poor" or avg_time > 3.0:
                # Significant degradation needed
                recommended = max(current_quality - 20, 30)
                reason = f"poor_network_performance_{avg_time:.1f}s"
            elif status == "fair" or avg_time > 1.5:
                # Moderate degradation
                recommended = max(current_quality - 10, 30)
                reason = f"fair_network_performance_{avg_time:.1f}s"
            elif status == "excellent" and avg_time < 0.3:
                # Can improve quality
                recommended = min(current_quality + 10, 85)
                reason = f"excellent_network_performance_{avg_time:.1f}s"
            elif status == "good" and avg_time < 0.5:
                # Moderate improvement
                recommended = min(current_quality + 5, 85)
                reason = f"good_network_performance_{avg_time:.1f}s"
            else:
                # Keep current quality
                recommended = current_quality
                reason = f"stable_network_performance_{avg_time:.1f}s"
            
            return recommended, reason
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics
        
        Returns:
            dict: Performance metrics
        """
        current_time = time.time()
        
        with self._lock:
            return {
                "current_status": self.current_status,
                "trend": self.get_trend(),
                "sample_count": len(self.samples),
                "total_samples": self.total_samples,
                "uptime": current_time - self.start_time,
                "last_assessment_age": current_time - self.last_assessment_time,
                
                # Recent performance
                "average_delivery_time": self.get_average_delivery_time(),
                "average_delivery_time_recent": self.get_average_delivery_time(sample_count=3),
                "average_throughput_kbps": self.get_average_throughput(),
                
                # Current conditions
                "is_network_slow": self.is_network_slow(),
                "is_network_fast": self.is_network_fast(),
                
                # Sample details
                "oldest_sample_age": self.samples[0].age if self.samples else 0,
                "newest_sample_age": self.samples[-1].age if self.samples else 0,
                "sample_range_seconds": (
                    self.samples[-1].timestamp - self.samples[0].timestamp 
                    if len(self.samples) > 1 else 0
                )
            }
    
    def get_recent_samples(self, count: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent samples as dictionaries
        
        Args:
            count: Number of recent samples to return
            
        Returns:
            list: Recent samples
        """
        with self._lock:
            recent = self.samples[-count:] if count > 0 else self.samples
            return [
                {
                    "timestamp": s.timestamp,
                    "delivery_time": s.delivery_time,
                    "frame_size": s.frame_size,
                    "client_count": s.client_count,
                    "throughput_kbps": s.throughput_kbps,
                    "age": s.age
                }
                for s in recent
            ]
    
    def clear_samples(self):
        """Clear all performance samples"""
        with self._lock:
            self.samples.clear()
            self.current_status = "unknown"
            self.last_assessment_time = 0.0
            print("🧹 Network performance samples cleared")
    
    def get_client_load_factor(self) -> float:
        """
        Get current client load factor based on recent samples
        
        Returns:
            float: Load factor (1.0 = single client baseline)
        """
        with self._lock:
            if not self.samples:
                return 1.0
            
            # Use average client count from recent samples
            recent_samples = self.samples[-5:]
            avg_clients = sum(s.client_count for s in recent_samples) / len(recent_samples)
            
            # Scale factor: more clients = higher load
            return max(avg_clients / 3.0, 1.0)  # Baseline for 3 clients
    
    def get_bandwidth_estimate(self) -> Dict[str, float]:
        """
        Get rough bandwidth estimates
        
        Returns:
            dict: Bandwidth estimates in KB/s and Mbps
        """
        with self._lock:
            if not self.samples:
                return {"kbps": 0.0, "mbps": 0.0}
            
            # Use recent throughput average
            avg_kbps = self.get_average_throughput(sample_count=5)
            
            return {
                "kbps": avg_kbps,
                "mbps": avg_kbps / 1024.0
            }
    
    def should_degrade_quality(self, current_quality: int) -> bool:
        """
        Simple check if quality should be degraded
        
        Args:
            current_quality: Current quality percentage
            
        Returns:
            bool: True if quality should be reduced
        """
        return (self.is_network_slow() and 
                current_quality > 30 and 
                len(self.samples) >= 3)
    
    def should_improve_quality(self, current_quality: int) -> bool:
        """
        Simple check if quality can be improved
        
        Args:
            current_quality: Current quality percentage
            
        Returns:
            bool: True if quality can be increased
        """
        return (self.is_network_fast() and 
                current_quality < 85 and 
                len(self.samples) >= 5)
    
    def get_status_summary(self) -> str:
        """
        Get human-readable status summary
        
        Returns:
            str: Status summary
        """
        metrics = self.get_performance_metrics()
        
        return (
            f"Status: {metrics['current_status']} | "
            f"Trend: {metrics['trend']} | "
            f"Avg Time: {metrics['average_delivery_time']:.2f}s | "
            f"Samples: {metrics['sample_count']}"
        )