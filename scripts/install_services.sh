#!/bin/bash

# Raspberry Pi Camera Web App Service Installation Script
# Creates systemd services for auto-start on boot

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"  # Use current git repository
SERVICE_NAME="camera-app"
TMUX_SESSION="camera-app"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${PURPLE}
╔══════════════════════════════════════════════════════════════╗
║                    🔧 Service Installation                    ║
║              Auto-start Camera App on Boot                   ║
╚══════════════════════════════════════════════════════════════╝${NC}"
}

# Function to display current credentials
display_current_credentials() {
    print_status "Displaying current access credentials..."
    
    # Check if .env file exists
    if [[ ! -f "$PROJECT_DIR/.env" ]]; then
        print_warning "No .env file found. Please run setup script first."
        return 1
    fi
    
    # Extract credentials from .env file
    local api_key
    local web_password
    
    api_key=$(grep "^API_KEY=" "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d '"')
    web_password=$(grep "^WEB_PASSWORD=" "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d '"')
    
    if [[ -z "$api_key" ]] || [[ -z "$web_password" ]]; then
        print_warning "Credentials not found in .env file. Please run setup script first."
        return 1
    fi
    
    # Display credentials prominently
    echo
    echo -e "${PURPLE}═══════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${PURPLE}🔑 CAMERA SYSTEM ACCESS CREDENTIALS${NC}"
    echo -e "${PURPLE}═══════════════════════════════════════════════════════════════════════${NC}"
    echo
    echo -e "${GREEN}📋 Your access credentials:${NC}"
    echo
    echo -e "   ${BLUE}🔑 API KEY:      ${NC}$api_key"
    echo -e "   ${BLUE}🔒 WEB PASSWORD: ${NC}$web_password"
    echo
    echo -e "${YELLOW}💡 How to use these credentials:${NC}"
    echo "   • WEB_PASSWORD: Login to the web interface at http://your-pi-ip:8003"
    echo "   • API_KEY: For direct API access and automation"
    echo
    echo -e "${YELLOW}📝 Need to change credentials?${NC}"
    echo "   • Edit the .env file in $PROJECT_DIR"
    echo "   • Restart the service after changes"
    echo
    echo -e "${PURPLE}═══════════════════════════════════════════════════════════════════════${NC}"
    echo
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if project directory exists
    if [[ ! -d "$PROJECT_DIR" ]]; then
        print_error "Project directory not found: $PROJECT_DIR"
        print_status "Please run the setup script first: ./scripts/setup.sh"
        exit 1
    fi
    
    # Check if application files exist
    if [[ ! -f "$PROJECT_DIR/src/main.py" ]]; then
        print_error "Application files not found"
        print_status "Please run the setup script first: ./scripts/setup.sh"
        exit 1
    fi
    
    # Check if virtual environment exists
    if [[ ! -d "$PROJECT_DIR/venv" ]]; then
        print_error "Virtual environment not found"
        print_status "Please run the setup script first: ./scripts/setup.sh"
        exit 1
    fi
    
    # Check if tmux is installed
    if ! command -v tmux &> /dev/null; then
        print_error "tmux is not installed"
        print_status "Please install tmux: sudo apt install tmux"
        exit 1
    fi
    
    print_success "Prerequisites check passed"
}

# Function to create MediaMTX systemd service
create_mediamtx_service() {
    print_status "Creating MediaMTX streaming server service..."
    
    # Create the MediaMTX service file (system-wide)
    sudo tee /etc/systemd/system/mediamtx.service > /dev/null << EOF
[Unit]
Description=MediaMTX Media Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=$USER
Group=$(id -gn)
WorkingDirectory=/opt/mediamtx
ExecStart=/opt/mediamtx/mediamtx /opt/mediamtx/mediamtx.yml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    print_success "MediaMTX service created: /etc/systemd/system/mediamtx.service"
}

# Function to create camera app systemd service
create_camera_service() {
    print_status "Creating camera application service..."
    
    # Create user systemd directory
    mkdir -p ~/.config/systemd/user
    
    # Create the camera service file (depends on MediaMTX)
    cat > ~/.config/systemd/user/${SERVICE_NAME}.service << EOF
[Unit]
Description=Raspberry Pi Camera Web App (Tmux Session)
After=network-online.target mediamtx.service
Wants=network-online.target
Requires=mediamtx.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${PROJECT_DIR}
Environment=HOME=${HOME}
Environment=PATH=/usr/bin:/bin:/usr/local/bin
Environment=SHELL=/bin/bash
ExecStartPre=/bin/bash -c 'cd ${PROJECT_DIR} && source venv/bin/activate && python3 -c "from src.config import get_config; get_config()" > /dev/null'
ExecStartPre=/bin/bash -c 'until curl -s http://localhost:9997/v3/paths/list >/dev/null 2>&1; do sleep 1; done'
ExecStart=/bin/bash -c 'cd ${PROJECT_DIR} && source venv/bin/activate && tmux new-session -d -s ${TMUX_SESSION} "uvicorn src.main:app --host 0.0.0.0 --port 8003 --loop uvloop"'
ExecStop=/usr/bin/tmux kill-session -t ${TMUX_SESSION}
ExecStopPost=/bin/bash -c 'tmux kill-session -t ${TMUX_SESSION} 2>/dev/null || true'
TimeoutStartSec=60
TimeoutStopSec=10

[Install]
WantedBy=default.target
EOF
    
    print_success "Camera service created: ~/.config/systemd/user/${SERVICE_NAME}.service"
}

# Function to enable and start MediaMTX service
enable_mediamtx_service() {
    print_status "Enabling MediaMTX service for auto-start..."
    
    # Reload systemd daemon
    sudo systemctl daemon-reload
    
    # Enable the service
    sudo systemctl enable mediamtx.service
    
    print_success "MediaMTX service enabled for auto-start on boot"
}

# Function to enable and start camera service
enable_camera_service() {
    print_status "Enabling camera service for auto-start..."
    
    # Reload systemd user daemon
    systemctl --user daemon-reload
    
    # Enable the service
    systemctl --user enable ${SERVICE_NAME}.service
    
    # Enable lingering so service starts even without login
    sudo loginctl enable-linger $USER
    
    print_success "Camera service enabled for auto-start on boot"
}

# Function to start MediaMTX service
start_mediamtx_service() {
    print_status "Starting MediaMTX streaming server..."
    
    # Stop any existing service
    sudo systemctl stop mediamtx.service 2>/dev/null || true
    
    # Start the service
    sudo systemctl start mediamtx.service
    
    # Wait for MediaMTX to be ready
    local attempts=0
    local max_attempts=15
    while [[ $attempts -lt $max_attempts ]]; do
        if curl -s http://localhost:9997/v3/paths/list >/dev/null 2>&1; then
            print_success "MediaMTX streaming server started and ready"
            return 0
        fi
        sleep 1
        attempts=$((attempts + 1))
    done
    
    print_error "MediaMTX failed to start or is not responding"
    print_status "Check status with: sudo systemctl status mediamtx.service"
    return 1
}

# Function to start camera service
start_camera_service() {
    print_status "Starting camera service..."
    
    # Stop any existing service
    systemctl --user stop ${SERVICE_NAME}.service 2>/dev/null || true
    
    # Kill any existing tmux session
    tmux kill-session -t ${TMUX_SESSION} 2>/dev/null || true
    
    # Start the service
    systemctl --user start ${SERVICE_NAME}.service
    
    # Wait a moment for service to start
    sleep 3
    
    # Check service status
    if systemctl --user is-active ${SERVICE_NAME}.service >/dev/null 2>&1; then
        print_success "Camera service started successfully"
        
        # Check if tmux session is running
        if tmux has-session -t ${TMUX_SESSION} 2>/dev/null; then
            print_success "Tmux session '${TMUX_SESSION}' is active"
        else
            print_warning "Service started but tmux session not found"
        fi
        
    else
        print_error "Failed to start camera service"
        print_status "Check status with: systemctl --user status ${SERVICE_NAME}.service"
        exit 1
    fi
}

# Function to test complete streaming pipeline
test_streaming_pipeline() {
    print_status "Testing complete H.264 streaming pipeline..."
    
    # Wait for services to fully initialize
    sleep 8
    
    # Test MediaMTX API
    print_status "Checking MediaMTX status..."
    if curl -s --connect-timeout 5 http://127.0.0.1:9997/v3/paths/list > /dev/null; then
        local mediamtx_status
        mediamtx_status=$(curl -s http://127.0.0.1:9997/v3/paths/list)
        if echo "$mediamtx_status" | grep -q '"ready":true'; then
            print_success "✅ MediaMTX receiving H.264 stream from camera"
        else
            print_warning "⚠️ MediaMTX ready but no active stream yet"
        fi
    else
        print_warning "❌ MediaMTX API not responding"
    fi
    
    # Test Camera HTTP endpoint
    print_status "Checking camera application..."
    if curl -s --connect-timeout 10 http://127.0.0.1:8003/health > /dev/null; then
        print_success "✅ Camera web app is responding on port 8003"
        
        # Show health check response
        local health_response
        health_response=$(curl -s http://127.0.0.1:8003/health)
        echo "Camera health check:"
        echo "$health_response" | python3 -m json.tool 2>/dev/null || echo "$health_response"
        
    else
        print_warning "❌ Camera web app is not responding yet"
        print_status "This might be normal during initial startup"
        print_status "Check logs with: tmux attach -t ${TMUX_SESSION}"
    fi
    
    # Test streaming endpoints
    print_status "Checking streaming endpoints..."
    if curl -s --connect-timeout 5 http://127.0.0.1:8889/cam/whep > /dev/null 2>&1; then
        print_success "✅ WebRTC endpoint available"
    else
        print_status "⚠️ WebRTC endpoint not ready (normal during startup)"
    fi
    
    if curl -s --connect-timeout 5 http://127.0.0.1:8888/cam/index.m3u8 > /dev/null 2>&1; then
        print_success "✅ HLS endpoint available"
    else
        print_status "⚠️ HLS endpoint not ready (normal during startup)"
    fi
}

# Function to show service status
show_service_status() {
    print_header
    
    print_status "Checking streaming system status..."
    echo
    
    # Check MediaMTX service status
    print_status "MediaMTX streaming server status:"
    if sudo systemctl is-active mediamtx.service >/dev/null 2>&1; then
        print_success "✅ MediaMTX service is running"
    else
        print_warning "❌ MediaMTX service is not running"
    fi
    
    if sudo systemctl is-enabled mediamtx.service >/dev/null 2>&1; then
        print_success "✅ MediaMTX service is enabled (auto-start on boot)"
    else
        print_warning "❌ MediaMTX service is not enabled"
    fi
    
    # Check camera service status
    print_status "Camera application status:"
    if systemctl --user is-active ${SERVICE_NAME}.service >/dev/null 2>&1; then
        print_success "✅ Camera service is running"
    else
        print_warning "❌ Camera service is not running"
    fi
    
    if systemctl --user is-enabled ${SERVICE_NAME}.service >/dev/null 2>&1; then
        print_success "✅ Camera service is enabled (auto-start on boot)"
    else
        print_warning "❌ Camera service is not enabled"
    fi
    
    echo
    
    # Check tmux session
    print_status "Tmux session status:"
    if tmux has-session -t ${TMUX_SESSION} 2>/dev/null; then
        print_success "✅ Tmux session '${TMUX_SESSION}' is active"
        print_status "Attach with: tmux attach -t ${TMUX_SESSION}"
    else
        print_warning "❌ Tmux session not found"
    fi
    
    echo
    
    # Check HTTP endpoint
    print_status "Application status:"
    if curl -s --connect-timeout 5 http://127.0.0.1:8003/health > /dev/null; then
        print_success "✅ Web application is responding"
        print_status "Access at: http://$(hostname -I | awk '{print $1}'):8003"
    else
        print_warning "❌ Web application is not responding"
    fi
    
    echo
    
    # Check lingering
    print_status "User lingering status:"
    if loginctl show-user $USER | grep -q "Linger=yes"; then
        print_success "✅ User lingering enabled (service starts on boot)"
    else
        print_warning "❌ User lingering not enabled"
    fi
    
    echo
    print_status "Detailed status commands:"
    echo "  sudo systemctl status mediamtx.service           - MediaMTX service details"
    echo "  sudo journalctl -u mediamtx -f                   - MediaMTX logs"
    echo "  systemctl --user status ${SERVICE_NAME}.service  - Camera service details"
    echo "  tmux attach -t ${TMUX_SESSION}                    - View camera logs"  
    echo "  systemctl --user restart ${SERVICE_NAME}.service - Restart camera service"
    echo "  curl -s http://127.0.0.1:9997/v3/paths/list     - MediaMTX API status"
    echo "  curl -s http://127.0.0.1:8003/health            - Camera app health"
}

# Function to create management scripts
create_management_scripts() {
    print_status "Creating management scripts..."
    
    # Create restart script
    cat > "$PROJECT_DIR/restart_camera.sh" << 'EOF'
#!/bin/bash
echo "🔄 Restarting streaming services..."
echo "1. Restarting MediaMTX..."
sudo systemctl restart mediamtx.service
echo "2. Waiting for MediaMTX to be ready..."
sleep 3
echo "3. Restarting camera service..."
systemctl --user restart camera-app.service
sleep 3
echo "✅ Services restarted"
echo ""
echo "📊 Service status:"
sudo systemctl status mediamtx.service --no-pager -l | head -5
systemctl --user status camera-app.service --no-pager -l | head -5
EOF
    
    # Create status script  
    cat > "$PROJECT_DIR/camera_status.sh" << 'EOF'
#!/bin/bash

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🖥️  System Info:${NC}"
echo "   Hostname: $(hostname)"
echo "   User: $USER"
echo "   IP: $(hostname -I | awk '{print $1}')"
echo "   Uptime: $(uptime -p)"
echo ""

echo -e "${BLUE}📡 MediaMTX Status:${NC}"
if sudo systemctl is-active mediamtx.service >/dev/null 2>&1; then
    echo -e "   ${GREEN}✅ MediaMTX Service Running${NC}"
else
    echo -e "   ${RED}❌ MediaMTX Service Stopped${NC}"
fi

if curl -s --connect-timeout 3 http://127.0.0.1:9997/v3/paths/list >/dev/null 2>&1; then
    echo -e "   ${GREEN}✅ MediaMTX API Responding${NC}"
    if curl -s http://127.0.0.1:9997/v3/paths/list | grep -q '"ready":true'; then
        echo -e "   ${GREEN}✅ H.264 Stream Active${NC}"
    else
        echo -e "   ${YELLOW}⚠️  No Active Stream${NC}"
    fi
else
    echo -e "   ${RED}❌ MediaMTX API Not Responding${NC}"
fi

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

if curl -s --connect-timeout 5 http://127.0.0.1:8003/health > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅ HTTP Endpoint Responding${NC}"
else
    echo -e "   ${RED}❌ HTTP Endpoint Not Responding${NC}"
fi

echo ""
echo -e "${BLUE}🔗 Access URLs:${NC}"
echo "   Local: http://127.0.0.1:8003"
echo "   Network: http://$(hostname -I | awk '{print $1}'):8003"

echo ""
echo -e "${BLUE}🎬 Streaming URLs:${NC}"
echo "   WebRTC: http://127.0.0.1:8889/cam/whep"
echo "   HLS: http://127.0.0.1:8888/cam/index.m3u8"
echo "   RTSP: rtsp://127.0.0.1:8554/cam"

echo ""
echo -e "${BLUE}📋 Quick Commands:${NC}"
echo "   sudo systemctl status mediamtx.service      - Check MediaMTX"
echo "   sudo journalctl -u mediamtx -f              - MediaMTX logs"
echo "   systemctl --user status camera-app.service  - Check camera service"
echo "   tmux attach -t camera-app                   - View camera logs"
echo "   ./restart_camera.sh                         - Restart all services"
echo "   ./camera_status.sh                          - Run this status check"
EOF
    
    # Make scripts executable
    chmod +x "$PROJECT_DIR/restart_camera.sh"
    chmod +x "$PROJECT_DIR/camera_status.sh"
    
    print_success "Management scripts created:"
    print_status "  $PROJECT_DIR/restart_camera.sh - Restart service"
    print_status "  $PROJECT_DIR/camera_status.sh  - Check status"
}

# Function to show reboot information
show_reboot_info() {
    print_status "Checking if reboot is recommended..."
    
    # Check if services are properly configured
    local needs_reboot=false
    
    # Check if user lingering is enabled
    if ! loginctl show-user $USER | grep -q "Linger=yes"; then
        print_warning "User lingering may need a reboot to take full effect"
        needs_reboot=true
    fi
    
    # Check if service is enabled and working
    if ! systemctl --user is-enabled ${SERVICE_NAME}.service >/dev/null 2>&1; then
        print_warning "Service enablement may need a reboot to take full effect"
        needs_reboot=true
    fi
    
    if [[ "$needs_reboot" == "true" ]]; then
        echo
        print_warning "⚠️  A system reboot is recommended to ensure all services start properly on boot"
        print_status "The camera app is working now, but auto-start may not work until reboot"
        echo
        read -p "Reboot system now? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_status "Rebooting system in 5 seconds... (Ctrl+C to cancel)"
            sleep 5
            sudo reboot
        else
            print_status "Reboot skipped. Remember to reboot later for full functionality"
        fi
    else
        print_success "No reboot required - all services are configured correctly"
    fi
}

# Main installation function
install_services() {
    print_header
    
    print_status "Installing camera web app services..."
    print_status "This will create systemd services for auto-start on boot"
    echo
    
    # Check prerequisites
    check_prerequisites
    
    # Display credentials to user
    display_current_credentials
    
    # Create and configure services
    create_mediamtx_service
    create_camera_service
    enable_mediamtx_service
    enable_camera_service
    
    # Start services in correct order
    start_mediamtx_service
    start_camera_service
    
    # Test complete pipeline
    test_streaming_pipeline
    
    # Create management scripts
    create_management_scripts
    
    print_success "🎉 H.264 streaming system installation completed!"
    echo
    print_status "Complete streaming pipeline configured:"
    print_status "  📷 Picamera2 → H.264 hardware encoding"
    print_status "  📡 MediaMTX → WebRTC/HLS distribution" 
    print_status "  🔄 Both services start automatically on boot"
    echo
    print_status "Access the application at: http://$(hostname -I | awk '{print $1}'):8003"
    print_status "Stream formats: WebRTC (ultra-low latency), HLS (broad compatibility)"
    echo
    
    # Show reboot recommendation
    show_reboot_info
}

# Main script logic
case "${1:-install}" in
    "install")
        install_services
        ;;
    "status")
        show_service_status
        ;;
    "restart")
        print_status "Restarting camera service..."
        display_current_credentials
        systemctl --user restart ${SERVICE_NAME}.service
        sleep 3
        show_service_status
        ;;
    "stop")
        print_status "Stopping camera service..."
        systemctl --user stop ${SERVICE_NAME}.service
        tmux kill-session -t ${TMUX_SESSION} 2>/dev/null || true
        print_success "Camera service stopped"
        ;;
    "start")
        print_status "Starting camera service..."
        display_current_credentials
        start_camera_service
        test_camera_service
        ;;
    *)
        echo "Usage: $0 [install|status|restart|stop|start]"
        echo "  install - Install and configure services (default)"
        echo "  status  - Show service status"
        echo "  restart - Restart camera service"
        echo "  stop    - Stop camera service"
        echo "  start   - Start camera service"
        exit 1
        ;;
esac
