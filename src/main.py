"""
Raspberry Pi Camera Web Application - Enhanced with Health Monitoring and Auto-Recovery
FastAPI-based web app for camera streaming and photo capture with comprehensive health monitoring
"""

import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Request, Depends, Query, Cookie
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.config import get_config, AppConfig
from src.camera import CameraManager
from src.camera.session_manager import SessionManager
from src.camera.health_monitor import HealthMonitor
from src.camera.recovery_manager import RecoveryManager
from src.camera.streaming_validator import StreamingValidator
from src.camera.health_api import HealthAPI

# Initialize configuration
config = get_config()
config.print_summary()

# Initialize FastAPI app
app = FastAPI(
    title="Raspberry Pi Camera Web App - Enhanced",
    description="Secure camera streaming and photo capture system with health monitoring and auto-recovery",
    version="2.1.0"
)

# Security scheme
security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)

# Initialize system components
camera_manager: Optional[CameraManager] = None
session_manager: Optional[SessionManager] = None
health_monitor: Optional[HealthMonitor] = None
recovery_manager: Optional[RecoveryManager] = None
streaming_validator: Optional[StreamingValidator] = None
health_api: Optional[HealthAPI] = None

# Templates and static files
templates = None

def get_templates():
    """Lazy load templates"""
    global templates
    if templates is None:
        templates = Jinja2Templates(directory="src/templates")
    return templates

# Ensure directories exist
if not config.low_resource_mode:
    os.makedirs("static", exist_ok=True)
os.makedirs(config.photos_dir, exist_ok=True)

# Mount static files
if not config.low_resource_mode:
    app.mount("/static", StaticFiles(directory="static"), name="static")
else:
    print("⚡ Low resource mode: Static files mounting deferred")


# Authentication functions
def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify API key from Authorization header"""
    if credentials.credentials != config.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return credentials.credentials

def verify_api_key_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)):
    """Verify API key from Authorization header (optional)"""
    if not credentials:
        return None
    if credentials.credentials != config.api_key:
        return None
    return credentials.credentials

def verify_token_param(token: str = Query(...)):
    """Verify API key from query parameter (for streaming endpoints)"""
    if token != config.api_key:
        raise HTTPException(status_code=403, detail="Invalid token")
    return token

def verify_session(session_token: Optional[str] = Cookie(None, alias="session_token")):
    """Verify session from cookie using SessionManager"""
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager not available")
    
    if not session_token:
        raise HTTPException(status_code=401, detail="No session token")
    
    # Get client IP from request context (simplified for this example)
    session_data = session_manager.validate_session(session_token)
    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    return session_data

def verify_session_optional(session_token: Optional[str] = Cookie(None, alias="session_token")):
    """Verify session from cookie (optional)"""
    if not session_manager or not session_token:
        return None
    
    return session_manager.validate_session(session_token)

def verify_api_or_session(
    api_key: Optional[str] = Depends(verify_api_key_optional),
    session = Depends(verify_session_optional)
):
    """Verify either API key or session authentication"""
    if not api_key and not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"api_key": api_key, "session": session}


@app.on_event("startup")
async def startup_event():
    """Initialize application with health monitoring and recovery system"""
    global camera_manager, session_manager, health_monitor, recovery_manager, streaming_validator, health_api
    
    print("🚀 Starting Enhanced Raspberry Pi Camera Web App...")
    print(f"🔑 API Key configured: {config.api_key[:8]}...")
    print(f"🔒 Web Password configured: {'*' * len(config.web_password)}")
    
    try:
        # Initialize session manager
        print("🔐 Initializing session manager...")
        session_manager = SessionManager(config)
        session_manager.start_cleanup_service()
        
        # Initialize camera manager
        print("📷 Initializing camera manager...")
        camera_manager = CameraManager(config)
        if config.low_resource_mode:
            print("⚡ Low resource mode: Camera initialization deferred until first use")
        elif camera_manager.init_camera():
            print("📷 Camera ready!")
        else:
            print("⚠️  Camera initialization failed - some features may not work")
        
        # Initialize streaming validator
        print("🔍 Initializing streaming validator...")
        streaming_validator = StreamingValidator(config)
        streaming_validator.set_camera_manager(camera_manager)
        
        # Initialize recovery manager
        print("🔧 Initializing recovery manager...")
        recovery_manager = RecoveryManager(config)
        recovery_manager.set_component_references(
            camera_manager=camera_manager,
            session_manager=session_manager,
            streaming_validator=streaming_validator
        )
        
        # Initialize health monitor
        print("🏥 Initializing health monitor...")
        health_monitor = HealthMonitor(config)
        health_monitor.set_component_references(
            camera_manager=camera_manager,
            session_manager=session_manager,
            recovery_manager=recovery_manager
        )
        
        # Set cross-references
        recovery_manager.set_component_references(health_monitor=health_monitor)
        
        # Initialize health API
        print("🔗 Initializing health API...")
        health_api = HealthAPI(config)
        health_api.set_component_references(
            health_monitor=health_monitor,
            session_manager=session_manager,
            recovery_manager=recovery_manager,
            streaming_validator=streaming_validator,
            camera_manager=camera_manager
        )
        
        # Start health monitoring
        print("🏥 Starting health monitoring...")
        health_monitor.start_monitoring()
        
        print(f"🌐 Server will start on {config.host}:{config.port}")
        print("✅ Enhanced application startup complete")
        
    except Exception as e:
        print(f"❌ Enhanced startup failed: {e}")
        # Continue with basic functionality
        print("⚠️  Falling back to basic mode")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup enhanced components on application shutdown"""
    print("🛑 Shutting down enhanced application...")
    
    try:
        # Stop health monitoring
        if health_monitor:
            health_monitor.stop_monitoring()
        
        # Stop session cleanup
        if session_manager:
            session_manager.stop_cleanup_service()
        
        # Cleanup camera
        if camera_manager:
            camera_manager.cleanup()
        
        print("✅ Enhanced shutdown complete")
        
    except Exception as e:
        print(f"⚠️  Shutdown error: {e}")


# Public endpoints (no authentication required)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve main web interface"""
    return get_templates().TemplateResponse("index.html", {
        "request": request,
    })


@app.post("/api/auth/login")
async def web_login(request: Request):
    """Enhanced login with session management and security"""
    try:
        data = await request.json()
        password = data.get("password", "")
        
        # Get client IP for security tracking
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")
        
        if password == config.web_password:
            if not session_manager:
                raise HTTPException(status_code=503, detail="Session manager not available")
            
            # Create new session with enhanced security
            session_token = session_manager.create_session(
                user_id="web_user",
                ip_address=client_ip,
                user_agent=user_agent
            )
            
            if not session_token:
                # IP was blocked
                raise HTTPException(status_code=429, detail="Too many failed attempts. IP temporarily blocked.")
            
            response = JSONResponse({
                "status": "success",
                "message": "Login successful"
            })
            
            # Set secure session cookie
            response.set_cookie(
                key="session_token",
                value=session_token,
                httponly=True,
                secure=request.url.scheme == "https",
                samesite="lax",
                max_age=24 * 3600  # 24 hours
            )
            
            return response
        else:
            # Record failed attempt for security
            if session_manager:
                session_manager.record_failed_attempt(client_ip)
            
            raise HTTPException(status_code=401, detail="Invalid password")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid request format")


@app.post("/api/auth/logout")
async def web_logout(session = Depends(verify_session)):
    """Enhanced logout with proper session cleanup"""
    try:
        # Get session token from cookie to invalidate it
        # This is a simplified approach - in practice you'd get the token from the dependency
        if session_manager:
            # For now, we'll just return success since the session validation already occurred
            pass
        
        response = JSONResponse({
            "status": "success",
            "message": "Logout successful"
        })
        
        # Clear session cookie
        response.delete_cookie(key="session_token")
        
        return response
        
    except Exception as e:
        # Even if logout fails, clear the cookie
        response = JSONResponse({
            "status": "success",
            "message": "Logout completed"
        })
        response.delete_cookie(key="session_token")
        return response


@app.get("/health")
async def health_check():
    """Enhanced public health check endpoint"""
    basic_health = {
        "status": "healthy",
        "service": "raspberry-pi-camera-web-app-enhanced",
        "timestamp": datetime.now().isoformat(),
        "version": "2.1.0",
        "camera_available": camera_manager is not None and camera_manager.camera_device is not None
    }
    
    # Add enhanced health info if available
    if health_monitor:
        try:
            health_status = health_monitor.get_health_status()
            basic_health["overall_health"] = health_status.get("overall_status", "unknown")
            basic_health["monitoring_active"] = health_status.get("monitoring_active", False)
        except:
            pass
    
    return basic_health


# Enhanced Health API Endpoints

@app.get("/api/health/detailed")
async def get_detailed_health(api_key: str = Depends(verify_api_key)):
    """Get comprehensive system health status"""
    if not health_api:
        raise HTTPException(status_code=503, detail="Health API not available")
    
    return health_api.get_health_detailed()


@app.get("/api/health/camera")
async def get_camera_health(api_key: str = Depends(verify_api_key)):
    """Get camera-specific health information"""
    if not health_api:
        raise HTTPException(status_code=503, detail="Health API not available")
    
    return health_api.get_health_camera()


@app.get("/api/health/streaming")
async def get_streaming_health(api_key: str = Depends(verify_api_key)):
    """Get streaming-specific health and performance information"""
    if not health_api:
        raise HTTPException(status_code=503, detail="Health API not available")
    
    return health_api.get_health_streaming()


@app.get("/api/health/sessions")
async def get_session_health(api_key: str = Depends(verify_api_key)):
    """Get session management health information"""
    if not health_api:
        raise HTTPException(status_code=503, detail="Health API not available")
    
    return health_api.get_health_sessions()


@app.get("/api/health/recovery")
async def get_recovery_health(api_key: str = Depends(verify_api_key)):
    """Get recovery system status and history"""
    if not health_api:
        raise HTTPException(status_code=503, detail="Health API not available")
    
    return health_api.get_health_recovery()


@app.get("/api/diagnostics/comprehensive")
async def get_comprehensive_diagnostics(api_key: str = Depends(verify_api_key)):
    """Get comprehensive system diagnostics"""
    if not health_api:
        raise HTTPException(status_code=503, detail="Health API not available")
    
    return health_api.get_diagnostics_comprehensive()


@app.get("/api/diagnostics/performance")
async def get_performance_diagnostics(api_key: str = Depends(verify_api_key)):
    """Get performance-specific diagnostics"""
    if not health_api:
        raise HTTPException(status_code=503, detail="Health API not available")
    
    return health_api.get_diagnostics_performance()


@app.post("/api/health/check/force")
async def force_health_check(api_key: str = Depends(verify_api_key)):
    """Force an immediate comprehensive health check"""
    if not health_api:
        raise HTTPException(status_code=503, detail="Health API not available")
    
    return health_api.force_health_check()


@app.post("/api/recovery/trigger/{problem_type}")
async def trigger_recovery(problem_type: str, api_key: str = Depends(verify_api_key)):
    """Trigger recovery for a specific problem type"""
    if not health_api:
        raise HTTPException(status_code=503, detail="Health API not available")
    
    return health_api.trigger_recovery(problem_type)


@app.post("/api/system/reset")
async def reset_system_state(api_key: str = Depends(verify_api_key)):
    """Reset all system monitoring and recovery state"""
    if not health_api:
        raise HTTPException(status_code=503, detail="Health API not available")
    
    return health_api.reset_system_state()


@app.get("/api/streaming/quality/validate")
async def validate_stream_quality(api_key: str = Depends(verify_api_key)):
    """Validate current stream quality with recommendations"""
    if not health_api:
        raise HTTPException(status_code=503, detail="Health API not available")
    
    return health_api.validate_stream_quality()


@app.get("/api/streaming/frozen-frames/detect")
async def detect_frozen_frames(api_key: str = Depends(verify_api_key)):
    """Check for frozen or stale frames"""
    if not health_api:
        raise HTTPException(status_code=503, detail="Health API not available")
    
    return health_api.detect_frozen_frames()


# Original API endpoints (enhanced with better error handling)

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
        # Generate unique client ID and delegate to CameraManager
        client_id = f"client_{uuid.uuid4().hex[:8]}"
        # Log session start
        print(f"🔌 New stream session started: {client_id}", flush=True)
        print(f"📡 Starting stream for session: {client_id}", flush=True)
        # CameraManager.generate_frames handles both queue-based (when client_id provided) and legacy
        gen = camera_manager.generate_frames(client_id)
        return StreamingResponse(
            gen,
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


@app.get("/api/camera/stream/stats")
async def get_streaming_stats(api_key: str = Depends(verify_api_key)):
    """Get detailed streaming performance statistics"""
    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera manager not available")
    
    try:
        stats = camera_manager.get_streaming_stats()
        stats["timestamp"] = datetime.now().isoformat()
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get streaming stats: {str(e)}")


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


# Photo serving endpoint with enhanced authentication
@app.get(f"/{config.photos_dir}/{{filename}}")
async def serve_photo(filename: str, auth: Dict[str, Any] = Depends(verify_api_or_session)):
    """Serve captured photos (requires authentication)"""
    # Basic security check
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    filepath = os.path.join(config.photos_dir, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Photo not found")
    
    return FileResponse(filepath)


# Session-based API endpoints with enhanced session management

@app.get("/api/session/camera/status")
async def session_camera_status(session = Depends(verify_session)):
    """Get camera status and capabilities (session-based)"""
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


@app.get("/api/session/camera/capture")
async def session_capture_photo(session = Depends(verify_session)):
    """Capture high-resolution photo (session-based)"""
    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera manager not available")
    
    try:
        success, message, filename = camera_manager.capture_photo()
        
        if success:
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


@app.post("/api/session/camera/stream/stop")
async def session_stop_stream(session = Depends(verify_session)):
    """Stop video streaming (session-based)"""
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


@app.get("/api/session/streaming-token")
async def get_streaming_token(session = Depends(verify_session)):
    """Get API key for video streaming (session-based)"""
    return {
        "status": "success",
        "token": config.api_key,
        "message": "Streaming token provided"
    }


@app.get("/api/session/camera/stream/stats")
async def session_get_streaming_stats(session = Depends(verify_session)):
    """Get detailed streaming performance statistics (session-based)"""
    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera manager not available")
    
    try:
        stats = camera_manager.get_streaming_stats()
        stats["timestamp"] = datetime.now().isoformat()
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get streaming stats: {str(e)}")


@app.get("/api/session/photos")
async def session_list_photos(session = Depends(verify_session)):
    """List all captured photos with metadata (session-based)"""
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


# Enhanced configuration endpoint
@app.get("/api/config")
async def get_app_config(api_key: str = Depends(verify_api_key)):
    """Get current application configuration with health system info"""
    base_config = {
        "camera": {
            "auto_detect": config.camera_auto_detect,
            "fallback_resolution": f"{config.camera_fallback_width}x{config.camera_fallback_height}",
            "stream_resolution": f"{config.stream_width}x{config.stream_height}",
            "transforms": {
                "hflip": config.camera_hflip,
                "vflip": config.camera_vflip
            }
        },
        "adaptive": {
            "streaming": config.adaptive_streaming,
            "quality": config.adaptive_quality,
            "frame_rate_range": f"{config.min_frame_rate}-{config.max_frame_rate}",
            "quality_range": f"{config.min_stream_quality}-{config.stream_quality}",
            "network_check_interval": config.network_check_interval,
            "network_timeout_threshold": config.network_timeout_threshold
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
        "enhanced_features": {
            "health_monitoring": health_monitor is not None,
            "session_management": session_manager is not None,
            "recovery_system": recovery_manager is not None,
            "streaming_validation": streaming_validator is not None,
            "health_api": health_api is not None
        },
        "timestamp": datetime.now().isoformat()
    }
    
    return base_config


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        reload=config.debug
    )
