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

from src.config import get_config, print_config
from src.camera import Camera

# Display Python version information
import sys
print(f"🐍 Running on Python {sys.version.split()[0]} ({sys.implementation.name})")
print(f"📍 Python executable: {sys.executable}")

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
            "h264_bitrate": config.h264_bitrate
        }
    }


@app.get("/api/camera/metrics")
async def get_camera_metrics():
    """
    Get real-time camera and stream metrics.
    
    Returns actual measured values for resolution, configured FPS,
    quality settings, and stream status for both MJPEG and H.264 streams.
    
    Returns:
        dict: Real metrics including:
            - resolution: Actual stream dimensions
            - target_fps: Configured frame rate
            - stream_active: Whether MJPEG streaming is currently active
            - h264_stream_active: Whether H.264 streaming is currently active
            - encoder_type: Current encoder type for MJPEG stream
            - streaming_mode: "h264" if H.264 enabled, "mjpeg" if fallback
            - timestamp: Current server timestamp
    """
    if not camera:
        return {
            "error": "Camera not available",
            "h264_stream_active": False,
            "timestamp": datetime.now().isoformat()
        }
    
    metrics = {
        "resolution": {
            "width": config.stream_width,
            "height": config.stream_height
        },
        "target_fps": config.stream_fps,
        "h264_stream_active": camera.is_h264_streaming() if hasattr(camera, 'is_h264_streaming') else False,
        "camera_available": camera.is_available(),
        "streaming_mode": "h264",
        "h264_bitrate": config.h264_bitrate,
        "mediamtx_ports": {
            "webrtc": config.mediamtx_webrtc_port,
            "hls": config.mediamtx_hls_port,
            "udp": config.mediamtx_udp_port
        },
        "timestamp": datetime.now().isoformat()
    }
    
    return metrics


@app.get("/api/camera/stream")
async def video_stream():
    """
    H.264 video streaming endpoint via MediaMTX.
    
    Provides efficient H.264 streaming with WebRTC/HLS distribution.
    Uses hardware encoding for optimal performance on Raspberry Pi.
    
    Returns:
        dict: Stream information with available protocols
        
    Raises:
        HTTPException: If camera is not available or streaming fails to start
    """
    if not camera:
        raise HTTPException(status_code=503, detail="Camera not available")
    
    if not camera.is_available():
        raise HTTPException(status_code=503, detail="Camera hardware not detected")
    
    try:
        if not camera.start_h264_streaming():
            raise HTTPException(status_code=500, detail="Failed to start H.264 streaming to MediaMTX")
        
        # Return information about available streams
        return {
            "streaming_mode": "h264",
            "streams": {
                "webrtc": f"/api/mediamtx/webrtc",
                "hls": f"/api/mediamtx/hls",
                "rtsp": f"rtsp://{config.host}:8554/cam"
            },
            "message": "H.264 streaming active via MediaMTX"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Streaming error: {str(e)}")


@app.get("/api/camera/stream/info")
async def stream_info():
    """
    Get information about available H.264 streaming endpoints and current status.
    
    Returns:
        dict: Stream information including available protocols and URLs
    """
    if not camera or not camera.is_available():
        return {
            "camera_available": False,
            "streams": {},
            "message": "Camera not available"
        }
    
    return {
        "camera_available": True,
        "streaming_mode": "h264",
        "streams": {
            "h264": {
                "webrtc": f"http://{config.host}:{config.mediamtx_webrtc_port}/cam/whep",
                "hls": f"http://{config.host}:{config.mediamtx_hls_port}/cam/index.m3u8",
                "rtsp": f"rtsp://{config.host}:8554/cam"
            }
        }
    }


@app.get("/api/mediamtx/webrtc")
async def mediamtx_webrtc_proxy():
    """Proxy WebRTC requests to MediaMTX for domain compatibility."""
    return RedirectResponse(url=f"http://localhost:{config.mediamtx_webrtc_port}/cam/whep")


@app.get("/api/mediamtx/hls")
async def mediamtx_hls_proxy():
    """Proxy HLS requests to MediaMTX for domain compatibility."""
    return RedirectResponse(url=f"http://localhost:{config.mediamtx_hls_port}/cam/index.m3u8")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info"
    )