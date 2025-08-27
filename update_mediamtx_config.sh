#!/bin/bash

#######################################
# Update MediaMTX Configuration for LL-HLS
# This script updates your existing MediaMTX 
# configuration to use LL-HLS optimizations
#######################################

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration paths
MEDIAMTX_CONFIG="/opt/mediamtx/mediamtx.yml"
BACKUP_CONFIG="/opt/mediamtx/mediamtx.yml.backup"

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

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run with sudo"
        echo "Usage: sudo ./update_mediamtx_config.sh"
        exit 1
    fi
}

# Backup existing configuration
backup_config() {
    if [ -f "$MEDIAMTX_CONFIG" ]; then
        print_status "Backing up existing MediaMTX configuration..."
        cp "$MEDIAMTX_CONFIG" "$BACKUP_CONFIG"
        print_success "Backup saved to: $BACKUP_CONFIG"
    else
        print_warning "No existing configuration found at $MEDIAMTX_CONFIG"
    fi
}

# Apply LL-HLS optimized configuration
update_config() {
    print_status "Applying LL-HLS optimized configuration..."
    
    # Use the configuration from the project directory if it exists
    if [ -f "mediamtx.yml" ]; then
        print_status "Using configuration from current directory"
        cp mediamtx.yml "$MEDIAMTX_CONFIG"
    else
        # Create the LL-HLS optimized configuration
        cat > "$MEDIAMTX_CONFIG" << 'EOF'
###############################################
# MediaMTX Configuration - Optimized for LL-HLS
###############################################

# Global settings
logLevel: info
logDestinations: [stdout]
logFile: mediamtx.log

# API Configuration
api: yes
apiAddress: :9997

# Metrics
metrics: yes
metricsAddress: :9998

# PPROF for debugging (disable in production)
pprof: no
pprofAddress: :9999

# Recording settings
record: no
recordPath: ./recordings

# Playback settings
playback: no

# RTSP Server Configuration
rtsp: yes
rtspDisable: no
protocols: [tcp, udp]
rtspAddress: :8554
rtspsAddress: :8322
rtpAddress: :8000
rtcpAddress: :8001
multicastIPRange: 224.1.0.0/16
multicastRTPPort: 8002
multicastRTCPPort: 8003
serverKey: server.key
serverCert: server.crt
authMethods: [basic, digest]

# RTMP Server Configuration (disabled - not needed for HLS)
rtmp: no

# HLS Configuration - Optimized for Low Latency
hls: yes
hlsDisable: no
hlsAddress: :8888
hlsEncryption: no
hlsServerKey: server.key
hlsServerCert: server.crt
hlsAlwaysRemux: no
hlsAllowOrigin: "*"

# Low-Latency HLS (LL-HLS) Settings
hlsVariant: lowLatency

# Segment settings for LL-HLS
hlsSegmentCount: 7           # Number of segments in playlist
hlsSegmentDuration: 1s        # Duration of each segment (1s for LL-HLS)
hlsPartDuration: 200ms        # Duration of partial segments (200ms for low latency)
hlsSegmentMaxSize: 50M        # Max size of each segment

# Directory for HLS files
hlsDirectory: /tmp/mediamtx-hls

# WebRTC Configuration (as secondary option)
webrtc: yes
webrtcDisable: no
webrtcAddress: :8443
webrtcServerKey: server.key
webrtcServerCert: server.crt
webrtcLocalUDPAddress: :8189
webrtcLocalTCPAddress: :8189
webrtcIPsFromInterfaces: yes
webrtcIPsFromInterfacesList: []
webrtcAdditionalHosts: []
webrtcICEServers: []
webrtcAllowOrigin: "*"

# Path Configuration for Camera Stream
paths:
  cam:
    # Accept stream from Raspberry Pi camera via RTSP
    source: publisher
    
    # Enable source on demand
    sourceOnDemand: no
    sourceOnDemandStartTimeout: 10s
    sourceOnDemandCloseAfter: 10s
    
    # Disable recording for this path
    record: no
    
    # Enable HLS with LL-HLS optimizations
    publishUser:
    publishPass:
    publishIPs: [127.0.0.1, 192.168.0.0/16, 10.0.0.0/8]
    readUser:
    readPass:
    readIPs: []
    
    # Override HLS settings for this path
    overridePublisher: yes
    fallback:
    
    # Additional source protocol settings
    sourceProtocol: automatic
    sourceAnyPortEnable: yes
    sourceFingerprint:
    sourceOnDemandCmd:
    sourceOnDemandCloseAfterCmd:
    sourceRedirect:
    
    # Disable unneeded features
    disablePublisherOverride: no
    rpiCameraWidth:
    rpiCameraHeight:
    
    # Run commands
    runOnInit:
    runOnInitRestart: no
    runOnDemand:
    runOnDemandRestart: no
    runOnDemandStartTimeout: 10s
    runOnDemandCloseAfter: 10s
    runOnPublish:
    runOnPublishRestart: no
    runOnRead:
    runOnReadRestart: no
    runOnReady:
    runOnReadyRestart: no
    runOnNotReady:
    runOnDelete:
EOF
    fi
    
    print_success "LL-HLS configuration applied successfully"
}

# Restart MediaMTX service
restart_service() {
    print_status "Restarting MediaMTX service..."
    
    systemctl restart mediamtx
    sleep 3
    
    if systemctl is-active --quiet mediamtx; then
        print_success "MediaMTX service restarted successfully"
    else
        print_error "Failed to restart MediaMTX service"
        print_warning "Check logs with: journalctl -u mediamtx -n 50"
        exit 1
    fi
}

# Test MediaMTX API
test_mediamtx() {
    print_status "Testing MediaMTX API..."
    
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:9997/v3/config | grep -q "200"; then
        print_success "MediaMTX API is responding"
    else
        print_warning "MediaMTX API not responding yet"
    fi
}

# Show configuration summary
show_summary() {
    echo ""
    echo "========================================"
    print_success "MediaMTX LL-HLS Configuration Updated!"
    echo "========================================"
    echo ""
    print_status "Key LL-HLS Settings Applied:"
    echo "  • Variant: lowLatency"
    echo "  • Segment Duration: 1s"
    echo "  • Part Duration: 200ms (ultra-low latency)"
    echo "  • Segment Count: 7"
    echo "  • Expected Latency: 2-3 seconds"
    echo ""
    print_status "Streaming Endpoints:"
    echo "  • LL-HLS: http://$(hostname -I | awk '{print $1}'):8888/cam/index.m3u8"
    echo "  • WebRTC: http://$(hostname -I | awk '{print $1}'):8443/cam/whep"
    echo "  • RTSP:   rtsp://$(hostname -I | awk '{print $1}'):8554/cam"
    echo ""
    print_status "Management Commands:"
    echo "  • Status:  sudo systemctl status mediamtx"
    echo "  • Logs:    sudo journalctl -u mediamtx -f"
    echo "  • Restart: sudo systemctl restart mediamtx"
    echo ""
    if [ -f "$BACKUP_CONFIG" ]; then
        print_status "Restore backup if needed:"
        echo "  sudo cp $BACKUP_CONFIG $MEDIAMTX_CONFIG"
        echo "  sudo systemctl restart mediamtx"
    fi
}

# Main execution
main() {
    echo "========================================"
    echo "  MediaMTX LL-HLS Configuration Update"
    echo "========================================"
    echo ""
    
    check_root
    backup_config
    update_config
    restart_service
    test_mediamtx
    show_summary
}

# Run main function
main