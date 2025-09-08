#!/usr/bin/env python3
"""
SAP Concur API Integration
Direct expense report submission via Concur's REST API.
"""

import os
import json
import requests
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import base64
from urllib.parse import urlencode
import logging
from security_fixes import get_env_var, InputValidator

# Set up secure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Secure Concur API Configuration
CONCUR_CONFIG = {
    'BASE_URL': get_env_var('CONCUR_BASE_URL', 'https://us.api.concursolutions.com'),
    'CLIENT_ID': get_env_var('CONCUR_CLIENT_ID'),
    'CLIENT_SECRET': get_env_var('CONCUR_CLIENT_SECRET'),
    'REFRESH_TOKEN': get_env_var('CONCUR_REFRESH_TOKEN'),
    'COMPANY_ID': get_env_var('CONCUR_COMPANY_ID'),
    'OAUTH_URL': 'https://us.api.concursolutions.com/oauth2/v0/token',
    'EXPENSE_API_VERSION': 'v4.0',
    'RECEIPT_API_VERSION': 'v4.0',
    'REQUEST_TIMEOUT': 30  # Timeout for API requests
}


class ConcurAPIClient:
    """Client for interacting with SAP Concur APIs."""
    
    def __init__(self):
        self.base_url = CONCUR_CONFIG['BASE_URL']
        self.access_token = None
        self.token_expiry = None
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
    
    def authenticate(self) -> bool:
        """Authenticate with Concur using OAuth 2.0."""
        try:
            # Validate configuration
            if not all([CONCUR_CONFIG['CLIENT_ID'], CONCUR_CONFIG['CLIENT_SECRET'], 
                       CONCUR_CONFIG['REFRESH_TOKEN']]):
                logger.error("Missing Concur API credentials")
                return False
            
            # Use refresh token to get access token
            auth_data = {
                'grant_type': 'refresh_token',
                'refresh_token': CONCUR_CONFIG['REFRESH_TOKEN'],
                'client_id': CONCUR_CONFIG['CLIENT_ID'],
                'client_secret': CONCUR_CONFIG['CLIENT_SECRET']
            }
            
            response = requests.post(
                CONCUR_CONFIG['OAUTH_URL'],
                data=auth_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=CONCUR_CONFIG['REQUEST_TIMEOUT']
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                self.headers['Authorization'] = f"Bearer {self.access_token}"
                return True
            else:
                logger.error(f"Authentication failed: {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("Authentication request timed out")
            return False
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return False
    
    def create_expense_report(self, trip_data: Dict) -> Optional[str]:
        """
        Create a new expense report in Concur.
        
        Args:
            trip_data: Dictionary containing trip information
            
        Returns:
            Report ID if successful, None otherwise
        """
        if not self.access_token:
            if not self.authenticate():
                return None
        
        # Validate and prepare expense report data
        try:
            report_name = InputValidator.validate_string(
                trip_data.get('report_name', ''),
                max_length=100,
                name='report_name'
            )
            business_purpose = InputValidator.validate_string(
                trip_data.get('business_purpose', ''),
                max_length=500,
                name='business_purpose'
            )
            
            # Validate dates
            start_date = trip_data.get('start_date', '')
            end_date = trip_data.get('end_date', '')
            
            if not start_date or not end_date:
                logger.error("Missing required dates")
                return None
                
        except ValueError as e:
            logger.error(f"Validation error: {str(e)}")
            return None
        
        report_data = {
            'reportName': report_name,
            'reportDate': datetime.now().isoformat(),
            'purpose': business_purpose,
            'startDate': start_date,
            'endDate': end_date,
            'currencyCode': 'USD',
            'comment': "Auto-generated from Travel Expense Manager",
            'policy': {
                'id': CONCUR_CONFIG.get('POLICY_ID', 'DEFAULT')
            },
            'customData': {
                'trip_destination': InputValidator.validate_string(
                    trip_data.get('destination', ''), 
                    max_length=100
                ) if trip_data.get('destination') else None,
                'trip_duration': trip_data.get('duration_days')
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/expense/expensereport/{CONCUR_CONFIG['EXPENSE_API_VERSION']}/reports",
                json=report_data,
                headers=self.headers,
                timeout=CONCUR_CONFIG['REQUEST_TIMEOUT']
            )
            
            if response.status_code in [200, 201]:
                report = response.json()
                return report.get('reportID')
            else:
                logger.error(f"Failed to create report: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Create report request timed out")
            return None
        except Exception as e:
            logger.error(f"Error creating expense report: {str(e)}")
            return None
    
    def add_expense_entry(self, report_id: str, expense: Dict) -> Optional[str]:
        """
        Add an expense entry to an existing report.
        
        Args:
            report_id: The Concur report ID
            expense: Dictionary containing expense details
            
        Returns:
            Entry ID if successful, None otherwise
        """
        if not self.access_token:
            if not self.authenticate():
                return None
        
        # Map our categories to Concur expense types
        expense_type_mapping = {
            'AIRFARE': 'AIRFR',
            'HOTEL': 'LODNG',
            'MEALS': 'MEALS',
            'TRANSPORTATION': 'GROUND',
            'RENTAL_CAR': 'CARRT',
            'PARKING': 'PARKG',
            'OTHER': 'MISCL'
        }
        
        # Validate expense data
        try:
            amount = InputValidator.validate_amount(
                expense.get('amount', 0),
                min_val=0,
                max_val=1000000
            )
            vendor = InputValidator.validate_string(
                expense.get('vendor', 'Unknown'),
                max_length=100,
                name='vendor'
            )
            transaction_date = expense.get('date', '')
            
        except ValueError as e:
            logger.error(f"Expense validation error: {str(e)}")
            return None
        
        entry_data = {
            'reportID': report_id,
            'expenseTypeCode': expense_type_mapping.get(expense.get('category', 'OTHER'), 'MISCL'),
            'transactionDate': transaction_date,
            'transactionAmount': abs(amount),
            'currencyCode': expense.get('currency', 'USD')[:3],  # Ensure 3-char currency code
            'vendorDescription': vendor,
            'locationName': InputValidator.validate_string(
                expense.get('location', ''), 
                max_length=100
            ) if expense.get('location') else '',
            'businessPurpose': InputValidator.validate_string(
                expense.get('description', ''), 
                max_length=500
            ) if expense.get('description') else '',
            'isPersonal': False,
            'paymentTypeCode': 'CPAID',  # Company paid
            'receiptRequired': amount > 75  # Receipt required for expenses over $75
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/expense/expensereport/{CONCUR_CONFIG['EXPENSE_API_VERSION']}/reports/{report_id}/entries",
                json=entry_data,
                headers=self.headers,
                timeout=CONCUR_CONFIG['REQUEST_TIMEOUT']
            )
            
            if response.status_code in [200, 201]:
                entry = response.json()
                return entry.get('entryID')
            else:
                logger.error(f"Failed to add expense entry: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Add expense entry request timed out")
            return None
        except Exception as e:
            logger.error(f"Error adding expense entry: {str(e)}")
            return None
    
    def upload_receipt(self, entry_id: str, receipt_data: bytes, filename: str) -> bool:
        """
        Upload a receipt image to an expense entry.
        
        Args:
            entry_id: The expense entry ID
            receipt_data: Binary receipt image data
            filename: Receipt filename
            
        Returns:
            True if successful, False otherwise
        """
        if not self.access_token:
            if not self.authenticate():
                return False
        
        # Validate and sanitize filename
        try:
            safe_filename = InputValidator.sanitize_filename(filename)
        except Exception as e:
            logger.error(f"Invalid filename: {str(e)}")
            return False
            
        # Validate file size
        if len(receipt_data) > 10 * 1024 * 1024:  # 10MB limit
            logger.error("Receipt file too large (max 10MB)")
            return False
        
        # Prepare multipart form data
        files = {
            'receipt': (safe_filename, receipt_data, 'image/jpeg')
        }
        
        headers = self.headers.copy()
        headers.pop('Content-Type')  # Let requests set this for multipart
        
        try:
            response = requests.post(
                f"{self.base_url}/api/receipts/{CONCUR_CONFIG['RECEIPT_API_VERSION']}/entries/{entry_id}/receipts",
                files=files,
                headers=headers,
                timeout=CONCUR_CONFIG['REQUEST_TIMEOUT']
            )
            
            return response.status_code in [200, 201]
            
        except requests.exceptions.Timeout:
            logger.error("Upload receipt request timed out")
            return False
        except Exception as e:
            logger.error(f"Error uploading receipt: {str(e)}")
            return False
    
    def submit_report_for_approval(self, report_id: str) -> bool:
        """
        Submit an expense report for approval.
        
        Args:
            report_id: The Concur report ID
            
        Returns:
            True if successful, False otherwise
        """
        if not self.access_token:
            if not self.authenticate():
                return False
        
        try:
            response = requests.post(
                f"{self.base_url}/api/expense/expensereport/{CONCUR_CONFIG['EXPENSE_API_VERSION']}/reports/{report_id}/submit",
                headers=self.headers,
                timeout=CONCUR_CONFIG['REQUEST_TIMEOUT']
            )
            
            if response.status_code in [200, 202]:
                logger.info(f"Report {report_id} submitted for approval")
                return True
            else:
                logger.error(f"Failed to submit report: {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("Submit report request timed out")
            return False
        except Exception as e:
            logger.error(f"Error submitting report: {str(e)}")
            return False
    
    def get_report_status(self, report_id: str) -> Optional[Dict]:
        """
        Get the current status of an expense report.
        
        Args:
            report_id: The Concur report ID
            
        Returns:
            Report status dictionary if successful, None otherwise
        """
        if not self.access_token:
            if not self.authenticate():
                return None
        
        try:
            response = requests.get(
                f"{self.base_url}/api/expense/expensereport/{CONCUR_CONFIG['EXPENSE_API_VERSION']}/reports/{report_id}",
                headers=self.headers,
                timeout=CONCUR_CONFIG['REQUEST_TIMEOUT']
            )
            
            if response.status_code == 200:
                report = response.json()
                return {
                    'id': report.get('reportID'),
                    'name': report.get('reportName'),
                    'status': report.get('approvalStatus'),
                    'total': report.get('reportTotal'),
                    'submitted_date': report.get('submitDate'),
                    'approved_date': report.get('approvedDate')
                }
            else:
                logger.error(f"Failed to get report status: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Get report status request timed out")
            return None
        except Exception as e:
            logger.error(f"Error getting report status: {str(e)}")
            return None
    
    def process_complete_trip(self, trip: 'BusinessTrip') -> Optional[str]:
        """
        Process a complete trip by creating report and adding all expenses.
        
        Args:
            trip: BusinessTrip object containing all trip data
            
        Returns:
            Report ID if successful, None otherwise
        """
        # Create the expense report
        report_data = {
            'report_name': f"Business Trip to {trip.destination}",
            'business_purpose': trip.business_purpose,
            'start_date': trip.start_date.isoformat(),
            'end_date': trip.end_date.isoformat(),
            'destination': trip.destination,
            'duration_days': trip.duration_days
        }
        
        report_id = self.create_expense_report(report_data)
        if not report_id:
            logger.error("Failed to create expense report")
            return None
        
        logger.info(f"Created expense report: {report_id}")
        
        # Add each expense entry
        success_count = 0
        for transaction in trip.transactions:
            expense_data = {
                'date': transaction['date'].isoformat() if isinstance(transaction['date'], date) else transaction['date'],
                'vendor': transaction.get('name', 'Unknown'),
                'amount': abs(transaction['amount']),
                'category': self._categorize_transaction(transaction),
                'currency': transaction.get('iso_currency_code', 'USD'),
                'location': f"{transaction.get('location', {}).get('city', '')}, {transaction.get('location', {}).get('region', '')}",
                'description': transaction.get('merchant_name', '')
            }
            
            entry_id = self.add_expense_entry(report_id, expense_data)
            if entry_id:
                success_count += 1
                logger.info(f"Added expense entry: {entry_id}")
            else:
                logger.warning(f"Failed to add expense: {expense_data.get('vendor', 'Unknown')}")
        
        logger.info(f"Successfully added {success_count}/{len(trip.transactions)} expenses")
        
        # Submit for approval if all expenses added successfully
        if success_count == len(trip.transactions):
            if self.submit_report_for_approval(report_id):
                logger.info(f"Report {report_id} submitted for approval")
                return report_id
        
        return report_id
    
    def _categorize_transaction(self, transaction: Dict) -> str:
        """Categorize transaction for Concur."""
        name = transaction.get('name', '').upper()
        categories = transaction.get('category', [])
        
        if any('Airlines' in c for c in categories) or 'AIRLINE' in name:
            return 'AIRFARE'
        elif any('Lodging' in c for c in categories) or 'HOTEL' in name:
            return 'HOTEL'
        elif any('Food' in c for c in categories) or any(word in name for word in ['RESTAURANT', 'CAFE']):
            return 'MEALS'
        elif any('Car' in c for c in categories) or 'RENTAL' in name:
            return 'RENTAL_CAR'
        elif 'PARKING' in name:
            return 'PARKING'
        elif any(word in name for word in ['UBER', 'LYFT', 'TAXI']):
            return 'TRANSPORTATION'
        else:
            return 'OTHER'
    
    def get_user_profile(self) -> Optional[Dict]:
        """Get the current user's Concur profile."""
        if not self.access_token:
            if not self.authenticate():
                return None
        
        try:
            response = requests.get(
                f"{self.base_url}/api/user/v1.0/user",
                headers=self.headers,
                timeout=CONCUR_CONFIG['REQUEST_TIMEOUT']
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get user profile: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Get user profile request timed out")
            return None
        except Exception as e:
            logger.error(f"Error getting user profile: {str(e)}")
            return None
    
    def get_expense_policies(self) -> Optional[List[Dict]]:
        """Get available expense policies."""
        if not self.access_token:
            if not self.authenticate():
                return None
        
        try:
            response = requests.get(
                f"{self.base_url}/api/expense/expensereport/v2.0/policies",
                headers=self.headers,
                timeout=CONCUR_CONFIG['REQUEST_TIMEOUT']
            )
            
            if response.status_code == 200:
                return response.json().get('policies', [])
            else:
                logger.error(f"Failed to get policies: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Get policies request timed out")
            return None
        except Exception as e:
            logger.error(f"Error getting policies: {str(e)}")
            return None


# Quick submission function for Flask integration
def submit_trip_to_concur(trip_data: Dict) -> Dict:
    """
    Submit a complete trip to Concur.
    
    Args:
        trip_data: Dictionary containing trip and expense information
        
    Returns:
        Dictionary with success status and report ID
    """
    client = ConcurAPIClient()
    
    # Authenticate
    if not client.authenticate():
        return {
            'success': False,
            'error': 'Failed to authenticate with Concur'
        }
    
    # Create report
    report_id = client.create_expense_report(trip_data)
    if not report_id:
        return {
            'success': False,
            'error': 'Failed to create expense report'
        }
    
    # Add expenses
    expenses_added = 0
    for expense in trip_data.get('expenses', []):
        entry_id = client.add_expense_entry(report_id, expense)
        if entry_id:
            expenses_added += 1
    
    # Submit for approval
    submitted = False
    if expenses_added > 0:
        submitted = client.submit_report_for_approval(report_id)
    
    return {
        'success': True,
        'report_id': report_id,
        'expenses_added': expenses_added,
        'submitted': submitted,
        'concur_url': f"{CONCUR_CONFIG['BASE_URL']}/expense/report/{report_id}"
    }


if __name__ == '__main__':
    # Test Concur API connection
    print("Testing Concur API Integration")
    print("=" * 50)
    
    client = ConcurAPIClient()
    
    # Test authentication
    if client.authenticate():
        print("✅ Authentication successful")
        
        # Get user profile
        profile = client.get_user_profile()
        if profile:
            print(f"✅ User: {profile.get('LoginID', 'Unknown')}")
        
        # Get policies
        policies = client.get_expense_policies()
        if policies:
            print(f"✅ Found {len(policies)} expense policies")
    else:
        print("❌ Authentication failed - check your Concur credentials")
        print("\nRequired environment variables:")
        print("  CONCUR_CLIENT_ID")
        print("  CONCUR_CLIENT_SECRET")
        print("  CONCUR_REFRESH_TOKEN")
        print("  CONCUR_COMPANY_ID")