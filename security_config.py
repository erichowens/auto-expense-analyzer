#!/usr/bin/env python3
"""
Security Configuration and Middleware
Implements comprehensive security measures for PCI compliance and data protection.
"""

import os
import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Optional, Any
from flask import request, session, jsonify, abort
from cryptography.fernet import Fernet
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
import re

# Security Configuration
SECURITY_CONFIG = {
    # Encryption
    'ENCRYPTION_KEY': os.getenv('ENCRYPTION_KEY', Fernet.generate_key()),
    'JWT_SECRET_KEY': os.getenv('JWT_SECRET_KEY', secrets.token_hex(32)),
    'JWT_ALGORITHM': 'HS256',
    'JWT_EXPIRATION_HOURS': 24,
    
    # Session Security
    'SESSION_COOKIE_SECURE': True,  # HTTPS only
    'SESSION_COOKIE_HTTPONLY': True,  # No JS access
    'SESSION_COOKIE_SAMESITE': 'Strict',
    'SESSION_TIMEOUT_MINUTES': 30,
    'MAX_SESSION_LIFETIME_HOURS': 8,
    
    # Rate Limiting
    'MAX_LOGIN_ATTEMPTS': 5,
    'LOCKOUT_DURATION_MINUTES': 30,
    'API_RATE_LIMIT': '100 per hour',
    
    # Password Policy
    'MIN_PASSWORD_LENGTH': 12,
    'REQUIRE_UPPERCASE': True,
    'REQUIRE_LOWERCASE': True,
    'REQUIRE_NUMBERS': True,
    'REQUIRE_SPECIAL_CHARS': True,
    'PASSWORD_HISTORY_COUNT': 5,
    
    # Data Retention
    'MAX_LOG_RETENTION_DAYS': 90,
    'MAX_TRANSACTION_RETENTION_DAYS': 2555,  # 7 years for tax purposes
    
    # Security Headers
    'SECURITY_HEADERS': {
        'X-Frame-Options': 'DENY',
        'X-Content-Type-Options': 'nosniff',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.plaid.com; style-src 'self' 'unsafe-inline';",
        'Referrer-Policy': 'strict-origin-when-cross-origin'
    }
}

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('security_audit.log'),
        logging.StreamHandler()
    ]
)
security_logger = logging.getLogger('security')


class SecurityManager:
    """Manages application security features."""
    
    def __init__(self):
        self.cipher_suite = Fernet(SECURITY_CONFIG['ENCRYPTION_KEY'])
        self.failed_attempts = {}  # Track failed login attempts
        
    def encrypt_sensitive_data(self, data: str) -> str:
        """Encrypt sensitive data before storage."""
        if not data:
            return data
        return self.cipher_suite.encrypt(data.encode()).decode()
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data."""
        if not encrypted_data:
            return encrypted_data
        try:
            return self.cipher_suite.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            security_logger.error(f"Decryption failed: {e}")
            return None
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt."""
        return generate_password_hash(password, method='pbkdf2:sha256')
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash."""
        return check_password_hash(password_hash, password)
    
    def validate_password_strength(self, password: str) -> tuple[bool, str]:
        """Validate password meets security requirements."""
        if len(password) < SECURITY_CONFIG['MIN_PASSWORD_LENGTH']:
            return False, f"Password must be at least {SECURITY_CONFIG['MIN_PASSWORD_LENGTH']} characters"
        
        if SECURITY_CONFIG['REQUIRE_UPPERCASE'] and not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"
        
        if SECURITY_CONFIG['REQUIRE_LOWERCASE'] and not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"
        
        if SECURITY_CONFIG['REQUIRE_NUMBERS'] and not re.search(r'\d', password):
            return False, "Password must contain at least one number"
        
        if SECURITY_CONFIG['REQUIRE_SPECIAL_CHARS'] and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Password must contain at least one special character"
        
        return True, "Password meets requirements"
    
    def generate_session_token(self, user_id: str) -> str:
        """Generate secure session token."""
        payload = {
            'user_id': user_id,
            'exp': datetime.utcnow() + timedelta(hours=SECURITY_CONFIG['JWT_EXPIRATION_HOURS']),
            'iat': datetime.utcnow(),
            'session_id': secrets.token_hex(16)
        }
        return jwt.encode(payload, SECURITY_CONFIG['JWT_SECRET_KEY'], algorithm=SECURITY_CONFIG['JWT_ALGORITHM'])
    
    def verify_session_token(self, token: str) -> Optional[Dict]:
        """Verify and decode session token."""
        try:
            payload = jwt.decode(token, SECURITY_CONFIG['JWT_SECRET_KEY'], algorithms=[SECURITY_CONFIG['JWT_ALGORITHM']])
            return payload
        except jwt.ExpiredSignatureError:
            security_logger.warning("Expired token attempted")
            return None
        except jwt.InvalidTokenError as e:
            security_logger.warning(f"Invalid token: {e}")
            return None
    
    def check_rate_limit(self, identifier: str) -> bool:
        """Check if user has exceeded rate limits."""
        current_time = datetime.utcnow()
        
        if identifier not in self.failed_attempts:
            self.failed_attempts[identifier] = []
        
        # Clean old attempts
        self.failed_attempts[identifier] = [
            attempt for attempt in self.failed_attempts[identifier]
            if attempt > current_time - timedelta(minutes=SECURITY_CONFIG['LOCKOUT_DURATION_MINUTES'])
        ]
        
        # Check if locked out
        if len(self.failed_attempts[identifier]) >= SECURITY_CONFIG['MAX_LOGIN_ATTEMPTS']:
            return False
        
        return True
    
    def record_failed_attempt(self, identifier: str):
        """Record a failed login attempt."""
        if identifier not in self.failed_attempts:
            self.failed_attempts[identifier] = []
        
        self.failed_attempts[identifier].append(datetime.utcnow())
        
        security_logger.warning(f"Failed login attempt for: {identifier}")
    
    def sanitize_input(self, user_input: str) -> str:
        """Sanitize user input to prevent XSS and injection attacks."""
        if not user_input:
            return user_input
        
        # Remove any HTML tags
        clean = re.sub('<.*?>', '', user_input)
        
        # Remove any potential SQL injection patterns
        sql_patterns = [
            r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|CREATE|ALTER)\b)',
            r'(--|\';|\")',
            r'(\bOR\b.*=.*)',
            r'(\bAND\b.*=.*)'
        ]
        
        for pattern in sql_patterns:
            clean = re.sub(pattern, '', clean, flags=re.IGNORECASE)
        
        return clean.strip()
    
    def mask_sensitive_data(self, data: str, mask_type: str = 'card') -> str:
        """Mask sensitive data for display."""
        if not data:
            return data
        
        if mask_type == 'card':
            # Show only last 4 digits of card number
            if len(data) >= 4:
                return '*' * (len(data) - 4) + data[-4:]
        elif mask_type == 'email':
            # Mask email address
            parts = data.split('@')
            if len(parts) == 2:
                name = parts[0]
                if len(name) > 2:
                    masked_name = name[0] + '*' * (len(name) - 2) + name[-1]
                else:
                    masked_name = '*' * len(name)
                return masked_name + '@' + parts[1]
        elif mask_type == 'token':
            # Show only first and last 4 characters
            if len(data) > 8:
                return data[:4] + '...' + data[-4:]
        
        return '*' * len(data)


# Security decorators
security_manager = SecurityManager()


def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = session.get('auth_token') or request.headers.get('Authorization')
        
        if not token:
            security_logger.warning(f"Unauthorized access attempt to {request.path}")
            abort(401)
        
        if token.startswith('Bearer '):
            token = token[7:]
        
        payload = security_manager.verify_session_token(token)
        if not payload:
            security_logger.warning(f"Invalid token used for {request.path}")
            abort(401)
        
        request.user = payload
        return f(*args, **kwargs)
    
    return decorated_function


def apply_security_headers(response):
    """Apply security headers to response."""
    for header, value in SECURITY_CONFIG['SECURITY_HEADERS'].items():
        response.headers[header] = value
    return response


def audit_log(action: str, details: Dict[str, Any] = None):
    """Log security-relevant actions for audit trail."""
    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'action': action,
        'user': session.get('user_id', 'anonymous'),
        'ip_address': request.remote_addr,
        'user_agent': request.user_agent.string,
        'details': details or {}
    }
    
    security_logger.info(f"AUDIT: {json.dumps(log_entry)}")


class DataProtection:
    """Handles data protection and privacy compliance."""
    
    @staticmethod
    def anonymize_pii(data: Dict) -> Dict:
        """Anonymize personally identifiable information."""
        pii_fields = ['ssn', 'tax_id', 'drivers_license', 'passport']
        
        anonymized = data.copy()
        for field in pii_fields:
            if field in anonymized:
                anonymized[field] = hashlib.sha256(str(anonymized[field]).encode()).hexdigest()[:8]
        
        return anonymized
    
    @staticmethod
    def get_data_retention_policy() -> Dict:
        """Get data retention policy."""
        return {
            'transaction_data': f"{SECURITY_CONFIG['MAX_TRANSACTION_RETENTION_DAYS']} days",
            'log_data': f"{SECURITY_CONFIG['MAX_LOG_RETENTION_DAYS']} days",
            'session_data': "Until logout or timeout",
            'cached_data': "24 hours maximum"
        }
    
    @staticmethod
    def export_user_data(user_id: str) -> Dict:
        """Export all user data for GDPR compliance."""
        # This would gather all user data from various sources
        security_logger.info(f"Data export requested for user: {user_id}")
        return {
            'export_date': datetime.utcnow().isoformat(),
            'user_id': user_id,
            'data': {}  # Would include all user data
        }
    
    @staticmethod
    def delete_user_data(user_id: str) -> bool:
        """Delete user data for right to be forgotten."""
        security_logger.warning(f"Data deletion requested for user: {user_id}")
        # This would delete all user data
        return True


class SecurityMonitor:
    """Monitor for security threats and anomalies."""
    
    def __init__(self):
        self.threat_indicators = []
        
    def check_for_threats(self, request_data: Dict) -> tuple[bool, str]:
        """Check for potential security threats."""
        threats = []
        
        # Check for SQL injection attempts
        if self._contains_sql_injection(str(request_data)):
            threats.append("Potential SQL injection detected")
        
        # Check for XSS attempts
        if self._contains_xss(str(request_data)):
            threats.append("Potential XSS attack detected")
        
        # Check for path traversal
        if self._contains_path_traversal(str(request_data)):
            threats.append("Potential path traversal detected")
        
        # Check for unusual patterns
        if self._contains_unusual_patterns(request_data):
            threats.append("Unusual request pattern detected")
        
        if threats:
            security_logger.warning(f"Security threats detected: {', '.join(threats)}")
            return False, ', '.join(threats)
        
        return True, "No threats detected"
    
    def _contains_sql_injection(self, data: str) -> bool:
        """Check for SQL injection patterns."""
        sql_patterns = [
            r'(\bUNION\b.*\bSELECT\b)',
            r'(\bDROP\b.*\bTABLE\b)',
            r'(\bINSERT\b.*\bINTO\b)',
            r'(\bDELETE\b.*\bFROM\b)',
            r'(1\s*=\s*1)',
            r'(\bOR\b.*=)',
            r'(--\s*$)',
            r'(\';)',
            r'(\"|\')\s*\bOR\b'
        ]
        
        for pattern in sql_patterns:
            if re.search(pattern, data, re.IGNORECASE):
                return True
        return False
    
    def _contains_xss(self, data: str) -> bool:
        """Check for XSS patterns."""
        xss_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',
            r'<iframe[^>]*>',
            r'<embed[^>]*>',
            r'<object[^>]*>'
        ]
        
        for pattern in xss_patterns:
            if re.search(pattern, data, re.IGNORECASE):
                return True
        return False
    
    def _contains_path_traversal(self, data: str) -> bool:
        """Check for path traversal attempts."""
        patterns = [r'\.\./', r'\.\.\\', r'%2e%2e%2f', r'%252e%252e%252f']
        return any(pattern in data.lower() for pattern in patterns)
    
    def _contains_unusual_patterns(self, data: Dict) -> bool:
        """Check for unusual request patterns."""
        # Check for extremely long inputs
        for value in str(data):
            if len(str(value)) > 10000:
                return True
        
        # Check for binary data in text fields
        if '\x00' in str(data):
            return True
        
        return False


# Initialize security components
def init_security(app):
    """Initialize security features for Flask app."""
    
    # Set security configuration
    app.config.update(
        SECRET_KEY=SECURITY_CONFIG['JWT_SECRET_KEY'],
        SESSION_COOKIE_SECURE=SECURITY_CONFIG['SESSION_COOKIE_SECURE'],
        SESSION_COOKIE_HTTPONLY=SECURITY_CONFIG['SESSION_COOKIE_HTTPONLY'],
        SESSION_COOKIE_SAMESITE=SECURITY_CONFIG['SESSION_COOKIE_SAMESITE'],
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=SECURITY_CONFIG['SESSION_TIMEOUT_MINUTES'])
    )
    
    # Apply security headers to all responses
    app.after_request(apply_security_headers)
    
    # Log all requests for audit trail
    @app.before_request
    def log_request():
        audit_log('request', {
            'method': request.method,
            'path': request.path,
            'ip': request.remote_addr
        })
    
    security_logger.info("Security features initialized")
    
    return app


if __name__ == '__main__':
    # Security configuration test
    print("Security Configuration Test")
    print("=" * 50)
    
    sm = SecurityManager()
    
    # Test password validation
    test_password = "SecureP@ssw0rd123!"
    valid, message = sm.validate_password_strength(test_password)
    print(f"Password validation: {message}")
    
    # Test encryption
    sensitive_data = "4111-1111-1111-1111"
    encrypted = sm.encrypt_sensitive_data(sensitive_data)
    decrypted = sm.decrypt_sensitive_data(encrypted)
    print(f"Encryption test: {sensitive_data == decrypted}")
    
    # Test data masking
    masked_card = sm.mask_sensitive_data("4111111111111111", "card")
    print(f"Masked card: {masked_card}")
    
    # Test threat detection
    monitor = SecurityMonitor()
    safe, _ = monitor.check_for_threats({"input": "normal data"})
    print(f"Normal data threat check: {safe}")
    
    dangerous, threat = monitor.check_for_threats({"input": "'; DROP TABLE users; --"})
    print(f"SQL injection threat check: {not dangerous}")
    
    print("\n✅ Security configuration complete")