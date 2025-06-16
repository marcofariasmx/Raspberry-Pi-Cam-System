"""
Quality Adaptation for Streaming

Handles adaptive frame rate and JPEG quality adjustments based on network
performance to maintain real-time streaming under varying conditions.
"""

import time
import threading
from typing import Optional, TYPE_CHECKING
from src.config import AppConfig
from ..camera_exceptions import StreamingError

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


class QualityAdapter:
    """
    Manages adaptive streaming quality and frame rate adjustments
    
    Automatically adjusts JPEG quality and frame rate based on network
    performance metrics to maintain optimal streaming experience.
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        
        # Current adaptive settings
        self.current_frame_rate = config.max_frame_rate
        self.current_quality = config.stream_quality
        self.max_quality = config.stream_quality  # Remember user's preferred quality
        
        # Adaptation timing
        self.last_adaptation_time = time.time()
        self.adaptation_lock = threading.Lock()
        
        # Recovery tracking for gradual adaptation (more conservative)
        self.consecutive_good_periods = 0
        self.min_consecutive_good_for_recovery = 3  # Require 3 good periods before recovery
        
        # Delivery ratio history for anti-oscillation
        self.delivery_ratio_history = []
        self.max_history_length = 5
        
        # Delivery ratio thresholds
        self.emergency_threshold = 0.10  # 10% - emergency mode
        self.poor_threshold = 0.50       # 50% - degrade
        self.good_threshold = 0.85       # 85% - recover (higher to prevent oscillation)
        
        # Spike detection threshold (kept as secondary check)
        self.spike_threshold = 3.0  # Raised back up since delivery ratio is primary
        
        # Intended vs actual delivery tracking for efficiency metrics
        self.intended_deliveries = 0
        self.actual_deliveries = 0
        self.delivery_tracking_start_time = time.time()
        
        # Encoder management
        self.current_encoder: Optional[JpegEncoder] = None
        self.camera_device = None
        self.stream_output = None
    
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
        
        print(f"🎨 JPEG encoder initialized with quality: {quality}%")
        return self.current_encoder
    
    def _update_delivery_ratio_history(self, delivery_ratio: float):
        """Update delivery ratio history for anti-oscillation"""
        self.delivery_ratio_history.append(delivery_ratio)
        if len(self.delivery_ratio_history) > self.max_history_length:
            self.delivery_ratio_history.pop(0)
    
    def _should_degrade_quality(self, metrics: dict) -> tuple[bool, str]:
        """Determine if quality should be degraded using delivery ratio as primary metric"""
        # Calculate delivery ratio (primary metric)
        frames_written = metrics.get("frames_written", 1)
        frames_delivered = metrics.get("frames_delivered", 0)
        delivery_ratio = frames_delivered / frames_written if frames_written > 0 else 0.0
        
        # Update history for trend analysis
        self._update_delivery_ratio_history(delivery_ratio)
        
        # Emergency mode: Extremely poor delivery ratio
        if delivery_ratio < self.emergency_threshold:  # Less than 10% delivered
            return True, "emergency_poor_delivery"
        
        # Poor delivery ratio - primary degradation trigger
        if delivery_ratio < self.poor_threshold:  # Less than 50% delivered
            return True, "poor_delivery_ratio"
        
        # Secondary check: Delivery time spikes (keep as backup)
        avg_delivery = metrics.get("average_delivery_time", 0.0)
        if avg_delivery > self.spike_threshold:
            return True, "delivery_time_spike"
        
        return False, "good_performance"
    
    def _should_recover_quality(self, metrics: dict) -> bool:
        """Determine if quality should be recovered using strict criteria"""
        # Calculate delivery ratio
        frames_written = metrics.get("frames_written", 1)
        frames_delivered = metrics.get("frames_delivered", 0)
        delivery_ratio = frames_delivered / frames_written if frames_written > 0 else 0.0
        
        # Require excellent delivery ratio for recovery
        if delivery_ratio < self.good_threshold:  # Must be 85%+ delivered
            return False
        
        # Require sustained good performance (anti-oscillation)
        if len(self.delivery_ratio_history) >= 3:
            recent_ratios = self.delivery_ratio_history[-3:]
            if not all(ratio >= self.good_threshold for ratio in recent_ratios):
                return False
        
        # Also check delivery time as secondary confirmation
        avg_delivery = metrics.get("average_delivery_time", 0.0)
        if avg_delivery > 0.5:  # Delivery time should be reasonable
            return False
        
        return True
    
    def update_delivery_tracking(self, intended_rate: Optional[float] = None):
        """
        Update intended vs actual delivery tracking
        
        Args:
            intended_rate: Current intended frame rate (uses current_frame_rate if None)
        """
        current_time = time.time()
        elapsed = current_time - self.delivery_tracking_start_time
        
        if elapsed >= 1.0:  # Update every second
            intended_fps = intended_rate or self.current_frame_rate
            self.intended_deliveries += intended_fps * elapsed
            
            # Get actual deliveries from stream output if available
            if self.stream_output:
                try:
                    metrics = self.stream_output.get_performance_metrics()
                    frames_delivered = metrics.get("frames_delivered", 0)
                    if hasattr(self, '_last_frames_delivered'):
                        self.actual_deliveries += frames_delivered - self._last_frames_delivered
                    self._last_frames_delivered = frames_delivered
                except:
                    pass
            
            self.delivery_tracking_start_time = current_time
    
    def get_intended_delivery_efficiency(self) -> float:
        """
        Calculate intended delivery efficiency (actual vs intended deliveries)
        
        Returns:
            float: Efficiency percentage (0.0 to 1.0)
        """
        if self.intended_deliveries == 0:
            return 1.0
        
        efficiency = min(self.actual_deliveries / self.intended_deliveries, 1.0)
        return max(efficiency, 0.0)
    
    def get_current_delivery_ratio(self, metrics: dict) -> float:
        """Get current delivery ratio from metrics"""
        frames_written = metrics.get("frames_written", 1)
        frames_delivered = metrics.get("frames_delivered", 0)
        return frames_delivered / frames_written if frames_written > 0 else 0.0
    
    def reset_delivery_tracking(self):
        """Reset delivery tracking counters"""
        self.intended_deliveries = 0
        self.actual_deliveries = 0
        self.delivery_tracking_start_time = time.time()
        if hasattr(self, '_last_frames_delivered'):
            delattr(self, '_last_frames_delivered')
    
    def adapt_frame_rate(self, metrics: dict) -> bool:
        """
        Adapt frame rate based on delivery ratio and network performance
        
        Args:
            metrics: Performance metrics from StreamOutput
            
        Returns:
            bool: True if frame rate was changed
        """
        if not self.config.adaptive_streaming:
            return False
        
        old_frame_rate = self.current_frame_rate
        
        # Check if we should degrade performance
        should_degrade, reason = self._should_degrade_quality(metrics)
        
        if should_degrade:
            # Reduce frame rate and reset good period counter
            self.consecutive_good_periods = 0
            if self.current_frame_rate > self.config.min_frame_rate:
                # Aggressive reduction based on severity
                if reason == "emergency_poor_delivery":
                    # Emergency: Drop to minimum immediately
                    self.current_frame_rate = self.config.min_frame_rate
                    print(f"🚨 Emergency: Frame rate dropped to {self.current_frame_rate} fps (delivery ratio < 10%)")
                elif reason == "poor_delivery_ratio":
                    reduction = 6  # Large reduction for poor delivery ratio
                    self.current_frame_rate = max(
                        self.current_frame_rate - reduction,
                        self.config.min_frame_rate
                    )
                    print(f"📉 Frame rate reduced to {self.current_frame_rate} fps ({reason})")
                else:
                    reduction = 4  # Moderate reduction for delivery time spikes
                    self.current_frame_rate = max(
                        self.current_frame_rate - reduction,
                        self.config.min_frame_rate
                    )
                    print(f"📉 Frame rate reduced to {self.current_frame_rate} fps ({reason})")
        
        elif self._should_recover_quality(metrics):
            # Network performance is excellent - track consecutive good periods
            self.consecutive_good_periods += 1
            
            # Conservative recovery - require sustained good performance
            if (self.consecutive_good_periods >= self.min_consecutive_good_for_recovery and 
                self.current_frame_rate < self.config.max_frame_rate):
                self.current_frame_rate = min(
                    self.current_frame_rate + 2,  # Smaller recovery steps
                    self.config.max_frame_rate
                )
                # Reset counter after successful recovery attempt
                self.consecutive_good_periods = 0
                delivery_ratio = self.get_current_delivery_ratio(metrics)
                print(f"📈 Frame rate increased to {self.current_frame_rate} fps (delivery ratio: {delivery_ratio:.1%})")
        
        else:
            # Neutral performance - don't reset counter but don't change settings
            pass
        
        return self.current_frame_rate != old_frame_rate
    
    def adapt_quality(self, metrics: dict) -> bool:
        """
        Adapt JPEG quality based on delivery ratio and network performance
        
        Args:
            metrics: Performance metrics from StreamOutput
            
        Returns:
            bool: True if quality was changed
        """
        if not self.config.adaptive_quality:
            return False
        
        old_quality = self.current_quality
        new_quality = None
        
        # Check if we should degrade performance
        should_degrade, reason = self._should_degrade_quality(metrics)
        
        if should_degrade:
            # Reduce quality
            if self.current_quality > self.config.min_stream_quality:
                # Aggressive reduction based on severity
                if reason == "emergency_poor_delivery":
                    # Emergency: Drop to minimum immediately
                    new_quality = self.config.min_stream_quality
                elif reason == "poor_delivery_ratio":
                    reduction = self.config.quality_step_size + 10  # Large reduction
                    new_quality = max(
                        self.current_quality - reduction,
                        self.config.min_stream_quality
                    )
                else:
                    reduction = self.config.quality_step_size + 5  # Moderate reduction
                    new_quality = max(
                        self.current_quality - reduction,
                        self.config.min_stream_quality
                    )
        
        elif self._should_recover_quality(metrics):
            # Network performance is excellent - track consecutive good periods
            self.consecutive_good_periods += 1
            
            # Conservative recovery
            if (self.consecutive_good_periods >= self.min_consecutive_good_for_recovery and 
                self.current_quality < self.max_quality):
                # Smaller recovery steps for stability
                recovery_step = max(5, self.config.quality_step_size // 2)
                new_quality = min(
                    self.current_quality + recovery_step,
                    self.max_quality
                )
        
        # Apply quality change if needed
        if new_quality is not None and new_quality != self.current_quality:
            if self._update_encoder_quality(new_quality):
                if new_quality > old_quality:
                    delivery_ratio = self.get_current_delivery_ratio(metrics)
                    print(f"📈 Quality increased to {new_quality}% (delivery ratio: {delivery_ratio:.1%})")
                else:
                    print(f"📉 Quality reduced to {new_quality}% ({reason})")
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
    
    def perform_adaptation(self, metrics: dict) -> dict:
        """
        Perform both frame rate and quality adaptation
        
        Args:
            metrics: Performance metrics from StreamOutput
            
        Returns:
            dict: Adaptation results
        """
        with self.adaptation_lock:
            current_time = time.time()
            time_since_last_adaptation = current_time - self.last_adaptation_time
            
            # Update delivery tracking
            self.update_delivery_tracking()
            
            # Only adapt every few seconds to avoid oscillation
            if time_since_last_adaptation < self.config.network_check_interval:
                return {"adapted": False, "reason": "too_soon"}
            
            frame_rate_changed = self.adapt_frame_rate(metrics)
            quality_changed = self.adapt_quality(metrics)
            
            self.last_adaptation_time = current_time
            
            # Calculate current delivery ratio for reporting
            delivery_ratio = self.get_current_delivery_ratio(metrics)
            
            return {
                "adapted": frame_rate_changed or quality_changed,
                "frame_rate_changed": frame_rate_changed,
                "quality_changed": quality_changed,
                "current_frame_rate": self.current_frame_rate,
                "current_quality": self.current_quality,
                "consecutive_good_periods": self.consecutive_good_periods,
                "intended_delivery_efficiency": self.get_intended_delivery_efficiency(),
                "current_delivery_ratio": delivery_ratio
            }
    
    def reset_to_maximum_quality(self):
        """Reset quality and frame rate to maximum values"""
        with self.adaptation_lock:
            self.current_frame_rate = self.config.max_frame_rate
            
            if self.config.adaptive_quality:
                self._update_encoder_quality(self.max_quality)
            
            self.consecutive_good_periods = 0
            self.delivery_ratio_history.clear()
            self.reset_delivery_tracking()
            print(f"🔄 Reset to maximum: {self.current_frame_rate} fps, {self.current_quality}% quality")
    
    def get_adaptation_status(self) -> dict:
        """
        Get current adaptation status
        
        Returns:
            dict: Current adaptation settings and status
        """
        return {
            "adaptive_streaming_enabled": self.config.adaptive_streaming,
            "adaptive_quality_enabled": self.config.adaptive_quality,
            "current_frame_rate": self.current_frame_rate,
            "current_quality": self.current_quality,
            "max_quality": self.max_quality,
            "frame_rate_range": [self.config.min_frame_rate, self.config.max_frame_rate],
            "quality_range": [self.config.min_stream_quality, self.max_quality],
            "consecutive_good_periods": self.consecutive_good_periods,
            "quality_step_size": self.config.quality_step_size,
            "low_resource_mode": self.config.low_resource_mode,
            "delivery_ratio_history_length": len(self.delivery_ratio_history),
            "spike_threshold": self.spike_threshold,
            "intended_delivery_efficiency": self.get_intended_delivery_efficiency(),
            "intended_deliveries": self.intended_deliveries,
            "actual_deliveries": self.actual_deliveries,
            "delivery_ratio_thresholds": {
                "emergency": self.emergency_threshold,
                "poor": self.poor_threshold,
                "good": self.good_threshold
            }
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
            print(f"🎯 Quality manually set to {new_quality}%")
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
        
        print(f"🎯 Frame rate manually set to {new_frame_rate} fps")
        return True
    
    def get_recommended_settings(self, metrics: dict) -> dict:
        """
        Get recommended settings based on current metrics (without applying them)
        
        Args:
            metrics: Performance metrics
            
        Returns:
            dict: Recommended settings
        """
        delivery_ratio = self.get_current_delivery_ratio(metrics)
        should_degrade, reason = self._should_degrade_quality(metrics)
        
        if should_degrade:
            # Recommend conservative settings
            if delivery_ratio < self.emergency_threshold:
                recommended_fps = self.config.min_frame_rate
                recommended_quality = self.config.min_stream_quality
                performance_level = "emergency"
            else:
                recommended_fps = max(self.config.min_frame_rate, self.current_frame_rate - 6)
                recommended_quality = max(self.config.min_stream_quality, 
                                       self.current_quality - (self.config.quality_step_size + 10))
                performance_level = "poor"
        elif delivery_ratio >= self.good_threshold:
            # Recommend optimal settings
            recommended_fps = self.config.max_frame_rate
            recommended_quality = self.max_quality
            performance_level = "excellent"
        elif delivery_ratio >= 0.70:
            # Recommend good settings
            recommended_fps = min(self.config.max_frame_rate, self.current_frame_rate + 2)
            recommended_quality = min(self.max_quality, 
                                   self.current_quality + 5)
            performance_level = "good"
        else:
            # Recommend current settings
            recommended_fps = self.current_frame_rate
            recommended_quality = self.current_quality
            performance_level = "fair"
        
        return {
            "recommended_frame_rate": recommended_fps,
            "recommended_quality": recommended_quality,
            "performance_level": performance_level,
            "network_condition": "degraded" if should_degrade else "normal",
            "current_delivery_ratio": delivery_ratio,
            "degradation_reason": reason if should_degrade else None,
            "intended_delivery_efficiency": self.get_intended_delivery_efficiency()
        }
