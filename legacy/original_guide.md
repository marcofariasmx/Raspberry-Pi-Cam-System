# Complete Raspberry Pi Camera Web App Guide (FIXED)

## 📋 Overview

This guide provides a complete, step-by-step process to set up a modern camera web application on Raspberry Pi using **Picamera2** and **FastAPI**, accessible worldwide through **Cloudflare Tunnel**. Everything runs automatically on boot using **tmux sessions** for easy debugging.

## 🎯 What You'll Get

- ✅ Modern camera web app with live streaming and photo capture
- ✅ Secure web interface with password protection
- ✅ Accessible from anywhere via HTTPS (Cloudflare Tunnel)
- ✅ Auto-start services on boot (FIXED!)
- ✅ Easy log access via tmux sessions
- ✅ Universal setup (works with any username)

## 📦 Prerequisites

### Hardware
- Raspberry Pi (any model) with Raspberry Pi OS
- Raspberry Pi Camera Module (V1, V2, V3, or HQ)
- Internet connection

### Software
- Raspberry Pi OS (Bullseye or later)
- Cloudflare account with a domain
- SSH access to your Pi

## 🚀 Part 1: System Setup

### Step 1: Update Your Raspberry Pi

```bash
# Update package lists and system
sudo apt update && sudo apt upgrade -y

# Reboot to ensure all updates are applied
sudo reboot
```

### Step 2: Install System Dependencies

```bash
# Update package lists
sudo apt update

# Install ALL required packages including tmux (ESSENTIAL!)
sudo apt install -y python3-picamera2 python3-opencv python3-venv git tmux

# Verify installations
echo "Checking installations..."
tmux -V
git --version
python3 --version
libcamera-hello --version 2>/dev/null || echo "Camera tools installed"
echo "✅ All dependencies installed successfully"
```

**IMPORTANT**: `tmux` is **critical** for this setup. The systemd service creates a tmux session to run the camera app.

### Step 3: Test Camera

```bash
# Test camera with libcamera (should show 5-second preview)
libcamera-hello -t 5000

# If this works, your camera is properly connected
```

## 🐍 Part 2: Python Environment Setup

### Step 1: Create Project Directory

```bash
# Create project directory (works with any username)
mkdir -p ~/cloudflare-apps/camera-app
cd ~/cloudflare-apps/camera-app
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment with system packages access
python3 -m venv venv --system-site-packages

# Activate virtual environment
source venv/bin/activate

# Verify picamera2 is available
python3 -c "import picamera2; print('✅ Picamera2 is available')"
```

### Step 3: Install Python Dependencies

```bash
# Install FastAPI and related packages
pip install fastapi uvicorn python-multipart jinja2 aiofiles

# Verify installation
python3 -c "import fastapi, picamera2; print('✅ All dependencies available')"

# Create requirements.txt for reproducibility
pip freeze > requirements.txt

# View requirements
echo "Requirements created:"
cat requirements.txt
```

### Step 4: Create Directory Structure

```bash
# Create necessary directories
mkdir -p templates static captured_images

# Your directory structure:
# ~/cloudflare-apps/camera-app/
# ├── venv/
# ├── templates/
# ├── static/
# ├── captured_images/
# ├── main.py (next step)
# ├── templates/index.html (next step)
# └── requirements.txt
```

## 💻 Part 3: Create the Camera Application

### Step 1: Create the FastAPI Application

Create `main.py`:

```python
from fastapi import FastAPI, HTTPException, Request, Depends, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import io
import time
from datetime import datetime
import os
import threading
from typing import Optional
import cv2
import numpy as np

# Import picamera2 - the modern camera library
try:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput
    from libcamera import Transform
    PICAMERA2_AVAILABLE = True
    print("✅ Picamera2 imported successfully")
except ImportError as e:
    print(f"❌ Picamera2 not available: {e}")
    PICAMERA2_AVAILABLE = False

app = FastAPI(title="Modern Camera Web App (Picamera2)", version="2.0.0")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Security configuration
API_KEY = "cam_secure_key_raspberry_pi_monitor"
WEB_LOGIN_PASSWORD = "camera123"  # Change this for production!

# Security scheme
security = HTTPBearer()

def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return credentials.credentials

def verify_token_param(token: str = Query(...)):
    if token != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid token")
    return token

class StreamingOutput(io.BufferedIOBase):
    """Custom output class for MJPEG streaming"""
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

class ModernCameraManager:
    def __init__(self):
        self.picam2 = None
        self.is_streaming = False
        self.streaming_output = None
        self.jpeg_encoder = None
        
    def initialize_camera(self):
        """Initialize Picamera2 for modern Raspberry Pi"""
        if not PICAMERA2_AVAILABLE:
            print("❌ Picamera2 not available - cannot initialize camera")
            return False
            
        try:
            self.picam2 = Picamera2()
            
            # Create configuration for both still images and video streaming
            config = self.picam2.create_video_configuration(
                main={"size": (640, 480), "format": "RGB888"},
                lores={"size": (320, 240), "format": "YUV420"},
                transform=Transform(hflip=True, vflip=True)  # 180 degree rotation
            )
            
            self.picam2.configure(config)
            self.picam2.start()
            
            # Wait for camera to stabilize
            time.sleep(2)
            
            print("✅ Picamera2 initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ Picamera2 initialization error: {e}")
            return False
    
    def capture_frame_array(self):
        """Capture frame as numpy array for processing"""
        if not self.picam2:
            if not self.initialize_camera():
                return None
        
        try:
            frame = self.picam2.capture_array("main")
            return frame
        except Exception as e:
            print(f"❌ Error capturing frame array: {e}")
            return None
    
    def setup_streaming(self):
        """Setup MJPEG streaming with encoder"""
        if not self.picam2:
            if not self.initialize_camera():
                return False
                
        try:
            self.streaming_output = StreamingOutput()
            self.jpeg_encoder = JpegEncoder()
            
            self.picam2.start_recording(
                self.jpeg_encoder, 
                FileOutput(self.streaming_output)
            )
            
            print("✅ Streaming setup complete")
            return True
            
        except Exception as e:
            print(f"❌ Streaming setup error: {e}")
            return False
    
    def stop_streaming(self):
        """Stop MJPEG streaming"""
        try:
            if self.picam2:
                self.picam2.stop_recording()
            self.is_streaming = False
            print("🛑 Streaming stopped")
        except Exception as e:
            print(f"❌ Error stopping streaming: {e}")
    
    def release_camera(self):
        """Release camera resources"""
        if self.picam2:
            try:
                if self.is_streaming:
                    self.stop_streaming()
                self.picam2.stop()
                self.picam2.close()
                print("🔒 Camera released")
            except Exception as e:
                print(f"❌ Error releasing camera: {e}")
            self.picam2 = None

# Initialize camera manager
cam_manager = ModernCameraManager()

@app.on_event("startup")
async def startup_event():
    """Initialize camera on startup"""
    print("🚀 Starting Modern Camera Web App (Picamera2)...")
    print(f"🔑 API Key: {API_KEY}")
    print(f"🔒 Web Password: {WEB_LOGIN_PASSWORD}")
    
    # Ensure directories exist
    os.makedirs("captured_images", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    
    if cam_manager.initialize_camera():
        print("📷 Camera ready!")
    else:
        print("⚠️  Camera not found - some features may not work")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("🛑 Shutting down...")
    cam_manager.release_camera()

# Public endpoints (no auth required)
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "api_key": API_KEY
    })

@app.post("/api/auth/login")
async def web_login(request: Request):
    try:
        data = await request.json()
        password = data.get("password", "")
        
        if password == WEB_LOGIN_PASSWORD:
            return {
                "status": "success",
                "api_key": API_KEY,
                "message": "Login successful"
            }
        else:
            raise HTTPException(status_code=401, detail="Invalid password")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid request")

# Protected API endpoints (require API key)
@app.get("/api/camera/status")
async def camera_status(api_key: str = Depends(verify_api_key)):
    is_available = cam_manager.picam2 is not None
    return {
        "status": "available" if is_available else "unavailable",
        "streaming": cam_manager.is_streaming,
        "timestamp": datetime.now().isoformat(),
        "library": "picamera2"
    }

@app.get("/api/camera/capture")
async def capture_photo(api_key: str = Depends(verify_api_key)):
    try:
        print("📸 Attempting to capture photo...")
        
        frame = cam_manager.capture_frame_array()
        if frame is None:
            raise HTTPException(status_code=500, detail="Failed to capture frame")
        
        # Convert RGB to BGR for OpenCV saving
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        else:
            frame_bgr = frame
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"photo_{timestamp}.jpg"
        filepath = os.path.join("captured_images", filename)
        
        # Save image
        success = cv2.imwrite(filepath, frame_bgr)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save image file")
        
        print(f"✅ Photo saved: {filename}")
        
        return {
            "status": "success",
            "filename": filename,
            "filepath": filepath,
            "timestamp": datetime.now().isoformat(),
            "message": "Photo captured successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Capture error: {e}")
        raise HTTPException(status_code=500, detail=f"Capture failed: {str(e)}")

def generate_frames():
    """Generate frames for MJPEG streaming"""
    while cam_manager.is_streaming:
        try:
            if not cam_manager.streaming_output:
                break
                
            with cam_manager.streaming_output.condition:
                cam_manager.streaming_output.condition.wait()
                frame = cam_manager.streaming_output.frame
                
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                time.sleep(0.01)
                
        except Exception as e:
            print(f"❌ Streaming error: {e}")
            break

@app.get("/api/camera/stream")
async def video_stream(token: str = Depends(verify_token_param)):
    """Modern MJPEG video stream using Picamera2"""
    try:
        if not cam_manager.is_streaming:
            if not cam_manager.setup_streaming():
                raise HTTPException(status_code=500, detail="Failed to setup streaming")
            cam_manager.is_streaming = True
        
        return StreamingResponse(
            generate_frames(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Streaming failed: {str(e)}")

@app.post("/api/camera/stream/stop")
async def stop_stream(api_key: str = Depends(verify_api_key)):
    """Stop video stream"""
    cam_manager.stop_streaming()
    return {"status": "success", "message": "Stream stopped"}

@app.get("/api/photos")
async def list_photos(api_key: str = Depends(verify_api_key)):
    """List all captured photos"""
    try:
        photos = []
        if os.path.exists("captured_images"):
            for filename in os.listdir("captured_images"):
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    filepath = os.path.join("captured_images", filename)
                    if os.path.exists(filepath):
                        stat = os.stat(filepath)
                        photos.append({
                            "filename": filename,
                            "size": stat.st_size,
                            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            "url": f"/captured_images/{filename}"
                        })
        
        # Sort by creation time (newest first)
        photos.sort(key=lambda x: x["created"], reverse=True)
        
        return {
            "status": "success",
            "count": len(photos),
            "photos": photos
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list photos: {str(e)}")

# Serve captured images
@app.get("/captured_images/{filename}")
async def serve_image(filename: str):
    """Serve captured images"""
    filepath = os.path.join("captured_images", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(filepath)

@app.get("/health")
async def health_check():
    """Public health check endpoint"""
    return {
        "status": "healthy",
        "service": "modern-camera-web-app",
        "timestamp": datetime.now().isoformat(),
        "library": "picamera2",
        "camera_available": cam_manager.picam2 is not None
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8003)
```

### Step 2: Create the Web Interface

Create `templates/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Secure Camera Web App</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .login-container {
            max-width: 400px;
            margin: 100px auto;
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            text-align: center;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .controls {
            display: flex;
            gap: 15px;
            justify-content: center;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.3s;
        }
        .btn-primary { background: #007bff; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-secondary { background: #6c757d; color: white; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
        .camera-container {
            text-align: center;
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        .camera-stream {
            max-width: 100%;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }
        .status {
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
            text-align: center;
        }
        .status.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .status.error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .status.info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        .photos-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .photo-card {
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .photo-card img {
            width: 100%;
            height: 150px;
            object-fit: cover;
        }
        .photo-info {
            padding: 10px;
            font-size: 12px;
            color: #666;
        }
        .form-group {
            margin-bottom: 20px;
            text-align: left;
        }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
            box-sizing: border-box;
        }
        .form-group input:focus {
            border-color: #007bff;
            outline: none;
        }
        .hidden { display: none; }
    </style>
</head>
<body>
    <!-- Login Screen -->
    <div id="loginScreen" class="login-container">
        <h1>🔒 Camera Access</h1>
        <p>Enter password to access the camera system</p>
        
        <div class="form-group">
            <label for="password">Password:</label>
            <input type="password" id="password" placeholder="Enter password" />
        </div>
        
        <button class="btn btn-primary" onclick="login()" style="width: 100%;">
            🔑 Login
        </button>
        
        <div id="loginStatus" class="status" style="display: none;"></div>
    </div>

    <!-- Main App (hidden until login) -->
    <div id="mainApp" class="hidden">
        <div class="header">
            <h1>📷 Modern Camera Web App</h1>
            <p>Powered by Picamera2 - Live streaming and photo capture</p>
            <button class="btn btn-secondary" onclick="logout()" style="float: right;">
                🚪 Logout
            </button>
            <div id="status" class="status"></div>
        </div>

        <div class="controls">
            <button class="btn btn-success" onclick="capturePhoto()">📸 Capture Photo</button>
            <button class="btn btn-primary" onclick="startStream()">🎥 Start Stream</button>
            <button class="btn btn-danger" onclick="stopStream()">⏹️ Stop Stream</button>
            <button class="btn btn-primary" onclick="loadPhotos()">🖼️ Load Photos</button>
        </div>

        <div class="camera-container">
            <img id="cameraStream" class="camera-stream" style="display:none;" />
            <div id="streamPlaceholder">
                <h3>📷 Camera Stream</h3>
                <p>Click "Start Stream" to begin live video</p>
            </div>
        </div>

        <div id="photosContainer">
            <h3>📸 Captured Photos</h3>
            <div id="photosGrid" class="photos-grid"></div>
        </div>
    </div>

    <script>
        let isStreaming = false;
        let apiKey = null;
        let isAuthenticated = false;

        // Login function
        async function login() {
            const password = document.getElementById('password').value;
            const statusDiv = document.getElementById('loginStatus');
            
            if (!password) {
                statusDiv.className = 'status error';
                statusDiv.textContent = 'Please enter a password';
                statusDiv.style.display = 'block';
                return;
            }
            
            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ password: password })
                });
                
                const data = await response.json();
                
                if (response.ok && data.status === 'success') {
                    apiKey = data.api_key;
                    isAuthenticated = true;
                    
                    // Hide login, show main app
                    document.getElementById('loginScreen').classList.add('hidden');
                    document.getElementById('mainApp').classList.remove('hidden');
                    
                    // Initialize main app
                    checkCameraStatus();
                    loadPhotos();
                    
                } else {
                    throw new Error(data.detail || 'Login failed');
                }
                
            } catch (error) {
                statusDiv.className = 'status error';
                statusDiv.textContent = `❌ ${error.message}`;
                statusDiv.style.display = 'block';
            }
        }

        // Logout function
        function logout() {
            apiKey = null;
            isAuthenticated = false;
            
            // Stop any streaming
            if (isStreaming) {
                stopStream();
            }
            
            // Show login, hide main app
            document.getElementById('loginScreen').classList.remove('hidden');
            document.getElementById('mainApp').classList.add('hidden');
            
            // Clear password field
            document.getElementById('password').value = '';
            document.getElementById('loginStatus').style.display = 'none';
        }

        // API helper function
        async function apiCall(endpoint, options = {}) {
            if (!apiKey) {
                throw new Error('Not authenticated');
            }
            
            const defaultOptions = {
                headers: {
                    'Authorization': `Bearer ${apiKey}`,
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            };
            
            return fetch(endpoint, { ...options, ...defaultOptions });
        }

        // Check camera status
        async function checkCameraStatus() {
            try {
                const response = await apiCall('/api/camera/status');
                const data = await response.json();
                
                const statusDiv = document.getElementById('status');
                if (data.status === 'available') {
                    statusDiv.className = 'status success';
                    statusDiv.textContent = `✅ Camera ready (${data.library})`;
                } else {
                    statusDiv.className = 'status error';
                    statusDiv.textContent = '❌ Camera not available';
                }
            } catch (error) {
                console.error('Status check failed:', error);
                document.getElementById('status').className = 'status error';
                document.getElementById('status').textContent = '❌ Connection failed';
            }
        }

        // Capture photo
        async function capturePhoto() {
            try {
                const response = await apiCall('/api/camera/capture');
                const data = await response.json();
                
                if (data.status === 'success') {
                    document.getElementById('status').className = 'status success';
                    document.getElementById('status').textContent = `✅ Photo captured: ${data.filename}`;
                    loadPhotos(); // Refresh photos
                } else {
                    throw new Error(data.message || 'Capture failed');
                }
            } catch (error) {
                document.getElementById('status').className = 'status error';
                document.getElementById('status').textContent = `❌ Capture failed: ${error.message}`;
            }
        }

        // Start stream
        function startStream() {
            if (isStreaming || !apiKey) return;
            
            const img = document.getElementById('cameraStream');
            const placeholder = document.getElementById('streamPlaceholder');
            
            img.src = `/api/camera/stream?token=${apiKey}&t=${new Date().getTime()}`;
            img.style.display = 'block';
            placeholder.style.display = 'none';
            isStreaming = true;
            
            document.getElementById('status').className = 'status success';
            document.getElementById('status').textContent = '🎥 Live stream started';
        }

        // Stop stream
        async function stopStream() {
            if (!isStreaming) return;
            
            try {
                await apiCall('/api/camera/stream/stop', { method: 'POST' });
                
                const img = document.getElementById('cameraStream');
                const placeholder = document.getElementById('streamPlaceholder');
                
                img.style.display = 'none';
                img.src = '';
                placeholder.style.display = 'block';
                isStreaming = false;
                
                document.getElementById('status').className = 'status success';
                document.getElementById('status').textContent = '⏹️ Stream stopped';
            } catch (error) {
                console.error('Failed to stop stream:', error);
            }
        }

        // Load photos
        async function loadPhotos() {
            try {
                const response = await apiCall('/api/photos');
                const data = await response.json();
                
                const grid = document.getElementById('photosGrid');
                
                if (data.photos && data.photos.length > 0) {
                    grid.innerHTML = data.photos.map(photo => `
                        <div class="photo-card">
                            <img src="${photo.url}" alt="${photo.filename}" />
                            <div class="photo-info">
                                <div><strong>${photo.filename}</strong></div>
                                <div>${new Date(photo.created).toLocaleString()}</div>
                                <div>${(photo.size / 1024).toFixed(1)} KB</div>
                            </div>
                        </div>
                    `).join('');
                } else {
                    grid.innerHTML = '<p>No photos captured yet. Click "Capture Photo" to take your first picture!</p>';
                }
            } catch (error) {
                console.error('Failed to load photos:', error);
                document.getElementById('photosGrid').innerHTML = '<p>Failed to load photos</p>';
            }
        }

        // Enter key support for password field
        document.addEventListener('DOMContentLoaded', function() {
            document.getElementById('password').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    login();
                }
            });
        });
    </script>
</body>
</html>
```

## 🧪 Part 4: Test the Application Locally

### Step 1: Start the Application

```bash
# Make sure you're in the right directory with venv activated
cd ~/cloudflare-apps/camera-app
source venv/bin/activate

# Start the application
uvicorn main:app --host 127.0.0.1 --port 8003 --reload
```

### Step 2: Test Locally

1. **Open browser** to: `http://YOUR_PI_IP:8003`
2. **Login** with password: `camera123`
3. **Test camera functions**:
   - Click "Capture Photo"
   - Click "Start Stream"
   - Verify live video works

## 🌐 Part 5: Cloudflare Tunnel Setup

### Step 1: Install cloudflared

```bash
# Download cloudflared for ARM64
wget -O cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb

# Install
sudo dpkg -i cloudflared.deb

# Verify installation
cloudflared --version
```

### Step 2: Create Tunnel via Dashboard

1. **Go to**: Cloudflare Dashboard → Zero Trust → Networks → Tunnels
2. **Click**: "Create a tunnel"
3. **Name**: `pi-camera` (or your preferred name)
4. **Save tunnel**
5. **Configure**:
   - **Subdomain**: `camera`
   - **Domain**: `yourdomain.com`
   - **Service Type**: `HTTP`
   - **Service URL**: `127.0.0.1:8003`
6. **Save**
7. **Copy the tunnel token** from the installation command

## 🔄 Part 6: Auto-Start Services with Tmux (FIXED!)

### Step 1: Create Camera App Service

```bash
# Create user systemd directory
mkdir -p ~/.config/systemd/user

# Create the camera service (FIXED VERSION)
cat > ~/.config/systemd/user/camera-app.service << 'EOF'
[Unit]
Description=Camera Web App (Tmux Session)
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=%h/cloudflare-apps/camera-app
Environment=HOME=%h
Environment=PATH=/usr/bin:/bin:/usr/local/bin
Environment=SHELL=/bin/bash
ExecStart=/bin/bash -c 'cd %h/cloudflare-apps/camera-app && source venv/bin/activate && tmux new-session -d -s camera-app "uvicorn main:app --host 127.0.0.1 --port 8003"'
ExecStop=/usr/bin/tmux kill-session -t camera-app
ExecStopPost=/bin/bash -c 'tmux kill-session -t camera-app 2>/dev/null || true'

[Install]
WantedBy=default.target
EOF

echo "✅ Camera service created"
```

### Step 2: Create Cloudflare Tunnel Service

```bash
# Create tunnel service
sudo tee /etc/systemd/system/cloudflared.service > /dev/null << 'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/cloudflared tunnel run --token YOUR_TOKEN_HERE
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "⚠️  IMPORTANT: Edit the tunnel service to add your token:"
echo "   sudo nano /etc/systemd/system/cloudflared.service"
echo "   Replace 'YOUR_TOKEN_HERE' with your actual Cloudflare tunnel token"
```

### Step 3: Add Your Tunnel Token

```bash
# Edit the tunnel service file to add your token
sudo nano /etc/systemd/system/cloudflared.service

# Replace 'YOUR_TOKEN_HERE' with your actual token from Cloudflare Dashboard
# The token looks like: eyJhIjoiNWVjMzF...
```

### Step 4: Enable Auto-Start on Boot

```bash
# Reload and enable camera service
systemctl --user daemon-reload
systemctl --user enable camera-app.service

# Enable lingering so service starts even without login
sudo loginctl enable-linger $USER

# Enable tunnel service
sudo systemctl daemon-reload
sudo systemctl enable cloudflared

echo "✅ Services configured for auto-start on boot"
```

### Step 5: Start Services

```bash
# Start camera app
systemctl --user start camera-app.service

# Start tunnel (make sure you added your token first!)
sudo systemctl start cloudflared

# Check status
systemctl --user status camera-app.service
sudo systemctl status cloudflared
```

### Step 6: Verify Everything Works

```bash
# Check tmux session
tmux list-sessions

# Test local access
curl -I http://127.0.0.1:8003/health

# Test external access (replace with your domain)
curl -I https://camera.yourdomain.com/health

# View live logs (Ctrl+B then D to exit)
tmux attach -t camera-app
```

## 🔍 Part 7: Management and Monitoring

### Check Service Status

```bash
# Camera app status
systemctl --user status camera-app.service

# Tunnel status
sudo systemctl status cloudflared

# Check tmux session
tmux list-sessions

# Test connectivity
curl -I http://127.0.0.1:8003/health
```

### View Logs

```bash
# Live camera logs via tmux (Ctrl+B then D to exit)
tmux attach -t camera-app

# Systemd service logs
journalctl --user -f -u camera-app.service
sudo journalctl -f -u cloudflared
```

### Restart Services

```bash
# Restart camera app
systemctl --user restart camera-app.service

# Restart tunnel
sudo systemctl restart cloudflared
```

### Status Script

```bash
# Create status monitoring script
cat > ~/camera_status.sh << 'EOF'
#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🖥️  System Info:${NC}"
echo "   Hostname: $(hostname)"
echo "   User: $USER"
echo "   IP: $(hostname -I | awk '{print $1}')"
echo "   Uptime: $(uptime -p)"
echo ""

echo -e "${BLUE}📷 Camera App Status:${NC}"
if systemctl --user is-active camera-app.service >/dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Service Running${NC}"
else
    echo -e "   ${RED}❌ Service Stopped${NC}"
fi

if tmux has-session -t camera-app 2>/dev/null; then
    echo -e "   ${GREEN}✅ Tmux Session Active${NC}"
else
    echo -e "   ${RED}❌ Tmux Session Missing${NC}"
fi

# Test HTTP endpoint
if curl -s http://127.0.0.1:8003/health > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅ HTTP Endpoint Responding${NC}"
else
    echo -e "   ${RED}❌ HTTP Endpoint Not Responding${NC}"
fi

echo ""
echo -e "${BLUE}🌐 Tunnel Status:${NC}"  
if systemctl is-active cloudflared >/dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Running${NC}"
else
    echo -e "   ${RED}❌ Stopped${NC}"
fi

echo ""
echo -e "${BLUE}🔗 Access URLs:${NC}"
echo "   Local: http://127.0.0.1:8003"
echo "   Public: https://camera.yourdomain.com"

echo ""
echo -e "${BLUE}📋 Quick Commands:${NC}"
echo "   systemctl --user status camera-app.service  - Check service"
echo "   tmux attach -t camera-app                   - View logs"
echo "   systemctl --user restart camera-app.service - Restart"
echo "   ~/camera_status.sh                          - Run this status check"
EOF

chmod +x ~/camera_status.sh

# Create restart script
cat > ~/restart_camera.sh << 'EOF'
#!/bin/bash
echo "🔄 Restarting camera service..."
systemctl --user restart camera-app.service
sleep 3
~/camera_status.sh
EOF

chmod +x ~/restart_camera.sh
```

## 🛠️ Part 8: Troubleshooting

### Common Issues and Fixes

#### Service Won't Start After Reboot:
```bash
# Check if service is enabled
systemctl --user is-enabled camera-app.service

# Check if lingering is enabled
loginctl show-user $USER | grep Linger

# Enable both if missing
systemctl --user enable camera-app.service
sudo loginctl enable-linger $USER
```

#### Camera Not Working:
```bash
# Enable camera interface
sudo raspi-config
# → Interface Options → Camera → Enable
sudo reboot
```

#### Tmux Session Issues:
```bash
# Kill existing sessions
tmux kill-session -t camera-app 2>/dev/null

# Restart service
systemctl --user restart camera-app.service
```

### Useful Commands

```bash
# Camera service management
systemctl --user status camera-app.service    # Check status
systemctl --user restart camera-app.service   # Restart
systemctl --user stop camera-app.service      # Stop
systemctl --user start camera-app.service     # Start

# Tmux session management  
tmux list-sessions                            # List sessions
tmux attach -t camera-app                     # Attach to logs
tmux kill-session -t camera-app               # Kill session

# Testing
curl -I http://127.0.0.1:8003/health         # Local test
curl -I https://camera.yourdomain.com/health # External test
```

## 🎯 Final Checklist

- ✅ **Tmux installed and verified**
- ✅ Camera hardware connected and detected
- ✅ Picamera2 working in virtual environment
- ✅ FastAPI app running locally
- ✅ Camera streaming and photo capture working
- ✅ Cloudflare tunnel configured with token
- ✅ External HTTPS access working
- ✅ User systemd service configured (FIXED!)
- ✅ Auto-start on boot enabled
- ✅ Tmux session accessible for logs

### Quick Test

```bash
# Full system test
~/camera_status.sh

# Reboot test
sudo reboot
# Wait 2 minutes, then check:
~/camera_status.sh
tmux attach -t camera-app
```

## 🎉 Conclusion

You now have a complete, modern camera web application that:

- **Starts automatically** on boot using user systemd service (FIXED!)
- **Runs in tmux session** for easy log access and debugging
- **Works with any username** using universal variables
- **Streams live video** and captures photos using modern Picamera2
- **Accessible worldwide** via secure Cloudflare tunnel
- **Simple to manage** with standard systemd commands

### Key Commands

```bash
systemctl --user status camera-app.service    # Check service
tmux attach -t camera-app                     # View logs (Ctrl+B then D to exit)
~/camera_status.sh                           # Full system status
~/restart_camera.sh                          # Restart camera service
```

**Access your camera at**: `https://camera.yourdomain.com`  
**Default login**: `camera123` (change this in `main.py`)

## 🔧 Key Fixes Made:

1. **Service Type**: Changed from `Type=simple` to `Type=oneshot` + `RemainAfterExit=yes`
2. **Environment**: Added proper PATH and SHELL variables
3. **Cleanup**: Added `ExecStopPost` for better cleanup
4. **Removed**: Unnecessary restart logic that was causing loops

---

*This guide now includes all fixes and should work reliably for auto-starting the camera service on boot!*