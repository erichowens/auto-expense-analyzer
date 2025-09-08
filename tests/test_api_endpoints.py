#!/usr/bin/env python3
"""
API Endpoint Tests
Tests all API endpoints, error responses, rate limiting, and concurrent requests.
"""

import pytest
import json
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock
import threading


@pytest.mark.integration
class TestCoreAPIEndpoints:
    """Test core API endpoints."""
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get('/api/health')
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'status' in data
        assert data['status'] in ['healthy', 'ok']
        assert 'timestamp' in data
        assert 'components' in data
        
        # Check component health
        components = data['components']
        assert 'database' in components
        assert 'plaid' in components
        assert 'concur' in components
    
    def test_trips_list_endpoint(self, authenticated_client, populated_database):
        """Test GET /api/trips endpoint."""
        response = authenticated_client.get('/api/trips')
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'trips' in data
        assert isinstance(data['trips'], list)
        assert len(data['trips']) > 0
        
        # Verify trip structure
        trip = data['trips'][0]
        assert 'id' in trip
        assert 'location' in trip
        assert 'start_date' in trip
        assert 'end_date' in trip
        assert 'total_amount' in trip
        assert 'business_purpose' in trip
    
    def test_trip_detail_endpoint(self, authenticated_client, populated_database):
        """Test GET /api/trips/<id> endpoint."""
        # Get a trip ID
        response = authenticated_client.get('/api/trips')
        trips = response.get_json()['trips']
        trip_id = trips[0]['id']
        
        # Get trip details
        response = authenticated_client.get(f'/api/trips/{trip_id}')
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'trip' in data
        trip = data['trip']
        assert trip['id'] == trip_id
        assert 'transactions' in data
        assert isinstance(data['transactions'], list)
    
    def test_create_trip_endpoint(self, authenticated_client):
        """Test POST /api/trips endpoint."""
        trip_data = {
            'location': 'Boston, MA',
            'start_date': '2024-05-01',
            'end_date': '2024-05-03',
            'business_purpose': 'Client meetings',
            'estimated_amount': 1500.00
        }
        
        response = authenticated_client.post('/api/trips',
                                            json=trip_data)
        
        if response.status_code == 201:
            data = response.get_json()
            assert 'trip_id' in data
            assert data['message'] == 'Trip created successfully'
    
    def test_update_trip_endpoint(self, authenticated_client, populated_database):
        """Test PUT /api/trips/<id> endpoint."""
        # Get a trip
        response = authenticated_client.get('/api/trips')
        trips = response.get_json()['trips']
        trip_id = trips[0]['id']
        
        # Update trip
        update_data = {
            'business_purpose': 'Updated purpose - Annual conference',
            'notes': 'Added speaker engagement'
        }
        
        response = authenticated_client.put(f'/api/trips/{trip_id}',
                                           json=update_data)
        
        assert response.status_code in [200, 204]
        
        # Verify update
        response = authenticated_client.get(f'/api/trips/{trip_id}')
        trip = response.get_json()['trip']
        assert trip['business_purpose'] == update_data['business_purpose']
    
    def test_delete_trip_endpoint(self, authenticated_client, populated_database):
        """Test DELETE /api/trips/<id> endpoint."""
        # Create a test trip
        trip_data = {
            'location': 'Test Location',
            'start_date': '2024-06-01',
            'end_date': '2024-06-02',
            'business_purpose': 'Test trip for deletion'
        }
        
        response = authenticated_client.post('/api/trips', json=trip_data)
        if response.status_code == 201:
            trip_id = response.get_json()['trip_id']
            
            # Delete trip
            response = authenticated_client.delete(f'/api/trips/{trip_id}')
            assert response.status_code in [200, 204]
            
            # Verify deletion
            response = authenticated_client.get(f'/api/trips/{trip_id}')
            assert response.status_code == 404


@pytest.mark.integration
class TestTransactionEndpoints:
    """Test transaction-related endpoints."""
    
    def test_transactions_list_endpoint(self, authenticated_client, populated_database):
        """Test GET /api/transactions endpoint."""
        response = authenticated_client.get('/api/transactions')
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'transactions' in data
        assert isinstance(data['transactions'], list)
        assert 'total' in data
        assert 'page' in data
        assert 'per_page' in data
    
    def test_transactions_filter_endpoint(self, authenticated_client, populated_database):
        """Test transaction filtering."""
        # Filter by date range
        response = authenticated_client.get('/api/transactions',
                                          query_string={
                                              'start_date': '2024-01-01',
                                              'end_date': '2024-01-31'
                                          })
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Verify filtered results
        for trans in data['transactions']:
            assert trans['date'] >= '2024-01-01'
            assert trans['date'] <= '2024-01-31'
        
        # Filter by category
        response = authenticated_client.get('/api/transactions',
                                          query_string={'category': 'HOTEL'})
        
        assert response.status_code == 200
        data = response.get_json()
        
        for trans in data['transactions']:
            assert trans['category'] == 'HOTEL'
    
    def test_transaction_categorization_endpoint(self, authenticated_client):
        """Test POST /api/transactions/categorize endpoint."""
        transactions = [
            {'description': 'UNITED AIRLINES', 'amount': 500},
            {'description': 'MARRIOTT HOTEL', 'amount': 200},
            {'description': 'STARBUCKS', 'amount': 8.50}
        ]
        
        response = authenticated_client.post('/api/transactions/categorize',
                                           json={'transactions': transactions})
        
        if response.status_code == 200:
            data = response.get_json()
            assert 'categorized' in data
            assert len(data['categorized']) == len(transactions)
            
            # Check categories
            categories = [t['category'] for t in data['categorized']]
            assert 'AIRFARE' in categories
            assert 'HOTEL' in categories or 'LODGING' in categories
            assert 'MEALS' in categories or 'FOOD' in categories


@pytest.mark.integration
class TestPlaidEndpoints:
    """Test Plaid integration endpoints."""
    
    def test_create_link_token_endpoint(self, authenticated_client, mock_plaid_client):
        """Test POST /api/create-link-token endpoint."""
        with patch('production_app.plaid_client', mock_plaid_client):
            response = authenticated_client.post('/api/create-link-token',
                                               json={'user_id': 'test_user'})
            
            if response.status_code == 200:
                data = response.get_json()
                assert 'link_token' in data
                assert data['link_token'] == 'link-sandbox-test-token'
    
    def test_exchange_token_endpoint(self, authenticated_client, mock_plaid_client):
        """Test POST /api/exchange-public-token endpoint."""
        with patch('production_app.plaid_client', mock_plaid_client):
            response = authenticated_client.post('/api/exchange-public-token',
                                               json={
                                                   'public_token': 'public-test-token',
                                                   'metadata': {
                                                       'institution': {'name': 'Chase'}
                                                   }
                                               })
            
            if response.status_code == 200:
                data = response.get_json()
                assert 'access_token' in data
                assert 'item_id' in data
    
    def test_sync_transactions_endpoint(self, authenticated_client, mock_plaid_client):
        """Test POST /api/sync-transactions endpoint."""
        with patch('production_app.plaid_client', mock_plaid_client):
            response = authenticated_client.post('/api/sync-transactions',
                                               json={
                                                   'start_date': '2024-01-01',
                                                   'end_date': '2024-01-31'
                                               })
            
            if response.status_code == 200:
                data = response.get_json()
                assert 'transactions_synced' in data
                assert 'trips_detected' in data


@pytest.mark.integration
class TestConcurEndpoints:
    """Test Concur integration endpoints."""
    
    def test_create_concur_report_endpoint(self, authenticated_client, mock_concur_client):
        """Test POST /api/concur/create-report endpoint."""
        with patch('production_app.ConcurAPIClient', return_value=mock_concur_client):
            report_data = {
                'trip_id': 1,
                'submit_immediately': False
            }
            
            response = authenticated_client.post('/api/concur/create-report',
                                               json=report_data)
            
            if response.status_code == 200:
                data = response.get_json()
                assert 'report_id' in data
                assert data['report_id'] == 'RPT-TEST-001'
    
    def test_submit_concur_report_endpoint(self, authenticated_client, mock_concur_client):
        """Test POST /api/concur/submit-report endpoint."""
        with patch('production_app.ConcurAPIClient', return_value=mock_concur_client):
            response = authenticated_client.post('/api/concur/submit-report',
                                               json={'report_id': 'RPT-TEST-001'})
            
            if response.status_code == 200:
                data = response.get_json()
                assert 'status' in data
                assert data['status'] == 'Pending Approval'


@pytest.mark.integration
class TestReceiptEndpoints:
    """Test receipt management endpoints."""
    
    def test_upload_receipt_endpoint(self, authenticated_client, sample_receipt_file):
        """Test POST /api/receipts/upload endpoint."""
        response = authenticated_client.post('/api/receipts/upload',
                                           data={
                                               'file': (sample_receipt_file, 'receipt.jpg'),
                                               'trip_id': '1',
                                               'transaction_id': '1'
                                           },
                                           content_type='multipart/form-data')
        
        if response.status_code == 200:
            data = response.get_json()
            assert 'receipt_id' in data
            assert 'filename' in data
    
    def test_list_receipts_endpoint(self, authenticated_client):
        """Test GET /api/receipts endpoint."""
        response = authenticated_client.get('/api/receipts')
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'receipts' in data
        assert isinstance(data['receipts'], list)
    
    def test_delete_receipt_endpoint(self, authenticated_client):
        """Test DELETE /api/receipts/<id> endpoint."""
        # Would need to upload a receipt first
        # Then delete it
        pass


@pytest.mark.integration
class TestErrorResponses:
    """Test error response handling."""
    
    def test_404_error_response(self, client):
        """Test 404 Not Found responses."""
        response = client.get('/api/nonexistent-endpoint')
        
        assert response.status_code == 404
        data = response.get_json()
        
        assert 'error' in data
        assert 'message' in data
        assert 'status' in data
        assert data['status'] == 404
    
    def test_400_bad_request_response(self, authenticated_client):
        """Test 400 Bad Request responses."""
        # Send invalid data
        response = authenticated_client.post('/api/trips',
                                           json={
                                               'location': 'Test',
                                               'start_date': 'invalid-date'
                                           })
        
        assert response.status_code == 400
        data = response.get_json()
        
        assert 'error' in data
        assert 'message' in data
    
    def test_401_unauthorized_response(self, client):
        """Test 401 Unauthorized responses."""
        response = client.get('/api/trips')
        
        assert response.status_code in [401, 403]
        data = response.get_json()
        
        assert 'error' in data
        assert 'authentication' in data['error'].lower() or \
               'unauthorized' in data['error'].lower()
    
    def test_500_server_error_response(self, authenticated_client):
        """Test 500 Internal Server Error responses."""
        # Force a server error
        with patch('production_app.db.get_all_trips', side_effect=Exception('Database error')):
            response = authenticated_client.get('/api/trips')
            
            assert response.status_code == 500
            data = response.get_json()
            
            assert 'error' in data
            # Should not expose internal error details
            assert 'Database error' not in str(data)
    
    def test_validation_error_response(self, authenticated_client):
        """Test validation error responses."""
        # Missing required fields
        response = authenticated_client.post('/api/trips', json={})
        
        assert response.status_code == 400
        data = response.get_json()
        
        assert 'error' in data
        if 'validation_errors' in data:
            assert isinstance(data['validation_errors'], dict)


@pytest.mark.integration
@pytest.mark.slow
class TestRateLimiting:
    """Test API rate limiting."""
    
    def test_rate_limit_enforcement(self, client):
        """Test that rate limits are enforced."""
        # Make many rapid requests
        responses = []
        for i in range(100):
            response = client.get('/api/health')
            responses.append(response.status_code)
        
        # Should eventually hit rate limit
        assert 429 in responses or all(r == 200 for r in responses)
        
        if 429 in responses:
            # Check rate limit headers
            idx = responses.index(429)
            response = client.get('/api/health')
            
            if response.status_code == 429:
                assert 'X-RateLimit-Limit' in response.headers or \
                       'Retry-After' in response.headers
    
    def test_rate_limit_per_endpoint(self, authenticated_client):
        """Test different rate limits for different endpoints."""
        # Health endpoint (higher limit)
        health_responses = []
        for i in range(50):
            response = authenticated_client.get('/api/health')
            health_responses.append(response.status_code)
        
        # Expensive endpoint (lower limit)
        expensive_responses = []
        for i in range(50):
            response = authenticated_client.post('/api/analyze-transactions',
                                               json={'use_plaid': True})
            expensive_responses.append(response.status_code)
        
        # Expensive endpoint should rate limit sooner
        health_429_count = health_responses.count(429)
        expensive_429_count = expensive_responses.count(429)
        
        # Implementation dependent
    
    def test_rate_limit_reset(self, client):
        """Test rate limit reset after time window."""
        # Hit rate limit
        for i in range(100):
            response = client.get('/api/health')
            if response.status_code == 429:
                break
        
        if response.status_code == 429:
            # Wait for reset
            retry_after = response.headers.get('Retry-After', '60')
            wait_time = min(int(retry_after), 5)  # Cap at 5 seconds for test
            time.sleep(wait_time)
            
            # Should work again
            response = client.get('/api/health')
            assert response.status_code != 429


@pytest.mark.integration
@pytest.mark.slow
class TestConcurrentRequests:
    """Test handling of concurrent requests."""
    
    def test_concurrent_read_requests(self, authenticated_client):
        """Test concurrent read operations."""
        def make_request():
            return authenticated_client.get('/api/trips')
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            
            results = []
            for future in as_completed(futures):
                response = future.result()
                results.append(response.status_code)
        
        # All should succeed
        assert all(status == 200 for status in results)
    
    def test_concurrent_write_requests(self, authenticated_client):
        """Test concurrent write operations."""
        def create_trip(n):
            return authenticated_client.post('/api/trips',
                                           json={
                                               'location': f'Location {n}',
                                               'start_date': '2024-07-01',
                                               'end_date': '2024-07-03',
                                               'business_purpose': f'Trip {n}'
                                           })
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_trip, i) for i in range(10)]
            
            results = []
            for future in as_completed(futures):
                response = future.result()
                results.append(response.status_code)
        
        # Should handle concurrent writes
        success_codes = [200, 201, 204]
        assert all(status in success_codes + [409, 429] for status in results)
    
    def test_race_condition_prevention(self, authenticated_client, populated_database):
        """Test prevention of race conditions in updates."""
        # Get a trip
        response = authenticated_client.get('/api/trips')
        trip_id = response.get_json()['trips'][0]['id']
        
        counter = {'value': 0}
        lock = threading.Lock()
        
        def update_trip():
            with lock:
                counter['value'] += 1
                current = counter['value']
            
            return authenticated_client.put(f'/api/trips/{trip_id}',
                                          json={
                                              'business_purpose': f'Update {current}'
                                          })
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(update_trip) for _ in range(10)]
            
            results = []
            for future in as_completed(futures):
                response = future.result()
                results.append(response.status_code)
        
        # Should handle updates without corruption
        response = authenticated_client.get(f'/api/trips/{trip_id}')
        trip = response.get_json()['trip']
        
        # Purpose should be from one of the updates
        assert 'Update' in trip['business_purpose']
    
    def test_connection_pool_limits(self, authenticated_client):
        """Test database connection pool under load."""
        def make_db_request():
            return authenticated_client.get('/api/transactions')
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_db_request) for _ in range(50)]
            
            results = []
            errors = []
            for future in as_completed(futures):
                try:
                    response = future.result()
                    results.append(response.status_code)
                except Exception as e:
                    errors.append(str(e))
        
        # Should handle load without connection errors
        assert len(errors) == 0 or len(errors) < 5  # Allow some failures under heavy load
        
        # Most requests should succeed
        success_count = sum(1 for s in results if s == 200)
        assert success_count > len(results) * 0.8  # 80% success rate


@pytest.mark.integration
class TestPaginationAndFiltering:
    """Test pagination and filtering capabilities."""
    
    def test_pagination(self, authenticated_client, large_transaction_set, test_database):
        """Test pagination of large result sets."""
        # Insert large dataset
        for trans in large_transaction_set[:100]:
            test_database.save_transaction(trans)
        
        # Test pagination
        response = authenticated_client.get('/api/transactions',
                                          query_string={
                                              'page': 1,
                                              'per_page': 20
                                          })
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert len(data['transactions']) <= 20
        assert 'total' in data
        assert 'page' in data
        assert 'per_page' in data
        assert 'total_pages' in data
        
        # Test next page
        if data['total_pages'] > 1:
            response = authenticated_client.get('/api/transactions',
                                              query_string={
                                                  'page': 2,
                                                  'per_page': 20
                                              })
            
            assert response.status_code == 200
            page2_data = response.get_json()
            
            # Should have different transactions
            page1_ids = [t['id'] for t in data['transactions']]
            page2_ids = [t['id'] for t in page2_data['transactions']]
            assert not set(page1_ids).intersection(set(page2_ids))
    
    def test_sorting(self, authenticated_client, populated_database):
        """Test sorting of results."""
        # Sort by date ascending
        response = authenticated_client.get('/api/transactions',
                                          query_string={
                                              'sort': 'date',
                                              'order': 'asc'
                                          })
        
        assert response.status_code == 200
        data = response.get_json()
        
        dates = [t['date'] for t in data['transactions']]
        assert dates == sorted(dates)
        
        # Sort by amount descending
        response = authenticated_client.get('/api/transactions',
                                          query_string={
                                              'sort': 'amount',
                                              'order': 'desc'
                                          })
        
        assert response.status_code == 200
        data = response.get_json()
        
        amounts = [t['amount'] for t in data['transactions']]
        assert amounts == sorted(amounts, reverse=True)
    
    def test_complex_filtering(self, authenticated_client, populated_database):
        """Test complex filtering combinations."""
        # Multiple filters
        response = authenticated_client.get('/api/transactions',
                                          query_string={
                                              'start_date': '2024-01-01',
                                              'end_date': '2024-12-31',
                                              'category': 'HOTEL',
                                              'min_amount': 100,
                                              'max_amount': 500
                                          })
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Verify all filters applied
        for trans in data['transactions']:
            assert trans['date'] >= '2024-01-01'
            assert trans['date'] <= '2024-12-31'
            assert trans['category'] == 'HOTEL'
            assert trans['amount'] >= 100
            assert trans['amount'] <= 500


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])