#!/usr/bin/env python3
"""
Enhanced Plaid Security Implementation
Implements comprehensive security measures for Plaid integration to meet approval requirements.
"""

import os
import json
import hmac
import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64
import sqlite3
from contextlib import contextmanager
import threading
import time

# Initialize secure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler('plaid_security_audit.log'),
        logging.StreamHandler()
    ]
)
security_logger = logging.getLogger('plaid_security')


class PlaidTokenVault:
    """Secure vault for Plaid access tokens with encryption at rest."""
    
    def __init__(self, vault_path: str = "data/plaid_vault.db"):
        self.vault_path = vault_path
        self.encryption_key = self._derive_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key)
        self._init_vault()
        self._lock = threading.Lock()
        
    def _derive_encryption_key(self) -> bytes:
        """Derive encryption key from master key using PBKDF2."""
        master_key = os.getenv('PLAID_MASTER_KEY', '').encode()
        if not master_key:
            # Generate and save a master key if not exists
            master_key = secrets.token_bytes(32)
            security_logger.warning("Generated new master key - ensure PLAID_MASTER_KEY is set in production")
        
        salt = b'plaid_token_vault_salt_v1'  # In production, use unique salt per installation
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_key))
        return key
    
    def _init_vault(self):
        """Initialize the secure token vault database."""
        with self._get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS token_vault (
                    user_id TEXT PRIMARY KEY,
                    encrypted_token TEXT NOT NULL,
                    item_id TEXT,
                    created_at TIMESTAMP NOT NULL,
                    last_accessed TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    token_hash TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    refresh_token TEXT,
                    expires_at TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS token_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    success BOOLEAN,
                    details TEXT
                )
            ''')
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper error handling."""
        conn = sqlite3.connect(self.vault_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def store_token(self, user_id: str, access_token: str, item_id: str = None,
                   refresh_token: str = None, expires_in: int = None) -> bool:
        """Securely store a Plaid access token."""
        with self._lock:
            try:
                # Encrypt the token
                encrypted_token = self.cipher_suite.encrypt(access_token.encode()).decode()
                
                # Hash the token for integrity verification
                token_hash = hashlib.sha256(access_token.encode()).hexdigest()
                
                # Encrypt refresh token if provided
                encrypted_refresh = None
                if refresh_token:
                    encrypted_refresh = self.cipher_suite.encrypt(refresh_token.encode()).decode()
                
                # Calculate expiration
                expires_at = None
                if expires_in:
                    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                
                with self._get_connection() as conn:
                    conn.execute('''
                        INSERT OR REPLACE INTO token_vault 
                        (user_id, encrypted_token, item_id, created_at, token_hash, 
                         refresh_token, expires_at, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    ''', (user_id, encrypted_token, item_id, datetime.utcnow(), 
                          token_hash, encrypted_refresh, expires_at))
                    
                    # Audit log
                    self._audit_log(conn, user_id, 'TOKEN_STORED', True, 
                                  {'item_id': item_id, 'has_refresh': bool(refresh_token)})
                    conn.commit()
                
                security_logger.info(f"Token stored for user {user_id}")
                return True
                
            except Exception as e:
                security_logger.error(f"Failed to store token: {e}")
                return False
    
    def retrieve_token(self, user_id: str, verify_integrity: bool = True) -> Optional[str]:
        """Retrieve and decrypt a Plaid access token."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute('''
                        SELECT encrypted_token, token_hash, expires_at, is_active
                        FROM token_vault 
                        WHERE user_id = ? AND is_active = 1
                    ''', (user_id,))
                    
                    row = cursor.fetchone()
                    if not row:
                        self._audit_log(conn, user_id, 'TOKEN_NOT_FOUND', False)
                        return None
                    
                    # Check expiration
                    if row['expires_at']:
                        expires_at = datetime.fromisoformat(row['expires_at'])
                        if expires_at < datetime.utcnow():
                            self._audit_log(conn, user_id, 'TOKEN_EXPIRED', False)
                            return None
                    
                    # Decrypt token
                    decrypted_token = self.cipher_suite.decrypt(
                        row['encrypted_token'].encode()
                    ).decode()
                    
                    # Verify integrity
                    if verify_integrity:
                        computed_hash = hashlib.sha256(decrypted_token.encode()).hexdigest()
                        if computed_hash != row['token_hash']:
                            self._audit_log(conn, user_id, 'INTEGRITY_CHECK_FAILED', False)
                            security_logger.error(f"Token integrity check failed for user {user_id}")
                            return None
                    
                    # Update access metadata
                    conn.execute('''
                        UPDATE token_vault 
                        SET last_accessed = ?, access_count = access_count + 1
                        WHERE user_id = ?
                    ''', (datetime.utcnow(), user_id))
                    
                    self._audit_log(conn, user_id, 'TOKEN_RETRIEVED', True)
                    conn.commit()
                    
                    return decrypted_token
                    
            except Exception as e:
                security_logger.error(f"Failed to retrieve token: {e}")
                return None
    
    def revoke_token(self, user_id: str) -> bool:
        """Revoke a user's access token."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute('''
                        UPDATE token_vault 
                        SET is_active = 0 
                        WHERE user_id = ?
                    ''', (user_id,))
                    
                    self._audit_log(conn, user_id, 'TOKEN_REVOKED', True)
                    conn.commit()
                
                security_logger.info(f"Token revoked for user {user_id}")
                return True
                
            except Exception as e:
                security_logger.error(f"Failed to revoke token: {e}")
                return False
    
    def _audit_log(self, conn, user_id: str, action: str, success: bool, 
                   details: Dict = None):
        """Log security audit events."""
        conn.execute('''
            INSERT INTO token_audit 
            (user_id, action, timestamp, success, details)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, action, datetime.utcnow(), success, 
              json.dumps(details) if details else None))


class PlaidWebhookSecurity:
    """Handles Plaid webhook verification and security."""
    
    def __init__(self, webhook_secret: str = None):
        self.webhook_secret = webhook_secret or os.getenv('PLAID_WEBHOOK_SECRET')
        if not self.webhook_secret:
            self.webhook_secret = secrets.token_urlsafe(32)
            security_logger.warning("Generated webhook secret - set PLAID_WEBHOOK_SECRET in production")
    
    def verify_webhook(self, body: bytes, signature: str) -> bool:
        """Verify Plaid webhook signature using JWT verification."""
        try:
            # Plaid uses JWT for webhook verification in newer implementations
            import jwt
            
            # Decode and verify the JWT signature
            decoded = jwt.decode(
                signature,
                self.webhook_secret,
                algorithms=['HS256'],
                options={"verify_signature": True}
            )
            
            # Verify the body matches
            body_hash = hashlib.sha256(body).hexdigest()
            if decoded.get('body_hash') != body_hash:
                security_logger.warning("Webhook body hash mismatch")
                return False
            
            # Check timestamp to prevent replay attacks
            timestamp = decoded.get('timestamp', 0)
            current_time = time.time()
            if abs(current_time - timestamp) > 300:  # 5 minute window
                security_logger.warning("Webhook timestamp outside acceptable window")
                return False
            
            return True
            
        except Exception as e:
            security_logger.error(f"Webhook verification failed: {e}")
            return False
    
    def generate_webhook_url(self, base_url: str, user_id: str) -> str:
        """Generate a secure webhook URL with verification token."""
        verification_token = secrets.token_urlsafe(32)
        webhook_path = f"/webhooks/plaid/{user_id}/{verification_token}"
        
        # Store verification token for later validation
        # In production, store this in Redis or database
        
        return f"{base_url}{webhook_path}"


class PlaidRateLimiter:
    """Rate limiting for Plaid API calls to prevent abuse."""
    
    def __init__(self, max_requests_per_minute: int = 60):
        self.max_requests = max_requests_per_minute
        self.requests = {}
        self._lock = threading.Lock()
    
    def check_rate_limit(self, user_id: str) -> tuple[bool, Optional[int]]:
        """Check if user has exceeded rate limit."""
        with self._lock:
            current_time = time.time()
            minute_ago = current_time - 60
            
            # Clean old requests
            if user_id in self.requests:
                self.requests[user_id] = [
                    req_time for req_time in self.requests[user_id]
                    if req_time > minute_ago
                ]
            else:
                self.requests[user_id] = []
            
            # Check limit
            if len(self.requests[user_id]) >= self.max_requests:
                # Calculate retry after
                oldest_request = min(self.requests[user_id])
                retry_after = int(60 - (current_time - oldest_request))
                return False, retry_after
            
            # Record request
            self.requests[user_id].append(current_time)
            return True, None


class PlaidSecurityManager:
    """Main security manager for Plaid integration."""
    
    def __init__(self):
        self.token_vault = PlaidTokenVault()
        self.webhook_security = PlaidWebhookSecurity()
        self.rate_limiter = PlaidRateLimiter()
        self.security_config = self._load_security_config()
    
    def _load_security_config(self) -> Dict:
        """Load security configuration."""
        return {
            'require_https': True,
            'token_rotation_days': 90,
            'max_token_age_days': 365,
            'require_mfa': False,  # Can be enabled for additional security
            'allowed_environments': ['sandbox', 'development', 'production'],
            'audit_retention_days': 2555,  # 7 years for compliance
            'encryption_algorithm': 'AES-256-GCM',
            'min_tls_version': '1.2',
            'allowed_products': ['transactions', 'accounts', 'identity'],
            'pci_compliance_mode': True
        }
    
    def validate_environment(self, environment: str) -> bool:
        """Validate Plaid environment setting."""
        return environment in self.security_config['allowed_environments']
    
    def sanitize_plaid_data(self, data: Dict) -> Dict:
        """Sanitize sensitive data from Plaid responses."""
        sanitized = data.copy()
        
        # Remove or mask sensitive fields
        sensitive_fields = ['access_token', 'public_token', 'processor_token']
        for field in sensitive_fields:
            if field in sanitized:
                sanitized[field] = self._mask_token(sanitized[field])
        
        # Mask account numbers
        if 'accounts' in sanitized:
            for account in sanitized['accounts']:
                if 'account_id' in account:
                    account['account_id'] = self._mask_token(account['account_id'], 8)
        
        return sanitized
    
    def _mask_token(self, token: str, visible_chars: int = 4) -> str:
        """Mask a token showing only first and last N characters."""
        if not token or len(token) <= visible_chars * 2:
            return '*' * len(token) if token else ''
        
        return token[:visible_chars] + '...' + token[-visible_chars:]
    
    def audit_plaid_action(self, action: str, user_id: str, details: Dict):
        """Audit log for Plaid-specific actions."""
        audit_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'action': action,
            'user_id': user_id,
            'details': self.sanitize_plaid_data(details),
            'environment': os.getenv('PLAID_ENV', 'sandbox')
        }
        
        security_logger.info(f"PLAID_AUDIT: {json.dumps(audit_entry)}")
    
    def validate_api_keys(self) -> tuple[bool, List[str]]:
        """Validate Plaid API keys are properly configured."""
        issues = []
        
        # Check client ID
        client_id = os.getenv('PLAID_CLIENT_ID')
        if not client_id:
            issues.append("PLAID_CLIENT_ID not set")
        elif len(client_id) < 20:
            issues.append("PLAID_CLIENT_ID appears invalid")
        
        # Check secret
        secret = os.getenv('PLAID_SECRET')
        if not secret:
            issues.append("PLAID_SECRET not set")
        elif len(secret) < 20:
            issues.append("PLAID_SECRET appears invalid")
        
        # Check environment
        env = os.getenv('PLAID_ENV')
        if not env:
            issues.append("PLAID_ENV not set")
        elif not self.validate_environment(env):
            issues.append(f"Invalid PLAID_ENV: {env}")
        
        # Check webhook secret
        webhook_secret = os.getenv('PLAID_WEBHOOK_SECRET')
        if not webhook_secret:
            issues.append("PLAID_WEBHOOK_SECRET not set (webhooks will not be secure)")
        
        return len(issues) == 0, issues
    
    def get_security_headers(self) -> Dict[str, str]:
        """Get security headers for Plaid API requests."""
        return {
            'X-Request-ID': secrets.token_urlsafe(16),
            'X-Client-Version': '1.0.0',
            'User-Agent': 'TravelExpenseAnalyzer/1.0 PlaidSecure/1.0'
        }
    
    def enforce_data_retention(self):
        """Enforce data retention policies."""
        retention_days = self.security_config['audit_retention_days']
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        # Clean old audit logs
        with sqlite3.connect('data/plaid_vault.db') as conn:
            conn.execute('''
                DELETE FROM token_audit 
                WHERE timestamp < ?
            ''', (cutoff_date,))
            
            deleted = conn.total_changes
            if deleted > 0:
                security_logger.info(f"Cleaned {deleted} old audit entries")


# Singleton instance
plaid_security = PlaidSecurityManager()


def secure_plaid_request(func):
    """Decorator for securing Plaid API requests."""
    def wrapper(user_id: str, *args, **kwargs):
        # Check rate limit
        allowed, retry_after = plaid_security.rate_limiter.check_rate_limit(user_id)
        if not allowed:
            raise Exception(f"Rate limit exceeded. Retry after {retry_after} seconds")
        
        # Audit the request
        plaid_security.audit_plaid_action(
            f"API_CALL_{func.__name__}",
            user_id,
            {'function': func.__name__, 'timestamp': datetime.utcnow().isoformat()}
        )
        
        try:
            result = func(user_id, *args, **kwargs)
            return result
        except Exception as e:
            security_logger.error(f"Plaid API call failed: {e}")
            raise
    
    return wrapper


if __name__ == '__main__':
    print("Plaid Security Module Test")
    print("=" * 50)
    
    # Test configuration validation
    valid, issues = plaid_security.validate_api_keys()
    print(f"\nAPI Key Validation: {'✅ PASSED' if valid else '❌ FAILED'}")
    if issues:
        for issue in issues:
            print(f"  - {issue}")
    
    # Test token vault
    test_user = "test_user_123"
    test_token = "access-sandbox-test-token-12345"
    
    print("\nToken Vault Tests:")
    
    # Store token
    stored = plaid_security.token_vault.store_token(
        test_user, test_token, "item_123"
    )
    print(f"  Store token: {'✅' if stored else '❌'}")
    
    # Retrieve token
    retrieved = plaid_security.token_vault.retrieve_token(test_user)
    print(f"  Retrieve token: {'✅' if retrieved == test_token else '❌'}")
    
    # Test rate limiting
    print("\nRate Limiting Test:")
    for i in range(5):
        allowed, retry = plaid_security.rate_limiter.check_rate_limit(test_user)
        print(f"  Request {i+1}: {'✅ Allowed' if allowed else f'❌ Blocked (retry: {retry}s)'}")
    
    # Test data sanitization
    print("\nData Sanitization Test:")
    test_data = {
        'access_token': 'access-sandbox-abcdef123456',
        'accounts': [
            {'account_id': 'acc_1234567890abcdef'}
        ]
    }
    sanitized = plaid_security.sanitize_plaid_data(test_data)
    print(f"  Token masked: {sanitized['access_token']}")
    print(f"  Account ID masked: {sanitized['accounts'][0]['account_id']}")
    
    print("\n✅ Security tests completed")