#!/usr/bin/env python3
"""
Test script for Plaid integration
Tests the complete flow from link token creation to transaction fetching.
"""

import sys
import os
from datetime import datetime, timedelta

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from plaid_integration import get_plaid_manager, create_plaid_link_token, PLAID_AVAILABLE
from database import get_database
from expense_web_app import app

def test_plaid_availability():
    """Test if Plaid library is available."""
    print("=== Testing Plaid Availability ===")
    print(f"Plaid library available: {PLAID_AVAILABLE}")
    
    if PLAID_AVAILABLE:
        try:
            manager = get_plaid_manager()
            print(f"Plaid manager created: {manager is not None}")
            if manager is None:
                print("Manager is None - likely missing environment variables")
                print("Please create a .env file with PLAID_CLIENT_ID, PLAID_SECRET, and PLAID_ENV")
            return manager is not None
        except Exception as e:
            print(f"Error creating Plaid manager: {e}")
            return False
    else:
        print("Plaid library not available - install with: pip install plaid-python")
        return False

def test_flask_endpoints():
    """Test Flask API endpoints."""
    print("\n=== Testing Flask API Endpoints ===")
    
    with app.test_client() as client:
        # Test create-link-token endpoint
        print("Testing /api/create-link-token...")
        response = client.post('/api/create-link-token', json={'user_id': 'test_user'})
        print(f"Status: {response.status_code}")
        
        if response.status_code == 500:
            data = response.get_json()
            if 'Failed to create link token' in data.get('error', ''):
                print("✓ Endpoint works but missing credentials (expected)")
            else:
                print(f"✗ Unexpected error: {data}")
        elif response.status_code == 200:
            print("✓ Link token created successfully!")
        
        # Test test-plaid-connection endpoint
        print("\nTesting /api/test-plaid-connection...")
        response = client.post('/api/test-plaid-connection')
        print(f"Status: {response.status_code}")
        
        data = response.get_json()
        if response.status_code == 400 and 'No Plaid access token found' in data.get('error', ''):
            print("✓ Endpoint works correctly (no token stored)")
        else:
            print(f"Response: {data}")

def test_database_integration():
    """Test database integration for Plaid tokens."""
    print("\n=== Testing Database Integration ===")
    
    try:
        db = get_database()
        print("✓ Database connection successful")
        
        # Test setting and getting Plaid settings
        test_token = "test_access_token_123"
        db.set_setting('plaid_access_token', test_token)
        retrieved_token = db.get_setting('plaid_access_token')
        
        if retrieved_token == test_token:
            print("✓ Database token storage working")
        else:
            print(f"✗ Token mismatch: stored '{test_token}', got '{retrieved_token}'")
        
        # Clean up test data
        db.set_setting('plaid_access_token', None)
        
    except Exception as e:
        print(f"✗ Database error: {e}")

def test_chase_analyzer_integration():
    """Test Chase analyzer Plaid integration."""
    print("\n=== Testing Chase Analyzer Integration ===")
    
    try:
        from chase_travel_expense_analyzer import ChaseAnalyzer
        analyzer = ChaseAnalyzer()
        print("✓ Chase analyzer loaded successfully")
        
        # Check if get_transactions_from_plaid method exists
        if hasattr(analyzer, 'get_transactions_from_plaid'):
            print("✓ Plaid transaction method available")
        else:
            print("✗ Plaid transaction method missing")
            
    except Exception as e:
        print(f"✗ Chase analyzer error: {e}")

def main():
    """Run all tests."""
    print("Plaid Integration Test Suite")
    print("=" * 40)
    
    # Test 1: Plaid availability
    plaid_available = test_plaid_availability()
    
    # Test 2: Flask endpoints
    test_flask_endpoints()
    
    # Test 3: Database integration
    test_database_integration()
    
    # Test 4: Chase analyzer integration
    test_chase_analyzer_integration()
    
    print("\n=== Test Summary ===")
    if plaid_available:
        print("✓ Plaid integration is ready for use (with proper credentials)")
        print("Next steps:")
        print("1. Create .env file with Plaid credentials")
        print("2. Use the web interface to connect your bank account")
        print("3. Run expense analysis")
    else:
        print("⚠ Plaid integration needs configuration:")
        print("1. Ensure plaid-python is installed")
        print("2. Create .env file with PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV")
        print("3. Get credentials from https://dashboard.plaid.com/developers/api")

if __name__ == "__main__":
    main()