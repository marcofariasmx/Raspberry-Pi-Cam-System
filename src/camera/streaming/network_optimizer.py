"""
Network Optimization for Efficient Streaming
Implements TCP_NODELAY, write batching, and adaptive buffer management
for optimal Pi Zero 2W network performance.
"""

import socket
import time
import threading
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from collections import deque


@dataclass
class NetworkMetrics:
    """Track network performance metrics"""
    bytes_sent: int = 0
    writes_performed: int = 0
    batches_sent: int = 0
    avg_batch_size: float = 0.0
    last_write_time: float = 0.0
    connection_established: float = 0.0


class AdaptiveWriteBuffer:
    """
    Adaptive write buffer that batches network writes for efficiency
    while maintaining low latency for Pi Zero 2W streaming
    """
    
    def __init__(self, target_batch_size: int = 4096, max_delay_ms: float = 16.0):
        """
        Initialize adaptive write buffer
        
        Args:
            target_batch_size: Target size for batched writes (default: 4KB)
            max_delay_ms: Maximum delay before forced flush (default: 16ms for ~60fps)
        """
        self.target_batch_size = target_batch_size
        self.max_delay_seconds = max_delay_ms / 1000.0
        
        # Buffer management
        self.buffer = bytearray()
        self.buffer_lock = threading.Lock()
        
        # Timing control
        self.last_write_time = time.time()
        self.pending_since = None
        
        # Performance tracking
        self.metrics = NetworkMetrics()
        
        print(f"📦 AdaptiveWriteBuffer: {target_batch_size/1024:.1f}KB batches, {max_delay_ms:.1f}ms max delay")
    
    def add_data(self, data: bytes) -> Optional[bytes]:
        """
        Add data to buffer, return batched data if ready to send
        
        Args:
            data: Data to add to buffer
            
        Returns:
            bytes: Batched data ready to send, or None if not ready
        """
        if not data:
            return None
        
        current_time = time.time()
        
        with self.buffer_lock:
            # Add data to buffer
            self.buffer.extend(data)
            
            # Mark when we first started accumulating if buffer was empty
            if self.pending_since is None:
                self.pending_since = current_time
            
            # Check if we should flush (size or time threshold)
            should_flush = (
                len(self.buffer) >= self.target_batch_size or
                (self.pending_since and 
                 current_time - self.pending_since >= self.max_delay_seconds)
            )
            
            if should_flush:
                return self._flush_buffer(current_time)
        
        return None
    
    def _flush_buffer(self, current_time: float) -> bytes:
        """
        Flush buffer and return data to send
        
        Args:
            current_time: Current timestamp
            
        Returns:
            bytes: Data to send
        """
        if not self.buffer:
            return b''
        
        # Extract data
        data_to_send = bytes(self.buffer)
        
        # Update metrics
        self.metrics.bytes_sent += len(data_to_send)
        self.metrics.batches_sent += 1
        self.metrics.last_write_time = current_time
        
        # Update average batch size
        if self.metrics.batches_sent > 0:
            self.metrics.avg_batch_size = self.metrics.bytes_sent / self.metrics.batches_sent
        
        # Clear buffer
        self.buffer.clear()
        self.pending_since = None
        
        return data_to_send
    
    def force_flush(self) -> bytes:
        """
        Force flush of any pending data
        
        Returns:
            bytes: Any pending data
        """
        current_time = time.time()
        
        with self.buffer_lock:
            return self._flush_buffer(current_time)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get buffer performance metrics"""
        current_time = time.time()
        
        with self.buffer_lock:
            return {
                "buffer_size_bytes": len(self.buffer),
                "target_batch_size": self.target_batch_size,
                "max_delay_ms": self.max_delay_seconds * 1000,
                "pending_time_ms": (
                    (current_time - self.pending_since) * 1000 
                    if self.pending_since else 0.0
                ),
                "metrics": {
                    "bytes_sent": self.metrics.bytes_sent,
                    "batches_sent": self.metrics.batches_sent,
                    "avg_batch_size_bytes": self.metrics.avg_batch_size,
                    "last_write_time": self.metrics.last_write_time
                },
                "efficiency": {
                    "batching_ratio": (
                        self.metrics.avg_batch_size / self.target_batch_size
                        if self.target_batch_size > 0 else 0.0
                    ),
                    "memory_efficiency": "good" if len(self.buffer) < self.target_batch_size else "high"
                }
            }


class NetworkOptimizer:
    """
    Network optimizer for streaming connections
    Implements TCP_NODELAY, socket buffer optimization, and adaptive batching
    """
    
    def __init__(self, connection_id: str = "default"):
        """
        Initialize network optimizer
        
        Args:
            connection_id: Unique identifier for this connection
        """
        self.connection_id = connection_id
        self.write_buffer = AdaptiveWriteBuffer()
        self.socket_optimized = False
        
        # Connection tracking
        self.bytes_transmitted = 0
        self.start_time = time.time()
        self.last_activity = self.start_time
        
        # Performance optimization state
        self.tcp_nodelay_enabled = False
        self.socket_buffers_optimized = False
        
        print(f"🌐 NetworkOptimizer created for connection: {connection_id}")
    
    def optimize_socket(self, sock: socket.socket) -> bool:
        """
        Apply socket optimizations for streaming
        
        Args:
            sock: Socket to optimize
            
        Returns:
            bool: True if optimizations were applied successfully
        """
        try:
            # Enable TCP_NODELAY for low latency
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.tcp_nodelay_enabled = True
            
            # Optimize socket buffers for streaming
            # Larger send buffer for Pi Zero 2W's limited memory bandwidth
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)  # 64KB send buffer
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32768)  # 32KB receive buffer
            
            # Set socket to non-blocking for better control
            sock.setblocking(False)
            
            self.socket_buffers_optimized = True
            self.socket_optimized = True
            
            print(f"✅ Socket optimized for {self.connection_id}:")
            print(f"   🚀 TCP_NODELAY: Enabled")
            print(f"   📦 Send buffer: 64KB")
            print(f"   📥 Receive buffer: 32KB")
            print(f"   ⚡ Non-blocking: Enabled")
            
            return True
            
        except Exception as e:
            print(f"⚠️ Socket optimization failed for {self.connection_id}: {e}")
            return False
    
    def prepare_frame_data(self, frame_data: bytes) -> Optional[bytes]:
        """
        Prepare frame data for network transmission with batching
        
        Args:
            frame_data: Raw frame data to send
            
        Returns:
            bytes: Batched data ready to send, or None if not ready
        """
        if not frame_data:
            return None
        
        self.last_activity = time.time()
        
        # Add to write buffer for batching
        batched_data = self.write_buffer.add_data(frame_data)
        
        if batched_data:
            self.bytes_transmitted += len(batched_data)
            
        return batched_data
    
    def flush_pending_data(self) -> bytes:
        """
        Flush any pending data in write buffer
        
        Returns:
            bytes: Any pending data to send
        """
        pending_data = self.write_buffer.force_flush()
        
        if pending_data:
            self.bytes_transmitted += len(pending_data)
            self.last_activity = time.time()
        
        return pending_data
    
    def update_batch_size(self, new_size: int):
        """
        Dynamically update batch size based on network conditions
        
        Args:
            new_size: New target batch size in bytes
        """
        # Clamp to reasonable values for Pi Zero 2W
        new_size = max(1024, min(new_size, 16384))  # 1KB to 16KB
        
        if new_size != self.write_buffer.target_batch_size:
            self.write_buffer.target_batch_size = new_size
            print(f"📦 {self.connection_id}: Batch size updated to {new_size/1024:.1f}KB")
    
    def get_connection_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive connection metrics
        
        Returns:
            dict: Connection performance metrics
        """
        current_time = time.time()
        uptime = current_time - self.start_time
        
        buffer_metrics = self.write_buffer.get_metrics()
        
        return {
            "connection_id": self.connection_id,
            "uptime_seconds": uptime,
            "bytes_transmitted": self.bytes_transmitted,
            "last_activity": self.last_activity,
            "time_since_activity": current_time - self.last_activity,
            "average_throughput_kbps": (
                (self.bytes_transmitted / 1024) / uptime if uptime > 0 else 0.0
            ),
            "optimization_status": {
                "socket_optimized": self.socket_optimized,
                "tcp_nodelay_enabled": self.tcp_nodelay_enabled,
                "socket_buffers_optimized": self.socket_buffers_optimized,
                "write_batching_active": True
            },
            "write_buffer": buffer_metrics,
            "efficiency": {
                "batching_efficiency": buffer_metrics["efficiency"]["batching_ratio"],
                "network_utilization": "optimal" if buffer_metrics["efficiency"]["batching_ratio"] > 0.7 else "good",
                "pi_zero_optimized": self.socket_optimized and buffer_metrics["metrics"]["avg_batch_size_bytes"] > 2048
            }
        }
    
    def get_status_summary(self) -> str:
        """
        Get human-readable status summary
        
        Returns:
            str: Concise status summary
        """
        metrics = self.get_connection_metrics()
        
        return (
            f"{self.connection_id}: "
            f"Sent: {metrics['bytes_transmitted']/1024:.1f}KB | "
            f"Throughput: {metrics['average_throughput_kbps']:.1f}KB/s | "
            f"Batch Eff: {metrics['write_buffer']['efficiency']['batching_ratio']:.2f} | "
            f"Optimized: {'Yes' if metrics['optimization_status']['socket_optimized'] else 'No'}"
        )


class ConnectionPool:
    """
    Pool of network optimizers for multiple client connections
    Manages resources efficiently for Pi Zero 2W constraints
    """
    
    def __init__(self, max_connections: int = 32):
        """
        Initialize connection pool
        
        Args:
            max_connections: Maximum concurrent connections (default: 32, hardware will limit naturally)
        """
        self.max_connections = max_connections
        self.connections: Dict[str, NetworkOptimizer] = {}
        self.connection_lock = threading.RLock()
        
        # Pool-wide metrics
        self.total_connections_created = 0
        self.pool_start_time = time.time()
        
        print(f"🌐 ConnectionPool initialized: max {max_connections} connections")
    
    def get_optimizer(self, connection_id: str) -> NetworkOptimizer:
        """
        Get or create network optimizer for connection
        
        Args:
            connection_id: Unique connection identifier
            
        Returns:
            NetworkOptimizer: Optimizer for the connection
        """
        with self.connection_lock:
            if connection_id not in self.connections:
                # Check pool capacity
                if len(self.connections) >= self.max_connections:
                    # Remove oldest inactive connection
                    self._cleanup_inactive_connections()
                
                # Create new optimizer
                optimizer = NetworkOptimizer(connection_id)
                self.connections[connection_id] = optimizer
                self.total_connections_created += 1
                
                print(f"📊 Connection pool: {connection_id} added ({len(self.connections)}/{self.max_connections})")
            
            return self.connections[connection_id]
    
    def remove_connection(self, connection_id: str) -> bool:
        """
        Remove connection from pool
        
        Args:
            connection_id: Connection to remove
            
        Returns:
            bool: True if connection was removed
        """
        with self.connection_lock:
            if connection_id in self.connections:
                # Flush any pending data
                optimizer = self.connections[connection_id]
                optimizer.flush_pending_data()
                
                # Remove from pool
                del self.connections[connection_id]
                
                print(f"🗑️ Connection pool: {connection_id} removed ({len(self.connections)}/{self.max_connections})")
                return True
        
        return False
    
    def _cleanup_inactive_connections(self):
        """Remove inactive connections to make room"""
        current_time = time.time()
        inactive_threshold = 300.0  # 5 minutes
        
        inactive_connections = [
            conn_id for conn_id, optimizer in self.connections.items()
            if current_time - optimizer.last_activity > inactive_threshold
        ]
        
        for conn_id in inactive_connections:
            self.remove_connection(conn_id)
        
        if inactive_connections:
            print(f"🧹 Cleaned up {len(inactive_connections)} inactive connections")
    
    def get_pool_metrics(self) -> Dict[str, Any]:
        """Get pool-wide metrics"""
        current_time = time.time()
        uptime = current_time - self.pool_start_time
        
        with self.connection_lock:
            total_bytes = sum(opt.bytes_transmitted for opt in self.connections.values())
            active_connections = len(self.connections)
            
            return {
                "pool_stats": {
                    "active_connections": active_connections,
                    "max_connections": self.max_connections,
                    "total_created": self.total_connections_created,
                    "pool_utilization": active_connections / self.max_connections,
                    "uptime_seconds": uptime
                },
                "aggregate_metrics": {
                    "total_bytes_transmitted": total_bytes,
                    "average_throughput_kbps": (total_bytes / 1024) / uptime if uptime > 0 else 0.0,
                    "connections_per_mb": active_connections / max(total_bytes / (1024*1024), 0.001)
                },
                "optimization_summary": {
                    "all_optimized": all(opt.socket_optimized for opt in self.connections.values()),
                    "batching_efficiency": sum(
                        opt.write_buffer.metrics.avg_batch_size / opt.write_buffer.target_batch_size
                        for opt in self.connections.values()
                    ) / max(active_connections, 1)
                }
            }
    
    def get_all_connection_status(self) -> Dict[str, str]:
        """Get status summary for all connections"""
        with self.connection_lock:
            return {
                conn_id: optimizer.get_status_summary()
                for conn_id, optimizer in self.connections.items()
            }