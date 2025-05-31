"""
Camera-specific exceptions and error handling

Provides a hierarchy of custom exceptions for camera operations,
enabling precise error handling and user-friendly error messages.
"""

from typing import Optional


class CameraError(Exception):
    """Base exception for all camera-related errors"""
    
    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)
    
    def __str__(self):
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class CameraInitializationError(CameraError):
    """Raised when camera initialization fails"""
    
    def __init__(self, message: str = "Camera initialization failed", details: Optional[str] = None):
        super().__init__(message, details)


class StreamingError(CameraError):
    """Raised when streaming operations fail"""
    
    def __init__(self, message: str = "Streaming operation failed", details: Optional[str] = None):
        super().__init__(message, details)


class PhotoCaptureError(CameraError):
    """Raised when photo capture operations fail"""
    
    def __init__(self, message: str = "Photo capture failed", details: Optional[str] = None):
        super().__init__(message, details)


class HardwareDetectionError(CameraError):
    """Raised when hardware detection fails"""
    
    def __init__(self, message: str = "Hardware detection failed", details: Optional[str] = None):
        super().__init__(message, details)


class ConfigurationError(CameraError):
    """Raised when camera configuration is invalid"""
    
    def __init__(self, message: str = "Invalid camera configuration", details: Optional[str] = None):
        super().__init__(message, details)


class NetworkPerformanceError(CameraError):
    """Raised when network performance monitoring fails"""
    
    def __init__(self, message: str = "Network performance monitoring failed", details: Optional[str] = None):
        super().__init__(message, details)


def handle_camera_error(func):
    """
    Decorator to handle camera errors gracefully
    
    Converts common exceptions into appropriate CameraError subclasses
    with helpful error messages for debugging.
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ImportError as e:
            if "picamera2" in str(e).lower():
                raise CameraInitializationError(
                    "Picamera2 library not available",
                    f"Import error: {str(e)}"
                )
            raise CameraError("Required library not available", str(e))
        except PermissionError as e:
            raise CameraInitializationError(
                "Camera access denied",
                "Check if another process is using the camera or if permissions are correct"
            )
        except FileNotFoundError as e:
            if "video" in str(e).lower() or "camera" in str(e).lower():
                raise CameraInitializationError(
                    "Camera device not found",
                    "Check if camera is properly connected and enabled"
                )
            raise CameraError("File not found", str(e))
        except Exception as e:
            # Re-raise if it's already a CameraError
            if isinstance(e, CameraError):
                raise
            # Convert other exceptions
            raise CameraError(f"Unexpected error in {func.__name__}", str(e))
    
    return wrapper
