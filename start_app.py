#!/usr/bin/env python3
"""
Start the Travel Expense Analyzer application.
"""

import os
import sys
from pathlib import Path

def check_requirements():
    """Check if all requirements are installed."""
    missing = []
    
    required_packages = [
        'flask',
        'flask_limiter',
        'pydantic',
        'bleach',
        'dotenv'
    ]
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_').replace('flask_limiter', 'flask_limiter'))
        except ImportError:
            missing.append(package)
    
    if missing:
        print("❌ Missing required packages:")
        for pkg in missing:
            print(f"   - {pkg}")
        print("\n📦 Install them with:")
        print("   pip install -r requirements.txt")
        return False
    
    return True

def setup_environment():
    """Set up the environment."""
    # Create data directory if it doesn't exist
    Path("data").mkdir(exist_ok=True)
    Path("uploads").mkdir(exist_ok=True)
    
    # Check for .env file
    if not os.path.exists('.env'):
        if os.path.exists('.env.example'):
            print("⚠️  No .env file found. Creating from .env.example...")
            import shutil
            shutil.copy('.env.example', '.env')
            print("✅ Created .env file. Please edit it with your credentials if needed.")
        else:
            print("⚠️  No .env file found. Using default settings.")
    
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Environment variables loaded")
    except ImportError:
        print("⚠️  python-dotenv not installed. Using system environment variables.")

def main():
    """Start the application."""
    print("=" * 60)
    print("🚀 STARTING TRAVEL EXPENSE ANALYZER")
    print("=" * 60)
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    # Set up environment
    setup_environment()
    
    # Set default port if not specified
    port = int(os.getenv('PORT', 5000))
    
    print(f"\n✅ Starting Flask application on port {port}...")
    print(f"🌐 Open http://localhost:{port} in your browser")
    print("\n🔥 FRIDAY PANIC BUTTON is ready to save your day!")
    print("\nPress Ctrl+C to stop the server")
    print("-" * 60)
    
    # Import and run the app
    try:
        from expense_web_app import app
        
        # Run the app
        app.run(
            host='0.0.0.0',  # Bind to all interfaces
            port=port,
            debug=os.getenv('FLASK_ENV') == 'development',
            use_reloader=False  # Disable reloader to avoid issues
        )
    except ImportError as e:
        print(f"❌ Error importing app: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error starting app: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()