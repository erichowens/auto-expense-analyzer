#!/usr/bin/env python3
"""
Generate demo data for testing the Friday Panic Button.
"""

import json
from datetime import datetime, timedelta
import random

def generate_demo_transactions():
    """Generate realistic demo transactions."""
    transactions = []
    
    # Trip 1: San Francisco (Jan 2024)
    transactions.extend([
        {'date': '2024-01-15', 'description': 'UNITED AIRLINES', 'amount': 523.40, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-15', 'description': 'MARRIOTT UNION SQUARE', 'amount': 289.00, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-15', 'description': 'UBER FROM AIRPORT', 'amount': 47.23, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-16', 'description': 'STARBUCKS MARKET ST', 'amount': 8.45, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-16', 'description': 'THE PALM RESTAURANT', 'amount': 287.50, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-17', 'description': 'MARRIOTT UNION SQUARE', 'amount': 289.00, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-17', 'description': 'LUNCH - CHIPOTLE', 'amount': 14.50, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-18', 'description': 'UNITED AIRLINES', 'amount': 523.40, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-18', 'description': 'SFO AIRPORT PARKING', 'amount': 45.00, 'location': 'SAN FRANCISCO, CA'},
    ])
    
    # Trip 2: New York (Feb 2024)
    transactions.extend([
        {'date': '2024-02-10', 'description': 'DELTA AIR LINES', 'amount': 412.30, 'location': 'NEW YORK, NY'},
        {'date': '2024-02-10', 'description': 'HILTON MIDTOWN', 'amount': 359.00, 'location': 'NEW YORK, NY'},
        {'date': '2024-02-11', 'description': 'YELLOW CAB', 'amount': 35.50, 'location': 'NEW YORK, NY'},
        {'date': '2024-02-11', 'description': 'CLIENT DINNER - NOBU', 'amount': 425.00, 'location': 'NEW YORK, NY'},
        {'date': '2024-02-12', 'description': 'HILTON MIDTOWN', 'amount': 359.00, 'location': 'NEW YORK, NY'},
        {'date': '2024-02-12', 'description': 'UBER TO JFK', 'amount': 68.00, 'location': 'NEW YORK, NY'},
        {'date': '2024-02-13', 'description': 'DELTA AIR LINES', 'amount': 412.30, 'location': 'NEW YORK, NY'},
    ])
    
    # Trip 3: Austin (Mar 2024)
    transactions.extend([
        {'date': '2024-03-05', 'description': 'SOUTHWEST AIRLINES', 'amount': 234.50, 'location': 'AUSTIN, TX'},
        {'date': '2024-03-05', 'description': 'HYATT REGENCY AUSTIN', 'amount': 199.00, 'location': 'AUSTIN, TX'},
        {'date': '2024-03-06', 'description': 'CONFERENCE REGISTRATION', 'amount': 799.00, 'location': 'AUSTIN, TX'},
        {'date': '2024-03-06', 'description': 'BREAKFAST - IHOP', 'amount': 18.75, 'location': 'AUSTIN, TX'},
        {'date': '2024-03-06', 'description': 'HYATT REGENCY AUSTIN', 'amount': 199.00, 'location': 'AUSTIN, TX'},
        {'date': '2024-03-07', 'description': 'TEAM DINNER - BBQ PLACE', 'amount': 156.00, 'location': 'AUSTIN, TX'},
        {'date': '2024-03-08', 'description': 'SOUTHWEST AIRLINES', 'amount': 234.50, 'location': 'AUSTIN, TX'},
    ])
    
    # Add some recent transactions (current month)
    today = datetime.now()
    for i in range(5):
        date = (today - timedelta(days=i*2)).strftime('%Y-%m-%d')
        transactions.append({
            'date': date,
            'description': random.choice(['STARBUCKS', 'UBER', 'LUNCH MEETING', 'OFFICE SUPPLIES']),
            'amount': round(random.uniform(10, 100), 2),
            'location': 'LOCAL'
        })
    
    return transactions

def save_demo_data():
    """Save demo data to a JSON file."""
    transactions = generate_demo_transactions()
    
    with open('demo_transactions.json', 'w') as f:
        json.dump(transactions, f, indent=2)
    
    print(f"✅ Generated {len(transactions)} demo transactions")
    print("📁 Saved to demo_transactions.json")
    
    # Calculate totals
    total = sum(t['amount'] for t in transactions)
    trips = {}
    for t in transactions:
        month = t['date'][:7]
        if month not in trips:
            trips[month] = {'count': 0, 'total': 0}
        trips[month]['count'] += 1
        trips[month]['total'] += t['amount']
    
    print(f"\n💰 Total expenses: ${total:,.2f}")
    print(f"📅 Spanning {len(trips)} months")
    print("\n📊 Monthly breakdown:")
    for month, data in sorted(trips.items()):
        print(f"   {month}: {data['count']} transactions, ${data['total']:,.2f}")

if __name__ == '__main__':
    save_demo_data()
    print("\n🎯 Next steps:")
    print("1. Open http://localhost:5000 in your browser")
    print("2. Click the FRIDAY PANIC button")
    print("3. Choose 'Process ALL Since Jan 2024'")
    print("4. Watch the magic happen! 🎉")