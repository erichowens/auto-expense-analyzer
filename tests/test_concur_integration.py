#!/usr/bin/env python3
"""
Concur Integration Tests
Tests Concur API client, report creation, expense submission, and error handling.
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock
import requests


@pytest.mark.integration
class TestConcurAPIClient:
    """Test Concur API client functionality."""
    
    def test_client_initialization(self):
        """Test Concur client initialization."""
        from concur_api_integration import ConcurAPIClient
        
        client = ConcurAPIClient()
        
        assert client.base_url is not None
        assert client.access_token is None
        assert client.headers['Accept'] == 'application/json'
        assert client.headers['Content-Type'] == 'application/json'
    
    def test_authentication_success(self, mock_concur_responses):
        """Test successful authentication with Concur."""
        from concur_api_integration import ConcurAPIClient
        
        client = ConcurAPIClient()
        
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_concur_responses['auth_token']
            mock_post.return_value = mock_response
            
            result = client.authenticate()
            
            assert result is True
            assert client.access_token == 'concur-access-token-test'
            assert 'Bearer concur-access-token-test' in client.headers['Authorization']
    
    def test_authentication_failure(self):
        """Test authentication failure handling."""
        from concur_api_integration import ConcurAPIClient
        
        client = ConcurAPIClient()
        
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.text = 'Invalid credentials'
            mock_post.return_value = mock_response
            
            result = client.authenticate()
            
            assert result is False
            assert client.access_token is None
    
    def test_token_refresh(self, mock_concur_responses):
        """Test access token refresh mechanism."""
        from concur_api_integration import ConcurAPIClient
        
        client = ConcurAPIClient()
        
        # Set expired token
        client.access_token = 'expired_token'
        client.token_expiry = datetime.now() - timedelta(hours=1)
        
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_concur_responses['auth_token']
            mock_post.return_value = mock_response
            
            # Should auto-refresh
            client.ensure_authenticated()
            
            assert client.access_token == 'concur-access-token-test'
    
    def test_request_retry_logic(self):
        """Test request retry logic on failures."""
        from concur_api_integration import ConcurAPIClient
        
        client = ConcurAPIClient()
        client.access_token = 'test_token'
        
        with patch('requests.get') as mock_get:
            # First call fails, second succeeds
            mock_get.side_effect = [
                Mock(status_code=503, text='Service unavailable'),
                Mock(status_code=200, json=lambda: {'data': 'success'})
            ]
            
            result = client.make_request('GET', '/test-endpoint', retry=True)
            
            assert result is not None
            assert mock_get.call_count == 2


@pytest.mark.integration
class TestExpenseReportCreation:
    """Test expense report creation in Concur."""
    
    def test_create_basic_report(self, mock_concur_client, populated_database):
        """Test creating a basic expense report."""
        from concur_api_integration import create_expense_report_from_trip
        
        # Get a trip from database
        trip = populated_database.get_all_trips()[0]
        
        with patch('concur_api_integration.ConcurAPIClient', return_value=mock_concur_client):
            report_id = create_expense_report_from_trip(trip)
            
            assert report_id == 'RPT-TEST-001'
            mock_concur_client.create_expense_report.assert_called_once()
    
    def test_create_report_with_expenses(self, mock_concur_client, populated_database):
        """Test creating report with multiple expenses."""
        from concur_api_integration import ConcurReportBuilder
        
        trip = populated_database.get_all_trips()[0]
        transactions = populated_database.get_trip_transactions(trip['id'])
        
        builder = ConcurReportBuilder(mock_concur_client)
        report_id = builder.create_report(trip, transactions)
        
        assert report_id == 'RPT-TEST-001'
        
        # Verify expenses were added
        for trans in transactions:
            mock_concur_client.add_expense_to_report.assert_any_call(
                report_id=report_id,
                expense_data=pytest.Any(dict)
            )
    
    def test_report_validation(self):
        """Test report data validation before submission."""
        from concur_api_integration import validate_report_data
        
        # Valid report data
        valid_data = {
            'reportName': 'Business Trip - Seattle',
            'purpose': 'Client meetings',
            'startDate': '2024-01-15',
            'endDate': '2024-01-18',
            'currencyCode': 'USD'
        }
        
        assert validate_report_data(valid_data) is True
        
        # Invalid data (missing required field)
        invalid_data = {
            'reportName': 'Business Trip',
            'startDate': '2024-01-15'
        }
        
        assert validate_report_data(invalid_data) is False
    
    def test_report_name_generation(self):
        """Test automatic report name generation."""
        from concur_api_integration import generate_report_name
        
        trip = {
            'primary_location': 'New York',
            'start_date': '2024-02-10',
            'end_date': '2024-02-12'
        }
        
        name = generate_report_name(trip)
        
        assert 'New York' in name
        assert 'Feb' in name or '02' in name
        assert len(name) <= 100  # Concur limit
    
    def test_multi_city_report(self):
        """Test creating report for multi-city trip."""
        from concur_api_integration import ConcurReportBuilder
        
        multi_city_trip = {
            'id': 1,
            'locations': ['Seattle, WA', 'Portland, OR', 'San Francisco, CA'],
            'start_date': '2024-01-15',
            'end_date': '2024-01-20',
            'business_purpose': 'West Coast client tour'
        }
        
        builder = ConcurReportBuilder(MagicMock())
        report_data = builder.prepare_report_data(multi_city_trip)
        
        assert 'Multi-City' in report_data['reportName'] or \
               all(city.split(',')[0] in report_data['reportName'] 
                   for city in multi_city_trip['locations'][:2])


@pytest.mark.integration
class TestExpenseSubmission:
    """Test expense submission to Concur."""
    
    def test_submit_airfare_expense(self, mock_concur_client):
        """Test submitting airfare expense."""
        from concur_api_integration import submit_expense
        
        expense_data = {
            'type': 'AIRFARE',
            'amount': 523.40,
            'date': '2024-01-15',
            'vendor': 'Delta Airlines',
            'description': 'SEA-SFO roundtrip',
            'location': 'Seattle, WA'
        }
        
        expense_id = submit_expense(mock_concur_client, 'RPT-001', expense_data)
        
        assert expense_id == 'EXP-TEST-001'
        mock_concur_client.add_expense_to_report.assert_called_once()
    
    def test_submit_hotel_expense(self, mock_concur_client):
        """Test submitting hotel expense with itemization."""
        from concur_api_integration import submit_hotel_expense
        
        hotel_data = {
            'vendor': 'Marriott Seattle',
            'check_in': '2024-01-15',
            'check_out': '2024-01-18',
            'room_rate': 189.00,
            'taxes': 28.35,
            'total': 585.35,
            'nights': 3
        }
        
        expense_id = submit_hotel_expense(mock_concur_client, 'RPT-001', hotel_data)
        
        assert expense_id is not None
        
        # Verify itemization
        call_args = mock_concur_client.add_expense_to_report.call_args
        expense_data = call_args[1]['expense_data']
        
        assert 'itemizations' in expense_data or 'room_rate' in expense_data
    
    def test_submit_meal_expense(self, mock_concur_client):
        """Test submitting meal expense."""
        from concur_api_integration import submit_meal_expense
        
        meal_data = {
            'vendor': 'Restaurant ABC',
            'amount': 45.60,
            'date': '2024-01-16',
            'meal_type': 'dinner',
            'attendees': ['John Doe', 'Jane Smith'],
            'business_purpose': 'Client dinner discussion'
        }
        
        expense_id = submit_meal_expense(mock_concur_client, 'RPT-001', meal_data)
        
        assert expense_id is not None
        
        # Verify attendee information
        call_args = mock_concur_client.add_expense_to_report.call_args
        expense_data = call_args[1]['expense_data']
        
        assert 'attendees' in expense_data or 'comment' in expense_data
    
    def test_submit_transportation_expense(self, mock_concur_client):
        """Test submitting ground transportation expense."""
        from concur_api_integration import submit_transportation_expense
        
        transport_data = {
            'type': 'UBER',
            'amount': 35.20,
            'date': '2024-01-16',
            'from_location': 'Airport',
            'to_location': 'Hotel',
            'distance': '15 miles'
        }
        
        expense_id = submit_transportation_expense(mock_concur_client, 'RPT-001', transport_data)
        
        assert expense_id is not None
    
    def test_expense_with_receipt(self, mock_concur_client, sample_receipt_file):
        """Test submitting expense with receipt attachment."""
        from concur_api_integration import submit_expense_with_receipt
        
        expense_data = {
            'type': 'MEALS',
            'amount': 52.30,
            'date': '2024-01-16',
            'vendor': 'Restaurant XYZ'
        }
        
        expense_id = submit_expense_with_receipt(
            mock_concur_client,
            'RPT-001',
            expense_data,
            sample_receipt_file
        )
        
        assert expense_id is not None
        
        # Verify receipt upload was called
        mock_concur_client.upload_receipt.assert_called_once()
    
    def test_bulk_expense_submission(self, mock_concur_client, populated_database):
        """Test submitting multiple expenses at once."""
        from concur_api_integration import submit_trip_expenses
        
        trip = populated_database.get_all_trips()[0]
        transactions = populated_database.get_trip_transactions(trip['id'])
        
        results = submit_trip_expenses(mock_concur_client, 'RPT-001', transactions)
        
        assert len(results) == len(transactions)
        assert all('expense_id' in r for r in results)
        assert mock_concur_client.add_expense_to_report.call_count == len(transactions)


@pytest.mark.integration
class TestReceiptHandling:
    """Test receipt upload and management."""
    
    def test_upload_image_receipt(self, mock_concur_client, sample_receipt_file):
        """Test uploading image receipt."""
        from concur_api_integration import upload_receipt
        
        receipt_id = upload_receipt(
            mock_concur_client,
            sample_receipt_file,
            'image/jpeg'
        )
        
        assert receipt_id == 'RCPT-TEST-001'
        mock_concur_client.upload_receipt.assert_called_once()
    
    def test_upload_pdf_receipt(self, mock_concur_client, sample_pdf_file):
        """Test uploading PDF receipt."""
        from concur_api_integration import upload_receipt
        
        receipt_id = upload_receipt(
            mock_concur_client,
            sample_pdf_file,
            'application/pdf'
        )
        
        assert receipt_id == 'RCPT-TEST-001'
    
    def test_link_receipt_to_expense(self, mock_concur_client):
        """Test linking receipt to expense."""
        from concur_api_integration import link_receipt_to_expense
        
        result = link_receipt_to_expense(
            mock_concur_client,
            'EXP-001',
            'RCPT-001'
        )
        
        assert result is True
        mock_concur_client.link_receipt.assert_called_once()
    
    def test_receipt_validation(self, sample_receipt_file):
        """Test receipt file validation."""
        from concur_api_integration import validate_receipt_file
        
        # Valid receipt
        is_valid, error = validate_receipt_file(sample_receipt_file)
        assert is_valid is True
        assert error is None
        
        # Invalid file (too large)
        large_file = b'x' * (10 * 1024 * 1024 + 1)  # > 10MB
        is_valid, error = validate_receipt_file(large_file)
        assert is_valid is False
        assert 'size' in error.lower()


@pytest.mark.integration
class TestReportSubmission:
    """Test report submission and approval workflow."""
    
    def test_submit_report_for_approval(self, mock_concur_client):
        """Test submitting report for approval."""
        from concur_api_integration import submit_report
        
        result = submit_report(mock_concur_client, 'RPT-001')
        
        assert result['approvalStatus'] == 'Pending Approval'
        assert 'workflowActionUrl' in result
        mock_concur_client.submit_report.assert_called_once()
    
    def test_validate_before_submission(self, mock_concur_client):
        """Test validation before report submission."""
        from concur_api_integration import validate_report_for_submission
        
        # Report with all required data
        mock_concur_client.get_report.return_value = {
            'id': 'RPT-001',
            'expenses': [
                {'id': 'EXP-001', 'amount': 100},
                {'id': 'EXP-002', 'amount': 200}
            ],
            'totalAmount': 300,
            'hasReceipts': True
        }
        
        is_valid, errors = validate_report_for_submission(mock_concur_client, 'RPT-001')
        
        assert is_valid is True
        assert len(errors) == 0
        
        # Report missing receipts
        mock_concur_client.get_report.return_value['hasReceipts'] = False
        
        is_valid, errors = validate_report_for_submission(mock_concur_client, 'RPT-001')
        
        assert is_valid is False or len(errors) > 0
    
    def test_recall_submitted_report(self, mock_concur_client):
        """Test recalling a submitted report."""
        from concur_api_integration import recall_report
        
        mock_concur_client.recall_report.return_value = {
            'id': 'RPT-001',
            'approvalStatus': 'Recalled'
        }
        
        result = recall_report(mock_concur_client, 'RPT-001')
        
        assert result['approvalStatus'] == 'Recalled'
    
    def test_get_report_status(self, mock_concur_client):
        """Test getting report approval status."""
        from concur_api_integration import get_report_status
        
        mock_concur_client.get_report.return_value = {
            'id': 'RPT-001',
            'approvalStatus': 'Approved',
            'approvedDate': '2024-01-20T10:00:00Z'
        }
        
        status = get_report_status(mock_concur_client, 'RPT-001')
        
        assert status['approvalStatus'] == 'Approved'
        assert 'approvedDate' in status


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling in Concur integration."""
    
    def test_handle_authentication_error(self):
        """Test handling of authentication errors."""
        from concur_api_integration import ConcurAPIClient
        
        client = ConcurAPIClient()
        
        with patch('requests.post') as mock_post:
            mock_post.side_effect = requests.ConnectionError('Network error')
            
            result = client.authenticate()
            
            assert result is False
    
    def test_handle_rate_limiting(self, mock_concur_client):
        """Test handling of Concur rate limits."""
        from concur_api_integration import handle_rate_limit
        
        # Simulate rate limit response
        rate_limit_response = {
            'error': 'Rate limit exceeded',
            'retry_after': 60
        }
        
        with patch('time.sleep') as mock_sleep:
            should_retry = handle_rate_limit(rate_limit_response)
            
            assert should_retry is True
            mock_sleep.assert_called_with(60)
    
    def test_handle_validation_errors(self):
        """Test handling of Concur validation errors."""
        from concur_api_integration import handle_validation_error
        
        validation_error = {
            'errors': [
                {'field': 'amount', 'message': 'Amount must be positive'},
                {'field': 'date', 'message': 'Date cannot be in future'}
            ]
        }
        
        formatted_errors = handle_validation_error(validation_error)
        
        assert len(formatted_errors) == 2
        assert any('amount' in e for e in formatted_errors)
        assert any('date' in e for e in formatted_errors)
    
    def test_handle_partial_success(self, mock_concur_client):
        """Test handling partial success in bulk operations."""
        from concur_api_integration import submit_expenses_batch
        
        expenses = [
            {'id': 1, 'amount': 100},
            {'id': 2, 'amount': -50},  # Invalid
            {'id': 3, 'amount': 200}
        ]
        
        # Mock partial success
        mock_concur_client.add_expense_to_report.side_effect = [
            {'id': 'EXP-001'},
            Exception('Invalid amount'),
            {'id': 'EXP-003'}
        ]
        
        results = submit_expenses_batch(mock_concur_client, 'RPT-001', expenses)
        
        assert results['successful'] == 2
        assert results['failed'] == 1
        assert len(results['errors']) == 1
    
    def test_connection_timeout_handling(self):
        """Test handling of connection timeouts."""
        from concur_api_integration import ConcurAPIClient
        
        client = ConcurAPIClient()
        
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.Timeout('Request timed out')
            
            result = client.make_request('GET', '/test-endpoint')
            
            assert result is None
    
    def test_invalid_response_handling(self):
        """Test handling of invalid API responses."""
        from concur_api_integration import parse_concur_response
        
        # Invalid JSON
        invalid_json = "not json"
        result = parse_concur_response(invalid_json)
        assert result is None
        
        # Missing required fields
        incomplete_response = {'id': 'RPT-001'}
        result = parse_concur_response(incomplete_response, required_fields=['id', 'status'])
        assert result is None or 'error' in result


@pytest.mark.integration
class TestConcurDataMapping:
    """Test data mapping between internal format and Concur format."""
    
    def test_transaction_to_expense_mapping(self):
        """Test mapping transaction to Concur expense format."""
        from concur_api_integration import map_transaction_to_expense
        
        transaction = {
            'date': '2024-01-15',
            'description': 'DELTA AIR LINES',
            'amount': 523.40,
            'location': 'Seattle, WA',
            'category': 'AIRFARE',
            'vendor_name': 'Delta Airlines'
        }
        
        expense = map_transaction_to_expense(transaction)
        
        assert expense['expenseType'] in ['AIRFR', 'AIRFARE']
        assert expense['transactionAmount']['value'] == 523.40
        assert expense['transactionDate'] == '2024-01-15'
        assert expense['vendor']['name'] == 'Delta Airlines'
    
    def test_category_mapping(self):
        """Test category mapping to Concur expense types."""
        from concur_api_integration import map_category_to_expense_type
        
        mappings = {
            'AIRFARE': 'AIRFR',
            'HOTEL': 'LODNG',
            'MEALS': 'MEALS',
            'TRANSPORTATION': 'GRTRN',
            'CAR RENTAL': 'CARRT',
            'PARKING': 'PARKN',
            'TOLLS': 'TOLLS'
        }
        
        for internal_cat, concur_type in mappings.items():
            result = map_category_to_expense_type(internal_cat)
            assert result == concur_type
    
    def test_location_parsing(self):
        """Test location parsing for Concur format."""
        from concur_api_integration import parse_location_for_concur
        
        locations = [
            ('Seattle, WA', {'city': 'Seattle', 'state': 'WA', 'country': 'US'}),
            ('London, UK', {'city': 'London', 'country': 'GB'}),
            ('Tokyo', {'city': 'Tokyo', 'country': 'JP'}),
        ]
        
        for input_loc, expected in locations:
            result = parse_location_for_concur(input_loc)
            assert result['city'] == expected['city']
            if 'state' in expected:
                assert result['state'] == expected['state']
            if 'country' in expected:
                assert result['country'] == expected['country']
    
    def test_currency_conversion(self):
        """Test currency handling for international expenses."""
        from concur_api_integration import convert_currency_for_concur
        
        # USD expense (no conversion)
        usd_expense = {'amount': 100.00, 'currency': 'USD'}
        result = convert_currency_for_concur(usd_expense)
        assert result['amount'] == 100.00
        assert result['currency'] == 'USD'
        
        # Foreign currency (needs exchange rate)
        eur_expense = {'amount': 100.00, 'currency': 'EUR'}
        result = convert_currency_for_concur(eur_expense, exchange_rate=1.1)
        assert result['amount'] == 110.00  # Converted to USD
        assert result['originalAmount'] == 100.00
        assert result['originalCurrency'] == 'EUR'


@pytest.mark.integration
@pytest.mark.slow
class TestConcurIntegrationE2E:
    """End-to-end Concur integration tests."""
    
    def test_complete_expense_workflow(self, mock_concur_client, populated_database):
        """Test complete workflow from trip to submitted report."""
        from concur_api_integration import process_trip_to_concur
        
        # Get trip and transactions
        trip = populated_database.get_all_trips()[0]
        transactions = populated_database.get_trip_transactions(trip['id'])
        
        # Process complete workflow
        result = process_trip_to_concur(
            mock_concur_client,
            trip,
            transactions,
            auto_submit=True
        )
        
        assert result['report_id'] == 'RPT-TEST-001'
        assert result['status'] == 'Pending Approval'
        assert result['total_expenses'] == len(transactions)
        assert result['total_amount'] > 0
    
    def test_multi_trip_processing(self, mock_concur_client, populated_database):
        """Test processing multiple trips to Concur."""
        from concur_api_integration import process_multiple_trips
        
        trips = populated_database.get_all_trips()
        
        results = process_multiple_trips(mock_concur_client, trips)
        
        assert len(results) == len(trips)
        assert all('report_id' in r for r in results)
        assert mock_concur_client.create_expense_report.call_count == len(trips)
    
    def test_retry_failed_submissions(self, mock_concur_client, populated_database):
        """Test retry mechanism for failed submissions."""
        from concur_api_integration import retry_failed_submissions
        
        # Simulate some failed submissions
        failed_submissions = [
            {'trip_id': 1, 'error': 'Network timeout'},
            {'trip_id': 2, 'error': 'Validation error'}
        ]
        
        # Store failed submissions
        for fail in failed_submissions:
            populated_database.save_failed_submission(fail)
        
        # Retry with fixed issues
        mock_concur_client.create_expense_report.return_value = 'RPT-RETRY-001'
        
        results = retry_failed_submissions(mock_concur_client, populated_database)
        
        assert results['retried'] == 2
        assert results['successful'] >= 0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])