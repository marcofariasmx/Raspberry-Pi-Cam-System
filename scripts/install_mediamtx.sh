#!/bin/bash

# MediaMTX Installation Script for Raspberry Pi Zero 2W
# Downloads and configures MediaMTX for H.264 streaming

set -e

echo "🎬 Installing MediaMTX for Raspberry Pi Zero 2W..."

# Detect architecture
ARCH=$(uname -m)
case $ARCH in
    armv6l)
        MEDIAMTX_ARCH="armv6"
        ;;
    armv7l)
        MEDIAMTX_ARCH="armv7"
        ;;
    aarch64)
        MEDIAMTX_ARCH="arm64v8"
        ;;
    *)
        echo "❌ Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

echo "📱 Detected architecture: $ARCH (using $MEDIAMTX_ARCH)"

# Create MediaMTX directory
MEDIAMTX_DIR="/opt/mediamtx"
sudo mkdir -p $MEDIAMTX_DIR

# Download latest MediaMTX release
echo "⬇️  Downloading MediaMTX..."
LATEST_VERSION=$(curl -s https://api.github.com/repos/bluenviron/mediamtx/releases/latest | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/')
DOWNLOAD_URL="https://github.com/bluenviron/mediamtx/releases/download/${LATEST_VERSION}/mediamtx_${LATEST_VERSION}_linux_${MEDIAMTX_ARCH}.tar.gz"

echo "📦 Downloading: $DOWNLOAD_URL"
curl -L $DOWNLOAD_URL | sudo tar -xz -C $MEDIAMTX_DIR

# Make executable
sudo chmod +x $MEDIAMTX_DIR/mediamtx

# Create configuration directory
sudo mkdir -p $MEDIAMTX_DIR/config

# Create MediaMTX configuration file optimized for Pi Zero 2W
sudo tee $MEDIAMTX_DIR/mediamtx.yml > /dev/null << 'EOF'
# MediaMTX Configuration for Raspberry Pi Zero 2W H.264 Streaming
# Optimized for low resource usage and maximum efficiency

# General settings
logLevel: info
logDestinations: [stdout]
logFile: mediamtx.log

# API settings
api: yes
apiAddress: 127.0.0.1:9997

# Metrics (lightweight monitoring)
metrics: yes
metricsAddress: 127.0.0.1:9998

# WebRTC settings (optimized for low latency)
webrtc: yes
webrtcAddress: :8889
webrtcEncryption: no  # Reduce CPU overhead on Pi Zero 2W
webrtcServerKey: server.key
webrtcServerCert: server.crt
webrtcAllowOrigin: "*"
webrtcTrustedProxies: []
webrtcLocalUDPAddress: :8000
webrtcLocalTCPAddress: :8001

# HLS settings (fallback for non-WebRTC browsers)
hls: yes
hlsAddress: :8888
hlsEncryption: no
hlsServerKey: server.key
hlsServerCert: server.crt
hlsAllowOrigin: "*"
hlsTrustedProxies: []
hlsAlwaysRemux: no
hlsVariant: lowLatency
hlsSegmentCount: 3
hlsSegmentDuration: 1s
hlsPartDuration: 200ms
hlsSegmentMaxSize: 50M

# RTSP settings (for debugging and testing)
rtsp: yes
rtspAddress: :8554
protocols: [tcp, udp]
encryption: "no"
serverKey: server.key
serverCert: server.crt
authMethods: []

# Path configuration for camera stream
paths:
  cam:
    # Source will be the UDP stream from picamera2
    source: udp://127.0.0.1:8890
    sourceProtocol: udp
    
    # Enable all protocols for maximum compatibility
    publishUser: ""
    publishPass: ""
    publishIPs: []
    readUser: ""
    readPass: ""
    readIPs: []
    
    # Recording disabled to save resources
    record: no
    
    # WebRTC optimization
    runOnInit: ""
    runOnInitRestart: no
    runOnDemand: ""
    runOnDemandRestart: no
    runOnDemandStartTimeout: 10s
    runOnDemandCloseAfter: 10s
    runOnReady: ""
    runOnReadyRestart: no
    runOnNotReady: ""
    runOnNotReadyRestart: no
    runOnRead: ""
    runOnReadRestart: no
    runOnUnread: ""
    runOnUnreadRestart: no
EOF

# Create systemd service for MediaMTX
sudo tee /etc/systemd/system/mediamtx.service > /dev/null << EOF
[Unit]
Description=MediaMTX Media Server
After=network.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=$MEDIAMTX_DIR
ExecStart=$MEDIAMTX_DIR/mediamtx $MEDIAMTX_DIR/mediamtx.yml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Resource limits for Pi Zero 2W
LimitNOFILE=65536
MemoryLimit=256M

[Install]
WantedBy=multi-user.target
EOF

# Create log directory
sudo mkdir -p /var/log/mediamtx
sudo chown pi:pi /var/log/mediamtx

# Set permissions
sudo chown -R pi:pi $MEDIAMTX_DIR

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable mediamtx

echo "✅ MediaMTX installed successfully!"
echo "📍 Installation directory: $MEDIAMTX_DIR"
echo "🔧 Configuration file: $MEDIAMTX_DIR/mediamtx.yml"
echo ""
echo "🚀 To start MediaMTX:"
echo "   sudo systemctl start mediamtx"
echo ""
echo "📊 To check status:"
echo "   sudo systemctl status mediamtx"
echo ""
echo "🔍 To view logs:"
echo "   journalctl -u mediamtx -f"
echo ""
echo "🌐 Stream URLs (after starting your camera app):"
echo "   WebRTC: http://your-pi-ip:8889/cam/whep"
echo "   HLS: http://your-pi-ip:8888/cam/index.m3u8"
echo "   RTSP: rtsp://your-pi-ip:8554/cam"