# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Essential Commands

### Setup and Installation
```bash
# Initial setup (run once after cloning)
chmod +x scripts/*.sh
./scripts/setup.sh

# Install systemd services for auto-start
./scripts/install_services.sh

# Check setup status
./scripts/setup.sh status

# Update application from git
./scripts/setup.sh update
```

### Development
```bash
# Activate Python environment
source venv/bin/activate

# Run application manually (development)
python3 src/main.py

# Test application configuration
python3 -c "from src.config import get_config; get_config()"

# Test camera libraries
python3 -c "from picamera2 import Picamera2; print('Camera libraries working')"
```

### Service Management
```bash
# Service control
systemctl --user status camera-app.service    # Check status
systemctl --user restart camera-app.service   # Restart
systemctl --user stop camera-app.service      # Stop
systemctl --user start camera-app.service     # Start

# View application logs
tmux attach -t camera-app

# Quick status and restart scripts
./camera_status.sh     # Check all system status
./restart_camera.sh    # Restart service
```

### Testing and Health Checks
```bash
# Test HTTP endpoints
curl -s http://127.0.0.1:8003/health | python3 -m json.tool

# Test camera hardware
libcamera-hello -t 5000

# Check network connectivity
curl -I https://camera.yourdomain.com/health

# Test new efficient streaming system
python3 test_efficient_streaming.py
```

## Architecture Overview

### Core System Design
This is a **FastAPI-based Raspberry Pi camera web application** with a modular architecture:

- **FastAPI Backend** (`src/main.py`) - Web server and API endpoints
- **Camera Manager** (`src/camera/camera_manager.py`) - Main orchestrator for all camera operations
- **Modular Camera System** (`src/camera/`) - Specialized modules for different camera functions
- **Configuration Management** (`src/config.py`) - Environment-based configuration with automatic credential generation

### Key Architectural Patterns

#### 1. Modular Camera System
The camera functionality is split into focused modules:
- `hardware_detection.py` - Auto-detects camera modules and capabilities
- `photo_capture.py` - High-resolution photo capture while streaming
- `streaming/` directory - Video streaming with adaptive quality
- `health_monitor.py` - System health monitoring and diagnostics
- `recovery_manager.py` - Automatic error recovery
- `session_manager.py` - Session and authentication management

#### 2. Streaming Architecture
**Dual-stream configuration** allows simultaneous high-quality photos and efficient streaming:
- **Main stream** - High resolution for photo capture
- **Low-res stream** - Optimized for video streaming
- **Adaptive quality** - Dynamic adjustment based on network conditions
- **Shared frame queue** - Efficient memory management for multiple clients

#### 3. Service Management
Uses **systemd user services** with **tmux sessions** for:
- Auto-start on boot (with user lingering)
- Easy log access and debugging
- Professional service management
- Git-based updates without reinstallation

#### 4. Configuration System
**Environment-driven configuration** with automatic security:
- Auto-generates secure credentials on first run
- All settings configurable via `.env` file
- Runtime configuration validation
- Development vs production mode support

### Important Implementation Details

#### Camera Module Detection
The system automatically detects Camera Module 2, 3, and other variants:
```python
# Hardware detection pattern used throughout
from src.camera.hardware_detection import HardwareDetector
detector = HardwareDetector()
camera_config = detector.configure_camera()
```

#### Streaming Quality Adaptation
Implements adaptive streaming for different network conditions:
- Network performance monitoring
- Dynamic quality adjustment
- Queue metrics and time-window analysis
- Client-specific stream management

#### Error Handling and Recovery
Robust error handling with automatic recovery:
- Graceful camera initialization fallbacks
- Automatic restart on streaming errors
- Health monitoring with configurable thresholds
- Exception handling with context preservation

### Security Architecture
- **Automatic credential generation** - No default passwords
- **API key authentication** for API endpoints
- **Session-based web authentication** for UI
- **Environment-based secrets** - All credentials in `.env`
- **HTTPS support** via Cloudflare Tunnel integration

## Development Guidelines

### Working with Camera Code
1. **Always check hardware availability** - The code includes graceful fallbacks for development environments without camera hardware
2. **Test streaming changes carefully** - Streaming affects multiple clients and has memory implications
3. **Respect the modular architecture** - Keep camera logic in specialized modules rather than main.py

### Configuration Changes
1. **Use environment variables** - All configuration should be in `.env` or environment variables
2. **Test configuration validation** - The config system validates all settings on startup
3. **Document new config options** - Update `.env.example` for new configuration options

### Service Integration
1. **Test systemd service changes** - Service configuration affects auto-start behavior
2. **Verify tmux session compatibility** - Logging and debugging depend on tmux integration
3. **Check user lingering requirements** - Auto-start requires proper user session configuration

### Testing Strategy
- **Hardware tests** use `libcamera-hello` for camera verification
- **Application tests** use configuration imports and health endpoints
- **Service tests** use systemctl status checks and HTTP endpoint tests
- **No formal test framework** - Testing is done via setup scripts and manual verification

## File Structure Notes

### Critical Files
- `src/main.py` - FastAPI application entry point and route definitions
- `src/config.py` - Configuration management with automatic credential generation
- `src/camera/camera_manager.py` - Main camera orchestrator
- `scripts/setup.sh` - Primary installation and configuration script
- `scripts/install_services.sh` - Systemd service installation
- `.env` - Runtime configuration (created by setup, not in git)

### Streaming Module Organization
The `src/camera/streaming/` directory contains the efficient streaming components:

- `efficient_streaming_system.py` - Main coordinator for efficient streaming
- `multi_quality_producer.py` - Produces multiple JPEG quality levels from single frame
- `simple_client_manager.py` - Per-client adaptive quality management  
- `network_performance_tracker.py` - Simple network performance monitoring
- `streaming_stats.py` - Performance statistics tracking

### Auto-Generated Files
These files are created by the setup process:
- `.env` - Environment configuration
- `camera_status.sh` - Status checking script
- `restart_camera.sh` - Service restart script
- `venv/` - Python virtual environment
- `captured_images/` - Photo storage directory

## Update Workflow

This project uses a **git-based update workflow**:

1. **Pull latest code**: `git pull`
2. **Update dependencies** (if needed): `./scripts/setup.sh update`
3. **Restart service**: `systemctl --user restart camera-app.service`
4. **Verify operation**: `./camera_status.sh`

The entire application runs from the git repository, making updates seamless without reinstallation.

## Efficient Streaming System

### Key Features
The efficient streaming system provides optimal performance for Raspberry Pi camera streaming:

- **Memory Efficiency**: <400KB total memory usage (Pi Zero 2W compatible)
- **Per-Client Quality**: Each client gets optimal quality independent of others
- **Simple Architecture**: 4 core components vs 11+ complex files
- **Real-Time Adaptation**: 3-5 second adaptation vs 10-30 seconds
- **Multi-Quality Production**: Produces 4 quality levels (30%, 50%, 70%, 85%) from single frame

### Architecture Benefits
- **No Shared State**: Clients don't affect each other
- **Immediate Encoding**: No frame queues or buffering
- **Simple Network Metrics**: Average delivery time over 5 frames
- **Progressive Quality Steps**: ±10-15% quality adjustments
- **Hardware Optimization**: Uses GPU-based JPEG encoding when available

### API Endpoints
```bash
# Stream with client-specific adaptation
GET /api/camera/stream?client_id=client_1

# Get all active clients
GET /api/camera/stream/clients

# Get specific client info
GET /api/camera/stream/clients/{client_id}

# Force client quality
POST /api/camera/stream/clients/{client_id}/quality

# Disconnect client
DELETE /api/camera/stream/clients/{client_id}

# Memory efficiency report
GET /api/camera/stream/efficiency
```

### Development Notes
- System designed for Pi Zero 2W with <500MB RAM
- Per-client adaptation prevents "worst client affects all" problem  
- Simple network measurement for fast adaptation
- Hardware-accelerated JPEG encoding when available