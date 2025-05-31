"""
Camera Manager - Main Orchestrator

Coordinates all camera system components including hardware detection,
photo capture, video streaming, and adaptive quality management.

This refactored version maintains the same public API while delegating
functionality to specialized modules for better maintainability.
"""

import time
import threading
from typing import Optional, Tuple, Dict, Any

from src.config import AppConfig
from .camera_exceptions import (
    CameraInitializationError, 
    StreamingError, 
    PhotoCaptureError,
    handle_camera_error
)
from .hardware_detection import HardwareDetector, create_minimal_camera_config
from .photo_capture import PhotoCapture
from .streaming.video_streaming import StreamOutput, FrameGenerator, create_stream_output
from .streaming.quality_adaptation import QualityAdapter
from .streaming.network_performance import NetworkMonitor
from .streaming.streaming_stats import StreamingStats

# Import picamera2 - graceful handling for development environments
try:
    from picamera2 import Picamera2 # type: ignore
    from picamera2.outputs import FileOutput # type: ignore
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False
    # Mock classes for development
    class Picamera2:
        def __init__(self): pass
        def close(self): pass
        def configure(self, config): pass
        def start(self): pass
        def stop(self): pass
        def start_recording(self, encoder, output): pass
        def stop_recording(self): pass
        def create_video_configuration(self, **kwargs): return {}
    
    class FileOutput:
        def __init__(self, output): pass


class CameraManager:
    """
    Main camera management orchestrator
    
    Coordinates hardware detection, photo capture, video streaming,
    adaptive quality control, and performance monitoring while
    maintaining the same public API as the original implementation.
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        
        # Core camera device
        self.camera_device: Optional[Picamera2] = None
        
        # Component modules
        self.hardware_detector = HardwareDetector(config)
        self.photo_capture = PhotoCapture(config)
        self.quality_adapter = QualityAdapter(config)
        self.network_monitor = NetworkMonitor(config)
        self.streaming_stats = StreamingStats()
        
        # Streaming components
        self.stream_output: Optional[StreamOutput] = None
        self.frame_generator: Optional[FrameGenerator] = None
        self.is_streaming = False
        
        # Performance tracking
        self.total_frames_sent = 0
        self.total_frames_dropped = 0
        
        # Lazy initialization for low resource mode
        if not config.low_resource_mode:
            # For normal systems, detect capabilities early
            self.hardware_detector.detect_camera_capabilities()
    
    @handle_camera_error
    def init_camera(self) -> bool:
        """
        Initialize camera with dual-stream configuration
        
        Returns:
            bool: True if initialization was successful
            
        Raises:
            CameraInitializationError: If initialization fails
        """
        if not PICAMERA2_AVAILABLE:
            print("⚠️  Picamera2 not available - camera initialization skipped")
            return False
        
        try:
            print("🚀 Initializing camera...")
            
            # Lazy detection for low resource mode
            if self.config.low_resource_mode and not self.hardware_detector.sensor_resolution:
                self.hardware_detector.detect_camera_capabilities()
            
            # Get optimal configuration for this camera module
            camera_config = self.hardware_detector.get_optimal_camera_config()
            
            # Print configuration summary
            self.hardware_detector.print_detection_summary()
            
            # Create camera instance
            self.camera_device = Picamera2()
            
            # Create dual-stream video configuration
            video_config = self.camera_device.create_video_configuration(
                main=camera_config["main_stream"],
                lores=camera_config["lores_stream"],
                encode="lores",  # Stream the lower resolution
                buffer_count=camera_config["buffer_count"],
                transform=camera_config["transform"]
            )
            
            # Configure and start camera
            self.camera_device.configure(video_config)
            self.camera_device.start()
            
            # Wait for camera to stabilize
            time.sleep(2)
            
            print("✅ Camera initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ Camera initialization failed: {e}")
            return self._try_minimal_config()
    
    def _try_minimal_config(self) -> bool:
        """Last resort minimal configuration"""
        if not PICAMERA2_AVAILABLE:
            return False
        
        try:
            print("🔄 Trying minimal camera configuration...")
            
            self.camera_device = Picamera2()
            
            # Use minimal config helper
            minimal_config = create_minimal_camera_config()
            if self.config.low_resource_mode:
                minimal_config["buffer_count"] = 1
            
            self.camera_device.configure(minimal_config)
            self.camera_device.start()
            time.sleep(2)
            
            print("✅ Minimal camera configuration successful")
            return True
            
        except Exception as e:
            print(f"❌ Even minimal config failed: {e}")
            return False
    
    def capture_photo(self) -> Tuple[bool, str, str]:
        """
        Capture high-resolution still photo without interrupting video stream
        
        Returns:
            Tuple[bool, str, str]: (success, message, filename)
            
        Raises:
            PhotoCaptureError: If capture fails
        """
        if not self.camera_device:
            if not self.init_camera():
                return False, "Camera initialization failed", ""
        
        return self.photo_capture.capture_photo(self.camera_device)
    
    @handle_camera_error
    def setup_streaming(self) -> bool:
        """
        Setup MJPEG streaming from lores stream with adaptive capabilities
        
        Returns:
            bool: True if streaming setup was successful
            
        Raises:
            StreamingError: If streaming setup fails
        """
        if not self.camera_device:
            if not self.init_camera():
                return False
        
        if not PICAMERA2_AVAILABLE:
            print("⚠️  Streaming not available without Picamera2")
            return False
        
        try:
            print("🎥 Setting up adaptive video streaming...")
            
            # Create streaming components
            self.stream_output = create_stream_output(enable_queue=True, queue_size=10)
            self.frame_generator = FrameGenerator(
                self.stream_output, 
                self.quality_adapter.current_frame_rate
            )
            
            # Initialize quality adapter with encoder
            encoder = self.quality_adapter.initialize_encoder()
            
            # Set up component references
            self.quality_adapter.set_camera_references(self.camera_device, self.stream_output)
            self.network_monitor.set_components(self.stream_output, self.quality_adapter)
            
            # Set up adaptation callback for statistics
            self.network_monitor.set_adaptation_callback(self._on_adaptation)
            
            # Start recording from lores stream for streaming
            self.camera_device.start_recording( # type: ignore
                encoder,
                FileOutput(self.stream_output)
            )
            
            self.is_streaming = True
            
            # Start network monitoring if adaptive streaming is enabled
            if self.config.adaptive_streaming or self.config.adaptive_quality:
                self.network_monitor.start_monitoring()
            
            # Print status
            status = self.quality_adapter.get_adaptation_status()
            print(f"✅ Adaptive video streaming started")
            print(f"   🎯 Quality: {status['current_quality']}% (max: {status['max_quality']}%)")
            print(f"   📊 Frame rate: {status['current_frame_rate']} fps")
            print(f"   🔄 Adaptive streaming: {status['adaptive_streaming_enabled']}")
            print(f"   🎨 Adaptive quality: {status['adaptive_quality_enabled']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Streaming setup failed: {e}")
            raise StreamingError(f"Failed to setup streaming: {str(e)}")
    
    def stop_streaming(self) -> bool:
        """
        Stop video streaming and network monitoring
        
        Returns:
            bool: True if streaming was stopped successfully
        """
        if not self.is_streaming or not self.camera_device:
            return True
        
        try:
            print("🛑 Stopping adaptive video stream...")
            
            # Stop frame generation
            if self.frame_generator:
                self.frame_generator.stop()
            
            # Stop network monitoring
            self.network_monitor.stop_monitoring()
            
            # Stop camera recording
            self.camera_device.stop_recording()
            self.is_streaming = False
            
            # Reset adaptive parameters
            self.quality_adapter.reset_to_maximum_quality()
            
            print("✅ Adaptive video streaming stopped")
            return True
            
        except Exception as e:
            print(f"❌ Error stopping stream: {e}")
            return False
    
    def generate_frames(self):
        """
        Generate frames for MJPEG streaming with adaptive frame rate
        
        Yields:
            bytes: MJPEG frame data
        """
        if not self.frame_generator or not self.is_streaming:
            return
        
        # Use the frame generator from the video streaming module
        for frame in self.frame_generator.generate_frames():
            yield frame
            
            # Update statistics
            self.total_frames_sent += 1
            self.streaming_stats.record_frame_sent()
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get camera status information with adaptive streaming metrics
        
        Returns:
            dict: Comprehensive camera status
        """
        # Get hardware information
        hardware_info = self.hardware_detector.get_hardware_info()
        
        # Base status
        status = {
            "available": self.camera_device is not None,
            "streaming": self.is_streaming,
            "module": hardware_info["camera_module"],
            "resolution": hardware_info["sensor_resolution"],
            "buffer_count": hardware_info["recommended_buffer_count"],
            "picamera2_available": PICAMERA2_AVAILABLE,
            "low_resource_mode": self.config.low_resource_mode,
            
            # Performance metrics
            "total_frames_sent": self.total_frames_sent,
            "total_frames_dropped": self.total_frames_dropped
        }
        
        # Add adaptive streaming status if available
        if self.quality_adapter:
            adaptation_status = self.quality_adapter.get_adaptation_status()
            status.update({
                "adaptive_streaming": adaptation_status["adaptive_streaming_enabled"],
                "adaptive_quality": adaptation_status["adaptive_quality_enabled"],
                "current_frame_rate": adaptation_status["current_frame_rate"],
                "current_quality": adaptation_status["current_quality"],
                "max_quality": adaptation_status["max_quality"],
                "target_frame_rate_range": f"{adaptation_status['frame_rate_range'][0]}-{adaptation_status['frame_rate_range'][1]}",
                "quality_range": f"{adaptation_status['quality_range'][0]}-{adaptation_status['quality_range'][1]}",
            })
        
        # Add streaming statistics if available
        if self.stream_output:
            performance_metrics = self.stream_output.get_performance_metrics()
            status.update({
                "frames_written": performance_metrics["frames_written"],
                "frames_delivered": performance_metrics["frames_delivered"],
                "network_slow": performance_metrics["network_slow"],
                "average_delivery_time": round(performance_metrics["average_delivery_time"], 3),
                "streaming_mode": "adaptive_latest_frame_broadcast"
            })
        
        # Add network monitoring status
        if self.network_monitor:
            network_status = self.network_monitor.get_current_network_status()
            status["network_status"] = network_status["status"]
            status["network_monitoring"] = network_status.get("monitoring_active", False)
        
        return status
    
    def get_streaming_stats(self) -> Dict[str, Any]:
        """
        Get detailed streaming performance statistics
        
        Returns:
            dict: Comprehensive streaming statistics
        """
        if not self.stream_output:
            return {"error": "No active stream"}
        
        # Get base metrics from stream output
        metrics = self.stream_output.get_performance_metrics()
        
        # Get adaptation status
        adaptation_status = self.quality_adapter.get_adaptation_status() if self.quality_adapter else {}
        
        # Get frame generation stats
        generation_stats = self.frame_generator.get_generation_stats() if self.frame_generator else {}
        
        # Get comprehensive streaming statistics
        comprehensive_stats = self.streaming_stats.get_comprehensive_stats()
        
        # Get network monitoring stats
        monitoring_stats = self.network_monitor.get_monitoring_stats() if self.network_monitor else {}
        
        return {
            "performance": metrics,
            "adaptation": {
                "current_frame_rate": adaptation_status.get("current_frame_rate", 0),
                "current_quality": adaptation_status.get("current_quality", 0),
                "max_quality": adaptation_status.get("max_quality", 0),
                "frames_sent": generation_stats.get("frames_sent", 0),
                "frames_dropped": generation_stats.get("frames_dropped", 0),
                "drop_rate": 1.0 - generation_stats.get("success_rate", 0.0)
            },
            "configuration": {
                "adaptive_streaming": adaptation_status.get("adaptive_streaming_enabled", False),
                "adaptive_quality": adaptation_status.get("adaptive_quality_enabled", False),
                "frame_rate_range": adaptation_status.get("frame_rate_range", [0, 0]),
                "quality_range": adaptation_status.get("quality_range", [0, 0]),
                "network_check_interval": self.config.network_check_interval,
                "network_timeout_threshold": self.config.network_timeout_threshold
            },
            "detailed_stats": comprehensive_stats,
            "monitoring": monitoring_stats
        }
    
    def _on_adaptation(self, adaptation_result: Dict[str, Any], metrics: Dict[str, Any]):
        """
        Callback for when adaptation occurs
        
        Args:
            adaptation_result: Results from quality adapter
            metrics: Current performance metrics
        """
        # Record adaptation in statistics
        self.streaming_stats.record_adaptation(adaptation_result, metrics)
        
        # Update frame generator if frame rate changed
        if (adaptation_result.get("frame_rate_changed", False) and 
            self.frame_generator and 
            "current_frame_rate" in adaptation_result):
            self.frame_generator.update_frame_rate(adaptation_result["current_frame_rate"])
        
        # Record network condition
        network_condition = "slow" if metrics.get("network_slow", False) else "stable"
        self.streaming_stats.record_network_condition(network_condition)
    
    def cleanup(self):
        """Clean up camera resources and stop all components"""
        try:
            # Stop streaming if active
            if self.is_streaming:
                self.stop_streaming()
            
            # Stop network monitoring
            if self.network_monitor:
                self.network_monitor.stop_monitoring()
            
            # Close camera device
            if self.camera_device:
                self.camera_device.stop()
                self.camera_device.close()
                self.camera_device = None
                print("🔒 Camera resources released")
            
            # Reset statistics
            if self.streaming_stats:
                print(f"📊 Final session stats: {self.streaming_stats.export_stats_summary()}")
                
        except Exception as e:
            print(f"⚠️  Error during cleanup: {e}")
    
    # Properties for backward compatibility
    @property
    def sensor_resolution(self) -> Optional[Tuple[int, int]]:
        """Get sensor resolution from hardware detector"""
        return self.hardware_detector.sensor_resolution
    
    @property
    def camera_module(self) -> str:
        """Get camera module type from hardware detector"""
        return self.hardware_detector.camera_module
    
    @property
    def recommended_buffer_count(self) -> int:
        """Get recommended buffer count from hardware detector"""
        return self.hardware_detector.recommended_buffer_count
    
    # Additional utility methods
    def get_photo_stats(self) -> Dict[str, Any]:
        """Get photo capture statistics"""
        return self.photo_capture.get_capture_stats()
    
    def get_hardware_info(self) -> Dict[str, Any]:
        """Get hardware detection information"""
        return self.hardware_detector.get_hardware_info()
    
    def force_quality_change(self, new_quality: int) -> bool:
        """Force a manual quality change"""
        if self.quality_adapter:
            return self.quality_adapter.force_quality_change(new_quality)
        return False
    
    def force_frame_rate_change(self, new_frame_rate: int) -> bool:
        """Force a manual frame rate change"""
        if self.quality_adapter:
            success = self.quality_adapter.force_frame_rate_change(new_frame_rate)
            if success and self.frame_generator:
                self.frame_generator.update_frame_rate(new_frame_rate)
            return success
        return False
    
    def reset_adaptive_settings(self):
        """Reset adaptive streaming to maximum quality"""
        if self.quality_adapter:
            self.quality_adapter.reset_to_maximum_quality()
    
    def get_network_status(self) -> Dict[str, Any]:
        """Get current network status"""
        if self.network_monitor:
            return self.network_monitor.get_current_network_status()
        return {"status": "unavailable"}
