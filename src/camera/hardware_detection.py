"""
Camera Hardware Detection and Configuration

Handles automatic detection of Raspberry Pi camera modules,
capability assessment, and configuration optimization based on hardware.
"""

from typing import Optional, Tuple, Dict, Any
from src.config import AppConfig
from .camera_exceptions import HardwareDetectionError, handle_camera_error

# Import picamera2 - graceful handling for development environments
try:
    from picamera2 import Picamera2 # type: ignore
    from libcamera import Transform # type: ignore
    PICAMERA2_AVAILABLE = True
    print("✅ Picamera2 imported successfully")
except ImportError as e:
    print(f"⚠️  Picamera2 not available: {e}")
    PICAMERA2_AVAILABLE = False
    # Mock classes for development
    class Picamera2:
        def __init__(self): pass
        @property
        def sensor_resolution(self): return (1920, 1080)
        def close(self): pass
    
    class Transform:
        def __init__(self, **kwargs): pass


class HardwareDetector:
    """
    Detects camera hardware and optimizes configuration
    
    Automatically identifies camera module type (Module 2, Module 3, etc.)
    and provides optimized settings for performance and resource usage.
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.sensor_resolution: Optional[Tuple[int, int]] = None
        self.camera_module: str = "unknown"
        self.recommended_buffer_count: int = 2
    
    @handle_camera_error
    def detect_camera_capabilities(self) -> bool:
        """
        Auto-detect camera module and adapt settings
        
        Returns:
            bool: True if detection was successful, False otherwise
            
        Raises:
            HardwareDetectionError: If detection fails critically
        """
        if not PICAMERA2_AVAILABLE:
            print("⚠️  Picamera2 not available - using mock configuration")
            self._use_fallback_configuration()
            return False
        
        try:
            # Temporary camera instance for detection
            temp_camera = Picamera2()
            self.sensor_resolution = temp_camera.sensor_resolution
            temp_camera.close()
            
            # Detect module type based on resolution
            self._classify_camera_module()
            
            print(f"📷 {self.camera_module} detected: {self.sensor_resolution[0]}x{self.sensor_resolution[1]}")
            return True
            
        except Exception as e:
            print(f"⚠️  Camera detection failed: {e}")
            self._use_fallback_configuration()
            return False
    
    def _classify_camera_module(self):
        """Classify camera module based on sensor resolution"""
        if not self.sensor_resolution:
            self.camera_module = "unknown"
            self.recommended_buffer_count = 2
            return
        
        width, height = self.sensor_resolution
        total_pixels = width * height
        
        if total_pixels >= 12000000:  # 12MP+ (Module 3)
            self.camera_module = "Camera Module 3"
            self.recommended_buffer_count = 2 if self.config.low_resource_mode else 2
        elif total_pixels >= 8000000:  # 8MP+ (Module 2)
            self.camera_module = "Camera Module 2"
            self.recommended_buffer_count = 2 if self.config.low_resource_mode else 3
        elif total_pixels >= 5000000:  # 5MP+ (Module 1 v2)
            self.camera_module = "Camera Module 1 v2"
            self.recommended_buffer_count = 2
        else:
            self.camera_module = "Camera Module (other)"
            self.recommended_buffer_count = 2
    
    def _use_fallback_configuration(self):
        """Use fallback configuration when detection fails"""
        self.sensor_resolution = (
            self.config.camera_fallback_width,
            self.config.camera_fallback_height
        )
        self.camera_module = "fallback"
        self.recommended_buffer_count = 2
    
    def get_optimal_camera_config(self) -> Dict[str, Any]:
        """
        Get camera configuration optimized for detected module and resource mode
        
        Returns:
            Dict containing optimized camera configuration
        """
        # Main stream - full resolution for photo capture
        if self.config.camera_auto_detect and self.sensor_resolution:
            main_size = self.sensor_resolution
        else:
            main_size = (
                self.config.camera_fallback_width,
                self.config.camera_fallback_height
            )
        
        # Lores stream - consistent across modules for video streaming
        lores_size = (self.config.stream_width, self.config.stream_height)
        
        # Camera buffer count optimization
        if self.config.low_resource_mode:
            buffer_count = 1  # Single buffer for Pi Zero 2W
        elif self.config.buffer_count_auto:
            buffer_count = self.recommended_buffer_count
        else:
            buffer_count = self.config.buffer_count_fallback
        
        # Format optimization for low resource mode
        if self.config.low_resource_mode:
            # Prefer YUV420 for better performance on Pi Zero 2W
            main_format = "YUV420" if self.config.main_stream_format == "RGB888" else self.config.main_stream_format
            lores_format = "YUV420"
        else:
            main_format = self.config.main_stream_format
            lores_format = self.config.lores_stream_format
        
        return {
            "main_stream": {
                "size": main_size,
                "format": main_format
            },
            "lores_stream": {
                "size": lores_size,
                "format": lores_format
            },
            "buffer_count": buffer_count,
            "transform": Transform(
                hflip=self.config.camera_hflip,
                vflip=self.config.camera_vflip
            ) if PICAMERA2_AVAILABLE else None
        }
    
    def get_hardware_info(self) -> Dict[str, Any]:
        """
        Get comprehensive hardware information
        
        Returns:
            Dict containing hardware detection results
        """
        return {
            "sensor_resolution": self.sensor_resolution,
            "camera_module": self.camera_module,
            "recommended_buffer_count": self.recommended_buffer_count,
            "picamera2_available": PICAMERA2_AVAILABLE,
            "low_resource_mode": self.config.low_resource_mode,
            "detection_successful": self.sensor_resolution is not None and self.camera_module != "fallback"
        }
    
    def print_detection_summary(self):
        """Print a summary of hardware detection results"""
        config = self.get_optimal_camera_config()
        
        print("📋 Hardware Detection Summary:")
        print(f"   📷 Camera: {self.camera_module}")
        print(f"   📐 Main stream: {config['main_stream']['size']} ({config['main_stream']['format']})")
        print(f"   📺 Lores stream: {config['lores_stream']['size']} ({config['lores_stream']['format']})")
        print(f"   🧠 Buffer count: {config['buffer_count']}")
        print(f"   ⚡ Low resource mode: {self.config.low_resource_mode}")
        print(f"   🔄 Transform: HFlip={self.config.camera_hflip}, VFlip={self.config.camera_vflip}")


def create_minimal_camera_config() -> Dict[str, Any]:
    """
    Create minimal camera configuration for fallback scenarios
    
    Returns:
        Dict containing minimal but functional camera configuration
    """
    return {
        "main": {"size": (1920, 1080), "format": "RGB888"},
        "lores": {"size": (640, 480)},
        "encode": "lores",
        "buffer_count": 1
    }


def validate_camera_config(config: Dict[str, Any]) -> bool:
    """
    Validate camera configuration for common issues
    
    Args:
        config: Camera configuration dictionary
        
    Returns:
        bool: True if configuration is valid
    """
    try:
        # Check required keys
        required_keys = ["main_stream", "lores_stream", "buffer_count"]
        for key in required_keys:
            if key not in config:
                print(f"⚠️  Missing required configuration key: {key}")
                return False
        
        # Check resolution formats
        main_size = config["main_stream"]["size"]
        lores_size = config["lores_stream"]["size"]
        
        if not isinstance(main_size, tuple) or len(main_size) != 2:
            print("⚠️  Invalid main stream size format")
            return False
        
        if not isinstance(lores_size, tuple) or len(lores_size) != 2:
            print("⚠️  Invalid lores stream size format")
            return False
        
        # Check reasonable dimensions
        if main_size[0] < 320 or main_size[1] < 240:
            print("⚠️  Main stream resolution too small")
            return False
        
        if lores_size[0] < 160 or lores_size[1] < 120:
            print("⚠️  Lores stream resolution too small")
            return False
        
        # Check buffer count
        buffer_count = config["buffer_count"]
        if not isinstance(buffer_count, int) or buffer_count < 1 or buffer_count > 10:
            print("⚠️  Invalid buffer count (must be 1-10)")
            return False
        
        return True
        
    except Exception as e:
        print(f"⚠️  Configuration validation error: {e}")
        return False
