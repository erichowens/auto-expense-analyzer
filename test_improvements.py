#!/usr/bin/env python3
"""
Test script to verify the critical and important improvements work correctly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all new modules can be imported."""
    print("Testing imports...")
    
    try:
        from config import get_config, Config
        print("✅ Config module imports successfully")
        
        from api_response import APIResponse
        print("✅ API Response module imports successfully")
        
        from validators import TransactionInput, BulkProcessRequest, FridayPanicRequest
        print("✅ Validators module imports successfully")
        
        from database_pool import ConnectionPool, DatabaseManager
        print("✅ Database pool module imports successfully")
        
        from services import ExpenseProcessingService, TaskService, BusinessPurposeService
        print("✅ Services module imports successfully")
        
        from friday_panic_button import FridayPanicButton
        print("✅ Friday Panic Button imports successfully")
        
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def test_validation():
    """Test input validation with Pydantic."""
    print("\nTesting input validation...")
    
    from validators import TransactionInput, validate_request_data
    from pydantic import ValidationError
    
    # Test valid transaction
    valid_data = {
        'date': '2024-01-15',
        'description': 'Test transaction',
        'amount': 100.50,
        'location': 'San Francisco, CA'
    }
    
    is_valid, validated, error = validate_request_data(valid_data, TransactionInput)
    if is_valid:
        print("✅ Valid transaction accepted")
    else:
        print(f"❌ Valid transaction rejected: {error}")
        return False
    
    # Test invalid transaction (negative amount)
    invalid_data = {
        'date': '2024-01-15',
        'description': 'Test transaction',
        'amount': -100.50
    }
    
    is_valid, validated, error = validate_request_data(invalid_data, TransactionInput)
    if not is_valid and 'greater than 0' in error:
        print("✅ Invalid transaction correctly rejected (negative amount)")
    else:
        print(f"❌ Invalid transaction not properly validated")
        return False
    
    # Test SQL injection attempt
    malicious_data = {
        'date': '2024-01-15',
        'description': '<script>alert("XSS")</script>',
        'amount': 100.50
    }
    
    is_valid, validated, error = validate_request_data(malicious_data, TransactionInput)
    if is_valid and '<script>' not in validated.description:
        print("✅ HTML/Script tags properly sanitized")
    else:
        print(f"❌ Security validation failed")
        return False
    
    return True

def test_error_handling():
    """Test improved error handling."""
    print("\nTesting error handling...")
    
    from friday_panic_button import FridayPanicButton
    import logging
    
    # Set up logging to capture warnings
    logging.basicConfig(level=logging.WARNING)
    
    panic = FridayPanicButton()
    
    # Test with invalid date format
    transactions = [
        {'date': 'invalid-date', 'description': 'TEST', 'amount': 100}
    ]
    
    try:
        result = panic.panic_categorize(transactions)
        print("✅ Handled invalid date gracefully")
    except Exception as e:
        print(f"❌ Failed to handle invalid date: {e}")
        return False
    
    return True

def test_database_pool():
    """Test database connection pooling."""
    print("\nTesting database connection pooling...")
    
    from database_pool import ConnectionPool
    import tempfile
    import sqlite3
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        # Create pool
        pool = ConnectionPool(db_path, pool_size=2)
        
        # Test getting connections
        conn1 = pool.get_connection()
        conn2 = pool.get_connection()
        
        if conn1 and conn2:
            print("✅ Connection pool created successfully")
        
        # Test transaction context
        with pool.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            cursor.execute("INSERT INTO test VALUES (1)")
        
        # Verify transaction committed
        result = pool.execute("SELECT * FROM test", fetch='all')
        if result and len(result) == 1:
            print("✅ Transaction management works correctly")
        else:
            print("❌ Transaction not committed properly")
            return False
        
        # Clean up
        pool.return_connection(conn1)
        pool.return_connection(conn2)
        pool.close_all()
        
        return True
        
    except Exception as e:
        print(f"❌ Database pool test failed: {e}")
        return False
    finally:
        os.unlink(db_path)

def test_api_responses():
    """Test standardized API responses."""
    print("\nTesting API responses...")
    
    from api_response import APIResponse
    from flask import Flask
    import json
    
    # Create a test Flask app context
    app = Flask(__name__)
    
    with app.app_context():
        # Test success response
        response, status = APIResponse.success(data={'test': 'data'}, message='Success')
        response_data = json.loads(response.data)
        
        if response_data['status'] == 'success' and status == 200:
            print("✅ Success response formatted correctly")
        else:
            print("❌ Success response format incorrect")
            return False
        
        # Test error response
        response, status = APIResponse.error('Test error', status_code=400)
        response_data = json.loads(response.data)
        
        if response_data['status'] == 'error' and status == 400:
            print("✅ Error response formatted correctly")
        else:
            print("❌ Error response format incorrect")
            return False
        
        # Test validation error
        errors = {'field1': 'error1', 'field2': 'error2'}
        response, status = APIResponse.validation_error(errors)
        response_data = json.loads(response.data)
        
        if status == 422 and 'validation_errors' in response_data.get('details', {}):
            print("✅ Validation error response formatted correctly")
        else:
            print("❌ Validation error format incorrect")
            return False
    
    return True

def test_config():
    """Test configuration management."""
    print("\nTesting configuration...")
    
    from config import Config, get_config
    
    # Test default config
    config = get_config('development')
    
    if config.BATCH_SIZE == 100:
        print("✅ Default configuration loaded")
    else:
        print("❌ Configuration not loaded properly")
        return False
    
    # Test config validation
    try:
        config.validate()
        print("✅ Configuration validation passed")
    except ValueError as e:
        print(f"⚠️  Configuration validation warning: {e}")
    
    return True

def main():
    """Run all tests."""
    print("=" * 60)
    print("TESTING CRITICAL AND IMPORTANT IMPROVEMENTS")
    print("=" * 60)
    
    all_passed = True
    
    # Run tests
    tests = [
        ("Imports", test_imports),
        ("Input Validation", test_validation),
        ("Error Handling", test_error_handling),
        ("Database Pool", test_database_pool),
        ("API Responses", test_api_responses),
        ("Configuration", test_config)
    ]
    
    for test_name, test_func in tests:
        try:
            if not test_func():
                all_passed = False
                print(f"\n❌ {test_name} test failed")
        except Exception as e:
            all_passed = False
            print(f"\n❌ {test_name} test crashed: {e}")
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED - Improvements working correctly!")
    else:
        print("❌ Some tests failed - Please review the output above")
    print("=" * 60)
    
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())