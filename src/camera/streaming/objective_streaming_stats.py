"""
Objective Streaming Statistics
Provides measurable, objective streaming metrics without subjective classifications
or unreliable network measurements from the server side.
"""

import time
from typing import Dict, Any, List
from datetime import datetime


class ObjectiveStreamingStats:
    """
    Objective streaming statistics focused on measurable server-side metrics
    
    Removes subjective classifications and unreliable network measurements.
    Focuses on what the server can actually measure accurately.
    """
    
    def __init__(self):
        # Frame production counters (server can measure this accurately)
        self.frames_produced = 0
        self.frames_encoded = 0
        self.encoding_errors = 0
        
        # Session timing
        self.session_start_time = time.time()
        self.last_reset_time = time.time()
        
        # Quality management tracking
        self.quality_changes = 0
        self.client_count_changes = 0
        self.max_concurrent_clients = 0
        self.total_client_connections = 0
        
        # Frame interval tracking (for production FPS)
        self.frame_intervals: List[float] = []
        self.max_interval_samples = 100
        self.last_frame_time = 0.0
        
        # Encoding performance tracking
        self.encoding_times: List[float] = []
        self.max_encoding_samples = 50
        
        print("📊 ObjectiveStreamingStats initialized")
    
    def record_frame_produced(self):
        """Record a frame successfully produced by camera"""
        current_time = time.time()
        self.frames_produced += 1
        
        # Record frame interval for production FPS calculation
        if self.last_frame_time > 0:
            interval = current_time - self.last_frame_time
            self.frame_intervals.append(interval)
            
            # Keep only recent samples
            if len(self.frame_intervals) > self.max_interval_samples:
                self.frame_intervals.pop(0)
        
        self.last_frame_time = current_time
    
    def record_frame_encoded(self, encoding_time: float):
        """Record a frame successfully encoded with timing"""
        self.frames_encoded += 1
        
        # Record encoding performance
        self.encoding_times.append(encoding_time)
        if len(self.encoding_times) > self.max_encoding_samples:
            self.encoding_times.pop(0)
    
    def record_encoding_error(self):
        """Record an encoding failure"""
        self.encoding_errors += 1
    
    def record_quality_change(self):
        """Record a quality adaptation event"""
        self.quality_changes += 1
    
    def record_client_count_change(self, new_count: int):
        """Record client count change"""
        if new_count != getattr(self, '_last_client_count', 0):
            self.client_count_changes += 1
            self.max_concurrent_clients = max(self.max_concurrent_clients, new_count)
            self._last_client_count = new_count
    
    def record_client_connection(self):
        """Record new client connection"""
        self.total_client_connections += 1
    
    def get_production_fps(self) -> float:
        """Get camera frame production FPS (server-side measurement)"""
        if len(self.frame_intervals) < 3:
            return 0.0
        
        avg_interval = sum(self.frame_intervals) / len(self.frame_intervals)
        return 1.0 / avg_interval if avg_interval > 0 else 0.0
    
    def get_encoding_performance(self) -> Dict[str, Any]:
        """Get encoding performance metrics"""
        if not self.encoding_times:
            return {
                "samples": 0,
                "average_time_ms": 0.0,
                "max_time_ms": 0.0,
                "min_time_ms": 0.0
            }
        
        encoding_times_ms = [t * 1000 for t in self.encoding_times]
        
        return {
            "samples": len(self.encoding_times),
            "average_time_ms": round(sum(encoding_times_ms) / len(encoding_times_ms), 2),
            "max_time_ms": round(max(encoding_times_ms), 2),
            "min_time_ms": round(min(encoding_times_ms), 2),
            "encoding_success_rate": (
                self.frames_encoded / (self.frames_encoded + self.encoding_errors)
                if (self.frames_encoded + self.encoding_errors) > 0 else 1.0
            )
        }
    
    def get_objective_stats(self) -> Dict[str, Any]:
        """Get comprehensive objective statistics"""
        current_time = time.time()
        session_duration = current_time - self.session_start_time
        time_since_reset = current_time - self.last_reset_time
        
        # Production rate (what server can actually measure)
        production_fps = self.get_production_fps()
        
        # Session FPS (alternative calculation)
        session_fps = self.frames_produced / session_duration if session_duration > 0 else 0.0
        
        return {
            "session": {
                "start_time": datetime.fromtimestamp(self.session_start_time).isoformat(),
                "duration_seconds": round(session_duration, 1),
                "duration_minutes": round(session_duration / 60.0, 2),
                "time_since_reset": round(time_since_reset, 1)
            },
            "production": {
                "frames_produced": self.frames_produced,
                "frames_encoded": self.frames_encoded,
                "encoding_errors": self.encoding_errors,
                "production_fps": round(production_fps, 2),
                "session_average_fps": round(session_fps, 2),
                "frame_interval_samples": len(self.frame_intervals)
            },
            "encoding": self.get_encoding_performance(),
            "adaptation": {
                "quality_changes": self.quality_changes,
                "client_count_changes": self.client_count_changes,
                "max_concurrent_clients": self.max_concurrent_clients,
                "total_client_connections": self.total_client_connections
            },
            "timing": {
                "last_frame_seconds_ago": round(current_time - self.last_frame_time, 1) if self.last_frame_time > 0 else None,
                "is_actively_producing": (current_time - self.last_frame_time) < 5.0 if self.last_frame_time > 0 else False
            }
        }
    
    def get_health_indicators(self) -> Dict[str, Any]:
        """Get objective health indicators with measurable thresholds"""
        stats = self.get_objective_stats()
        current_time = time.time()
        
        # Objective thresholds (measurable, not subjective)
        fps_threshold_low = 15.0
        encoding_error_rate_threshold = 0.05  # 5%
        stale_threshold_seconds = 10.0
        
        # Calculate flags
        production_fps = stats["production"]["production_fps"]
        encoding_error_rate = (
            self.encoding_errors / (self.frames_encoded + self.encoding_errors)
            if (self.frames_encoded + self.encoding_errors) > 0 else 0.0
        )
        time_since_last_frame = current_time - self.last_frame_time if self.last_frame_time > 0 else float('inf')
        
        flags = {
            "low_production_fps": production_fps < fps_threshold_low and production_fps > 0,
            "high_encoding_error_rate": encoding_error_rate > encoding_error_rate_threshold,
            "stale_frames": time_since_last_frame > stale_threshold_seconds,
            "no_frame_production": self.frames_produced == 0
        }
        
        return {
            "flags": flags,
            "active_issues": sum(flags.values()),
            "thresholds": {
                "min_fps": fps_threshold_low,
                "max_encoding_error_rate": encoding_error_rate_threshold,
                "max_stale_seconds": stale_threshold_seconds
            },
            "measurements": {
                "current_production_fps": production_fps,
                "current_encoding_error_rate": round(encoding_error_rate, 4),
                "seconds_since_last_frame": round(time_since_last_frame, 1) if time_since_last_frame != float('inf') else None
            }
        }
    
    def reset_stats(self):
        """Reset statistics to start fresh"""
        self.frames_produced = 0
        self.frames_encoded = 0
        self.encoding_errors = 0
        self.quality_changes = 0
        self.client_count_changes = 0
        self.total_client_connections = 0
        
        self.last_reset_time = time.time()
        self.frame_intervals.clear()
        self.encoding_times.clear()
        self.last_frame_time = 0.0
        
        print("📊 Objective streaming statistics reset")
    
    def get_summary(self) -> str:
        """Get human-readable summary"""
        stats = self.get_objective_stats()
        health = self.get_health_indicators()
        
        issues = f" ({health['active_issues']} issues)" if health['active_issues'] > 0 else ""
        
        return (
            f"Produced: {stats['production']['frames_produced']} frames | "
            f"FPS: {stats['production']['production_fps']} | "
            f"Clients: {stats['adaptation']['max_concurrent_clients']} max{issues}"
        )