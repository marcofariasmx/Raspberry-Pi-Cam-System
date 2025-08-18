"""
System Resource Monitor
Provides objective system metrics for the camera server.
"""

import time
import psutil
import threading
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SystemSample:
    """System resource sample at a point in time"""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_available_mb: float
    disk_free_gb: float
    load_average: Optional[float]
    temperature_c: Optional[float]


class SystemMonitor:
    """
    Objective system resource monitoring for camera server
    
    Provides measurable, objective metrics without subjective classifications.
    Designed for Raspberry Pi deployment.
    """
    
    def __init__(self, max_samples: int = 60):
        """
        Initialize system monitor
        
        Args:
            max_samples: Maximum number of samples to keep (default: 60 = 1 minute at 1Hz)
        """
        self.max_samples = max_samples
        self.samples = []
        self._lock = threading.RLock()
        
        # Performance counters
        self.start_time = time.time()
        self.total_samples = 0
        
        # System info (static)
        self.system_info = self._get_system_info()
        
        print(f"🖥️  SystemMonitor initialized for {self.system_info['platform']}")
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get static system information"""
        try:
            # Get memory info
            memory = psutil.virtual_memory()
            
            # Get disk info
            disk = psutil.disk_usage('/')
            
            # Get CPU info
            cpu_count = psutil.cpu_count()
            cpu_count_logical = psutil.cpu_count(logical=True)
            
            return {
                "platform": psutil.os.name,
                "boot_time": psutil.boot_time(),
                "cpu_cores_physical": cpu_count,
                "cpu_cores_logical": cpu_count_logical,
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "pid": psutil.os.getpid()
            }
        except Exception as e:
            print(f"⚠️  Could not get full system info: {e}")
            return {"platform": "unknown", "error": str(e)}
    
    def _get_temperature(self) -> Optional[float]:
        """Get CPU temperature (Raspberry Pi specific)"""
        try:
            # Try Raspberry Pi thermal zone
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp_str = f.read().strip()
                return float(temp_str) / 1000.0  # Convert millidegree to degree
        except:
            try:
                # Try psutil sensors (if available)
                sensors = psutil.sensors_temperatures()
                if 'cpu_thermal' in sensors:
                    return sensors['cpu_thermal'][0].current
            except:
                pass
        return None
    
    def _get_load_average(self) -> Optional[float]:
        """Get system load average (1 minute)"""
        try:
            return psutil.os.getloadavg()[0]  # 1-minute load average
        except:
            return None
    
    def sample_now(self) -> SystemSample:
        """Take an immediate system sample"""
        current_time = time.time()
        
        try:
            # CPU usage (averaged over short interval)
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_mb = memory.available / (1024**2)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_free_gb = disk.free / (1024**3)
            
            # Load average
            load_avg = self._get_load_average()
            
            # Temperature
            temperature = self._get_temperature()
            
            sample = SystemSample(
                timestamp=current_time,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_available_mb=memory_available_mb,
                disk_free_gb=disk_free_gb,
                load_average=load_avg,
                temperature_c=temperature
            )
            
            # Store sample
            with self._lock:
                self.samples.append(sample)
                self.total_samples += 1
                
                # Keep only recent samples
                if len(self.samples) > self.max_samples:
                    self.samples.pop(0)
            
            return sample
            
        except Exception as e:
            print(f"❌ Error sampling system metrics: {e}")
            # Return minimal sample
            return SystemSample(
                timestamp=current_time,
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_available_mb=0.0,
                disk_free_gb=0.0,
                load_average=None,
                temperature_c=None
            )
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current system metrics"""
        sample = self.sample_now()
        
        return {
            "timestamp": datetime.fromtimestamp(sample.timestamp).isoformat(),
            "cpu_percent": round(sample.cpu_percent, 1),
            "memory_percent": round(sample.memory_percent, 1),
            "memory_available_mb": round(sample.memory_available_mb, 1),
            "disk_free_gb": round(sample.disk_free_gb, 2),
            "load_average": round(sample.load_average, 2) if sample.load_average else None,
            "temperature_c": round(sample.temperature_c, 1) if sample.temperature_c else None
        }
    
    def get_historical_metrics(self, minutes: int = 5) -> Dict[str, Any]:
        """Get historical metrics for specified time period"""
        current_time = time.time()
        cutoff_time = current_time - (minutes * 60)
        
        with self._lock:
            recent_samples = [s for s in self.samples if s.timestamp >= cutoff_time]
        
        if not recent_samples:
            return {"error": "No historical data available"}
        
        # Calculate averages
        cpu_values = [s.cpu_percent for s in recent_samples]
        memory_values = [s.memory_percent for s in recent_samples]
        temp_values = [s.temperature_c for s in recent_samples if s.temperature_c is not None]
        load_values = [s.load_average for s in recent_samples if s.load_average is not None]
        
        return {
            "time_period_minutes": minutes,
            "sample_count": len(recent_samples),
            "cpu": {
                "average": round(sum(cpu_values) / len(cpu_values), 1),
                "min": round(min(cpu_values), 1),
                "max": round(max(cpu_values), 1)
            },
            "memory": {
                "average": round(sum(memory_values) / len(memory_values), 1),
                "min": round(min(memory_values), 1),
                "max": round(max(memory_values), 1)
            },
            "temperature": {
                "average": round(sum(temp_values) / len(temp_values), 1) if temp_values else None,
                "min": round(min(temp_values), 1) if temp_values else None,
                "max": round(max(temp_values), 1) if temp_values else None
            } if temp_values else None,
            "load_average": {
                "average": round(sum(load_values) / len(load_values), 2) if load_values else None,
                "min": round(min(load_values), 2) if load_values else None,
                "max": round(max(load_values), 2) if load_values else None
            } if load_values else None
        }
    
    def get_performance_status(self) -> Dict[str, Any]:
        """Get objective performance assessment based on measurable thresholds"""
        current = self.get_current_metrics()
        
        # Objective thresholds (no subjective "good/bad")
        cpu_threshold_high = 80.0
        memory_threshold_high = 85.0
        temp_threshold_high = 75.0  # Celsius
        disk_threshold_low = 1.0    # GB
        
        # Calculate status flags
        flags = {
            "cpu_high_utilization": current["cpu_percent"] > cpu_threshold_high,
            "memory_high_utilization": current["memory_percent"] > memory_threshold_high,
            "temperature_high": current["temperature_c"] and current["temperature_c"] > temp_threshold_high,
            "disk_space_low": current["disk_free_gb"] < disk_threshold_low
        }
        
        # Count active flags
        active_flags = sum(flags.values())
        
        return {
            "flags": flags,
            "active_warnings": active_flags,
            "thresholds": {
                "cpu_percent": cpu_threshold_high,
                "memory_percent": memory_threshold_high,
                "temperature_c": temp_threshold_high,
                "disk_free_gb": disk_threshold_low
            },
            "system_info": self.system_info,
            "uptime_hours": round((time.time() - self.start_time) / 3600, 1)
        }
    
    def get_resource_summary(self) -> str:
        """Get human-readable resource summary"""
        current = self.get_current_metrics()
        status = self.get_performance_status()
        
        temp_str = f", {current['temperature_c']}°C" if current['temperature_c'] else ""
        warnings = f" ({status['active_warnings']} warnings)" if status['active_warnings'] > 0 else ""
        
        return (
            f"CPU: {current['cpu_percent']}% | "
            f"Memory: {current['memory_percent']}% | "
            f"Disk: {current['disk_free_gb']}GB{temp_str}{warnings}"
        )
    
    def clear_history(self):
        """Clear historical samples"""
        with self._lock:
            self.samples.clear()
        print("🧹 System monitor history cleared")