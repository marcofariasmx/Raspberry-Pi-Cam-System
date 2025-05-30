"""
Raspberry Pi Camera Web Application
FastAPI-based web app for camera streaming and photo capture with secure access
"""

import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import get_config, AppConfig
from camera_manager import CameraManager

# Initialize configuration
config = get_config()
config.print_summary()

# Initialize FastAPI app
app = FastAPI(
    title="Raspberry Pi Camera Web App",
    description="Secure camera streaming and photo capture system",
    version="2.0.0"
)

# Security scheme
security = HTTPBearer()

# Initialize camera manager
camera_manager: Optional[CameraManager] = None

# Templates and static files (will be created during setup)
# Lazy initialization for templates (performance optimization)
templates = None

def get_templates():
    """Lazy load templates"""
    global templates
    if templates is None:
        templates = Jinja2Templates(directory="src/templates")
    return templates

# Ensure static and photos directories exist
# Conditionally create static directory based on resource mode
if not config.low_resource_mode:
    os.makedirs("static", exist_ok=True)
os.makedirs(config.photos_dir, exist_ok=True)

# Mount static files
# Conditionally mount static files based on resource mode
if not config.low_resource_mode:
    app.mount("/static", StaticFiles(directory="static"), name="static")
else:
    print("⚡ Low resource mode: Static files mounting deferred")


def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify API key from Authorization header"""
    if credentials.credentials != config.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return credentials.credentials


def verify_token_param(token: str = Query(...)):
    """Verify API key from query parameter (for streaming endpoints)"""
    if token != config.api_key:
        raise HTTPException(status_code=403, detail="Invalid token")
    return token


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    global camera_manager
    
    print("🚀 Starting Raspberry Pi Camera Web App...")
    print(f"🔑 API Key configured: {config.api_key[:8]}...")
    print(f"🔒 Web Password configured: {'*' * len(config.web_password)}")
    
    # Initialize camera manager
    try:
        camera_manager = CameraManager(config)
        if config.low_resource_mode:
            print("⚡ Low resource mode: Camera initialization deferred until first use")
        elif camera_manager.init_camera():
            print("📷 Camera ready!")
        else:
            print("⚠️  Camera initialization failed - some features may not work")
    except Exception as e:
        print(f"❌ Camera manager initialization failed: {e}")
        # Continue without camera for debugging
    
    print(f"🌐 Server will start on {config.host}:{config.port}")
    print("✅ Application startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    print("🛑 Shutting down application...")
    if camera_manager:
        camera_manager.cleanup()
    print("✅ Shutdown complete")


# Public endpoints (no authentication required)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve main web interface"""
    return get_templates().TemplateResponse("index.html", {
        "request": request,
        "api_key": config.api_key
    })


@app.post("/api/auth/login")
async def web_login(request: Request):
    """Authenticate with web password and return API key"""
    try:
        data = await request.json()
        password = data.get("password", "")
        
        if password == config.web_password:
            return {
                "status": "success",
                "api_key": config.api_key,
                "message": "Login successful"
            }
        else:
            raise HTTPException(status_code=401, detail="Invalid password")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid request format")


@app.get("/health")
async def health_check():
    """Public health check endpoint"""
    return {
        "status": "healthy",
        "service": "raspberry-pi-camera-web-app",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "camera_available": camera_manager is not None and camera_manager.camera_device is not None
    }


# Protected API endpoints (require API key authentication)

@app.get("/api/camera/status")
async def camera_status(api_key: str = Depends(verify_api_key)):
    """Get camera status and capabilities"""
    if not camera_manager:
        return {
            "status": "unavailable",
            "error": "Camera manager not initialized",
            "timestamp": datetime.now().isoformat()
        }
    
    status = camera_manager.get_status()
    status.update({
        "timestamp": datetime.now().isoformat(),
        "library": "picamera2"
    })
    
    return status


@app.get("/api/camera/capture")
async def capture_photo(api_key: str = Depends(verify_api_key)):
    """Capture high-resolution photo"""
    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera manager not available")
    
    try:
        success, message, filename = camera_manager.capture_photo()
        
        if success:
            # Get file info
            filepath = os.path.join(config.photos_dir, filename)
            file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
            
            return {
                "status": "success",
                "message": message,
                "filename": filename,
                "filepath": filepath,
                "size": file_size,
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail=message)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.get("/api/camera/stream")
async def video_stream(token: str = Depends(verify_token_param)):
    """MJPEG video stream endpoint"""
    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera manager not available")
    
    try:
        # Setup streaming if not already active
        if not camera_manager.is_streaming:
            if not camera_manager.setup_streaming():
                raise HTTPException(status_code=500, detail="Failed to setup video streaming")
        
        # Return streaming response
        return StreamingResponse(
            camera_manager.generate_frames(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Streaming failed: {str(e)}")


@app.post("/api/camera/stream/stop")
async def stop_stream(api_key: str = Depends(verify_api_key)):
    """Stop video streaming"""
    if not camera_manager:
        return {"status": "success", "message": "No camera manager available"}
    
    try:
        success = camera_manager.stop_streaming()
        return {
            "status": "success" if success else "error",
            "message": "Stream stopped" if success else "Failed to stop stream",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error stopping stream: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@app.get("/api/photos")
async def list_photos(api_key: str = Depends(verify_api_key)):
    """List all captured photos with metadata"""
    try:
        photos = []
        
        if os.path.exists(config.photos_dir):
            for filename in os.listdir(config.photos_dir):
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    filepath = os.path.join(config.photos_dir, filename)
                    
                    if os.path.exists(filepath):
                        stat = os.stat(filepath)
                        photos.append({
                            "filename": filename,
                            "size": stat.st_size,
                            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "url": f"/{config.photos_dir}/{filename}"
                        })
        
        # Sort by creation time (newest first)
        photos.sort(key=lambda x: x["created"], reverse=True)
        
        # Apply max photos limit if configured
        if config.max_photos > 0:
            photos = photos[:config.max_photos]
        
        return {
            "status": "success",
            "count": len(photos),
            "photos": photos,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list photos: {str(e)}")


@app.delete("/api/photos/{filename}")
async def delete_photo(filename: str, api_key: str = Depends(verify_api_key)):
    """Delete a specific photo"""
    try:
        # Validate filename (security check)
        if not filename or '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        filepath = os.path.join(config.photos_dir, filename)
        
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Photo not found")
        
        os.remove(filepath)
        
        return {
            "status": "success",
            "message": f"Photo {filename} deleted successfully",
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete photo: {str(e)}")


# Photo serving endpoint
@app.get(f"/{config.photos_dir}/{{filename}}")
async def serve_photo(filename: str):
    """Serve captured photos (public access for simplicity)"""
    # Basic security check
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    filepath = os.path.join(config.photos_dir, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Photo not found")
    
    return FileResponse(filepath)


# Configuration endpoint (for debugging)
@app.get("/api/config")
async def get_app_config(api_key: str = Depends(verify_api_key)):
    """Get current application configuration (sensitive data masked)"""
    return {
        "camera": {
            "auto_detect": config.camera_auto_detect,
            "fallback_resolution": f"{config.camera_fallback_width}x{config.camera_fallback_height}",
            "stream_resolution": f"{config.stream_width}x{config.stream_height}",
            "transforms": {
                "hflip": config.camera_hflip,
                "vflip": config.camera_vflip
            }
        },
        "server": {
            "host": config.host,
            "port": config.port,
            "debug": config.debug
        },
        "photos": {
            "directory": config.photos_dir,
            "max_photos": config.max_photos
        },
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        debug=config.debug
    )
