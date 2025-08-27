# Low-Latency HLS (LL-HLS) Setup Guide

This guide explains how to set up and optimize Low-Latency HLS streaming for your Raspberry Pi camera system.

## What is LL-HLS?

Low-Latency HLS is an extension of the HTTP Live Streaming (HLS) protocol that significantly reduces streaming latency while maintaining broad compatibility. Key features:

- **Reduced Latency**: 2-3 seconds (vs 10-30 seconds for traditional HLS)
- **Partial Segments**: 200ms segments for faster delivery
- **Broad Compatibility**: Works on all modern browsers
- **Adaptive Bitrate**: Automatic quality adjustment
- **HTTP-based**: Works through firewalls and proxies

## Quick Start

### 1. Install MediaMTX with LL-HLS Support

```bash
# Run the automated installation script
sudo ./scripts/install_mediamtx.sh

# Verify installation
sudo systemctl status mediamtx
```

### 2. Start the Camera Application

```bash
# Start with default settings
python src/main.py

# Or with custom settings
H264_BITRATE=2000000 STREAM_FPS=30 python src/main.py
```

### 3. Access the Stream

Open your browser and navigate to:
```
http://your-pi-ip:8000
```

The web interface will automatically use LL-HLS as the primary streaming protocol.

## Configuration

### MediaMTX Configuration (mediamtx.yml)

The key LL-HLS settings in `/opt/mediamtx/mediamtx.yml`:

```yaml
# Low-Latency HLS Settings
hlsVariant: lowLatency        # Enable LL-HLS mode
hlsSegmentCount: 7             # Number of segments in playlist
hlsSegmentDuration: 1s         # Duration of each segment
hlsPartDuration: 200ms         # Duration of partial segments (key for low latency)
hlsSegmentMaxSize: 50M         # Maximum segment size
```

### Camera Application Settings

Environment variables for optimization:

```bash
# Stream Quality
export H264_BITRATE=1500000   # 1.5 Mbps (good balance)
export STREAM_WIDTH=1280      # HD width
export STREAM_HEIGHT=720      # HD height
export STREAM_FPS=30           # 30 FPS for smooth video

# HLS Specific
export MEDIAMTX_HLS_PORT=8888  # HLS server port
```

### Web Interface Configuration

The web interface (index.html) is configured with HLS.js optimizations:

```javascript
const hls = new Hls({
    lowLatencyMode: true,           // Enable LL-HLS mode
    liveSyncDurationCount: 2,       // Segments to stay behind live edge
    liveMaxLatencyDurationCount: 4, // Maximum latency tolerance
    maxBufferLength: 5,             // Maximum buffer in seconds
    // ... other optimizations
});
```

## Performance Optimization

### For Lowest Latency (2-3 seconds)

```bash
# MediaMTX settings
hlsPartDuration: 200ms
hlsSegmentDuration: 1s
hlsSegmentCount: 5

# Camera settings
export STREAM_FPS=30
export H264_BITRATE=2000000
```

### For Best Stability (3-5 seconds)

```bash
# MediaMTX settings
hlsPartDuration: 400ms
hlsSegmentDuration: 2s
hlsSegmentCount: 7

# Camera settings
export STREAM_FPS=15
export H264_BITRATE=1000000
```

### For Limited Bandwidth (5-7 seconds)

```bash
# MediaMTX settings
hlsPartDuration: 500ms
hlsSegmentDuration: 2s
hlsSegmentCount: 10

# Camera settings
export STREAM_FPS=10
export H264_BITRATE=500000
```

## Network Requirements

### Bandwidth Recommendations

| Resolution | FPS | Bitrate | Bandwidth Required |
|------------|-----|---------|-------------------|
| 640x480    | 15  | 500 Kbps | ~600 Kbps |
| 1280x720   | 15  | 1 Mbps   | ~1.2 Mbps |
| 1280x720   | 30  | 2 Mbps   | ~2.4 Mbps |
| 1920x1080  | 30  | 4 Mbps   | ~4.8 Mbps |

### Port Configuration

Ensure these ports are accessible:

- **8000**: Camera web interface
- **8554**: RTSP (camera → MediaMTX)
- **8888**: LL-HLS streaming
- **8443**: WebRTC (fallback)
- **9997**: MediaMTX API

```bash
# Open ports with UFW
sudo ufw allow 8000/tcp
sudo ufw allow 8888/tcp
sudo ufw allow 8443/tcp
```

## Browser Compatibility

### Native Support (Best Performance)
- Safari (iOS/macOS): Full native LL-HLS support
- Edge: Native HLS support

### HLS.js Support (Good Performance)
- Chrome: Full LL-HLS with HLS.js
- Firefox: Full LL-HLS with HLS.js
- Opera: Full LL-HLS with HLS.js

## Monitoring and Debugging

### Check MediaMTX Status

```bash
# View service status
sudo systemctl status mediamtx

# View logs
journalctl -u mediamtx -f

# Check active streams
curl http://localhost:9997/v3/paths/list
```

### Monitor Stream Metrics

```bash
# Get stream metrics
curl http://localhost:9997/v3/paths/get/cam

# Check HLS segments
ls -la /tmp/mediamtx-hls/cam/
```

### Browser Console

Check browser console for HLS.js debug information:
```javascript
// Enable debug logging
localStorage.debug = 'hls:*'
```

## Troubleshooting

### High Latency Issues

1. **Check segment duration**:
   ```bash
   # Reduce segment duration in mediamtx.yml
   hlsSegmentDuration: 500ms
   hlsPartDuration: 100ms
   ```

2. **Optimize encoding**:
   ```bash
   # Use lower GOP size
   export H264_BITRATE=1500000
   export STREAM_FPS=25
   ```

3. **Check network**:
   ```bash
   # Test network latency
   ping -c 10 your-pi-ip
   ```

### Stream Not Loading

1. **Verify MediaMTX is running**:
   ```bash
   sudo systemctl restart mediamtx
   ```

2. **Check camera is streaming**:
   ```bash
   curl http://localhost:8000/api/camera/stream/info
   ```

3. **Test HLS endpoint directly**:
   ```bash
   curl -I http://localhost:8888/cam/index.m3u8
   ```

### Playback Stuttering

1. **Reduce quality settings**:
   ```bash
   export H264_BITRATE=750000
   export STREAM_WIDTH=640
   export STREAM_HEIGHT=480
   ```

2. **Increase buffer**:
   ```yaml
   # In mediamtx.yml
   hlsSegmentCount: 10
   ```

3. **Check CPU usage**:
   ```bash
   top -d 1
   ```

## Advanced Configuration

### Custom Segment Settings

For ultra-low latency (experimental):
```yaml
hlsVariant: lowLatency
hlsSegmentDuration: 500ms
hlsPartDuration: 100ms
hlsSegmentCount: 4
```

### Adaptive Bitrate Streaming

Create multiple quality streams:
```yaml
paths:
  cam_high:
    source: publisher
    # High quality: 1080p
  
  cam_medium:
    source: publisher
    # Medium quality: 720p
  
  cam_low:
    source: publisher  
    # Low quality: 480p
```

### CDN Integration

For scalability, integrate with a CDN:
```nginx
location /hls/ {
    proxy_pass http://localhost:8888/;
    proxy_cache_valid 200 1s;
    add_header Cache-Control "public, max-age=1";
}
```

## Comparison with Other Protocols

| Protocol | Latency | Browser Support | Bandwidth | Complexity |
|----------|---------|----------------|-----------|------------|
| **LL-HLS** | 2-3s | Excellent | Medium | Medium |
| WebRTC | 0.5-1s | Good | Low | High |
| Traditional HLS | 10-30s | Excellent | Medium | Low |
| MJPEG | 0.5-1s | Excellent | Very High | Low |
| RTSP | 0.5-2s | None* | Low | Medium |

*Requires VLC or special players

## Best Practices

1. **Start with default settings** and optimize based on your needs
2. **Monitor metrics** regularly to ensure optimal performance
3. **Use wired connection** when possible for best stability
4. **Test on target devices** to ensure compatibility
5. **Keep MediaMTX updated** for latest LL-HLS improvements

## Resources

- [MediaMTX Documentation](https://github.com/bluenviron/mediamtx)
- [HLS.js Documentation](https://github.com/video-dev/hls.js)
- [Apple LL-HLS Specification](https://developer.apple.com/documentation/http_live_streaming)
- [Project Repository](https://github.com/your-repo/Raspberry-Pi-Cam-System)