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

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json
import logging
import socket
import weakref

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

# Simple WebSocket connection management
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.use_tornado = False  # Flag to enable high-performance Tornado WebSocket
    
    @property
    def connection_count(self) -> int:
        """Get current connection count for health endpoint compatibility."""
        if self.use_tornado:
            try:
                from src.tornado_websocket import get_client_count
                return get_client_count()
            except ImportError:
                return 0
        return len(self.active_connections)
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"🔌 WebSocket connected. Active connections: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"🔌 WebSocket disconnected. Active connections: {len(self.active_connections)}")
    
    async def broadcast_binary(self, data: bytes):
        if not self.active_connections:
            return
        
        # Send to all clients, remove any that fail
        disconnected = []
        for connection in self.active_connections[:]:
            try:
                await connection.send_bytes(data)
            except Exception:
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            await self.disconnect(conn)
    
    async def broadcast_text(self, data: str):
        if not self.active_connections:
            return
        
        # Send to all clients, remove any that fail
        disconnected = []
        for connection in self.active_connections[:]:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            await self.disconnect(conn)

manager = ConnectionManager()

# Mount static files
app.mount("/static", StaticFiles(directory="src/static"), name="static")

# Middleware for Cloudflare proxy compatibility
@app.middleware("http")
async def cloudflare_proxy_middleware(request: Request, call_next):
    """Handle Cloudflare proxy headers and WebSocket upgrades."""
    # Extract real client IP for logging
    real_ip = request.headers.get("CF-Connecting-IP") or \
              request.headers.get("X-Forwarded-For") or \
              request.headers.get("X-Real-IP") or \
              (request.client.host if request.client else "unknown")
    
    request.state.real_ip = real_ip
    
    # Process the request
    response = await call_next(request)
    
    # Add CORS headers if needed
    if request.method == "OPTIONS":
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
    
    # Ensure WebSocket connections work through proxy
    if "websocket" in request.headers.get("upgrade", "").lower():
        response.headers["Connection"] = "upgrade"
        response.headers["Upgrade"] = "websocket"
    
    return response


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
    
    Initializes picamera2 for WebCodecs H.264 streaming via WebSocket.
    """
    global camera
    
    print("🚀 Starting Pi Camera WebCodecs Streaming App...")
    print("📹 Using picamera2 with WebSocket H.264 streaming for WebCodecs")
    
    try:
        # Initialize camera with optimized settings
        camera = Camera(config)
        if camera.is_available():
            print("✅ Camera initialized and ready for WebSocket streaming")

            # Auto-start simple WebSocket H.264 streaming
            print("🎬 Auto-starting simple WebSocket H.264 streaming...")
            if camera.start_websocket_h264_streaming(manager):
                print("✅ Simple WebSocket H.264 streaming auto-started successfully")
                print("🌐 WebCodecs clients can now connect to /ws endpoint")
            else:
                print("⚠️  Failed to auto-start WebSocket H.264 streaming")
        else:
            print("⚠️  Camera not available - check hardware connection")
    except Exception as e:
        print(f"❌ Camera initialization failed: {e}")
        camera = None
    
    print(f"🌐 Server starting on {config.host}:{config.port}")
    print("📺 Visit the web interface to view the WebCodecs stream")


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


@app.websocket("/ws")
async def websocket_h264_stream(websocket: WebSocket):
    """
    WebSocket endpoint for raw H.264 streaming.
    
    Provides direct H.264 stream data to WebCodecs-capable browsers.
    Each WebSocket message contains one complete H.264 access unit (frame).
    """
    # Log client connection 
    client_ip = 'websocket-client'  # We can't get real IP in websocket handler easily
    print(f"🔌 WebSocket connection established")
    
    await manager.connect(websocket)
    
    try:
        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for ping/control messages from client with shorter timeout
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                
                # Handle client control messages
                try:
                    parsed = json.loads(message)
                    if parsed.get("type") == "pong":
                        # Client responded to our keepalive
                        pass
                except (json.JSONDecodeError, KeyError):
                    # Not a valid control message, ignore
                    pass
                    
            except asyncio.TimeoutError:
                # Send keepalive to client
                try:
                    await websocket.send_text('{"type":"keepalive"}')
                except Exception:
                    # Connection likely closed
                    break
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"⚠️ WebSocket error: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"⚠️ WebSocket handler error: {e}")
    finally:
        await manager.disconnect(websocket)
        print(f"🔌 WebSocket disconnected")

@app.get("/health")
@app.head("/health")
async def health_check():
    """
    System health and status endpoint for Cloudflare proxying.
    """
    return {
        "status": "healthy",
        "service": "pi-camera-webcodecs-stream",
        "timestamp": datetime.now().isoformat(),
        "camera_available": camera.is_available() if camera else False,
        "websocket_connections": manager.connection_count,
        "stream_config": {
            "resolution": f"{config.stream_width}x{config.stream_height}",
            "fps": config.stream_fps,
            "h264_bitrate": config.h264_bitrate,
            "streaming_protocol": "websocket_webcodecs"
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


@app.get("/api/stream/info")
async def stream_info():
    """
    Get stream metadata for WebCodecs client initialization.
    
    Returns:
        dict: Stream information including resolution, fps, codec details
    """
    if not camera or not camera.is_available():
        return {
            "camera_available": False,
            "streaming_protocol": "websocket_webcodecs",
            "error": "Camera not available"
        }
    
    return {
        "camera_available": True,
        "streaming_protocol": "websocket_webcodecs",
        "websocket_endpoint": "/ws",
        "resolution": {
            "width": config.stream_width,
            "height": config.stream_height
        },
        "fps": config.stream_fps,
        "codec": {
            "name": "h264",
            "profile": "high",
            "level": "3.1",
            "bitrate": config.h264_bitrate
        },
        "websocket_info": {
            "buffer_size": config.websocket_buffer_size,
            "max_viewers": config.max_concurrent_viewers,
            "current_connections": manager.connection_count
        },
        "h264_streaming": camera.is_h264_streaming() if hasattr(camera, 'is_h264_streaming') else False
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
    import os
    
    # Check if we should use high-performance Tornado WebSocket
    USE_TORNADO = os.getenv("USE_TORNADO", "true").lower() == "true"
    
    if USE_TORNADO:
        print("🚀 Starting with high-performance Tornado WebSocket server...")
        try:
            from src.tornado_websocket import start_tornado_server
            tornado_port = int(os.getenv("TORNADO_PORT", "8001"))
            
            if start_tornado_server(tornado_port):
                manager.use_tornado = True
                print(f"✅ Tornado WebSocket server started on port {tornado_port}")
                print(f"🌐 WebSocket endpoint: ws://localhost:{tornado_port}/ws")
            else:
                print("❌ Failed to start Tornado server, falling back to FastAPI WebSocket")
        except ImportError as e:
            print(f"⚠️ Tornado not available: {e}")
            print("💡 Install tornado: pip install tornado")
    else:
        print("📡 Using FastAPI WebSocket (set USE_TORNADO=true for better performance)")
    
    # TCP optimizations for low-latency streaming
    uvicorn_config = uvicorn.Config(
        app,
        host=config.host,
        port=config.port,
        log_level="info",
        loop="uvloop",  # Use uvloop for better performance
        ws_ping_interval=20,  # WebSocket ping interval
        ws_ping_timeout=10,   # WebSocket ping timeout
        access_log=True,
        # Enable TCP optimizations
        backlog=2048,
    )
    
    server = uvicorn.Server(uvicorn_config)
    
    # Apply TCP socket optimizations
    try:
        original_create_server = server.create_server
        def optimized_create_server():
            sock = original_create_server()
            if hasattr(socket, 'TCP_NODELAY'):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            if hasattr(socket, 'SO_SNDBUF'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            if hasattr(socket, 'SO_RCVBUF'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            return sock
        server.create_server = optimized_create_server
    except Exception as e:
        print(f"⚠️ Could not apply TCP optimizations: {e}")
    
    print("🚀 Starting WebCodecs streaming server with TCP optimizations...")
    server.run()