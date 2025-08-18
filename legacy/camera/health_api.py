"""
Health API - Health Monitoring and Recovery API Endpoints

Provides comprehensive health monitoring, diagnostics, and recovery
endpoints for system health management without a dashboard UI.
"""

from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import HTTPException
from src.config import AppConfig


class HealthAPI:
    """
    Health monitoring and recovery API endpoints
    
    Provides:
    - System health status endpoints
    - Detailed diagnostics endpoints
    - Recovery management endpoints
    - Performance monitoring endpoints
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        
        # Component references (set by main application)
        self.health_monitor = None
        self.session_manager = None
        self.recovery_manager = None
        self.streaming_validator = None
        self.camera_manager = None
        
        print("🔗 HealthAPI initialized")
    
    def set_component_references(self, health_monitor=None, session_manager=None, 
                               recovery_manager=None, streaming_validator=None, camera_manager=None):
        """Set references to system components"""
        if health_monitor:
            self.health_monitor = health_monitor
        if session_manager:
            self.session_manager = session_manager
        if recovery_manager:
            self.recovery_manager = recovery_manager
        if streaming_validator:
            self.streaming_validator = streaming_validator
        if camera_manager:
            self.camera_manager = camera_manager
    
    # Main Health Endpoints
    
    def get_health_detailed(self) -> Dict[str, Any]:
        """Get comprehensive system health status"""
        try:
            result = {
                "overall_status": "unknown",
                "timestamp": datetime.now().isoformat(),
                "components": {},
                "summary": {}
            }
            
            # Health Monitor Status
            if self.health_monitor:
                health_status = self.health_monitor.get_health_status()
                result["overall_status"] = health_status.get("overall_status", "unknown")
                result["components"]["health_monitor"] = health_status
            else:
                result["components"]["health_monitor"] = {"error": "Health monitor not available"}
            
            # Camera Health
            if self.camera_manager:
                camera_status = self.camera_manager.get_status()
                result["components"]["camera"] = camera_status
            else:
                result["components"]["camera"] = {"error": "Camera manager not available"}
            
            # Session Management Health
            if self.session_manager:
                session_stats = self.session_manager.get_session_stats()
                result["components"]["sessions"] = session_stats
            else:
                result["components"]["sessions"] = {"error": "Session manager not available"}
            
            # Streaming Health
            if self.streaming_validator:
                streaming_health = self.streaming_validator.validate_stream_health()
                result["components"]["streaming"] = streaming_health
            else:
                result["components"]["streaming"] = {"error": "Streaming validator not available"}
            
            # Recovery Manager Status
            if self.recovery_manager:
                recovery_status = self.recovery_manager.get_recovery_status()
                result["components"]["recovery"] = recovery_status
            else:
                result["components"]["recovery"] = {"error": "Recovery manager not available"}
            
            # Generate summary
            result["summary"] = self._generate_health_summary(result["components"])
            
            return result
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")
    
    def get_health_camera(self) -> Dict[str, Any]:
        """Get camera-specific health information"""
        try:
            if not self.camera_manager:
                raise HTTPException(status_code=503, detail="Camera manager not available")
            
            # Basic camera status
            camera_status = self.camera_manager.get_status()
            
            # Hardware detection info
            hardware_info = self.camera_manager.get_hardware_info()
            
            # Photo capture stats
            photo_stats = self.camera_manager.get_photo_stats()
            
            # Streaming stats if available
            streaming_stats = {}
            if self.camera_manager.is_streaming:
                streaming_stats = self.camera_manager.get_streaming_stats()
            
            # Health monitor camera metrics
            camera_health = {}
            if self.health_monitor:
                health_status = self.health_monitor.get_health_status()
                camera_metrics = health_status.get("metrics", {})
                camera_health = {
                    "camera_availability": camera_metrics.get("camera_availability", {}),
                    "hardware_timeout": camera_metrics.get("hardware_timeout", {}),
                    "frame_generation": camera_metrics.get("frame_generation", {})
                }
            
            return {
                "status": camera_status,
                "hardware": hardware_info,
                "photo_stats": photo_stats,
                "streaming_stats": streaming_stats,
                "health_metrics": camera_health,
                "timestamp": datetime.now().isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Camera health check failed: {str(e)}")
    
    def get_health_streaming(self) -> Dict[str, Any]:
        """Get streaming-specific health and performance information"""
        try:
            result = {
                "timestamp": datetime.now().isoformat()
            }
            
            # Streaming validator health
            if self.streaming_validator:
                stream_health = self.streaming_validator.validate_stream_health()
                frozen_frames = self.streaming_validator.detect_frozen_frames()
                performance_trends = self.streaming_validator.get_performance_trends()
                validator_status = self.streaming_validator.get_validator_status()
                
                result.update({
                    "stream_health": stream_health,
                    "frozen_frame_detection": frozen_frames,
                    "performance_trends": performance_trends,
                    "validator_status": validator_status
                })
            else:
                result["error"] = "Streaming validator not available"
            
            # Camera manager streaming info
            if self.camera_manager and self.camera_manager.is_streaming:
                streaming_stats = self.camera_manager.get_streaming_stats()
                result["camera_streaming_stats"] = streaming_stats
            
            return result
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Streaming health check failed: {str(e)}")
    
    def get_health_sessions(self) -> Dict[str, Any]:
        """Get session management health information"""
        try:
            if not self.session_manager:
                raise HTTPException(status_code=503, detail="Session manager not available")
            
            # Session statistics
            session_stats = self.session_manager.get_session_stats()
            
            # Active sessions (limited info for security)
            active_sessions = self.session_manager.get_active_sessions()
            
            # Security status
            security_status = self.session_manager.get_security_status()
            
            return {
                "session_stats": session_stats,
                "active_sessions_count": len(active_sessions),
                "security_status": security_status,
                "timestamp": datetime.now().isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Session health check failed: {str(e)}")
    
    def get_health_recovery(self) -> Dict[str, Any]:
        """Get recovery system status and history"""
        try:
            if not self.recovery_manager:
                raise HTTPException(status_code=503, detail="Recovery manager not available")
            
            # Recovery status
            recovery_status = self.recovery_manager.get_recovery_status()
            
            # Recent recovery history
            recovery_history = self.recovery_manager.get_recovery_history(limit=20)
            
            return {
                "recovery_status": recovery_status,
                "recent_recovery_history": recovery_history,
                "timestamp": datetime.now().isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Recovery health check failed: {str(e)}")
    
    # Diagnostic Endpoints
    
    def get_diagnostics_comprehensive(self) -> Dict[str, Any]:
        """Get comprehensive system diagnostics"""
        try:
            diagnostics = {
                "timestamp": datetime.now().isoformat(),
                "system_info": self._get_system_info(),
                "components": {}
            }
            
            # Health monitor diagnostics
            if self.health_monitor:
                diagnostics["components"]["health_monitor"] = self.health_monitor.get_detailed_diagnostics()
            
            # Streaming validator diagnostics
            if self.streaming_validator:
                quality_validation = self.streaming_validator.validate_stream_quality()
                diagnostics["components"]["streaming_validator"] = quality_validation
            
            # Camera diagnostics
            if self.camera_manager:
                diagnostics["components"]["camera"] = {
                    "status": self.camera_manager.get_status(),
                    "hardware_info": self.camera_manager.get_hardware_info(),
                    "network_status": self.camera_manager.get_network_status()
                }
            
            return diagnostics
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Comprehensive diagnostics failed: {str(e)}")
    
    def get_diagnostics_performance(self) -> Dict[str, Any]:
        """Get performance-specific diagnostics"""
        try:
            performance = {
                "timestamp": datetime.now().isoformat()
            }
            
            # Streaming performance
            if self.streaming_validator:
                trends = self.streaming_validator.get_performance_trends()
                performance["streaming_trends"] = trends
            
            # Camera performance
            if self.camera_manager and self.camera_manager.is_streaming:
                streaming_stats = self.camera_manager.get_streaming_stats()
                performance["camera_streaming"] = streaming_stats
            
            # Session performance
            if self.session_manager:
                session_stats = self.session_manager.get_session_stats()
                performance["session_management"] = session_stats
            
            return performance
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Performance diagnostics failed: {str(e)}")
    
    # Recovery Control Endpoints
    
    def force_health_check(self) -> Dict[str, Any]:
        """Force an immediate comprehensive health check"""
        try:
            if not self.health_monitor:
                raise HTTPException(status_code=503, detail="Health monitor not available")
            
            health_status = self.health_monitor.force_health_check()
            
            return {
                "message": "Forced health check completed",
                "health_status": health_status,
                "timestamp": datetime.now().isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Forced health check failed: {str(e)}")
    
    def trigger_recovery(self, problem_type: str) -> Dict[str, Any]:
        """Trigger recovery for a specific problem type"""
        try:
            if not self.recovery_manager:
                raise HTTPException(status_code=503, detail="Recovery manager not available")
            
            # Validate problem type
            valid_types = [
                "camera_availability", "hardware_timeout", "frame_generation",
                "stream_quality", "session_management", "streaming_performance"
            ]
            
            if problem_type not in valid_types:
                raise HTTPException(status_code=400, detail=f"Invalid problem type. Valid types: {valid_types}")
            
            success = self.recovery_manager.force_recovery(problem_type)
            
            return {
                "message": f"Recovery {'successful' if success else 'failed'} for {problem_type}",
                "problem_type": problem_type,
                "success": success,
                "timestamp": datetime.now().isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Recovery trigger failed: {str(e)}")
    
    def reset_system_state(self) -> Dict[str, Any]:
        """Reset all system monitoring and recovery state"""
        try:
            reset_results = {}
            
            # Reset health monitor
            if self.health_monitor:
                self.health_monitor.reset_metrics()
                reset_results["health_monitor"] = "reset"
            
            # Reset streaming validator
            if self.streaming_validator:
                self.streaming_validator.reset_validation_state()
                reset_results["streaming_validator"] = "reset"
            
            # Reset recovery manager
            if self.recovery_manager:
                self.recovery_manager.reset_recovery_state()
                reset_results["recovery_manager"] = "reset"
            
            # Force session cleanup
            if self.session_manager:
                cleanup_result = self.session_manager.force_cleanup()
                reset_results["session_manager"] = cleanup_result
            
            return {
                "message": "System state reset completed",
                "reset_results": reset_results,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"System state reset failed: {str(e)}")
    
    # Utility Methods
    
    def _generate_health_summary(self, components: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a summary of component health"""
        summary = {
            "healthy_components": 0,
            "warning_components": 0,
            "critical_components": 0,
            "offline_components": 0,
            "total_components": 0,
            "overall_assessment": "unknown"
        }
        
        for component_name, component_data in components.items():
            if "error" in component_data:
                summary["offline_components"] += 1
            else:
                # Try to extract status from different component formats
                status = "unknown"
                if "overall_status" in component_data:
                    status = component_data["overall_status"]
                elif "health_status" in component_data:
                    status = component_data["health_status"]
                elif "status" in component_data:
                    if isinstance(component_data["status"], dict) and "available" in component_data["status"]:
                        status = "healthy" if component_data["status"]["available"] else "critical"
                
                if status in ["healthy", "success"]:
                    summary["healthy_components"] += 1
                elif status in ["warning", "degraded"]:
                    summary["warning_components"] += 1
                elif status in ["critical", "error", "failed"]:
                    summary["critical_components"] += 1
                else:
                    summary["offline_components"] += 1
            
            summary["total_components"] += 1
        
        # Determine overall assessment
        if summary["critical_components"] > 0:
            summary["overall_assessment"] = "critical"
        elif summary["warning_components"] > 0:
            summary["overall_assessment"] = "warning"
        elif summary["healthy_components"] == summary["total_components"]:
            summary["overall_assessment"] = "healthy"
        else:
            summary["overall_assessment"] = "mixed"
        
        return summary
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get basic system information"""
        return {
            "config": {
                "low_resource_mode": self.config.low_resource_mode,
                "adaptive_streaming": self.config.adaptive_streaming,
                "adaptive_quality": self.config.adaptive_quality,
                "photos_dir": self.config.photos_dir,
                "max_photos": self.config.max_photos
            },
            "component_availability": {
                "health_monitor": self.health_monitor is not None,
                "session_manager": self.session_manager is not None,
                "recovery_manager": self.recovery_manager is not None,
                "streaming_validator": self.streaming_validator is not None,
                "camera_manager": self.camera_manager is not None
            }
        }
    
    # Quality and Validation Endpoints
    
    def validate_stream_quality(self) -> Dict[str, Any]:
        """Validate current stream quality with recommendations"""
        try:
            if not self.streaming_validator:
                raise HTTPException(status_code=503, detail="Streaming validator not available")
            
            quality_report = self.streaming_validator.validate_stream_quality()
            
            return {
                "quality_report": quality_report,
                "timestamp": datetime.now().isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Stream quality validation failed: {str(e)}")
    
    def detect_frozen_frames(self) -> Dict[str, Any]:
        """Check for frozen or stale frames"""
        try:
            if not self.streaming_validator:
                raise HTTPException(status_code=503, detail="Streaming validator not available")
            
            frozen_status = self.streaming_validator.detect_frozen_frames()
            
            return {
                "frozen_frame_status": frozen_status,
                "timestamp": datetime.now().isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Frozen frame detection failed: {str(e)}")
