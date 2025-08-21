"""
Configuration Management for Raspberry Pi Camera Streaming Application

This module provides centralized configuration management for the camera streaming
system with support for environment variable overrides and runtime validation.

The configuration system handles:
- Server network settings (host/port)
- Camera stream parameters (resolution, framerate, quality)
- Hardware-specific settings (camera transforms)
- Environment-based configuration overrides

All settings can be customized via environment variables for deployment flexibility.
"""

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


@dataclass
class Config:
    """
    Configuration dataclass for camera streaming application.
    
    This class defines all configurable parameters for the streaming system,
    including server settings, camera parameters, and hardware configurations.
    All values have sensible defaults and can be overridden via environment variables.
    
    Attributes:
        host: Server bind address (default: "0.0.0.0" for all interfaces)
        port: Server port number (default: 8000)
        stream_width: Video stream width in pixels (default: 640 for Pi Zero 2W efficiency)
        stream_height: Video stream height in pixels (default: 480)  
        stream_fps: Video stream frames per second (default: 15)
        
        # H.264 MediaMTX streaming
        h264_bitrate: H.264 bitrate in bps (default: 1,000,000 = 1 Mbps)
        mediamtx_udp_port: UDP port for streaming to MediaMTX (default: 8890)
        mediamtx_webrtc_port: MediaMTX WebRTC port (default: 8889)
        mediamtx_hls_port: MediaMTX HLS port (default: 8888)
        
        camera_hflip: Enable horizontal flip of camera image (default: False)
        camera_vflip: Enable vertical flip of camera image (default: False)
    """
    
    # Server network configuration
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Camera stream parameters
    stream_width: int = 800
    stream_height: int = 600
    stream_fps: int = 15
    
    # H.264 streaming via MediaMTX
    h264_bitrate: int = 1000000  # 1 Mbps
    mediamtx_udp_port: int = 8890
    mediamtx_webrtc_port: int = 8889
    mediamtx_hls_port: int = 8888
    
    # Camera hardware settings
    camera_hflip: bool = False
    camera_vflip: bool = False


def get_config() -> Config:
    """
    Create configuration instance with .env file and environment variable overrides.
    
    Loads configuration in the following priority order:
    1. Default values
    2. .env file values (if available)  
    3. Environment variable overrides (highest priority)
    
    This allows for flexible deployment configuration with .env files
    for development and environment variables for production.
    
    Environment Variables:
        CAMERA_HOST: Override server host address
        CAMERA_PORT: Override server port number
        STREAM_WIDTH: Override video stream width
        STREAM_HEIGHT: Override video stream height
        STREAM_FPS: Override video stream framerate
        
        # H.264 MediaMTX settings
        H264_BITRATE: Override H.264 bitrate in bps (e.g., "2000000" for 2Mbps)
        MEDIAMTX_UDP_PORT: UDP port for streaming to MediaMTX
        MEDIAMTX_WEBRTC_PORT: MediaMTX WebRTC port
        MEDIAMTX_HLS_PORT: MediaMTX HLS port
        CAMERA_HFLIP: Enable horizontal flip ("true"/"false")
        CAMERA_VFLIP: Enable vertical flip ("true"/"false")
    
    Returns:
        Config: Configured instance with .env and environment overrides applied
    """
    # Load .env file if available
    if DOTENV_AVAILABLE:
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            # Try loading from current working directory
            load_dotenv()
    
    return Config(
        host=os.getenv("CAMERA_HOST", "0.0.0.0"),
        port=int(os.getenv("CAMERA_PORT", "8000")),
        stream_width=int(os.getenv("STREAM_WIDTH", "800")),
        stream_height=int(os.getenv("STREAM_HEIGHT", "600")),
        stream_fps=int(os.getenv("STREAM_FPS", "15")),
        
        # H.264 MediaMTX settings
        h264_bitrate=int(os.getenv("H264_BITRATE", "1000000")),
        mediamtx_udp_port=int(os.getenv("MEDIAMTX_UDP_PORT", "8890")),
        mediamtx_webrtc_port=int(os.getenv("MEDIAMTX_WEBRTC_PORT", "8889")),
        mediamtx_hls_port=int(os.getenv("MEDIAMTX_HLS_PORT", "8888")),
        
        camera_hflip=os.getenv("CAMERA_HFLIP", "false").lower() == "true",
        camera_vflip=os.getenv("CAMERA_VFLIP", "false").lower() == "true"
    )


def print_config(config: Config):
    """
    Display configuration summary for debugging and verification.
    
    Prints a human-readable summary of the current configuration settings,
    useful for startup logging and troubleshooting.
    
    Args:
        config: Configuration instance to display
    """
    print("📷 Camera Streaming Configuration:")
    print(f"   Server: {config.host}:{config.port}")
    print(f"   Stream: {config.stream_width}x{config.stream_height} @ {config.stream_fps}fps")
    
    print(f"   H.264: {config.h264_bitrate//1000000}Mbps bitrate")
    print(f"   MediaMTX: WebRTC:{config.mediamtx_webrtc_port}, HLS:{config.mediamtx_hls_port}")
    
    print(f"   Transforms: hflip={config.camera_hflip}, vflip={config.camera_vflip}")