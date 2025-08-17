"""
Memory Pool System for Efficient Frame Buffer Management
Reduces garbage collection pressure and memory allocations for Pi Zero 2W optimization.
"""

import queue
import threading
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class BufferMetrics:
    """Track buffer pool performance metrics"""
    total_allocations: int = 0
    pool_hits: int = 0
    pool_misses: int = 0
    current_pool_size: int = 0
    peak_usage: int = 0
    bytes_saved: int = 0


class FrameBufferPool:
    """
    Memory pool for frame buffers to reduce GC pressure on Pi Zero 2W
    
    Pre-allocates buffers and reuses them to minimize memory allocations
    during high-frequency frame processing.
    """
    
    def __init__(self, buffer_size: int = 65536, pool_size: int = 8, name: str = "FramePool"):
        """
        Initialize frame buffer pool
        
        Args:
            buffer_size: Size of each buffer in bytes (default: 64KB)
            pool_size: Number of buffers to pre-allocate (default: 8)
            name: Pool name for debugging
        """
        self.buffer_size = buffer_size
        self.max_pool_size = pool_size
        self.name = name
        
        # Thread-safe buffer queue
        self.available_buffers = queue.Queue(maxsize=pool_size)
        self.in_use_buffers = set()
        self._lock = threading.Lock()
        
        # Performance metrics
        self.metrics = BufferMetrics()
        self.start_time = time.time()
        
        # Pre-allocate buffers
        self._preallocate_buffers()
        
        print(f"🧠 {name} initialized: {pool_size} buffers × {buffer_size/1024:.1f}KB = {pool_size * buffer_size/1024:.1f}KB total")
    
    def _preallocate_buffers(self):
        """Pre-allocate all buffers to avoid runtime allocations"""
        for i in range(self.max_pool_size):
            buffer = bytearray(self.buffer_size)
            self.available_buffers.put(buffer)
            
        self.metrics.current_pool_size = self.max_pool_size
        print(f"✅ Pre-allocated {self.max_pool_size} buffers for {self.name}")
    
    def get_buffer(self, required_size: Optional[int] = None) -> bytearray:
        """
        Get a buffer from the pool
        
        Args:
            required_size: Minimum required buffer size
            
        Returns:
            bytearray: Buffer ready for use
        """
        self.metrics.total_allocations += 1
        
        # Check if we need a larger buffer than our standard size
        if required_size and required_size > self.buffer_size:
            self.metrics.pool_misses += 1
            # Allocate larger buffer directly (not pooled)
            buffer = bytearray(required_size)
            print(f"⚠️ {self.name}: Large buffer allocated ({required_size/1024:.1f}KB > {self.buffer_size/1024:.1f}KB)")
            return buffer
        
        try:
            # Try to get buffer from pool
            buffer = self.available_buffers.get_nowait()
            self.metrics.pool_hits += 1
            
            with self._lock:
                self.in_use_buffers.add(id(buffer))
                self.metrics.peak_usage = max(self.metrics.peak_usage, len(self.in_use_buffers))
            
            # Clear buffer contents for reuse
            if required_size:
                # Only clear what we need to minimize memory writes
                buffer[:required_size] = b'\x00' * required_size
            else:
                buffer[:] = b'\x00' * len(buffer)
            
            return buffer
            
        except queue.Empty:
            # Pool exhausted, allocate new buffer
            self.metrics.pool_misses += 1
            buffer = bytearray(required_size or self.buffer_size)
            
            print(f"📊 {self.name}: Pool exhausted, fallback allocation "
                  f"(hits: {self.metrics.pool_hits}, misses: {self.metrics.pool_misses})")
            
            return buffer
    
    def return_buffer(self, buffer: bytearray):
        """
        Return a buffer to the pool for reuse
        
        Args:
            buffer: Buffer to return
        """
        if not isinstance(buffer, bytearray):
            return  # Can't pool non-bytearray objects
            
        # Only pool buffers that match our standard size
        if len(buffer) != self.buffer_size:
            return  # Let GC handle non-standard sizes
        
        with self._lock:
            buffer_id = id(buffer)
            if buffer_id in self.in_use_buffers:
                self.in_use_buffers.discard(buffer_id)
        
        try:
            # Return to pool if there's space
            self.available_buffers.put_nowait(buffer)
            
            # Calculate memory savings
            self.metrics.bytes_saved += len(buffer)
            
        except queue.Full:
            # Pool is full, let GC handle this buffer
            pass
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive pool performance metrics
        
        Returns:
            dict: Performance and efficiency metrics
        """
        uptime = time.time() - self.start_time
        hit_rate = (self.metrics.pool_hits / self.metrics.total_allocations 
                   if self.metrics.total_allocations > 0 else 0.0)
        
        with self._lock:
            current_in_use = len(self.in_use_buffers)
        
        return {
            "pool_name": self.name,
            "buffer_size_kb": self.buffer_size / 1024,
            "max_pool_size": self.max_pool_size,
            "current_available": self.available_buffers.qsize(),
            "current_in_use": current_in_use,
            "total_allocations": self.metrics.total_allocations,
            "pool_hits": self.metrics.pool_hits,
            "pool_misses": self.metrics.pool_misses,
            "hit_rate_percent": hit_rate * 100,
            "peak_concurrent_usage": self.metrics.peak_usage,
            "bytes_saved_kb": self.metrics.bytes_saved / 1024,
            "memory_efficiency": {
                "allocated_memory_kb": self.max_pool_size * self.buffer_size / 1024,
                "est_without_pool_kb": self.metrics.total_allocations * self.buffer_size / 1024,
                "memory_saved_percent": (1 - (self.max_pool_size / max(self.metrics.total_allocations, 1))) * 100
            },
            "uptime_seconds": uptime,
            "allocations_per_second": self.metrics.total_allocations / uptime if uptime > 0 else 0
        }
    
    def get_status_summary(self) -> str:
        """
        Get human-readable status summary
        
        Returns:
            str: Concise pool status
        """
        metrics = self.get_metrics()
        
        return (
            f"{self.name}: "
            f"Hit Rate: {metrics['hit_rate_percent']:.1f}% | "
            f"Available: {metrics['current_available']}/{self.max_pool_size} | "
            f"In Use: {metrics['current_in_use']} | "
            f"Saved: {metrics['bytes_saved_kb']:.1f}KB"
        )
    
    def clear_metrics(self):
        """Reset performance metrics"""
        self.metrics = BufferMetrics()
        self.metrics.current_pool_size = self.max_pool_size
        self.start_time = time.time()
        print(f"🧹 {self.name} metrics cleared")
    
    def resize_pool(self, new_size: int) -> bool:
        """
        Dynamically resize the pool (when not under heavy load)
        
        Args:
            new_size: New maximum pool size
            
        Returns:
            bool: True if resize was successful
        """
        if new_size < 1 or new_size > 32:  # Reasonable limits
            return False
            
        try:
            # Add buffers if expanding
            while self.available_buffers.qsize() < new_size and self.available_buffers.qsize() < self.max_pool_size:
                buffer = bytearray(self.buffer_size)
                self.available_buffers.put_nowait(buffer)
            
            # Remove buffers if shrinking (drain excess)
            while self.available_buffers.qsize() > new_size:
                try:
                    self.available_buffers.get_nowait()
                except queue.Empty:
                    break
            
            old_size = self.max_pool_size
            self.max_pool_size = new_size
            self.metrics.current_pool_size = self.available_buffers.qsize()
            
            print(f"🔄 {self.name} resized: {old_size} → {new_size} buffers")
            return True
            
        except Exception as e:
            print(f"❌ Failed to resize {self.name}: {e}")
            return False


class MultiSizeBufferPool:
    """
    Multi-size buffer pool for different frame sizes
    Optimizes memory usage for various quality levels and resolutions
    """
    
    def __init__(self, sizes_and_counts: Dict[str, tuple]):
        """
        Initialize multi-size buffer pool
        
        Args:
            sizes_and_counts: Dict mapping size_name -> (buffer_size_bytes, pool_count)
            Example: {
                "small": (32768, 4),    # 32KB × 4 buffers  
                "medium": (65536, 6),   # 64KB × 6 buffers
                "large": (131072, 2)    # 128KB × 2 buffers
            }
        """
        self.pools = {}
        self.size_mapping = {}
        
        total_memory = 0
        for size_name, (buffer_size, pool_count) in sizes_and_counts.items():
            pool = FrameBufferPool(
                buffer_size=buffer_size,
                pool_size=pool_count,
                name=f"Pool-{size_name}"
            )
            self.pools[size_name] = pool
            self.size_mapping[size_name] = buffer_size
            total_memory += buffer_size * pool_count
        
        print(f"🎯 MultiSizeBufferPool initialized: {len(self.pools)} pools, {total_memory/1024:.1f}KB total")
    
    def get_optimal_buffer(self, required_size: int) -> tuple[bytearray, str]:
        """
        Get the smallest suitable buffer for the required size
        
        Args:
            required_size: Required buffer size in bytes
            
        Returns:
            tuple: (buffer, pool_name) 
        """
        # Find the smallest pool that can accommodate the required size
        suitable_pools = [
            (name, size) for name, size in self.size_mapping.items() 
            if size >= required_size
        ]
        
        if not suitable_pools:
            # No suitable pool, use the largest available and hope it's enough
            # or let the pool handle fallback allocation
            largest_pool = max(self.size_mapping.items(), key=lambda x: x[1])
            pool_name = largest_pool[0]
        else:
            # Use the smallest suitable pool
            pool_name = min(suitable_pools, key=lambda x: x[1])[0]
        
        buffer = self.pools[pool_name].get_buffer(required_size)
        return buffer, pool_name
    
    def return_buffer(self, buffer: bytearray, pool_name: str):
        """
        Return buffer to the appropriate pool
        
        Args:
            buffer: Buffer to return
            pool_name: Name of the pool it came from
        """
        if pool_name in self.pools:
            self.pools[pool_name].return_buffer(buffer)
    
    def get_combined_metrics(self) -> Dict[str, Any]:
        """Get metrics for all pools"""
        combined = {
            "total_pools": len(self.pools),
            "pools": {},
            "overall": {
                "total_allocations": 0,
                "total_hits": 0,
                "total_misses": 0,
                "total_memory_kb": 0,
                "total_saved_kb": 0
            }
        }
        
        for name, pool in self.pools.items():
            metrics = pool.get_metrics()
            combined["pools"][name] = metrics
            
            # Aggregate overall stats
            combined["overall"]["total_allocations"] += metrics["total_allocations"]
            combined["overall"]["total_hits"] += metrics["pool_hits"]
            combined["overall"]["total_misses"] += metrics["pool_misses"]
            combined["overall"]["total_memory_kb"] += metrics["memory_efficiency"]["allocated_memory_kb"]
            combined["overall"]["total_saved_kb"] += metrics["bytes_saved_kb"]
        
        # Calculate overall hit rate
        total_requests = combined["overall"]["total_allocations"]
        if total_requests > 0:
            combined["overall"]["hit_rate_percent"] = (combined["overall"]["total_hits"] / total_requests) * 100
        else:
            combined["overall"]["hit_rate_percent"] = 0.0
        
        return combined
    
    def get_status_summary(self) -> str:
        """Get summary of all pools"""
        summaries = [pool.get_status_summary() for pool in self.pools.values()]
        return " | ".join(summaries)