"""
Recovery Manager - Automatic System Recovery and Self-Healing

Handles automatic recovery from system failures, camera timeouts,
streaming issues, and other problems detected by the health monitor.
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from enum import Enum

from src.config import AppConfig
from .health_monitor import HealthMetric


class RecoveryResult(Enum):
    """Recovery operation result"""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    IN_PROGRESS = "in_progress"


@dataclass
class RecoveryOperation:
    """Recovery operation record"""
    name: str
    target: str  # What was being recovered
    result: RecoveryResult
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    recovery_actions: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if self.recovery_actions is None:
            self.recovery_actions = []


class RecoveryManager:
    """
    Automatic recovery and self-healing system
    
    Provides:
    - Automatic camera re-initialization
    - Stream restart and recovery
    - Session cleanup and recovery
    - Hardware timeout recovery
    - Progressive recovery strategies
    - Recovery history and analytics
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        
        # Component references
        self.camera_manager = None
        self.session_manager = None
        self.health_monitor = None
        self.streaming_validator = None
        
        # Recovery configuration
        self.max_recovery_attempts = 3
        self.recovery_cooldown_seconds = 60  # Wait between recovery attempts
        self.progressive_backoff = True  # Increase delay with each attempt
        
        # Recovery state
        self.recovery_history: List[RecoveryOperation] = []
        self.max_history_length = 50
        self.recovery_lock = threading.RLock()
        
        # Attempt tracking
        self.recovery_attempts: Dict[str, List[float]] = {}
        self.last_recovery_time: Dict[str, float] = {}
        
        # Recovery strategies
        self.recovery_strategies: Dict[str, List[Callable]] = {}
        self._initialize_recovery_strategies()
        
        print("🔧 RecoveryManager initialized")
    
    def set_component_references(self, camera_manager=None, session_manager=None, 
                               health_monitor=None, streaming_validator=None):
        """Set references to other system components"""
        if camera_manager:
            self.camera_manager = camera_manager
        if session_manager:
            self.session_manager = session_manager
        if health_monitor:
            self.health_monitor = health_monitor
        if streaming_validator:
            self.streaming_validator = streaming_validator
    
    def _initialize_recovery_strategies(self):
        """Initialize recovery strategies for different types of problems"""
        
        # Camera hardware issues
        self.recovery_strategies["camera_availability"] = [
            self._restart_camera_device,
            self._reinitialize_camera_system,
            self._reset_camera_configuration
        ]
        
        # Hardware timeout issues
        self.recovery_strategies["hardware_timeout"] = [
            self._reset_hardware_connection,
            self._restart_camera_device,
            self._force_camera_restart
        ]
        
        # Frame generation issues
        self.recovery_strategies["frame_generation"] = [
            self._restart_streaming,
            self._reset_frame_buffer,
            self._restart_camera_device
        ]
        
        # Stream quality issues
        self.recovery_strategies["stream_quality"] = [
            self._reduce_stream_quality,
            self._restart_streaming,
            self._reset_adaptive_settings
        ]
        
        # Session management issues
        self.recovery_strategies["session_management"] = [
            self._cleanup_expired_sessions,
            self._reset_session_state,
            self._restart_session_manager
        ]
        
        # Streaming performance issues
        self.recovery_strategies["streaming_performance"] = [
            self._optimize_streaming_settings,
            self._restart_streaming,
            self._reset_network_monitoring
        ]
    
    def attempt_recovery(self, problem_type: str, metric: HealthMetric) -> bool:
        """
        Attempt recovery for a specific problem
        
        Args:
            problem_type: Type of problem to recover from
            metric: Health metric that triggered recovery
            
        Returns:
            bool: True if recovery was successful
        """
        with self.recovery_lock:
            current_time = time.time()
            
            # Check recovery cooldown
            if problem_type in self.last_recovery_time:
                time_since_last = current_time - self.last_recovery_time[problem_type]
                if time_since_last < self.recovery_cooldown_seconds:
                    print(f"🕒 Recovery cooldown active for {problem_type}: {time_since_last:.1f}s ago")
                    return False
            
            # Check maximum attempts
            if problem_type not in self.recovery_attempts:
                self.recovery_attempts[problem_type] = []
            
            # Clean old attempts (last hour)
            cutoff_time = current_time - 3600
            self.recovery_attempts[problem_type] = [
                attempt for attempt in self.recovery_attempts[problem_type]
                if attempt > cutoff_time
            ]
            
            if len(self.recovery_attempts[problem_type]) >= self.max_recovery_attempts:
                print(f"🚫 Maximum recovery attempts reached for {problem_type}")
                return False
            
            # Record recovery attempt
            self.recovery_attempts[problem_type].append(current_time)
            self.last_recovery_time[problem_type] = current_time
            
            # Start recovery operation
            operation = RecoveryOperation(
                name=f"recovery_{problem_type}_{int(current_time)}",
                target=problem_type,
                result=RecoveryResult.IN_PROGRESS,
                started_at=datetime.now()
            )
            
            print(f"🔧 Starting recovery for: {problem_type}")
            
            try:
                # Execute recovery strategies
                recovery_success = self._execute_recovery_strategies(problem_type, operation)
                
                # Update operation result
                operation.completed_at = datetime.now()
                if recovery_success:
                    operation.result = RecoveryResult.SUCCESS
                    print(f"✅ Recovery successful for: {problem_type}")
                else:
                    operation.result = RecoveryResult.FAILED
                    print(f"❌ Recovery failed for: {problem_type}")
                
                # Store in history
                self._store_recovery_operation(operation)
                
                return recovery_success
                
            except Exception as e:
                operation.completed_at = datetime.now()
                operation.result = RecoveryResult.FAILED
                operation.error_message = str(e)
                self._store_recovery_operation(operation)
                
                print(f"❌ Recovery exception for {problem_type}: {e}")
                return False
    
    def _execute_recovery_strategies(self, problem_type: str, operation: RecoveryOperation) -> bool:
        """Execute recovery strategies for a problem type"""
        strategies = self.recovery_strategies.get(problem_type, [])
        
        if not strategies:
            print(f"⚠️ No recovery strategies defined for: {problem_type}")
            return False
        
        for i, strategy in enumerate(strategies):
            try:
                print(f"🔧 Executing recovery strategy {i+1}/{len(strategies)}: {strategy.__name__}")
                
                success = strategy()
                operation.recovery_actions.append(f"{strategy.__name__}: {'success' if success else 'failed'}")
                
                if success:
                    print(f"✅ Recovery strategy succeeded: {strategy.__name__}")
                    return True
                else:
                    print(f"❌ Recovery strategy failed: {strategy.__name__}")
                    
                # Brief pause between strategies
                time.sleep(2.0)
                
            except Exception as e:
                error_msg = f"{strategy.__name__}: error - {str(e)}"
                operation.recovery_actions.append(error_msg)
                print(f"❌ Recovery strategy exception: {error_msg}")
        
        print(f"❌ All recovery strategies failed for: {problem_type}")
        return False
    
    # Recovery Strategy Implementations
    
    def _restart_camera_device(self) -> bool:
        """Restart camera device"""
        try:
            if not self.camera_manager:
                return False
            
            print("🔄 Restarting camera device...")
            
            # Stop streaming if active
            if self.camera_manager.is_streaming:
                self.camera_manager.stop_streaming()
                time.sleep(2.0)
            
            # Cleanup current camera
            self.camera_manager.cleanup()
            time.sleep(3.0)
            
            # Reinitialize camera
            success = self.camera_manager.init_camera()
            
            if success:
                print("✅ Camera device restarted successfully")
                return True
            else:
                print("❌ Camera device restart failed")
                return False
                
        except Exception as e:
            print(f"❌ Camera restart exception: {e}")
            return False
    
    def _reinitialize_camera_system(self) -> bool:
        """Reinitialize entire camera system"""
        try:
            if not self.camera_manager:
                return False
            
            print("🔄 Reinitializing camera system...")
            
            # Full cleanup
            self.camera_manager.cleanup()
            time.sleep(5.0)
            
            # Reset adaptive settings
            if hasattr(self.camera_manager, 'reset_adaptive_settings'):
                self.camera_manager.reset_adaptive_settings()
            
            # Reinitialize
            success = self.camera_manager.init_camera()
            
            if success:
                print("✅ Camera system reinitialized successfully")
                return True
            else:
                print("❌ Camera system reinitialization failed")
                return False
                
        except Exception as e:
            print(f"❌ Camera system reinitialization exception: {e}")
            return False
    
    def _reset_camera_configuration(self) -> bool:
        """Reset camera configuration to defaults"""
        try:
            if not self.camera_manager:
                return False
            
            print("🔄 Resetting camera configuration...")
            
            # Reset hardware detector
            if hasattr(self.camera_manager, 'hardware_detector'):
                self.camera_manager.hardware_detector.sensor_resolution = None
                self.camera_manager.hardware_detector.camera_module = "unknown"
            
            # Cleanup and reinitialize
            self.camera_manager.cleanup()
            time.sleep(3.0)
            
            success = self.camera_manager.init_camera()
            
            if success:
                print("✅ Camera configuration reset successfully")
                return True
            else:
                print("❌ Camera configuration reset failed")
                return False
                
        except Exception as e:
            print(f"❌ Camera configuration reset exception: {e}")
            return False
    
    def _reset_hardware_connection(self) -> bool:
        """Reset hardware connection"""
        try:
            if not self.camera_manager:
                return False
            
            print("🔄 Resetting hardware connection...")
            
            # Stop all camera operations
            if self.camera_manager.is_streaming:
                self.camera_manager.stop_streaming()
            
            # Close camera device
            if self.camera_manager.camera_device:
                try:
                    self.camera_manager.camera_device.stop()
                    self.camera_manager.camera_device.close()
                except:
                    pass
                self.camera_manager.camera_device = None
            
            # Wait for hardware to reset
            time.sleep(5.0)
            
            # Reinitialize
            success = self.camera_manager.init_camera()
            
            if success:
                print("✅ Hardware connection reset successfully")
                return True
            else:
                print("❌ Hardware connection reset failed")
                return False
                
        except Exception as e:
            print(f"❌ Hardware connection reset exception: {e}")
            return False
    
    def _force_camera_restart(self) -> bool:
        """Force camera restart with aggressive cleanup"""
        try:
            if not self.camera_manager:
                return False
            
            print("🔄 Force restarting camera...")
            
            # Aggressive cleanup
            try:
                if self.camera_manager.is_streaming:
                    self.camera_manager.stop_streaming()
                
                if self.camera_manager.camera_device:
                    self.camera_manager.camera_device.stop()
                    self.camera_manager.camera_device.close()
                    
                self.camera_manager.camera_device = None
                self.camera_manager.is_streaming = False
                
            except Exception as e:
                print(f"⚠️ Cleanup exception (continuing): {e}")
            
            # Extended wait
            time.sleep(10.0)
            
            # Try minimal initialization
            success = self.camera_manager.init_camera()
            
            if success:
                print("✅ Force camera restart successful")
                return True
            else:
                print("❌ Force camera restart failed")
                return False
                
        except Exception as e:
            print(f"❌ Force camera restart exception: {e}")
            return False
    
    def _restart_streaming(self) -> bool:
        """Restart streaming"""
        try:
            if not self.camera_manager:
                return False
            
            print("🔄 Restarting streaming...")
            
            # Stop current streaming
            if self.camera_manager.is_streaming:
                self.camera_manager.stop_streaming()
                time.sleep(3.0)
            
            # Start streaming again
            success = self.camera_manager.setup_streaming()
            
            if success:
                print("✅ Streaming restarted successfully")
                return True
            else:
                print("❌ Streaming restart failed")
                return False
                
        except Exception as e:
            print(f"❌ Streaming restart exception: {e}")
            return False
    
    def _reset_frame_buffer(self) -> bool:
        """Reset frame buffer"""
        try:
            if not self.camera_manager or not hasattr(self.camera_manager, 'stream_output'):
                return False
            
            print("🔄 Resetting frame buffer...")
            
            # Reset stream output metrics
            if self.camera_manager.stream_output:
                self.camera_manager.stream_output.reset_performance_counters()
            
            # Reset streaming stats
            if hasattr(self.camera_manager, 'streaming_stats'):
                # Reset streaming statistics
                pass
            
            print("✅ Frame buffer reset successfully")
            return True
                
        except Exception as e:
            print(f"❌ Frame buffer reset exception: {e}")
            return False
    
    def _reduce_stream_quality(self) -> bool:
        """Reduce stream quality to improve performance"""
        try:
            if not self.camera_manager:
                return False
            
            print("🔄 Reducing stream quality...")
            
            # Try to reduce quality
            if hasattr(self.camera_manager, 'force_quality_change'):
                # Reduce quality by 20%
                current_quality = getattr(self.camera_manager.quality_adapter, 'current_quality', 85)
                new_quality = max(30, int(current_quality * 0.8))
                success = self.camera_manager.force_quality_change(new_quality)
                
                if success:
                    print(f"✅ Stream quality reduced to {new_quality}%")
                    return True
            
            print("❌ Stream quality reduction failed")
            return False
                
        except Exception as e:
            print(f"❌ Stream quality reduction exception: {e}")
            return False
    
    def _reset_adaptive_settings(self) -> bool:
        """Reset adaptive streaming settings"""
        try:
            if not self.camera_manager:
                return False
            
            print("🔄 Resetting adaptive settings...")
            
            if hasattr(self.camera_manager, 'reset_adaptive_settings'):
                self.camera_manager.reset_adaptive_settings()
                print("✅ Adaptive settings reset successfully")
                return True
            
            print("❌ Adaptive settings reset not available")
            return False
                
        except Exception as e:
            print(f"❌ Adaptive settings reset exception: {e}")
            return False
    
    def _cleanup_expired_sessions(self) -> bool:
        """Cleanup expired sessions"""
        try:
            if not self.session_manager:
                return False
            
            print("🔄 Cleaning up expired sessions...")
            
            result = self.session_manager.force_cleanup()
            
            if result["sessions_removed"] > 0 or result["ips_unblocked"] > 0:
                print(f"✅ Session cleanup successful: {result}")
                return True
            else:
                print("✅ Session cleanup completed (no items removed)")
                return True
                
        except Exception as e:
            print(f"❌ Session cleanup exception: {e}")
            return False
    
    def _reset_session_state(self) -> bool:
        """Reset session manager state"""
        try:
            if not self.session_manager:
                return False
            
            print("🔄 Resetting session state...")
            
            # Reset statistics
            if hasattr(self.session_manager, 'stats'):
                self.session_manager.stats["validation_failures"] = 0
            
            # Clear failed attempts for all IPs
            self.session_manager.failed_attempts.clear()
            self.session_manager.blocked_ips.clear()
            
            print("✅ Session state reset successfully")
            return True
                
        except Exception as e:
            print(f"❌ Session state reset exception: {e}")
            return False
    
    def _restart_session_manager(self) -> bool:
        """Restart session manager"""
        try:
            if not self.session_manager:
                return False
            
            print("🔄 Restarting session manager...")
            
            # Stop cleanup service
            self.session_manager.stop_cleanup_service()
            time.sleep(2.0)
            
            # Start cleanup service
            self.session_manager.start_cleanup_service()
            
            print("✅ Session manager restarted successfully")
            return True
                
        except Exception as e:
            print(f"❌ Session manager restart exception: {e}")
            return False
    
    def _optimize_streaming_settings(self) -> bool:
        """Optimize streaming settings for better performance"""
        try:
            if not self.camera_manager:
                return False
            
            print("🔄 Optimizing streaming settings...")
            
            # Reduce frame rate if high
            if hasattr(self.camera_manager, 'force_frame_rate_change'):
                current_fps = getattr(self.camera_manager.quality_adapter, 'current_frame_rate', 30)
                if current_fps > 15:
                    new_fps = max(10, int(current_fps * 0.7))
                    self.camera_manager.force_frame_rate_change(new_fps)
                    print(f"📊 Frame rate reduced to {new_fps} fps")
            
            # Reduce quality if high
            if hasattr(self.camera_manager, 'force_quality_change'):
                current_quality = getattr(self.camera_manager.quality_adapter, 'current_quality', 85)
                if current_quality > 60:
                    new_quality = max(50, int(current_quality * 0.8))
                    self.camera_manager.force_quality_change(new_quality)
                    print(f"📊 Quality reduced to {new_quality}%")
            
            print("✅ Streaming settings optimized")
            return True
                
        except Exception as e:
            print(f"❌ Streaming optimization exception: {e}")
            return False
    
    def _reset_network_monitoring(self) -> bool:
        """Reset network monitoring"""
        try:
            if not self.camera_manager or not hasattr(self.camera_manager, 'network_monitor'):
                return False
            
            print("🔄 Resetting network monitoring...")
            
            # Reset network monitor
            network_monitor = self.camera_manager.network_monitor
            if hasattr(network_monitor, 'reset_monitoring_state'):
                network_monitor.reset_monitoring_state()
            
            print("✅ Network monitoring reset successfully")
            return True
                
        except Exception as e:
            print(f"❌ Network monitoring reset exception: {e}")
            return False
    
    def _store_recovery_operation(self, operation: RecoveryOperation):
        """Store recovery operation in history"""
        self.recovery_history.append(operation)
        
        # Keep only recent history
        if len(self.recovery_history) > self.max_history_length:
            self.recovery_history.pop(0)
    
    def get_recovery_status(self) -> Dict[str, Any]:
        """Get recovery manager status"""
        current_time = time.time()
        
        # Calculate recovery statistics
        recent_operations = [
            op for op in self.recovery_history
            if (datetime.now() - op.started_at).total_seconds() < 3600  # Last hour
        ]
        
        successful_recoveries = len([op for op in recent_operations if op.result == RecoveryResult.SUCCESS])
        failed_recoveries = len([op for op in recent_operations if op.result == RecoveryResult.FAILED])
        
        return {
            "total_recovery_operations": len(self.recovery_history),
            "recent_operations_count": len(recent_operations),
            "recent_successful_recoveries": successful_recoveries,
            "recent_failed_recoveries": failed_recoveries,
            "success_rate": successful_recoveries / max(len(recent_operations), 1),
            "active_cooldowns": {
                problem_type: self.recovery_cooldown_seconds - (current_time - last_time)
                for problem_type, last_time in self.last_recovery_time.items()
                if current_time - last_time < self.recovery_cooldown_seconds
            },
            "recovery_attempts_by_type": {
                problem_type: len(attempts)
                for problem_type, attempts in self.recovery_attempts.items()
            },
            "configuration": {
                "max_recovery_attempts": self.max_recovery_attempts,
                "recovery_cooldown_seconds": self.recovery_cooldown_seconds,
                "progressive_backoff": self.progressive_backoff
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def get_recovery_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent recovery history"""
        recent_history = self.recovery_history[-limit:] if limit > 0 else self.recovery_history
        
        return [
            {
                "name": op.name,
                "target": op.target,
                "result": op.result.value,
                "started_at": op.started_at.isoformat(),
                "completed_at": op.completed_at.isoformat() if op.completed_at else None,
                "duration_seconds": (op.completed_at - op.started_at).total_seconds() if op.completed_at else None,
                "error_message": op.error_message,
                "recovery_actions": op.recovery_actions
            }
            for op in reversed(recent_history)
        ]
    
    def force_recovery(self, problem_type: str) -> bool:
        """Force recovery for a specific problem type (bypass cooldowns)"""
        print(f"🚨 Forcing recovery for: {problem_type}")
        
        # Temporarily clear cooldown
        if problem_type in self.last_recovery_time:
            del self.last_recovery_time[problem_type]
        
        # Create dummy metric for recovery
        from .health_monitor import HealthMetric, HealthStatus
        dummy_metric = HealthMetric(
            name=problem_type,
            status=HealthStatus.CRITICAL,
            value=True,
            message="Forced recovery",
            last_updated=datetime.now()
        )
        
        return self.attempt_recovery(problem_type, dummy_metric)
    
    def reset_recovery_state(self):
        """Reset recovery manager state"""
        with self.recovery_lock:
            self.recovery_attempts.clear()
            self.last_recovery_time.clear()
            self.recovery_history.clear()
            print("🔧 Recovery manager state reset")
