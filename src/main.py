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
import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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


async def monitor_stream_readiness():
    """Monitor MediaMTX to detect when H.264 stream becomes ready."""
    max_attempts = 15  # 15 attempts = ~15 seconds max wait
    attempt = 0
    
    while attempt < max_attempts:
        try:
            await asyncio.sleep(1)  # Check every second
            attempt += 1
            
            # Check MediaMTX API for stream readiness
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get("http://localhost:9997/v3/paths/list")
                data = response.json()
                
                # Look for 'cam' path with ready=true
                for item in data.get("items", []):
                    if item.get("name") == "cam" and item.get("ready", False):
                        print(f"🟢 Stream ready! MediaMTX is now receiving H.264 stream (took {attempt} seconds)")
                        print("🌐 WebRTC/HLS endpoints are now available for clients")
                        return
                        
        except Exception as e:
            # Silently continue - MediaMTX might not be ready yet
            pass
    
    print("⚠️  Stream readiness check timed out - stream may still be starting")


@app.on_event("startup")
async def startup_event():
    """
    Application startup event handler.
    
    Initializes picamera2 for full camera control while streaming to MediaMTX.
    """
    global camera
    
    print("🚀 Starting Pi Camera Streaming App...")
    print("📹 Using picamera2 with MediaMTX streaming integration")
    
    try:
        # Initialize camera with optimized settings
        camera = Camera(config)
        if camera.is_available():
            print("✅ Camera initialized and ready for streaming")
            
            # Auto-start H.264 streaming to MediaMTX on startup
            print("🎬 Auto-starting H.264 streaming to MediaMTX...")
            if camera.start_h264_streaming():
                print("✅ H.264 streaming auto-started successfully")
                print("⏳ Stream will be available in MediaMTX within ~5 seconds...")
                
                # Start background task to monitor stream readiness
                asyncio.create_task(monitor_stream_readiness())
            else:
                print("⚠️  Failed to auto-start H.264 streaming")
        else:
            print("⚠️  Camera not available - check hardware connection")
    except Exception as e:
        print(f"❌ Camera initialization failed: {e}")
        print("💡 If MediaMTX is using camera, restart it first")
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
    Start H.264 streaming from picamera2 to MediaMTX.
    
    Uses optimized H.264 encoding with hardware acceleration,
    streaming via UDP to MediaMTX for WebRTC/HLS distribution.
    
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
        # Start optimized H.264 streaming to MediaMTX
        print("🎬 Starting picamera2 H.264 streaming to MediaMTX...")
        if not camera.start_h264_streaming():
            print("❌ Failed to start H.264 streaming")
            raise HTTPException(status_code=500, detail="Failed to start H.264 streaming to MediaMTX")
        
        print("✅ H.264 streaming started successfully")
        
        # Return information about available streams
        return {
            "streaming_mode": "h264",
            "streams": {
                "webrtc": f"/api/mediamtx/webrtc",
                "hls": f"/api/mediamtx/hls",
                "rtsp": f"rtsp://{config.host}:8554/cam"
            },
            "message": "H.264 streaming active: picamera2 → MediaMTX → WebRTC/HLS"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Streaming error: {str(e)}")


@app.get("/api/camera/stream/info")
async def stream_info():
    """
    Get information about picamera2 streaming status and available endpoints.
    
    Returns:
        dict: Stream information including available protocols and URLs
    """
    if not camera or not camera.is_available():
        return {
            "camera_available": False,
            "streams": {},
            "message": "Camera not available"
        }
    
    # Check if H.264 streaming is active
    h264_active = camera.is_h264_streaming() if hasattr(camera, 'is_h264_streaming') else False
    
    return {
        "camera_available": True,
        "h264_streaming": h264_active,
        "streaming_mode": "h264",
        "streams": {
            "h264": {
                "webrtc": f"/api/mediamtx/webrtc",
                "hls": f"/api/mediamtx/hls", 
                "rtsp": f"rtsp://{config.host}:8554/cam"
            }
        } if h264_active else {},
        "message": "picamera2 → MediaMTX → WebRTC/HLS pipeline"
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


class CameraSettings(BaseModel):
    """Camera settings model for API requests."""
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[int] = None
    bitrate: Optional[int] = None

@app.post("/api/camera/controls")
async def update_camera_settings(settings: CameraSettings):
    """
    Update all camera settings in one request (picamera2 advantage!).
    
    Only updates the provided parameters. Example:
    - {"fps": 30} - Only change FPS
    - {"width": 1640, "height": 1232, "bitrate": 3000000} - Change resolution and bitrate
    - {"fps": 30, "width": 1640, "height": 1232, "bitrate": 3000000} - Change everything
    """
    if not camera or not camera.is_available():
        raise HTTPException(status_code=503, detail="Camera not available")
    
    try:
        # Track what's being changed
        changes = []
        
        # Stop current streaming
        camera.stop_h264_streaming()
        
        # Update provided settings
        if settings.width is not None and settings.height is not None:
            config.stream_width = settings.width
            config.stream_height = settings.height
            changes.append(f"resolution to {settings.width}x{settings.height}")
        elif settings.width is not None or settings.height is not None:
            raise HTTPException(status_code=400, detail="Both width and height must be provided together")
        
        if settings.fps is not None:
            config.stream_fps = settings.fps
            changes.append(f"FPS to {settings.fps}")
            
        if settings.bitrate is not None:
            config.h264_bitrate = settings.bitrate
            changes.append(f"bitrate to {settings.bitrate//1000000}Mbps")
        
        if not changes:
            raise HTTPException(status_code=400, detail="No settings provided to update")
        
        # Restart with new settings
        camera.start_h264_streaming()
        
        return {
            "message": f"Updated {', '.join(changes)}",
            "current_settings": {
                "resolution": f"{config.stream_width}x{config.stream_height}",
                "fps": config.stream_fps,
                "bitrate_mbps": config.h264_bitrate // 1000000
            },
            "restart_required": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update camera settings: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info"
    )