"""
Raspberry Pi Camera System

A modular camera management system for Raspberry Pi with adaptive streaming,
high-resolution photo capture, and comprehensive hardware detection.
"""

from .camera_manager import CameraManager
from .camera_exceptions import (
    CameraError,
    CameraInitializationError,
    StreamingError,
    PhotoCaptureError
)

__all__ = [
    'CameraManager',
    'CameraError',
    'CameraInitializationError', 
    'StreamingError',
    'PhotoCaptureError'
]

__version__ = "2.0.0"
