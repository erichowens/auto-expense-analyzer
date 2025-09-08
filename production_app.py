#!/usr/bin/env python3
"""
Production Travel Expense Management System
Real OAuth, intelligent trip detection, and Concur-ready reporting.
"""

from flask import Flask, render_template_string, request, redirect, session, url_for, jsonify, flash, abort
from flask_session import Session
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, generate_csrf
from wtforms import StringField, FloatField, SelectField, HiddenField
from wtforms.validators import DataRequired, Length, NumberRange
import plaid
from plaid.api import plaid_api
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
import os
import json
import sqlite3
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
import secrets
from collections import defaultdict
import re
from dataclasses import dataclass, asdict
from enum import Enum

# Import security utilities
from security_fixes import (
    SecureDatabase, InputValidator, CSRFProtection, SessionManager,
    require_csrf, require_session, rate_limit, get_env_var,
    SecurityConfig, SQLQueryBuilder
)

# Initialize Flask app with security
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SECRET_KEY'] = get_env_var('SECRET_KEY') or secrets.token_hex(32)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True  # No JS access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = None  # No time limit for CSRF tokens

Session(app)
csrf = CSRFProtect(app)

# Secure Plaid Configuration
PLAID_CLIENT_ID = get_env_var('PLAID_CLIENT_ID')
PLAID_SECRET = get_env_var('PLAID_SECRET')
PLAID_ENV = get_env_var('PLAID_ENV', 'sandbox')
PLAID_PRODUCTS = [Products('transactions')]
PLAID_COUNTRY_CODES = [CountryCode('US')]

# Initialize Plaid client
plaid_env_mapping = {
    'sandbox': plaid.Environment.Sandbox,
    'development': plaid.Environment.Sandbox,  # Use sandbox for development
    'production': plaid.Environment.Production
}

configuration = plaid.Configuration(
    host=plaid_env_mapping.get(PLAID_ENV, plaid.Environment.Sandbox),
    api_key={
        'clientId': PLAID_CLIENT_ID,
        'secret': PLAID_SECRET,
    }
)
api_client = plaid.ApiClient(configuration)
plaid_client = plaid_api.PlaidApi(api_client)

# State codes mapping
US_STATES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
    'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia',
    'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa',
    'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri',
    'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey',
    'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio',
    'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont',
    'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming'
}


class TripRule(Enum):
    """Rules for detecting business trips."""
    OUT_OF_STATE_2_DAYS = "out_of_state_2_days"  # Out of state for 2+ consecutive days
    OUT_OF_STATE_3_DAYS = "out_of_state_3_days"  # Out of state for 3+ consecutive days
    AWAY_FROM_HOME_50_MILES = "away_50_miles"    # 50+ miles from home
    INTERNATIONAL = "international"               # Any international transaction
    CUSTOM = "custom"                             # Custom rule


@dataclass
class UserSettings:
    """User preferences and settings."""
    home_state: str
    home_city: Optional[str]
    trip_detection_rule: TripRule
    min_trip_days: int
    per_diem_amount: float
    selected_account_ids: List[str]
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data):
        data['trip_detection_rule'] = TripRule(data.get('trip_detection_rule', TripRule.OUT_OF_STATE_2_DAYS.value))
        return cls(**data)


@dataclass
class BusinessTrip:
    """Represents a business trip."""
    trip_id: str
    start_date: date
    end_date: date
    destination: str
    destination_state: str
    total_expenses: float
    expense_count: int
    categories: Dict[str, float]
    transactions: List[Dict]
    business_purpose: str
    
    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1
    
    def to_concur_format(self):
        """Convert to Concur expense report format."""
        return {
            'report_name': f"Business Trip to {self.destination}",
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'business_purpose': self.business_purpose,
            'total_amount': self.total_expenses,
            'expenses': self._format_expenses_for_concur()
        }
    
    def _format_expenses_for_concur(self):
        """Format expenses according to Concur requirements."""
        concur_expenses = []
        for transaction in self.transactions:
            concur_expenses.append({
                'date': transaction['date'],
                'vendor': transaction['name'],
                'amount': abs(transaction['amount']),
                'expense_type': self._map_to_concur_category(transaction['category']),
                'description': transaction.get('description', ''),
                'payment_type': 'Credit Card',
                'currency': transaction.get('iso_currency_code', 'USD')
            })
        return concur_expenses
    
    def _map_to_concur_category(self, plaid_category):
        """Map Plaid categories to Concur expense types."""
        mapping = {
            'Airlines': 'Airfare',
            'Lodging': 'Hotel',
            'Food and Drink': 'Meals',
            'Taxi': 'Ground Transportation',
            'Car Rental': 'Rental Car',
            'Gas Stations': 'Fuel',
            'Parking': 'Parking',
        }
        
        for key, value in mapping.items():
            if key in str(plaid_category):
                return value
        return 'Other'


class TripDetector:
    """Detects and groups business trips from transactions."""
    
    def __init__(self, settings: UserSettings):
        self.settings = settings
    
    def detect_trips(self, transactions: List[Dict]) -> List[BusinessTrip]:
        """Detect business trips from transactions."""
        # Filter out-of-state transactions
        out_of_state_transactions = self._filter_out_of_state(transactions)
        
        if not out_of_state_transactions:
            return []
        
        # Sort by date
        out_of_state_transactions.sort(key=lambda x: x['date'])
        
        # Group into trips based on rules
        trip_groups = self._group_into_trips(out_of_state_transactions)
        
        # Create BusinessTrip objects
        trips = []
        for group in trip_groups:
            trip = self._create_trip_from_group(group)
            if trip:
                trips.append(trip)
        
        return trips
    
    def _filter_out_of_state(self, transactions: List[Dict]) -> List[Dict]:
        """Filter transactions that are out of home state."""
        out_of_state = []
        
        for trans in transactions:
            location = trans.get('location', {})
            
            # Check state
            state = location.get('region')
            if state and state != self.settings.home_state:
                trans['detected_state'] = state
                out_of_state.append(trans)
            
            # Check merchant name for travel indicators
            elif self._is_travel_merchant(trans.get('name', '')):
                out_of_state.append(trans)
        
        return out_of_state
    
    def _is_travel_merchant(self, merchant_name: str) -> bool:
        """Check if merchant indicates travel."""
        travel_keywords = [
            'AIRLINE', 'AIRWAYS', 'DELTA', 'UNITED', 'AMERICAN', 'SOUTHWEST',
            'HOTEL', 'INN', 'MARRIOTT', 'HILTON', 'HYATT',
            'RENTAL', 'HERTZ', 'AVIS', 'ENTERPRISE',
            'AIRPORT', 'TSA'
        ]
        merchant_upper = merchant_name.upper()
        return any(keyword in merchant_upper for keyword in travel_keywords)
    
    def _group_into_trips(self, transactions: List[Dict]) -> List[List[Dict]]:
        """Group transactions into logical trips."""
        if not transactions:
            return []
        
        trips = []
        current_trip = [transactions[0]]
        
        for i in range(1, len(transactions)):
            current_date = transactions[i]['date']
            prev_date = transactions[i-1]['date']
            
            # Check if this transaction belongs to current trip
            days_gap = (current_date - prev_date).days
            
            if days_gap <= 2:  # Allow 2-day gap in trip
                current_trip.append(transactions[i])
            else:
                # Start new trip
                if self._is_valid_trip(current_trip):
                    trips.append(current_trip)
                current_trip = [transactions[i]]
        
        # Don't forget last trip
        if self._is_valid_trip(current_trip):
            trips.append(current_trip)
        
        return trips
    
    def _is_valid_trip(self, trip_transactions: List[Dict]) -> bool:
        """Check if group of transactions constitutes a valid trip."""
        if not trip_transactions:
            return False
        
        # Calculate trip duration
        start_date = min(t['date'] for t in trip_transactions)
        end_date = max(t['date'] for t in trip_transactions)
        duration = (end_date - start_date).days + 1
        
        # Apply trip detection rules
        if self.settings.trip_detection_rule == TripRule.OUT_OF_STATE_2_DAYS:
            return duration >= 2
        elif self.settings.trip_detection_rule == TripRule.OUT_OF_STATE_3_DAYS:
            return duration >= 3
        else:
            return duration >= self.settings.min_trip_days
    
    def _create_trip_from_group(self, transactions: List[Dict]) -> Optional[BusinessTrip]:
        """Create a BusinessTrip object from grouped transactions."""
        if not transactions:
            return None
        
        # Determine trip dates
        start_date = min(t['date'] for t in transactions)
        end_date = max(t['date'] for t in transactions)
        
        # Determine destination
        destinations = defaultdict(int)
        states = defaultdict(int)
        
        for trans in transactions:
            location = trans.get('location', {})
            city = location.get('city')
            state = trans.get('detected_state') or location.get('region')
            
            if city:
                destinations[city] += 1
            if state:
                states[state] += 1
        
        destination = max(destinations.items(), key=lambda x: x[1])[0] if destinations else 'Unknown'
        destination_state = max(states.items(), key=lambda x: x[1])[0] if states else 'Unknown'
        
        # Calculate expense categories
        categories = defaultdict(float)
        for trans in transactions:
            category = self._categorize_expense(trans)
            categories[category] += abs(trans['amount'])
        
        # Generate business purpose
        business_purpose = self._generate_business_purpose(destination, start_date, end_date, categories)
        
        return BusinessTrip(
            trip_id=f"TRIP_{start_date.isoformat()}_{destination[:3].upper()}",
            start_date=start_date,
            end_date=end_date,
            destination=destination,
            destination_state=destination_state,
            total_expenses=sum(abs(t['amount']) for t in transactions),
            expense_count=len(transactions),
            categories=dict(categories),
            transactions=transactions,
            business_purpose=business_purpose
        )
    
    def _categorize_expense(self, transaction: Dict) -> str:
        """Categorize expense for reporting."""
        categories = transaction.get('category', [])
        name = transaction.get('name', '').upper()
        
        # Priority categorization
        if any('Airlines' in c for c in categories) or 'AIRLINE' in name:
            return 'AIRFARE'
        elif any('Lodging' in c for c in categories) or 'HOTEL' in name:
            return 'HOTEL'
        elif any('Food' in c for c in categories) or any(word in name for word in ['RESTAURANT', 'CAFE', 'COFFEE']):
            return 'MEALS'
        elif any('Car' in c for c in categories) or any(word in name for word in ['UBER', 'LYFT', 'TAXI']):
            return 'TRANSPORTATION'
        else:
            return 'OTHER'
    
    def _generate_business_purpose(self, destination: str, start: date, end: date, categories: Dict) -> str:
        """Generate business purpose statement."""
        duration = (end - start).days + 1
        
        # Determine primary activity based on expenses
        if 'AIRFARE' in categories:
            activity = "client meetings"
        elif 'HOTEL' in categories and duration > 2:
            activity = "conference attendance"
        elif duration == 1:
            activity = "day trip for business meeting"
        else:
            activity = "business development"
        
        return f"Business trip to {destination} for {activity} from {start.strftime('%b %d')} to {end.strftime('%b %d, %Y')}."


# Database setup
def init_database():
    """Initialize database with proper schema."""
    with SecureDatabase('expense_tracker.db') as db:
    
        # User settings table with secure schema
        db.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                id INTEGER PRIMARY KEY,
                user_id TEXT UNIQUE NOT NULL,
                home_state TEXT NOT NULL,
                home_city TEXT,
                trip_detection_rule TEXT,
                min_trip_days INTEGER DEFAULT 2,
                per_diem_amount REAL DEFAULT 75.00,
                selected_account_ids TEXT,
                plaid_access_token TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
        # Trips table with user association
        db.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                trip_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                destination TEXT,
                destination_state TEXT,
                total_expenses REAL,
                expense_count INTEGER,
                business_purpose TEXT,
                concur_report_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
        # Transactions table with user association
        db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                trip_id TEXT,
                account_id TEXT,
                amount REAL NOT NULL,
                date DATE NOT NULL,
                name TEXT,
                merchant_name TEXT,
                category TEXT,
                location_city TEXT,
                location_state TEXT,
                iso_currency_code TEXT,
                pending BOOLEAN,
                FOREIGN KEY (trip_id) REFERENCES trips (trip_id)
            )
        """)
        
        # Create indexes for performance
        db.execute("CREATE INDEX IF NOT EXISTS idx_trips_user ON trips(user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)")


# Professional UI
PRODUCTION_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Travel Expense Management System</title>
    <link rel="stylesheet" href="/static/css/modern-ui.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f7fa;
            color: #2c3e50;
            line-height: 1.6;
        }
        
        .navbar {
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 1rem 0;
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .nav-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .logo {
            font-size: 1.5rem;
            font-weight: bold;
            color: #4a90e2;
        }
        
        .container {
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 20px;
        }
        
        .setup-wizard {
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.07);
            padding: 2rem;
            margin-bottom: 2rem;
        }
        
        .wizard-step {
            display: none;
        }
        
        .wizard-step.active {
            display: block;
        }
        
        .step-indicators {
            display: flex;
            justify-content: space-between;
            margin-bottom: 2rem;
            position: relative;
        }
        
        .step-indicators::before {
            content: '';
            position: absolute;
            top: 20px;
            left: 0;
            right: 0;
            height: 2px;
            background: #e0e0e0;
            z-index: -1;
        }
        
        .step-indicator {
            background: white;
            border: 2px solid #e0e0e0;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            color: #999;
        }
        
        .step-indicator.active {
            background: #4a90e2;
            border-color: #4a90e2;
            color: white;
        }
        
        .step-indicator.completed {
            background: #28a745;
            border-color: #28a745;
            color: white;
        }
        
        .form-group {
            margin-bottom: 1.5rem;
        }
        
        .form-label {
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 500;
            color: #495057;
        }
        
        .form-control {
            width: 100%;
            padding: 0.75rem;
            border: 1px solid #ced4da;
            border-radius: 6px;
            font-size: 1rem;
            transition: border-color 0.15s ease-in-out;
        }
        
        .form-control:focus {
            outline: none;
            border-color: #4a90e2;
            box-shadow: 0 0 0 3px rgba(74,144,226,0.1);
        }
        
        .form-select {
            appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23333' d='M6 9L1 4h10z'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 0.75rem center;
            background-size: 12px;
            padding-right: 2.5rem;
        }
        
        .btn {
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s ease-in-out;
            display: inline-block;
            text-align: center;
            text-decoration: none;
        }
        
        .btn-primary {
            background: #4a90e2;
            color: white;
        }
        
        .btn-primary:hover {
            background: #357abd;
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(74,144,226,0.25);
        }
        
        .btn-secondary {
            background: #6c757d;
            color: white;
            margin-right: 1rem;
        }
        
        .btn-success {
            background: #28a745;
            color: white;
        }
        
        .btn-plaid {
            background: #000;
            color: white;
            width: 100%;
            padding: 1rem;
            font-size: 1.1rem;
        }
        
        .btn-plaid:hover {
            background: #333;
        }
        
        .trip-card {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08);
            padding: 1.5rem;
            margin-bottom: 1rem;
            transition: all 0.2s ease;
        }
        
        .trip-card:hover {
            box-shadow: 0 4px 12px rgba(0,0,0,0.12);
            transform: translateY(-2px);
        }
        
        .trip-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }
        
        .trip-destination {
            font-size: 1.25rem;
            font-weight: 600;
            color: #2c3e50;
        }
        
        .trip-dates {
            color: #6c757d;
            font-size: 0.9rem;
        }
        
        .trip-amount {
            font-size: 1.5rem;
            font-weight: bold;
            color: #4a90e2;
        }
        
        .expense-categories {
            display: flex;
            gap: 1rem;
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid #e9ecef;
        }
        
        .category-pill {
            padding: 0.25rem 0.75rem;
            background: #f8f9fa;
            border-radius: 20px;
            font-size: 0.85rem;
            color: #495057;
        }
        
        .accounts-list {
            display: grid;
            gap: 1rem;
            margin-top: 1rem;
        }
        
        .account-item {
            padding: 1rem;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .account-item:hover {
            border-color: #4a90e2;
            background: #f8f9fa;
        }
        
        .account-item.selected {
            border-color: #4a90e2;
            background: #e7f3ff;
        }
        
        .account-name {
            font-weight: 600;
            margin-bottom: 0.25rem;
        }
        
        .account-details {
            color: #6c757d;
            font-size: 0.9rem;
        }
        
        .loading-spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(74,144,226,0.3);
            border-radius: 50%;
            border-top-color: #4a90e2;
            animation: spin 1s ease-in-out infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .alert {
            padding: 1rem;
            border-radius: 6px;
            margin-bottom: 1rem;
        }
        
        .alert-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .alert-info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        
        .alert-warning {
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
        }
        
        .date-range-selector {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        
        .stat-card {
            background: white;
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08);
        }
        
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: #4a90e2;
        }
        
        .stat-label {
            color: #6c757d;
            font-size: 0.9rem;
            margin-top: 0.25rem;
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="nav-container">
            <div class="logo">✈️ Travel Expense Manager</div>
            <div id="user-info"></div>
        </div>
    </nav>
    
    <div class="container">
        <!-- Setup Wizard -->
        <div class="setup-wizard" id="setup-wizard">
            <div class="step-indicators">
                <div class="step-indicator active" data-step="1">1</div>
                <div class="step-indicator" data-step="2">2</div>
                <div class="step-indicator" data-step="3">3</div>
                <div class="step-indicator" data-step="4">4</div>
            </div>
            
            <!-- Step 1: Plaid Connection -->
            <div class="wizard-step active" id="step-1">
                <h2>Connect Your Bank Account</h2>
                <p style="color: #6c757d; margin-bottom: 2rem;">
                    Securely connect your bank account to automatically import transactions.
                </p>
                
                <button class="btn btn-plaid" onclick="connectPlaid()">
                    Connect with Plaid
                </button>
                
                <div id="plaid-status" style="margin-top: 1rem;"></div>
            </div>
            
            <!-- Step 2: Account Selection -->
            <div class="wizard-step" id="step-2">
                <h2>Select Accounts to Track</h2>
                <p style="color: #6c757d; margin-bottom: 2rem;">
                    Choose which accounts contain your business expenses.
                </p>
                
                <div id="accounts-list" class="accounts-list"></div>
                
                <div style="margin-top: 2rem;">
                    <button class="btn btn-secondary" onclick="previousStep()">Back</button>
                    <button class="btn btn-primary" onclick="saveSelectedAccounts()">Continue</button>
                </div>
            </div>
            
            <!-- Step 3: Home Location & Rules -->
            <div class="wizard-step" id="step-3">
                <h2>Set Your Travel Rules</h2>
                
                <div class="form-group">
                    <label class="form-label">Home State</label>
                    <select class="form-control form-select" id="home-state">
                        <option value="">Select your home state...</option>
                        ${Object.entries(US_STATES).map(([code, name]) => 
                            `<option value="${code}">${name}</option>`
                        ).join('')}
                    </select>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Home City (Optional)</label>
                    <input type="text" class="form-control" id="home-city" placeholder="e.g., Portland">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Trip Detection Rule</label>
                    <select class="form-control form-select" id="trip-rule">
                        <option value="out_of_state_2_days">Out of state for 2+ consecutive days</option>
                        <option value="out_of_state_3_days">Out of state for 3+ consecutive days</option>
                        <option value="away_50_miles">50+ miles from home</option>
                        <option value="international">Any international transaction</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Daily Per Diem Amount</label>
                    <input type="number" class="form-control" id="per-diem" value="75" step="5">
                </div>
                
                <div style="margin-top: 2rem;">
                    <button class="btn btn-secondary" onclick="previousStep()">Back</button>
                    <button class="btn btn-primary" onclick="saveSettings()">Continue</button>
                </div>
            </div>
            
            <!-- Step 4: Date Range & Process -->
            <div class="wizard-step" id="step-4">
                <h2>Select Date Range to Analyze</h2>
                
                <div class="date-range-selector">
                    <div class="form-group">
                        <label class="form-label">Start Date</label>
                        <input type="date" class="form-control" id="start-date">
                    </div>
                    <div class="form-group">
                        <label class="form-label">End Date</label>
                        <input type="date" class="form-control" id="end-date">
                    </div>
                </div>
                
                <div style="margin-top: 2rem;">
                    <button class="btn btn-secondary" onclick="previousStep()">Back</button>
                    <button class="btn btn-success" onclick="processExpenses()" style="padding: 1rem 2rem; font-size: 1.1rem;">
                        🚀 Analyze Expenses
                    </button>
                </div>
                
                <div id="processing-status" style="margin-top: 2rem;"></div>
            </div>
        </div>
        
        <!-- Results Section -->
        <div id="results-section" style="display: none;">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" id="total-trips">0</div>
                    <div class="stat-label">Business Trips Found</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="total-expenses">$0</div>
                    <div class="stat-label">Total Expenses</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="avg-trip-cost">$0</div>
                    <div class="stat-label">Average Trip Cost</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="concur-ready">0</div>
                    <div class="stat-label">Concur Reports Ready</div>
                </div>
            </div>
            
            <h2 style="margin-bottom: 1rem;">Detected Business Trips</h2>
            <div id="trips-list"></div>
            
            <div style="margin-top: 2rem;">
                <button class="btn btn-success" onclick="exportToConcur()">
                    📊 Export All to Concur Format
                </button>
                <button class="btn btn-primary" onclick="startOver()" style="margin-left: 1rem;">
                    🔄 Start New Analysis
                </button>
            </div>
        </div>
        
        <div id="alerts"></div>
    </div>
    
    <!-- Plaid Link Script -->
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    
    <script>
        let currentStep = 1;
        let plaidHandler = null;
        let accessToken = null;
        let selectedAccounts = [];
        let userSettings = {};
        
        // Initialize date inputs
        document.getElementById('end-date').valueAsDate = new Date();
        const startDate = new Date();
        startDate.setMonth(startDate.getMonth() - 3);
        document.getElementById('start-date').valueAsDate = startDate;
        
        function nextStep() {
            if (currentStep < 4) {
                document.getElementById(`step-${currentStep}`).classList.remove('active');
                document.querySelector(`[data-step="${currentStep}"]`).classList.add('completed');
                currentStep++;
                document.getElementById(`step-${currentStep}`).classList.add('active');
                document.querySelector(`[data-step="${currentStep}"]`).classList.add('active');
            }
        }
        
        function previousStep() {
            if (currentStep > 1) {
                document.getElementById(`step-${currentStep}`).classList.remove('active');
                document.querySelector(`[data-step="${currentStep}"]`).classList.remove('active');
                currentStep--;
                document.getElementById(`step-${currentStep}`).classList.add('active');
            }
        }
        
        function connectPlaid() {
            showAlert('info', 'Connecting to Plaid...');
            
            fetch('/api/plaid/link-token', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            })
            .then(response => response.json())
            .then(data => {
                if (data.link_token) {
                    initializePlaidLink(data.link_token);
                } else {
                    showAlert('warning', 'Please configure Plaid credentials in .env file');
                }
            })
            .catch(error => {
                showAlert('danger', 'Error: ' + error.message);
            });
        }
        
        function initializePlaidLink(linkToken) {
            plaidHandler = Plaid.create({
                token: linkToken,
                onSuccess: (public_token, metadata) => {
                    exchangePublicToken(public_token, metadata);
                },
                onLoad: () => {
                    console.log('Plaid Link loaded');
                },
                onExit: (err, metadata) => {
                    if (err) {
                        showAlert('warning', 'Plaid connection cancelled');
                    }
                },
                onEvent: (eventName, metadata) => {
                    console.log('Plaid event:', eventName);
                }
            });
            
            plaidHandler.open();
        }
        
        function exchangePublicToken(publicToken, metadata) {
            fetch('/api/plaid/exchange-token', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    public_token: publicToken,
                    institution: metadata.institution
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    accessToken = data.access_token;
                    showAlert('success', 'Bank account connected successfully!');
                    document.getElementById('plaid-status').innerHTML = 
                        '<div class="alert alert-success">✓ Connected to ' + 
                        metadata.institution.name + '</div>';
                    
                    // Load accounts
                    loadAccounts();
                    
                    // Auto advance to next step
                    setTimeout(() => nextStep(), 1500);
                }
            })
            .catch(error => {
                showAlert('danger', 'Error exchanging token: ' + error.message);
            });
        }
        
        function loadAccounts() {
            fetch('/api/plaid/accounts')
                .then(response => response.json())
                .then(data => {
                    if (data.accounts) {
                        displayAccounts(data.accounts);
                    }
                })
                .catch(error => {
                    console.error('Error loading accounts:', error);
                });
        }
        
        function displayAccounts(accounts) {
            const container = document.getElementById('accounts-list');
            container.innerHTML = accounts.map(account => `
                <div class="account-item" onclick="toggleAccount('${account.account_id}')">
                    <div class="account-name">${account.name}</div>
                    <div class="account-details">
                        ${account.subtype} • $${account.balances.current.toFixed(2)}
                    </div>
                    <input type="checkbox" id="account-${account.account_id}" 
                           value="${account.account_id}" style="display: none;">
                </div>
            `).join('');
        }
        
        function toggleAccount(accountId) {
            const checkbox = document.getElementById(`account-${accountId}`);
            const accountItem = checkbox.closest('.account-item');
            
            checkbox.checked = !checkbox.checked;
            
            if (checkbox.checked) {
                accountItem.classList.add('selected');
                if (!selectedAccounts.includes(accountId)) {
                    selectedAccounts.push(accountId);
                }
            } else {
                accountItem.classList.remove('selected');
                selectedAccounts = selectedAccounts.filter(id => id !== accountId);
            }
        }
        
        function saveSelectedAccounts() {
            if (selectedAccounts.length === 0) {
                showAlert('warning', 'Please select at least one account');
                return;
            }
            
            userSettings.selectedAccounts = selectedAccounts;
            nextStep();
        }
        
        function saveSettings() {
            const homeState = document.getElementById('home-state').value;
            const homeCity = document.getElementById('home-city').value;
            const tripRule = document.getElementById('trip-rule').value;
            const perDiem = document.getElementById('per-diem').value;
            
            if (!homeState) {
                showAlert('warning', 'Please select your home state');
                return;
            }
            
            userSettings.homeState = homeState;
            userSettings.homeCity = homeCity;
            userSettings.tripRule = tripRule;
            userSettings.perDiem = parseFloat(perDiem);
            
            // Save to backend
            fetch('/api/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(userSettings)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    nextStep();
                }
            })
            .catch(error => {
                showAlert('danger', 'Error saving settings: ' + error.message);
            });
        }
        
        function processExpenses() {
            const startDate = document.getElementById('start-date').value;
            const endDate = document.getElementById('end-date').value;
            
            if (!startDate || !endDate) {
                showAlert('warning', 'Please select date range');
                return;
            }
            
            document.getElementById('processing-status').innerHTML = 
                '<div class="alert alert-info"><span class="loading-spinner"></span> Analyzing transactions...</div>';
            
            fetch('/api/process-expenses', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    start_date: startDate,
                    end_date: endDate
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    displayResults(data);
                    document.getElementById('setup-wizard').style.display = 'none';
                    document.getElementById('results-section').style.display = 'block';
                } else {
                    showAlert('danger', data.error || 'Processing failed');
                }
            })
            .catch(error => {
                showAlert('danger', 'Error: ' + error.message);
            });
        }
        
        function displayResults(data) {
            // Update statistics
            document.getElementById('total-trips').textContent = data.trips.length;
            document.getElementById('total-expenses').textContent = 
                '$' + data.total_expenses.toFixed(2);
            document.getElementById('avg-trip-cost').textContent = 
                '$' + (data.total_expenses / (data.trips.length || 1)).toFixed(2);
            document.getElementById('concur-ready').textContent = data.trips.length;
            
            // Display trips
            const tripsContainer = document.getElementById('trips-list');
            tripsContainer.innerHTML = data.trips.map(trip => `
                <div class="trip-card">
                    <div class="trip-header">
                        <div>
                            <div class="trip-destination">${trip.destination}</div>
                            <div class="trip-dates">
                                ${new Date(trip.start_date).toLocaleDateString()} - 
                                ${new Date(trip.end_date).toLocaleDateString()}
                                (${trip.duration_days} days)
                            </div>
                        </div>
                        <div class="trip-amount">$${trip.total_expenses.toFixed(2)}</div>
                    </div>
                    <div style="color: #6c757d; margin: 0.5rem 0;">
                        ${trip.business_purpose}
                    </div>
                    <div class="expense-categories">
                        ${Object.entries(trip.categories).map(([cat, amount]) => 
                            `<span class="category-pill">${cat}: $${amount.toFixed(2)}</span>`
                        ).join('')}
                    </div>
                    <div style="margin-top: 1rem;">
                        <button class="btn btn-primary" onclick="viewTripDetails('${trip.trip_id}')">
                            View Details
                        </button>
                        <button class="btn btn-success" onclick="exportTrip('${trip.trip_id}')" style="margin-left: 0.5rem;">
                            Export to Concur
                        </button>
                    </div>
                </div>
            `).join('');
        }
        
        function exportToConcur() {
            fetch('/api/export/concur', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            })
            .then(response => response.blob())
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'concur_expense_reports.csv';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                showAlert('success', 'Concur export downloaded successfully!');
            })
            .catch(error => {
                showAlert('danger', 'Export failed: ' + error.message);
            });
        }
        
        function viewTripDetails(tripId) {
            // Would open modal with full transaction list
            console.log('View trip:', tripId);
        }
        
        function exportTrip(tripId) {
            // Export individual trip
            console.log('Export trip:', tripId);
        }
        
        function startOver() {
            location.reload();
        }
        
        function showAlert(type, message) {
            const alertsDiv = document.getElementById('alerts');
            const alertClass = type === 'success' ? 'alert-success' : 
                              type === 'danger' ? 'alert-warning' : 'alert-info';
            
            const alert = document.createElement('div');
            alert.className = `alert ${alertClass}`;
            alert.textContent = message;
            
            alertsDiv.innerHTML = '';
            alertsDiv.appendChild(alert);
            
            setTimeout(() => {
                alert.style.opacity = '0';
                setTimeout(() => alert.remove(), 300);
            }, 5000);
        }
    </script>
</body>
</html>
"""


# API Routes
@app.route('/')
def index():
    """Main dashboard with CSRF token."""
    csrf_token = generate_csrf()
    return render_template_string(PRODUCTION_DASHBOARD, states=US_STATES, csrf_token=csrf_token)


@app.route('/api/plaid/link-token', methods=['POST'])
@require_csrf
@rate_limit(max_attempts=10, window_minutes=1)
def create_link_token():
    """Create Plaid Link token."""
    if not PLAID_CLIENT_ID or not PLAID_SECRET:
        return jsonify({
            'error': 'Plaid not configured',
            'message': 'Please add PLAID_CLIENT_ID and PLAID_SECRET to your .env file'
        }), 400
    
    try:
        request = LinkTokenCreateRequest(
            products=PLAID_PRODUCTS,
            client_name='Travel Expense Manager',
            country_codes=PLAID_COUNTRY_CODES,
            language='en',
            user={'client_user_id': str(SessionManager.create_session(secrets.token_urlsafe(16)))}
        )
        
        response = plaid_client.link_token_create(request)
        return jsonify({'link_token': response['link_token']})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/plaid/exchange-token', methods=['POST'])
@require_csrf
@require_session
@rate_limit(max_attempts=5, window_minutes=1)
def exchange_public_token():
    """Exchange public token for access token."""
    try:
        data = request.get_json()
        public_token = data['public_token']
        
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = plaid_client.item_public_token_exchange(request)
        
        access_token = response['access_token']
        
        # Store in session (in production, store in database)
        session['plaid_access_token'] = access_token
        
        return jsonify({
            'success': True,
            'access_token': access_token[:20] + '...'  # Don't send full token
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/plaid/accounts')
@require_session
@rate_limit(max_attempts=30, window_minutes=1)
def get_accounts():
    """Get user's bank accounts."""
    try:
        access_token = session.get('plaid_access_token')
        if not access_token:
            return jsonify({'error': 'Not authenticated'}), 401
        
        request = AccountsGetRequest(access_token=access_token)
        response = plaid_client.accounts_get(request)
        
        return jsonify({'accounts': response['accounts']})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings', methods=['POST'])
@require_csrf
@require_session
@rate_limit(max_attempts=10, window_minutes=1)
def save_settings():
    """Save user settings with validation."""
    try:
        data = request.get_json()
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        # Validate inputs
        try:
            home_state = InputValidator.validate_state_code(data.get('homeState', ''))
            home_city = InputValidator.validate_string(
                data.get('homeCity', ''), 
                max_length=100, 
                name='home_city'
            ) if data.get('homeCity') else None
            per_diem = InputValidator.validate_amount(
                data.get('perDiem', 75.0),
                min_val=0,
                max_val=1000
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        settings = UserSettings(
            home_state=home_state,
            home_city=home_city,
            trip_detection_rule=TripRule(data.get('tripRule', 'out_of_state_2_days')),
            min_trip_days=2,
            per_diem_amount=per_diem,
            selected_account_ids=data.get('selectedAccounts', [])
        )
        
        # Store in session (in production, store in database)
        session['user_settings'] = settings.to_dict()
        
        # Save to database securely
        with SecureDatabase('expense_tracker.db') as db:
            # Check if user settings exist
            existing = db.select(
                'user_settings',
                where={'user_id': user_id}
            )
            
            settings_data = {
                'user_id': user_id,
                'home_state': settings.home_state,
                'home_city': settings.home_city,
                'trip_detection_rule': settings.trip_detection_rule.value,
                'per_diem_amount': settings.per_diem_amount,
                'selected_account_ids': json.dumps(settings.selected_account_ids),
                'plaid_access_token': session.get('plaid_access_token'),
                'updated_at': datetime.now().isoformat()
            }
            
            if existing:
                db.update(
                    'user_settings',
                    settings_data,
                    where={'user_id': user_id}
                )
            else:
                settings_data['created_at'] = datetime.now().isoformat()
                db.insert('user_settings', settings_data)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/process-expenses', methods=['POST'])
@require_csrf
@require_session
@rate_limit(max_attempts=5, window_minutes=1)
def process_expenses():
    """Process expenses and detect trips with validation."""
    try:
        data = request.get_json()
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        # Validate dates
        try:
            start_date = InputValidator.validate_date(data.get('start_date', ''))
            end_date = InputValidator.validate_date(data.get('end_date', ''))
            
            if end_date < start_date:
                raise ValueError("End date must be after start date")
            
            # Limit date range to prevent abuse
            if (end_date - start_date).days > 365:
                raise ValueError("Date range cannot exceed 365 days")
                
            start_date = start_date.date()
            end_date = end_date.date()
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        access_token = session.get('plaid_access_token')
        if not access_token:
            return jsonify({'error': 'Not authenticated'}), 401
        
        # Get transactions from Plaid
        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
            options={'account_ids': session.get('user_settings', {}).get('selectedAccounts', [])}
        )
        
        response = plaid_client.transactions_get(request)
        transactions = response['transactions']
        
        # Convert Plaid transactions to our format
        formatted_transactions = []
        for trans in transactions:
            formatted_transactions.append({
                'transaction_id': trans['transaction_id'],
                'account_id': trans['account_id'],
                'amount': trans['amount'],
                'date': datetime.strptime(trans['date'], '%Y-%m-%d').date(),
                'name': trans['name'],
                'merchant_name': trans.get('merchant_name'),
                'category': trans.get('category', []),
                'location': trans.get('location', {}),
                'iso_currency_code': trans.get('iso_currency_code', 'USD'),
                'pending': trans.get('pending', False)
            })
        
        # Load user settings
        settings_dict = session.get('user_settings', {})
        settings = UserSettings.from_dict(settings_dict)
        
        # Detect trips
        detector = TripDetector(settings)
        trips = detector.detect_trips(formatted_transactions)
        
        # Save trips to database securely
        with SecureDatabase('expense_tracker.db') as db:
        
            for trip in trips:
                trip_data = {
                    'trip_id': trip.trip_id,
                    'user_id': user_id,
                    'start_date': trip.start_date.isoformat(),
                    'end_date': trip.end_date.isoformat(),
                    'destination': InputValidator.validate_string(trip.destination, max_length=100),
                    'destination_state': trip.destination_state,
                    'total_expenses': InputValidator.validate_amount(trip.total_expenses),
                    'expense_count': trip.expense_count,
                    'business_purpose': InputValidator.validate_string(trip.business_purpose, max_length=500),
                    'created_at': datetime.now().isoformat()
                }
                
                # Check if trip exists
                existing_trip = db.select(
                    'trips',
                    where={'trip_id': trip.trip_id, 'user_id': user_id}
                )
                
                if existing_trip:
                    db.update(
                        'trips',
                        trip_data,
                        where={'trip_id': trip.trip_id, 'user_id': user_id}
                    )
                else:
                    db.insert('trips', trip_data)
            
                # Save transactions
                for trans in trip.transactions:
                    trans_data = {
                        'transaction_id': trans.get('transaction_id'),
                        'user_id': user_id,
                        'trip_id': trip.trip_id,
                        'account_id': trans.get('account_id'),
                        'amount': InputValidator.validate_amount(trans.get('amount', 0)),
                        'date': trans.get('date').isoformat() if isinstance(trans.get('date'), date) else trans.get('date'),
                        'name': InputValidator.validate_string(trans.get('name', ''), max_length=200),
                        'merchant_name': InputValidator.validate_string(trans.get('merchant_name', ''), max_length=200) if trans.get('merchant_name') else None,
                        'category': json.dumps(trans.get('category', [])),
                        'location_city': InputValidator.validate_string(trans.get('location', {}).get('city', ''), max_length=100) if trans.get('location', {}).get('city') else None,
                        'location_state': trans.get('location', {}).get('region'),
                        'iso_currency_code': trans.get('iso_currency_code', 'USD'),
                        'pending': trans.get('pending', False)
                    }
                    
                    # Check if transaction exists
                    existing_trans = db.select(
                        'transactions',
                        where={'transaction_id': trans.get('transaction_id'), 'user_id': user_id}
                    )
                    
                    if not existing_trans:
                        db.insert('transactions', trans_data)
        
        # Prepare response
        trips_data = []
        for trip in trips:
            trips_data.append({
                'trip_id': trip.trip_id,
                'start_date': trip.start_date.isoformat(),
                'end_date': trip.end_date.isoformat(),
                'destination': trip.destination,
                'destination_state': trip.destination_state,
                'duration_days': trip.duration_days,
                'total_expenses': trip.total_expenses,
                'expense_count': trip.expense_count,
                'categories': trip.categories,
                'business_purpose': trip.business_purpose
            })
        
        total_expenses = sum(trip.total_expenses for trip in trips)
        
        return jsonify({
            'success': True,
            'trips': trips_data,
            'total_expenses': total_expenses,
            'transaction_count': len(formatted_transactions)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/submit/concur/<trip_id>', methods=['POST'])
@require_csrf
@require_session
@rate_limit(max_attempts=5, window_minutes=1)
def submit_to_concur(trip_id):
    """Submit a trip directly to Concur via API."""
    try:
        from concur_api_integration import ConcurAPIClient
        
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
            
        # Validate and sanitize trip_id
        try:
            trip_id = InputValidator.validate_string(trip_id, max_length=50, pattern=r'^TRIP_[A-Z0-9_-]+$')
        except ValueError:
            return jsonify({'error': 'Invalid trip ID'}), 400
        
        # Get trip from database with user validation
        with SecureDatabase('expense_tracker.db') as db:
            trips = db.select(
                'trips',
                where={'trip_id': trip_id, 'user_id': user_id}
            )
            
            if not trips:
                return jsonify({'error': 'Trip not found or access denied'}), 404
            
            trip_data = trips[0]
            # Get transactions for trip with user validation
            transactions = db.select(
                'transactions',
                where={'trip_id': trip_id, 'user_id': user_id}
            )
        
        # Initialize Concur client
        client = ConcurAPIClient()
        if not client.authenticate():
            return jsonify({'error': 'Failed to authenticate with Concur'}), 401
        
        # Create expense report
        report_data = {
            'report_name': f"Business Trip to {trip_data[3]}",
            'business_purpose': trip_data[7],
            'start_date': trip_data[1],
            'end_date': trip_data[2],
            'destination': trip_data[3],
            'duration_days': (datetime.strptime(trip_data[2], '%Y-%m-%d') - 
                            datetime.strptime(trip_data[1], '%Y-%m-%d')).days + 1
        }
        
        report_id = client.create_expense_report(report_data)
        if not report_id:
            return jsonify({'error': 'Failed to create Concur report'}), 500
        
        # Add expenses
        expenses_added = 0
        for trans in transactions:
            expense = {
                'date': trans[4],
                'vendor': trans[5],
                'amount': abs(trans[3]),
                'category': json.loads(trans[7]) if trans[7] else [],
                'currency': trans[10] or 'USD',
                'location': f"{trans[8] or ''}, {trans[9] or ''}",
                'description': trans[6] or ''
            }
            
            entry_id = client.add_expense_entry(report_id, expense)
            if entry_id:
                expenses_added += 1
        
        # Submit for approval
        submitted = client.submit_report_for_approval(report_id)
        
        return jsonify({
            'success': True,
            'report_id': report_id,
            'expenses_added': expenses_added,
            'submitted': submitted,
            'concur_url': f"https://www.concursolutions.com/expense/report/{report_id}"
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/concur', methods=['POST'])
@require_csrf
@require_session
@rate_limit(max_attempts=10, window_minutes=1)
def export_concur():
    """Export trips in Concur CSV format."""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
        # Get trips from database with user filtering
        with SecureDatabase('expense_tracker.db') as db:
            # Use parameterized query for user filtering
            cursor = db.execute(
                """
                SELECT t.*, tr.*
                FROM trips t
                LEFT JOIN transactions tr ON t.trip_id = tr.trip_id
                WHERE t.user_id = ? AND tr.user_id = ?
                ORDER BY t.start_date, tr.date
                """,
                [user_id, user_id]
            )
            results = cursor.fetchall()
        
        # Format as CSV for Concur
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Report Name', 'Start Date', 'End Date', 'Business Purpose',
            'Expense Date', 'Vendor', 'Amount', 'Expense Type', 'Payment Type',
            'Description', 'Currency'
        ])
        
        # Write data
        current_trip = None
        for row in results:
            if not current_trip or current_trip != row[0]:  # New trip
                current_trip = row[0]
                trip_data = {
                    'report_name': f"Business Trip to {row[3]}",
                    'start_date': row[1],
                    'end_date': row[2],
                    'business_purpose': row[7]
                }
            
            # Write expense row
            writer.writerow([
                trip_data['report_name'],
                trip_data['start_date'],
                trip_data['end_date'],
                trip_data['business_purpose'],
                row[13],  # expense date
                row[14],  # vendor
                abs(row[12]),  # amount
                'Business Expense',  # expense type
                'Credit Card',
                row[15] or '',  # description
                'USD'
            ])
        
        # Return as file
        output.seek(0)
        from flask import Response
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=concur_expenses.csv'}
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 PRODUCTION TRAVEL EXPENSE MANAGEMENT SYSTEM")
    print("=" * 60)
    print("\n✅ Features:")
    print("  • Real Plaid OAuth integration")
    print("  • Intelligent trip detection")
    print("  • Automated expense categorization")
    print("  • Concur-ready export format")
    print("  • Per diem tracking")
    print("\n📋 Setup:")
    print("  1. Add to .env file:")
    print("     PLAID_CLIENT_ID=your_client_id")
    print("     PLAID_SECRET=your_secret")
    print("     PLAID_ENV=sandbox  (or development/production)")
    print("\n🌐 Open: http://localhost:8080")
    print("\nPress Ctrl+C to stop")
    print("-" * 60)
    
    # Initialize database
    init_database()
    print("✅ Database initialized")
    
    # Check Plaid configuration
    if PLAID_CLIENT_ID and PLAID_SECRET:
        print(f"✅ Plaid configured ({PLAID_ENV} environment)")
    else:
        print("⚠️  Plaid not configured - add credentials to .env file")
    
    app.run(host='0.0.0.0', port=8080, debug=True)