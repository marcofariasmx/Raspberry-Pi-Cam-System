# Raspberry Pi Camera Web App - Complete Deployment Guide

This guide provides step-by-step instructions to deploy the Raspberry Pi Camera Web App with auto-start services and worldwide access via Cloudflare Tunnel.

## 📋 Overview

This deployment will give you:
- ✅ Modern camera web app with live streaming and photo capture
- ✅ Secure web interface with password protection  
- ✅ Accessible from anywhere via HTTPS (Cloudflare Tunnel)
- ✅ Auto-start services on boot using tmux sessions
- ✅ Easy log access and debugging
- ✅ Universal setup compatible with Camera Module 2 & 3

## 🛠️ Prerequisites

### Hardware Requirements
- Raspberry Pi (any model with Raspberry Pi OS)
- Raspberry Pi Camera Module (V1, V2, V3, or HQ Camera)
- MicroSD card (16GB+ recommended)
- Internet connection
- Power supply appropriate for your Pi model

### Software Requirements
- Raspberry Pi OS (Bullseye or later)
- SSH access to your Pi
- Cloudflare account with a domain (for external access)

### Domain Requirements
- Active domain managed through Cloudflare
- Cloudflare account with tunnel access

## 🚀 Part 1: Initial System Setup

### Step 1: Update System

```bash
# Update package lists and upgrade system
sudo apt update && sudo apt upgrade -y

# Reboot to ensure updates are applied
sudo reboot
```

### Step 2: Enable Camera Interface

```bash
# Enable camera interface using raspi-config
sudo raspi-config

# Navigate to:
# Interface Options -> Camera -> Enable

# Alternatively, enable via command line:
sudo raspi-config nonint do_camera 0

# Reboot after enabling camera
sudo reboot
```

### Step 3: Test Camera Hardware

```bash
# Test camera detection and basic functionality
libcamera-hello -t 5000

# If successful, you should see a 5-second camera preview
# If this fails, check camera connection and interface settings
```

## 🏗️ Part 2: Application Installation

### Step 1: Clone Repository

```bash
# Clone the repository
cd ~
git clone https://github.com/yourusername/Raspberry-Pi-Cam-System.git
cd Raspberry-Pi-Cam-System

# Make scripts executable
chmod +x scripts/*.sh
```

### Step 2: Run Automated Setup

```bash
# Run the main setup script
./scripts/setup.sh

# The script will:
# 1. Install system dependencies
# 2. Verify camera functionality
# 3. Set up Python environment
# 4. Configure the application
# 5. Create project structure

# Monitor progress in tmux session if desired:
# tmux attach -t camera_setup
```

### Step 3: Configure Environment (Optional)

The setup script creates a `.env` file with default settings. You can customize it:

```bash
# Navigate to project directory
cd ~/cloudflare-apps/camera-app

# Edit configuration
nano .env
```

**Key Configuration Options:**
```env
# Security (customize these!)
API_KEY=your_secure_api_key_here
WEB_PASSWORD=your_secure_password_here

# Camera settings
CAMERA_AUTO_DETECT=true
CAMERA_FALLBACK_WIDTH=1920
CAMERA_FALLBACK_HEIGHT=1080

# Streaming settings
STREAM_WIDTH=640
STREAM_HEIGHT=480
STREAM_QUALITY=85

# Camera orientation
CAMERA_HFLIP=true
CAMERA_VFLIP=true
```

### Step 4: Test Application

```bash
# Navigate to project directory
cd ~/cloudflare-apps/camera-app

# Activate virtual environment
source venv/bin/activate

# Test application startup
python3 src/main.py

# You should see output like:
# 🚀 Starting Raspberry Pi Camera Web App...
# 📷 Camera Module 2 detected: 3280x2464
# ✅ Camera initialized successfully
# 🌐 Server will start on 127.0.0.1:8003
```

Test locally by opening: `http://YOUR_PI_IP:8003`

## 🔧 Part 3: Service Installation

### Step 1: Install Auto-Start Services

```bash
# Install systemd services for auto-start on boot
./scripts/install_services.sh

# This will:
# 1. Create systemd user service
# 2. Enable auto-start on boot
# 3. Start the camera service
# 4. Create management scripts
# 5. Set up Cloudflare tunnel template
```

### Step 2: Verify Service Status

```bash
# Check service status
./scripts/install_services.sh status

# Or use individual commands:
systemctl --user status camera-app.service
tmux list-sessions
```

### Step 3: Test Auto-Start (Optional)

```bash
# Reboot to test auto-start functionality
sudo reboot

# After reboot, check if service started automatically
systemctl --user status camera-app.service
tmux has-session -t camera-app && echo "Tmux session is running"
```

## 🌐 Part 4: Cloudflare Tunnel Setup

### Step 1: Install Cloudflared

The modern approach uses the Cloudflare Dashboard to generate installation commands:

1. **Go to Cloudflare Dashboard**: https://dash.cloudflare.com/
2. **Navigate to**: Zero Trust → Networks → Tunnels
3. **Click**: "Create a tunnel"
4. **Choose**: "Cloudflared"
5. **Name your tunnel**: `pi-camera` (or your preferred name)
6. **Choose environment**: Linux ARM64-bit
7. **Copy the installation command** (it will look like):
   ```bash
   curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
   sudo dpkg -i cloudflared.deb
   ```

8. **Run the installation command on your Pi**

### Step 2: Configure Tunnel

1. **In the Cloudflare Dashboard**, continue the tunnel setup:
   - **Subdomain**: `camera` (or your choice)
   - **Domain**: Select your domain
   - **Service Type**: `HTTP`
   - **Service URL**: `127.0.0.1:8003`

2. **Copy the service installation command** provided by Cloudflare:
   ```bash
   sudo cloudflared service install eyJhIjoiNWVjMzF...
   ```

3. **Run the service installation command on your Pi**

### Step 3: Test Tunnel

```bash
# Check tunnel service status
sudo systemctl status cloudflared

# Test external access
curl -I https://camera.yourdomain.com/health

# You should receive a successful HTTP response
```

### Step 4: Alternative Manual Method (if needed)

If you prefer manual configuration:

```bash
# Edit the tunnel service with your token
sudo nano /etc/systemd/system/cloudflared.service

# Replace YOUR_TOKEN_HERE with your actual tunnel token
# The token is provided in the Cloudflare Dashboard

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

## 📊 Part 5: Monitoring and Management

### Service Management Commands

```bash
# Check overall status
~/cloudflare-apps/camera-app/camera_status.sh

# Restart camera service
~/cloudflare-apps/camera-app/restart_camera.sh

# View live logs
tmux attach -t camera-app

# Service control
systemctl --user status camera-app.service    # Check status
systemctl --user restart camera-app.service   # Restart
systemctl --user stop camera-app.service      # Stop
systemctl --user start camera-app.service     # Start

# Tunnel management
sudo systemctl status cloudflared             # Check tunnel
sudo systemctl restart cloudflared            # Restart tunnel
```

### Log Access

```bash
# Application logs (via tmux)
tmux attach -t camera-app

# Exit tmux: Ctrl+B then D

# Service logs
journalctl --user -f -u camera-app.service

# Tunnel logs
sudo journalctl -f -u cloudflared
```

### Health Checks

```bash
# Local health check
curl -s http://127.0.0.1:8003/health | python3 -m json.tool

# External health check (replace with your domain)
curl -s https://camera.yourdomain.com/health | python3 -m json.tool

# Camera status check
curl -s -H "Authorization: Bearer YOUR_API_KEY" \
  http://127.0.0.1:8003/api/camera/status | python3 -m json.tool
```

## 🔒 Part 6: Security Configuration

### Default Credentials

**⚠️ Important**: Change the default credentials before deployment!

```bash
# Edit environment configuration
cd ~/cloudflare-apps/camera-app
nano .env

# Update these values:
API_KEY=your_new_secure_api_key_here
WEB_PASSWORD=your_new_secure_password_here
```

### Additional Security Measures

1. **Change SSH password** or use key-based authentication
2. **Enable UFW firewall** if needed:
   ```bash
   sudo ufw enable
   sudo ufw allow ssh
   sudo ufw allow 8003  # Only if you need local network access
   ```
3. **Regular updates**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

## 🐛 Part 7: Troubleshooting

### Common Issues

#### Camera Not Detected
```bash
# Check camera interface
sudo raspi-config nonint get_camera
# Should return 0 if enabled

# Test camera directly
libcamera-hello -t 2000 --nopreview

# Check for camera in device tree
vcgencmd get_camera
```

#### Service Won't Start
```bash
# Check service status
systemctl --user status camera-app.service

# Check if tmux is available
which tmux

# Manually test application
cd ~/cloudflare-apps/camera-app
source venv/bin/activate
python3 src/main.py
```

#### Tunnel Connection Issues
```bash
# Check cloudflared status
sudo systemctl status cloudflared

# Test DNS resolution
nslookup camera.yourdomain.com

# Check tunnel configuration
sudo cloudflared tunnel info
```

#### Memory Issues (especially Pi Zero)
```bash
# Check memory usage
free -h

# Reduce buffer count in .env
BUFFER_COUNT_FALLBACK=1

# Or use lower resolution
CAMERA_FALLBACK_WIDTH=1280
CAMERA_FALLBACK_HEIGHT=720
```

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Edit .env file
cd ~/cloudflare-apps/camera-app
nano .env

# Set debug mode
DEBUG=true

# Restart service
systemctl --user restart camera-app.service

# View detailed logs
tmux attach -t camera-app
```

### Reset Installation

If you need to start over:

```bash
# Stop services
systemctl --user stop camera-app.service
sudo systemctl stop cloudflared

# Remove installation
rm -rf ~/cloudflare-apps/camera-app

# Disable services
systemctl --user disable camera-app.service
sudo systemctl disable cloudflared

# Remove service files
rm -f ~/.config/systemd/user/camera-app.service
sudo rm -f /etc/systemd/system/cloudflared.service

# Reload systemd
systemctl --user daemon-reload
sudo systemctl daemon-reload

# Start fresh installation
cd ~/Raspberry-Pi-Cam-System
./scripts/setup.sh
```

## 📝 Part 8: Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `cam_secure_key_raspberry_pi_monitor` | Authentication key for API access |
| `WEB_PASSWORD` | `camera123` | Password for web interface login |
| `CAMERA_AUTO_DETECT` | `true` | Auto-detect camera capabilities |
| `CAMERA_FALLBACK_WIDTH` | `1920` | Fallback resolution width |
| `CAMERA_FALLBACK_HEIGHT` | `1080` | Fallback resolution height |
| `STREAM_WIDTH` | `640` | Video stream width |
| `STREAM_HEIGHT` | `480` | Video stream height |
| `STREAM_QUALITY` | `85` | JPEG quality for streaming (1-100) |
| `BUFFER_COUNT_AUTO` | `true` | Auto-adjust buffer count based on camera |
| `BUFFER_COUNT_FALLBACK` | `2` | Manual buffer count |
| `CAMERA_HFLIP` | `true` | Horizontal flip |
| `CAMERA_VFLIP` | `true` | Vertical flip |
| `MAIN_STREAM_FORMAT` | `RGB888` | Main stream format |
| `LORES_STREAM_FORMAT` | `YUV420` | Low-res stream format |
| `HOST` | `127.0.0.1` | Server bind address |
| `PORT` | `8003` | Server port |
| `DEBUG` | `false` | Debug mode |
| `PHOTOS_DIR` | `captured_images` | Photos storage directory |
| `MAX_PHOTOS` | `100` | Maximum photos to display |

### API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | None | Web interface |
| `/health` | GET | None | Health check |
| `/api/auth/login` | POST | None | Web authentication |
| `/api/camera/status` | GET | API Key | Camera status |
| `/api/camera/capture` | GET | API Key | Capture photo |
| `/api/camera/stream` | GET | Token | Video stream |
| `/api/camera/stream/stop` | POST | API Key | Stop stream |
| `/api/photos` | GET | API Key | List photos |
| `/api/photos/{filename}` | DELETE | API Key | Delete photo |
| `/captured_images/{filename}` | GET | None | Serve photo |

## 🎉 Part 9: Final Verification

### Complete System Test

1. **Reboot your Pi**:
   ```bash
   sudo reboot
   ```

2. **Wait 2-3 minutes** for full boot and service startup

3. **Check all services**:
   ```bash
   ~/cloudflare-apps/camera-app/camera_status.sh
   ```

4. **Test local access**:
   - Open: `http://YOUR_PI_IP:8003`
   - Login with your configured password
   - Test photo capture and video streaming

5. **Test external access**:
   - Open: `https://camera.yourdomain.com`
   - Verify secure HTTPS connection
   - Test all functionality

6. **Verify auto-start**:
   - Services should automatically start after reboot
   - Check with: `systemctl --user status camera-app.service`

### Success Indicators

✅ **Camera service** running and enabled  
✅ **Tmux session** active with application logs  
✅ **HTTP endpoint** responding on port 8003  
✅ **Cloudflare tunnel** active and accessible  
✅ **Photo capture** working correctly  
✅ **Video streaming** functioning smoothly  
✅ **Auto-start** working after reboot  

## 🔗 Part 10: Next Steps

After successful deployment:

1. **Bookmark your camera URL**: `https://camera.yourdomain.com`
2. **Set up regular monitoring** of the service
3. **Configure automated backups** if needed
4. **Document your specific settings** for future reference
5. **Consider setting up additional security** like VPN access
6. **Plan for regular system updates**

## 📞 Support

If you encounter issues:

1. **Check the troubleshooting section** above
2. **Review service logs**: `tmux attach -t camera-app`
3. **Verify hardware connections**
4. **Test with minimal configuration**
5. **Check GitHub issues** for similar problems

---

**Congratulations!** 🎉 Your Raspberry Pi Camera Web App is now fully deployed with professional-grade auto-start services and worldwide HTTPS access via Cloudflare Tunnel.
