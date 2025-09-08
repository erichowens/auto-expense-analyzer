#!/usr/bin/env python3
"""
Run expense web app on a different port.
"""
import sys
import os

# Set the port via environment variable
os.environ['FLASK_RUN_PORT'] = '5001'

# Import and run the app
from expense_web_app import app

if __name__ == '__main__':
    print("Starting Expense Web App on port 5001...")
    print("Open: http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=True)