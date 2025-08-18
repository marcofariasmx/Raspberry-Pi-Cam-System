/**
 * Frontend Metrics System
 * Measures what only the client can know: true FPS, latency, connection quality
 */

class TrueFPSMeasurer {
    constructor() {
        this.frameTimestamps = [];
        this.maxSamples = 30; // 1 second at 30fps
        this.fps = 0;
        this.jitter = 0;
        this.totalFrames = 0;
    }
    
    onFrameReceived() {
        const now = performance.now();
        this.frameTimestamps.push(now);
        this.totalFrames++;
        
        // Keep only recent samples
        if (this.frameTimestamps.length > this.maxSamples) {
            this.frameTimestamps.shift();
        }
        
        // Calculate FPS and jitter
        if (this.frameTimestamps.length >= 3) {
            this.calculateMetrics();
        }
    }
    
    calculateMetrics() {
        const timestamps = this.frameTimestamps;
        const intervals = [];
        
        // Calculate intervals between frames
        for (let i = 1; i < timestamps.length; i++) {
            intervals.push(timestamps[i] - timestamps[i - 1]);
        }
        
        if (intervals.length === 0) return;
        
        // Calculate FPS
        const avgInterval = intervals.reduce((a, b) => a + b) / intervals.length;
        this.fps = 1000 / avgInterval; // Convert ms to fps
        
        // Calculate jitter (standard deviation of intervals)
        const variance = intervals.reduce((acc, val) => acc + Math.pow(val - avgInterval, 2), 0) / intervals.length;
        this.jitter = Math.sqrt(variance);
    }
    
    getMetrics() {
        return {
            fps: Math.round(this.fps * 10) / 10,
            jitter_ms: Math.round(this.jitter * 10) / 10,
            total_frames: this.totalFrames,
            samples: this.frameTimestamps.length,
            is_stable: this.jitter < 50, // <50ms jitter = stable
            timestamp: Date.now()
        };
    }
    
    reset() {
        this.frameTimestamps = [];
        this.fps = 0;
        this.jitter = 0;
        this.totalFrames = 0;
    }
}

class LatencyMeasurer {
    constructor() {
        this.measurements = [];
        this.maxMeasurements = 20;
        this.isRunning = false;
        this.measurementInterval = null;
    }
    
    start() {
        if (this.isRunning) return;
        
        this.isRunning = true;
        this.measurementInterval = setInterval(() => {
            this.measureLatency();
        }, 5000); // Measure every 5 seconds
        
        // Take immediate measurement
        this.measureLatency();
    }
    
    stop() {
        this.isRunning = false;
        if (this.measurementInterval) {
            clearInterval(this.measurementInterval);
            this.measurementInterval = null;
        }
    }
    
    async measureLatency() {
        const start = performance.now();
        
        try {
            const response = await fetch('/health', {
                method: 'HEAD',
                cache: 'no-cache',
                headers: {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            });
            
            if (response.ok) {
                const latency = performance.now() - start;
                this.recordMeasurement(latency, true);
            } else {
                this.recordMeasurement(null, false);
            }
        } catch (error) {
            this.recordMeasurement(null, false);
        }
    }
    
    recordMeasurement(latency, success) {
        this.measurements.push({
            latency,
            success,
            timestamp: Date.now()
        });
        
        // Keep only recent measurements
        if (this.measurements.length > this.maxMeasurements) {
            this.measurements.shift();
        }
    }
    
    getMetrics() {
        const successful = this.measurements.filter(m => m.success);
        const recent = this.measurements.slice(-10);
        const recentSuccessful = recent.filter(m => m.success);
        
        if (successful.length === 0) {
            return {
                latency_ms: null,
                success_rate: 0,
                samples: this.measurements.length,
                is_connected: false
            };
        }
        
        const latencies = successful.map(m => m.latency);
        const successRate = this.measurements.length > 0 ? 
            successful.length / this.measurements.length : 0;
        
        return {
            latency_ms: Math.round(latencies[latencies.length - 1]),
            avg_latency_ms: Math.round(latencies.reduce((a, b) => a + b) / latencies.length),
            min_latency_ms: Math.round(Math.min(...latencies)),
            max_latency_ms: Math.round(Math.max(...latencies)),
            success_rate: Math.round(successRate * 100) / 100,
            samples: this.measurements.length,
            recent_success_rate: recentSuccessful.length / Math.max(recent.length, 1),
            is_connected: recentSuccessful.length > 0,
            timestamp: Date.now()
        };
    }
    
    reset() {
        this.measurements = [];
    }
}

class ConnectionHealthMonitor {
    constructor() {
        this.events = [];
        this.lastFrameTime = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.connectionStartTime = null;
        this.totalDisconnections = 0;
    }
    
    onFrameReceived() {
        const now = Date.now();
        this.lastFrameTime = now;
        
        if (!this.isConnected) {
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.recordEvent('connected');
            
            if (!this.connectionStartTime) {
                this.connectionStartTime = now;
            }
        }
    }
    
    onConnectionLost() {
        if (this.isConnected) {
            this.isConnected = false;
            this.totalDisconnections++;
            this.recordEvent('disconnected');
        }
    }
    
    onReconnectAttempt() {
        this.reconnectAttempts++;
        this.recordEvent('reconnect_attempt');
    }
    
    checkHealth() {
        const now = Date.now();
        const timeSinceLastFrame = this.lastFrameTime ? now - this.lastFrameTime : null;
        
        // Auto-detect disconnection based on frame timing
        if (this.isConnected && timeSinceLastFrame && timeSinceLastFrame > 10000) {
            this.onConnectionLost();
        }
        
        return {
            is_connected: this.isConnected,
            time_since_last_frame_ms: timeSinceLastFrame,
            reconnect_attempts: this.reconnectAttempts,
            total_disconnections: this.totalDisconnections,
            connection_stability: this.calculateStability(),
            uptime_seconds: this.connectionStartTime ? 
                Math.round((now - this.connectionStartTime) / 1000) : 0,
            timestamp: now
        };
    }
    
    calculateStability() {
        const recentEvents = this.events.slice(-20);
        const disconnections = recentEvents.filter(e => e.type === 'disconnected').length;
        
        // Stability score: 100% - (5% per disconnection)
        return Math.max(0, 100 - (disconnections * 5));
    }
    
    recordEvent(type) {
        this.events.push({
            type,
            timestamp: Date.now()
        });
        
        // Keep last 100 events
        if (this.events.length > 100) {
            this.events.shift();
        }
    }
    
    getMetrics() {
        return this.checkHealth();
    }
    
    reset() {
        this.events = [];
        this.lastFrameTime = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.connectionStartTime = null;
        this.totalDisconnections = 0;
    }
}

class StreamQualityDetector {
    constructor(videoElement = null) {
        this.frameSizes = [];
        this.maxSamples = 10;
        this.actualQuality = null;        // Objective quality from server
        this.qualityHistory = [];         // Track quality changes
        this.videoElement = videoElement;
        this.lastResolutionCheck = 0;
        this.currentResolution = null;
        this.lastFrameTimestamp = null;   // Server frame timestamp
    }
    
    onFrameReceived(frameSize, mjpegHeaders = null) {
        if (frameSize && frameSize > 0) {
            this.frameSizes.push(frameSize);
            
            if (this.frameSizes.length > this.maxSamples) {
                this.frameSizes.shift();
            }
        }
        
        // Parse objective quality from MJPEG headers
        if (mjpegHeaders) {
            this.parseQualityFromHeaders(mjpegHeaders);
        }
        
        // Check video resolution periodically (every 2 seconds)
        const now = Date.now();
        if (now - this.lastResolutionCheck > 2000) {
            this.checkVideoResolution();
            this.lastResolutionCheck = now;
        }
    }
    
    parseQualityFromHeaders(headers) {
        try {
            // Parse MJPEG frame headers for objective quality
            const qualityMatch = headers.match(/X-Frame-Quality:\s*(\d+)/);
            const timestampMatch = headers.match(/X-Frame-Timestamp:\s*([\d.]+)/);
            
            if (qualityMatch) {
                const newQuality = parseInt(qualityMatch[1]);
                
                // Record quality change
                if (this.actualQuality !== newQuality) {
                    this.qualityHistory.push({
                        quality: newQuality,
                        timestamp: Date.now(),
                        server_timestamp: timestampMatch ? parseFloat(timestampMatch[1]) : null
                    });
                    
                    // Keep last 20 quality changes
                    if (this.qualityHistory.length > 20) {
                        this.qualityHistory.shift();
                    }
                }
                
                this.actualQuality = newQuality;
            }
            
            if (timestampMatch) {
                this.lastFrameTimestamp = parseFloat(timestampMatch[1]);
            }
        } catch (error) {
            console.warn('Could not parse quality headers:', error);
        }
    }
    
    checkVideoResolution() {
        if (!this.videoElement) return;
        
        try {
            // For video elements, check actual rendered dimensions
            const videoWidth = this.videoElement.videoWidth;
            const videoHeight = this.videoElement.videoHeight;
            const displayWidth = this.videoElement.clientWidth;
            const displayHeight = this.videoElement.clientHeight;
            
            if (videoWidth && videoHeight) {
                this.currentResolution = {
                    source_width: videoWidth,
                    source_height: videoHeight,
                    display_width: displayWidth,
                    display_height: displayHeight,
                    aspect_ratio: Math.round((videoWidth / videoHeight) * 100) / 100,
                    is_scaled: videoWidth !== displayWidth || videoHeight !== displayHeight,
                    scale_factor: Math.round((displayWidth / videoWidth) * 100) / 100
                };
            }
        } catch (error) {
            console.warn('Could not detect video resolution:', error);
        }
    }
    
    setVideoElement(videoElement) {
        this.videoElement = videoElement;
        if (videoElement) {
            this.checkVideoResolution();
        }
    }
    
    getQualityStats() {
        if (this.qualityHistory.length === 0) {
            return {
                current_quality: this.actualQuality,
                changes_count: 0,
                trend: 'stable'
            };
        }
        
        // Analyze quality adaptation trend
        const recent = this.qualityHistory.slice(-5);
        const qualityValues = recent.map(h => h.quality);
        
        let trend = 'stable';
        if (qualityValues.length >= 2) {
            const first = qualityValues[0];
            const last = qualityValues[qualityValues.length - 1];
            const difference = last - first;
            
            if (difference > 10) trend = 'improving';
            else if (difference < -10) trend = 'degrading';
        }
        
        return {
            current_quality: this.actualQuality,
            changes_count: this.qualityHistory.length,
            trend: trend,
            recent_changes: recent.length,
            quality_range: qualityValues.length > 0 ? {
                min: Math.min(...qualityValues),
                max: Math.max(...qualityValues)
            } : null
        };
    }
    
    getMetrics() {
        const avgSize = this.frameSizes.length > 0 ?
            this.frameSizes.reduce((a, b) => a + b) / this.frameSizes.length : 0;
        
        const qualityStats = this.getQualityStats();
        
        return {
            // OBJECTIVE quality from server (not estimated!)
            actual_quality: this.actualQuality,
            quality_stats: qualityStats,
            
            // Frame size metrics
            avg_frame_size_kb: Math.round(avgSize / 1024 * 10) / 10,
            frame_size_samples: this.frameSizes.length,
            
            // Resolution metrics
            resolution: this.currentResolution,
            
            // Server synchronization
            last_server_timestamp: this.lastFrameTimestamp,
            client_server_time_diff: this.lastFrameTimestamp ? 
                (Date.now() / 1000) - this.lastFrameTimestamp : null,
                
            timestamp: Date.now()
        };
    }
    
    reset() {
        this.frameSizes = [];
        this.actualQuality = null;
        this.qualityHistory = [];
        this.currentResolution = null;
        this.lastResolutionCheck = 0;
        this.lastFrameTimestamp = null;
    }
}

class FrontendMetricsSystem {
    constructor() {
        this.fpsMonitor = new TrueFPSMeasurer();
        this.latencyMonitor = new LatencyMeasurer();
        this.healthMonitor = new ConnectionHealthMonitor();
        this.qualityDetector = new StreamQualityDetector();
        
        this.isRunning = false;
        this.updateInterval = null;
    }
    
    start() {
        if (this.isRunning) return;
        
        this.isRunning = true;
        this.latencyMonitor.start();
        
        // Start regular health checks
        this.updateInterval = setInterval(() => {
            this.healthMonitor.checkHealth();
        }, 1000);
        
        console.log('📊 Frontend metrics system started');
    }
    
    stop() {
        this.isRunning = false;
        this.latencyMonitor.stop();
        
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
        
        console.log('📊 Frontend metrics system stopped');
    }
    
    onFrameReceived(frameSize = null) {
        this.fpsMonitor.onFrameReceived();
        this.healthMonitor.onFrameReceived();
        
        if (frameSize) {
            this.qualityDetector.onFrameReceived(frameSize);
        }
    }
    
    onConnectionLost() {
        this.healthMonitor.onConnectionLost();
    }
    
    onReconnectAttempt() {
        this.healthMonitor.onReconnectAttempt();
    }
    
    getAllMetrics() {
        return {
            fps: this.fpsMonitor.getMetrics(),
            latency: this.latencyMonitor.getMetrics(),
            connection: this.healthMonitor.getMetrics(),
            quality: this.qualityDetector.getMetrics(),
            timestamp: Date.now()
        };
    }
    
    setVideoElement(videoElement) {
        this.qualityDetector.setVideoElement(videoElement);
    }
    
    getDisplayMetrics() {
        const all = this.getAllMetrics();
        
        return {
            // Main display values
            fps: all.fps.fps,
            latency_ms: all.latency.latency_ms,
            connection_status: all.connection.is_connected ? 'connected' : 'disconnected',
            quality_estimate: all.quality.estimated_quality,
            resolution: all.quality.resolution,
            
            // Additional info
            fps_jitter: all.fps.jitter_ms,
            connection_stability: all.connection.connection_stability,
            reconnect_attempts: all.connection.reconnect_attempts,
            uptime_seconds: all.connection.uptime_seconds,
            frame_size_kb: all.quality.avg_frame_size_kb,
            
            // Status flags
            is_stable_fps: all.fps.is_stable,
            is_connected: all.connection.is_connected,
            has_latency_data: all.latency.latency_ms !== null,
            has_resolution_data: all.quality.resolution !== null,
            
            timestamp: all.timestamp
        };
    }
    
    reset() {
        this.fpsMonitor.reset();
        this.latencyMonitor.reset();
        this.healthMonitor.reset();
        this.qualityDetector.reset();
        
        console.log('📊 Frontend metrics reset');
    }
}