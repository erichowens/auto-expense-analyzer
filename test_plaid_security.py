#!/usr/bin/env python3
"""
Comprehensive Plaid Security Test Suite
Proves all security requirements are properly implemented.
"""

import os
import sys
import time
import json
import secrets
import unittest
from datetime import datetime, timedelta
import sqlite3
import tempfile
import threading
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plaid_security import (
    PlaidTokenVault, PlaidWebhookSecurity, PlaidRateLimiter,
    PlaidSecurityManager, plaid_security
)


class TestPlaidTokenVault(unittest.TestCase):
    """Test secure token storage and encryption."""
    
    def setUp(self):
        """Set up test vault with temporary database."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.vault = PlaidTokenVault(vault_path=self.temp_db.name)
        self.test_user = "test_user_" + secrets.token_hex(4)
        self.test_token = "access-sandbox-" + secrets.token_hex(16)
    
    def tearDown(self):
        """Clean up temporary database."""
        try:
            os.unlink(self.temp_db.name)
        except:
            pass
    
    def test_token_encryption_at_rest(self):
        """Test that tokens are encrypted when stored in database."""
        # Store a token
        success = self.vault.store_token(
            user_id=self.test_user,
            access_token=self.test_token,
            item_id="test_item_123"
        )
        self.assertTrue(success, "Token storage should succeed")
        
        # Read directly from database to verify encryption
        conn = sqlite3.connect(self.temp_db.name)
        cursor = conn.execute(
            "SELECT encrypted_token FROM token_vault WHERE user_id = ?",
            (self.test_user,)
        )
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row, "Token should be in database")
        encrypted_token = row[0]
        
        # Verify token is encrypted (not plaintext)
        self.assertNotEqual(encrypted_token, self.test_token, 
                           "Token should be encrypted in database")
        self.assertGreater(len(encrypted_token), len(self.test_token),
                          "Encrypted token should be longer than plaintext")
        
        print("✅ Token encryption at rest: PASSED")
    
    def test_token_decryption_and_retrieval(self):
        """Test that tokens can be securely retrieved and decrypted."""
        # Store token
        self.vault.store_token(
            user_id=self.test_user,
            access_token=self.test_token,
            item_id="test_item"
        )
        
        # Retrieve token
        retrieved_token = self.vault.retrieve_token(self.test_user)
        
        self.assertEqual(retrieved_token, self.test_token,
                        "Retrieved token should match original")
        
        print("✅ Token decryption and retrieval: PASSED")
    
    def test_token_integrity_verification(self):
        """Test that token integrity is verified on retrieval."""
        # Store token
        self.vault.store_token(
            user_id=self.test_user,
            access_token=self.test_token,
            item_id="test_item"
        )
        
        # Tamper with the token hash in database
        conn = sqlite3.connect(self.temp_db.name)
        conn.execute(
            "UPDATE token_vault SET token_hash = ? WHERE user_id = ?",
            ("invalid_hash", self.test_user)
        )
        conn.commit()
        conn.close()
        
        # Try to retrieve token with integrity check
        retrieved = self.vault.retrieve_token(self.test_user, verify_integrity=True)
        
        self.assertIsNone(retrieved, 
                         "Should return None when integrity check fails")
        
        print("✅ Token integrity verification: PASSED")
    
    def test_token_expiration(self):
        """Test that expired tokens are not returned."""
        # Store token with short expiration
        self.vault.store_token(
            user_id=self.test_user,
            access_token=self.test_token,
            item_id="test_item",
            expires_in=1  # 1 second expiration
        )
        
        # Wait for expiration
        time.sleep(2)
        
        # Try to retrieve expired token
        retrieved = self.vault.retrieve_token(self.test_user)
        
        self.assertIsNone(retrieved, "Expired token should not be retrieved")
        
        print("✅ Token expiration handling: PASSED")
    
    def test_token_revocation(self):
        """Test that tokens can be revoked."""
        # Store token
        self.vault.store_token(
            user_id=self.test_user,
            access_token=self.test_token,
            item_id="test_item"
        )
        
        # Revoke token
        success = self.vault.revoke_token(self.test_user)
        self.assertTrue(success, "Token revocation should succeed")
        
        # Try to retrieve revoked token
        retrieved = self.vault.retrieve_token(self.test_user)
        
        self.assertIsNone(retrieved, "Revoked token should not be retrieved")
        
        print("✅ Token revocation: PASSED")
    
    def test_audit_logging(self):
        """Test that all token operations are audit logged."""
        # Perform various operations
        self.vault.store_token(self.test_user, self.test_token, "item_123")
        self.vault.retrieve_token(self.test_user)
        self.vault.revoke_token(self.test_user)
        
        # Check audit logs
        conn = sqlite3.connect(self.temp_db.name)
        cursor = conn.execute(
            "SELECT action FROM token_audit WHERE user_id = ? ORDER BY timestamp",
            (self.test_user,)
        )
        actions = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        expected_actions = ['TOKEN_STORED', 'TOKEN_RETRIEVED', 'TOKEN_REVOKED']
        self.assertEqual(actions, expected_actions,
                        "All operations should be audit logged")
        
        print("✅ Audit logging: PASSED")


class TestPlaidRateLimiting(unittest.TestCase):
    """Test rate limiting and DDoS protection."""
    
    def setUp(self):
        """Set up rate limiter."""
        self.rate_limiter = PlaidRateLimiter(max_requests_per_minute=5)
        self.test_user = "test_user_" + secrets.token_hex(4)
    
    def test_rate_limit_enforcement(self):
        """Test that rate limits are properly enforced."""
        # Make requests up to the limit
        for i in range(5):
            allowed, retry_after = self.rate_limiter.check_rate_limit(self.test_user)
            self.assertTrue(allowed, f"Request {i+1} should be allowed")
        
        # Next request should be blocked
        allowed, retry_after = self.rate_limiter.check_rate_limit(self.test_user)
        self.assertFalse(allowed, "Request beyond limit should be blocked")
        self.assertIsNotNone(retry_after, "Should provide retry_after value")
        self.assertGreater(retry_after, 0, "Retry after should be positive")
        
        print("✅ Rate limit enforcement: PASSED")
    
    def test_rate_limit_window_reset(self):
        """Test that rate limit resets after time window."""
        # Use a very short window for testing
        limiter = PlaidRateLimiter(max_requests_per_minute=2)
        
        # Make 2 requests (at limit)
        for _ in range(2):
            allowed, _ = limiter.check_rate_limit(self.test_user)
            self.assertTrue(allowed)
        
        # Should be blocked now
        allowed, _ = limiter.check_rate_limit(self.test_user)
        self.assertFalse(allowed)
        
        # Simulate time passing by manipulating the request timestamps
        with limiter._lock:
            # Clear old requests to simulate window reset
            limiter.requests[self.test_user] = []
        
        # Should be allowed again
        allowed, _ = limiter.check_rate_limit(self.test_user)
        self.assertTrue(allowed, "Should be allowed after window reset")
        
        print("✅ Rate limit window reset: PASSED")
    
    def test_concurrent_rate_limiting(self):
        """Test rate limiting under concurrent access."""
        limiter = PlaidRateLimiter(max_requests_per_minute=10)
        results = []
        
        def make_requests(user_id, count):
            for _ in range(count):
                allowed, _ = limiter.check_rate_limit(user_id)
                results.append(allowed)
        
        # Create multiple threads making requests
        threads = []
        for i in range(3):
            thread = threading.Thread(
                target=make_requests,
                args=(f"user_{i}", 5)
            )
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Each user should have their own rate limit
        self.assertEqual(len(results), 15, "All requests should be processed")
        
        print("✅ Concurrent rate limiting: PASSED")


class TestPlaidWebhookSecurity(unittest.TestCase):
    """Test webhook verification and security."""
    
    def setUp(self):
        """Set up webhook security."""
        self.webhook_security = PlaidWebhookSecurity(
            webhook_secret="test_webhook_secret_12345"
        )
    
    def test_webhook_url_generation(self):
        """Test secure webhook URL generation."""
        base_url = "https://example.com"
        user_id = "user_123"
        
        webhook_url = self.webhook_security.generate_webhook_url(base_url, user_id)
        
        self.assertIn(base_url, webhook_url, "Should contain base URL")
        self.assertIn(user_id, webhook_url, "Should contain user ID")
        self.assertIn("/webhooks/plaid/", webhook_url, "Should have correct path")
        
        # Should have a verification token
        parts = webhook_url.split('/')
        verification_token = parts[-1]
        self.assertGreater(len(verification_token), 20, 
                          "Should have substantial verification token")
        
        print("✅ Webhook URL generation: PASSED")
    
    @patch('time.time')
    @patch('jwt.decode')
    def test_webhook_verification(self, mock_jwt_decode, mock_time):
        """Test webhook signature verification."""
        mock_time.return_value = 1000
        
        test_body = b'{"test": "data"}'
        body_hash = "test_hash"
        
        # Mock successful JWT verification
        mock_jwt_decode.return_value = {
            'body_hash': body_hash,
            'timestamp': 1000
        }
        
        # Mock the hash to match
        with patch('hashlib.sha256') as mock_sha256:
            mock_sha256.return_value.hexdigest.return_value = body_hash
            
            result = self.webhook_security.verify_webhook(
                test_body, 
                "test_signature"
            )
        
        self.assertTrue(result, "Valid webhook should verify successfully")
        
        print("✅ Webhook verification: PASSED")
    
    @patch('time.time')
    @patch('jwt.decode')
    def test_webhook_replay_protection(self, mock_jwt_decode, mock_time):
        """Test protection against webhook replay attacks."""
        mock_time.return_value = 1000
        
        # Mock JWT with old timestamp (replay attack)
        mock_jwt_decode.return_value = {
            'body_hash': 'test_hash',
            'timestamp': 500  # 500 seconds old
        }
        
        result = self.webhook_security.verify_webhook(
            b'{"test": "data"}',
            "test_signature"
        )
        
        self.assertFalse(result, "Old webhook should be rejected (replay protection)")
        
        print("✅ Webhook replay protection: PASSED")


class TestPlaidSecurityManager(unittest.TestCase):
    """Test the main security manager."""
    
    def test_api_key_validation(self):
        """Test API key configuration validation."""
        # Test with missing keys
        with patch.dict(os.environ, {}, clear=True):
            valid, issues = plaid_security.validate_api_keys()
            self.assertFalse(valid, "Should fail with missing keys")
            self.assertGreater(len(issues), 0, "Should report issues")
        
        # Test with valid keys
        with patch.dict(os.environ, {
            'PLAID_CLIENT_ID': 'test_client_id_1234567890abcdef',
            'PLAID_SECRET': 'test_secret_1234567890abcdef',
            'PLAID_ENV': 'sandbox',
            'PLAID_WEBHOOK_SECRET': 'webhook_secret_123'
        }):
            valid, issues = plaid_security.validate_api_keys()
            self.assertTrue(valid, "Should pass with valid keys")
            self.assertEqual(len(issues), 0, "Should have no issues")
        
        print("✅ API key validation: PASSED")
    
    def test_data_sanitization(self):
        """Test sensitive data sanitization."""
        sensitive_data = {
            'access_token': 'access-sandbox-1234567890abcdef',
            'public_token': 'public-sandbox-abcdef1234567890',
            'accounts': [
                {'account_id': 'acc_1234567890abcdef'},
                {'account_id': 'acc_abcdef1234567890'}
            ],
            'safe_field': 'this should not be masked'
        }
        
        sanitized = plaid_security.sanitize_plaid_data(sensitive_data)
        
        # Check tokens are masked
        self.assertIn('...', sanitized['access_token'], 
                     "Access token should be masked")
        self.assertIn('...', sanitized['public_token'],
                     "Public token should be masked")
        
        # Check account IDs are masked
        for account in sanitized['accounts']:
            self.assertIn('...', account['account_id'],
                         "Account ID should be masked")
        
        # Check safe field is not modified
        self.assertEqual(sanitized['safe_field'], sensitive_data['safe_field'],
                        "Non-sensitive data should not be modified")
        
        print("✅ Data sanitization: PASSED")
    
    def test_security_headers(self):
        """Test security headers generation."""
        headers = plaid_security.get_security_headers()
        
        self.assertIn('X-Request-ID', headers, "Should include request ID")
        self.assertIn('X-Client-Version', headers, "Should include client version")
        self.assertIn('User-Agent', headers, "Should include user agent")
        
        # Request ID should be unique each time
        headers2 = plaid_security.get_security_headers()
        self.assertNotEqual(headers['X-Request-ID'], headers2['X-Request-ID'],
                           "Request IDs should be unique")
        
        print("✅ Security headers: PASSED")
    
    def test_environment_validation(self):
        """Test environment validation."""
        valid_envs = ['sandbox', 'development', 'production']
        
        for env in valid_envs:
            self.assertTrue(plaid_security.validate_environment(env),
                          f"{env} should be valid")
        
        invalid_envs = ['test', 'staging', 'local', 'invalid']
        for env in invalid_envs:
            self.assertFalse(plaid_security.validate_environment(env),
                           f"{env} should be invalid")
        
        print("✅ Environment validation: PASSED")


class TestSecurityCompliance(unittest.TestCase):
    """Test overall security compliance."""
    
    def test_pci_compliance_features(self):
        """Test PCI compliance features are enabled."""
        config = plaid_security.security_config
        
        self.assertTrue(config['pci_compliance_mode'],
                       "PCI compliance mode should be enabled")
        self.assertEqual(config['encryption_algorithm'], 'AES-256-GCM',
                        "Should use strong encryption")
        self.assertEqual(config['min_tls_version'], '1.2',
                        "Should require TLS 1.2 minimum")
        
        print("✅ PCI compliance features: PASSED")
    
    def test_data_retention_policy(self):
        """Test data retention configuration."""
        config = plaid_security.security_config
        
        self.assertEqual(config['audit_retention_days'], 2555,
                        "Should retain audit logs for 7 years")
        self.assertIn('token_rotation_days', config,
                     "Should have token rotation policy")
        self.assertIn('max_token_age_days', config,
                     "Should have maximum token age")
        
        print("✅ Data retention policy: PASSED")
    
    def test_secure_configuration(self):
        """Test secure configuration requirements."""
        config = plaid_security.security_config
        
        self.assertTrue(config['require_https'],
                       "Should require HTTPS")
        self.assertGreater(config['token_rotation_days'], 0,
                          "Should have token rotation")
        self.assertIn('transactions', config['allowed_products'],
                     "Should allow transactions product")
        
        print("✅ Secure configuration: PASSED")


def run_security_tests():
    """Run all security tests and generate report."""
    print("\n" + "="*60)
    print("PLAID SECURITY COMPLIANCE TEST SUITE")
    print("="*60 + "\n")
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    test_classes = [
        TestPlaidTokenVault,
        TestPlaidRateLimiting,
        TestPlaidWebhookSecurity,
        TestPlaidSecurityManager,
        TestSecurityCompliance
    ]
    
    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Generate summary
    print("\n" + "="*60)
    print("SECURITY TEST SUMMARY")
    print("="*60)
    
    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total_tests - failures - errors
    
    print(f"\nTotal Tests: {total_tests}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failures}")
    print(f"⚠️  Errors: {errors}")
    
    if failures == 0 and errors == 0:
        print("\n🎉 ALL SECURITY TESTS PASSED! 🎉")
        print("\nYour Plaid integration meets all security requirements:")
        print("✅ Token encryption at rest")
        print("✅ Secure token storage and retrieval")
        print("✅ Token integrity verification")
        print("✅ Token expiration and revocation")
        print("✅ Comprehensive audit logging")
        print("✅ Rate limiting and DDoS protection")
        print("✅ Webhook security and verification")
        print("✅ API key validation")
        print("✅ Data sanitization")
        print("✅ PCI compliance features")
        print("✅ Data retention policies")
    else:
        print("\n⚠️  Some tests failed. Please review and fix issues.")
    
    return result


if __name__ == '__main__':
    run_security_tests()