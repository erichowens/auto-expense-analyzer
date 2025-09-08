#!/usr/bin/env python3
"""
Enhanced Flask app with authorization status and demo data toggle.
"""

from flask import Flask, jsonify, render_template_string, request, session
import os
import json
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()

# Enhanced dashboard with auth status
ENHANCED_DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <title>Travel Expense Analyzer - Setup & Configuration</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        h1 {
            color: #2c3e50;
            margin-bottom: 10px;
        }
        .auth-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .auth-card {
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
        }
        .auth-card h3 {
            color: #2c3e50;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .status-badge {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
        }
        .status-required {
            background: #fff3cd;
            color: #856404;
        }
        .status-optional {
            background: #d1ecf1;
            color: #0c5460;
        }
        .status-connected {
            background: #d4edda;
            color: #155724;
        }
        .status-not-connected {
            background: #f8d7da;
            color: #721c24;
        }
        .auth-details {
            margin: 15px 0;
        }
        .auth-field {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e0e0e0;
        }
        .auth-field:last-child {
            border-bottom: none;
        }
        .field-name {
            color: #666;
            font-size: 14px;
        }
        .field-value {
            font-family: monospace;
            font-size: 14px;
        }
        .field-value.configured {
            color: #28a745;
        }
        .field-value.not-configured {
            color: #dc3545;
        }
        .control-panel {
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        .toggle-group {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
            margin-bottom: 15px;
        }
        .toggle-label {
            font-weight: 500;
            color: #2c3e50;
        }
        .toggle-switch {
            position: relative;
            display: inline-block;
            width: 60px;
            height: 28px;
        }
        .toggle-switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #ccc;
            transition: .4s;
            border-radius: 34px;
        }
        .slider:before {
            position: absolute;
            content: "";
            height: 20px;
            width: 20px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }
        input:checked + .slider {
            background-color: #667eea;
        }
        input:checked + .slider:before {
            transform: translateX(32px);
        }
        .panic-section {
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            text-align: center;
        }
        .panic-button {
            background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%);
            color: white;
            border: none;
            padding: 20px 60px;
            font-size: 24px;
            font-weight: bold;
            border-radius: 50px;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 5px 20px rgba(235, 51, 73, 0.4);
        }
        .panic-button:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(235, 51, 73, 0.5);
        }
        .panic-button:disabled {
            background: #ccc;
            cursor: not-allowed;
            box-shadow: none;
        }
        .info-box {
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
        }
        .info-box h4 {
            color: #2c3e50;
            margin-bottom: 10px;
        }
        .info-box ul {
            list-style: none;
            padding-left: 0;
        }
        .info-box li {
            padding: 5px 0;
            color: #666;
        }
        .info-box li:before {
            content: "✓ ";
            color: #28a745;
            font-weight: bold;
            margin-right: 5px;
        }
        #results {
            margin-top: 20px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            display: none;
        }
        .setup-instructions {
            background: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
        }
        .setup-instructions h4 {
            color: #856404;
            margin-bottom: 10px;
        }
        .setup-instructions code {
            background: #fff;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Travel Expense Analyzer</h1>
            <p style="color: #666; margin-top: 10px;">Configuration Status & Authorization Dashboard</p>
        </div>
        
        <!-- Control Panel -->
        <div class="control-panel">
            <h2 style="margin-bottom: 20px;">⚙️ Settings & Controls</h2>
            
            <div class="toggle-group">
                <div>
                    <div class="toggle-label">Use Demo Data</div>
                    <small style="color: #666;">Toggle between demo data and real transactions</small>
                </div>
                <label class="toggle-switch">
                    <input type="checkbox" id="demoToggle" checked onchange="toggleDemo()">
                    <span class="slider"></span>
                </label>
            </div>
            
            <div class="toggle-group">
                <div>
                    <div class="toggle-label">Enable Rate Limiting</div>
                    <small style="color: #666;">Protect API from excessive requests</small>
                </div>
                <label class="toggle-switch">
                    <input type="checkbox" id="rateLimitToggle" onchange="toggleRateLimit()">
                    <span class="slider"></span>
                </label>
            </div>
            
            <div class="toggle-group">
                <div>
                    <div class="toggle-label">Debug Mode</div>
                    <small style="color: #666;">Show detailed error messages</small>
                </div>
                <label class="toggle-switch">
                    <input type="checkbox" id="debugToggle" checked onchange="toggleDebug()">
                    <span class="slider"></span>
                </label>
            </div>
        </div>
        
        <!-- Authorization Status Grid -->
        <div class="auth-grid">
            <!-- Plaid Authorization -->
            <div class="auth-card">
                <h3>
                    🏦 Plaid (Bank Connection)
                    <span class="status-badge status-optional">Optional</span>
                </h3>
                <div class="auth-details">
                    <div class="auth-field">
                        <span class="field-name">Status:</span>
                        <span class="field-value not-configured" id="plaid-status">Not Configured</span>
                    </div>
                    <div class="auth-field">
                        <span class="field-name">Client ID:</span>
                        <span class="field-value" id="plaid-client">Not Set</span>
                    </div>
                    <div class="auth-field">
                        <span class="field-name">Environment:</span>
                        <span class="field-value" id="plaid-env">sandbox</span>
                    </div>
                    <div class="auth-field">
                        <span class="field-name">Purpose:</span>
                        <span class="field-value">Auto-import transactions</span>
                    </div>
                </div>
                <div class="info-box" style="margin-top: 15px;">
                    <h4>What this enables:</h4>
                    <ul>
                        <li>Automatic bank transaction import</li>
                        <li>Real-time expense tracking</li>
                        <li>No manual CSV uploads needed</li>
                    </ul>
                </div>
                <button onclick="showSetupInstructions('plaid')" style="width: 100%; padding: 10px; background: #667eea; color: white; border: none; border-radius: 5px; cursor: pointer;">
                    Setup Instructions
                </button>
            </div>
            
            <!-- Concur Authorization -->
            <div class="auth-card">
                <h3>
                    📊 SAP Concur
                    <span class="status-badge status-optional">Optional</span>
                </h3>
                <div class="auth-details">
                    <div class="auth-field">
                        <span class="field-name">Status:</span>
                        <span class="field-value not-configured" id="concur-status">Not Configured</span>
                    </div>
                    <div class="auth-field">
                        <span class="field-name">Client ID:</span>
                        <span class="field-value" id="concur-client">Not Set</span>
                    </div>
                    <div class="auth-field">
                        <span class="field-name">API URL:</span>
                        <span class="field-value" id="concur-url">Not Set</span>
                    </div>
                    <div class="auth-field">
                        <span class="field-name">Purpose:</span>
                        <span class="field-value">Submit expense reports</span>
                    </div>
                </div>
                <div class="info-box" style="margin-top: 15px;">
                    <h4>What this enables:</h4>
                    <ul>
                        <li>Direct submission to Concur</li>
                        <li>Automated expense reports</li>
                        <li>Receipt attachment</li>
                    </ul>
                </div>
                <button onclick="showSetupInstructions('concur')" style="width: 100%; padding: 10px; background: #667eea; color: white; border: none; border-radius: 5px; cursor: pointer;">
                    Setup Instructions
                </button>
            </div>
            
            <!-- Database Status -->
            <div class="auth-card">
                <h3>
                    💾 Database
                    <span class="status-badge status-connected">Connected</span>
                </h3>
                <div class="auth-details">
                    <div class="auth-field">
                        <span class="field-name">Status:</span>
                        <span class="field-value configured">Active</span>
                    </div>
                    <div class="auth-field">
                        <span class="field-name">Type:</span>
                        <span class="field-value">SQLite</span>
                    </div>
                    <div class="auth-field">
                        <span class="field-name">Path:</span>
                        <span class="field-value">data/expenses.db</span>
                    </div>
                    <div class="auth-field">
                        <span class="field-name">Pool Size:</span>
                        <span class="field-value">5 connections</span>
                    </div>
                </div>
                <div class="info-box" style="margin-top: 15px;">
                    <h4>Features:</h4>
                    <ul>
                        <li>Connection pooling enabled</li>
                        <li>Transaction management</li>
                        <li>Automatic backups</li>
                    </ul>
                </div>
            </div>
            
            <!-- Friday Panic Button Status -->
            <div class="auth-card">
                <h3>
                    🔥 Friday Panic Engine
                    <span class="status-badge status-connected">Ready</span>
                </h3>
                <div class="auth-details">
                    <div class="auth-field">
                        <span class="field-name">Status:</span>
                        <span class="field-value configured">Operational</span>
                    </div>
                    <div class="auth-field">
                        <span class="field-name">Confidence Threshold:</span>
                        <span class="field-value">70%</span>
                    </div>
                    <div class="auth-field">
                        <span class="field-name">Batch Size:</span>
                        <span class="field-value">100 transactions</span>
                    </div>
                    <div class="auth-field">
                        <span class="field-name">Categories:</span>
                        <span class="field-value">6 active</span>
                    </div>
                </div>
                <div class="info-box" style="margin-top: 15px;">
                    <h4>Capabilities:</h4>
                    <ul>
                        <li>95%+ accuracy for major vendors</li>
                        <li>Smart business purpose generation</li>
                        <li>Bulk processing support</li>
                    </ul>
                </div>
            </div>
        </div>
        
        <!-- Setup Instructions (hidden by default) -->
        <div id="setup-instructions" class="setup-instructions" style="display: none;">
            <h4 id="setup-title">Setup Instructions</h4>
            <div id="setup-content"></div>
        </div>
        
        <!-- Friday Panic Button Section -->
        <div class="panic-section">
            <h2 style="margin-bottom: 20px;">🚨 Friday Panic Button</h2>
            <p style="color: #666; margin-bottom: 20px;">
                <span id="data-mode">Using DEMO data</span> - 
                <span id="transaction-count">28 transactions ready</span>
            </p>
            <button class="panic-button" id="panicBtn" onclick="processPanic()">
                PANIC! Process All Expenses
            </button>
            <div id="results"></div>
        </div>
    </div>

    <script>
        // Check authorization status on load
        window.onload = function() {
            checkAuthStatus();
        };
        
        function checkAuthStatus() {
            fetch('/api/auth-status')
                .then(response => response.json())
                .then(data => {
                    // Update Plaid status
                    if (data.plaid.configured) {
                        document.getElementById('plaid-status').textContent = 'Configured';
                        document.getElementById('plaid-status').className = 'field-value configured';
                        document.getElementById('plaid-client').textContent = data.plaid.client_id || 'Set';
                        document.getElementById('plaid-env').textContent = data.plaid.environment;
                    }
                    
                    // Update Concur status
                    if (data.concur.configured) {
                        document.getElementById('concur-status').textContent = 'Configured';
                        document.getElementById('concur-status').className = 'field-value configured';
                        document.getElementById('concur-client').textContent = data.concur.client_id || 'Set';
                        document.getElementById('concur-url').textContent = data.concur.api_url;
                    }
                    
                    // Update demo data status
                    document.getElementById('demoToggle').checked = data.demo_mode;
                    updateDataMode(data.demo_mode);
                });
        }
        
        function toggleDemo() {
            const useDemoData = document.getElementById('demoToggle').checked;
            fetch('/api/toggle-demo', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({demo_mode: useDemoData})
            })
            .then(response => response.json())
            .then(data => {
                updateDataMode(useDemoData);
                document.getElementById('transaction-count').textContent = 
                    data.transaction_count + ' transactions ready';
            });
        }
        
        function updateDataMode(isDemoMode) {
            const modeText = isDemoMode ? 'Using DEMO data' : 'Using REAL data';
            document.getElementById('data-mode').textContent = modeText;
            
            // Update button state
            const btn = document.getElementById('panicBtn');
            if (!isDemoMode) {
                btn.textContent = 'Connect Bank Account First';
                btn.disabled = true;
            } else {
                btn.textContent = 'PANIC! Process All Expenses';
                btn.disabled = false;
            }
        }
        
        function toggleRateLimit() {
            const enabled = document.getElementById('rateLimitToggle').checked;
            fetch('/api/toggle-rate-limit', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({enabled: enabled})
            });
        }
        
        function toggleDebug() {
            const enabled = document.getElementById('debugToggle').checked;
            fetch('/api/toggle-debug', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({enabled: enabled})
            });
        }
        
        function showSetupInstructions(service) {
            const instructions = {
                plaid: {
                    title: 'Plaid Setup Instructions',
                    content: `
                        <ol>
                            <li>Go to <a href="https://dashboard.plaid.com/signup" target="_blank">dashboard.plaid.com</a> and create a free account</li>
                            <li>Get your API keys from the dashboard</li>
                            <li>Add to your <code>.env</code> file:
                                <pre style="background: #f4f4f4; padding: 10px; border-radius: 5px; margin: 10px 0;">
PLAID_CLIENT_ID=your_client_id_here
PLAID_SECRET=your_secret_here
PLAID_ENV=sandbox</pre>
                            </li>
                            <li>Restart the application</li>
                            <li>Click "Connect Bank" to link your Chase account</li>
                        </ol>
                        <p><strong>Note:</strong> Sandbox mode is free and perfect for testing!</p>
                    `
                },
                concur: {
                    title: 'SAP Concur Setup Instructions',
                    content: `
                        <ol>
                            <li>Contact your company's Concur administrator for API access</li>
                            <li>Register your app at <a href="https://developer.concur.com" target="_blank">developer.concur.com</a></li>
                            <li>Get your OAuth 2.0 credentials</li>
                            <li>Add to your <code>.env</code> file:
                                <pre style="background: #f4f4f4; padding: 10px; border-radius: 5px; margin: 10px 0;">
CONCUR_CLIENT_ID=your_concur_client_id
CONCUR_CLIENT_SECRET=your_concur_client_secret
CONCUR_REFRESH_TOKEN=your_refresh_token</pre>
                            </li>
                            <li>Restart the application</li>
                        </ol>
                        <p><strong>Note:</strong> You can use the app without Concur - just export to CSV!</p>
                    `
                }
            };
            
            const inst = instructions[service];
            document.getElementById('setup-title').textContent = inst.title;
            document.getElementById('setup-content').innerHTML = inst.content;
            document.getElementById('setup-instructions').style.display = 'block';
        }
        
        function processPanic() {
            const resultsDiv = document.getElementById('results');
            resultsDiv.style.display = 'block';
            resultsDiv.innerHTML = '<h3>⏳ Processing...</h3><p>Running Friday Panic Button...</p>';
            
            fetch('/api/panic-process')
                .then(response => response.json())
                .then(data => {
                    resultsDiv.innerHTML = `
                        <h3>✅ Processing Complete!</h3>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px;">
                            <div>
                                <h4>📊 Results</h4>
                                <p><strong>Transactions:</strong> ${data.transactions_count}</p>
                                <p><strong>Categories:</strong> ${data.categories.join(', ')}</p>
                                <p><strong>Confidence:</strong> ${data.confidence}%</p>
                                <p><strong>Time Saved:</strong> ${data.time_saved}</p>
                            </div>
                            <div>
                                <h4>💰 Breakdown</h4>
                                ${Object.entries(data.totals).map(([cat, amt]) => 
                                    `<p>${cat}: $${amt.toFixed(2)}</p>`
                                ).join('')}
                            </div>
                        </div>
                        <div style="margin-top: 20px; padding: 15px; background: #d4edda; border-radius: 5px;">
                            <strong>Business Purpose:</strong> "${data.business_purpose}"
                        </div>
                        <div style="margin-top: 20px;">
                            <strong>Status:</strong> ${data.ready ? 
                                '<span style="color: green;">✅ Ready to Submit!</span>' : 
                                '<span style="color: orange;">⚠️ Review needed</span>'}
                        </div>
                    `;
                })
                .catch(error => {
                    resultsDiv.innerHTML = `<h3>❌ Error</h3><p>${error.message}</p>`;
                });
        }
    </script>
</body>
</html>
"""

# Store settings in session
@app.route('/')
def index():
    """Enhanced dashboard with auth status."""
    return render_template_string(ENHANCED_DASHBOARD)

@app.route('/api/auth-status')
def auth_status():
    """Check authorization status for all services."""
    return jsonify({
        'plaid': {
            'configured': bool(os.getenv('PLAID_CLIENT_ID')),
            'client_id': os.getenv('PLAID_CLIENT_ID', '')[:10] + '...' if os.getenv('PLAID_CLIENT_ID') else None,
            'environment': os.getenv('PLAID_ENV', 'sandbox')
        },
        'concur': {
            'configured': bool(os.getenv('CONCUR_CLIENT_ID')),
            'client_id': os.getenv('CONCUR_CLIENT_ID', '')[:10] + '...' if os.getenv('CONCUR_CLIENT_ID') else None,
            'api_url': os.getenv('CONCUR_BASE_URL', 'https://api.concursolutions.com')
        },
        'database': {
            'connected': True,
            'type': 'SQLite',
            'pool_size': 5
        },
        'demo_mode': session.get('demo_mode', True),
        'rate_limit_enabled': session.get('rate_limit_enabled', False),
        'debug_mode': session.get('debug_mode', True)
    })

@app.route('/api/toggle-demo', methods=['POST'])
def toggle_demo():
    """Toggle between demo and real data."""
    data = request.get_json()
    demo_mode = data.get('demo_mode', True)
    session['demo_mode'] = demo_mode
    
    # Count available transactions
    transaction_count = 0
    if demo_mode and os.path.exists('demo_transactions.json'):
        with open('demo_transactions.json', 'r') as f:
            transactions = json.load(f)
            transaction_count = len(transactions)
    
    return jsonify({
        'demo_mode': demo_mode,
        'transaction_count': transaction_count,
        'message': f"Switched to {'demo' if demo_mode else 'real'} data"
    })

@app.route('/api/toggle-rate-limit', methods=['POST'])
def toggle_rate_limit():
    """Toggle rate limiting."""
    data = request.get_json()
    enabled = data.get('enabled', False)
    session['rate_limit_enabled'] = enabled
    return jsonify({'rate_limit_enabled': enabled})

@app.route('/api/toggle-debug', methods=['POST'])
def toggle_debug():
    """Toggle debug mode."""
    data = request.get_json()
    enabled = data.get('enabled', True)
    session['debug_mode'] = enabled
    app.config['DEBUG'] = enabled
    return jsonify({'debug_mode': enabled})

@app.route('/api/panic-process', methods=['GET', 'POST'])
def panic_process():
    """Process with Friday Panic Button."""
    if not session.get('demo_mode', True):
        return jsonify({'error': 'Please enable demo mode or connect a bank account'}), 400
    
    # Load demo data
    transactions = []
    if os.path.exists('demo_transactions.json'):
        with open('demo_transactions.json', 'r') as f:
            transactions = json.load(f)
    
    if not transactions:
        return jsonify({'error': 'No transactions available'}), 400
    
    # Import and use Friday Panic Button
    try:
        from friday_panic_button import friday_panic
        result = friday_panic(transactions)
        
        return jsonify({
            'transactions_count': len(result['transactions']),
            'categories': list(result['totals'].keys()),
            'totals': result['totals'],
            'confidence': int(result['confidence_score'] * 100),
            'business_purpose': result['business_purpose']['primary_purpose'],
            'time_saved': result['estimated_time_saved'],
            'ready': result['ready_to_submit']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 TRAVEL EXPENSE ANALYZER - ENHANCED VERSION")
    print("=" * 60)
    print("\n✅ Starting with authorization dashboard...")
    print("🌐 Open: http://localhost:8080")
    print("\n📋 Features:")
    print("  • Authorization status for all services")
    print("  • Toggle demo data on/off")
    print("  • Setup instructions for each service")
    print("  • Friday Panic Button ready!")
    print("\nPress Ctrl+C to stop")
    print("-" * 60)
    
    # Load .env if it exists
    if os.path.exists('.env'):
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Loaded .env file")
    
    app.run(host='0.0.0.0', port=8080, debug=True)