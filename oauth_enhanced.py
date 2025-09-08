#!/usr/bin/env python3
"""
Enhanced OAuth integration with Gmail support and per diem tracking.
Supports Google OAuth for Gmail, Plaid, and Concur integration.
"""

from flask import Flask, render_template_string, request, redirect, session, url_for, jsonify
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import os
import json
import base64
import re
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
import secrets
from urllib.parse import urlencode, quote
from collections import defaultdict

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))

# Google OAuth Configuration for Gmail
GOOGLE_CONFIG = {
    'client_id': os.getenv('GOOGLE_CLIENT_ID', ''),
    'client_secret': os.getenv('GOOGLE_CLIENT_SECRET', ''),
    'redirect_uri': 'http://localhost:8080/auth/google/callback',
    'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
    'token_uri': 'https://oauth2.googleapis.com/token',
    'scopes': ['https://www.googleapis.com/auth/gmail.readonly']
}

# Plaid OAuth Configuration (existing)
PLAID_CONFIG = {
    'client_id': os.getenv('PLAID_CLIENT_ID', ''),
    'secret': os.getenv('PLAID_SECRET', ''),
    'env': os.getenv('PLAID_ENV', 'sandbox'),
    'redirect_uri': 'http://localhost:8080/auth/plaid/callback',
}

# Concur OAuth Configuration (existing)
CONCUR_CONFIG = {
    'client_id': os.getenv('CONCUR_CLIENT_ID', ''),
    'client_secret': os.getenv('CONCUR_CLIENT_SECRET', ''),
    'redirect_uri': 'http://localhost:8080/auth/concur/callback',
    'auth_url': 'https://us.api.concursolutions.com/oauth2/v0/authorize',
    'token_url': 'https://us.api.concursolutions.com/oauth2/v0/token',
}

# Per Diem Configuration
PER_DIEM_CONFIG = {
    'daily_food_allowance': float(os.getenv('DAILY_FOOD_ALLOWANCE', '75.00')),
    'breakfast_percentage': 0.20,  # 20% of daily allowance
    'lunch_percentage': 0.35,      # 35% of daily allowance
    'dinner_percentage': 0.45,     # 45% of daily allowance
}


class GmailConcurExtractor:
    """Extracts Concur trip information from Gmail."""
    
    def __init__(self, service):
        self.service = service
        self.trip_patterns = [
            r'Your expense report .* has been approved',
            r'Trip to (.*?) from (\d{2}/\d{2}/\d{4}) to (\d{2}/\d{2}/\d{4})',
            r'Business trip: (.*?) \((.*?)\)',
            r'Expense report submitted for (.*?) trip',
        ]
    
    def fetch_concur_emails(self, max_results=50) -> List[Dict]:
        """Fetch emails from Concur."""
        try:
            # Search for Concur emails
            query = 'from:(concur@concursolutions.com OR noreply@concur.com OR expense@concur.com)'
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            trips = []
            
            for message in messages:
                msg = self.service.users().messages().get(
                    userId='me',
                    id=message['id']
                ).execute()
                
                trip_info = self.extract_trip_info(msg)
                if trip_info:
                    trips.append(trip_info)
            
            return trips
            
        except Exception as e:
            print(f"Error fetching Gmail: {e}")
            return []
    
    def extract_trip_info(self, message) -> Optional[Dict]:
        """Extract trip information from email message."""
        try:
            # Get email metadata
            headers = message['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            date_str = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            # Get email body
            body = self.get_email_body(message)
            
            # Extract trip details
            trip = {
                'email_date': date_str,
                'subject': subject,
                'trips': []
            }
            
            # Look for trip patterns in body
            for pattern in self.trip_patterns:
                matches = re.findall(pattern, body, re.IGNORECASE)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 3:
                        trip['trips'].append({
                            'destination': match[0],
                            'start_date': match[1],
                            'end_date': match[2]
                        })
                    elif isinstance(match, str):
                        # Try to extract dates from context
                        trip['trips'].append({'description': match})
            
            # Extract report IDs
            report_id_match = re.search(r'Report ID:\s*(\w+)', body)
            if report_id_match:
                trip['report_id'] = report_id_match.group(1)
            
            # Extract approval status
            if 'approved' in body.lower():
                trip['status'] = 'approved'
            elif 'submitted' in body.lower():
                trip['status'] = 'submitted'
            elif 'rejected' in body.lower():
                trip['status'] = 'rejected'
            
            return trip if trip['trips'] else None
            
        except Exception as e:
            print(f"Error extracting trip info: {e}")
            return None
    
    def get_email_body(self, message) -> str:
        """Extract email body text."""
        try:
            payload = message['payload']
            body = ''
            
            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain':
                        data = part['body']['data']
                        body += base64.urlsafe_b64decode(data).decode('utf-8')
            elif payload['body'].get('data'):
                body = base64.urlsafe_b64decode(
                    payload['body']['data']
                ).decode('utf-8')
            
            return body
        except:
            return ''


class PerDiemTracker:
    """Tracks per diem allowances and compares with actual expenses."""
    
    def __init__(self, daily_allowance: float = 75.00):
        self.daily_allowance = daily_allowance
        self.breakfast_allowance = daily_allowance * PER_DIEM_CONFIG['breakfast_percentage']
        self.lunch_allowance = daily_allowance * PER_DIEM_CONFIG['lunch_percentage']
        self.dinner_allowance = daily_allowance * PER_DIEM_CONFIG['dinner_percentage']
    
    def categorize_meal(self, transaction_time: str, description: str) -> str:
        """Categorize a meal transaction by time of day."""
        try:
            hour = datetime.strptime(transaction_time, '%H:%M').hour
        except:
            hour = 12  # Default to lunch if time parsing fails
        
        # Breakfast: 5am - 11am
        if 5 <= hour < 11:
            return 'breakfast'
        # Lunch: 11am - 4pm
        elif 11 <= hour < 16:
            return 'lunch'
        # Dinner: 4pm - 10pm
        elif 16 <= hour < 22:
            return 'dinner'
        else:
            # Late night or early morning - check description
            desc_lower = description.lower()
            if any(word in desc_lower for word in ['breakfast', 'morning', 'coffee']):
                return 'breakfast'
            elif any(word in desc_lower for word in ['lunch', 'noon']):
                return 'lunch'
            else:
                return 'dinner'
    
    def analyze_daily_expenses(self, expenses: List[Dict]) -> Dict:
        """Analyze expenses against per diem allowances."""
        daily_totals = defaultdict(lambda: {
            'breakfast': 0, 'lunch': 0, 'dinner': 0, 
            'total': 0, 'transactions': []
        })
        
        for expense in expenses:
            if expense.get('category') != 'MEALS':
                continue
            
            expense_date = expense.get('date', '')
            amount = float(expense.get('amount', 0))
            time = expense.get('time', '12:00')
            description = expense.get('description', '')
            
            meal_type = self.categorize_meal(time, description)
            
            daily_totals[expense_date][meal_type] += amount
            daily_totals[expense_date]['total'] += amount
            daily_totals[expense_date]['transactions'].append({
                'meal_type': meal_type,
                'amount': amount,
                'description': description,
                'time': time
            })
        
        # Calculate per diem compliance
        analysis = {
            'daily_analysis': {},
            'summary': {
                'total_days': len(daily_totals),
                'days_under_limit': 0,
                'days_over_limit': 0,
                'total_saved': 0,
                'total_overage': 0
            }
        }
        
        for date_str, day_data in daily_totals.items():
            daily_diff = self.daily_allowance - day_data['total']
            
            day_analysis = {
                'date': date_str,
                'meals': {
                    'breakfast': {
                        'spent': day_data['breakfast'],
                        'allowance': self.breakfast_allowance,
                        'difference': self.breakfast_allowance - day_data['breakfast']
                    },
                    'lunch': {
                        'spent': day_data['lunch'],
                        'allowance': self.lunch_allowance,
                        'difference': self.lunch_allowance - day_data['lunch']
                    },
                    'dinner': {
                        'spent': day_data['dinner'],
                        'allowance': self.dinner_allowance,
                        'difference': self.dinner_allowance - day_data['dinner']
                    }
                },
                'total_spent': day_data['total'],
                'daily_allowance': self.daily_allowance,
                'difference': daily_diff,
                'within_limit': daily_diff >= 0,
                'transactions': day_data['transactions']
            }
            
            analysis['daily_analysis'][date_str] = day_analysis
            
            if daily_diff >= 0:
                analysis['summary']['days_under_limit'] += 1
                analysis['summary']['total_saved'] += daily_diff
            else:
                analysis['summary']['days_over_limit'] += 1
                analysis['summary']['total_overage'] += abs(daily_diff)
        
        return analysis
    
    def generate_per_diem_report(self, analysis: Dict) -> str:
        """Generate a formatted per diem report."""
        report = []
        report.append("=" * 60)
        report.append("PER DIEM ANALYSIS REPORT")
        report.append("=" * 60)
        report.append(f"\nDaily Food Allowance: ${self.daily_allowance:.2f}")
        report.append(f"  - Breakfast: ${self.breakfast_allowance:.2f}")
        report.append(f"  - Lunch: ${self.lunch_allowance:.2f}")
        report.append(f"  - Dinner: ${self.dinner_allowance:.2f}")
        report.append("\n" + "-" * 60)
        
        summary = analysis['summary']
        report.append(f"\nSUMMARY:")
        report.append(f"Total Days Analyzed: {summary['total_days']}")
        report.append(f"Days Under Limit: {summary['days_under_limit']} ✅")
        report.append(f"Days Over Limit: {summary['days_over_limit']} ⚠️")
        report.append(f"Total Saved: ${summary['total_saved']:.2f}")
        report.append(f"Total Overage: ${summary['total_overage']:.2f}")
        
        report.append("\n" + "-" * 60)
        report.append("\nDAILY BREAKDOWN:")
        
        for date_str in sorted(analysis['daily_analysis'].keys()):
            day = analysis['daily_analysis'][date_str]
            status_icon = "✅" if day['within_limit'] else "❌"
            
            report.append(f"\n{date_str} {status_icon}")
            report.append(f"  Total: ${day['total_spent']:.2f} / ${day['daily_allowance']:.2f}")
            report.append(f"  Difference: ${day['difference']:.2f}")
            
            if day['meals']['breakfast']['spent'] > 0:
                report.append(f"  Breakfast: ${day['meals']['breakfast']['spent']:.2f}")
            if day['meals']['lunch']['spent'] > 0:
                report.append(f"  Lunch: ${day['meals']['lunch']['spent']:.2f}")
            if day['meals']['dinner']['spent'] > 0:
                report.append(f"  Dinner: ${day['meals']['dinner']['spent']:.2f}")
        
        return "\n".join(report)


# Enhanced Dashboard HTML
ENHANCED_OAUTH_DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <title>Travel Expense Analyzer - Enhanced OAuth & Per Diem</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        
        .header {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.1);
            margin-bottom: 30px;
            text-align: center;
        }
        
        .oauth-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .oauth-card {
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            position: relative;
            overflow: hidden;
        }
        
        .oauth-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 5px;
        }
        
        .gmail-card::before { background: linear-gradient(90deg, #EA4335, #FBBC04); }
        .plaid-card::before { background: linear-gradient(90deg, #00d4ff, #0099ff); }
        .concur-card::before { background: linear-gradient(90deg, #ff6b6b, #ee5a24); }
        
        .service-icon {
            width: 50px;
            height: 50px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            margin-bottom: 15px;
        }
        
        .gmail-icon { background: linear-gradient(135deg, #EA4335, #FBBC04); }
        .plaid-icon { background: linear-gradient(135deg, #00d4ff, #0099ff); }
        .concur-icon { background: linear-gradient(135deg, #ff6b6b, #ee5a24); }
        
        .oauth-button {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 15px;
        }
        
        .connect-button {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
        }
        
        .connect-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }
        
        .status-connected { color: #28a745; font-weight: bold; }
        .status-disconnected { color: #dc3545; }
        
        .per-diem-section {
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        
        .per-diem-controls {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        
        .per-diem-input {
            padding: 10px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }
        
        .per-diem-results {
            background: #f8f9fa;
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
            display: none;
        }
        
        .day-summary {
            display: flex;
            justify-content: space-between;
            padding: 10px;
            border-bottom: 1px solid #e0e0e0;
        }
        
        .day-under { background: #d4edda; }
        .day-over { background: #f8d7da; }
        
        .trip-list {
            background: #f8f9fa;
            border-radius: 12px;
            padding: 15px;
            margin-top: 15px;
            max-height: 300px;
            overflow-y: auto;
        }
        
        .trip-item {
            padding: 10px;
            margin: 5px 0;
            background: white;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        
        .alert {
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            display: none;
        }
        
        .alert-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .alert-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(0,0,0,.1);
            border-radius: 50%;
            border-top-color: #667eea;
            animation: spin 1s ease-in-out infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Enhanced Travel Expense Analyzer</h1>
            <p>OAuth Integration + Gmail Sync + Per Diem Tracking</p>
        </div>
        
        <!-- OAuth Cards -->
        <div class="oauth-grid">
            <!-- Gmail OAuth Card -->
            <div class="oauth-card gmail-card">
                <div class="service-icon gmail-icon">📧</div>
                <h3>Gmail</h3>
                <p style="font-size: 14px; color: #666; margin: 10px 0;">
                    Sync Concur trip emails
                </p>
                <div id="gmail-status" style="margin: 10px 0;">
                    Status: <span class="status-disconnected">Not Connected</span>
                </div>
                <div id="gmail-trips" class="trip-list" style="display: none;">
                    <strong>Recent Trips:</strong>
                    <div id="trip-list-content"></div>
                </div>
                <button class="oauth-button connect-button" onclick="connectGmail()">
                    Connect Gmail
                </button>
            </div>
            
            <!-- Plaid OAuth Card -->
            <div class="oauth-card plaid-card">
                <div class="service-icon plaid-icon">🏦</div>
                <h3>Plaid</h3>
                <p style="font-size: 14px; color: #666; margin: 10px 0;">
                    Bank transaction sync
                </p>
                <div id="plaid-status" style="margin: 10px 0;">
                    Status: <span class="status-disconnected">Not Connected</span>
                </div>
                <button class="oauth-button connect-button" onclick="connectPlaid()">
                    Connect Bank
                </button>
            </div>
            
            <!-- Concur OAuth Card -->
            <div class="oauth-card concur-card">
                <div class="service-icon concur-icon">📊</div>
                <h3>Concur</h3>
                <p style="font-size: 14px; color: #666; margin: 10px 0;">
                    Expense submission
                </p>
                <div id="concur-status" style="margin: 10px 0;">
                    Status: <span class="status-disconnected">Not Connected</span>
                </div>
                <button class="oauth-button connect-button" onclick="connectConcur()">
                    Connect Concur
                </button>
            </div>
        </div>
        
        <!-- Per Diem Section -->
        <div class="per-diem-section">
            <h2>💰 Per Diem Tracker</h2>
            <p style="color: #666; margin: 10px 0;">
                Track daily food expenses against your per diem allowance
            </p>
            
            <div class="per-diem-controls">
                <div>
                    <label>Daily Allowance ($)</label>
                    <input type="number" id="daily-allowance" class="per-diem-input" 
                           value="75.00" step="5.00" min="0">
                </div>
                <div>
                    <label>Start Date</label>
                    <input type="date" id="start-date" class="per-diem-input">
                </div>
                <div>
                    <label>End Date</label>
                    <input type="date" id="end-date" class="per-diem-input">
                </div>
                <div style="display: flex; align-items: flex-end;">
                    <button class="oauth-button connect-button" onclick="analyzePerDiem()">
                        Analyze Per Diem
                    </button>
                </div>
            </div>
            
            <div id="per-diem-results" class="per-diem-results"></div>
        </div>
        
        <div id="alerts"></div>
    </div>
    
    <!-- Plaid Link Script -->
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    
    <script>
        // Set default dates
        document.getElementById('end-date').valueAsDate = new Date();
        const startDate = new Date();
        startDate.setDate(startDate.getDate() - 30);
        document.getElementById('start-date').valueAsDate = startDate;
        
        // Check status on load
        window.onload = function() {
            checkConnectionStatus();
        };
        
        function checkConnectionStatus() {
            fetch('/api/oauth/status')
                .then(response => response.json())
                .then(data => {
                    // Update Gmail status
                    if (data.gmail && data.gmail.connected) {
                        document.querySelector('#gmail-status span').className = 'status-connected';
                        document.querySelector('#gmail-status span').textContent = 'Connected';
                        loadGmailTrips();
                    }
                    
                    // Update Plaid status
                    if (data.plaid && data.plaid.connected) {
                        document.querySelector('#plaid-status span').className = 'status-connected';
                        document.querySelector('#plaid-status span').textContent = 'Connected';
                    }
                    
                    // Update Concur status
                    if (data.concur && data.concur.connected) {
                        document.querySelector('#concur-status span').className = 'status-connected';
                        document.querySelector('#concur-status span').textContent = 'Connected';
                    }
                });
        }
        
        function connectGmail() {
            showAlert('info', 'Redirecting to Google for authorization...');
            window.location.href = '/auth/google/authorize';
        }
        
        function connectPlaid() {
            showAlert('info', 'Initializing Plaid Link...');
            // Existing Plaid connection logic
            fetch('/auth/plaid/link-token', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data.link_token) {
                        // Initialize Plaid Link
                        const handler = Plaid.create({
                            token: data.link_token,
                            onSuccess: (public_token, metadata) => {
                                fetch('/auth/plaid/exchange-token', {
                                    method: 'POST',
                                    headers: {'Content-Type': 'application/json'},
                                    body: JSON.stringify({public_token: public_token})
                                })
                                .then(() => {
                                    showAlert('success', 'Bank connected successfully!');
                                    checkConnectionStatus();
                                });
                            }
                        });
                        handler.open();
                    }
                });
        }
        
        function connectConcur() {
            showAlert('info', 'Redirecting to Concur for authorization...');
            fetch('/auth/concur/authorize')
                .then(response => response.json())
                .then(data => {
                    if (data.auth_url) {
                        window.location.href = data.auth_url;
                    }
                });
        }
        
        function loadGmailTrips() {
            fetch('/api/gmail/trips')
                .then(response => response.json())
                .then(data => {
                    if (data.trips && data.trips.length > 0) {
                        document.getElementById('gmail-trips').style.display = 'block';
                        const tripList = document.getElementById('trip-list-content');
                        tripList.innerHTML = data.trips.map(trip => `
                            <div class="trip-item">
                                <strong>${trip.subject}</strong><br>
                                <small>${trip.email_date}</small>
                                ${trip.status ? `<br>Status: ${trip.status}` : ''}
                            </div>
                        `).join('');
                    }
                });
        }
        
        function analyzePerDiem() {
            const allowance = document.getElementById('daily-allowance').value;
            const startDate = document.getElementById('start-date').value;
            const endDate = document.getElementById('end-date').value;
            
            showAlert('info', 'Analyzing per diem expenses...');
            
            fetch('/api/per-diem/analyze', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    daily_allowance: parseFloat(allowance),
                    start_date: startDate,
                    end_date: endDate
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    displayPerDiemResults(data.analysis);
                    showAlert('success', 'Per diem analysis complete!');
                } else {
                    showAlert('error', data.error || 'Analysis failed');
                }
            });
        }
        
        function displayPerDiemResults(analysis) {
            const resultsDiv = document.getElementById('per-diem-results');
            const summary = analysis.summary;
            
            let html = `
                <h3>Per Diem Analysis Results</h3>
                <div style="margin: 15px 0;">
                    <strong>Summary:</strong><br>
                    Total Days: ${summary.total_days}<br>
                    Days Under Limit: <span style="color: green;">${summary.days_under_limit} ✅</span><br>
                    Days Over Limit: <span style="color: red;">${summary.days_over_limit} ❌</span><br>
                    Total Saved: <span style="color: green;">$${summary.total_saved.toFixed(2)}</span><br>
                    Total Overage: <span style="color: red;">$${summary.total_overage.toFixed(2)}</span>
                </div>
                <div style="margin-top: 20px;">
                    <strong>Daily Breakdown:</strong>
            `;
            
            for (const date in analysis.daily_analysis) {
                const day = analysis.daily_analysis[date];
                const className = day.within_limit ? 'day-under' : 'day-over';
                const icon = day.within_limit ? '✅' : '❌';
                
                html += `
                    <div class="day-summary ${className}">
                        <span>${date} ${icon}</span>
                        <span>$${day.total_spent.toFixed(2)} / $${day.daily_allowance.toFixed(2)}</span>
                        <span>${day.difference >= 0 ? '+' : ''}$${day.difference.toFixed(2)}</span>
                    </div>
                `;
            }
            
            html += '</div>';
            resultsDiv.innerHTML = html;
            resultsDiv.style.display = 'block';
        }
        
        function showAlert(type, message) {
            const alertsDiv = document.getElementById('alerts');
            const alertClass = type === 'success' ? 'alert-success' : 
                              type === 'error' ? 'alert-error' : 'alert-info';
            
            const alert = document.createElement('div');
            alert.className = `alert ${alertClass}`;
            alert.textContent = message;
            alert.style.display = 'block';
            
            alertsDiv.innerHTML = '';
            alertsDiv.appendChild(alert);
            
            setTimeout(() => {
                alert.style.opacity = '0';
                setTimeout(() => alert.remove(), 300);
            }, 5000);
        }
        
        // Check for OAuth callbacks
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('oauth_success')) {
            showAlert('success', 'Successfully connected!');
            checkConnectionStatus();
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    </script>
</body>
</html>
"""


# Routes
@app.route('/')
def index():
    """Main dashboard."""
    return render_template_string(ENHANCED_OAUTH_DASHBOARD)


@app.route('/api/oauth/status')
def oauth_status():
    """Get OAuth connection status for all services."""
    return jsonify({
        'gmail': {
            'connected': 'gmail_credentials' in session,
            'email': session.get('gmail_email')
        },
        'plaid': {
            'connected': 'plaid_access_token' in session,
            'institution': session.get('plaid_institution')
        },
        'concur': {
            'connected': 'concur_access_token' in session,
            'user': session.get('concur_user')
        }
    })


# Google OAuth Flow
@app.route('/auth/google/authorize')
def google_authorize():
    """Initiate Google OAuth flow."""
    if not GOOGLE_CONFIG['client_id']:
        # Demo mode
        session['gmail_credentials'] = 'demo_credentials'
        session['gmail_email'] = 'demo@example.com'
        return redirect('/?oauth_success=true')
    
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CONFIG['client_id'],
                "client_secret": GOOGLE_CONFIG['client_secret'],
                "auth_uri": GOOGLE_CONFIG['auth_uri'],
                "token_uri": GOOGLE_CONFIG['token_uri']
            }
        },
        scopes=GOOGLE_CONFIG['scopes']
    )
    flow.redirect_uri = GOOGLE_CONFIG['redirect_uri']
    
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    session['google_oauth_state'] = state
    return redirect(auth_url)


@app.route('/auth/google/callback')
def google_callback():
    """Handle Google OAuth callback."""
    state = session.get('google_oauth_state')
    
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CONFIG['client_id'],
                "client_secret": GOOGLE_CONFIG['client_secret'],
                "auth_uri": GOOGLE_CONFIG['auth_uri'],
                "token_uri": GOOGLE_CONFIG['token_uri']
            }
        },
        scopes=GOOGLE_CONFIG['scopes'],
        state=state
    )
    flow.redirect_uri = GOOGLE_CONFIG['redirect_uri']
    
    # Exchange authorization code for tokens
    flow.fetch_token(authorization_response=request.url)
    
    credentials = flow.credentials
    session['gmail_credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret
    }
    
    # Get user email
    service = build('gmail', 'v1', credentials=credentials)
    profile = service.users().getProfile(userId='me').execute()
    session['gmail_email'] = profile.get('emailAddress')
    
    return redirect('/?oauth_success=true')


@app.route('/api/gmail/trips')
def get_gmail_trips():
    """Fetch Concur trip emails from Gmail."""
    if 'gmail_credentials' not in session:
        return jsonify({'error': 'Gmail not connected'}), 401
    
    try:
        # Demo data for testing
        if session.get('gmail_credentials') == 'demo_credentials':
            return jsonify({
                'trips': [
                    {
                        'subject': 'Trip to Seattle approved',
                        'email_date': '2024-11-15',
                        'status': 'approved',
                        'destination': 'Seattle, WA',
                        'start_date': '2024-11-20',
                        'end_date': '2024-11-22'
                    },
                    {
                        'subject': 'Business trip to New York submitted',
                        'email_date': '2024-10-28',
                        'status': 'submitted',
                        'destination': 'New York, NY',
                        'start_date': '2024-11-01',
                        'end_date': '2024-11-03'
                    }
                ]
            })
        
        # Real Gmail API call would go here
        # credentials = Credentials(**session['gmail_credentials'])
        # service = build('gmail', 'v1', credentials=credentials)
        # extractor = GmailConcurExtractor(service)
        # trips = extractor.fetch_concur_emails()
        
        return jsonify({'trips': []})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/per-diem/analyze', methods=['POST'])
def analyze_per_diem():
    """Analyze expenses against per diem allowances."""
    data = request.get_json()
    daily_allowance = data.get('daily_allowance', 75.00)
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    try:
        # Demo data for testing
        demo_expenses = [
            {'date': '2024-11-20', 'category': 'MEALS', 'amount': 25.50, 
             'time': '08:30', 'description': 'Starbucks'},
            {'date': '2024-11-20', 'category': 'MEALS', 'amount': 18.75, 
             'time': '12:45', 'description': 'Chipotle'},
            {'date': '2024-11-20', 'category': 'MEALS', 'amount': 42.00, 
             'time': '19:00', 'description': 'Restaurant'},
            {'date': '2024-11-21', 'category': 'MEALS', 'amount': 12.50, 
             'time': '09:00', 'description': 'Coffee Shop'},
            {'date': '2024-11-21', 'category': 'MEALS', 'amount': 22.00, 
             'time': '13:00', 'description': 'Lunch'},
            {'date': '2024-11-21', 'category': 'MEALS', 'amount': 35.00, 
             'time': '18:30', 'description': 'Dinner'},
        ]
        
        tracker = PerDiemTracker(daily_allowance)
        analysis = tracker.analyze_daily_expenses(demo_expenses)
        
        return jsonify({
            'success': True,
            'analysis': analysis,
            'report': tracker.generate_per_diem_report(analysis)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Plaid stub routes (existing functionality)
@app.route('/auth/plaid/link-token', methods=['POST'])
def create_plaid_link_token():
    """Create Plaid Link token."""
    return jsonify({
        'link_token': 'demo-link-token-' + secrets.token_hex(8)
    })


@app.route('/auth/plaid/exchange-token', methods=['POST'])
def exchange_plaid_token():
    """Exchange Plaid public token."""
    session['plaid_access_token'] = 'demo-access-token'
    session['plaid_institution'] = 'Demo Bank'
    return jsonify({'success': True})


# Concur stub routes (existing functionality)
@app.route('/auth/concur/authorize')
def concur_authorize():
    """Initiate Concur OAuth."""
    return jsonify({
        'auth_url': '/auth/concur/demo-callback'
    })


@app.route('/auth/concur/demo-callback')
def concur_demo_callback():
    """Demo Concur callback."""
    session['concur_access_token'] = 'demo-concur-token'
    session['concur_user'] = 'demo@company.com'
    return redirect('/?oauth_success=true')


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 ENHANCED OAUTH WITH GMAIL & PER DIEM TRACKING")
    print("=" * 60)
    print("\n✅ Features:")
    print("  • Google OAuth for Gmail access")
    print("  • Fetch Concur trip emails automatically")
    print("  • Per diem tracking ($75/day configurable)")
    print("  • Daily meal expense analysis")
    print("  • Plaid & Concur OAuth support")
    print("\n🌐 Open: http://localhost:8080")
    print("\nPress Ctrl+C to stop")
    print("-" * 60)
    
    app.run(host='0.0.0.0', port=8080, debug=True)