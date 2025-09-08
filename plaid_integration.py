#!/usr/bin/env python3
"""
Plaid Link OAuth Integration
Handles the complete Plaid Link flow including token exchange and transaction fetching.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

try:
    from plaid.api import plaid_api
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.model.transactions_get_request import TransactionsGetRequest
    from plaid.model.accounts_get_request import AccountsGetRequest
    from plaid.model.country_code import CountryCode
    from plaid.model.products import Products
    from plaid.configuration import Configuration
    from plaid.api_client import ApiClient
    from dotenv import load_dotenv
    PLAID_AVAILABLE = True
except ImportError:
    PLAID_AVAILABLE = False

# Import our enhanced security module
try:
    from plaid_security import plaid_security, secure_plaid_request
    SECURITY_ENABLED = True
except ImportError:
    SECURITY_ENABLED = False
    print("Warning: plaid_security module not available")

logger = logging.getLogger(__name__)

class PlaidLinkManager:
    """Manages Plaid Link integration with proper OAuth flow."""
    
    def __init__(self):
        if not PLAID_AVAILABLE:
            raise ImportError("Plaid Python library not available. Install with: pip install plaid-python")
        
        load_dotenv()
        
        self.client_id = os.getenv('PLAID_CLIENT_ID')
        self.secret = os.getenv('PLAID_SECRET')
        self.env = os.getenv('PLAID_ENV', 'sandbox')
        
        if not self.client_id or not self.secret:
            raise ValueError("Plaid credentials not found in environment variables")
        
        # Configure Plaid client
        configuration = Configuration(
            host=self._get_plaid_host(),
            api_key={
                'clientId': self.client_id,
                'secret': self.secret
            }
        )
        
        api_client = ApiClient(configuration)
        self.client = plaid_api.PlaidApi(api_client)
        
        logger.info(f"Plaid client initialized for {self.env} environment")

    def _get_plaid_host(self):
        """Get the appropriate Plaid host for the environment."""
        env_mapping = {
            'sandbox': plaid_api.Environment.sandbox,
            'development': plaid_api.Environment.development,
            'production': plaid_api.Environment.production
        }
        return env_mapping.get(self.env, plaid_api.Environment.sandbox)

    def create_link_token(self, user_id: str, webhook_url: Optional[str] = None) -> Dict:
        """Create a Link token for client-side Link initialization."""
        try:
            # Create Link token request
            request = LinkTokenCreateRequest(
                products=[Products('transactions')],
                client_name="Travel Expense Analyzer",
                country_codes=[CountryCode('US')],
                language='en',
                user=LinkTokenCreateRequestUser(client_user_id=user_id)
            )
            
            # Add webhook if provided
            if webhook_url:
                request.webhook = webhook_url
            
            # Add redirect URI for OAuth (if needed)
            # request.redirect_uri = "https://yourapp.com/oauth-redirect"
            
            response = self.client.link_token_create(request)
            
            return {
                'link_token': response['link_token'],
                'expiration': response['expiration'],
                'request_id': response['request_id']
            }
            
        except Exception as e:
            logger.error(f"Error creating link token: {e}")
            raise Exception(f"Failed to create link token: {str(e)}")

    def exchange_public_token(self, public_token: str, user_id: str = None) -> Dict:
        """Exchange a public token for an access token with secure storage."""
        try:
            request = ItemPublicTokenExchangeRequest(public_token=public_token)
            response = self.client.item_public_token_exchange(request)
            
            access_token = response['access_token']
            item_id = response['item_id']
            
            # Securely store the token if security module is available
            if SECURITY_ENABLED and user_id:
                stored = plaid_security.token_vault.store_token(
                    user_id=user_id,
                    access_token=access_token,
                    item_id=item_id
                )
                if stored:
                    logger.info(f"Token securely stored for user {user_id}")
                    # Audit the token exchange
                    plaid_security.audit_plaid_action(
                        'TOKEN_EXCHANGE',
                        user_id,
                        {'item_id': item_id, 'success': True}
                    )
            
            return {
                'access_token': access_token,
                'item_id': item_id,
                'request_id': response['request_id']
            }
            
        except Exception as e:
            logger.error(f"Error exchanging public token: {e}")
            if SECURITY_ENABLED and user_id:
                plaid_security.audit_plaid_action(
                    'TOKEN_EXCHANGE_FAILED',
                    user_id,
                    {'error': str(e)}
                )
            raise Exception(f"Failed to exchange public token: {str(e)}")

    def get_accounts(self, access_token: str) -> List[Dict]:
        """Get account information for a user."""
        try:
            request = AccountsGetRequest(access_token=access_token)
            response = self.client.accounts_get(request)
            
            accounts = []
            for account in response['accounts']:
                accounts.append({
                    'account_id': account['account_id'],
                    'name': account['name'],
                    'official_name': account.get('official_name'),
                    'type': account['type'].value,
                    'subtype': account['subtype'].value if account.get('subtype') else None,
                    'mask': account.get('mask'),
                    'balances': {
                        'available': account['balances'].get('available'),
                        'current': account['balances'].get('current'),
                        'limit': account['balances'].get('limit'),
                        'iso_currency_code': account['balances'].get('iso_currency_code')
                    }
                })
            
            return accounts
            
        except Exception as e:
            logger.error(f"Error getting accounts: {e}")
            raise Exception(f"Failed to get accounts: {str(e)}")

    def get_all_account_ids(self, access_token: str) -> List[str]:
        """Return all account IDs for the given access token."""
        try:
            accounts = self.get_accounts(access_token)
            return [a['account_id'] for a in accounts]
        except Exception as e:
            logger.error(f"Error getting all account IDs: {e}")
            return []

    def get_transactions(self, access_token: str, start_date: datetime, end_date: datetime, 
                        account_ids: Optional[List[str]] = None, count: int = 500) -> List[Dict]:
        """Get transactions for specified date range."""
        try:
            request = TransactionsGetRequest(
                access_token=access_token,
                start_date=start_date.date(),
                end_date=end_date.date(),
                count=count
            )
            
            if account_ids:
                request.account_ids = account_ids
            
            response = self.client.transactions_get(request)
            total_transactions = response['total_transactions']
            
            transactions = []
            
            # Get all transactions (may require multiple requests if > 500)
            while len(transactions) < total_transactions:
                if len(transactions) > 0:
                    # Make additional request for remaining transactions
                    request.offset = len(transactions)
                    response = self.client.transactions_get(request)
                
                for transaction in response['transactions']:
                    # Process transaction data
                    processed_transaction = self._process_transaction(transaction)
                    transactions.append(processed_transaction)
                
                # Break if we got fewer transactions than expected (end of data)
                if len(response['transactions']) < count:
                    break
            
            logger.info(f"Retrieved {len(transactions)} transactions")
            return transactions
            
        except Exception as e:
            logger.error(f"Error getting transactions: {e}")
            raise Exception(f"Failed to get transactions: {str(e)}")

    def _process_transaction(self, transaction) -> Dict:
        """Process a raw Plaid transaction into our format."""
        # Extract location information
        location_info = transaction.get('location', {})
        location_str = None
        
        if location_info:
            city = location_info.get('city')
            region = location_info.get('region')
            if city and region:
                location_str = f"{city}, {region}"
            elif region:
                location_str = region
        
        # Determine if transaction is in Oregon
        is_oregon = False
        oregon_indicators = ['OR', 'OREGON', 'PORTLAND', 'SALEM', 'EUGENE']
        
        if location_str:
            is_oregon = any(indicator in location_str.upper() for indicator in oregon_indicators)
        
        # Categorize transaction
        category = self._categorize_plaid_transaction(transaction)
        
        return {
            'transaction_id': transaction['transaction_id'],
            'account_id': transaction['account_id'],
            'date': transaction['date'].isoformat(),
            'description': transaction['name'],
            'amount': abs(transaction['amount']),  # Plaid uses negative for expenses
            'location': location_str,
            'category': category,
            'is_oregon': is_oregon,
            'merchant_name': transaction.get('merchant_name'),
            'account_owner': transaction.get('account_owner'),
            'iso_currency_code': transaction.get('iso_currency_code', 'USD'),
            'plaid_category': transaction.get('category', []),
            'original_description': transaction.get('original_description')
        }

    def _categorize_plaid_transaction(self, transaction) -> str:
        """Categorize a transaction based on Plaid data and merchant info."""
        # Get Plaid's category classification
        plaid_categories = transaction.get('category', [])
        merchant_name = transaction.get('merchant_name', '').upper()
        description = transaction.get('name', '').upper()
        
        # Hotel detection
        hotel_keywords = ['HOTEL', 'MOTEL', 'INN', 'RESORT', 'LODGING', 'MARRIOTT', 
                         'HILTON', 'HYATT', 'HOLIDAY INN', 'COMFORT', 'HAMPTON']
        if any(keyword in merchant_name or keyword in description for keyword in hotel_keywords):
            return 'HOTEL'
        
        # Airline detection
        airline_keywords = ['AIRLINE', 'AIRWAYS', 'DELTA', 'UNITED', 'AMERICAN', 
                           'SOUTHWEST', 'JETBLUE', 'ALASKA AIR']
        if any(keyword in merchant_name or keyword in description for keyword in airline_keywords):
            return 'AIRFARE'
        
        # Transportation detection
        transport_keywords = ['TAXI', 'UBER', 'LYFT', 'RENTAL', 'HERTZ', 'AVIS',
                             'ENTERPRISE', 'BUDGET', 'PARKING']
        if any(keyword in merchant_name or keyword in description for keyword in transport_keywords):
            return 'TRANSPORTATION'
        
        # Restaurant/meals detection using Plaid categories
        if any('Food and Drink' in cat or 'Restaurants' in cat for cat in plaid_categories):
            return 'MEALS'
        
        # Use Plaid categories for additional classification
        if any('Travel' in cat for cat in plaid_categories):
            if any('Lodging' in cat for cat in plaid_categories):
                return 'HOTEL'
            elif any('Transportation' in cat for cat in plaid_categories):
                return 'TRANSPORTATION'
            else:
                return 'OTHER'  # Travel-related but unclear type
        
        # Default to OTHER for manual review
        return 'OTHER'

    def get_credit_account_ids(self, access_token: str) -> List[str]:
        """Return account IDs for all credit card accounts across any institution.

        Uses Plaid account 'type' and 'subtype' to determine credit cards.
        """
        try:
            accounts = self.get_accounts(access_token)
            credit_ids: List[str] = []
            for account in accounts:
                acc_type = (account.get('type') or '').lower()
                acc_subtype = (account.get('subtype') or '').lower()
                if acc_type == 'credit' or 'credit' in acc_subtype:
                    credit_ids.append(account['account_id'])
            return credit_ids
        except Exception as e:
            logger.error(f"Error determining credit account IDs: {e}")
            return []

    def validate_access_token(self, access_token: str) -> bool:
        """Validate that an access token is still valid."""
        try:
            request = AccountsGetRequest(access_token=access_token)
            self.client.accounts_get(request)
            return True
        except Exception as e:
            logger.warning(f"Access token validation failed: {e}")
            return False

    def get_chase_account_ids(self, access_token: str, credit_only: bool = False) -> List[str]:
        """Get account IDs for Chase accounts specifically.

        Args:
            access_token: Plaid access token
            credit_only: If True, only include Chase credit card accounts
        """
        try:
            accounts = self.get_accounts(access_token)
            
            chase_account_ids = []
            for account in accounts:
                # Look for Chase in the account name or official name
                account_name = (account.get('name', '') + ' ' + 
                              account.get('official_name', '')).lower()
                
                if 'chase' in account_name:
                    if credit_only:
                        acc_type = (account.get('type') or '').lower()
                        acc_subtype = (account.get('subtype') or '').lower()
                        # Plaid credit cards typically have type 'credit' and/or subtype including 'credit'
                        if acc_type != 'credit' and 'credit' not in acc_subtype:
                            continue
                    chase_account_ids.append(account['account_id'])
            
            return chase_account_ids
            
        except Exception as e:
            logger.error(f"Error getting Chase account IDs: {e}")
            return []

# Global instance
plaid_manager = None

def get_plaid_manager() -> Optional[PlaidLinkManager]:
    """Get global Plaid manager instance."""
    global plaid_manager
    
    if not PLAID_AVAILABLE:
        return None
    
    if plaid_manager is None:
        try:
            plaid_manager = PlaidLinkManager()
        except Exception as e:
            logger.error(f"Failed to initialize Plaid manager: {e}")
            return None
    
    return plaid_manager

def create_plaid_link_token(user_id: str = "default_user") -> Optional[Dict]:
    """Create a Plaid Link token for frontend integration."""
    manager = get_plaid_manager()
    if not manager:
        return None
    
    try:
        return manager.create_link_token(user_id)
    except Exception as e:
        logger.error(f"Error creating link token: {e}")
        return None

def exchange_plaid_token(public_token: str) -> Optional[Dict]:
    """Exchange public token for access token."""
    manager = get_plaid_manager()
    if not manager:
        return None
    
    try:
        return manager.exchange_public_token(public_token)
    except Exception as e:
        logger.error(f"Error exchanging token: {e}")
        return None

def get_plaid_transactions(access_token: str, start_date: datetime, end_date: datetime, filter_mode: Optional[str] = "credit") -> Optional[List[Dict]]:
    """Get transactions from Plaid.

    If filter_mode is None or empty, reads PLAID_ACCOUNT_FILTER from environment.
    Accepts 'credit' (only credit card accounts) or 'all' (all accounts).
    Defaults to 'credit'.
    """
    manager = get_plaid_manager()
    if not manager:
        return None
    
    try:
        # Determine which accounts to include based on filter_mode or env
        account_ids: Optional[List[str]] = None
        if not filter_mode:
            filter_mode = os.getenv('PLAID_ACCOUNT_FILTER', 'credit').lower().strip()

        if filter_mode == "credit":
            account_ids = manager.get_credit_account_ids(access_token)
        elif filter_mode == "all":
            account_ids = manager.get_all_account_ids(access_token)
        else:
            # Fallback to credit if invalid value provided
            logger.warning(f"Unknown filter_mode '{filter_mode}', defaulting to 'credit'")
            account_ids = manager.get_credit_account_ids(access_token)

        # Fetch transactions for the selected accounts (if any found)
        return manager.get_transactions(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
            account_ids=account_ids if account_ids else None
        )
    except Exception as e:
        logger.error(f"Error getting transactions: {e}")
        return None

if __name__ == "__main__":
    # Test the Plaid integration
    if PLAID_AVAILABLE:
        try:
            manager = PlaidLinkManager()
            
            # Create a test link token
            link_token_response = manager.create_link_token("test_user")
            print(f"Link token created: {link_token_response['link_token'][:20]}...")
            
            print("Plaid integration test successful!")
            
        except Exception as e:
            print(f"Plaid integration test failed: {e}")
    else:
        print("Plaid library not available for testing")