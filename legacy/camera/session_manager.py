"""
Session Manager - Enhanced Session Management and Authentication

Handles secure session management with automatic cleanup, validation,
and recovery mechanisms to prevent 401 authentication errors.
"""

import time
import threading
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Set, List
from dataclasses import dataclass

from src.config import AppConfig


@dataclass
class SessionData:
    """Session data structure"""
    user_id: str
    created: datetime
    expires: datetime
    last_access: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    access_count: int = 0
    is_active: bool = True


class SessionManager:
    """
    Enhanced session management with automatic cleanup and recovery
    
    Provides:
    - Secure session token generation
    - Automatic session expiration and cleanup
    - Session validation and recovery
    - Concurrent session protection
    - Session health monitoring
    - Authentication failure prevention
    """
    
    def __init__(self, config: AppConfig):
        self.config = config
        
        # Session storage
        self.sessions: Dict[str, SessionData] = {}
        self.session_lock = threading.RLock()
        
        # Configuration
        self.session_expire_hours = 24
        self.max_sessions_per_user = 5
        self.cleanup_interval = 300  # 5 minutes
        self.session_timeout_minutes = 60  # Auto-logout after inactivity
        
        # Cleanup management
        self.cleanup_thread: Optional[threading.Thread] = None
        self.is_running = False
        
        # Statistics
        self.stats = {
            "total_sessions_created": 0,
            "total_sessions_expired": 0,
            "total_sessions_cleaned": 0,
            "active_sessions": 0,
            "validation_failures": 0,
            "cleanup_runs": 0
        }
        
        # Suspicious activity tracking
        self.failed_attempts: Dict[str, List[float]] = {}
        self.blocked_ips: Set[str] = set()
        self.max_failed_attempts = 5
        self.block_duration = 300  # 5 minutes
        
        print("🔐 SessionManager initialized")
    
    def start_cleanup_service(self):
        """Start automatic session cleanup service"""
        if self.is_running:
            return
        
        self.is_running = True
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        print("🧹 Session cleanup service started")
    
    def stop_cleanup_service(self):
        """Stop automatic session cleanup service"""
        self.is_running = False
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5.0)
        print("🧹 Session cleanup service stopped")
    
    def _cleanup_loop(self):
        """Main cleanup loop"""
        while self.is_running:
            try:
                self._cleanup_expired_sessions()
                self._cleanup_blocked_ips()
                self._cleanup_failed_attempts()
                time.sleep(self.cleanup_interval)
            except Exception as e:
                print(f"❌ Session cleanup error: {e}")
                time.sleep(60)  # Longer sleep on error
    
    def generate_session_token(self) -> str:
        """Generate a cryptographically secure session token"""
        return secrets.token_urlsafe(32)
    
    def create_session(self, user_id: str = "web_user", ip_address: Optional[str] = None, 
                      user_agent: Optional[str] = None) -> Optional[str]:
        """
        Create a new session with security checks
        
        Args:
            user_id: User identifier
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            str: Session token if successful, None if blocked
        """
        # Check if IP is blocked
        if ip_address and ip_address in self.blocked_ips:
            print(f"🚫 Blocked IP attempted login: {ip_address}")
            return None
        
        with self.session_lock:
            # Cleanup expired sessions for this user
            self._cleanup_user_sessions(user_id)
            
            # Check session limits
            user_sessions = [s for s in self.sessions.values() if s.user_id == user_id and s.is_active]
            if len(user_sessions) >= self.max_sessions_per_user:
                # Remove oldest session
                oldest_session = min(user_sessions, key=lambda x: x.last_access)
                self._remove_session_by_data(oldest_session)
                print(f"🔄 Removed oldest session for user: {user_id}")
            
            # Create new session
            token = self.generate_session_token()
            expiry = datetime.now() + timedelta(hours=self.session_expire_hours)
            
            session_data = SessionData(
                user_id=user_id,
                created=datetime.now(),
                expires=expiry,
                last_access=datetime.now(),
                ip_address=ip_address,
                user_agent=user_agent,
                access_count=1,
                is_active=True
            )
            
            self.sessions[token] = session_data
            self.stats["total_sessions_created"] += 1
            self.stats["active_sessions"] = len([s for s in self.sessions.values() if s.is_active])
            
            print(f"✅ Session created for user: {user_id} (token: {token[:8]}...)")
            return token
    
    def validate_session(self, token: str, ip_address: Optional[str] = None) -> Optional[SessionData]:
        """
        Validate session token with security checks
        
        Args:
            token: Session token
            ip_address: Client IP address for validation
            
        Returns:
            SessionData: Session data if valid, None otherwise
        """
        if not token:
            return None
        
        with self.session_lock:
            session_data = self.sessions.get(token)
            
            if not session_data:
                self.stats["validation_failures"] += 1
                return None
            
            # Check if session is active
            if not session_data.is_active:
                self._remove_session(token)
                self.stats["validation_failures"] += 1
                return None
            
            # Check expiration
            now = datetime.now()
            if now > session_data.expires:
                self._remove_session(token)
                self.stats["validation_failures"] += 1
                self.stats["total_sessions_expired"] += 1
                return None
            
            # Check session timeout (inactivity)
            time_since_access = now - session_data.last_access
            if time_since_access > timedelta(minutes=self.session_timeout_minutes):
                self._remove_session(token)
                self.stats["validation_failures"] += 1
                self.stats["total_sessions_expired"] += 1
                print(f"⏰ Session expired due to inactivity: {token[:8]}...")
                return None
            
            # IP validation (optional but recommended)
            if ip_address and session_data.ip_address:
                if ip_address != session_data.ip_address:
                    print(f"⚠️ IP address mismatch for session: {token[:8]}...")
                    # Don't immediately invalidate - could be legitimate IP change
                    # But log for security monitoring
            
            # Update last access
            session_data.last_access = now
            session_data.access_count += 1
            
            return session_data
    
    def invalidate_session(self, token: str) -> bool:
        """
        Invalidate a specific session
        
        Args:
            token: Session token to invalidate
            
        Returns:
            bool: True if session was invalidated
        """
        with self.session_lock:
            if token in self.sessions:
                self._remove_session(token)
                print(f"🚫 Session invalidated: {token[:8]}...")
                return True
            return False
    
    def invalidate_user_sessions(self, user_id: str) -> int:
        """
        Invalidate all sessions for a specific user
        
        Args:
            user_id: User identifier
            
        Returns:
            int: Number of sessions invalidated
        """
        count = 0
        with self.session_lock:
            tokens_to_remove = [
                token for token, session in self.sessions.items()
                if session.user_id == user_id
            ]
            
            for token in tokens_to_remove:
                self._remove_session(token)
                count += 1
        
        print(f"🚫 Invalidated {count} sessions for user: {user_id}")
        return count
    
    def extend_session(self, token: str, hours: Optional[int] = None) -> bool:
        """
        Extend session expiration time
        
        Args:
            token: Session token
            hours: Hours to extend (default: session_expire_hours)
            
        Returns:
            bool: True if session was extended
        """
        if not hours:
            hours = self.session_expire_hours
        
        with self.session_lock:
            session_data = self.sessions.get(token)
            if session_data and session_data.is_active:
                session_data.expires = datetime.now() + timedelta(hours=hours)
                print(f"⏰ Session extended: {token[:8]}... (+{hours}h)")
                return True
            return False
    
    def record_failed_attempt(self, ip_address: str):
        """
        Record a failed authentication attempt
        
        Args:
            ip_address: IP address of failed attempt
        """
        if not ip_address:
            return
        
        current_time = time.time()
        
        # Initialize or clean old attempts
        if ip_address not in self.failed_attempts:
            self.failed_attempts[ip_address] = []
        
        # Remove attempts older than block duration
        self.failed_attempts[ip_address] = [
            attempt_time for attempt_time in self.failed_attempts[ip_address]
            if current_time - attempt_time < self.block_duration
        ]
        
        # Add new attempt
        self.failed_attempts[ip_address].append(current_time)
        
        # Check if should block
        if len(self.failed_attempts[ip_address]) >= self.max_failed_attempts:
            self.blocked_ips.add(ip_address)
            print(f"🚫 IP blocked due to failed attempts: {ip_address}")
    
    def is_ip_blocked(self, ip_address: str) -> bool:
        """Check if an IP address is blocked"""
        return ip_address in self.blocked_ips
    
    def unblock_ip(self, ip_address: str) -> bool:
        """Manually unblock an IP address"""
        if ip_address in self.blocked_ips:
            self.blocked_ips.remove(ip_address)
            self.failed_attempts.pop(ip_address, None)
            print(f"✅ IP unblocked: {ip_address}")
            return True
        return False
    
    def _remove_session(self, token: str):
        """Remove a session (internal method)"""
        if token in self.sessions:
            del self.sessions[token]
            self.stats["active_sessions"] = len([s for s in self.sessions.values() if s.is_active])
    
    def _remove_session_by_data(self, session_data: SessionData):
        """Remove a session by its data (internal method)"""
        token_to_remove = None
        for token, data in self.sessions.items():
            if data is session_data:
                token_to_remove = token
                break
        
        if token_to_remove:
            self._remove_session(token_to_remove)
    
    def _cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        current_time = datetime.now()
        expired_tokens = []
        
        with self.session_lock:
            for token, session_data in self.sessions.items():
                if (current_time > session_data.expires or 
                    current_time - session_data.last_access > timedelta(minutes=self.session_timeout_minutes)):
                    expired_tokens.append(token)
            
            # Remove expired sessions
            for token in expired_tokens:
                self._remove_session(token)
                self.stats["total_sessions_expired"] += 1
                self.stats["total_sessions_cleaned"] += 1
        
        if expired_tokens:
            print(f"🧹 Cleaned up {len(expired_tokens)} expired sessions")
        
        self.stats["cleanup_runs"] += 1
    
    def _cleanup_user_sessions(self, user_id: str):
        """Clean up expired sessions for a specific user"""
        current_time = datetime.now()
        expired_tokens = []
        
        for token, session_data in self.sessions.items():
            if (session_data.user_id == user_id and 
                (current_time > session_data.expires or 
                 current_time - session_data.last_access > timedelta(minutes=self.session_timeout_minutes))):
                expired_tokens.append(token)
        
        # Remove expired sessions
        for token in expired_tokens:
            self._remove_session(token)
    
    def _cleanup_blocked_ips(self):
        """Clean up expired IP blocks"""
        current_time = time.time()
        ips_to_unblock = []
        
        for ip in list(self.blocked_ips):
            # Check if any recent failed attempts
            if ip in self.failed_attempts:
                recent_attempts = [
                    attempt for attempt in self.failed_attempts[ip]
                    if current_time - attempt < self.block_duration
                ]
                if not recent_attempts:
                    ips_to_unblock.append(ip)
            else:
                ips_to_unblock.append(ip)
        
        # Unblock expired IPs
        for ip in ips_to_unblock:
            self.blocked_ips.discard(ip)
            self.failed_attempts.pop(ip, None)
        
        if ips_to_unblock:
            print(f"🧹 Unblocked {len(ips_to_unblock)} expired IP blocks")
    
    def _cleanup_failed_attempts(self):
        """Clean up old failed attempt records"""
        current_time = time.time()
        ips_to_clean = []
        
        for ip, attempts in self.failed_attempts.items():
            # Keep only recent attempts
            recent_attempts = [
                attempt for attempt in attempts
                if current_time - attempt < self.block_duration
            ]
            
            if recent_attempts:
                self.failed_attempts[ip] = recent_attempts
            else:
                ips_to_clean.append(ip)
        
        # Remove IPs with no recent attempts
        for ip in ips_to_clean:
            del self.failed_attempts[ip]
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get session management statistics"""
        with self.session_lock:
            active_sessions = len([s for s in self.sessions.values() if s.is_active])
            
            # Calculate session ages
            now = datetime.now()
            session_ages = [
                (now - session.created).total_seconds() / 3600  # Hours
                for session in self.sessions.values()
                if session.is_active
            ]
            
            return {
                **self.stats,
                "active_sessions": active_sessions,
                "blocked_ips": len(self.blocked_ips),
                "failed_attempt_ips": len(self.failed_attempts),
                "average_session_age_hours": sum(session_ages) / len(session_ages) if session_ages else 0,
                "oldest_session_age_hours": max(session_ages) if session_ages else 0,
                "configuration": {
                    "session_expire_hours": self.session_expire_hours,
                    "session_timeout_minutes": self.session_timeout_minutes,
                    "max_sessions_per_user": self.max_sessions_per_user,
                    "cleanup_interval": self.cleanup_interval,
                    "max_failed_attempts": self.max_failed_attempts,
                    "block_duration": self.block_duration
                }
            }
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get list of active sessions (for monitoring)"""
        with self.session_lock:
            sessions = []
            for token, session_data in self.sessions.items():
                if session_data.is_active:
                    sessions.append({
                        "token_prefix": token[:8] + "...",
                        "user_id": session_data.user_id,
                        "created": session_data.created.isoformat(),
                        "last_access": session_data.last_access.isoformat(),
                        "access_count": session_data.access_count,
                        "ip_address": session_data.ip_address,
                        "expires": session_data.expires.isoformat()
                    })
            return sessions
    
    def force_cleanup(self) -> Dict[str, int]:
        """Force immediate cleanup of all expired resources"""
        print("🧹 Forcing comprehensive session cleanup...")
        
        with self.session_lock:
            initial_sessions = len(self.sessions)
            initial_blocked = len(self.blocked_ips)
            
            self._cleanup_expired_sessions()
            self._cleanup_blocked_ips()
            self._cleanup_failed_attempts()
            
            final_sessions = len(self.sessions)
            final_blocked = len(self.blocked_ips)
            
            result = {
                "sessions_removed": initial_sessions - final_sessions,
                "ips_unblocked": initial_blocked - final_blocked,
                "active_sessions": final_sessions,
                "blocked_ips": final_blocked
            }
            
            print(f"🧹 Cleanup complete: {result}")
            return result
    
    def get_security_status(self) -> Dict[str, Any]:
        """Get security-related status information"""
        with self.session_lock:
            return {
                "blocked_ips": list(self.blocked_ips),
                "failed_attempts_summary": {
                    ip: len(attempts) for ip, attempts in self.failed_attempts.items()
                },
                "security_events": {
                    "total_blocks": len(self.blocked_ips),
                    "total_failed_ips": len(self.failed_attempts),
                    "validation_failures": self.stats["validation_failures"]
                },
                "thresholds": {
                    "max_failed_attempts": self.max_failed_attempts,
                    "block_duration_minutes": self.block_duration / 60,
                    "session_timeout_minutes": self.session_timeout_minutes
                }
            }
