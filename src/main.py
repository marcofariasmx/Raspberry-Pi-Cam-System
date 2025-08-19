"""
Raspberry Pi Camera Streaming Web Application

A FastAPI-based web server that provides live camera streaming from Raspberry Pi
camera modules. This application offers a simple web interface for viewing live
camera feeds with configurable streaming parameters.

Key Features:
- Live MJPEG video streaming via HTTP
- Web-based interface for stream viewing
- RESTful API endpoints for system status
- Configurable stream resolution, framerate, and quality
- Development mode support for testing without hardware
- Automatic camera detection and initialization

The application provides both a web interface for users and API endpoints
for integration with other systems or monitoring tools.

Endpoints:
- GET / : Web interface for viewing camera stream
- GET /health : System health and status information
- GET /api/camera/stream : MJPEG video stream endpoint

The server automatically detects available camera hardware and falls back
to development mode when running without camera modules for testing purposes.
"""

import os
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from config import get_config, print_config
from camera import Camera

# Initialize configuration with environment overrides
config = get_config()
print_config(config)

# Initialize FastAPI application with metadata
app = FastAPI(
    title="Pi Camera Stream",
    description="Raspberry Pi camera streaming web application",
    version="1.0.0"
)

# Initialize global components
camera: Camera = None
templates = Jinja2Templates(directory="src/templates")

# Mount static files
app.mount("/static", StaticFiles(directory="src/static"), name="static")


@app.on_event("startup")
async def startup_event():
    """
    Application startup event handler.
    
    Initializes the camera system when the web server starts up.
    This includes camera hardware detection, configuration validation,
    and preparation for streaming operations.
    
    The startup process logs the initialization status and reports
    any issues with camera hardware availability.
    """
    global camera
    
    print("🚀 Starting Pi Camera Streaming App...")
    
    try:
        camera = Camera(config)
        if camera.is_available():
            print("✅ Camera ready for streaming")
        else:
            print("⚠️  Camera not available - check hardware connection")
    except Exception as e:
        print(f"❌ Camera initialization failed: {e}")
        camera = None
    
    print(f"🌐 Server starting on {config.host}:{config.port}")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Application shutdown event handler.
    
    Performs cleanup operations when the web server is shutting down.
    This includes stopping camera operations, releasing hardware resources,
    and ensuring graceful application termination.
    """
    print("🛑 Shutting down...")
    
    if camera:
        camera.cleanup()
    
    print("✅ Shutdown complete")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """
    Serve the main web interface for camera streaming.
    
    Returns an HTML page that displays the live camera stream along with
    system information and configuration details. The interface is designed
    to be simple and responsive for viewing on various devices.
    
    Args:
        request: FastAPI request object for template context
        
    Returns:
        HTMLResponse: Rendered HTML page with embedded stream viewer
    """
    return templates.TemplateResponse("index.html", {
        "request": request,
        "config": config
    })


@app.get("/health")
@app.head("/health")
async def health_check():
    """
    System health and status endpoint.
    
    Provides information about the application status, camera availability,
    and current configuration. This endpoint is useful for monitoring
    systems and automated health checks.
    
    Returns:
        dict: JSON object containing:
            - status: Overall system status ("healthy")
            - service: Service name identifier
            - timestamp: Current timestamp in ISO format
            - camera_available: Boolean indicating camera hardware status
            - stream_config: Current streaming configuration details
    """
    return {
        "status": "healthy",
        "service": "pi-camera-stream",
        "timestamp": datetime.now().isoformat(),
        "camera_available": camera.is_available() if camera else False,
        "stream_config": {
            "resolution": f"{config.stream_width}x{config.stream_height}",
            "fps": config.stream_fps,
            "quality": config.jpeg_quality
        }
    }


@app.get("/api/camera/metrics")
async def get_camera_metrics():
    """
    Get real-time camera and stream metrics.
    
    Returns actual measured values for resolution, configured FPS,
    JPEG quality, and stream status. No estimations.
    
    Returns:
        dict: Real metrics including:
            - resolution: Actual stream dimensions
            - target_fps: Configured frame rate
            - jpeg_quality: Configured JPEG quality percentage
            - stream_active: Whether streaming is currently active
            - timestamp: Current server timestamp
    """
    if not camera:
        return {
            "error": "Camera not available",
            "stream_active": False,
            "timestamp": datetime.now().isoformat()
        }
    
    return {
        "resolution": {
            "width": config.stream_width,
            "height": config.stream_height
        },
        "target_fps": config.stream_fps,
        "jpeg_quality": config.jpeg_quality,
        "stream_active": camera.is_streaming() if hasattr(camera, 'is_streaming') else False,
        "camera_available": camera.is_available(),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/camera/stream")
async def video_stream():
    """
    MJPEG video streaming endpoint.
    
    Provides a continuous MJPEG video stream from the camera hardware.
    The stream is formatted for direct consumption by web browsers and
    media players that support MJPEG over HTTP.
    
    Stream characteristics:
    - Format: Motion JPEG (MJPEG)
    - Resolution: Configured via stream_width/stream_height settings
    - Framerate: Configured via stream_fps setting
    - Quality: Configured via jpeg_quality setting
    - Content-Type: multipart/x-mixed-replace with frame boundaries
    
    The endpoint automatically starts camera streaming if not already active
    and handles camera errors gracefully.
    
    Returns:
        StreamingResponse: HTTP streaming response with MJPEG video data
        
    Raises:
        HTTPException: If camera is not available or streaming fails to start
    """
    if not camera:
        raise HTTPException(status_code=503, detail="Camera not available")
    
    if not camera.is_available():
        raise HTTPException(status_code=503, detail="Camera hardware not detected")
    
    try:
        # Start streaming
        if not camera.start_streaming():
            raise HTTPException(status_code=500, detail="Failed to start camera streaming")
        
        # Return streaming response
        return StreamingResponse(
            camera.generate_frames(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Streaming error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info"
    )