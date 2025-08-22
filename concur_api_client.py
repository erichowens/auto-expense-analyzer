#!/usr/bin/env python3
"""
SAP Concur API Client
Integrates with SAP Concur APIs to automatically create expense reports and upload receipts.
"""

import requests
import json
import base64
from datetime import datetime, date
from typing import List, Dict, Optional, Union
from dataclasses import dataclass, asdict
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

@dataclass
class ConcurExpenseEntry:
    expense_type: str  # e.g., "MEALS", "LODGING", "AIRFARE", "GROUND"
    transaction_date: date
    transaction_amount: float
    business_purpose: str
    vendor_name: str
    location: Optional[str] = None
    receipt_image_id: Optional[str] = None
    currency_code: str = "USD"
    payment_type: str = "CBCP"  # Company Card
    custom_fields: Optional[Dict] = None

@dataclass
class ConcurExpenseReport:
    report_name: str
    business_purpose: str
    expense_entries: List[ConcurExpenseEntry]
    user_id: Optional[str] = None
    policy_id: Optional[str] = None
    report_id: Optional[str] = None

class ConcurAPIClient:
    def __init__(self, base_url: str = None, client_id: str = None, client_secret: str = None):
        """Initialize Concur API client."""
        if DOTENV_AVAILABLE:
            load_dotenv()
        
        self.base_url = base_url or os.getenv('CONCUR_BASE_URL', 'https://us.api.concursolutions.com')
        self.client_id = client_id or os.getenv('CONCUR_CLIENT_ID')
        self.client_secret = client_secret or os.getenv('CONCUR_CLIENT_SECRET')
        self.refresh_token = os.getenv('CONCUR_REFRESH_TOKEN')
        
        self.access_token = None
        self.token_expires_at = None
        
        # API endpoints
        self.endpoints = {
            'oauth': '/oauth2/v0/token',
            'expense_reports_v4': '/expensereports/v4/users/{user_id}/context/{context_type}/reports',
            'expense_entries_v4': '/expense/expensereports/v4/reports/{report_id}/expenses',
            'quick_expense_v4': '/quickexpense/v4/users/{user_id}/context/{context_type}/quickexpenses',
            'receipts': '/receipts/v4/users/{user_id}',
            'spend_documents': '/spend-documents/v4',
            'users': '/profile/v1/me'
        }
        
        # Expense type mappings
        self.expense_type_mapping = {
            'HOTEL': 'LODGING',
            'AIRFARE': 'AIRFARE', 
            'MEALS': 'MEALS',
            'TRANSPORTATION': 'GROUND',
            'OTHER': 'MISCELLANEOUS'
        }

    def authenticate(self) -> bool:
        """Authenticate with Concur using refresh token."""
        if not self.client_id or not self.client_secret or not self.refresh_token:
            raise ValueError("Missing required authentication credentials")
        
        auth_url = f"{self.base_url}{self.endpoints['oauth']}"
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        try:
            response = requests.post(auth_url, headers=headers, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            expires_in = token_data.get('expires_in', 3600)
            
            # Calculate expiration time
            self.token_expires_at = datetime.now().timestamp() + expires_in
            
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"Authentication failed: {e}")
            return False

    def _ensure_authenticated(self):
        """Ensure we have a valid access token."""
        if not self.access_token or (
            self.token_expires_at and 
            datetime.now().timestamp() >= self.token_expires_at - 300  # Refresh 5 min early
        ):
            if not self.authenticate():
                raise Exception("Failed to authenticate with Concur")

    def _make_request(self, method: str, endpoint: str, data: Dict = None, files: Dict = None) -> requests.Response:
        """Make authenticated request to Concur API."""
        self._ensure_authenticated()
        
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json'
        }
        
        if data and not files:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(data)
        
        response = requests.request(method, url, headers=headers, data=data, files=files)
        
        if response.status_code == 401:
            # Token might be expired, try to refresh
            if self.authenticate():
                headers['Authorization'] = f'Bearer {self.access_token}'
                response = requests.request(method, url, headers=headers, data=data, files=files)
        
        return response

    def get_user_profile(self) -> Dict:
        """Get current user profile information."""
        response = self._make_request('GET', self.endpoints['users'])
        response.raise_for_status()
        return response.json()

    def create_expense_report(self, report: ConcurExpenseReport) -> str:
        """Create a new expense report and return report ID."""
        user_profile = self.get_user_profile()
        user_id = user_profile.get('id')
        
        if not user_id:
            raise Exception("Could not determine user ID")
        
        endpoint = self.endpoints['expense_reports_v4'].format(
            user_id=user_id, 
            context_type='TRAVELER'
        )
        
        report_data = {
            'name': report.report_name,
            'businessPurpose': report.business_purpose,
            'currencyCode': 'USD'
        }
        
        if report.policy_id:
            report_data['policyId'] = report.policy_id
        
        response = self._make_request('POST', endpoint, data=report_data)
        response.raise_for_status()
        
        result = response.json()
        report_id = result.get('reportId')
        
        if not report_id:
            raise Exception("Failed to create expense report")
        
        # Add expenses to the report
        for expense_entry in report.expense_entries:
            self.add_expense_to_report(report_id, expense_entry)
        
        return report_id

    def add_expense_to_report(self, report_id: str, expense: ConcurExpenseEntry) -> str:
        """Add an expense entry to an existing report."""
        endpoint = self.endpoints['expense_entries_v4'].format(report_id=report_id)
        
        expense_data = {
            'expenseTypeCode': self.expense_type_mapping.get(expense.expense_type, expense.expense_type),
            'transactionDate': expense.transaction_date.isoformat(),
            'transactionAmount': {
                'value': expense.transaction_amount,
                'currencyCode': expense.currency_code
            },
            'businessPurpose': expense.business_purpose,
            'vendor': {
                'name': expense.vendor_name
            },
            'paymentType': {
                'code': expense.payment_type
            }
        }
        
        if expense.location:
            expense_data['location'] = {
                'name': expense.location
            }
        
        if expense.receipt_image_id:
            expense_data['receiptImageId'] = expense.receipt_image_id
        
        if expense.custom_fields:
            expense_data['customData'] = expense.custom_fields
        
        response = self._make_request('POST', endpoint, data=expense_data)
        response.raise_for_status()
        
        result = response.json()
        return result.get('expenseId')

    def upload_receipt_image(self, user_id: str, image_path: str, expense_entry: ConcurExpenseEntry) -> str:
        """Upload a receipt image and return the image ID."""
        endpoint = self.endpoints['receipts'].format(user_id=user_id)
        
        with open(image_path, 'rb') as image_file:
            files = {
                'image': (os.path.basename(image_path), image_file, 'image/jpeg')
            }
            
            # Metadata about the receipt
            metadata = {
                'vendor': expense_entry.vendor_name,
                'transactionDate': expense_entry.transaction_date.isoformat(),
                'total': str(expense_entry.transaction_amount),
                'currencyCode': expense_entry.currency_code
            }
            
            data = {
                'metadata': json.dumps(metadata)
            }
            
            response = self._make_request('POST', endpoint, data=data, files=files)
            response.raise_for_status()
            
            result = response.json()
            return result.get('imageId')

    def upload_spend_document(self, file_path: str, document_type: str = 'RECEIPT') -> str:
        """Upload a spend document (like hotel folio) using Spend Documents v4 API."""
        endpoint = self.endpoints['spend_documents']
        
        with open(file_path, 'rb') as file:
            file_content = base64.b64encode(file.read()).decode('utf-8')
        
        document_data = {
            'documentType': document_type,
            'fileName': os.path.basename(file_path),
            'fileContent': file_content,
            'contentType': 'application/pdf' if file_path.endswith('.pdf') else 'image/jpeg'
        }
        
        response = self._make_request('POST', endpoint, data=document_data)
        response.raise_for_status()
        
        result = response.json()
        return result.get('documentId')

    def create_quick_expense(self, expense: ConcurExpenseEntry, user_id: str = None) -> str:
        """Create a quick expense entry."""
        if not user_id:
            user_profile = self.get_user_profile()
            user_id = user_profile.get('id')
        
        endpoint = self.endpoints['quick_expense_v4'].format(
            user_id=user_id,
            context_type='TRAVELER'
        )
        
        quick_expense_data = {
            'expenseTypeCode': self.expense_type_mapping.get(expense.expense_type, expense.expense_type),
            'transactionDate': expense.transaction_date.isoformat(),
            'transactionAmount': {
                'value': expense.transaction_amount,
                'currencyCode': expense.currency_code
            },
            'comment': expense.business_purpose,
            'vendor': expense.vendor_name
        }
        
        if expense.location:
            quick_expense_data['location'] = expense.location
        
        response = self._make_request('POST', endpoint, data=quick_expense_data)
        response.raise_for_status()
        
        result = response.json()
        return result.get('quickExpenseId')

    def submit_expense_report(self, report_id: str) -> bool:
        """Submit an expense report for approval."""
        # This would use the workflow API to submit the report
        # Implementation depends on company's specific workflow configuration
        endpoint = f"/expensereports/v4/reports/{report_id}/submit"
        
        try:
            response = self._make_request('POST', endpoint)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Failed to submit report: {e}")
            return False

def convert_trip_to_concur_report(trip_summary: Dict, folios_dir: str = None) -> ConcurExpenseReport:
    """Convert a trip summary from the expense analyzer to a Concur expense report."""
    
    # Create report name based on trip details
    report_name = f"Travel - {trip_summary['primary_location']} ({trip_summary['start_date']} - {trip_summary['end_date']})"
    
    business_purpose = f"Business travel to {trip_summary['primary_location']}"
    
    expense_entries = []
    
    # Convert transactions to Concur expense entries
    for transaction in trip_summary['transactions']:
        expense_type = transaction.category
        
        expense_entry = ConcurExpenseEntry(
            expense_type=expense_type,
            transaction_date=transaction.date.date(),
            transaction_amount=transaction.amount,
            business_purpose=business_purpose,
            vendor_name=transaction.description.split()[0],  # First word as vendor
            location=transaction.location,
            currency_code="USD"
        )
        
        expense_entries.append(expense_entry)
    
    return ConcurExpenseReport(
        report_name=report_name,
        business_purpose=business_purpose,
        expense_entries=expense_entries
    )

def main():
    """Test the Concur API client."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Concur API integration')
    parser.add_argument('--test-auth', action='store_true', help='Test authentication')
    parser.add_argument('--create-report', help='Trip summary JSON file to create report from')
    parser.add_argument('--upload-receipt', help='Receipt image path to upload')
    
    args = parser.parse_args()
    
    try:
        client = ConcurAPIClient()
        
        if args.test_auth:
            print("Testing Concur authentication...")
            if client.authenticate():
                print("✓ Authentication successful")
                
                user_profile = client.get_user_profile()
                print(f"✓ Connected as: {user_profile.get('firstName', '')} {user_profile.get('lastName', '')}")
            else:
                print("✗ Authentication failed")
        
        if args.create_report:
            print(f"Creating expense report from {args.create_report}...")
            # This would load trip summary and create report
            # Implementation depends on the specific data format
            pass
        
        if args.upload_receipt:
            print(f"Uploading receipt {args.upload_receipt}...")
            # This would upload a receipt image
            pass
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()