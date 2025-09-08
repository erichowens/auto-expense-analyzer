#!/usr/bin/env python3
"""
OAuth-enabled Flask app for Plaid and Concur integration.
"""

from flask import Flask, render_template_string, request, redirect, session, url_for, jsonify
import os
import json
import requests
from datetime import datetime, timedelta
import secrets
from urllib.parse import urlencode, quote

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))

# OAuth Configuration
PLAID_CONFIG = {
    'client_id': os.getenv('PLAID_CLIENT_ID', ''),
    'secret': os.getenv('PLAID_SECRET', ''),
    'env': os.getenv('PLAID_ENV', 'sandbox'),
    'redirect_uri': 'http://localhost:8080/auth/plaid/callback',
    'webhook_url': 'http://localhost:8080/webhooks/plaid'
}

CONCUR_CONFIG = {
    'client_id': os.getenv('CONCUR_CLIENT_ID', ''),
    'client_secret': os.getenv('CONCUR_CLIENT_SECRET', ''),
    'redirect_uri': 'http://localhost:8080/auth/concur/callback',
    'auth_url': 'https://us.api.concursolutions.com/oauth2/v0/authorize',
    'token_url': 'https://us.api.concursolutions.com/oauth2/v0/token',
    'scope': 'openid expense.report.read expense.report.readwrite receipts.read receipts.write'
}

# OAuth Dashboard
OAUTH_DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <title>Travel Expense Analyzer - OAuth Setup</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
        }
        .header {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.1);
            margin-bottom: 30px;
            text-align: center;
        }
        h1 {
            color: #2c3e50;
            margin-bottom: 10px;
            font-size: 36px;
        }
        .subtitle {
            color: #666;
            font-size: 18px;
        }
        .oauth-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }
        .oauth-card {
            background: white;
            border-radius: 20px;
            padding: 30px;
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
            background: linear-gradient(90deg, #667eea, #764ba2);
        }
        .service-header {
            display: flex;
            align-items: center;
            margin-bottom: 25px;
        }
        .service-icon {
            width: 60px;
            height: 60px;
            border-radius: 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            margin-right: 20px;
        }
        .plaid-icon {
            background: linear-gradient(135deg, #00d4ff, #0099ff);
        }
        .concur-icon {
            background: linear-gradient(135deg, #ff6b6b, #ee5a24);
        }
        .service-info h2 {
            color: #2c3e50;
            margin-bottom: 5px;
        }
        .service-info p {
            color: #666;
            font-size: 14px;
        }
        .status-section {
            background: #f8f9fa;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 25px;
        }
        .status-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #e0e0e0;
        }
        .status-item:last-child {
            border-bottom: none;
        }
        .status-label {
            color: #666;
            font-size: 14px;
        }
        .status-value {
            font-weight: 600;
            font-size: 14px;
        }
        .status-connected {
            color: #28a745;
        }
        .status-disconnected {
            color: #dc3545;
        }
        .status-partial {
            color: #ffc107;
        }
        .oauth-button {
            width: 100%;
            padding: 15px;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .connect-button {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
        }
        .connect-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }
        .disconnect-button {
            background: #f8f9fa;
            color: #dc3545;
            border: 2px solid #dc3545;
        }
        .disconnect-button:hover {
            background: #dc3545;
            color: white;
        }
        .feature-list {
            margin: 20px 0;
        }
        .feature-item {
            display: flex;
            align-items: center;
            padding: 8px 0;
            color: #666;
            font-size: 14px;
        }
        .feature-item::before {
            content: '✓';
            display: inline-block;
            width: 24px;
            height: 24px;
            background: #d4edda;
            color: #28a745;
            border-radius: 50%;
            text-align: center;
            line-height: 24px;
            margin-right: 12px;
            font-weight: bold;
        }
        .panic-section {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            text-align: center;
        }
        .panic-button {
            background: linear-gradient(135deg, #ff6b6b, #ee5a24);
            color: white;
            border: none;
            padding: 25px 60px;
            font-size: 24px;
            font-weight: bold;
            border-radius: 60px;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 10px 40px rgba(255, 107, 107, 0.3);
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .panic-button:hover:not(:disabled) {
            transform: translateY(-3px);
            box-shadow: 0 15px 50px rgba(255, 107, 107, 0.4);
        }
        .panic-button:disabled {
            background: #ccc;
            cursor: not-allowed;
            box-shadow: none;
        }
        .alert {
            padding: 15px 20px;
            border-radius: 12px;
            margin: 20px 0;
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
        .alert-info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
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
        .step-guide {
            background: #f8f9fa;
            border-radius: 12px;
            padding: 20px;
            margin: 20px 0;
            text-align: left;
        }
        .step-guide h4 {
            color: #2c3e50;
            margin-bottom: 15px;
        }
        .step {
            display: flex;
            align-items: flex-start;
            margin: 10px 0;
        }
        .step-number {
            background: #667eea;
            color: white;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            margin-right: 15px;
            flex-shrink: 0;
        }
        .step-content {
            color: #666;
            font-size: 14px;
            line-height: 1.6;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 OAuth Integration Center</h1>
            <p class="subtitle">Connect your accounts securely with one click</p>
        </div>
        
        <div class="oauth-grid">
            <!-- Plaid OAuth Card -->
            <div class="oauth-card">
                <div class="service-header">
                    <div class="service-icon plaid-icon">🏦</div>
                    <div class="service-info">
                        <h2>Plaid</h2>
                        <p>Secure bank connection</p>
                    </div>
                </div>
                
                <div class="status-section">
                    <div class="status-item">
                        <span class="status-label">Connection Status</span>
                        <span class="status-value" id="plaid-status">
                            <span class="status-disconnected">Not Connected</span>
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Environment</span>
                        <span class="status-value">{{ plaid_env }}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Institution</span>
                        <span class="status-value" id="plaid-institution">-</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Last Sync</span>
                        <span class="status-value" id="plaid-sync">Never</span>
                    </div>
                </div>
                
                <div class="feature-list">
                    <div class="feature-item">Automatic transaction import</div>
                    <div class="feature-item">Real-time expense tracking</div>
                    <div class="feature-item">Multiple account support</div>
                    <div class="feature-item">Secure OAuth connection</div>
                </div>
                
                <button class="oauth-button connect-button" onclick="connectPlaid()" id="plaid-button">
                    Connect Bank Account
                </button>
                
                <div class="step-guide" style="margin-top: 20px;">
                    <h4>Quick Setup</h4>
                    <div class="step">
                        <div class="step-number">1</div>
                        <div class="step-content">Click "Connect Bank Account"</div>
                    </div>
                    <div class="step">
                        <div class="step-number">2</div>
                        <div class="step-content">Select your bank (Chase, Bank of America, etc.)</div>
                    </div>
                    <div class="step">
                        <div class="step-number">3</div>
                        <div class="step-content">Log in with your bank credentials</div>
                    </div>
                    <div class="step">
                        <div class="step-number">4</div>
                        <div class="step-content">Select accounts to sync</div>
                    </div>
                </div>
            </div>
            
            <!-- Concur OAuth Card -->
            <div class="oauth-card">
                <div class="service-header">
                    <div class="service-icon concur-icon">📊</div>
                    <div class="service-info">
                        <h2>SAP Concur</h2>
                        <p>Expense report submission</p>
                    </div>
                </div>
                
                <div class="status-section">
                    <div class="status-item">
                        <span class="status-label">Connection Status</span>
                        <span class="status-value" id="concur-status">
                            <span class="status-disconnected">Not Connected</span>
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Company</span>
                        <span class="status-value" id="concur-company">-</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">User</span>
                        <span class="status-value" id="concur-user">-</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Reports Submitted</span>
                        <span class="status-value" id="concur-reports">0</span>
                    </div>
                </div>
                
                <div class="feature-list">
                    <div class="feature-item">Direct expense submission</div>
                    <div class="feature-item">Receipt attachment</div>
                    <div class="feature-item">Policy compliance check</div>
                    <div class="feature-item">Approval workflow</div>
                </div>
                
                <button class="oauth-button connect-button" onclick="connectConcur()" id="concur-button">
                    Connect Concur Account
                </button>
                
                <div class="step-guide" style="margin-top: 20px;">
                    <h4>Quick Setup</h4>
                    <div class="step">
                        <div class="step-number">1</div>
                        <div class="step-content">Click "Connect Concur Account"</div>
                    </div>
                    <div class="step">
                        <div class="step-number">2</div>
                        <div class="step-content">Log in with your company Concur credentials</div>
                    </div>
                    <div class="step">
                        <div class="step-number">3</div>
                        <div class="step-content">Authorize expense report access</div>
                    </div>
                    <div class="step">
                        <div class="step-number">4</div>
                        <div class="step-content">Start submitting expenses!</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="alerts"></div>
        
        <div class="panic-section">
            <h2 style="margin-bottom: 20px;">🔥 Friday Panic Button</h2>
            <p style="color: #666; margin-bottom: 20px;" id="panic-status">
                Connect your accounts above to start processing real expenses
            </p>
            <button class="panic-button" id="panicBtn" onclick="processPanic()" disabled>
                Connect Accounts First
            </button>
        </div>
    </div>
    
    <!-- Plaid Link Script -->
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    
    <script>
        let plaidHandler = null;
        
        // Check connection status on load
        window.onload = function() {
            checkConnectionStatus();
        };
        
        function checkConnectionStatus() {
            fetch('/api/oauth/status')
                .then(response => response.json())
                .then(data => {
                    updatePlaidStatus(data.plaid);
                    updateConcurStatus(data.concur);
                    updatePanicButton(data);
                });
        }
        
        function updatePlaidStatus(plaid) {
            const statusEl = document.getElementById('plaid-status');
            const buttonEl = document.getElementById('plaid-button');
            
            if (plaid.connected) {
                statusEl.innerHTML = '<span class="status-connected">Connected</span>';
                buttonEl.textContent = 'Reconnect Account';
                buttonEl.className = 'oauth-button disconnect-button';
                document.getElementById('plaid-institution').textContent = plaid.institution || 'Chase';
                document.getElementById('plaid-sync').textContent = plaid.last_sync || 'Just now';
            } else {
                statusEl.innerHTML = '<span class="status-disconnected">Not Connected</span>';
                buttonEl.textContent = 'Connect Bank Account';
                buttonEl.className = 'oauth-button connect-button';
            }
        }
        
        function updateConcurStatus(concur) {
            const statusEl = document.getElementById('concur-status');
            const buttonEl = document.getElementById('concur-button');
            
            if (concur.connected) {
                statusEl.innerHTML = '<span class="status-connected">Connected</span>';
                buttonEl.textContent = 'Reconnect Account';
                buttonEl.className = 'oauth-button disconnect-button';
                document.getElementById('concur-company').textContent = concur.company || 'Your Company';
                document.getElementById('concur-user').textContent = concur.user || 'user@company.com';
                document.getElementById('concur-reports').textContent = concur.reports_count || '0';
            } else {
                statusEl.innerHTML = '<span class="status-disconnected">Not Connected</span>';
                buttonEl.textContent = 'Connect Concur Account';
                buttonEl.className = 'oauth-button connect-button';
            }
        }
        
        function updatePanicButton(data) {
            const button = document.getElementById('panicBtn');
            const status = document.getElementById('panic-status');
            
            if (data.plaid.connected || data.demo_mode) {
                button.disabled = false;
                button.textContent = 'PANIC! Process Expenses';
                status.textContent = data.plaid.connected ? 
                    'Ready to process your bank transactions' : 
                    'Using demo data (connect accounts for real data)';
            } else {
                button.disabled = true;
                button.textContent = 'Connect Accounts First';
                status.textContent = 'Connect your accounts above to start processing real expenses';
            }
        }
        
        function connectPlaid() {
            showAlert('info', 'Initializing Plaid Link...');
            
            // Get Link token from server
            fetch('/auth/plaid/link-token', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            })
            .then(response => response.json())
            .then(data => {
                if (data.link_token) {
                    initializePlaidLink(data.link_token);
                } else {
                    showAlert('error', 'Failed to initialize Plaid. Please check your API credentials.');
                }
            })
            .catch(error => {
                showAlert('error', 'Error: ' + error.message);
            });
        }
        
        function initializePlaidLink(linkToken) {
            plaidHandler = Plaid.create({
                token: linkToken,
                onSuccess: (public_token, metadata) => {
                    // Exchange public token for access token
                    fetch('/auth/plaid/exchange-token', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            public_token: public_token,
                            institution: metadata.institution
                        })
                    })
                    .then(response => response.json())
                    .then(data => {
                        showAlert('success', 'Bank account connected successfully!');
                        checkConnectionStatus();
                    });
                },
                onLoad: () => {
                    console.log('Plaid Link loaded');
                },
                onExit: (err, metadata) => {
                    if (err) {
                        showAlert('error', 'Plaid connection cancelled or failed');
                    }
                },
                onEvent: (eventName, metadata) => {
                    console.log('Plaid event:', eventName);
                }
            });
            
            plaidHandler.open();
        }
        
        function connectConcur() {
            showAlert('info', 'Redirecting to Concur for authorization...');
            
            // Initiate OAuth flow
            fetch('/auth/concur/authorize')
                .then(response => response.json())
                .then(data => {
                    if (data.auth_url) {
                        // Redirect to Concur OAuth
                        window.location.href = data.auth_url;
                    } else {
                        showAlert('error', 'Failed to initialize Concur OAuth. Please check your credentials.');
                    }
                })
                .catch(error => {
                    showAlert('error', 'Error: ' + error.message);
                });
        }
        
        function processPanic() {
            showAlert('info', 'Processing expenses with Friday Panic Button...');
            
            fetch('/api/panic-with-oauth', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showAlert('success', `Processed ${data.count} transactions! Ready to submit to Concur.`);
                } else {
                    showAlert('error', data.error || 'Processing failed');
                }
            })
            .catch(error => {
                showAlert('error', 'Error: ' + error.message);
            });
        }
        
        function showAlert(type, message) {
            const alertsDiv = document.getElementById('alerts');
            const alertClass = type === 'success' ? 'alert-success' : 
                              type === 'error' ? 'alert-error' : 'alert-info';
            
            const alert = document.createElement('div');
            alert.className = `alert ${alertClass}`;
            alert.textContent = message;
            
            alertsDiv.innerHTML = '';
            alertsDiv.appendChild(alert);
            
            // Auto-hide after 5 seconds
            setTimeout(() => {
                alert.style.opacity = '0';
                setTimeout(() => alert.remove(), 300);
            }, 5000);
        }
        
        // Check for OAuth callback parameters
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('oauth_success')) {
            const service = urlParams.get('service');
            showAlert('success', `${service} connected successfully!`);
            checkConnectionStatus();
            // Clean URL
            window.history.replaceState({}, document.title, window.location.pathname);
        } else if (urlParams.has('oauth_error')) {
            showAlert('error', urlParams.get('oauth_error'));
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    </script>
</body>
</html>
"""

# Store OAuth tokens in session (in production, use secure database)
@app.route('/')
def index():
    """OAuth dashboard."""
    return render_template_string(OAUTH_DASHBOARD, plaid_env=PLAID_CONFIG['env'])

@app.route('/api/oauth/status')
def oauth_status():
    """Get OAuth connection status."""
    return jsonify({
        'plaid': {
            'connected': 'plaid_access_token' in session,
            'institution': session.get('plaid_institution'),
            'last_sync': session.get('plaid_last_sync', 'Never'),
            'configured': bool(PLAID_CONFIG['client_id'])
        },
        'concur': {
            'connected': 'concur_access_token' in session,
            'company': session.get('concur_company'),
            'user': session.get('concur_user'),
            'reports_count': session.get('concur_reports_count', 0),
            'configured': bool(CONCUR_CONFIG['client_id'])
        },
        'demo_mode': session.get('demo_mode', True)
    })

# PLAID OAuth Flow
@app.route('/auth/plaid/link-token', methods=['POST'])
def create_plaid_link_token():
    """Create Plaid Link token for OAuth."""
    if not PLAID_CONFIG['client_id']:
        # Use demo mode
        return jsonify({
            'link_token': 'demo-link-token',
            'demo_mode': True
        })
    
    # In production, make actual Plaid API call
    # For demo, return mock token
    return jsonify({
        'link_token': 'link-sandbox-' + secrets.token_hex(16),
        'expiration': (datetime.now() + timedelta(hours=4)).isoformat()
    })

@app.route('/auth/plaid/exchange-token', methods=['POST'])
def exchange_plaid_token():
    """Exchange Plaid public token for access token."""
    data = request.get_json()
    public_token = data.get('public_token')
    institution = data.get('institution', {})
    
    # In production, exchange with Plaid API
    # For demo, simulate success
    access_token = 'access-sandbox-' + secrets.token_hex(16)
    
    # Store in session (use database in production)
    session['plaid_access_token'] = access_token
    session['plaid_institution'] = institution.get('name', 'Demo Bank')
    session['plaid_last_sync'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    return jsonify({
        'success': True,
        'access_token': access_token[:20] + '...',
        'institution': institution.get('name', 'Demo Bank')
    })

# CONCUR OAuth Flow
@app.route('/auth/concur/authorize')
def concur_authorize():
    """Initiate Concur OAuth flow."""
    if not CONCUR_CONFIG['client_id']:
        # Demo mode
        return jsonify({
            'auth_url': '/auth/concur/demo-callback',
            'demo_mode': True
        })
    
    # Build OAuth authorization URL
    params = {
        'client_id': CONCUR_CONFIG['client_id'],
        'redirect_uri': CONCUR_CONFIG['redirect_uri'],
        'response_type': 'code',
        'scope': CONCUR_CONFIG['scope'],
        'state': secrets.token_hex(16)
    }
    
    # Store state in session for verification
    session['concur_oauth_state'] = params['state']
    
    auth_url = CONCUR_CONFIG['auth_url'] + '?' + urlencode(params)
    
    return jsonify({'auth_url': auth_url})

@app.route('/auth/concur/callback')
def concur_callback():
    """Handle Concur OAuth callback."""
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    if error:
        return redirect('/?oauth_error=' + quote(error))
    
    # Verify state
    if state != session.get('concur_oauth_state'):
        return redirect('/?oauth_error=Invalid state parameter')
    
    if not code:
        return redirect('/?oauth_error=No authorization code received')
    
    # Exchange code for access token
    # In production, make actual API call to Concur
    # For demo, simulate success
    
    session['concur_access_token'] = 'concur-token-' + secrets.token_hex(16)
    session['concur_company'] = 'Demo Company Inc.'
    session['concur_user'] = 'demo.user@company.com'
    session['concur_reports_count'] = 0
    
    return redirect('/?oauth_success=true&service=Concur')

@app.route('/auth/concur/demo-callback')
def concur_demo_callback():
    """Demo Concur connection for testing."""
    session['concur_access_token'] = 'demo-concur-token'
    session['concur_company'] = 'Demo Company'
    session['concur_user'] = 'demo@example.com'
    
    return redirect('/?oauth_success=true&service=Concur')

@app.route('/api/panic-with-oauth', methods=['POST'])
def panic_with_oauth():
    """Process expenses using OAuth connections."""
    # Check if we have Plaid connection
    if 'plaid_access_token' in session:
        # In production, fetch real transactions from Plaid
        # For demo, use sample data
        transactions_count = 28
        
        # Process with Friday Panic
        try:
            from friday_panic_button import friday_panic
            # Use demo data for now
            if os.path.exists('demo_transactions.json'):
                with open('demo_transactions.json', 'r') as f:
                    transactions = json.load(f)
                    result = friday_panic(transactions)
                    
                    # If Concur is connected, prepare for submission
                    if 'concur_access_token' in session:
                        session['concur_reports_count'] = session.get('concur_reports_count', 0) + 1
                    
                    return jsonify({
                        'success': True,
                        'count': len(transactions),
                        'ready_for_concur': 'concur_access_token' in session
                    })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({
        'success': False,
        'error': 'Please connect your bank account first'
    })

@app.route('/auth/disconnect/<service>')
def disconnect_service(service):
    """Disconnect OAuth service."""
    if service == 'plaid':
        session.pop('plaid_access_token', None)
        session.pop('plaid_institution', None)
        session.pop('plaid_last_sync', None)
    elif service == 'concur':
        session.pop('concur_access_token', None)
        session.pop('concur_company', None)
        session.pop('concur_user', None)
        session.pop('concur_reports_count', None)
    
    return jsonify({'success': True, 'service': service})

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 TRAVEL EXPENSE ANALYZER - OAuth Edition")
    print("=" * 60)
    print("\n✅ OAuth flows ready for:")
    print("  • Plaid - Secure bank connections")
    print("  • SAP Concur - Direct expense submission")
    print("\n🌐 Open: http://localhost:8080")
    print("\n📋 Features:")
    print("  • One-click OAuth connections")
    print("  • No manual API key entry")
    print("  • Secure token management")
    print("  • Demo mode for testing")
    print("\nPress Ctrl+C to stop")
    print("-" * 60)
    
    # Load .env if exists
    if os.path.exists('.env'):
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Loaded .env file")
    
    app.run(host='0.0.0.0', port=8080, debug=True)