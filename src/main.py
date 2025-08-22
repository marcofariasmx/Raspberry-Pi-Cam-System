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
import httpx

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, Response
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
    
    Since MediaMTX manages the camera directly, we just check MediaMTX availability
    instead of initializing camera hardware directly.
    """
    global camera
    
    print("🚀 Starting Pi Camera Streaming App...")
    print("📹 Using MediaMTX for camera management (no direct camera initialization)")
    
    # Set camera to None since MediaMTX handles it
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
    
    MediaMTX manages the camera directly via rpiCamera source.
    This endpoint just returns information about available stream protocols.
    
    Returns:
        dict: Stream information with available protocols
    """
    # Check if MediaMTX camera is available via API
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:9997/v3/paths/list")
            paths = response.json()
            
            # Find cam path and check if ready
            cam_ready = False
            for item in paths.get("items", []):
                if item["name"] == "cam" and item["ready"]:
                    cam_ready = True
                    break
            
            if not cam_ready:
                raise HTTPException(status_code=503, detail="MediaMTX camera not ready")
        
        print("🎬 MediaMTX camera stream available")
        
        # Return information about available streams
        return {
            "streaming_mode": "h264",
            "streams": {
                "webrtc": f"/api/mediamtx/webrtc",
                "hls": f"/api/mediamtx/hls",
                "rtsp": f"rtsp://{config.host}:8554/cam"
            },
            "message": "H.264 streaming available via MediaMTX rpiCamera source"
        }
        
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="MediaMTX not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Streaming error: {str(e)}")


@app.get("/api/camera/stream/info")
async def stream_info():
    """
    Get information about available H.264 streaming endpoints via MediaMTX.
    
    Returns:
        dict: Stream information including available protocols and URLs
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:9997/v3/paths/list")
            paths = response.json()
            
            # Find cam path and check if ready
            cam_ready = False
            for item in paths.get("items", []):
                if item["name"] == "cam":
                    cam_ready = item["ready"]
                    break
        
        return {
            "camera_available": cam_ready,
            "streaming_mode": "h264",
            "streams": {
                "h264": {
                    "webrtc": f"/api/mediamtx/webrtc",
                    "hls": f"/api/mediamtx/hls", 
                    "rtsp": f"rtsp://{config.host}:8554/cam"
                }
            } if cam_ready else {}
        }
        
    except httpx.RequestError:
        return {
            "camera_available": False,
            "streams": {},
            "message": "MediaMTX not available"
        }


@app.api_route("/api/mediamtx/webrtc", methods=["GET", "POST", "PATCH", "DELETE"])
async def mediamtx_webrtc_proxy(request: Request):
    """Proxy WebRTC requests to MediaMTX for domain compatibility."""
    target_url = f"http://localhost:{config.mediamtx_webrtc_port}/cam/whep"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Forward the request to MediaMTX
        response = await client.request(
            method=request.method,
            url=target_url,
            headers=dict(request.headers),
            content=await request.body(),
            follow_redirects=True
        )
        
        # Return the response from MediaMTX
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers)
        )


@app.get("/api/mediamtx/hls")
@app.get("/api/mediamtx/hls/{path:path}")
async def mediamtx_hls_proxy(path: str = "index.m3u8"):
    """Proxy HLS requests to MediaMTX for domain compatibility."""
    target_url = f"http://localhost:{config.mediamtx_hls_port}/cam/{path}"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(target_url, follow_redirects=True)
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers)
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info"
    )