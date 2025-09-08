#!/usr/bin/env python3
"""
Plaid OAuth Setup Script
This script helps you configure Plaid OAuth integration by validating your API keys.
"""

import os
import sys
from dotenv import load_dotenv, set_key

def setup_plaid_oauth():
    """Interactive setup for Plaid OAuth configuration."""
    
    print("=" * 60)
    print("🏦 PLAID OAUTH SETUP")
    print("=" * 60)
    print()
    
    # Load existing .env if it exists
    env_file = ".env"
    if not os.path.exists(env_file):
        # Copy from example
        if os.path.exists(".env.example"):
            with open(".env.example", "r") as src, open(".env", "w") as dst:
                dst.write(src.read())
            print("✅ Created .env file from .env.example")
        else:
            print("❌ No .env.example found. Please create .env file manually.")
            return False
    
    load_dotenv()
    
    print("📝 Current Plaid Configuration:")
    print(f"   Client ID: {os.getenv('PLAID_CLIENT_ID', 'Not set')}")
    print(f"   Secret: {'*' * 8 if os.getenv('PLAID_SECRET') else 'Not set'}")
    print(f"   Environment: {os.getenv('PLAID_ENV', 'sandbox')}")
    print()
    
    # Prompt for configuration
    print("🔧 Enter your Plaid API credentials:")
    print("   Get them from: https://dashboard.plaid.com/signup")
    print()
    
    client_id = input("Plaid Client ID: ").strip()
    secret = input("Plaid Secret: ").strip()
    
    env_options = {
        '1': 'sandbox',
        '2': 'development', 
        '3': 'production'
    }
    
    print("\nEnvironment options:")
    for key, value in env_options.items():
        print(f"  {key}. {value}")
    
    env_choice = input("Choose environment (1-3) [1]: ").strip() or '1'
    environment = env_options.get(env_choice, 'sandbox')
    
    if not client_id or not secret:
        print("❌ Client ID and Secret are required!")
        return False
    
    # Update .env file
    try:
        set_key(env_file, "PLAID_CLIENT_ID", client_id)
        set_key(env_file, "PLAID_SECRET", secret)
        set_key(env_file, "PLAID_ENV", environment)
        
        print()
        print("✅ Configuration saved to .env file")
        print()
        
        # Test the configuration
        print("🧪 Testing Plaid connection...")
        
        try:
            from plaid_integration import get_plaid_manager
            
            # Reload environment with new values
            load_dotenv(override=True)
            
            manager = get_plaid_manager()
            if manager:
                # Try to create a link token
                link_response = manager.create_link_token("test_user")
                if link_response:
                    print("✅ Plaid connection test successful!")
                    print(f"   Link token created: {link_response['link_token'][:20]}...")
                    print()
                    print("🎉 SETUP COMPLETE!")
                    print()
                    print("Next steps:")
                    print("1. Start your application: python expense_web_app.py")
                    print("2. Go to the dashboard and click 'Connect Bank'")
                    print("3. Follow the Plaid Link flow to connect your Chase account")
                    return True
                else:
                    print("❌ Failed to create link token. Check your credentials.")
            else:
                print("❌ Failed to initialize Plaid manager.")
                
        except ImportError:
            print("⚠️  Plaid library not available. Install with:")
            print("   pip install plaid-python")
            print()
            print("✅ Configuration saved. Install dependencies and try again.")
            return True
            
        except Exception as e:
            print(f"❌ Connection test failed: {e}")
            print("   Check your credentials and try again.")
    
    except Exception as e:
        print(f"❌ Failed to save configuration: {e}")
        return False
    
    return False

def main():
    """Main setup function."""
    
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print("Plaid OAuth Setup Script")
        print("Usage: python setup_plaid_oauth.py")
        print()
        print("This script will guide you through setting up Plaid OAuth integration.")
        print("You'll need your Plaid Client ID and Secret from dashboard.plaid.com")
        return
    
    success = setup_plaid_oauth()
    
    if success:
        print()
        print("🎯 Ready to use Plaid OAuth!")
        print("   Your application can now connect to Chase accounts via Plaid.")
        
    else:
        print()
        print("❌ Setup incomplete. Please try again or check your credentials.")
        sys.exit(1)

if __name__ == "__main__":
    main()