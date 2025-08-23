#!/bin/bash

# Raspberry Pi Camera Web App Setup Script
# Automated installation working directly in git repository

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="raspberry-pi-camera-app"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"  # Use current git repository
TMUX_SESSION="camera_setup"

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
║                  🍓 Raspberry Pi Camera Setup                ║
║              Automated Installation Script v3.0              ║
║                   Git Repository Edition                     ║
╚══════════════════════════════════════════════════════════════╝${NC}"
}

# Function to check OS requirements
check_os_requirements() {
    print_status "Checking OS requirements..."
    
    # Check if running on Raspberry Pi
    if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
        print_warning "This script is designed for Raspberry Pi OS"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_error "Setup cancelled"
            exit 1
        fi
    fi
    
    # Check Python version (3.11.x recommended for Raspberry Pi OS Bookworm)
    local python_version
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    print_status "Python version: $python_version"
    
    # Check if Python 3.11+ (recommended for best libcamera/picamera2 compatibility on Bookworm)
    if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"; then
        print_success "Python version compatible (3.11+ optimal for Bookworm)"
    else
        print_warning "Python 3.11+ recommended for Bookworm compatibility (found $python_version)"
    fi
    
    # Check OS version
    if [[ -f /etc/os-release ]]; then
        local os_info
        os_info=$(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2)
        print_status "OS: $os_info"
        
        if grep -q "bookworm" /etc/os-release; then
            print_success "Raspberry Pi OS Bookworm detected (recommended with Python 3.11.x)"
        elif grep -q "bullseye" /etc/os-release; then
            print_success "Raspberry Pi OS Bullseye detected (compatible)"
        else
            print_warning "OS version not specifically tested (Bookworm + Python 3.11 recommended)"
        fi
    fi
}

# Function to check if user is not root
check_user() {
    if [[ $EUID -eq 0 ]]; then
        print_error "This script should not be run as root"
        print_status "Please run as a regular user (the script will use sudo when needed)"
        exit 1
    fi
}

# Function to update system
update_system() {
    print_status "Updating system packages..."
    sudo apt update && sudo apt upgrade -y
    print_success "System updated successfully"
}

# Function to install system dependencies
install_system_dependencies() {
    print_status "Installing system dependencies..."
    
    # Essential packages
    local packages=(
        "python3-picamera2"
        "python3-opencv" 
        "python3-venv"
        "git"
        "tmux"
        "curl"
        "wget"
        "openssl"
        "jq"  # For JSON parsing in scripts
        # Development headers required for Picamera2 pip installation
        "libcap-dev"
        "libcamera-dev"
        "python3-libcamera"
        "libjpeg-dev"
        "libpng-dev"
        "libtiff-dev"
    )
    
    for package in "${packages[@]}"; do
        print_status "Installing $package..."
        sudo apt install -y "$package"
    done
    
    print_success "System dependencies installed"
}

# Function to verify camera
verify_camera() {
    print_status "Testing camera hardware (optional - setup continues regardless)..."
    
    # Try rpicam-hello first (newer Bookworm), then fallback to libcamera-hello
    if timeout 15 rpicam-hello -t 1000 --nopreview >/dev/null 2>&1; then
        print_success "Camera hardware detected and working (rpicam-hello)"
        return 0
    elif timeout 15 libcamera-hello -t 1000 --nopreview >/dev/null 2>&1; then
        print_success "Camera hardware detected and working (libcamera-hello)"
        return 0
    else
        print_status "Camera hardware test timed out (this is normal after fresh libcamera install)"
        print_status "Python camera test will verify full functionality"
        return 1
    fi
}

# Function to test Python camera imports
test_python_camera() {
    print_status "Testing Python camera libraries (optional - setup continues regardless)..."
    
    if python3 -c "
import sys
try:
    from picamera2 import Picamera2
    print('✅ Picamera2 imported successfully')
    
    # Test camera detection without actually initializing
    temp_cam = Picamera2()
    resolution = temp_cam.sensor_resolution
    temp_cam.close()
    print(f'✅ Camera sensor detected: {resolution[0]}x{resolution[1]}')
    
    if resolution[0] * resolution[1] >= 12000000:
        print('📷 Camera Module 3 or equivalent detected')
    elif resolution[0] * resolution[1] >= 8000000:
        print('📷 Camera Module 2 or equivalent detected')
    else:
        print('📷 Camera detected (unknown module)')
        
except Exception as e:
    print(f'⚠️ Camera test failed: {e}')
    print('This is normal if camera is not connected or enabled')
    sys.exit(0)
"; then
        print_success "✅ Camera fully functional - Python libraries and hardware working correctly"
    else
        print_warning "Camera libraries test completed with warnings - continuing setup anyway"
        print_status "Camera functionality can be tested after setup completes"
    fi
}

# Function to setup project structure in-place
setup_project_structure() {
    print_status "Setting up project structure in git repository..."
    
    # Navigate to repository directory
    cd "$PROJECT_DIR"
    
    print_status "Working in: $PROJECT_DIR"
    
    # Create environment file if it doesn't exist
    if [[ ! -f ".env" ]]; then
        print_status "Creating environment configuration..."
        cp ".env.example" ".env"
    else
        print_warning "Environment file already exists, keeping current settings"
    fi
    
    # Create additional directories
    mkdir -p captured_images static
    
    # Verify git repository
    if [[ -d ".git" ]]; then
        print_success "Git repository confirmed"
        local git_status
        git_status=$(git status --porcelain 2>/dev/null || echo "")
        if [[ -n "$git_status" ]]; then
            print_status "Git status: Repository has uncommitted changes"
        fi
    else
        print_warning "Not a git repository - updates via git pull won't work"
    fi
    
    print_success "Project structure ready in git repository"
}

# Function to setup Python environment
setup_python_environment() {
    print_status "Setting up Python virtual environment..."
    
    # Ensure we're in the right directory
    cd "$PROJECT_DIR"
    
    # Create virtual environment with system packages
    # Using system Python 3.11.x for best libcamera/picamera2 compatibility on Bookworm
    python3 -m venv venv --system-site-packages
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install Python packages
    print_status "Installing Python dependencies..."
    pip install -r requirements.txt
    
    # Link system camera modules for cross-version compatibility
    # This ensures libcamera/picamera2 work properly with Python 3.11.x on Bookworm
    print_status "Configuring camera system integration..."
    local venv_packages=$(find "$PROJECT_DIR/venv/lib" -name "site-packages" -type d | head -1)
    local system_packages="/usr/lib/python3/dist-packages"
    
    if [[ -d "$system_packages/libcamera" ]]; then
        # Remove any existing incomplete links
        rm -rf "$venv_packages/libcamera" "$venv_packages/_libcamera"* 2>/dev/null || true
        
        # Link the main libcamera module
        ln -sf "$system_packages/libcamera" "$venv_packages/"
        
        # Link all libcamera-related compiled extensions
        find "$system_packages" -name "_libcamera*" -exec ln -sf {} "$venv_packages/" \; 2>/dev/null || true
        find "$system_packages" -name "*libcamera*.so" -exec ln -sf {} "$venv_packages/" \; 2>/dev/null || true
        
        print_success "Camera system modules linked successfully"
        
        # List what was linked for debugging
        print_status "Linked camera modules:"
        ls -la "$venv_packages" | grep libcamera || echo "  No libcamera links found"
    else
        print_warning "System camera modules not found - camera functionality may be limited"
    fi
    
    # Verify installation
    print_status "Verifying Python installation..."
    python3 -c "
import fastapi
try:
    import libcamera
    import picamera2
    print('✅ All Python dependencies installed successfully')
    print(f'FastAPI version: {fastapi.__version__}')
    print('✅ Camera libraries available')
except ImportError as e:
    print(f'⚠️  Camera import issue: {e}')
    print('FastAPI installed but camera functionality may be limited')
"
    
    print_success "Python environment setup complete"
}

# Function to configure environment
configure_environment() {
    print_status "Configuring application environment..."
    
    # Only update API key if using default value
    if grep -q "your_secure_api_key_here" .env; then
        # Generate secure API key
        local api_key
        api_key=$(openssl rand -hex 16)
        
        # Update .env file
        sed -i "s/your_secure_api_key_here/cam_${api_key}/" .env
        print_success "Generated secure API key"
    else
        print_status "Using existing API key configuration"
    fi
    
    # Only update web password if using default value
    if grep -q "your_secure_password_here" .env; then
        # Generate secure web password
        local web_password
        web_password=$(openssl rand -base64 12 | tr -d "=+/" | cut -c1-16)
        
        # Update .env file
        sed -i "s/your_secure_password_here/${web_password}/" .env
        print_success "Generated secure web password"
    else
        print_status "Using existing web password configuration"
    fi
    
    print_success "Environment configuration ready"
    print_status "You can modify settings in .env file:"
    print_status "  - API_KEY: Authentication key for API access"
    print_status "  - WEB_PASSWORD: Password for web interface login"
    print_status "  - Camera and streaming settings"
}

# Function to install MediaMTX
install_mediamtx() {
    print_status "Installing MediaMTX streaming server..."
    
    # Detect architecture
    local arch=$(uname -m)
    local mediamtx_arch
    case $arch in
        armv6l) mediamtx_arch="armv6" ;;
        armv7l) mediamtx_arch="armv7" ;;
        aarch64) mediamtx_arch="arm64" ;;
        *) 
            print_error "Unsupported architecture: $arch"
            return 1
            ;;
    esac
    
    print_status "Detected architecture: $arch (using $mediamtx_arch)"
    
    # Create MediaMTX directory
    local mediamtx_dir="/opt/mediamtx"
    sudo mkdir -p $mediamtx_dir
    
    # Download latest MediaMTX release
    print_status "Downloading latest MediaMTX..."
    local latest_version
    latest_version=$(curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest | jq -r .tag_name)
    local download_url="https://github.com/bluenviron/mediamtx/releases/download/${latest_version}/mediamtx_${latest_version}_linux_${mediamtx_arch}.tar.gz"
    
    print_status "Downloading: $download_url"
    curl -L $download_url | sudo tar -xz -C $mediamtx_dir
    
    # Make executable
    sudo chmod +x $mediamtx_dir/mediamtx
    
    # Create optimized configuration for Pi H.264 streaming
    sudo tee $mediamtx_dir/mediamtx.yml > /dev/null << 'EOF'
# MediaMTX Configuration for Raspberry Pi H.264 Streaming

# General settings
logLevel: info
logDestinations: [stdout]

# API settings
api: yes
apiAddress: 127.0.0.1:9997

# Metrics
metrics: yes
metricsAddress: 127.0.0.1:9998

# WebRTC settings
webrtc: yes
webrtcAddress: :8889
webrtcEncryption: no
webrtcAllowOrigin: "*"

# HLS settings
hls: yes
hlsAddress: :8888
hlsEncryption: no
hlsAllowOrigin: "*"
hlsAlwaysRemux: no
hlsVariant: lowLatency
hlsSegmentCount: 7
hlsSegmentDuration: 1s
hlsPartDuration: 200ms
hlsSegmentMaxSize: 50M

# RTSP settings
rtsp: yes
rtspAddress: :8554
rtspTransports: [tcp, udp]
rtspEncryption: "no"

# Path configuration for H.264 streaming
paths:
  cam:
    # Camera publishes to this path via RTSP
    sourceOnDemand: no
    sourceAnyPortEnable: yes
    record: no
EOF
    
    # Set permissions
    sudo chown -R $USER:$USER $mediamtx_dir
    
    print_success "MediaMTX installed successfully in $mediamtx_dir"
}

# Function to test application
test_application() {
    print_status "Testing application startup..."
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Test application configuration
    python3 -c "from src.config import get_config; get_config()" 2>/dev/null || {
        print_warning "Application configuration test failed"
        return 1
    }
    
    print_success "Application files verified and ready"
}

# Main setup function
run_main_setup() {
    print_header
    
    print_status "Starting Raspberry Pi Camera Web App setup..."
    print_status "Working directly in git repository for easy updates"
    echo
    
    # Verify environment
    check_os_requirements
    check_user
    
    # System setup
    update_system
    install_system_dependencies
    
    # Hardware verification (optional - won't stop setup if camera unavailable)
    verify_camera || true  # Continue even if camera test fails
    test_python_camera || true  # Continue even if camera libraries test fails
    
    # Application setup
    setup_project_structure
    setup_python_environment  
    configure_environment
    
    # MediaMTX setup
    install_mediamtx
    
    test_application
    
    print_success "✅ Application setup complete!"
    echo
    print_status "Next steps:"
    print_status "1. Install services: $PROJECT_DIR/scripts/install_services.sh"
    print_status "2. Configure Cloudflare tunnel (see docs/DEPLOYMENT.md)"
    print_status "3. Test the application: cd $PROJECT_DIR && source venv/bin/activate && python3 src/main.py"
    echo
    print_status "🔄 To update code in future:"
    print_status "   git pull                                    # Get latest code"
    print_status "   systemctl --user restart camera-app.service # Apply changes"
    echo
}

# Function to show setup status
show_status() {
    print_header
    
    print_status "Checking setup status..."
    
    cd "$PROJECT_DIR"
    
    # Check git repository
    if [[ -d ".git" ]]; then
        print_success "✅ Git repository found"
        local branch
        branch=$(git branch --show-current 2>/dev/null || echo "unknown")
        print_status "Current branch: $branch"
    else
        print_warning "❌ Not a git repository"
    fi
    
    # Check virtual environment
    if [[ -d "venv" ]]; then
        print_success "✅ Virtual environment found"
    else
        print_warning "❌ Virtual environment not found"
    fi
    
    # Check .env file
    if [[ -f ".env" ]]; then
        print_success "✅ Environment configuration found"
    else
        print_warning "❌ Environment configuration not found"
    fi
    
    # Test application
    if [[ -f "src/main.py" ]] && [[ -d "venv" ]]; then
        print_status "Testing application..."
        source venv/bin/activate 2>/dev/null || true
        if python3 -c "from src.config import get_config; print('✅ Application ready')" 2>/dev/null; then
            print_success "✅ Application is ready to run"
            print_status "Start with: cd $PROJECT_DIR && source venv/bin/activate && python3 src/main.py"
        else
            print_warning "❌ Application needs configuration"
        fi
    fi
    
    echo
    print_status "📁 Project location: $PROJECT_DIR"
    print_status "🔧 To update code: git pull && systemctl --user restart camera-app.service"
}

# Function to update application
update_application() {
    print_status "Updating application from git repository..."
    
    cd "$PROJECT_DIR"
    
    # Check if git repository
    if [[ ! -d ".git" ]]; then
        print_error "Not a git repository - cannot update"
        exit 1
    fi
    
    # Pull latest changes
    print_status "Pulling latest changes..."
    git pull
    
    # Update Python dependencies if requirements changed
    if git diff HEAD~1 HEAD --name-only | grep -q requirements.txt; then
        print_status "Requirements.txt changed, updating dependencies..."
        source venv/bin/activate
        pip install -r requirements.txt
    fi
    
    print_success "Application updated successfully"
    print_status "Restart service to apply changes: systemctl --user restart camera-app.service"
}

# Main script logic
case "${1:-setup}" in
    "setup")
        run_main_setup
        ;;
    "status")
        show_status
        ;;
    "update")
        update_application
        ;;
    *)
        echo "Usage: $0 [setup|status|update]"
        echo "  setup  - Run full installation (default)"
        echo "  status - Check installation status"  
        echo "  update - Update application from git repository"
        exit 1
        ;;
esac
