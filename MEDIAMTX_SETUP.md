# MediaMTX + H.264 Streaming Setup

This guide explains how to set up and use the new MediaMTX + H.264 streaming functionality for ultra-low latency and efficient video streaming.

## Overview

The system now supports two streaming modes:

1. **H.264 via MediaMTX** (Primary, recommended)
   - Hardware-encoded H.264 streaming
   - WebRTC for ultra-low latency (50-150ms)
   - HLS fallback for broader compatibility
   - ~80% bandwidth reduction vs MJPEG

2. **MJPEG** (Legacy fallback)
   - Direct MJPEG streaming
   - Instant browser compatibility
   - Higher bandwidth usage

## Quick Start

### 1. Install MediaMTX

```bash
# Run the installation script
./scripts/install_mediamtx.sh

# Start MediaMTX service
sudo systemctl start mediamtx
sudo systemctl status mediamtx
```

### 2. Configure Streaming Mode

**Option A: Environment Variables**
```bash
export H264_ENABLED=true
export H264_BITRATE=1000000  # 1 Mbps
export STREAM_WIDTH=640
export STREAM_HEIGHT=480
```

**Option B: .env File**
```
H264_ENABLED=true
H264_BITRATE=1000000
STREAM_WIDTH=640
STREAM_HEIGHT=480
STREAM_FPS=15
```

### 3. Start the Camera Application

```bash
python src/main.py
```

The web interface will automatically detect the best streaming protocol:
1. **WebRTC** (if supported) - Ultra-low latency
2. **HLS** (fallback) - Good compatibility  
3. **MJPEG** (final fallback) - Universal compatibility

## Streaming Endpoints

### MediaMTX Streams (H.264)
- **WebRTC**: `http://your-pi:8443/cam/whep`
- **HLS**: `http://your-pi:8888/cam/index.m3u8` 
- **RTSP**: `rtsp://your-pi:8554/cam`

### Legacy Streams
- **MJPEG**: `http://your-pi:8000/api/camera/stream/mjpeg`

### API Endpoints
- **Stream Info**: `GET /api/camera/stream/info`
- **Metrics**: `GET /api/camera/metrics`
- **Primary Stream**: `GET /api/camera/stream`

## Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `H264_ENABLED` | `true` | Enable H.264 streaming via MediaMTX |
| `H264_BITRATE` | `1000000` | H.264 bitrate in bps (1 Mbps) |
| `STREAM_WIDTH` | `640` | Stream width in pixels |
| `STREAM_HEIGHT` | `480` | Stream height in pixels |
| `STREAM_FPS` | `15` | Target frames per second |
| `MEDIAMTX_WEBRTC_PORT` | `8443` | MediaMTX WebRTC port |
| `MEDIAMTX_HLS_PORT` | `8888` | MediaMTX HLS port |
| `MEDIAMTX_UDP_PORT` | `8890` | UDP port for camera → MediaMTX |

## Performance Optimization

### Raspberry Pi Models

**Pi Zero 2W / Pi 4 / Pi 3** (Hardware H.264 encoding available):
- ✅ Recommended: H.264 @ 1-2 Mbps
- ✅ CPU usage: ~5-10%
- ✅ Bandwidth: ~1-2 Mbps

**Pi 5** (Software H.264 encoding only):
- ⚠️ Higher CPU usage for H.264
- 💡 Consider MJPEG for lower-end applications
- 💡 Use higher bitrates if CPU allows

### Bitrate Guidelines

| Resolution | Recommended Bitrate | Quality |
|------------|-------------------|---------|
| 320x240 | 250 Kbps | Basic |
| 640x480 | 1 Mbps | Good |
| 1280x720 | 2-3 Mbps | High |
| 1920x1080 | 4-6 Mbps | Very High |

### Network Optimization

**WiFi Networks:**
- 2.4GHz: Up to 2-3 Mbps recommended
- 5GHz: Up to 5-10 Mbps possible

**Ethernet:**
- No bandwidth limitations for typical streaming

## Troubleshooting

### MediaMTX Not Starting

```bash
# Check MediaMTX status
sudo systemctl status mediamtx

# View MediaMTX logs
journalctl -u mediamtx -f

# Test MediaMTX manually
cd /opt/mediamtx
sudo ./mediamtx mediamtx.yml
```

### WebRTC Connection Issues

1. **Check browser support**: Modern Chrome/Firefox required
2. **Check ports**: Ensure ports 8443, 8888, 8890 are accessible
3. **Check firewall**: Allow MediaMTX ports through firewall
4. **Check logs**: Browser console and MediaMTX logs

### High CPU Usage

1. **Reduce bitrate**: Lower `H264_BITRATE` setting
2. **Reduce resolution**: Lower `STREAM_WIDTH/HEIGHT`
3. **Reduce FPS**: Lower `STREAM_FPS`
4. **Check Pi model**: Pi 5 has no hardware encoding

### Streaming Latency

**Expected Latency:**
- WebRTC: 50-150ms
- HLS: 2-5 seconds
- MJPEG: 100-300ms

**Reducing Latency:**
1. Use WebRTC when possible
2. Reduce network hops
3. Use wired connection
4. Optimize MediaMTX settings

## Service Management

### MediaMTX Service Commands

```bash
# Start MediaMTX
sudo systemctl start mediamtx

# Stop MediaMTX
sudo systemctl stop mediamtx

# Restart MediaMTX
sudo systemctl restart mediamtx

# Enable auto-start
sudo systemctl enable mediamtx

# Disable auto-start
sudo systemctl disable mediamtx

# View status
sudo systemctl status mediamtx

# View logs
journalctl -u mediamtx -f
```

### Camera Application

```bash
# Start camera app
python src/main.py

# Start with custom config
H264_BITRATE=2000000 python src/main.py

# Background service (example)
nohup python src/main.py > camera.log 2>&1 &
```

## Advanced Configuration

### MediaMTX Configuration

The MediaMTX configuration file is located at `/opt/mediamtx/mediamtx.yml`. 

Key settings for optimization:

```yaml
# Reduce latency
hlsSegmentDuration: 1s
hlsPartDuration: 200ms
hlsSegmentCount: 3

# Disable encryption for lower CPU
webrtcEncryption: no
hlsEncryption: no

# Resource limits
paths:
  cam:
    source: udp://127.0.0.1:8890
    record: no  # Disable recording to save CPU/disk
```

### Multiple Streams

You can run multiple camera streams by:

1. Using different UDP ports
2. Creating different MediaMTX paths
3. Running multiple camera instances

Example for dual cameras:
```bash
# Camera 1
MEDIAMTX_UDP_PORT=8890 CAMERA_PORT=8000 python src/main.py &

# Camera 2  
MEDIAMTX_UDP_PORT=8891 CAMERA_PORT=8001 python src/main.py &
```

## Migration from MJPEG

### Automatic Migration

The system automatically uses H.264 when `H264_ENABLED=true`. No code changes needed.

### Manual Migration Steps

1. Install MediaMTX: `./scripts/install_mediamtx.sh`
2. Update configuration: Set `H264_ENABLED=true`
3. Restart application
4. Test streaming in browser
5. Adjust bitrate as needed

### Rollback to MJPEG

```bash
export H264_ENABLED=false
python src/main.py
```

Or set `H264_ENABLED=false` in your `.env` file.

## Monitoring and Metrics

### Web Interface Metrics

The web interface shows:
- Current protocol (WebRTC/HLS/MJPEG)
- Stream resolution and FPS
- Bitrate/quality settings
- Connection latency
- Stream status

### API Metrics

```bash
# Get current metrics
curl http://your-pi:8000/api/camera/metrics

# Get stream information
curl http://your-pi:8000/api/camera/stream/info
```

### MediaMTX Metrics

MediaMTX provides metrics at: `http://your-pi:9998/metrics`

```bash
# View MediaMTX metrics
curl http://localhost:9998/metrics
```

## Security Considerations

### Network Security

1. **Use private networks**: Don't expose streaming ports to internet
2. **Firewall rules**: Only allow necessary ports
3. **Authentication**: Consider adding authentication to MediaMTX
4. **HTTPS**: Use HTTPS for production deployments

### Default Ports

- 8000: Camera application (HTTP)
- 8554: MediaMTX RTSP
- 8888: MediaMTX HLS 
- 8443: MediaMTX WebRTC
- 8890: UDP stream (camera → MediaMTX)
- 9997: MediaMTX API
- 9998: MediaMTX metrics

### Firewall Configuration

```bash
# Allow camera streaming ports
sudo ufw allow 8000/tcp   # Camera app
sudo ufw allow 8888/tcp   # HLS
sudo ufw allow 8443/tcp   # WebRTC
sudo ufw allow 8554/tcp   # RTSP

# Block external access to internal ports
sudo ufw deny 8890/udp    # Internal UDP
sudo ufw deny 9997/tcp    # Internal API
sudo ufw deny 9998/tcp    # Internal metrics
```