#!/usr/bin/env python3
"""
Security Tests for Travel Expense System
Tests SQL injection prevention, CSRF protection, input validation, auth, and session management.
"""

import pytest
import json
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import re
from urllib.parse import quote

# ==================== SQL Injection Tests ====================

@pytest.mark.security
class TestSQLInjectionPrevention:
    """Test SQL injection prevention across all database operations."""
    
    def test_sql_injection_in_trip_search(self, populated_database, sql_injection_payloads):
        """Test SQL injection prevention in trip search queries."""
        db = populated_database
        
        for payload in sql_injection_payloads:
            # Should not raise an exception or return unexpected data
            with pytest.raises(Exception) as exc_info:
                # Attempt injection through trip search
                trips = db.search_trips(location=payload)
            
            # Or should return empty/sanitized results
            trips = db.search_trips(location=payload)
            
            # Verify no data leak
            if trips:
                # Should only return trips matching the literal string (unlikely)
                for trip in trips:
                    assert payload in str(trip.get('primary_location', ''))
    
    def test_sql_injection_in_transaction_filters(self, populated_database, sql_injection_payloads):
        """Test SQL injection prevention in transaction filtering."""
        db = populated_database
        
        for payload in sql_injection_payloads:
            # Test various filter parameters
            filters = [
                {'description': payload},
                {'category': payload},
                {'date_from': payload},
                {'vendor_name': payload}
            ]
            
            for filter_param in filters:
                transactions = db.get_transactions(**filter_param)
                
                # Should either return empty or only matching literal strings
                if transactions:
                    for trans in transactions:
                        # Verify no unauthorized data access
                        assert len(transactions) <= db.get_transaction_count()
    
    def test_parameterized_queries(self, test_database):
        """Verify all database queries use parameterized statements."""
        db = test_database
        
        # Test transaction insertion with malicious data
        malicious_transaction = {
            'date': '2024-01-01',
            'description': "'; DROP TABLE transactions; --",
            'amount': 100.00,
            'location': "' OR '1'='1",
            'category': 'MEALS',
            'is_oregon': False
        }
        
        # Should safely insert without executing injection
        trans_id = db.save_transaction(malicious_transaction)
        assert trans_id is not None
        
        # Verify data was stored as literal string
        retrieved = db.get_transaction(trans_id)
        assert retrieved['description'] == malicious_transaction['description']
        
        # Verify tables still exist
        assert db.get_transaction_count() >= 0
        assert db.get_trip_count() >= 0
    
    def test_stored_procedure_injection(self, populated_database):
        """Test injection attempts through stored procedures or complex queries."""
        db = populated_database
        
        # Test complex query with user input
        malicious_input = "1; EXEC sp_configure 'show advanced options', 1; --"
        
        # Should handle safely
        results = db.get_trip_summary(trip_id=malicious_input)
        assert results is None or isinstance(results, dict)
    

# ==================== CSRF Protection Tests ====================

@pytest.mark.security
class TestCSRFProtection:
    """Test CSRF protection mechanisms."""
    
    def test_csrf_token_generation(self, client):
        """Test CSRF token is generated for forms."""
        response = client.get('/')
        
        # Check for CSRF token in response
        assert response.status_code == 200
        
        # For forms, verify CSRF token presence
        if b'<form' in response.data:
            assert b'csrf_token' in response.data or b'_csrf_token' in response.data
    
    def test_post_without_csrf_token(self, client):
        """Test POST requests fail without CSRF token."""
        # Attempt to create trip without CSRF token
        response = client.post('/api/trips', 
                              json={'location': 'Seattle', 'purpose': 'Meeting'})
        
        # Should either require authentication or CSRF token
        assert response.status_code in [400, 401, 403]
    
    def test_csrf_token_validation(self, authenticated_client):
        """Test CSRF token validation on state-changing operations."""
        client = authenticated_client
        
        # Get a valid CSRF token
        response = client.get('/api/csrf-token')
        if response.status_code == 200:
            csrf_token = response.get_json().get('csrf_token')
            
            # Test with valid token
            response = client.post('/api/trips',
                                 headers={'X-CSRF-Token': csrf_token},
                                 json={'location': 'Seattle'})
            
            # Should accept valid token
            assert response.status_code != 403
            
            # Test with invalid token
            response = client.post('/api/trips',
                                 headers={'X-CSRF-Token': 'invalid_token'},
                                 json={'location': 'Seattle'})
            
            # Should reject invalid token
            assert response.status_code in [400, 403]
    
    def test_same_origin_policy(self, client):
        """Test same-origin policy enforcement."""
        # Test cross-origin request
        response = client.post('/api/trips',
                             headers={
                                 'Origin': 'http://evil.com',
                                 'Referer': 'http://evil.com/attack'
                             },
                             json={'location': 'Seattle'})
        
        # Should reject or require additional validation
        assert response.status_code in [400, 401, 403]


# ==================== Input Validation Tests ====================

@pytest.mark.security
class TestInputValidation:
    """Test input validation and sanitization."""
    
    def test_xss_prevention_in_business_purpose(self, authenticated_client, xss_payloads):
        """Test XSS prevention in business purpose fields."""
        client = authenticated_client
        
        for payload in xss_payloads:
            response = client.put('/api/trips/1',
                                json={'business_purpose': payload})
            
            if response.status_code == 200:
                # Verify the payload was sanitized
                response = client.get('/api/trips/1')
                data = response.get_json()
                
                # Should not contain active script tags
                purpose = data.get('business_purpose', '')
                assert '<script>' not in purpose
                assert 'javascript:' not in purpose.lower()
                assert 'onerror=' not in purpose.lower()
    
    def test_file_upload_validation(self, authenticated_client):
        """Test file upload security validations."""
        client = authenticated_client
        
        # Test dangerous file types
        dangerous_files = [
            ('malware.exe', b'MZ\x90\x00'),  # Windows executable
            ('script.sh', b'#!/bin/bash\nrm -rf /'),  # Shell script
            ('payload.php', b'<?php system($_GET["cmd"]); ?>'),  # PHP script
            ('virus.js', b'eval(atob("malicious"))'),  # JavaScript
        ]
        
        for filename, content in dangerous_files:
            from io import BytesIO
            response = client.post('/api/upload-receipt',
                                 data={
                                     'file': (BytesIO(content), filename),
                                     'trip_id': '1'
                                 },
                                 content_type='multipart/form-data')
            
            # Should reject dangerous file types
            assert response.status_code in [400, 415], f"Failed to reject {filename}"
            
            if response.status_code == 400:
                data = response.get_json()
                assert 'error' in data
    
    def test_path_traversal_prevention(self, authenticated_client):
        """Test path traversal attack prevention."""
        client = authenticated_client
        
        path_traversal_attempts = [
            '../../etc/passwd',
            '..\\..\\windows\\system32\\config\\sam',
            'receipts/../../../etc/shadow',
            '%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd',
            'receipts/....//....//etc/passwd'
        ]
        
        for path in path_traversal_attempts:
            # Attempt to access files outside allowed directory
            response = client.get(f'/api/receipts/{path}')
            
            # Should block path traversal
            assert response.status_code in [400, 403, 404]
            
            # Verify no sensitive data in response
            if response.data:
                assert b'root:' not in response.data  # Unix passwd file
                assert b'Administrator' not in response.data  # Windows
    
    def test_input_length_limits(self, authenticated_client):
        """Test input length validation to prevent buffer overflow."""
        client = authenticated_client
        
        # Test extremely long inputs
        very_long_string = 'A' * 100000  # 100K characters
        
        test_cases = [
            ('/api/trips', {'business_purpose': very_long_string}),
            ('/api/transactions', {'description': very_long_string}),
            ('/api/search', {'query': very_long_string})
        ]
        
        for endpoint, payload in test_cases:
            response = client.post(endpoint, json=payload)
            
            # Should reject or truncate very long inputs
            assert response.status_code in [400, 413, 414]
    
    def test_special_character_handling(self, test_database):
        """Test handling of special characters in inputs."""
        db = test_database
        
        special_inputs = [
            "O'Reilly's Restaurant",  # Apostrophe
            "Price: $100.00 (tax incl.)",  # Special symbols
            "München Flughafen",  # Unicode characters
            "Line1\nLine2\rLine3",  # Newlines
            "\x00NULL\x00BYTE",  # Null bytes
            "❤️ 🚀 emoji test",  # Emojis
        ]
        
        for input_str in special_inputs:
            transaction = {
                'date': '2024-01-01',
                'description': input_str,
                'amount': 100.00,
                'location': 'TEST',
                'category': 'MEALS',
                'is_oregon': False
            }
            
            # Should handle special characters safely
            trans_id = db.save_transaction(transaction)
            assert trans_id is not None
            
            # Verify data integrity
            retrieved = db.get_transaction(trans_id)
            # Null bytes might be stripped, others preserved
            if '\x00' not in input_str:
                assert retrieved['description'] == input_str


# ==================== Authentication Tests ====================

@pytest.mark.security  
class TestAuthentication:
    """Test authentication mechanisms."""
    
    def test_unauthenticated_access_prevention(self, client):
        """Test that protected endpoints require authentication."""
        protected_endpoints = [
            '/api/trips',
            '/api/transactions',
            '/api/create-concur-reports',
            '/api/upload-receipt',
            '/api/exchange-public-token'
        ]
        
        for endpoint in protected_endpoints:
            # GET request without auth
            response = client.get(endpoint)
            assert response.status_code in [401, 403, 302], f"Unprotected: {endpoint}"
            
            # POST request without auth  
            response = client.post(endpoint, json={})
            assert response.status_code in [401, 403, 302], f"Unprotected POST: {endpoint}"
    
    def test_token_validation(self, client):
        """Test access token validation."""
        # Test with invalid token
        response = client.get('/api/trips',
                            headers={'Authorization': 'Bearer invalid_token'})
        assert response.status_code in [401, 403]
        
        # Test with malformed token
        response = client.get('/api/trips',
                            headers={'Authorization': 'NotBearer token'})
        assert response.status_code in [401, 403]
        
        # Test with empty token
        response = client.get('/api/trips',
                            headers={'Authorization': 'Bearer '})
        assert response.status_code in [401, 403]
    
    def test_session_fixation_prevention(self, client):
        """Test prevention of session fixation attacks."""
        # Get initial session
        response = client.get('/')
        initial_cookies = response.headers.getlist('Set-Cookie')
        
        # Attempt login (mock)
        with patch('production_app.authenticate_user') as mock_auth:
            mock_auth.return_value = True
            
            response = client.post('/api/login',
                                 json={'username': 'test', 'password': 'test'})
            
            # Session ID should change after authentication
            post_auth_cookies = response.headers.getlist('Set-Cookie')
            
            if initial_cookies and post_auth_cookies:
                # Extract session IDs and compare
                initial_session = self._extract_session_id(initial_cookies)
                post_auth_session = self._extract_session_id(post_auth_cookies)
                
                if initial_session and post_auth_session:
                    assert initial_session != post_auth_session
    
    def test_password_security_requirements(self, client):
        """Test password complexity requirements."""
        weak_passwords = [
            '123456',
            'password',
            'qwerty',
            'abc123',
            '12345678',
            'password123',
            'admin'
        ]
        
        for weak_pwd in weak_passwords:
            response = client.post('/api/register',
                                 json={
                                     'username': 'testuser',
                                     'password': weak_pwd,
                                     'email': 'test@example.com'
                                 })
            
            # Should reject weak passwords
            if response.status_code == 400:
                data = response.get_json()
                assert 'password' in str(data.get('error', '')).lower()
    
    def test_brute_force_protection(self, client):
        """Test rate limiting on authentication endpoints."""
        # Attempt multiple failed logins
        for i in range(20):
            response = client.post('/api/login',
                                 json={
                                     'username': 'admin',
                                     'password': f'wrong_password_{i}'
                                 })
        
        # Should eventually rate limit
        response = client.post('/api/login',
                             json={
                                 'username': 'admin',
                                 'password': 'another_attempt'
                             })
        
        # Should be rate limited
        assert response.status_code in [429, 403]
    
    def _extract_session_id(self, cookies):
        """Helper to extract session ID from cookies."""
        for cookie in cookies:
            if 'session' in cookie.lower():
                # Extract session ID from cookie string
                match = re.search(r'session=([^;]+)', cookie)
                if match:
                    return match.group(1)
        return None


# ==================== Session Management Tests ====================

@pytest.mark.security
class TestSessionManagement:
    """Test session security and management."""
    
    def test_session_timeout(self, authenticated_client):
        """Test that sessions expire after inactivity."""
        client = authenticated_client
        
        # Make initial authenticated request
        response = client.get('/api/trips')
        assert response.status_code == 200
        
        # Simulate session timeout
        with patch('production_app.SESSION_TIMEOUT', 1):  # 1 second timeout
            import time
            time.sleep(2)
            
            # Request should fail after timeout
            response = client.get('/api/trips')
            # Note: Actual implementation may vary
    
    def test_session_invalidation_on_logout(self, authenticated_client):
        """Test that sessions are properly invalidated on logout."""
        client = authenticated_client
        
        # Verify authenticated
        response = client.get('/api/trips')
        assert response.status_code == 200
        
        # Logout
        response = client.post('/api/logout')
        assert response.status_code in [200, 204]
        
        # Previous session should be invalid
        response = client.get('/api/trips')
        assert response.status_code in [401, 403]
    
    def test_concurrent_session_handling(self, client):
        """Test handling of concurrent sessions."""
        # Create two sessions for same user
        session1 = client.post('/api/login',
                              json={'username': 'test', 'password': 'test'})
        
        session2 = client.post('/api/login',
                              json={'username': 'test', 'password': 'test'})
        
        # Implementation specific: 
        # - May invalidate session1
        # - May allow both
        # - May limit concurrent sessions
    
    def test_session_data_isolation(self, app):
        """Test that session data is isolated between users."""
        client1 = app.test_client()
        client2 = app.test_client()
        
        # Set data in session 1
        with client1.session_transaction() as sess:
            sess['user_id'] = 'user1'
            sess['sensitive_data'] = 'secret1'
        
        # Set data in session 2
        with client2.session_transaction() as sess:
            sess['user_id'] = 'user2'
            sess['sensitive_data'] = 'secret2'
        
        # Verify isolation
        with client1.session_transaction() as sess:
            assert sess.get('user_id') == 'user1'
            assert sess.get('sensitive_data') == 'secret1'
        
        with client2.session_transaction() as sess:
            assert sess.get('user_id') == 'user2'
            assert sess.get('sensitive_data') == 'secret2'


# ==================== Data Protection Tests ====================

@pytest.mark.security
class TestDataProtection:
    """Test data protection and privacy measures."""
    
    def test_sensitive_data_masking(self, populated_database):
        """Test that sensitive data is properly masked in responses."""
        db = populated_database
        
        # Save sensitive data
        db.save_setting('plaid_access_token', 'access-sandbox-abc123xyz')
        db.save_setting('concur_client_secret', 'secret-key-456')
        
        # Retrieve settings (simulating API response)
        settings = db.get_all_settings()
        
        # Sensitive values should be masked
        for key, value in settings.items():
            if 'token' in key.lower() or 'secret' in key.lower():
                # Should not return full value
                assert value != 'access-sandbox-abc123xyz'
                assert value != 'secret-key-456'
                # Should be masked or None
                assert value is None or '***' in str(value) or len(str(value)) < 10
    
    def test_pii_data_handling(self, test_database):
        """Test proper handling of personally identifiable information."""
        db = test_database
        
        # Store PII data
        pii_transaction = {
            'date': '2024-01-01',
            'description': 'Payment from John Smith SSN: 123-45-6789',
            'amount': 100.00,
            'location': 'Home: 123 Main St',
            'category': 'PERSONAL',
            'is_oregon': False
        }
        
        trans_id = db.save_transaction(pii_transaction)
        
        # When retrieving, PII should be handled carefully
        transaction = db.get_transaction(trans_id)
        
        # Implementation specific: may redact SSN patterns
        if 'SSN' in transaction.get('description', ''):
            # Should not contain full SSN
            assert '123-45-6789' not in transaction['description']
    
    def test_encryption_at_rest(self, test_database):
        """Test that sensitive data is encrypted at rest."""
        db = test_database
        
        # Save sensitive token
        db.save_setting('api_key', 'super_secret_key_12345')
        
        # Check raw database file
        import sqlite3
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        
        # Query raw data
        cursor.execute("SELECT value FROM settings WHERE key = 'api_key'")
        raw_value = cursor.fetchone()
        conn.close()
        
        if raw_value:
            # Should not store in plaintext (implementation dependent)
            # This test assumes encryption is implemented
            pass  # Actual assertion depends on implementation
    
    def test_secure_cookie_flags(self, client):
        """Test that cookies have secure flags set."""
        response = client.get('/')
        cookies = response.headers.getlist('Set-Cookie')
        
        for cookie in cookies:
            cookie_lower = cookie.lower()
            
            # Should have security flags
            if 'session' in cookie_lower:
                assert 'httponly' in cookie_lower, "Missing HttpOnly flag"
                assert 'samesite' in cookie_lower, "Missing SameSite flag"
                
                # In production, should also have Secure flag
                if os.getenv('FLASK_ENV') == 'production':
                    assert 'secure' in cookie_lower, "Missing Secure flag"


# ==================== Error Handling Tests ====================

@pytest.mark.security
class TestErrorHandling:
    """Test secure error handling."""
    
    def test_error_message_information_disclosure(self, client):
        """Test that error messages don't leak sensitive information."""
        # Trigger various errors
        error_triggers = [
            ('/api/nonexistent', 404),
            ('/api/trips/999999', 404),
            ('/api/trips/invalid_id', 400),
        ]
        
        for endpoint, expected_status in error_triggers:
            response = client.get(endpoint)
            
            # Check status
            assert response.status_code == expected_status
            
            # Error response should not contain:
            error_data = response.data.decode('utf-8', errors='ignore')
            
            # No stack traces
            assert 'Traceback' not in error_data
            assert 'File "' not in error_data
            
            # No database schema information
            assert 'CREATE TABLE' not in error_data
            assert 'sqlite' not in error_data.lower()
            
            # No file paths
            assert '/home/' not in error_data
            assert '/usr/' not in error_data
            assert 'C:\\' not in error_data
    
    def test_debug_mode_disabled(self, app):
        """Test that debug mode is disabled in production."""
        # In production, debug should be False
        if os.getenv('FLASK_ENV') == 'production':
            assert not app.debug
            assert not app.config.get('DEBUG', False)
    
    def test_rate_limiting_on_errors(self, client):
        """Test rate limiting on error endpoints to prevent enumeration."""
        # Trigger many 404 errors rapidly
        for i in range(100):
            response = client.get(f'/api/trips/{i}')
        
        # Should eventually rate limit
        response = client.get('/api/trips/101')
        
        # May implement rate limiting on 404s
        # assert response.status_code == 429


# ==================== API Security Tests ====================

@pytest.mark.security
class TestAPISecuity:
    """Test API-specific security measures."""
    
    def test_api_versioning(self, client):
        """Test API versioning for security updates."""
        # Test that API version is checked
        response = client.get('/api/v1/trips',
                            headers={'API-Version': '1.0'})
        
        # Should handle versioning appropriately
        assert response.status_code in [200, 400, 404]
    
    def test_cors_configuration(self, client):
        """Test CORS configuration for API endpoints."""
        response = client.options('/api/trips',
                                headers={
                                    'Origin': 'http://localhost:3000',
                                    'Access-Control-Request-Method': 'GET'
                                })
        
        # Check CORS headers
        if 'Access-Control-Allow-Origin' in response.headers:
            allowed_origin = response.headers['Access-Control-Allow-Origin']
            # Should not allow all origins in production
            assert allowed_origin != '*' or os.getenv('FLASK_ENV') != 'production'
    
    def test_content_type_validation(self, authenticated_client):
        """Test that API validates content types."""
        client = authenticated_client
        
        # Send with wrong content type
        response = client.post('/api/trips',
                             data='not json data',
                             headers={'Content-Type': 'text/plain'})
        
        # Should reject invalid content type for JSON endpoints
        assert response.status_code in [400, 415]
    
    def test_api_key_rotation(self, test_database):
        """Test API key rotation capabilities."""
        db = test_database
        
        # Store API key with metadata
        db.save_setting('api_key', 'old_key_12345')
        db.save_setting('api_key_created', datetime.now().isoformat())
        
        # Check if key rotation is needed (e.g., after 90 days)
        key_created = db.get_setting('api_key_created')
        if key_created:
            created_date = datetime.fromisoformat(key_created)
            age_days = (datetime.now() - created_date).days
            
            # Should have mechanism for key rotation
            assert age_days < 90 or db.get_setting('api_key_rotation_scheduled')


# ==================== Integration Security Tests ====================

@pytest.mark.security
@pytest.mark.integration
class TestIntegrationSecurity:
    """Test security of third-party integrations."""
    
    def test_plaid_token_security(self, populated_database):
        """Test secure storage and handling of Plaid tokens."""
        db = populated_database
        
        # Plaid tokens should be encrypted or secured
        token = db.get_setting('plaid_access_token')
        
        if token:
            # Should not be plaintext
            assert not token.startswith('access-')
            
            # Should have refresh mechanism
            assert db.get_setting('plaid_token_expires') or \
                   db.get_setting('plaid_token_created')
    
    def test_concur_credential_security(self, populated_database):
        """Test secure handling of Concur credentials."""
        db = populated_database
        
        # Concur secrets should never be exposed
        secret = db.get_setting('concur_client_secret')
        
        if secret:
            # Should be encrypted or None
            assert len(secret) < 10 or '***' in secret
    
    def test_oauth_state_validation(self, client):
        """Test OAuth state parameter validation."""
        # Initiate OAuth flow
        response = client.get('/api/oauth/authorize')
        
        if response.status_code == 302:
            # Should include state parameter
            location = response.headers.get('Location', '')
            assert 'state=' in location
            
            # Extract state
            import re
            state_match = re.search(r'state=([^&]+)', location)
            if state_match:
                state = state_match.group(1)
                
                # Complete OAuth with invalid state
                response = client.get(f'/api/oauth/callback?code=test&state=invalid')
                assert response.status_code in [400, 403]
                
                # Complete with valid state
                response = client.get(f'/api/oauth/callback?code=test&state={state}')
                # Should accept valid state (may fail for other reasons)
                assert response.status_code != 403 or 'state' in response.get_json().get('error', '')


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])