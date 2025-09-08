#!/usr/bin/env python3
"""
Command-line Friday Panic Button - Process expenses without a web browser.
"""

import json
import os
from datetime import datetime
from friday_panic_button import FridayPanicButton, friday_panic, process_bulk_expenses

def load_demo_data():
    """Load demo transactions."""
    if os.path.exists('demo_transactions.json'):
        with open('demo_transactions.json', 'r') as f:
            return json.load(f)
    else:
        print("❌ No demo data found. Run 'python demo_data.py' first.")
        return []

def display_results(result):
    """Display processing results in a nice format."""
    print("\n" + "=" * 60)
    print("📊 FRIDAY PANIC BUTTON RESULTS")
    print("=" * 60)
    
    # Transaction summary
    print(f"\n✅ Processed {len(result['transactions'])} transactions")
    print(f"📈 Overall Confidence: {result['confidence_score']:.0%}")
    print(f"⏱️  Time Saved: {result['estimated_time_saved']}")
    
    # Category breakdown
    print("\n💰 EXPENSE BREAKDOWN:")
    print("-" * 40)
    for category, amount in sorted(result['totals'].items(), key=lambda x: -x[1]):
        print(f"  {category:15} ${amount:>10,.2f}")
    
    total = sum(result['totals'].values())
    print("-" * 40)
    print(f"  {'TOTAL':15} ${total:>10,.2f}")
    
    # Business purpose
    print("\n📝 BUSINESS PURPOSE:")
    print("-" * 40)
    purpose = result['business_purpose']
    print(f"Primary: {purpose['primary_purpose']}")
    print(f"Confidence: {purpose['confidence']:.0%}")
    
    if purpose.get('alternatives'):
        print("\nAlternative Purposes:")
        for i, alt in enumerate(purpose['alternatives'][:3], 1):
            print(f"  {i}. {alt}")
    
    # Items needing review
    if result['needs_review']:
        print(f"\n⚠️  {len(result['needs_review'])} items need review:")
        for item in result['needs_review'][:5]:
            print(f"  - {item['description']}: ${item['amount']:.2f}")
    
    # Final status
    print("\n🎯 FINAL STATUS:")
    print("-" * 40)
    if result['ready_to_submit']:
        print("✅ READY TO SUBMIT TO CONCUR!")
        print("All transactions categorized with high confidence.")
    else:
        print("⚠️  Review needed before submission")
        print(f"Please check the {len(result['needs_review'])} flagged items.")

def main():
    """Run the CLI Friday Panic Button."""
    print("=" * 60)
    print("🔥 FRIDAY PANIC BUTTON - CLI VERSION")
    print("=" * 60)
    
    # Load transactions
    print("\n📁 Loading transactions...")
    transactions = load_demo_data()
    
    if not transactions:
        return
    
    print(f"✅ Loaded {len(transactions)} transactions")
    
    # Show date range
    dates = [t['date'] for t in transactions]
    print(f"📅 Date range: {min(dates)} to {max(dates)}")
    
    # Process with Friday Panic
    print("\n🚀 Processing with Friday Panic Button...")
    print("⏳ Auto-categorizing transactions...")
    
    result = friday_panic(transactions)
    
    # Display results
    display_results(result)
    
    # Save results
    print("\n💾 Saving results...")
    with open('panic_results.json', 'w') as f:
        # Convert any datetime objects to strings for JSON serialization
        def json_serial(obj):
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            return str(obj)
        
        json.dump(result, f, indent=2, default=json_serial)
    
    print("✅ Results saved to panic_results.json")
    
    print("\n" + "=" * 60)
    print("🎉 PROCESSING COMPLETE!")
    print("=" * 60)

if __name__ == '__main__':
    main()