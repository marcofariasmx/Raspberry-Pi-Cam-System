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
        stream_width: Video stream width in pixels (default: 800)
        stream_height: Video stream height in pixels (default: 600)  
        stream_fps: Video stream frames per second (default: 15)
        jpeg_quality: JPEG compression quality percentage (default: 85)
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
    jpeg_quality: int = 85
    
    # Camera hardware settings
    camera_hflip: bool = False
    camera_vflip: bool = False


def get_config() -> Config:
    """
    Create configuration instance with environment variable overrides.
    
    Loads the default configuration and applies any environment variable
    overrides. This allows for flexible deployment configuration without
    code changes.
    
    Environment Variables:
        CAMERA_HOST: Override server host address
        CAMERA_PORT: Override server port number
        STREAM_WIDTH: Override video stream width
        STREAM_HEIGHT: Override video stream height
        STREAM_FPS: Override video stream framerate
        JPEG_QUALITY: Override JPEG compression quality (10-100)
        CAMERA_HFLIP: Enable horizontal flip ("true"/"false")
        CAMERA_VFLIP: Enable vertical flip ("true"/"false")
    
    Returns:
        Config: Configured instance with environment overrides applied
    """
    return Config(
        host=os.getenv("CAMERA_HOST", "0.0.0.0"),
        port=int(os.getenv("CAMERA_PORT", "8000")),
        stream_width=int(os.getenv("STREAM_WIDTH", "800")),
        stream_height=int(os.getenv("STREAM_HEIGHT", "600")),
        stream_fps=int(os.getenv("STREAM_FPS", "15")),
        jpeg_quality=int(os.getenv("JPEG_QUALITY", "85")),
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
    print(f"   Quality: {config.jpeg_quality}% JPEG compression")
    print(f"   Transforms: hflip={config.camera_hflip}, vflip={config.camera_vflip}")