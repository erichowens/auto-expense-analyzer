#!/usr/bin/env python3
"""
Chase Travel Expense Analyzer
Analyzes Chase statements to find travel expenses outside Oregon for Concur reporting.
Supports both CSV files and Plaid API integration.
"""

import csv
import re
import os
import json
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Optional
import argparse

try:
    from plaid.api import plaid_api
    from plaid.model.transactions_get_request import TransactionsGetRequest
    from plaid.model.accounts_get_request import AccountsGetRequest
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.configuration import Configuration
    from plaid.api_client import ApiClient
    from dotenv import load_dotenv
    PLAID_AVAILABLE = True
except ImportError:
    PLAID_AVAILABLE = False

# Import hotel folio retriever if available
try:
    from hotel_folio_retriever import HotelFolioRetriever, HotelStay
    FOLIO_RETRIEVER_AVAILABLE = True
except ImportError:
    FOLIO_RETRIEVER_AVAILABLE = False

# Import Concur API client if available
try:
    from concur_api_client import ConcurAPIClient, convert_trip_to_concur_report
    CONCUR_API_AVAILABLE = True
except ImportError:
    CONCUR_API_AVAILABLE = False

@dataclass
class Transaction:
    date: datetime
    description: str
    amount: float
    location: Optional[str] = None
    is_oregon: bool = True
    category: str = "Other"

class ChaseAnalyzer:
    def __init__(self):
        self.oregon_indicators = [
            'OR', 'OREGON', 'PORTLAND', 'SALEM', 'EUGENE', 'BEND', 
            'CORVALLIS', 'MEDFORD', 'SPRINGFIELD', 'GRESHAM', 'HILLSBORO',
            'BEAVERTON', 'TIGARD', 'LAKE OSWEGO', 'MILWAUKIE', 'TUALATIN'
        ]
        
        self.expense_categories = {
            'HOTEL': ['HOTEL', 'MOTEL', 'INN', 'RESORT', 'LODGING', 'MARRIOTT', 
                      'HILTON', 'HYATT', 'HOLIDAY INN', 'COMFORT', 'HAMPTON'],
            'AIRFARE': ['AIRLINE', 'AIRWAYS', 'DELTA', 'UNITED', 'AMERICAN', 
                        'SOUTHWEST', 'JETBLUE', 'ALASKA AIR', 'SPIRIT'],
            'MEALS': ['RESTAURANT', 'CAFE', 'COFFEE', 'STARBUCKS', 'MCDONALD',
                      'SUBWAY', 'PIZZA', 'DINER', 'GRILL', 'BISTRO', 'BAR'],
            'TRANSPORTATION': ['TAXI', 'UBER', 'LYFT', 'RENTAL', 'HERTZ', 'AVIS',
                               'ENTERPRISE', 'BUDGET', 'PARKING', 'GAS', 'FUEL'],
            'OTHER': []
        }
        
        self.plaid_client = None
        if PLAID_AVAILABLE:
            self._setup_plaid_client()

    def _setup_plaid_client(self):
        """Initialize Plaid client with credentials from environment."""
        load_dotenv()
        
        client_id = os.getenv('PLAID_CLIENT_ID')
        secret = os.getenv('PLAID_SECRET')
        env = os.getenv('PLAID_ENV', 'sandbox')
        
        if not client_id or not secret:
            print("Warning: Plaid credentials not found in environment variables.")
            return
        
        configuration = Configuration(
            host=getattr(plaid_api.Environment, env, plaid_api.Environment.sandbox),
            api_key={
                'clientId': client_id,
                'secret': secret
            }
        )
        api_client = ApiClient(configuration)
        self.plaid_client = plaid_api.PlaidApi(api_client)

    def get_transactions_from_plaid(self, access_token: str, start_date: datetime, end_date: datetime) -> List[Transaction]:
        """Fetch transactions from Plaid API."""
        if not self.plaid_client:
            raise Exception("Plaid client not initialized. Check your credentials.")
        
        transactions = []
        
        try:
            # Get accounts first to filter for Chase accounts
            accounts_request = AccountsGetRequest(access_token=access_token)
            accounts_response = self.plaid_client.accounts_get(accounts_request)
            
            chase_account_ids = []
            chase_account_names = os.getenv('CHASE_ACCOUNT_NAMES', '').split(',')
            
            for account in accounts_response['accounts']:
                if any(name.strip().lower() in account['name'].lower() for name in chase_account_names if name.strip()):
                    chase_account_ids.append(account['account_id'])
                elif 'chase' in account['name'].lower():
                    chase_account_ids.append(account['account_id'])
            
            # Fetch transactions
            request = TransactionsGetRequest(
                access_token=access_token,
                start_date=start_date.date(),
                end_date=end_date.date(),
                account_ids=chase_account_ids if chase_account_ids else None
            )
            
            response = self.plaid_client.transactions_get(request)
            
            for transaction in response['transactions']:
                # Only process expenses (positive amounts in Plaid = money out)
                if transaction['amount'] > 0:
                    date = datetime.strptime(transaction['date'], '%Y-%m-%d')
                    description = transaction['name']
                    location_info = transaction.get('location', {})
                    
                    # Extract location from Plaid's location data
                    location = None
                    if location_info:
                        city = location_info.get('city')
                        region = location_info.get('region')
                        if city and region:
                            location = f"{city} {region}"
                        elif region:
                            location = region
                    
                    is_oregon = self._is_oregon_transaction(description, location)
                    category = self._categorize_transaction(description)
                    
                    transaction_obj = Transaction(
                        date=date,
                        description=description,
                        amount=transaction['amount'],
                        location=location,
                        is_oregon=is_oregon,
                        category=category
                    )
                    transactions.append(transaction_obj)
            
            return sorted(transactions, key=lambda x: x.date)
            
        except Exception as e:
            raise Exception(f"Error fetching transactions from Plaid: {str(e)}")

    def exchange_public_token(self, public_token: str) -> str:
        """Exchange public token for access token."""
        if not self.plaid_client:
            raise Exception("Plaid client not initialized.")
        
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = self.plaid_client.item_public_token_exchange(request)
        return response['access_token']

    def parse_chase_csv(self, file_path: str) -> List[Transaction]:
        """Parse Chase CSV file and return list of transactions."""
        transactions = []
        
        with open(file_path, 'r', encoding='utf-8') as file:
            # Try to detect the CSV format
            sample = file.read(1024)
            file.seek(0)
            
            # Skip potential header rows
            reader = csv.reader(file)
            headers = next(reader)
            
            # Common Chase CSV formats
            if 'Transaction Date' in headers:
                date_idx = headers.index('Transaction Date')
                desc_idx = headers.index('Description')
                amount_idx = headers.index('Amount')
            elif 'Date' in headers:
                date_idx = headers.index('Date')
                desc_idx = headers.index('Description')
                amount_idx = headers.index('Amount')
            else:
                # Assume standard format: Date, Description, Amount
                date_idx, desc_idx, amount_idx = 0, 1, 2
            
            for row in reader:
                try:
                    date_str = row[date_idx]
                    description = row[desc_idx]
                    amount_str = row[amount_idx]
                    
                    # Parse date (handle MM/DD/YYYY format)
                    date = datetime.strptime(date_str, '%m/%d/%Y')
                    
                    # Parse amount (remove $ and commas, handle negatives)
                    amount = float(amount_str.replace('$', '').replace(',', ''))
                    
                    # Only process expenses (negative amounts)
                    if amount < 0:
                        amount = abs(amount)
                        location = self._extract_location(description)
                        is_oregon = self._is_oregon_transaction(description, location)
                        category = self._categorize_transaction(description)
                        
                        transaction = Transaction(
                            date=date,
                            description=description,
                            amount=amount,
                            location=location,
                            is_oregon=is_oregon,
                            category=category
                        )
                        transactions.append(transaction)
                        
                except (ValueError, IndexError) as e:
                    print(f"Skipping row due to parsing error: {row}")
                    continue
        
        return sorted(transactions, key=lambda x: x.date)

    def _extract_location(self, description: str) -> Optional[str]:
        """Extract location information from transaction description."""
        description_upper = description.upper()
        
        # Look for state abbreviations
        state_pattern = r'\b[A-Z]{2}\b'
        states = re.findall(state_pattern, description_upper)
        
        # Look for city names (common patterns)
        city_pattern = r'\b[A-Z][A-Z\s]+(?=\s+[A-Z]{2}\b)'
        cities = re.findall(city_pattern, description_upper)
        
        if states:
            location = states[-1]  # Take the last state found
            if cities:
                location = f"{cities[-1].strip()} {location}"
            return location
        
        return None

    def _is_oregon_transaction(self, description: str, location: str) -> bool:
        """Determine if transaction occurred in Oregon."""
        text_to_check = f"{description} {location or ''}".upper()
        
        for indicator in self.oregon_indicators:
            if indicator in text_to_check:
                return True
        
        return False

    def _categorize_transaction(self, description: str) -> str:
        """Categorize transaction based on description."""
        description_upper = description.upper()
        
        for category, keywords in self.expense_categories.items():
            if category == 'OTHER':
                continue
            for keyword in keywords:
                if keyword in description_upper:
                    return category
        
        return 'OTHER'

    def group_trips(self, transactions: List[Transaction], max_gap_days: int = 2) -> List[List[Transaction]]:
        """Group non-Oregon transactions into trips based on date proximity."""
        non_oregon_transactions = [t for t in transactions if not t.is_oregon]
        
        if not non_oregon_transactions:
            return []
        
        trips = []
        current_trip = [non_oregon_transactions[0]]
        
        for i in range(1, len(non_oregon_transactions)):
            current_transaction = non_oregon_transactions[i]
            last_transaction = current_trip[-1]
            
            # Check if transactions are within the gap threshold
            gap = (current_transaction.date - last_transaction.date).days
            
            if gap <= max_gap_days:
                current_trip.append(current_transaction)
            else:
                trips.append(current_trip)
                current_trip = [current_transaction]
        
        trips.append(current_trip)
        return trips

    def summarize_trips(self, trips: List[List[Transaction]], retrieve_folios: bool = False) -> List[Dict]:
        """Summarize each trip for Concur reporting."""
        trip_summaries = []
        
        # Initialize folio retriever if requested
        folio_retriever = None
        if retrieve_folios and FOLIO_RETRIEVER_AVAILABLE:
            folio_retriever = HotelFolioRetriever()
        
        for i, trip in enumerate(trips, 1):
            start_date = min(t.date for t in trip)
            end_date = max(t.date for t in trip)
            
            # Get primary location (most common non-Oregon location)
            locations = [t.location for t in trip if t.location and not t.is_oregon]
            primary_location = max(set(locations), key=locations.count) if locations else "Unknown"
            
            # Categorize expenses
            category_totals = defaultdict(float)
            for transaction in trip:
                category_totals[transaction.category] += transaction.amount
            
            total_amount = sum(t.amount for t in trip)
            
            # Find hotel stays and retrieve folios
            hotel_stays = []
            hotel_folios = []
            
            if folio_retriever:
                # Identify hotel transactions in this trip
                hotel_transactions = [t for t in trip if t.category == 'HOTEL']
                
                for hotel_transaction in hotel_transactions:
                    hotel_stay = HotelStay(
                        hotel_name=folio_retriever._extract_hotel_name(hotel_transaction.description),
                        check_in=hotel_transaction.date,
                        check_out=hotel_transaction.date + timedelta(days=1),
                        total_amount=hotel_transaction.amount,
                        chain=folio_retriever._identify_hotel_chain(
                            folio_retriever._extract_hotel_name(hotel_transaction.description)
                        ),
                        location=hotel_transaction.location
                    )
                    hotel_stays.append(hotel_stay)
            
            summary = {
                'trip_number': i,
                'start_date': start_date.strftime('%m/%d/%Y'),
                'end_date': end_date.strftime('%m/%d/%Y'),
                'duration_days': (end_date - start_date).days + 1,
                'primary_location': primary_location,
                'total_amount': total_amount,
                'category_breakdown': dict(category_totals),
                'transaction_count': len(trip),
                'transactions': trip,
                'hotel_stays': hotel_stays,
                'hotel_folios': hotel_folios
            }
            
            trip_summaries.append(summary)
        
        return trip_summaries

    def filter_by_date_range(self, transactions: List[Transaction], years: int = 2) -> List[Transaction]:
        """Filter transactions to last N years."""
        cutoff_date = datetime.now() - timedelta(days=365 * years)
        return [t for t in transactions if t.date >= cutoff_date]

def main():
    parser = argparse.ArgumentParser(description='Analyze Chase statements for travel expenses')
    parser.add_argument('--files', nargs='*', help='Chase CSV statement files')
    parser.add_argument('--plaid', action='store_true', help='Use Plaid API to fetch transactions')
    parser.add_argument('--access-token', help='Plaid access token (if you have one)')
    parser.add_argument('--public-token', help='Plaid public token (to exchange for access token)')
    parser.add_argument('--years', type=int, default=2, help='Number of years to analyze (default: 2)')
    parser.add_argument('--gap-days', type=int, default=2, help='Max days between transactions in same trip (default: 2)')
    parser.add_argument('--output', help='Output file for summary (optional)')
    parser.add_argument('--setup-plaid', action='store_true', help='Show Plaid setup instructions')
    parser.add_argument('--retrieve-folios', action='store_true', help='Attempt to retrieve hotel folios')
    parser.add_argument('--email-config', help='Email configuration file for folio retrieval')
    parser.add_argument('--hotel-credentials', help='Hotel website credentials file')
    parser.add_argument('--create-concur-reports', action='store_true', help='Create expense reports in Concur')
    parser.add_argument('--submit-to-concur', action='store_true', help='Submit created reports to Concur for approval')
    
    args = parser.parse_args()
    
    if args.setup_plaid:
        show_plaid_setup()
        return
    
    if not PLAID_AVAILABLE and args.plaid:
        print("Plaid integration not available. Install requirements: pip install -r requirements.txt")
        return
    
    analyzer = ChaseAnalyzer()
    all_transactions = []
    
    if args.plaid:
        # Use Plaid API
        access_token = args.access_token
        
        if args.public_token and not access_token:
            print("Exchanging public token for access token...")
            access_token = analyzer.exchange_public_token(args.public_token)
            print(f"Access token: {access_token}")
            print("Save this access token for future use with --access-token")
        
        if not access_token:
            print("Error: Need either --access-token or --public-token for Plaid integration")
            print("Run with --setup-plaid for setup instructions")
            return
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * args.years)
        
        print(f"Fetching transactions from Plaid for the last {args.years} years...")
        try:
            all_transactions = analyzer.get_transactions_from_plaid(access_token, start_date, end_date)
        except Exception as e:
            print(f"Error fetching from Plaid: {e}")
            return
    
    else:
        # Use CSV files
        if not args.files:
            print("Error: Need either CSV files or --plaid flag")
            return
        
        # Process all CSV files
        for file_path in args.files:
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                continue
            
            print(f"Processing {file_path}...")
            transactions = analyzer.parse_chase_csv(file_path)
            all_transactions.extend(transactions)
        
        # Filter by date range
        all_transactions = analyzer.filter_by_date_range(all_transactions, args.years)
    
    if not all_transactions:
        print("No transactions found.")
        return
    
    print(f"Found {len(all_transactions)} transactions in the last {args.years} years")
    
    # Group into trips
    trips = analyzer.group_trips(all_transactions, args.gap_days)
    print(f"Identified {len(trips)} potential trips")
    
    # Summarize trips
    trip_summaries = analyzer.summarize_trips(trips, retrieve_folios=args.retrieve_folios)
    
    # Create Concur expense reports if requested
    if args.create_concur_reports and CONCUR_API_AVAILABLE:
        print("Creating expense reports in Concur...")
        concur_client = ConcurAPIClient()
        
        created_reports = []
        for trip_summary in trip_summaries:
            try:
                concur_report = convert_trip_to_concur_report(trip_summary)
                report_id = concur_client.create_expense_report(concur_report)
                created_reports.append(report_id)
                print(f"✓ Created Concur report {report_id} for trip to {trip_summary['primary_location']}")
                
                # Submit for approval if requested
                if args.submit_to_concur:
                    if concur_client.submit_expense_report(report_id):
                        print(f"✓ Submitted report {report_id} for approval")
                    else:
                        print(f"✗ Failed to submit report {report_id}")
                        
            except Exception as e:
                print(f"✗ Failed to create Concur report for {trip_summary['primary_location']}: {e}")
        
        print(f"Created {len(created_reports)} expense reports in Concur")
    
    elif args.create_concur_reports and not CONCUR_API_AVAILABLE:
        print("Concur API integration not available. Check requirements.")
    
    # Generate text report
    report = generate_concur_report(trip_summaries)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report saved to {args.output}")
    else:
        print(report)

def show_plaid_setup():
    """Show instructions for setting up Plaid integration."""
    setup_text = """
PLAID SETUP INSTRUCTIONS
========================

1. Create a Plaid Developer Account:
   - Go to https://dashboard.plaid.com/signup
   - Sign up for a free developer account

2. Create a new Application:
   - In the dashboard, create a new app
   - Choose 'Transactions' as the product
   - Note your CLIENT_ID and SECRET

3. Set up Environment Variables:
   - Copy .env.example to .env
   - Fill in your Plaid credentials:
     PLAID_CLIENT_ID=your_client_id_here
     PLAID_SECRET=your_secret_here
     PLAID_ENV=sandbox  # Use 'sandbox' for testing

4. Install Dependencies:
   pip install -r requirements.txt

5. Get an Access Token:
   Option A - Use Plaid Link (recommended):
   - Implement Plaid Link in a web app to get a public_token
   - Use: python script.py --plaid --public-token YOUR_PUBLIC_TOKEN
   
   Option B - Use Sandbox (testing only):
   - Plaid provides test tokens in sandbox mode
   - Check Plaid documentation for sandbox access tokens

6. Run the Script:
   python chase_travel_expense_analyzer.py --plaid --access-token YOUR_ACCESS_TOKEN

For production use, you'll need to:
- Complete Plaid's verification process
- Switch PLAID_ENV to 'production'
- Implement proper OAuth flow for user consent

SECURITY NOTE: Never commit your .env file to version control!
"""
    print(setup_text)

def generate_concur_report(trip_summaries: List[Dict]) -> str:
    """Generate a formatted report for Concur expense reporting."""
    report = []
    report.append("TRAVEL EXPENSE SUMMARY FOR CONCUR REPORTING")
    report.append("=" * 50)
    report.append("")
    
    total_expenses = sum(trip['total_amount'] for trip in trip_summaries)
    report.append(f"Total Travel Expenses: ${total_expenses:,.2f}")
    report.append(f"Number of Trips: {len(trip_summaries)}")
    report.append("")
    
    for trip in trip_summaries:
        report.append(f"TRIP #{trip['trip_number']}")
        report.append("-" * 20)
        report.append(f"Dates: {trip['start_date']} - {trip['end_date']} ({trip['duration_days']} days)")
        report.append(f"Location: {trip['primary_location']}")
        report.append(f"Total Amount: ${trip['total_amount']:,.2f}")
        report.append("")
        
        report.append("Expense Breakdown:")
        for category, amount in trip['category_breakdown'].items():
            report.append(f"  {category}: ${amount:,.2f}")
        report.append("")
        
        report.append("Transactions:")
        for transaction in trip['transactions']:
            report.append(f"  {transaction.date.strftime('%m/%d/%Y')} - "
                         f"${transaction.amount:.2f} - {transaction.description}")
        report.append("")
        report.append("")
    
    return "\n".join(report)

if __name__ == "__main__":
    main()