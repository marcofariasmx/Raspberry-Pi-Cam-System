"""
Enhanced Quality Adaptation with Time-Windowed Metrics

Fixes slow recovery and conflicting metrics issues by using time-windowed
performance measurement and progressive adaptation logic. Supports both
global system adaptation and per-client quality routing.
"""

import time
import threading
from typing import Optional, TYPE_CHECKING, Dict, Any
from src.config import AppConfig
from ..camera_exceptions import StreamingError
from .time_window_metrics import TimeWindowMetrics

if TYPE_CHECKING:
    # Import picamera2 types for type hints only
    try:
        from picamera2 import Picamera2 # type: ignore
        from picamera2.encoders import JpegEncoder # type: ignore
        from picamera2.outputs import FileOutput # type: ignore
    except ImportError:
        pass

# Runtime imports with fallback
try:
    from picamera2.encoders import JpegEncoder # type: ignore
    from picamera2.outputs import FileOutput # type: ignore
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False
    # Mock classes for development
    class JpegEncoder:
        def __init__(self, q=85): self.quality = q
    class FileOutput:
        def __init__(self, output): pass


class EnhancedQualityAdapter:
    """
    Enhanced quality adapter with time-windowed metrics and fast recovery
    
    Replaces cumulative metrics with time-based windows for more responsive
    adaptation. Fixes slow recovery issues and provides unified decision engine
    to prevent conflicting network status assessments.
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        
        # Current global adaptive settings
        self.current_frame_rate = config.max_frame_rate
        self.current_quality = config.stream_quality
        self.max_quality = config.stream_quality  # Remember user's preferred quality
        
        # Time-windowed metrics for global system performance
        self.global_metrics = TimeWindowMetrics()
        
        # Adaptation timing
        self.last_adaptation_time = time.time()
        self.adaptation_lock = threading.Lock()
        
        # Enhanced recovery tracking (faster and more responsive)
        self.consecutive_good_windows = 0
        self.consecutive_poor_windows = 0
        self.min_good_windows_for_recovery = 1  # Reduced from 3 to 1
        
        # Multi-client support tracking
        self.client_count_history = []
        self.system_load_factor = 1.0
        
        # Encoder management
        self.current_encoder: Optional[JpegEncoder] = None
        self.camera_device = None
        self.stream_output = None
        
        print("🔄 EnhancedQualityAdapter initialized with time-windowed metrics")
    
    def set_camera_references(self, camera_device, stream_output):
        """
        Set references to camera device and stream output
        
        Args:
            camera_device: Active Picamera2 instance
            stream_output: StreamOutput instance for monitoring
        """
        self.camera_device = camera_device
        self.stream_output = stream_output
    
    def initialize_encoder(self, initial_quality: Optional[int] = None) -> JpegEncoder:
        """
        Initialize JPEG encoder with specified quality
        
        Args:
            initial_quality: Initial JPEG quality (uses config default if None)
            
        Returns:
            JpegEncoder: Configured JPEG encoder
        """
        if not PICAMERA2_AVAILABLE:
            return JpegEncoder(q=85)  # Mock encoder
        
        # Use provided quality or adapt for low resource mode
        if initial_quality is not None:
            quality = initial_quality
        elif self.config.low_resource_mode:
            # Lower quality for better performance on Pi Zero 2W
            quality = min(self.config.stream_quality, 70)
        else:
            quality = self.config.stream_quality
        
        self.current_quality = quality
        self.max_quality = self.config.stream_quality
        self.current_encoder = JpegEncoder(q=quality)
        
        print(f"🎨 Enhanced JPEG encoder initialized with quality: {quality}%")
        return self.current_encoder
    
    def update_global_metrics(self, metrics: Dict[str, Any]):
        """
        Update global time-windowed metrics from system performance
        
        Args:
            metrics: Performance metrics from StreamOutput
        """
        # Calculate time-based delivery ratio (not cumulative)
        frames_written = metrics.get("frames_written", 1)
        frames_delivered = metrics.get("frames_delivered", 0)
        
        # Use recent delivery ratio rather than session total
        if frames_written > 0:
            delivery_ratio = frames_delivered / frames_written
        else:
            delivery_ratio = 0.0
        
        # Add to time windows for trend analysis
        self.global_metrics.add_sample("delivery_ratio_fast", delivery_ratio)
        self.global_metrics.add_sample("delivery_ratio_stable", delivery_ratio)
        
        # Add delivery time metrics
        avg_delivery_time = metrics.get("average_delivery_time", 0.0)
        if avg_delivery_time > 0:
            self.global_metrics.add_sample("delivery_time", avg_delivery_time)
        
        # Track system load based on client count
        active_clients = metrics.get("active_clients", 1)
        self.client_count_history.append(active_clients)
        if len(self.client_count_history) > 10:
            self.client_count_history.pop(0)
        
        # Calculate system load factor
        avg_clients = sum(self.client_count_history) / len(self.client_count_history)
        self.system_load_factor = min(avg_clients / 3.0, 2.0)  # Scale factor for 1-3 clients
    
    def get_global_performance_assessment(self) -> Dict[str, Any]:
        """
        Get unified global performance assessment using time windows
        
        Returns:
            dict: Comprehensive assessment with confidence levels
        """
        assessment = self.global_metrics.get_unified_assessment()
        
        if not assessment.get("available", False):
            return {
                "available": False,
                "reason": "insufficient_global_data",
                "should_degrade": False,
                "should_recover": False,
                "confidence": 0.0
            }
        
        # Adjust assessment based on system load
        if self.system_load_factor > 1.5:  # High load with multiple clients
            # Be more conservative about recovery
            if assessment["should_recover"]:
                assessment["confidence"] *= 0.8  # Reduce confidence
            
            # Be more aggressive about degradation
            if assessment["should_degrade"]:
                assessment["confidence"] = min(assessment["confidence"] * 1.2, 1.0)
        
        return assessment
    
    def adapt_frame_rate_enhanced(self, metrics: Dict[str, Any]) -> bool:
        """
        Enhanced frame rate adaptation using time-windowed assessment
        
        Args:
            metrics: Performance metrics from StreamOutput
            
        Returns:
            bool: True if frame rate was changed
        """
        if not self.config.adaptive_streaming:
            return False
        
        # Update global metrics first
        self.update_global_metrics(metrics)
        
        # Get performance assessment
        assessment = self.get_global_performance_assessment()
        
        if not assessment.get("available", False):
            return False  # Not enough data yet
        
        old_frame_rate = self.current_frame_rate
        
        # Progressive degradation
        if assessment["should_degrade"]:
            self.consecutive_good_windows = 0
            self.consecutive_poor_windows += 1
            
            if self.current_frame_rate > self.config.min_frame_rate:
                # Progressive reduction based on confidence and reason
                if assessment["reason"] == "emergency_delivery_ratio":
                    reduction = 12  # Emergency reduction
                elif assessment["confidence"] > 0.8:
                    reduction = 6   # High confidence reduction
                else:
                    reduction = 3   # Conservative reduction
                
                self.current_frame_rate = max(
                    self.current_frame_rate - reduction,
                    self.config.min_frame_rate
                )
                
                print(f"📉 Global FPS reduced to {self.current_frame_rate} fps ({assessment['reason']}, confidence: {assessment['confidence']:.1%})")
                return True
        
        # Enhanced recovery (faster and more responsive)
        elif assessment["should_recover"]:
            self.consecutive_poor_windows = 0
            self.consecutive_good_windows += 1
            
            # Faster recovery - only require 1-2 good windows instead of 3
            required_windows = 1 if assessment["confidence"] > 0.8 else 2
            
            if (self.consecutive_good_windows >= required_windows and 
                self.current_frame_rate < self.config.max_frame_rate):
                
                # Progressive recovery steps (larger when confident)
                if assessment["confidence"] > 0.8:
                    increase = 4  # Confident recovery
                elif assessment["confidence"] > 0.7:
                    increase = 3  # Good recovery
                else:
                    increase = 2  # Conservative recovery
                
                self.current_frame_rate = min(
                    self.current_frame_rate + increase,
                    self.config.max_frame_rate
                )
                
                # Don't reset counter completely - allow continued recovery
                self.consecutive_good_windows = max(0, self.consecutive_good_windows - 1)
                
                print(f"📈 Global FPS increased to {self.current_frame_rate} fps (confidence: {assessment['confidence']:.1%})")
                return True
        
        return False
    
    def adapt_quality_enhanced(self, metrics: Dict[str, Any]) -> bool:
        """
        Enhanced quality adaptation using time-windowed assessment
        
        Args:
            metrics: Performance metrics from StreamOutput
            
        Returns:
            bool: True if quality was changed
        """
        if not self.config.adaptive_quality:
            return False
        
        # Get performance assessment (metrics already updated in frame rate adaptation)
        assessment = self.get_global_performance_assessment()
        
        if not assessment.get("available", False):
            return False
        
        old_quality = self.current_quality
        
        # Progressive quality degradation
        if assessment["should_degrade"]:
            if self.current_quality > self.config.min_stream_quality:
                # Progressive reduction based on severity
                if assessment["reason"] == "emergency_delivery_ratio":
                    reduction = 30  # Emergency quality drop
                elif assessment["confidence"] > 0.8:
                    reduction = 15  # High confidence reduction
                else:
                    reduction = 10  # Conservative reduction
                
                new_quality = max(
                    self.current_quality - reduction,
                    self.config.min_stream_quality
                )
                
                if self._update_encoder_quality(new_quality):
                    print(f"📉 Global quality reduced to {new_quality}% ({assessment['reason']}, confidence: {assessment['confidence']:.1%})")
                    return True
        
        # Enhanced quality recovery
        elif assessment["should_recover"]:
            required_windows = 1 if assessment["confidence"] > 0.8 else 2
            
            if (self.consecutive_good_windows >= required_windows and 
                self.current_quality < self.max_quality):
                
                # Progressive quality increase
                if assessment["confidence"] > 0.8:
                    increase = 15  # Confident recovery
                elif assessment["confidence"] > 0.7:
                    increase = 10  # Good recovery
                else:
                    increase = 5   # Conservative recovery
                
                new_quality = min(
                    self.current_quality + increase,
                    self.max_quality
                )
                
                if self._update_encoder_quality(new_quality):
                    print(f"📈 Global quality increased to {new_quality}% (confidence: {assessment['confidence']:.1%})")
                    return True
        
        return False
    
    def _update_encoder_quality(self, new_quality: int) -> bool:
        """
        Update JPEG encoder quality during streaming
        
        Args:
            new_quality: New JPEG quality percentage
            
        Returns:
            bool: True if update was successful
        """
        if not self.camera_device or not PICAMERA2_AVAILABLE:
            # For development mode, just update the value
            self.current_quality = new_quality
            return True
        
        try:
            # Stop current recording
            self.camera_device.stop_recording()
            
            # Create new encoder with updated quality
            self.current_encoder = JpegEncoder(q=new_quality)
            
            # Start recording again with new encoder
            self.camera_device.start_recording(
                self.current_encoder,
                FileOutput(self.stream_output)
            )
            
            self.current_quality = new_quality
            return True
            
        except Exception as e:
            print(f"❌ Failed to update encoder quality: {e}")
            return False
    
    def perform_enhanced_adaptation(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform enhanced adaptation using time-windowed metrics
        
        Args:
            metrics: Performance metrics from StreamOutput
            
        Returns:
            dict: Comprehensive adaptation results
        """
        with self.adaptation_lock:
            current_time = time.time()
            time_since_last_adaptation = current_time - self.last_adaptation_time
            
            # Faster adaptation checks (reduce from network_check_interval)
            min_adaptation_interval = max(self.config.network_check_interval * 0.5, 1.0)
            
            if time_since_last_adaptation < min_adaptation_interval:
                return {"adapted": False, "reason": "too_soon"}
            
            # Perform enhanced adaptations
            frame_rate_changed = self.adapt_frame_rate_enhanced(metrics)
            quality_changed = self.adapt_quality_enhanced(metrics)
            
            self.last_adaptation_time = current_time
            
            # Get comprehensive assessment for reporting
            assessment = self.get_global_performance_assessment()
            
            return {
                "adapted": frame_rate_changed or quality_changed,
                "frame_rate_changed": frame_rate_changed,
                "quality_changed": quality_changed,
                "current_frame_rate": self.current_frame_rate,
                "current_quality": self.current_quality,
                "consecutive_good_windows": self.consecutive_good_windows,
                "consecutive_poor_windows": self.consecutive_poor_windows,
                "system_load_factor": self.system_load_factor,
                "performance_assessment": assessment,
                "global_metrics_status": self.global_metrics.get_comprehensive_status(),
                "adaptation_type": "enhanced_time_windowed"
            }
    
    def get_network_status_unified(self) -> Dict[str, Any]:
        """
        Get unified network status to prevent conflicting assessments
        
        Returns:
            dict: Unified network status
        """
        assessment = self.get_global_performance_assessment()
        
        if not assessment.get("available", False):
            return {
                "status": "unknown",
                "reason": "insufficient_data",
                "confidence": 0.0
            }
        
        # Determine unified status
        if assessment["should_degrade"]:
            if assessment["reason"] == "emergency_delivery_ratio":
                status = "critical"
            elif assessment["confidence"] > 0.8:
                status = "poor"
            else:
                status = "fair"
        elif assessment["should_recover"]:
            if assessment["confidence"] > 0.8:
                status = "excellent"
            else:
                status = "good"
        else:
            status = "stable"
        
        return {
            "status": status,
            "reason": assessment.get("reason", "stable"),
            "confidence": assessment.get("confidence", 0.0),
            "should_degrade": assessment["should_degrade"],
            "should_recover": assessment["should_recover"],
            "delivery_ratio_support": assessment.get("delivery_ratio_support", {}),
            "delivery_time_support": assessment.get("delivery_time_support", {}),
            "system_load_factor": self.system_load_factor
        }
    
    def reset_to_maximum_quality(self):
        """Reset quality and frame rate to maximum values"""
        with self.adaptation_lock:
            self.current_frame_rate = self.config.max_frame_rate
            
            if self.config.adaptive_quality:
                self._update_encoder_quality(self.max_quality)
            
            self.consecutive_good_windows = 0
            self.consecutive_poor_windows = 0
            self.global_metrics.clear_all_windows()
            
            print(f"🔄 Enhanced reset to maximum: {self.current_frame_rate} fps, {self.current_quality}% quality")
    
    def get_enhanced_adaptation_status(self) -> Dict[str, Any]:
        """
        Get comprehensive adaptation status
        
        Returns:
            dict: Enhanced adaptation settings and status
        """
        network_status = self.get_network_status_unified()
        
        return {
            "adaptive_streaming_enabled": self.config.adaptive_streaming,
            "adaptive_quality_enabled": self.config.adaptive_quality,
            "current_frame_rate": self.current_frame_rate,
            "current_quality": self.current_quality,
            "max_quality": self.max_quality,
            "frame_rate_range": [self.config.min_frame_rate, self.config.max_frame_rate],
            "quality_range": [self.config.min_stream_quality, self.max_quality],
            
            # Enhanced tracking
            "consecutive_good_windows": self.consecutive_good_windows,
            "consecutive_poor_windows": self.consecutive_poor_windows,
            "min_good_windows_for_recovery": self.min_good_windows_for_recovery,
            "system_load_factor": self.system_load_factor,
            
            # Time-windowed metrics
            "global_metrics_status": self.global_metrics.get_comprehensive_status(),
            "network_status": network_status,
            
            # Configuration
            "quality_step_size": self.config.quality_step_size,
            "low_resource_mode": self.config.low_resource_mode,
            "adaptation_type": "enhanced_time_windowed"
        }
    
    def force_quality_change(self, new_quality: int) -> bool:
        """
        Force a quality change (for manual control)
        
        Args:
            new_quality: New quality percentage (10-100)
            
        Returns:
            bool: True if change was successful
        """
        # Validate quality range
        new_quality = max(10, min(new_quality, 100))
        
        if self._update_encoder_quality(new_quality):
            print(f"🎯 Enhanced quality manually set to {new_quality}%")
            return True
        
        return False
    
    def force_frame_rate_change(self, new_frame_rate: int) -> bool:
        """
        Force a frame rate change (for manual control)
        
        Args:
            new_frame_rate: New frame rate in fps (1-60)
            
        Returns:
            bool: True if change was successful
        """
        # Validate frame rate range
        new_frame_rate = max(1, min(new_frame_rate, 60))
        
        old_frame_rate = self.current_frame_rate
        self.current_frame_rate = new_frame_rate
        
        print(f"🎯 Enhanced frame rate manually set to {new_frame_rate} fps")
        return True
    
    def get_performance_comparison(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare current enhanced performance with legacy approach
        
        Args:
            metrics: Current performance metrics
            
        Returns:
            dict: Performance comparison analysis
        """
        # Calculate what legacy approach would recommend
        frames_written = metrics.get("frames_written", 1)
        frames_delivered = metrics.get("frames_delivered", 0)
        legacy_delivery_ratio = frames_delivered / frames_written if frames_written > 0 else 0.0
        
        # Get enhanced assessment
        enhanced_assessment = self.get_global_performance_assessment()
        
        # Legacy thresholds
        legacy_poor_threshold = 0.50
        legacy_good_threshold = 0.85
        
        legacy_should_degrade = legacy_delivery_ratio < legacy_poor_threshold
        legacy_should_recover = legacy_delivery_ratio >= legacy_good_threshold
        
        return {
            "enhanced_assessment": enhanced_assessment,
            "legacy_assessment": {
                "delivery_ratio": legacy_delivery_ratio,
                "should_degrade": legacy_should_degrade,
                "should_recover": legacy_should_recover,
                "method": "cumulative_session_total"
            },
            "comparison": {
                "decisions_match": (
                    enhanced_assessment.get("should_degrade", False) == legacy_should_degrade and
                    enhanced_assessment.get("should_recover", False) == legacy_should_recover
                ),
                "enhanced_more_responsive": enhanced_assessment.get("available", False),
                "legacy_delivery_ratio": legacy_delivery_ratio,
                "enhanced_confidence": enhanced_assessment.get("confidence", 0.0)
            }
        }


# Compatibility wrapper for existing code
class QualityAdapter(EnhancedQualityAdapter):
    """
    Compatibility wrapper that provides the same interface as the original
    QualityAdapter but uses the enhanced implementation underneath.
    """
    
    def __init__(self, config: AppConfig):
        super().__init__(config)
        print("🔄 Using EnhancedQualityAdapter with legacy compatibility")
    
    def perform_adaptation(self, metrics: dict) -> dict:
        """Legacy compatibility method"""
        return self.perform_enhanced_adaptation(metrics)
    
    def get_adaptation_status(self) -> dict:
        """Legacy compatibility method"""
        return self.get_enhanced_adaptation_status()
    
    def get_current_delivery_ratio(self, metrics: dict) -> float:
        """Legacy compatibility method"""
        frames_written = metrics.get("frames_written", 1)
        frames_delivered = metrics.get("frames_delivered", 0)
        return frames_delivered / frames_written if frames_written > 0 else 0.0
