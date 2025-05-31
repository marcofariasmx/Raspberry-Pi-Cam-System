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
        
        # Recovery tracking for gradual adaptation
        self.consecutive_good_periods = 0
        self.min_consecutive_good_for_recovery = 1  # Faster recovery
        
        # Delivery time history for responsive logic
        self.delivery_time_history = []
        self.max_history_length = 5
        
        # Spike detection threshold (lowered for faster response)
        self.spike_threshold = 2.0  # Single delivery >2s triggers immediate response
        
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
    
    def _update_delivery_history(self, avg_delivery: float):
        """Update delivery time history for responsive logic"""
        self.delivery_time_history.append(avg_delivery)
        if len(self.delivery_time_history) > self.max_history_length:
            self.delivery_time_history.pop(0)
    
    def _should_degrade_quality(self, avg_delivery: float) -> tuple[bool, str]:
        """Determine if quality should be degraded with responsive thresholds"""
        # Spike detection - immediate response to single very high delivery time
        if avg_delivery > self.spike_threshold:
            return True, "spike_detected"
        
        # Immediate response to choppy streams - lowered threshold
        if avg_delivery > self.config.network_timeout_threshold:
            return True, "delivery_threshold_exceeded"
        
        # Progressive degradation for sustained moderate issues
        if len(self.delivery_time_history) >= 2:
            recent_avg = sum(self.delivery_time_history[-2:]) / 2
            if recent_avg > 0.8:  # Two consecutive readings > 0.8s average
                return True, "sustained_slow_delivery"
        
        return False, "good_performance"
    
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
    
    def reset_delivery_tracking(self):
        """Reset delivery tracking counters"""
        self.intended_deliveries = 0
        self.actual_deliveries = 0
        self.delivery_tracking_start_time = time.time()
        if hasattr(self, '_last_frames_delivered'):
            delattr(self, '_last_frames_delivered')
    
    def adapt_frame_rate(self, metrics: dict) -> bool:
        """
        Adapt frame rate based on network performance using improved logic
        
        Args:
            metrics: Performance metrics from StreamOutput
            
        Returns:
            bool: True if frame rate was changed
        """
        if not self.config.adaptive_streaming:
            return False
        
        avg_delivery = metrics.get("average_delivery_time", 0.0)
        self._update_delivery_history(avg_delivery)
        
        old_frame_rate = self.current_frame_rate
        
        # Check if we should degrade performance
        should_degrade, reason = self._should_degrade_quality(avg_delivery)
        
        if should_degrade:
            # Reduce frame rate and reset good period counter
            self.consecutive_good_periods = 0
            if self.current_frame_rate > self.config.min_frame_rate:
                # More aggressive reduction based on severity
                if reason == "spike_detected":
                    reduction = 6  # Larger reduction for spikes
                elif reason == "delivery_threshold_exceeded":
                    reduction = 4  # Moderate reduction for threshold exceeded
                else:
                    reduction = 3  # Standard reduction for sustained issues
                
                self.current_frame_rate = max(
                    self.current_frame_rate - reduction,
                    self.config.min_frame_rate
                )
                print(f"📉 Frame rate reduced to {self.current_frame_rate} fps ({reason})")
        
        elif avg_delivery < 0.8:  # Fast recovery threshold
            # Network performance is excellent - track consecutive good periods
            self.consecutive_good_periods += 1
            
            # Fast recovery
            if (self.consecutive_good_periods >= self.min_consecutive_good_for_recovery and 
                self.current_frame_rate < self.config.max_frame_rate):
                self.current_frame_rate = min(
                    self.current_frame_rate + 3,  # Faster recovery
                    self.config.max_frame_rate
                )
                # Reset counter after successful recovery attempt
                self.consecutive_good_periods = 0
                print(f"📈 Frame rate increased to {self.current_frame_rate} fps (network excellent)")
        
        else:
            # Neutral performance - don't reset counter but don't change settings
            pass
        
        return self.current_frame_rate != old_frame_rate
    
    def adapt_quality(self, metrics: dict) -> bool:
        """
        Adapt JPEG quality based on network performance using improved logic
        
        Args:
            metrics: Performance metrics from StreamOutput
            
        Returns:
            bool: True if quality was changed
        """
        if not self.config.adaptive_quality:
            return False
        
        avg_delivery = metrics.get("average_delivery_time", 0.0)
        old_quality = self.current_quality
        new_quality = None
        
        # Check if we should degrade performance
        should_degrade, reason = self._should_degrade_quality(avg_delivery)
        
        if should_degrade:
            # Reduce quality
            if self.current_quality > self.config.min_stream_quality:
                # More aggressive reduction based on severity
                if reason == "spike_detected":
                    reduction = self.config.quality_step_size + 10  # Larger reduction for spikes
                elif reason == "delivery_threshold_exceeded":
                    reduction = self.config.quality_step_size + 5  # Moderate reduction
                else:
                    reduction = self.config.quality_step_size  # Standard reduction
                    
                new_quality = max(
                    self.current_quality - reduction,
                    self.config.min_stream_quality
                )
        
        elif avg_delivery < 0.8:  # Fast recovery threshold
            # Network performance is excellent - track consecutive good periods
            self.consecutive_good_periods += 1
            
            # Fast recovery
            if (self.consecutive_good_periods >= self.min_consecutive_good_for_recovery and 
                self.current_quality < self.max_quality):
                # Faster recovery steps
                recovery_step = max(8, self.config.quality_step_size)
                new_quality = min(
                    self.current_quality + recovery_step,
                    self.max_quality
                )
        
        # Apply quality change if needed
        if new_quality is not None and new_quality != self.current_quality:
            if self._update_encoder_quality(new_quality):
                if new_quality > old_quality:
                    print(f"📈 Quality increased to {new_quality}% (network excellent)")
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
            
            return {
                "adapted": frame_rate_changed or quality_changed,
                "frame_rate_changed": frame_rate_changed,
                "quality_changed": quality_changed,
                "current_frame_rate": self.current_frame_rate,
                "current_quality": self.current_quality,
                "consecutive_good_periods": self.consecutive_good_periods,
                "intended_delivery_efficiency": self.get_intended_delivery_efficiency()
            }
    
    def reset_to_maximum_quality(self):
        """Reset quality and frame rate to maximum values"""
        with self.adaptation_lock:
            self.current_frame_rate = self.config.max_frame_rate
            
            if self.config.adaptive_quality:
                self._update_encoder_quality(self.max_quality)
            
            self.consecutive_good_periods = 0
            self.delivery_time_history.clear()
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
            "delivery_history_length": len(self.delivery_time_history),
            "spike_threshold": self.spike_threshold,
            "intended_delivery_efficiency": self.get_intended_delivery_efficiency(),
            "intended_deliveries": self.intended_deliveries,
            "actual_deliveries": self.actual_deliveries
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
        avg_delivery = metrics.get("average_delivery_time", 0.0)
        should_degrade, reason = self._should_degrade_quality(avg_delivery)
        
        if should_degrade:
            # Recommend conservative settings
            recommended_fps = max(self.config.min_frame_rate, self.current_frame_rate - 4)
            recommended_quality = max(self.config.min_stream_quality, 
                                   self.current_quality - (self.config.quality_step_size + 5))
            performance_level = "poor"
        elif avg_delivery < 0.5:
            # Recommend optimal settings
            recommended_fps = self.config.max_frame_rate
            recommended_quality = self.max_quality
            performance_level = "excellent"
        elif avg_delivery < 0.8:
            # Recommend good settings
            recommended_fps = min(self.config.max_frame_rate, self.current_frame_rate + 3)
            recommended_quality = min(self.max_quality, 
                                   self.current_quality + 8)
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
            "average_delivery_time": avg_delivery,
            "degradation_reason": reason if should_degrade else None,
            "intended_delivery_efficiency": self.get_intended_delivery_efficiency()
        }
