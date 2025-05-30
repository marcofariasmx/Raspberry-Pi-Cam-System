# 🍓 Raspberry Pi Camera Web App

A modern, secure camera web application for Raspberry Pi that provides live video streaming and photo capture with worldwide HTTPS access via Cloudflare Tunnel.

## ✨ Features

### 🎥 Camera Capabilities
- **Live Video Streaming** - Real-time MJPEG streaming from your Raspberry Pi camera
- **High-Resolution Photo Capture** - Capture full sensor resolution photos while streaming
- **Simultaneous Operations** - Stream video and capture photos at the same time
- **Auto Camera Detection** - Automatically detects and configures Camera Module 2 & 3
- **Flexible Configuration** - Adjustable resolutions, quality, and camera orientation

### 🔒 Security & Authentication
- **Password Protection** - Secure web interface with configurable password
- **API Key Authentication** - Secure API access with configurable keys
- **HTTPS Access** - Secure external access via Cloudflare Tunnel
- **Environment Configuration** - All secrets configurable via environment variables

### 🚀 Professional Deployment
- **Auto-Start Services** - Automatically starts on boot using systemd services
- **Tmux Integration** - Easy log access and debugging via tmux sessions
- **Health Monitoring** - Built-in health checks and status monitoring
- **Management Scripts** - Simple scripts for service management and monitoring
- **Git-Based Updates** - Easy code updates with `git pull` + service restart

### 🌐 Modern Web Interface
- **Responsive Design** - Works on desktop, tablet, and mobile devices
- **Real-Time Statistics** - Live camera status, photo count, and stream status
- **Photo Gallery** - View and manage captured photos with metadata
- **Progressive Web App** - Modern UI with smooth animations and transitions

## 🛠️ System Requirements

### Hardware
- Raspberry Pi (any model running Raspberry Pi OS)
- Raspberry Pi Camera Module (V1, V2, V3, or HQ Camera)
- MicroSD card (16GB+ recommended)
- Internet connection for external access

### Software
- **Raspberry Pi OS Bookworm** (64-bit recommended) or Bullseye
- **Python 3.11+** (comes with Bookworm) or Python 3.9+
- Git (for cloning and updates)
- Internet connection
- Cloudflare account with domain (for external access)

## 🚀 Quick Start

> **✅ Works out-of-the-box**: Clone → Setup → Run → Update with ease!

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/Raspberry-Pi-Cam-System.git
cd Raspberry-Pi-Cam-System
```

### 2. Run Automated Setup
```bash
chmod +x scripts/*.sh
./scripts/setup.sh
```

The setup script will:
- ✅ Check OS requirements (Bookworm/Bullseye + Python 3.11+)
- ✅ Install all system dependencies
- ✅ Configure Python environment **in the git repository**
- ✅ Test camera functionality
- ✅ Create environment configuration
- ✅ Verify everything works

### 3. Install Auto-Start Services
```bash
./scripts/install_services.sh
```

This configures the application to start automatically on boot.

### 4. Access Your Camera
- **Local Access**: `http://YOUR_PI_IP:8003`
- **Login**: Use the secure password displayed during first-time setup
- **Credentials**: Automatically generated and saved to `.env` file

### 5. Easy Updates (Future)
```bash
git pull                                    # Get latest code
systemctl --user restart camera-app.service # Apply changes
```

That's it! Your camera system is ready and can be updated anytime with a simple `git pull`.

## 🌐 External Access Setup

For secure worldwide access via HTTPS:

1. **Set up Cloudflare Tunnel** following the instructions in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
2. **Configure your domain** to point to the tunnel
3. **Access your camera** from anywhere: `https://camera.yourdomain.com`

## 📁 Project Structure

```
Raspberry-Pi-Cam-System/           # ← You work here (git repository)
├── src/                          # Application source code
│   ├── main.py                  # FastAPI application entry point
│   ├── camera_manager.py        # Camera handling with Picamera2
│   ├── config.py                # Configuration management
│   └── templates/               # Web interface templates
├── scripts/                     # Installation and management scripts
│   ├── setup.sh                # Automated setup script
│   └── install_services.sh     # Service installation
├── docs/                        # Documentation
│   └── DEPLOYMENT.md            # Complete deployment guide
├── venv/                        # Python virtual environment (created by setup)
├── captured_images/             # Photos storage (created by setup)
├── requirements.txt             # Python dependencies
├── .env                         # Your configuration (created by setup)
├── .env.example                 # Environment variables template
├── camera_status.sh             # Status monitoring script (created)
├── restart_camera.sh            # Service restart script (created)
└── README.md                    # This file
```

## ⚙️ Configuration

The application uses environment variables for configuration. The setup script creates `.env` from `.env.example`:

```env
# Security (change these!)
API_KEY=your_secure_api_key_here
WEB_PASSWORD=your_secure_password_here

# Camera settings
CAMERA_AUTO_DETECT=true
STREAM_WIDTH=640
STREAM_HEIGHT=480

# Server settings
HOST=127.0.0.1
PORT=8003
```

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for complete configuration options.

## 🔐 Automatic Security Setup

**NEW: Zero-Configuration Security!** This application automatically generates unique, cryptographically secure credentials on first run.

### 🚀 First-Time Setup Experience

When you first run the application (or if no `.env` file exists), you'll see:

```
======================================================================
🚀 FIRST-TIME SETUP: SECURE CREDENTIALS GENERATED!
======================================================================

📋 Your unique credentials have been automatically generated:

   🔑 API KEY:      cam_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
   🔒 WEB PASSWORD: K9#mP2$qR8@vL5!n

⚠️  IMPORTANT SECURITY NOTICE:
   • These credentials are UNIQUE to this installation
   • Save them securely - you'll need them to access the camera
   • The WEB_PASSWORD is for the web interface login
   • The API_KEY is for direct API access
   • Credentials are saved in the .env file

🛡️  BACKUP RECOMMENDATION:
   • Store these credentials in a password manager
   • Keep a backup of the .env file in a secure location

✅ Setup complete! You can now start the camera system.
======================================================================
```

### 🛡️ Security Benefits

✅ **No Default Passwords** - Eliminates the #1 IoT security risk  
✅ **Unique Per Installation** - Each deployment has different credentials  
✅ **Cryptographically Secure** - Generated using Python's `secrets` module  
✅ **Automatic HTTPS Detection** - Secure cookies for HTTPS, regular cookies for HTTP  
✅ **Photo Access Protection** - All captured images require authentication  
✅ **Session-Based Web Auth** - No API keys exposed to browsers  

### 🔑 Credential Details

- **API Key Format**: `cam_` + 32 random hexadecimal characters
- **Password Format**: 16 characters with letters, numbers, and symbols
- **Storage**: Automatically saved to `.env` file
- **Usage**: API key for direct API access, password for web interface

### ✏️ Manual Configuration

If you prefer to use your own credentials instead of auto-generated ones:

```bash
# Edit the .env file directly
nano .env

# Change the credentials to your preferred values:
API_KEY=your_custom_api_key_here
WEB_PASSWORD=your_custom_password_here

# Save and restart the application
python3 src/main.py
# OR
systemctl --user restart camera-app.service
```

**Benefits of manual configuration:**
- Use memorable passwords
- Consistent credentials across deployments
- Integration with existing credential management systems

### 🔄 Regenerating Credentials

To generate new credentials:

```bash
# Remove existing configuration
rm .env

# Restart application (will generate new credentials)
python3 src/main.py
# OR
systemctl --user restart camera-app.service
```

**Important**: Save the new credentials before they scroll off screen!

## 🔧 Management Commands

```bash
# Check system status
./camera_status.sh

# Restart camera service
./restart_camera.sh

# Update application code
git pull && systemctl --user restart camera-app.service

# View live application logs
tmux attach -t camera-app

# Service management
systemctl --user status camera-app.service    # Check status
systemctl --user restart camera-app.service   # Restart
systemctl --user stop camera-app.service      # Stop
systemctl --user start camera-app.service     # Start
```

## 📡 API Reference

The application provides a RESTful API for integration:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (public) |
| `/api/auth/login` | POST | Web authentication |
| `/api/camera/status` | GET | Camera status |
| `/api/camera/capture` | GET | Capture photo |
| `/api/camera/stream` | GET | Video stream |
| `/api/photos` | GET | List photos |

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for complete API documentation.

## 🏗️ Architecture

### Camera System
- **Picamera2 Integration** - Modern camera library for Raspberry Pi
- **Dual-Stream Configuration** - Simultaneous high-res photos and low-res streaming
- **Adaptive Buffer Management** - Optimized for different camera modules
- **Error Recovery** - Robust error handling and graceful fallbacks

### Web Application
- **FastAPI Backend** - Modern, high-performance Python web framework
- **Async Operations** - Non-blocking video streaming and photo capture
- **Security First** - Built-in authentication and authorization
- **RESTful API** - Clean, documented API for integration

### Service Management
- **Systemd Integration** - Professional service management
- **Tmux Sessions** - Easy debugging and log access
- **Auto-Recovery** - Automatic restart on failure
- **Boot Integration** - Starts automatically on system boot
- **Git-Based Updates** - Easy code updates without reinstallation

## 🎯 Use Cases

### Home Security
- Monitor your home remotely with live streaming
- Capture photos on demand or motion detection
- Secure HTTPS access from anywhere

### IoT Projects
- Integrate camera functionality into larger projects
- RESTful API for automation and control
- Reliable service for continuous operation

### Development & Learning
- Modern Python web development example
- Camera programming with Picamera2
- Service deployment and management
- Cloudflare Tunnel integration

## 🐛 Troubleshooting

### Common Issues

**Camera Not Working**
```bash
# Enable camera interface
sudo raspi-config
# Navigate to Interface Options -> Camera -> Enable

# Test camera
libcamera-hello -t 5000
```

**Service Not Starting**
```bash
# Check service status
systemctl --user status camera-app.service

# View logs
tmux attach -t camera-app
```

**External Access Issues**
```bash
# Check tunnel status
sudo systemctl status cloudflared

# Test connectivity
curl -I https://camera.yourdomain.com/health
```

**Code Updates Not Working**
```bash
# Ensure you're in the git repository
cd /path/to/Raspberry-Pi-Cam-System

# Pull latest changes
git pull

# Restart service to apply changes
systemctl --user restart camera-app.service
```

For detailed troubleshooting, see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## 📖 Documentation

- **[Complete Deployment Guide](docs/DEPLOYMENT.md)** - Step-by-step installation and configuration
- **[Configuration Reference](docs/DEPLOYMENT.md#part-8-configuration-reference)** - All environment variables and settings
- **[API Documentation](docs/DEPLOYMENT.md#api-endpoints)** - Complete API reference
- **[Troubleshooting Guide](docs/DEPLOYMENT.md#part-7-troubleshooting)** - Common issues and solutions

## 🔄 Update Workflow

This project is designed for easy updates:

```bash
# 1. Get latest code
git pull

# 2. Update dependencies if needed (automatic detection)
./scripts/setup.sh update

# 3. Restart service to apply changes
systemctl --user restart camera-app.service

# 4. Verify everything works
./camera_status.sh
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

### Development Setup
```bash
# Clone repository
git clone https://github.com/yourusername/Raspberry-Pi-Cam-System.git
cd Raspberry-Pi-Cam-System

# Run setup (creates venv and configures everything)
./scripts/setup.sh

# Start development server
source venv/bin/activate
python3 src/main.py
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Raspberry Pi Foundation** - For the amazing Raspberry Pi platform
- **Picamera2 Team** - For the modern camera library
- **FastAPI** - For the excellent web framework
- **Cloudflare** - For secure tunnel technology

## 📊 Project Status

This project is actively maintained and regularly updated. Key features are stable and production-ready.

### Recent Updates
- ✅ **Git-based workflow** - Easy updates with `git pull`
- ✅ **Fixed photo capture** during video streaming
- ✅ **OS compatibility** - Bookworm x64 and Python 3.11+ support
- ✅ **Improved setup** - Works out-of-the-box from git repository
- ✅ **Better documentation** - Clear installation and update workflow

### Planned Features
- 🔄 Motion detection alerts
- 🔄 Time-lapse photography
- 🔄 Mobile app companion
- 🔄 Multi-camera support

---

## 🚀 Ready to Get Started?

**Just 3 commands to get your camera system running:**

```bash
git clone https://github.com/yourusername/Raspberry-Pi-Cam-System.git
cd Raspberry-Pi-Cam-System
./scripts/setup.sh
```

For detailed setup instructions, see the [Complete Deployment Guide](docs/DEPLOYMENT.md).

For updates later: `git pull && systemctl --user restart camera-app.service`

**That's it!** 🎉
