/**
 * Real-time camera stream metrics using modern Performance API
 * No estimations - only actual measured values
 */

class StreamMetrics {
    constructor() {
        this.frameTimestamps = [];
        this.maxSamples = 30; // Rolling window for FPS calculation
        this.actualFPS = 0;
        this.latencyMeasurements = [];
        this.maxLatencyMeasurements = 10;
        this.isActive = false;
        
        // Signal quality metrics
        this.connectionDrops = 0;
        this.totalFrames = 0;
        this.lastFrameTime = null;
        this.frameDeliveryTimes = [];
        this.maxDeliveryTimeSamples = 20;
    }

    start() {
        this.isActive = true;
        this.startLatencyMeasurement();
        console.log('📊 Stream metrics started');
    }

    stop() {
        this.isActive = false;
        console.log('📊 Stream metrics stopped');
    }

    // Called when a new frame is received from MJPEG stream
    onFrameReceived() {
        console.log('onFrameReceived called, isActive:', this.isActive);
        if (!this.isActive) return;

        const timestamp = performance.now();
        this.frameTimestamps.push(timestamp);
        this.totalFrames++;

        console.log('Frame received, totalFrames now:', this.totalFrames);

        // Track connection stability
        if (this.lastFrameTime) {
            const deliveryTime = timestamp - this.lastFrameTime;
            this.frameDeliveryTimes.push(deliveryTime);
            
            // Keep only recent delivery times
            if (this.frameDeliveryTimes.length > this.maxDeliveryTimeSamples) {
                this.frameDeliveryTimes.shift();
            }
            
            // Detect connection drops (gap > 2 seconds)
            if (deliveryTime > 2000) {
                this.connectionDrops++;
            }
        }
        this.lastFrameTime = timestamp;

        // Keep only recent samples for FPS calculation
        if (this.frameTimestamps.length > this.maxSamples) {
            this.frameTimestamps.shift();
        }

        this.calculateActualFPS();
        
        // Debug every 5th frame for more frequent updates
        if (this.totalFrames % 5 === 0) {
            console.log('Frame tracking debug:', {
                totalFrames: this.totalFrames,
                frameTimestamps: this.frameTimestamps.length,
                frameDeliveryTimes: this.frameDeliveryTimes.length,
                latencyMeasurements: this.latencyMeasurements.length,
                connectionDrops: this.connectionDrops
            });
        }
    }

    // Calculate actual FPS from frame timestamps
    calculateActualFPS() {
        if (this.frameTimestamps.length < 2) {
            this.actualFPS = 0;
            return;
        }

        // Calculate intervals between frames
        const intervals = [];
        for (let i = 1; i < this.frameTimestamps.length; i++) {
            intervals.push(this.frameTimestamps[i] - this.frameTimestamps[i - 1]);
        }

        // Calculate average interval and convert to FPS
        const avgInterval = intervals.reduce((a, b) => a + b) / intervals.length;
        this.actualFPS = Math.round((1000 / avgInterval) * 10) / 10; // Round to 1 decimal
    }

    // Measure network latency to server
    async measureLatency() {
        const start = performance.now();
        
        try {
            const response = await fetch('/health', {
                method: 'HEAD',
                cache: 'no-cache'
            });
            
            if (response.ok) {
                const latency = performance.now() - start;
                this.latencyMeasurements.push(latency);
                
                // Keep only recent measurements
                if (this.latencyMeasurements.length > this.maxLatencyMeasurements) {
                    this.latencyMeasurements.shift();
                }
            }
        } catch (error) {
            console.warn('Latency measurement failed:', error);
        }
    }

    startLatencyMeasurement() {
        // Measure latency every 5 seconds
        setInterval(() => {
            if (this.isActive) {
                this.measureLatency();
            }
        }, 5000);
        
        // Initial measurement
        this.measureLatency();
    }

    // Calculate connection stability (0-100%)
    calculateConnectionStability() {
        if (this.totalFrames < 3) {
            console.log('Connection stability: not enough frames', this.totalFrames);
            return null;
        }
        
        const recentDrops = this.connectionDrops;
        const totalTime = this.totalFrames > 0 ? 
            (performance.now() - (this.frameTimestamps[0] || performance.now())) / 1000 : 0;
        
        // Stability decreases with connection drops and inconsistent delivery
        const dropPenalty = Math.min(recentDrops * 10, 50); // Max 50% penalty for drops
        const baseStability = Math.max(0, 100 - dropPenalty);
        
        console.log('Connection stability calculated:', Math.round(baseStability), 'totalFrames:', this.totalFrames, 'drops:', recentDrops);
        return Math.round(baseStability);
    }

    // Calculate network quality with actual values
    calculateNetworkQuality() {
        if (this.latencyMeasurements.length < 1) {
            console.log('Network quality: no latency measurements', this.latencyMeasurements.length);
            return null;
        }
        
        const avgLatency = this.latencyMeasurements.reduce((a, b) => a + b) / this.latencyMeasurements.length;
        const minLatency = Math.min(...this.latencyMeasurements);
        const maxLatency = Math.max(...this.latencyMeasurements);
        
        const result = {
            avg_latency: Math.round(avgLatency),
            min_latency: Math.round(minLatency),
            max_latency: Math.round(maxLatency),
            samples: this.latencyMeasurements.length
        };
        
        console.log('Network quality calculated:', result);
        return result;
    }

    // Calculate frame consistency with actual jitter values
    calculateFrameConsistency() {
        if (this.frameDeliveryTimes.length < 3) {
            console.log('Frame consistency: not enough delivery times', this.frameDeliveryTimes.length);
            return null;
        }
        
        const avgDelivery = this.frameDeliveryTimes.reduce((a, b) => a + b) / this.frameDeliveryTimes.length;
        const variance = this.frameDeliveryTimes.reduce((acc, val) => 
            acc + Math.pow(val - avgDelivery, 2), 0) / this.frameDeliveryTimes.length;
        const jitter = Math.sqrt(variance);
        
        const minDelivery = Math.min(...this.frameDeliveryTimes);
        const maxDelivery = Math.max(...this.frameDeliveryTimes);
        
        const result = {
            jitter_ms: Math.round(jitter * 10) / 10,
            avg_interval_ms: Math.round(avgDelivery),
            min_interval_ms: Math.round(minDelivery),
            max_interval_ms: Math.round(maxDelivery),
            samples: this.frameDeliveryTimes.length
        };
        
        console.log('Frame consistency calculated:', result);
        return result;
    }

    // Calculate overall stream health score with frontend + backend data
    calculateStreamHealth(backendMetrics = null) {
        const stability = this.calculateConnectionStability();
        const networkQuality = this.calculateNetworkQuality();
        const frameConsistency = this.calculateFrameConsistency();
        
        if (!stability || !networkQuality || !frameConsistency) return null;
        
        // Frontend metrics (60% total weight)
        let score = stability * 0.3; // 30% weight on stability
        
        // Network quality scoring based on actual latency
        const avgLatency = networkQuality.avg_latency;
        let networkScore = 100;
        if (avgLatency > 200) networkScore = 30;
        else if (avgLatency > 100) networkScore = 60;
        else if (avgLatency > 50) networkScore = 80;
        score += networkScore * 0.2; // 20% weight
        
        // Frame consistency scoring based on actual jitter
        const jitter = frameConsistency.jitter_ms;
        let consistencyScore = 100;
        if (jitter > 100) consistencyScore = 40;
        else if (jitter > 50) consistencyScore = 70;
        score += consistencyScore * 0.1; // 10% weight
        
        // Backend encoding health (40% weight if available)
        let encodingScore = 100;
        let encodingDetails = {};
        
        if (backendMetrics?.encoding_health && !backendMetrics.encoding_health.error) {
            const encoding = backendMetrics.encoding_health;
            encodingDetails = {
                frames_encoded: encoding.frames_encoded || 0,
                encoding_errors: encoding.encoding_errors || 0,
                avg_encode_time_ms: encoding.avg_encode_time_ms || 0,
                last_frame_size_kb: Math.round((encoding.last_frame_size_kb || 0) * 10) / 10
            };
            
            // Calculate encoding health score
            if (encodingDetails.frames_encoded > 0) {
                const errorRate = encodingDetails.encoding_errors / encodingDetails.frames_encoded;
                encodingScore = Math.max(0, 100 - (errorRate * 100)); // Penalize errors
                
                // Penalize slow encoding (should be < 50ms for real-time)
                if (encodingDetails.avg_encode_time_ms > 100) encodingScore *= 0.7;
                else if (encodingDetails.avg_encode_time_ms > 50) encodingScore *= 0.85;
            }
            
            score += encodingScore * 0.4; // 40% weight on backend encoding
        } else {
            // No backend data, redistribute weight to frontend metrics
            score = stability * 0.5 + networkScore * 0.3 + consistencyScore * 0.2;
        }
        
        return {
            overall_score: Math.round(score),
            stability_pct: stability,
            avg_latency_ms: avgLatency,
            jitter_ms: frameConsistency.jitter_ms,
            connection_drops: this.connectionDrops,
            total_frames: this.totalFrames,
            encoding_health: encodingDetails,
            encoding_score: Math.round(encodingScore)
        };
    }

    // Get current metrics - only real measured values
    getMetrics() {
        const currentLatency = this.latencyMeasurements.length > 0 
            ? Math.round(this.latencyMeasurements[this.latencyMeasurements.length - 1])
            : null;

        // Debug: log internal state
        console.log('getMetrics internal state:', {
            totalFrames: this.totalFrames,
            frameDeliveryTimes: this.frameDeliveryTimes.length,
            latencyMeasurements: this.latencyMeasurements.length
        });

        return {
            actual_fps: this.actualFPS,
            latency_ms: currentLatency,
            frame_samples: this.frameTimestamps.length,
            // Signal quality metrics
            connection_stability: this.calculateConnectionStability(),
            network_quality: this.calculateNetworkQuality(),
            frame_consistency: this.calculateFrameConsistency(),
            timestamp: Date.now()
        };
    }

    reset() {
        this.frameTimestamps = [];
        this.latencyMeasurements = [];
        this.actualFPS = 0;
        this.connectionDrops = 0;
        this.totalFrames = 0;
        this.lastFrameTime = null;
        this.frameDeliveryTimes = [];
    }
}

// Initialize metrics system
const streamMetrics = new StreamMetrics();

// Function to fetch backend metrics
async function fetchBackendMetrics() {
    try {
        const response = await fetch('/api/camera/metrics');
        if (response.ok) {
            return await response.json();
        }
    } catch (error) {
        console.warn('Failed to fetch backend metrics:', error);
    }
    return null;
}

// Combined metrics function
async function getAllMetrics() {
    const frontendMetrics = streamMetrics.getMetrics();
    const backendMetrics = await fetchBackendMetrics();
    
    // Calculate stream health with backend encoding data
    const streamHealth = streamMetrics.calculateStreamHealth(backendMetrics);
    
    return {
        ...frontendMetrics,
        stream_health: streamHealth,
        backend: backendMetrics
    };
}