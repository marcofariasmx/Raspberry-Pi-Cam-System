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
        MEDIAMTX_ARCH="arm64"
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
hlsVariant: lowLatency
hlsSegmentCount: 3
hlsSegmentDuration: 1s
hlsPartDuration: 200ms

# RTSP settings
rtsp: yes
rtspAddress: :8554
rtspTransports: [tcp, udp]
rtspEncryption: "no"

# Path configuration
paths:
  cam:
    source: udp://127.0.0.1:8891
    sourceProtocol: udp
    record: no
EOF

# Get current user and group
CURRENT_USER=$(whoami)
CURRENT_GROUP=$(id -gn)

echo "👤 Using user: $CURRENT_USER:$CURRENT_GROUP"

# Create systemd service for MediaMTX
sudo tee /etc/systemd/system/mediamtx.service > /dev/null << EOF
[Unit]
Description=MediaMTX Media Server
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$MEDIAMTX_DIR
ExecStart=$MEDIAMTX_DIR/mediamtx $MEDIAMTX_DIR/mediamtx.yml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Resource limits
LimitNOFILE=65536
MemoryLimit=256M

[Install]
WantedBy=multi-user.target
EOF

# Create log directory
sudo mkdir -p /var/log/mediamtx
sudo chown $CURRENT_USER:$CURRENT_GROUP /var/log/mediamtx

# Set permissions
sudo chown -R $CURRENT_USER:$CURRENT_GROUP $MEDIAMTX_DIR

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