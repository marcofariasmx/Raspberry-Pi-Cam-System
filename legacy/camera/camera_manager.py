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
from .streaming.efficient_streaming_system import EfficientStreamingSystem
from .streaming.optimized_stream_output import OptimizedStreamingOutput
from .streaming.streaming_stats import StreamingStats

# Import picamera2 - graceful handling for development environments
try:
    from picamera2 import Picamera2 # type: ignore
    from picamera2.outputs import FileOutput # type: ignore
    from picamera2.encoders import MJPEGEncoder # type: ignore
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
    
    class MJPEGEncoder:
        def __init__(self): pass


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
        self.streaming_stats = StreamingStats()
        
        # Efficient streaming system
        self.efficient_streaming: Optional[EfficientStreamingSystem] = None
        self.is_streaming = False
        
        # Initialize efficient streaming system
        quality_levels = [30, 50, 70, min(config.stream_quality, 85)]
        self.efficient_streaming = EfficientStreamingSystem(quality_levels)
        
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
            
            # Create optimized dual-stream configuration for efficient streaming
            # Use lower buffer counts for Pi Zero 2W memory efficiency
            optimized_buffer_count = 2 if self.config.low_resource_mode else camera_config["buffer_count"]
            
            video_config = self.camera_device.create_video_configuration(
                main=camera_config["main_stream"],  # High res for photos
                lores=camera_config["lores_stream"], # Low res for streaming  
                encode="lores",  # Stream the lower resolution
                buffer_count=optimized_buffer_count,  # Reduced for memory efficiency
                transform=camera_config["transform"]
            )
            
            print(f"📊 Camera config: Main {camera_config['main_stream']['size']}, "
                  f"Lores {camera_config['lores_stream']['size']}, "
                  f"Buffers: {optimized_buffer_count}")
            
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
        Setup efficient multi-quality streaming with per-client adaptation
        
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
            print("🚀 Setting up efficient multi-quality streaming...")
            
            # Start the efficient streaming system
            if self.efficient_streaming and self.efficient_streaming.start_streaming():
                self.is_streaming = True
                
                # Start camera recording to memory stream for frame capture
                if PICAMERA2_AVAILABLE and self.camera_device:
                    # Create a custom output that feeds frames to our efficient system
                    self._setup_camera_recording()
                
                # Start background frame processing thread (for fallback/mock frames if needed)
                self._start_frame_processing_thread()
                
                # Print status
                status = self.efficient_streaming.get_system_status()
                memory_usage = status["memory_usage"]
                
                print(f"✅ Efficient streaming started")
                print(f"   📊 Quality levels: {status['quality_levels']}")
                print(f"   💾 Memory usage: {memory_usage['total_memory_kb']:.1f}KB")
                print(f"   🎯 Target: <400KB for Pi Zero 2W compatibility")
                print(f"   🌊 Per-client adaptation: Enabled")
                
                return True
            else:
                print("❌ Failed to start efficient streaming system")
                return False
            
        except Exception as e:
            print(f"❌ Streaming setup failed: {e}")
            raise StreamingError(f"Failed to setup streaming: {str(e)}")
    
    def stop_streaming(self) -> bool:
        """
        Stop efficient streaming system
        
        Returns:
            bool: True if streaming was stopped successfully
        """
        if not self.is_streaming:
            return True
        
        try:
            print("🛑 Stopping efficient streaming system...")
            
            # Stop the efficient streaming system
            if self.efficient_streaming:
                self.efficient_streaming.stop_streaming()
            
            # Stop frame processing thread
            self._stop_frame_processing_thread()
            
            # Stop camera recording if active
            if self.camera_device and PICAMERA2_AVAILABLE:
                try:
                    self.camera_device.stop_recording()
                    print("📹 Camera recording stopped")
                except:
                    pass  # May not be recording
            
            self.is_streaming = False
            
            print("✅ Efficient streaming stopped")
            return True
            
        except Exception as e:
            print(f"❌ Error stopping stream: {e}")
            return False
    
    def generate_frames(self, client_id: Optional[str] = None):
        """
        Generate frames for MJPEG streaming with per-client adaptive quality
        
        Args:
            client_id: Optional client identifier for individual adaptation
        
        Yields:
            bytes: MJPEG frame data
        """
        if not self.efficient_streaming or not self.is_streaming:
            print("❌ Streaming system not available")
            return
        
        try:
            # Use the efficient streaming system
            for frame in self.efficient_streaming.create_client_stream(
                client_id=client_id,
                initial_quality=self.config.stream_quality,
                target_fps=30
            ):
                yield frame
                
                # Update statistics
                self.total_frames_sent += 1
                self.streaming_stats.record_frame_sent()
                
        except Exception as e:
            print(f"❌ Error generating frames: {e}")
    
    def _start_frame_processing_thread(self):
        """
        Start background thread to continuously process frames from camera
        """
        self._frame_processing_active = True
        self._frame_processing_thread = threading.Thread(
            target=self._frame_processing_loop,
            daemon=True,
            name="FrameProcessor"
        )
        self._frame_processing_thread.start()
        print("🔄 Frame processing thread started")
    
    def _stop_frame_processing_thread(self):
        """
        Stop background frame processing thread
        """
        self._frame_processing_active = False
        if hasattr(self, '_frame_processing_thread') and self._frame_processing_thread:
            self._frame_processing_thread.join(timeout=3.0)
        print("🛑 Frame processing thread stopped")
    
    def _frame_processing_loop(self):
        """
        Main frame processing loop that captures frames and feeds them to the streaming system
        """
        print("🎬 Frame processing loop started")
        
        # Mock frame data fallback for development
        mock_frame_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\'\" &\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x96\x00\x96\x01\x01"\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'  # Minimal JPEG
        
        while self._frame_processing_active and self.is_streaming:
            try:
                # This loop now serves as a fallback and health check
                # Primary frame feeding is done by camera recording -> EfficientStreamOutput
                
                if not (PICAMERA2_AVAILABLE and self.camera_device):
                    # Only use mock frames when camera is not available
                    if self.efficient_streaming:
                        self.efficient_streaming.process_frame(mock_frame_data)
                
                # Sleep for longer since camera recording handles the main feed
                time.sleep(1.0)  # Check every second instead of every 33ms
                
            except Exception as e:
                print(f"❌ Error in frame processing loop: {e}")
                time.sleep(0.1)  # Brief pause on error
        
        print("🔚 Frame processing loop ended")
    
    def _setup_camera_recording(self):
        """
        Setup optimized camera recording using official Picamera2 best practices
        - Uses hardware MJPEG encoder for better performance
        - Implements threading.Condition pattern for multi-client support
        - Integrates with EfficientStreamingSystem for quality adaptation
        """
        if not PICAMERA2_AVAILABLE or not self.camera_device:
            print("⚠️ Camera not available, skipping recording setup")
            return
        
        try:
            # Create optimized streaming output using official pattern
            self.optimized_stream_output = OptimizedStreamingOutput(self.efficient_streaming)
            
            # Use hardware MJPEG encoder (official best practice for 2025)
            encoder = MJPEGEncoder()  # Hardware accelerated
            
            # Start recording from lores stream with hardware encoding
            self.camera_device.start_recording(encoder, FileOutput(self.optimized_stream_output))
            
            print("✅ Optimized camera recording started")
            print(f"   🔧 Hardware MJPEG encoder: Enabled") 
            print(f"   🧵 Threading.Condition pattern: Active")
            print(f"   🌊 Multi-client support: Ready")
            print(f"   💾 Memory optimized for Pi Zero 2W: Yes")
            
        except Exception as e:
            print(f"❌ Failed to setup optimized recording: {e}")
            print("🔄 Falling back to frame capture method")
            # Keep the existing frame processing thread as fallback
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get camera status information with efficient streaming metrics
        
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
        
        # Add efficient streaming status if available
        if self.efficient_streaming:
            system_status = self.efficient_streaming.get_system_status()
            network_status = self.efficient_streaming.get_network_status()
            
            status.update({
                "streaming_system": "efficient_multi_quality",
                "quality_levels": system_status["quality_levels"],
                "active_clients": len(self.efficient_streaming.get_active_clients()),
                "memory_usage_kb": system_status["memory_usage"]["total_memory_kb"],
                "memory_efficiency": system_status["memory_usage"]["total_memory_kb"] <= 400,
                "system_fps": system_status["system"]["average_fps"],
                "network_status": network_status["status"],
                "network_trend": network_status["trend"],
                "client_load_factor": network_status["client_load_factor"]
            })
        
        return status
    
    def get_streaming_stats(self) -> Dict[str, Any]:
        """
        Get detailed efficient streaming performance statistics
        
        Returns:
            dict: Comprehensive streaming statistics
        """
        if not self.efficient_streaming:
            return {"error": "No efficient streaming system available"}
        
        # Get comprehensive system status
        system_status = self.efficient_streaming.get_system_status()
        
        # Get client information
        all_clients = self.efficient_streaming.get_all_clients_info()
        
        # Get network performance
        network_status = self.efficient_streaming.get_network_status()
        
        # Get memory efficiency report
        memory_report = self.efficient_streaming.get_memory_efficiency_report()
        
        return {
            "system_performance": system_status["system"],
            "frame_producer": system_status["frame_producer"],
            "client_manager": system_status["client_manager"],
            "network_performance": network_status,
            "memory_efficiency": memory_report,
            "active_clients": all_clients,
            "configuration": {
                "quality_levels": system_status["quality_levels"],
                "streaming_mode": "efficient_multi_quality_per_client",
                "memory_target_kb": 400,
                "pi_zero_compatible": memory_report["is_efficient"]
            },
            "recommendations": memory_report["recommendations"]
        }
    
    def get_client_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific client
        
        Args:
            client_id: Client identifier
            
        Returns:
            dict: Client information or None if not found
        """
        if self.efficient_streaming:
            return self.efficient_streaming.get_client_info(client_id)
        return None
    
    def force_client_quality(self, client_id: str, quality: int) -> bool:
        """
        Force a specific quality for a client
        
        Args:
            client_id: Target client
            quality: Quality percentage (30-85)
            
        Returns:
            bool: True if successful
        """
        if self.efficient_streaming:
            return self.efficient_streaming.force_client_quality(client_id, quality)
        return False
    
    def disconnect_client(self, client_id: str) -> bool:
        """
        Disconnect a specific client
        
        Args:
            client_id: Client to disconnect
            
        Returns:
            bool: True if client was disconnected
        """
        if self.efficient_streaming:
            return self.efficient_streaming.disconnect_client(client_id)
        return False
    
    def cleanup(self):
        """Clean up camera resources and stop all components"""
        try:
            # Stop streaming if active
            if self.is_streaming:
                self.stop_streaming()
            
            # Stop efficient streaming system
            if self.efficient_streaming:
                self.efficient_streaming.stop_streaming()
            
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
    
    def get_network_status(self) -> Dict[str, Any]:
        """Get current network performance status"""
        if self.efficient_streaming:
            return self.efficient_streaming.get_network_status()
        return {"status": "unavailable", "message": "Streaming system not available"}
    
    def clear_performance_data(self):
        """Clear all performance tracking data"""
        if self.efficient_streaming:
            self.efficient_streaming.clear_performance_data()
    
    def get_memory_efficiency_report(self) -> Dict[str, Any]:
        """Get memory efficiency analysis for Pi Zero 2W compatibility"""
        if self.efficient_streaming:
            return self.efficient_streaming.get_memory_efficiency_report()
        return {"error": "Streaming system not available"}
    
    def update_quality_levels(self, new_levels: list) -> bool:
        """Update available quality levels"""
        if self.efficient_streaming:
            return self.efficient_streaming.update_quality_levels(new_levels)
        return False
