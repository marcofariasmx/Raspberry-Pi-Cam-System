"""
Health Monitor - System Health Monitoring and Recovery

Monitors camera hardware, streaming performance, and system health.
Detects issues like frozen frames, hardware timeouts, and resource problems.
Coordinates automatic recovery actions.
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass
from enum import Enum

from src.config import AppConfig
from .camera_exceptions import handle_camera_error


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    WARNING = "warning" 
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthMetric:
    """Individual health metric"""
    name: str
    status: HealthStatus
    value: Any
    message: str
    last_updated: datetime
    threshold_warning: Optional[float] = None
    threshold_critical: Optional[float] = None


@dataclass
class RecoveryAction:
    """Recovery action definition"""
    name: str
    action: Callable
    priority: int  # Lower numbers = higher priority
    max_attempts: int = 3
    cooldown_seconds: int = 30
    description: str = ""


class HealthMonitor:
    """
    Comprehensive system health monitoring
    
    Monitors:
    - Camera hardware connectivity
    - Frame generation and staleness
    - Streaming performance
    - Resource usage
    - Session management
    
    Provides:
    - Real-time health status
    - Automatic problem detection
    - Recovery action coordination
    - Performance metrics tracking
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.is_running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # Health metrics storage
        self.metrics: Dict[str, HealthMetric] = {}
        self.overall_status = HealthStatus.UNKNOWN
        
        # Component references (set by external components)
        self.camera_manager = None
        self.session_manager = None
        self.recovery_manager = None
        
        # Monitoring intervals
        self.camera_check_interval = 10.0  # seconds
        self.stream_check_interval = 5.0   # seconds
        self.session_check_interval = 30.0 # seconds
        
        # Frame staleness detection
        self.last_frame_time: Optional[float] = None
        self.frame_stale_threshold = 10.0  # seconds
        self.consecutive_stale_frames = 0
        self.max_stale_frames = 3
        
        # Hardware timeout detection
        self.last_hardware_check = time.time()
        self.hardware_timeout_threshold = 30.0  # seconds
        self.hardware_failures = 0
        self.max_hardware_failures = 3
        
        # Performance tracking
        self.performance_history: List[Dict[str, Any]] = []
        self.max_history_length = 100
        
        # Recovery coordination
        self.recovery_actions: List[RecoveryAction] = []
        self.last_recovery_attempt = {}
        
        print("🏥 HealthMonitor initialized")
    
    def set_component_references(self, camera_manager=None, session_manager=None, recovery_manager=None):
        """Set references to other system components"""
        if camera_manager:
            self.camera_manager = camera_manager
        if session_manager:
            self.session_manager = session_manager
        if recovery_manager:
            self.recovery_manager = recovery_manager
    
    def register_recovery_action(self, action: RecoveryAction):
        """Register a recovery action"""
        self.recovery_actions.append(action)
        self.recovery_actions.sort(key=lambda x: x.priority)
        print(f"🔧 Recovery action registered: {action.name} (priority: {action.priority})")
    
    def start_monitoring(self):
        """Start the health monitoring service"""
        if self.is_running:
            return
        
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        print("🏥 Health monitoring started")
    
    def stop_monitoring(self):
        """Stop the health monitoring service"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
        print("🏥 Health monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        last_camera_check = 0
        last_stream_check = 0
        last_session_check = 0
        
        while self.is_running:
            try:
                current_time = time.time()
                
                # Camera health check
                if current_time - last_camera_check >= self.camera_check_interval:
                    self._check_camera_health()
                    last_camera_check = current_time
                
                # Stream health check
                if current_time - last_stream_check >= self.stream_check_interval:
                    self._check_streaming_health()
                    last_stream_check = current_time
                
                # Session health check
                if current_time - last_session_check >= self.session_check_interval:
                    self._check_session_health()
                    last_session_check = current_time
                
                # Update overall status
                self._update_overall_status()
                
                # Check for recovery needs
                self._check_recovery_needs()
                
                # Sleep before next iteration
                time.sleep(1.0)
                
            except Exception as e:
                print(f"❌ Health monitoring error: {e}")
                time.sleep(5.0)  # Longer sleep on error
    
    @handle_camera_error
    def _check_camera_health(self):
        """Check camera hardware health"""
        try:
            if not self.camera_manager:
                self._update_metric("camera_availability", HealthStatus.UNKNOWN, False, 
                                  "Camera manager not available")
                return
            
            # Check if camera is initialized
            camera_available = self.camera_manager.camera_device is not None
            status = HealthStatus.HEALTHY if camera_available else HealthStatus.CRITICAL
            self._update_metric("camera_availability", status, camera_available,
                              "Camera hardware available" if camera_available else "Camera hardware not available")
            
            if camera_available:
                # Check for hardware timeouts
                self._check_hardware_timeouts()
                
                # Check frame generation
                self._check_frame_generation()
                
                # Check streaming status
                self._check_streaming_status()
        
        except Exception as e:
            self._update_metric("camera_availability", HealthStatus.CRITICAL, False,
                              f"Camera health check failed: {str(e)}")
            self.hardware_failures += 1
    
    def _check_hardware_timeouts(self):
        """Check for hardware timeout issues"""
        try:
            # Get camera status to verify hardware responsiveness
            if self.camera_manager:
                status = self.camera_manager.get_status()
                
                # Check if camera is responsive
                if status.get("available", False):
                    self.hardware_failures = 0  # Reset failure counter
                    self.last_hardware_check = time.time()
                    self._update_metric("hardware_timeout", HealthStatus.HEALTHY, False,
                                      "Hardware responding normally")
                else:
                    self.hardware_failures += 1
                    
                # Check for repeated hardware failures
                if self.hardware_failures >= self.max_hardware_failures:
                    self._update_metric("hardware_timeout", HealthStatus.CRITICAL, True,
                                      f"Hardware failures detected: {self.hardware_failures}")
                elif self.hardware_failures > 0:
                    self._update_metric("hardware_timeout", HealthStatus.WARNING, False,
                                      f"Hardware instability detected: {self.hardware_failures} failures")
        
        except Exception as e:
            self.hardware_failures += 1
            self._update_metric("hardware_timeout", HealthStatus.WARNING, False,
                              f"Hardware timeout check failed: {str(e)}")
    
    def _check_frame_generation(self):
        """Check if frames are being generated and not stale"""
        try:
            if not self.camera_manager or not self.camera_manager.is_streaming:
                self._update_metric("frame_generation", HealthStatus.HEALTHY, True,
                                  "Streaming not active")
                return
            
            # Get streaming stats
            stats = self.camera_manager.get_streaming_stats()
            
            # Check frame generation rate
            current_time = time.time()
            frames_sent = stats.get("adaptation", {}).get("frames_sent", 0)
            
            # Detect stale frames by checking if frame count is increasing
            if hasattr(self, '_last_frame_count'):
                if frames_sent <= self._last_frame_count:
                    self.consecutive_stale_frames += 1
                else:
                    self.consecutive_stale_frames = 0
            
            self._last_frame_count = frames_sent
            
            # Evaluate frame generation health
            if self.consecutive_stale_frames >= self.max_stale_frames:
                self._update_metric("frame_generation", HealthStatus.CRITICAL, True,
                                  f"Frames appear frozen: {self.consecutive_stale_frames} consecutive stale checks")
            elif self.consecutive_stale_frames > 0:
                self._update_metric("frame_generation", HealthStatus.WARNING, False,
                                  f"Frame generation may be slow: {self.consecutive_stale_frames} stale checks")
            else:
                self._update_metric("frame_generation", HealthStatus.HEALTHY, False,
                                  "Frames generating normally")
        
        except Exception as e:
            self._update_metric("frame_generation", HealthStatus.WARNING, False,
                              f"Frame generation check failed: {str(e)}")
    
    def _check_streaming_status(self):
        """Check streaming health and performance"""
        try:
            if not self.camera_manager:
                return
            
            streaming_active = self.camera_manager.is_streaming
            
            if streaming_active:
                # Get detailed streaming stats
                stats = self.camera_manager.get_streaming_stats()
                performance = stats.get("performance", {})
                
                # Check for network issues
                network_slow = performance.get("network_slow", False)
                frames_dropped = performance.get("frames_dropped", 0)
                
                if network_slow or frames_dropped > 10:
                    self._update_metric("streaming_performance", HealthStatus.WARNING, False,
                                      f"Streaming issues detected: slow_network={network_slow}, dropped_frames={frames_dropped}")
                else:
                    self._update_metric("streaming_performance", HealthStatus.HEALTHY, False,
                                      "Streaming performance normal")
            else:
                self._update_metric("streaming_performance", HealthStatus.HEALTHY, False,
                                  "Streaming not active")
        
        except Exception as e:
            self._update_metric("streaming_performance", HealthStatus.WARNING, False,
                              f"Streaming status check failed: {str(e)}")
    
    def _check_streaming_health(self):
        """Check detailed streaming health"""
        try:
            if not self.camera_manager or not self.camera_manager.is_streaming:
                return
            
            # Get comprehensive streaming metrics
            metrics = self.camera_manager.get_streaming_stats()
            
            # Check adaptation metrics
            adaptation = metrics.get("adaptation", {})
            drop_rate = adaptation.get("drop_rate", 0.0)
            
            if drop_rate > 0.5:  # More than 50% drops
                self._update_metric("stream_quality", HealthStatus.CRITICAL, True,
                                  f"High frame drop rate: {drop_rate:.2%}")
            elif drop_rate > 0.1:  # More than 10% drops
                self._update_metric("stream_quality", HealthStatus.WARNING, False,
                                  f"Elevated frame drop rate: {drop_rate:.2%}")
            else:
                self._update_metric("stream_quality", HealthStatus.HEALTHY, False,
                                  f"Stream quality good: {drop_rate:.2%} drop rate")
        
        except Exception as e:
            self._update_metric("stream_quality", HealthStatus.WARNING, False,
                              f"Stream health check failed: {str(e)}")
    
    def _check_session_health(self):
        """Check session management health"""
        try:
            if not self.session_manager:
                self._update_metric("session_management", HealthStatus.UNKNOWN, False,
                                  "Session manager not available")
                return
            
            # Get session statistics
            session_stats = self.session_manager.get_session_stats()
            active_sessions = session_stats.get("active_sessions", 0)
            expired_sessions = session_stats.get("expired_sessions_cleaned", 0)
            
            # Check for session issues
            if active_sessions > 10:  # Too many active sessions
                self._update_metric("session_management", HealthStatus.WARNING, False,
                                  f"High number of active sessions: {active_sessions}")
            else:
                self._update_metric("session_management", HealthStatus.HEALTHY, False,
                                  f"Session management healthy: {active_sessions} active sessions")
        
        except Exception as e:
            self._update_metric("session_management", HealthStatus.WARNING, False,
                              f"Session health check failed: {str(e)}")
    
    def _update_metric(self, name: str, status: HealthStatus, needs_recovery: bool, message: str):
        """Update a health metric"""
        self.metrics[name] = HealthMetric(
            name=name,
            status=status,
            value=needs_recovery,
            message=message,
            last_updated=datetime.now()
        )
    
    def _update_overall_status(self):
        """Update overall system health status"""
        if not self.metrics:
            self.overall_status = HealthStatus.UNKNOWN
            return
        
        # Determine overall status based on individual metrics
        has_critical = any(m.status == HealthStatus.CRITICAL for m in self.metrics.values())
        has_warning = any(m.status == HealthStatus.WARNING for m in self.metrics.values())
        
        if has_critical:
            self.overall_status = HealthStatus.CRITICAL
        elif has_warning:
            self.overall_status = HealthStatus.WARNING
        else:
            self.overall_status = HealthStatus.HEALTHY
    
    def _check_recovery_needs(self):
        """Check if any metrics need recovery actions"""
        try:
            for metric in self.metrics.values():
                if metric.value is True and metric.status in [HealthStatus.CRITICAL, HealthStatus.WARNING]:
                    self._trigger_recovery(metric)
        except Exception as e:
            print(f"❌ Recovery check failed: {e}")
    
    def _trigger_recovery(self, metric: HealthMetric):
        """Trigger recovery actions for a failed metric"""
        if not self.recovery_manager:
            return
        
        # Check cooldown
        last_attempt = self.last_recovery_attempt.get(metric.name, 0)
        if time.time() - last_attempt < 30:  # 30 second cooldown
            return
        
        print(f"🚨 Triggering recovery for: {metric.name} - {metric.message}")
        
        # Delegate to recovery manager
        success = self.recovery_manager.attempt_recovery(metric.name, metric)
        
        self.last_recovery_attempt[metric.name] = time.time()
        
        if success:
            print(f"✅ Recovery successful for: {metric.name}")
        else:
            print(f"❌ Recovery failed for: {metric.name}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        return {
            "overall_status": self.overall_status.value,
            "timestamp": datetime.now().isoformat(),
            "metrics": {
                name: {
                    "status": metric.status.value,
                    "message": metric.message,
                    "last_updated": metric.last_updated.isoformat(),
                    "needs_recovery": metric.value
                }
                for name, metric in self.metrics.items()
            },
            "monitoring_active": self.is_running,
            "hardware_failures": self.hardware_failures,
            "consecutive_stale_frames": self.consecutive_stale_frames
        }
    
    def get_detailed_diagnostics(self) -> Dict[str, Any]:
        """Get detailed diagnostic information"""
        diagnostics = self.get_health_status()
        
        # Add performance history
        diagnostics["performance_history"] = self.performance_history[-10:]  # Last 10 entries
        
        # Add recovery action status
        diagnostics["recovery_actions"] = [
            {
                "name": action.name,
                "priority": action.priority,
                "description": action.description,
                "last_attempt": self.last_recovery_attempt.get(action.name)
            }
            for action in self.recovery_actions
        ]
        
        # Add system information
        diagnostics["system_info"] = {
            "monitoring_intervals": {
                "camera_check": self.camera_check_interval,
                "stream_check": self.stream_check_interval,
                "session_check": self.session_check_interval
            },
            "thresholds": {
                "frame_stale_threshold": self.frame_stale_threshold,
                "max_stale_frames": self.max_stale_frames,
                "hardware_timeout_threshold": self.hardware_timeout_threshold,
                "max_hardware_failures": self.max_hardware_failures
            }
        }
        
        return diagnostics
    
    def force_health_check(self) -> Dict[str, Any]:
        """Force an immediate comprehensive health check"""
        print("🏥 Forcing comprehensive health check...")
        
        self._check_camera_health()
        self._check_streaming_health()
        self._check_session_health()
        self._update_overall_status()
        
        return self.get_health_status()
    
    def reset_metrics(self):
        """Reset all health metrics"""
        self.metrics.clear()
        self.hardware_failures = 0
        self.consecutive_stale_frames = 0
        self.last_recovery_attempt.clear()
        print("🏥 Health metrics reset")
