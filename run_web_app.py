#!/usr/bin/env python3
"""
Startup script for the Travel Expense Analyzer Web Application
"""

import os
import sys
from pathlib import Path

def check_setup():
    """Check if the basic setup is complete."""
    print("🔍 Checking setup...")
    
    # Check if required directories exist
    required_dirs = ['templates', 'static', 'uploads', 'data']
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            print(f"📁 Creating directory: {dir_name}")
            os.makedirs(dir_name, exist_ok=True)
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        print("⚠️  No .env file found. Please create one with your API credentials.")
        print("   You can use .env.example as a template.")
        print("   Visit http://localhost:5000/setup for configuration help.")
    else:
        print("✅ .env file found")
    
    # Check if dependencies are installed
    try:
        import flask
        print("✅ Flask is installed")
    except ImportError:
        print("❌ Flask not found. Please run: pip install -r requirements.txt")
        return False
    
    return True

def run_production_server():
    """Run the application with Gunicorn for production."""
    try:
        import gunicorn.app.wsgiapp as wsgi
        
        print("🚀 Starting production server with Gunicorn...")
        
        # Gunicorn configuration
        sys.argv = [
            'gunicorn',
            '--bind', '0.0.0.0:5000',
            '--workers', '4',
            '--worker-class', 'sync',
            '--worker-connections', '1000',
            '--max-requests', '1000',
            '--max-requests-jitter', '100',
            '--timeout', '120',
            '--keep-alive', '2',
            '--preload',
            '--access-logfile', '-',
            '--error-logfile', '-',
            '--log-level', 'info',
            'expense_web_app:app'
        ]
        
        wsgi.run()
        
    except ImportError:
        print("⚠️  Gunicorn not available for production deployment.")
        print("   Install with: pip install gunicorn")
        print("   Falling back to development server...")
        return False
    
    return True

def run_development_server():
    """Run the Flask development server."""
    from expense_web_app import app
    
    print("🌐 Starting development server...")
    print("   Access the application at: http://localhost:5000")
    print("   Press Ctrl+C to stop the server")
    
    app.config['DEBUG'] = True
    app.config['ENV'] = 'development'
    
    app.run(debug=True, host='0.0.0.0', port=5000)

def main():
    print("🚀 Travel Expense Analyzer Web Application")
    print("=" * 50)
    
    if not check_setup():
        print("\n❌ Setup incomplete. Please fix the issues above and try again.")
        return
    
    print("\n✅ Setup looks good!")
    print("\n📝 What you can do:")
    print("   • Dashboard: http://localhost:5000/")
    print("   • Setup Guide: http://localhost:5000/setup")
    print("   • Trip Review: http://localhost:5000/trips")
    print("   • Receipt Manager: http://localhost:5000/receipts")
    print("   • Concur Submission: http://localhost:5000/concur")
    
    print("\n🔧 Configuration needed:")
    print("   1. Plaid API credentials (for bank transaction fetching)")
    print("   2. SAP Concur API access (requires company approval)")
    print("   3. Email access (optional, for hotel confirmations)")
    print("   4. Hotel loyalty accounts (optional, for folio downloads)")
    
    # Check if we're in production mode
    is_production = os.getenv('FLASK_ENV') == 'production'
    
    print("=" * 50)
    
    # Import and run the Flask app
    try:
        if is_production:
            if not run_production_server():
                run_development_server()
        else:
            run_development_server()
            
    except ImportError as e:
        print(f"❌ Error importing web application: {e}")
        print("   Make sure all files are in the correct location.")
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped. Goodbye!")
    except Exception as e:
        print(f"❌ Error starting server: {e}")

if __name__ == "__main__":
    main()