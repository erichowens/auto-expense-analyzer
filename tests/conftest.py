#!/usr/bin/env python3
"""
pytest configuration and fixtures for Travel Expense System
Provides test database, mock API responses, and test data factories.
"""

import pytest
import tempfile
import os
import json
import sqlite3
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, List, Any, Optional
from unittest.mock import MagicMock, patch, Mock
import secrets
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import application modules
from database import DatabaseManager, DatabaseTransaction, DatabaseTrip
from production_app import app as flask_app, UserSettings, TripRule
from concur_api_integration import ConcurAPIClient
from per_diem_tracker import PerDiemConfig, PerDiemAnalyzer
from plaid_integration import PlaidManager

# Test configuration
TEST_CONFIG = {
    'TESTING': True,
    'WTF_CSRF_ENABLED': False,
    'SECRET_KEY': secrets.token_hex(32),
    'SESSION_TYPE': 'filesystem',
    'PLAID_ENV': 'sandbox',
    'PLAID_CLIENT_ID': 'test_client_id',
    'PLAID_SECRET': 'test_secret',
    'CONCUR_CLIENT_ID': 'test_concur_client',
    'CONCUR_CLIENT_SECRET': 'test_concur_secret',
    'UPLOAD_FOLDER': tempfile.mkdtemp(),
    'MAX_CONTENT_LENGTH': 16 * 1024 * 1024  # 16MB max file size
}

# Test data constants
TEST_HOME_STATE = 'CA'
TEST_HOME_CITY = 'San Francisco'
TEST_USER_ID = 'test_user_001'


# ==================== Database Fixtures ====================

@pytest.fixture
def test_db_path():
    """Create a temporary database file path."""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_file.close()
    yield temp_file.name
    # Cleanup
    try:
        os.unlink(temp_file.name)
    except:
        pass


@pytest.fixture
def test_database(test_db_path):
    """Create a test database instance with schema."""
    db = DatabaseManager(test_db_path)
    return db


@pytest.fixture
def populated_database(test_database):
    """Create a database populated with test data."""
    db = test_database
    
    # Add test trips
    trips = [
        {
            'trip_number': 1,
            'primary_location': 'Seattle',
            'start_date': '2024-01-15',
            'end_date': '2024-01-18',
            'duration_days': 4,
            'total_amount': 1852.65,
            'business_purpose': 'Client meetings and product demo',
            'status': 'pending'
        },
        {
            'trip_number': 2,
            'primary_location': 'New York',
            'start_date': '2024-02-10',
            'end_date': '2024-02-12',
            'duration_days': 3,
            'total_amount': 1430.80,
            'business_purpose': 'Annual conference attendance',
            'status': 'submitted'
        }
    ]
    
    for trip in trips:
        db.save_trip(trip)
    
    # Add test transactions
    transactions = [
        # Seattle trip transactions
        {'date': '2024-01-15', 'description': 'DELTA AIR LINES', 'amount': 523.40, 
         'location': 'SEATTLE, WA', 'category': 'AIRFARE', 'trip_id': 1},
        {'date': '2024-01-15', 'description': 'HILTON SEATTLE', 'amount': 289.00,
         'location': 'SEATTLE, WA', 'category': 'HOTEL', 'trip_id': 1},
        {'date': '2024-01-16', 'description': 'STARBUCKS #4721', 'amount': 8.45,
         'location': 'SEATTLE, WA', 'category': 'MEALS', 'trip_id': 1},
        # New York trip transactions  
        {'date': '2024-02-10', 'description': 'UNITED AIRLINES', 'amount': 612.30,
         'location': 'NEW YORK, NY', 'category': 'AIRFARE', 'trip_id': 2},
        {'date': '2024-02-10', 'description': 'MARRIOTT TIMES SQUARE', 'amount': 359.00,
         'location': 'NEW YORK, NY', 'category': 'HOTEL', 'trip_id': 2},
    ]
    
    for trans in transactions:
        trans['is_oregon'] = 'OR' in trans.get('location', '')
        db.save_transaction(trans)
    
    # Add test settings
    settings = {
        'plaid_access_token': 'test_access_token',
        'plaid_item_id': 'test_item_id',
        'home_state': TEST_HOME_STATE,
        'home_city': TEST_HOME_CITY,
        'trip_detection_rule': TripRule.OUT_OF_STATE_2_DAYS.value,
        'per_diem_amount': 75.00
    }
    
    for key, value in settings.items():
        db.save_setting(key, value)
    
    return db


# ==================== Flask App Fixtures ====================

@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    flask_app.config.update(TEST_CONFIG)
    
    # Create test upload directory
    os.makedirs(TEST_CONFIG['UPLOAD_FOLDER'], exist_ok=True)
    
    with flask_app.app_context():
        yield flask_app
    
    # Cleanup
    import shutil
    shutil.rmtree(TEST_CONFIG['UPLOAD_FOLDER'], ignore_errors=True)


@pytest.fixture
def client(app):
    """Create a test client for the Flask application."""
    return app.test_client()


@pytest.fixture
def authenticated_client(client):
    """Create an authenticated test client with session."""
    with client.session_transaction() as sess:
        sess['user_id'] = TEST_USER_ID
        sess['authenticated'] = True
        sess['access_token'] = 'test_access_token'
    return client


# ==================== Mock API Response Fixtures ====================

@pytest.fixture
def mock_plaid_responses():
    """Mock responses from Plaid API."""
    return {
        'link_token': {
            'link_token': 'link-sandbox-test-token',
            'expiration': (datetime.now() + timedelta(hours=4)).isoformat()
        },
        'exchange_token': {
            'access_token': 'access-sandbox-test-token',
            'item_id': 'item-sandbox-test-id',
            'request_id': 'req-test-001'
        },
        'accounts': {
            'accounts': [
                {
                    'account_id': 'acc_test_001',
                    'name': 'Chase Sapphire Reserve',
                    'official_name': 'Chase Sapphire Reserve Card',
                    'type': 'credit',
                    'subtype': 'credit card',
                    'mask': '4242',
                    'balances': {
                        'available': 25000,
                        'current': 2500,
                        'limit': 27500
                    }
                }
            ]
        },
        'transactions': {
            'transactions': [
                {
                    'transaction_id': 'trans_001',
                    'account_id': 'acc_test_001',
                    'amount': 523.40,
                    'date': '2024-01-15',
                    'name': 'DELTA AIR LINES',
                    'merchant_name': 'Delta Airlines',
                    'category': ['Travel', 'Airlines and Aviation Services'],
                    'location': {
                        'city': 'Seattle',
                        'region': 'WA',
                        'country': 'US'
                    }
                },
                {
                    'transaction_id': 'trans_002',
                    'account_id': 'acc_test_001',
                    'amount': 289.00,
                    'date': '2024-01-15',
                    'name': 'HILTON SEATTLE',
                    'merchant_name': 'Hilton Hotels',
                    'category': ['Travel', 'Lodging'],
                    'location': {
                        'city': 'Seattle',
                        'region': 'WA',
                        'country': 'US'
                    }
                }
            ],
            'total_transactions': 2
        }
    }


@pytest.fixture
def mock_concur_responses():
    """Mock responses from Concur API."""
    return {
        'auth_token': {
            'access_token': 'concur-access-token-test',
            'refresh_token': 'concur-refresh-token-test',
            'expires_in': 3600,
            'scope': 'expense.report.readwrite receipts.write',
            'token_type': 'Bearer'
        },
        'create_report': {
            'id': 'RPT-TEST-001',
            'uri': 'https://api.concur.com/expense/v4/reports/RPT-TEST-001',
            'approvalStatus': 'Not Submitted',
            'approvedAmount': {'value': 0, 'currencyCode': 'USD'},
            'name': 'Seattle Business Trip - Jan 2024',
            'submitDate': None,
            'createdDate': datetime.now().isoformat()
        },
        'add_expense': {
            'id': 'EXP-TEST-001',
            'uri': 'https://api.concur.com/expense/v4/expenses/EXP-TEST-001',
            'reportId': 'RPT-TEST-001',
            'expenseType': {'id': 'AIRFR', 'name': 'Airfare'},
            'transactionAmount': {'value': 523.40, 'currencyCode': 'USD'},
            'transactionDate': '2024-01-15',
            'vendor': {'name': 'Delta Airlines'}
        },
        'submit_report': {
            'id': 'RPT-TEST-001',
            'approvalStatus': 'Pending Approval',
            'workflowActionUrl': 'https://www.concursolutions.com/expense/client/?reportId=RPT-TEST-001'
        },
        'upload_receipt': {
            'id': 'RCPT-TEST-001',
            'uri': 'https://api.concur.com/receipts/v4/RCPT-TEST-001',
            'status': 'UPLOADED',
            'dateTimeUploaded': datetime.now().isoformat()
        }
    }


@pytest.fixture
def mock_plaid_client(mock_plaid_responses):
    """Create a mock Plaid client."""
    client = MagicMock(spec=PlaidManager)
    
    # Mock methods
    client.create_link_token.return_value = mock_plaid_responses['link_token']
    client.exchange_public_token.return_value = mock_plaid_responses['exchange_token']
    client.get_accounts.return_value = mock_plaid_responses['accounts']['accounts']
    client.get_transactions.return_value = mock_plaid_responses['transactions']['transactions']
    client.validate_access_token.return_value = True
    
    return client


@pytest.fixture
def mock_concur_client(mock_concur_responses):
    """Create a mock Concur client."""
    client = MagicMock(spec=ConcurAPIClient)
    
    # Mock authentication
    client.authenticate.return_value = True
    client.access_token = mock_concur_responses['auth_token']['access_token']
    
    # Mock methods
    client.create_expense_report.return_value = mock_concur_responses['create_report']['id']
    client.add_expense_to_report.return_value = mock_concur_responses['add_expense']['id']
    client.submit_report.return_value = mock_concur_responses['submit_report']
    client.upload_receipt.return_value = mock_concur_responses['upload_receipt']['id']
    
    return client


# ==================== Test Data Factory Fixtures ====================

@pytest.fixture
def transaction_factory():
    """Factory for creating test transactions."""
    def create_transaction(**kwargs):
        base_date = kwargs.get('date', datetime.now().strftime('%Y-%m-%d'))
        defaults = {
            'date': base_date,
            'description': 'TEST MERCHANT',
            'amount': 100.00,
            'location': 'SAN FRANCISCO, CA',
            'category': 'MEALS',
            'is_oregon': False,
            'trip_id': None,
            'business_purpose': None
        }
        defaults.update(kwargs)
        return DatabaseTransaction(**defaults)
    return create_transaction


@pytest.fixture
def trip_factory():
    """Factory for creating test trips."""
    def create_trip(**kwargs):
        start_date = kwargs.get('start_date', datetime.now().strftime('%Y-%m-%d'))
        end_date = kwargs.get('end_date', (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'))
        defaults = {
            'id': None,
            'trip_number': 1,
            'primary_location': 'Seattle',
            'start_date': start_date,
            'end_date': end_date,
            'duration_days': 3,
            'total_amount': 1500.00,
            'business_purpose': 'Business meetings',
            'status': 'pending'
        }
        defaults.update(kwargs)
        return DatabaseTrip(**defaults)
    return create_trip


@pytest.fixture
def travel_transactions_factory():
    """Factory for creating sets of travel transactions."""
    def create_travel_set(destination='Seattle, WA', start_date=None, days=3):
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
        
        transactions = []
        
        # Day 1: Travel day
        transactions.append({
            'date': start_date.strftime('%Y-%m-%d'),
            'description': 'UNITED AIRLINES',
            'amount': 450.00 + (len(destination) * 10),  # Variable pricing
            'location': destination,
            'category': 'AIRFARE'
        })
        
        transactions.append({
            'date': start_date.strftime('%Y-%m-%d'),
            'description': f'MARRIOTT {destination.split(",")[0].upper()}',
            'amount': 189.00,
            'location': destination,
            'category': 'HOTEL'
        })
        
        # Subsequent days
        for day in range(1, days):
            current_date = (start_date + timedelta(days=day)).strftime('%Y-%m-%d')
            
            # Breakfast
            transactions.append({
                'date': current_date,
                'description': 'STARBUCKS',
                'amount': 8.45 + (day * 0.50),
                'location': destination,
                'category': 'MEALS',
                'time': '08:30'
            })
            
            # Lunch
            transactions.append({
                'date': current_date,
                'description': 'BUSINESS LUNCH',
                'amount': 25.00 + (day * 2),
                'location': destination,
                'category': 'MEALS',
                'time': '12:30'
            })
            
            # Hotel (if not last day)
            if day < days - 1:
                transactions.append({
                    'date': current_date,
                    'description': f'MARRIOTT {destination.split(",")[0].upper()}',
                    'amount': 189.00,
                    'location': destination,
                    'category': 'HOTEL'
                })
        
        return transactions
    
    return create_travel_set


# ==================== Authentication Helper Fixtures ====================

@pytest.fixture
def auth_headers():
    """Create authentication headers for API requests."""
    return {
        'Authorization': 'Bearer test_access_token',
        'Content-Type': 'application/json'
    }


@pytest.fixture
def mock_session():
    """Create a mock session with user data."""
    return {
        'user_id': TEST_USER_ID,
        'authenticated': True,
        'access_token': 'test_access_token',
        'home_state': TEST_HOME_STATE,
        'home_city': TEST_HOME_CITY,
        'trip_detection_rule': TripRule.OUT_OF_STATE_2_DAYS.value,
        'per_diem_amount': 75.00
    }


# ==================== File Upload Fixtures ====================

@pytest.fixture
def sample_receipt_file():
    """Create a sample receipt file for testing."""
    from io import BytesIO
    from PIL import Image
    import io
    
    # Create a simple test image
    img = Image.new('RGB', (100, 100), color='white')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    
    return img_bytes


@pytest.fixture
def sample_pdf_file():
    """Create a sample PDF file for testing."""
    from io import BytesIO
    import PyPDF2
    from PyPDF2 import PdfWriter, PageObject
    
    pdf_bytes = BytesIO()
    writer = PdfWriter()
    
    # Create a blank page
    page = PageObject.create_blank_page(width=612, height=792)
    writer.add_page(page)
    
    writer.write(pdf_bytes)
    pdf_bytes.seek(0)
    
    return pdf_bytes


# ==================== Security Testing Fixtures ====================

@pytest.fixture
def sql_injection_payloads():
    """Common SQL injection test payloads."""
    return [
        "' OR '1'='1",
        "'; DROP TABLE users--",
        "1' UNION SELECT * FROM users--",
        "admin'--",
        "' OR 1=1--",
        "1' AND '1'='1",
        "<script>alert('XSS')</script>",
        "../../etc/passwd",
        "%27%20OR%20%271%27%3D%271",
        "'; EXEC xp_cmdshell('dir')--"
    ]


@pytest.fixture
def xss_payloads():
    """Common XSS test payloads."""
    return [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "<svg onload=alert('XSS')>",
        "javascript:alert('XSS')",
        "<iframe src='javascript:alert(\"XSS\")'></iframe>",
        "<body onload=alert('XSS')>",
        "'><script>alert(String.fromCharCode(88,83,83))</script>",
        "<input type=\"text\" value=\"\" onclick=\"alert('XSS')\">",
        "<div style=\"background:url('javascript:alert(1)')\">",
        "<%2Fscript%3E%3Cscript%3Ealert%28%27XSS%27%29%3C%2Fscript%3E"
    ]


# ==================== Performance Testing Fixtures ====================

@pytest.fixture
def large_transaction_set():
    """Generate a large set of transactions for performance testing."""
    transactions = []
    base_date = datetime.now() - timedelta(days=365)
    
    for i in range(1000):
        date = base_date + timedelta(days=i % 365)
        transactions.append({
            'date': date.strftime('%Y-%m-%d'),
            'description': f'MERCHANT_{i % 50}',
            'amount': 10.00 + (i % 500),
            'location': f'CITY_{i % 20}, ST',
            'category': ['MEALS', 'HOTEL', 'AIRFARE', 'TRANSPORTATION'][i % 4]
        })
    
    return transactions


# ==================== Cleanup Fixtures ====================

@pytest.fixture(autouse=True)
def cleanup_test_files():
    """Automatically cleanup test files after each test."""
    test_files = []
    yield test_files
    
    # Cleanup any files added to the list
    for file_path in test_files:
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except:
            pass


# ==================== Test Markers ====================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "security: Security tests")
    config.addinivalue_line("markers", "performance: Performance tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "requires_api: Tests requiring external API access")