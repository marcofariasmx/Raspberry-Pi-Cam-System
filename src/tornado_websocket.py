#!/usr/bin/env python3
"""
High-Performance Tornado WebSocket Server for H.264 Video Streaming

Based on successful Raspberry Pi H.264 streaming projects that use Tornado
for optimal WebSocket performance. Tornado is proven to handle thousands
of simultaneous WebSocket connections with excellent performance.

References:
- pi-h264-to-browser-streamer (uses Tornado + jMuxer)
- 131's <0.1s latency h264 websocket browser player
- Multiple successful Pi streaming tutorials use Tornado
"""

import tornado.web
import tornado.websocket
import tornado.ioloop
import asyncio
import weakref
import json
import time
import threading
from typing import Set
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class H264WebSocketHandler(tornado.websocket.WebSocketHandler):
    """
    High-performance WebSocket handler optimized for H.264 video streaming.
    
    Tornado's WebSocket implementation is specifically designed for long-lived
    connections and high-frequency data transmission, making it ideal for
    real-time video streaming applications.
    """
    
    # Class-level set to track all connected clients
    clients: Set['H264WebSocketHandler'] = weakref.WeakSet()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_ping = time.time()
    
    def open(self):
        """Called when WebSocket connection is established."""
        self.clients.add(self)
        client_ip = self.request.remote_ip
        logger.info(f"🔌 Tornado WebSocket connected from {client_ip}. Total clients: {len(self.clients)}")
        
        # Send initial connection confirmation
        self.write_message(json.dumps({
            "type": "connected", 
            "message": "Tornado H.264 stream ready"
        }))
    
    def on_close(self):
        """Called when WebSocket connection is closed."""
        # WeakSet automatically removes closed connections
        logger.info(f"🔌 Tornado WebSocket disconnected. Total clients: {len(self.clients)}")
    
    def on_message(self, message):
        """Handle incoming messages from clients."""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == 'ping':
                self.last_ping = time.time()
                self.write_message(json.dumps({"type": "pong"}))
            elif msg_type == 'get_stats':
                self.send_stats()
                
        except (json.JSONDecodeError, KeyError):
            # Ignore malformed messages
            pass
    
    def send_stats(self):
        """Send current streaming statistics to client."""
        stats = {
            "type": "stats",
            "connected_clients": len(self.clients),
            "uptime": time.time() - getattr(self, 'start_time', time.time())
        }
        self.write_message(json.dumps(stats))
    
    def check_origin(self, origin):
        """Allow connections from any origin for development."""
        return True  # In production, implement proper origin checking
    
    @classmethod
    def broadcast_h264_frame(cls, frame_data: bytes):
        """
        Efficiently broadcast H.264 frame to all connected clients.
        
        Tornado's WebSocket implementation is optimized for this exact use case:
        - High-frequency binary data transmission
        - Multiple simultaneous connections
        - Non-blocking I/O for optimal performance
        """
        if not cls.clients:
            return
        
        # Remove any closed connections (garbage collection)
        dead_clients = [client for client in cls.clients if client.ws_connection is None]
        for client in dead_clients:
            cls.clients.discard(client)
        
        # Broadcast to all active clients
        for client in cls.clients.copy():  # Copy to avoid modification during iteration
            try:
                if client.ws_connection and not client.ws_connection.is_closing():
                    client.write_message(frame_data, binary=True)
            except Exception as e:
                logger.warning(f"⚠️ Failed to send frame to client: {e}")
                cls.clients.discard(client)
    
    @classmethod
    def get_client_count(cls) -> int:
        """Get current number of connected clients."""
        return len(cls.clients)
    
    @classmethod
    def is_active(cls) -> bool:
        """Check if any clients are connected."""
        return len(cls.clients) > 0


class TornadoH264Server:
    """
    Tornado-based H.264 streaming server optimized for Raspberry Pi.
    
    This server runs independently of FastAPI and provides high-performance
    WebSocket streaming specifically optimized for video data.
    """
    
    def __init__(self, port=8001):
        self.port = port
        self.app = None
        self.server = None
        self.ioloop = None
        self._running = False
    
    def create_app(self):
        """Create Tornado application with WebSocket handler."""
        return tornado.web.Application([
            (r"/ws", H264WebSocketHandler),
            (r"/health", self.HealthHandler),
        ], 
        websocket_ping_interval=20,  # Send ping every 20 seconds
        websocket_ping_timeout=10,   # Timeout after 10 seconds
        compress_response=False,     # Disable compression for video data
        )
    
    class HealthHandler(tornado.web.RequestHandler):
        """Health check endpoint for monitoring."""
        def get(self):
            self.write({
                "status": "ok", 
                "clients": H264WebSocketHandler.get_client_count(),
                "server": "tornado"
            })
    
    def start_server(self):
        """Start Tornado server in a separate thread."""
        def run_server():
            self.app = self.create_app()
            self.server = tornado.httpserver.HTTPServer(self.app)
            self.server.listen(self.port)
            self.ioloop = tornado.ioloop.IOLoop.current()
            
            logger.info(f"🚀 Tornado H.264 WebSocket server started on port {self.port}")
            logger.info(f"🌐 WebSocket endpoint: ws://localhost:{self.port}/ws")
            logger.info(f"💊 Health check: http://localhost:{self.port}/health")
            
            self._running = True
            self.ioloop.start()
        
        # Start server in background thread
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        
        # Give server time to start
        time.sleep(1)
        return self._running
    
    def stop_server(self):
        """Stop Tornado server."""
        if self.ioloop:
            self.ioloop.add_callback(self.ioloop.stop)
        self._running = False
    
    def broadcast_frame(self, frame_data: bytes):
        """Thread-safe frame broadcasting."""
        if self._running and H264WebSocketHandler.is_active():
            # Schedule broadcast on Tornado's IOLoop
            if self.ioloop:
                self.ioloop.add_callback(
                    H264WebSocketHandler.broadcast_h264_frame, 
                    frame_data
                )
    
    def get_stats(self):
        """Get server statistics."""
        return {
            "running": self._running,
            "port": self.port,
            "clients": H264WebSocketHandler.get_client_count(),
            "active": H264WebSocketHandler.is_active()
        }


# Global server instance
_tornado_server = None

def get_tornado_server(port=8001) -> TornadoH264Server:
    """Get or create global Tornado server instance."""
    global _tornado_server
    if _tornado_server is None:
        _tornado_server = TornadoH264Server(port)
    return _tornado_server

def start_tornado_server(port=8001) -> bool:
    """Start Tornado server and return success status."""
    server = get_tornado_server(port)
    return server.start_server()

def broadcast_h264_frame(frame_data: bytes):
    """Broadcast H.264 frame to all connected clients."""
    global _tornado_server
    if _tornado_server:
        _tornado_server.broadcast_frame(frame_data)

def get_client_count() -> int:
    """Get number of connected WebSocket clients."""
    return H264WebSocketHandler.get_client_count()

def is_streaming_active() -> bool:
    """Check if any clients are connected for streaming."""
    return H264WebSocketHandler.is_active()


if __name__ == "__main__":
    # Test server directly
    import signal
    import sys
    
    def signal_handler(sig, frame):
        print("\n🛑 Shutting down Tornado server...")
        if _tornado_server:
            _tornado_server.stop_server()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    print("🚀 Starting Tornado H.264 WebSocket server...")
    if start_tornado_server(8001):
        print("✅ Server started successfully!")
        print("🌐 Test with: ws://localhost:8001/ws")
        try:
            # Keep main thread alive
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        print("❌ Failed to start server")