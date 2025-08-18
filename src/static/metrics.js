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
        if (!this.isActive) return;

        const timestamp = performance.now();
        this.frameTimestamps.push(timestamp);

        // Keep only recent samples for FPS calculation
        if (this.frameTimestamps.length > this.maxSamples) {
            this.frameTimestamps.shift();
        }

        this.calculateActualFPS();
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

    // Get current metrics - only real measured values
    getMetrics() {
        const currentLatency = this.latencyMeasurements.length > 0 
            ? Math.round(this.latencyMeasurements[this.latencyMeasurements.length - 1])
            : null;

        return {
            actual_fps: this.actualFPS,
            latency_ms: currentLatency,
            frame_samples: this.frameTimestamps.length,
            timestamp: Date.now()
        };
    }

    reset() {
        this.frameTimestamps = [];
        this.latencyMeasurements = [];
        this.actualFPS = 0;
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
    
    return {
        ...frontendMetrics,
        backend: backendMetrics
    };
}