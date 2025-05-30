"""
Configuration management for Raspberry Pi Camera Web App
Handles environment variables with sensible defaults and validation
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class AppConfig:
    """Application configuration with environment variable support"""
    
    # Security
    api_key: str
    web_password: str
    
    # Camera settings
    camera_auto_detect: bool
    camera_fallback_width: int
    camera_fallback_height: int
    
    # Streaming
    stream_width: int
    stream_height: int
    stream_quality: int
    
    # Memory management
    buffer_count_auto: bool
    buffer_count_fallback: int
    
    # Camera orientation
    camera_hflip: bool
    camera_vflip: bool
    
    # Formats
    main_stream_format: str
    lores_stream_format: str
    
    # Server
    host: str
    port: int
    debug: bool
    
    # Application
    photos_dir: str
    max_photos: int

    @classmethod
    def from_env(cls) -> 'AppConfig':
        """Create configuration from environment variables with defaults"""
        
        def get_bool(key: str, default: bool) -> bool:
            """Get boolean from environment variable"""
            value = os.getenv(key, str(default)).lower()
            return value in ('true', '1', 'yes', 'on')
        
        def get_int(key: str, default: int) -> int:
            """Get integer from environment variable"""
            try:
                return int(os.getenv(key, str(default)))
            except ValueError:
                return default
        
        def get_str(key: str, default: str) -> str:
            """Get string from environment variable"""
            return os.getenv(key, default)
        
        return cls(
            # Security - generate secure defaults if not provided
            api_key=get_str('API_KEY', 'cam_secure_key_raspberry_pi_monitor'),
            web_password=get_str('WEB_PASSWORD', 'camera123'),
            
            # Camera configuration
            camera_auto_detect=get_bool('CAMERA_AUTO_DETECT', True),
            camera_fallback_width=get_int('CAMERA_FALLBACK_WIDTH', 1920),
            camera_fallback_height=get_int('CAMERA_FALLBACK_HEIGHT', 1080),
            
            # Streaming configuration
            stream_width=get_int('STREAM_WIDTH', 640),
            stream_height=get_int('STREAM_HEIGHT', 480),
            stream_quality=get_int('STREAM_QUALITY', 85),
            
            # Memory management
            buffer_count_auto=get_bool('BUFFER_COUNT_AUTO', True),
            buffer_count_fallback=get_int('BUFFER_COUNT_FALLBACK', 2),
            
            # Camera orientation
            camera_hflip=get_bool('CAMERA_HFLIP', True),
            camera_vflip=get_bool('CAMERA_VFLIP', True),
            
            # Format settings
            main_stream_format=get_str('MAIN_STREAM_FORMAT', 'RGB888'),
            lores_stream_format=get_str('LORES_STREAM_FORMAT', 'YUV420'),
            
            # Server configuration
            host=get_str('HOST', '127.0.0.1'),
            port=get_int('PORT', 8003),
            debug=get_bool('DEBUG', False),
            
            # Application settings
            photos_dir=get_str('PHOTOS_DIR', 'captured_images'),
            max_photos=get_int('MAX_PHOTOS', 100)
        )
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of errors"""
        errors = []
        
        # Validate security
        if not self.api_key or len(self.api_key) < 8:
            errors.append("API_KEY must be at least 8 characters long")
        
        if not self.web_password or len(self.web_password) < 6:
            errors.append("WEB_PASSWORD must be at least 6 characters long")
        
        # Validate camera settings
        if self.camera_fallback_width < 320 or self.camera_fallback_height < 240:
            errors.append("Camera fallback resolution too small (minimum 320x240)")
        
        if self.stream_width < 160 or self.stream_height < 120:
            errors.append("Stream resolution too small (minimum 160x120)")
        
        # Validate server settings
        if not (1 <= self.port <= 65535):
            errors.append("Port must be between 1 and 65535")
        
        # Validate formats
        valid_formats = ['RGB888', 'BGR888', 'YUV420']
        if self.main_stream_format not in valid_formats:
            errors.append(f"Invalid main stream format. Must be one of: {valid_formats}")
        
        return errors
    
    def print_summary(self):
        """Print configuration summary for debugging"""
        print("📋 Configuration Summary:")
        print(f"   🔒 Security: API key set, Password: {'*' * len(self.web_password)}")
        print(f"   📷 Camera: Auto-detect={self.camera_auto_detect}, Fallback={self.camera_fallback_width}x{self.camera_fallback_height}")
        print(f"   🎥 Stream: {self.stream_width}x{self.stream_height}, Quality={self.stream_quality}")
        print(f"   🧠 Memory: Auto-buffer={self.buffer_count_auto}, Fallback={self.buffer_count_fallback}")
        print(f"   🔄 Transform: HFlip={self.camera_hflip}, VFlip={self.camera_vflip}")
        print(f"   🌐 Server: {self.host}:{self.port}, Debug={self.debug}")
        print(f"   📁 Photos: {self.photos_dir}, Max={self.max_photos}")


def load_config() -> AppConfig:
    """Load and validate configuration"""
    try:
        # Try to load .env file if it exists
        env_file = '.env'
        if os.path.exists(env_file):
            print(f"📄 Loading configuration from {env_file}")
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
        else:
            print("⚠️  No .env file found, using environment variables and defaults")
        
        # Create configuration
        config = AppConfig.from_env()
        
        # Validate configuration
        errors = config.validate()
        if errors:
            print("❌ Configuration errors:")
            for error in errors:
                print(f"   - {error}")
            raise ValueError("Invalid configuration")
        
        return config
        
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        raise


# Global configuration instance
app_config: Optional[AppConfig] = None

def get_config() -> AppConfig:
    """Get global configuration instance"""
    global app_config
    if app_config is None:
        app_config = load_config()
    return app_config
