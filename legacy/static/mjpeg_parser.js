/**
 * MJPEG Stream Parser
 * Parses MJPEG stream to extract frame headers and provide objective quality data
 */

class MJPEGStreamParser {
    constructor(onFrameCallback) {
        this.onFrameCallback = onFrameCallback;
        this.buffer = '';
        this.boundary = null;
        this.currentHeaders = '';
        this.frameCount = 0;
    }
    
    /**
     * Process incoming stream data
     */
    processData(data) {
        this.buffer += data;
        
        while (this.buffer.length > 0) {
            if (!this.boundary) {
                this.findBoundary();
            }
            
            if (this.boundary) {
                this.parseFrame();
            } else {
                break; // Need more data to find boundary
            }
        }
    }
    
    findBoundary() {
        // Look for boundary in buffer
        const boundaryMatch = this.buffer.match(/--([a-zA-Z0-9]+)/);
        if (boundaryMatch) {
            this.boundary = '--' + boundaryMatch[1];
            console.log('📡 MJPEG boundary found:', this.boundary);
        }
    }
    
    parseFrame() {
        const boundaryIndex = this.buffer.indexOf(this.boundary);
        if (boundaryIndex === -1) {
            return; // No complete frame yet
        }
        
        // Extract frame data
        const frameData = this.buffer.substring(0, boundaryIndex);
        this.buffer = this.buffer.substring(boundaryIndex + this.boundary.length);
        
        if (frameData.trim().length === 0) {
            return; // Empty frame, skip
        }
        
        // Parse headers and body
        const headerEndIndex = frameData.indexOf('\r\n\r\n');
        if (headerEndIndex === -1) {
            return; // No complete headers
        }
        
        const headers = frameData.substring(0, headerEndIndex);
        const body = frameData.substring(headerEndIndex + 4);
        
        // Extract objective quality from headers
        const frameInfo = this.parseFrameHeaders(headers);
        
        this.frameCount++;
        
        // Callback with objective frame data
        if (this.onFrameCallback) {
            this.onFrameCallback({
                frameNumber: this.frameCount,
                headers: headers,
                bodySize: body.length,
                quality: frameInfo.quality,
                timestamp: frameInfo.timestamp,
                clientId: frameInfo.clientId,
                contentLength: frameInfo.contentLength
            });
        }
    }
    
    parseFrameHeaders(headerString) {
        const frameInfo = {
            quality: null,
            timestamp: null,
            clientId: null,
            contentLength: null
        };
        
        // Parse each header line
        const lines = headerString.split('\r\n');
        for (const line of lines) {
            const colonIndex = line.indexOf(':');
            if (colonIndex === -1) continue;
            
            const headerName = line.substring(0, colonIndex).trim().toLowerCase();
            const headerValue = line.substring(colonIndex + 1).trim();
            
            switch (headerName) {
                case 'x-frame-quality':
                    frameInfo.quality = parseInt(headerValue);
                    break;
                case 'x-frame-timestamp':
                    frameInfo.timestamp = parseFloat(headerValue);
                    break;
                case 'x-client-id':
                    frameInfo.clientId = headerValue;
                    break;
                case 'content-length':
                    frameInfo.contentLength = parseInt(headerValue);
                    break;
            }
        }
        
        return frameInfo;
    }
    
    getStats() {
        return {
            framesProcessed: this.frameCount,
            bufferSize: this.buffer.length,
            boundary: this.boundary,
            isActive: this.frameCount > 0
        };
    }
    
    reset() {
        this.buffer = '';
        this.boundary = null;
        this.currentHeaders = '';
        this.frameCount = 0;
    }
}

/**
 * Enhanced Image Element for MJPEG Stream Monitoring
 */
class MonitoredImageElement {
    constructor(imgElement, metricsSystem) {
        this.imgElement = imgElement;
        this.metricsSystem = metricsSystem;
        this.streamParser = new MJPEGStreamParser(this.onFrameReceived.bind(this));
        this.isMonitoring = false;
        this.originalSrc = '';
    }
    
    startMonitoring() {
        if (this.isMonitoring) return;
        
        this.isMonitoring = true;
        this.originalSrc = this.imgElement.src;
        
        // Override the image source with our monitoring fetch
        this.fetchAndMonitorStream();
        
        console.log('📡 Started MJPEG stream monitoring');
    }
    
    stopMonitoring() {
        this.isMonitoring = false;
        console.log('📡 Stopped MJPEG stream monitoring');
    }
    
    async fetchAndMonitorStream() {
        if (!this.isMonitoring) return;
        
        try {
            const response = await fetch(this.originalSrc);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            while (this.isMonitoring) {
                const { done, value } = await reader.read();
                if (done) break;
                
                // Convert bytes to string for header parsing
                const chunk = decoder.decode(value, { stream: true });
                this.streamParser.processData(chunk);
            }
            
        } catch (error) {
            console.error('MJPEG stream error:', error);
            if (this.metricsSystem) {
                this.metricsSystem.onConnectionLost();
            }
            
            // Retry after delay
            if (this.isMonitoring) {
                setTimeout(() => this.fetchAndMonitorStream(), 2000);
            }
        }
    }
    
    onFrameReceived(frameData) {
        if (!this.metricsSystem) return;
        
        // Notify metrics system with OBJECTIVE quality data
        this.metricsSystem.onFrameReceived(frameData.bodySize, frameData.headers);
        
        console.log('📸 Frame received - Quality:', frameData.quality + '%', 
                   'Size:', Math.round(frameData.bodySize / 1024) + 'KB');
    }
}

// Usage example:
/*
const img = document.getElementById('cameraStream');
const metrics = new FrontendMetricsSystem();
const monitoredImage = new MonitoredImageElement(img, metrics);

// Start monitoring when stream begins
monitoredImage.startMonitoring();

// Get objective quality data
setInterval(() => {
    const displayMetrics = metrics.getDisplayMetrics();
    console.log('Current quality:', displayMetrics.quality_estimate + '%');
}, 1000);
*/