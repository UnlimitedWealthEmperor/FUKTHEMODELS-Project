"""
Authentication Service for FuckTheModels
Simple password-based authentication with secure storage

Features:
- First-time password setup (forced)
- Session token authentication
- Password hashing with bcrypt fallback to SHA256
"""

import os
import json
import hashlib
import secrets
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict

# Try to use bcrypt, fallback to SHA256 if not available
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False


class AuthService:
    """
    Simple authentication service with password protection
    """
    
    def __init__(self, config_dir: Path = None):
        """Initialize auth service"""
        self.config_dir = config_dir or Path(__file__).parent.parent / "config"
        self.config_dir.mkdir(exist_ok=True)
        self.auth_file = self.config_dir / ".auth"
        self.sessions: Dict[str, datetime] = {}  # token -> expiry
        self.session_duration = timedelta(hours=24)  # Sessions last 24 hours
        
    @property
    def is_setup(self) -> bool:
        """Check if password has been set up"""
        return self.auth_file.exists()
    
    def _hash_password(self, password: str) -> str:
        """Hash a password securely"""
        if BCRYPT_AVAILABLE:
            return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        else:
            # Fallback to SHA256 with salt
            salt = secrets.token_hex(16)
            hash_val = hashlib.sha256((salt + password).encode()).hexdigest()
            return f"sha256:{salt}:{hash_val}"
    
    def _verify_password(self, password: str, stored_hash: str) -> bool:
        """Verify password against stored hash"""
        if stored_hash.startswith("sha256:"):
            # SHA256 fallback format
            parts = stored_hash.split(":")
            if len(parts) != 3:
                return False
            salt = parts[1]
            expected_hash = parts[2]
            actual_hash = hashlib.sha256((salt + password).encode()).hexdigest()
            return secrets.compare_digest(actual_hash, expected_hash)
        elif BCRYPT_AVAILABLE:
            try:
                return bcrypt.checkpw(password.encode(), stored_hash.encode())
            except:
                return False
        return False
    
    def setup_password(self, password: str) -> bool:
        """
        Set up the initial password (only works if not already set up)
        
        Returns True if successful, False if already set up
        """
        if self.is_setup:
            return False
        
        auth_data = {
            "password_hash": self._hash_password(password),
            "created_at": datetime.now().isoformat(),
            "version": 1
        }
        
        with open(self.auth_file, 'w') as f:
            json.dump(auth_data, f)
        
        # Set restrictive permissions (owner read/write only)
        try:
            os.chmod(self.auth_file, 0o600)
        except:
            pass  # Windows doesn't support chmod the same way
        
        return True
    
    def verify_password(self, password: str) -> bool:
        """Verify a password"""
        if not self.is_setup:
            return False
        
        try:
            with open(self.auth_file, 'r') as f:
                auth_data = json.load(f)
            return self._verify_password(password, auth_data["password_hash"])
        except:
            return False
    
    def create_session(self, password: str) -> Optional[str]:
        """
        Create a session token if password is valid
        
        Returns session token or None if invalid
        """
        if not self.verify_password(password):
            return None
        
        # Generate secure token
        token = secrets.token_urlsafe(32)
        self.sessions[token] = datetime.now() + self.session_duration
        
        # Clean up expired sessions
        self._cleanup_sessions()
        
        return token
    
    def verify_session(self, token: str) -> bool:
        """Verify a session token is valid"""
        if not token or token not in self.sessions:
            return False
        
        expiry = self.sessions[token]
        if datetime.now() > expiry:
            del self.sessions[token]
            return False
        
        return True
    
    def invalidate_session(self, token: str):
        """Invalidate a session (logout)"""
        if token in self.sessions:
            del self.sessions[token]
    
    def _cleanup_sessions(self):
        """Remove expired sessions"""
        now = datetime.now()
        expired = [t for t, exp in self.sessions.items() if now > exp]
        for token in expired:
            del self.sessions[token]


# Singleton instance
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get the singleton auth service instance"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
