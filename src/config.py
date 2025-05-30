"""
Configuration management for Raspberry Pi Camera Web App
Handles environment variables with automatic secure credential generation
"""

import os
import secrets
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
        """Create configuration from environment variables with secure defaults"""
        
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
        
        def get_str(key: str, default: str = None) -> str:
            """Get string from environment variable"""
            value = os.getenv(key, default)
            if value is None:
                raise ValueError(f"Required environment variable {key} not found")
            return value
        
        return cls(
            # Security - require these to be set (no defaults)
            api_key=get_str('API_KEY'),
            web_password=get_str('WEB_PASSWORD'),
            
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
        
        if not self.web_password:
            errors.append("WEB_PASSWORD is required")
        
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


def generate_secure_credentials() -> tuple[str, str]:
    """Generate cryptographically secure API key and password"""
    # Generate a secure API key: 'cam_' + 32 random hex characters
    api_key = "cam_" + secrets.token_hex(16)
    
    # Generate a secure password: 16 characters with letters, numbers, and symbols
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(16))
    
    return api_key, password


def create_env_file_with_secure_credentials() -> tuple[str, str]:
    """Create .env file with secure credentials using .env.example as template"""
    api_key, password = generate_secure_credentials()
    
    # Always use .env.example as the single source of truth
    env_example_path = '.env.example'
    
    if os.path.exists(env_example_path):
        with open(env_example_path, 'r') as f:
            env_content = f.read()
        
        # Replace the placeholder values with generated secure credentials
        env_content = env_content.replace('your_secure_api_key_here', api_key)
        env_content = env_content.replace('your_secure_password_here', password)
    else:
        # Minimal fallback only if .env.example is somehow missing
        print("⚠️  Warning: .env.example not found, creating minimal configuration")
        env_content = f"API_KEY={api_key}\nWEB_PASSWORD={password}\n"
    
    # Write the .env file
    with open('.env', 'w') as f:
        f.write(env_content)
    
    return api_key, password


def display_generated_credentials(api_key: str, password: str):
    """Display generated credentials prominently to the user"""
    print("\n" + "="*70)
    print("🚀 FIRST-TIME SETUP: SECURE CREDENTIALS GENERATED!")
    print("="*70)
    print()
    print("📋 Your unique credentials have been automatically generated:")
    print()
    print(f"   🔑 API KEY:      {api_key}")
    print(f"   🔒 WEB PASSWORD: {password}")
    print()
    print("⚠️  IMPORTANT SECURITY NOTICE:")
    print("   • These credentials are UNIQUE to this installation")
    print("   • Save them securely - you'll need them to access the camera")
    print("   • The WEB_PASSWORD is for the web interface login")
    print("   • The API_KEY is for direct API access")
    print("   • Credentials are saved in the .env file")
    print()
    print("💡 MANUAL CONFIGURATION:")
    print("   • You can edit the .env file to use your own credentials")
    print("   • Restart the application after making changes")
    print()
    print("🛡️  BACKUP RECOMMENDATION:")
    print("   • Store these credentials in a password manager")
    print("   • Keep a backup of the .env file in a secure location")
    print()
    print("✅ Setup complete! You can now start the camera system.")
    print("="*70)
    print()


def ensure_secure_env_file():
    """Ensure .env file exists with secure credentials"""
    env_file = '.env'
    
    if not os.path.exists(env_file):
        print("🔐 No configuration found. Generating secure credentials...")
        api_key, password = create_env_file_with_secure_credentials()
        display_generated_credentials(api_key, password)
        return True
    
    return False


def load_env_file():
    """Load environment variables from .env file"""
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
        raise FileNotFoundError("Configuration file .env not found")


def load_config() -> AppConfig:
    """Load and validate configuration with automatic secure credential generation"""
    try:
        # Ensure .env file exists with secure credentials
        first_run = ensure_secure_env_file()
        
        # Load environment variables from .env file
        load_env_file()
        
        # Create configuration
        config = AppConfig.from_env()
        
        # Validate configuration
        errors = config.validate()
        if errors:
            print("❌ Configuration errors:")
            for error in errors:
                print(f"   - {error}")
            raise ValueError("Invalid configuration")
        
        if not first_run:
            print("✅ Configuration loaded successfully")
        
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
