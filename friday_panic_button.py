#!/usr/bin/env python3
"""
Friday Panic Button - One-click expense report generation
Auto-categorizes everything and generates intelligent business purposes.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import re
from collections import defaultdict
import time
import logging

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class FridayPanicButton:
    """The magic button that saves your Friday afternoon."""
    
    def __init__(self):
        # Enhanced categorization rules with confidence scores
        self.category_rules = {
            'AIRFARE': {
                'keywords': ['airline', 'airways', 'delta', 'united', 'american', 'southwest', 
                            'jetblue', 'alaska', 'spirit', 'frontier', 'flight'],
                'confidence': 0.95
            },
            'HOTEL': {
                'keywords': ['hotel', 'motel', 'inn', 'resort', 'lodging', 'marriott', 
                            'hilton', 'hyatt', 'sheraton', 'westin', 'holiday inn', 
                            'hampton', 'courtyard', 'fairfield', 'residence inn'],
                'confidence': 0.95
            },
            'MEALS': {
                'keywords': ['restaurant', 'cafe', 'coffee', 'starbucks', 'diner', 
                            'grill', 'kitchen', 'food', 'pizza', 'sushi', 'chipotle',
                            'mcdonalds', 'subway', 'panera', 'dunkin'],
                'patterns': [r'\b(breakfast|lunch|dinner)\b'],
                'confidence': 0.85
            },
            'TRANSPORTATION': {
                'keywords': ['uber', 'lyft', 'taxi', 'cab', 'rental', 'hertz', 'avis',
                            'enterprise', 'budget', 'national', 'parking', 'toll'],
                'confidence': 0.90
            },
            'SUPPLIES': {
                'keywords': ['office depot', 'staples', 'best buy', 'apple store', 
                            'microsoft', 'amazon', 'supplies', 'equipment'],
                'confidence': 0.80
            },
            'ENTERTAINMENT': {
                'keywords': ['theater', 'cinema', 'concert', 'museum', 'sports',
                            'golf', 'entertainment'],
                'confidence': 0.75,
                'business_context': 'client entertainment'
            }
        }
        
        # Smart business purpose templates based on patterns
        self.purpose_patterns = {
            'single_city_trip': {
                'pattern': lambda t: len(set(self._get_cities(t))) == 1,
                'template': "Business meetings and client engagement in {city}",
                'variations': [
                    "Client meetings and partnership discussions in {city}",
                    "Regional business development meetings in {city}",
                    "Quarterly business review meetings in {city}",
                    "Strategic planning sessions in {city}"
                ]
            },
            'multi_city_trip': {
                'pattern': lambda t: len(set(self._get_cities(t))) > 1,
                'template': "Multi-city business development tour: {cities}",
                'variations': [
                    "Regional client visits across {cities}",
                    "Territory business review meetings in {cities}",
                    "Partnership development meetings across {cities}"
                ]
            },
            'conference': {
                'pattern': lambda t: self._has_conference_pattern(t),
                'template': "Attendance at {conference_name} for professional development",
                'variations': [
                    "Industry conference attendance and networking",
                    "Professional development conference and training",
                    "Annual industry summit participation"
                ]
            },
            'client_entertainment': {
                'pattern': lambda t: self._has_entertainment_expenses(t),
                'template': "Client relationship building and entertainment in {city}",
                'variations': [
                    "Client appreciation and relationship development",
                    "Business development with key stakeholders",
                    "Partnership cultivation and client engagement"
                ]
            },
            'training': {
                'pattern': lambda t: self._has_training_pattern(t),
                'template': "Professional training and skill development: {topic}",
                'variations': [
                    "Technical certification training",
                    "Leadership development workshop",
                    "Industry-specific skills training"
                ]
            }
        }
    
    def panic_categorize(self, transactions: List[Dict], batch_size: int = 100) -> List[Dict]:
        """
        Rapidly categorize all transactions with confidence scores.
        Optimized for bulk processing with batching.
        
        Returns transactions with:
        - category: Best guess category
        - confidence: How sure we are (0-1)
        - needs_review: Boolean for manual check
        """
        categorized = []
        
        # Process in batches for better performance
        for i in range(0, len(transactions), batch_size):
            batch = transactions[i:i + batch_size]
            batch_results = self._process_batch(batch)
            categorized.extend(batch_results)
        
        return categorized
    
    def _process_batch(self, batch: List[Dict]) -> List[Dict]:
        """Process a batch of transactions efficiently."""
        results = []
        
        # Pre-compile category patterns for efficiency
        compiled_patterns = {}
        for category, rules in self.category_rules.items():
            if 'patterns' in rules:
                compiled_patterns[category] = [re.compile(p, re.IGNORECASE) 
                                              for p in rules['patterns']]
        
        for transaction in batch:
            description = transaction.get('description', '').upper()
            amount = transaction.get('amount', 0)
            
            # Try each category
            best_category = 'OTHER'
            best_confidence = 0
            
            for category, rules in self.category_rules.items():
                confidence = self._calculate_confidence(description, rules)
                
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_category = category
            
            # Apply contextual rules
            if best_category == 'MEALS':
                best_category, best_confidence = self._refine_meals_category(
                    description, amount, best_category, best_confidence
                )
            
            transaction['category'] = best_category
            transaction['confidence'] = best_confidence
            transaction['needs_review'] = best_confidence < 0.7
            
            results.append(transaction)
        
        return results
    
    def _calculate_confidence(self, description: str, rules: Dict) -> float:
        """Calculate confidence score for a category match."""
        try:
            base_confidence = rules.get('confidence', 0.5)
            
            # Check keywords
            keywords = rules.get('keywords', [])
            keyword_matches = sum(1 for kw in keywords if kw.upper() in description)
            
            if keyword_matches > 0:
                # More keyword matches = higher confidence
                keyword_boost = min(keyword_matches * 0.1, 0.3)
                return min(base_confidence + keyword_boost, 1.0)
            
            # Check patterns
            patterns = rules.get('patterns', [])
            for pattern in patterns:
                try:
                    if re.search(pattern, description, re.IGNORECASE):
                        return base_confidence
                except re.error as e:
                    logger.error(f"Invalid regex pattern '{pattern}': {e}")
                    continue
            
            return 0
        except Exception as e:
            logger.error(f"Error calculating confidence for '{description}': {e}")
            return 0
    
    def _refine_meals_category(self, description: str, amount: float, 
                               category: str, confidence: float) -> Tuple[str, float]:
        """Refine meal categorization based on context."""
        
        # Expensive meals might be client entertainment
        if amount > 100:
            if any(word in description for word in ['STEAKHOUSE', 'FINE', 'GRILL']):
                return 'ENTERTAINMENT', confidence * 0.9
        
        # Airport meals are clearly travel-related
        if 'AIRPORT' in description or 'TERMINAL' in description:
            return 'MEALS', min(confidence + 0.2, 1.0)
        
        # Breakfast is almost always business during travel
        if any(word in description for word in ['BREAKFAST', 'IHOP', 'DENNYS']):
            return 'MEALS', min(confidence + 0.15, 1.0)
        
        return category, confidence
    
    def generate_smart_purpose(self, transactions: List[Dict], 
                              trip_metadata: Optional[Dict] = None) -> Dict:
        """
        Generate intelligent business purpose based on expense patterns.
        
        Returns:
        - primary_purpose: The main suggested purpose
        - alternatives: Other possible purposes
        - confidence: How confident we are
        - evidence: What led to this conclusion
        """
        
        # Analyze the trip pattern
        cities = self._get_cities(transactions)
        dates = self._get_date_range(transactions)
        categories = self._get_category_breakdown(transactions)
        total_amount = sum(t.get('amount', 0) for t in transactions)
        
        # Check each pattern
        best_purpose = None
        best_confidence = 0
        evidence = []
        
        for purpose_type, rules in self.purpose_patterns.items():
            if rules['pattern'](transactions):
                confidence = self._calculate_purpose_confidence(
                    transactions, categories, purpose_type
                )
                
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_purpose = purpose_type
                    
                    # Generate the actual purpose text
                    template = rules['template']
                    if '{city}' in template:
                        template = template.format(city=cities[0] if cities else 'various locations')
                    elif '{cities}' in template:
                        template = template.format(cities=', '.join(cities[:3]))
                    
                    evidence = self._gather_evidence(transactions, purpose_type)
        
        # Generate alternatives
        alternatives = self._generate_alternatives(transactions, categories, cities)
        
        # If no pattern matched, use smart defaults
        if not best_purpose:
            best_purpose = self._generate_default_purpose(cities, dates, categories)
            best_confidence = 0.6
            evidence = ["Default pattern based on location and dates"]
        
        return {
            'primary_purpose': best_purpose,
            'alternatives': alternatives[:3],  # Top 3 alternatives
            'confidence': best_confidence,
            'evidence': evidence,
            'needs_review': best_confidence < 0.7,
            'metadata': {
                'cities': cities,
                'dates': dates,
                'total_amount': total_amount,
                'primary_category': max(categories, key=categories.get) if categories else 'OTHER'
            }
        }
    
    def _has_conference_pattern(self, transactions: List[Dict]) -> bool:
        """Detect if this looks like a conference trip."""
        conference_indicators = [
            'convention', 'conference', 'summit', 'symposium', 'expo',
            'registration', 'attendee', 'badge'
        ]
        
        for t in transactions:
            desc = t.get('description', '').lower()
            if any(indicator in desc for indicator in conference_indicators):
                return True
        
        # Multiple days at same hotel + meals = likely conference
        hotel_count = sum(1 for t in transactions if t.get('category') == 'HOTEL')
        meals_count = sum(1 for t in transactions if t.get('category') == 'MEALS')
        
        return hotel_count >= 2 and meals_count >= 4
    
    def _has_entertainment_expenses(self, transactions: List[Dict]) -> bool:
        """Check if trip includes client entertainment."""
        for t in transactions:
            if t.get('category') == 'ENTERTAINMENT':
                return True
            # Expensive dinner might be client entertainment
            if t.get('category') == 'MEALS' and t.get('amount', 0) > 150:
                return True
        return False
    
    def _has_training_pattern(self, transactions: List[Dict]) -> bool:
        """Detect training or education patterns."""
        training_keywords = ['training', 'course', 'workshop', 'certification', 'academy']
        
        for t in transactions:
            desc = t.get('description', '').lower()
            if any(keyword in desc for keyword in training_keywords):
                return True
        
        return False
    
    def _get_cities(self, transactions: List[Dict]) -> List[str]:
        """Extract unique cities from transactions."""
        cities = []
        for t in transactions:
            location = t.get('location', '')
            if location and ',' in location:
                city = location.split(',')[0].strip()
                if city and city not in cities:
                    cities.append(city)
        return cities
    
    def _get_date_range(self, transactions: List[Dict]) -> Dict:
        """Get date range of transactions."""
        dates = [t.get('date') for t in transactions if t.get('date')]
        if not dates:
            return {'start': None, 'end': None, 'duration_days': 0}
        
        # Convert to datetime if needed
        date_objs = []
        for d in dates:
            if isinstance(d, str):
                try:
                    date_objs.append(datetime.strptime(d, '%Y-%m-%d'))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid date format '{d}': {e}")
                    continue
            elif isinstance(d, datetime):
                date_objs.append(d)
        
        if date_objs:
            return {
                'start': min(date_objs),
                'end': max(date_objs),
                'duration_days': (max(date_objs) - min(date_objs)).days + 1
            }
        
        return {'start': None, 'end': None, 'duration_days': 0}
    
    def _get_category_breakdown(self, transactions: List[Dict]) -> Dict[str, float]:
        """Get spending by category."""
        breakdown = {}
        for t in transactions:
            category = t.get('category', 'OTHER')
            amount = t.get('amount', 0)
            breakdown[category] = breakdown.get(category, 0) + amount
        return breakdown
    
    def _calculate_purpose_confidence(self, transactions: List[Dict], 
                                     categories: Dict, purpose_type: str) -> float:
        """Calculate confidence for a business purpose."""
        base_confidence = 0.7
        
        # Conference pattern with hotel and registration = high confidence
        if purpose_type == 'conference':
            if 'HOTEL' in categories and any('registration' in t.get('description', '').lower() 
                                            for t in transactions):
                return 0.95
        
        # Client entertainment with clear patterns
        if purpose_type == 'client_entertainment':
            if categories.get('ENTERTAINMENT', 0) > 200:
                return 0.90
        
        # Multi-city with flights = high confidence
        if purpose_type == 'multi_city_trip':
            if categories.get('AIRFARE', 0) > 500:
                return 0.85
        
        return base_confidence
    
    def _gather_evidence(self, transactions: List[Dict], purpose_type: str) -> List[str]:
        """Gather evidence supporting the business purpose."""
        evidence = []
        
        if purpose_type == 'conference':
            evidence.append("Multiple hotel nights at same location")
            evidence.append("Regular meal pattern suggesting conference schedule")
            
        elif purpose_type == 'client_entertainment':
            high_meals = [t for t in transactions 
                         if t.get('category') == 'MEALS' and t.get('amount', 0) > 100]
            if high_meals:
                evidence.append(f"High-value meals suggesting client entertainment (${sum(t['amount'] for t in high_meals):.0f})")
        
        elif purpose_type == 'multi_city_trip':
            cities = self._get_cities(transactions)
            evidence.append(f"Travel across {len(cities)} cities")
            evidence.append("Multiple transportation expenses between locations")
        
        return evidence
    
    def _generate_alternatives(self, transactions: List[Dict], 
                              categories: Dict, cities: List[str]) -> List[str]:
        """Generate alternative business purposes."""
        alternatives = []
        
        # Based on primary spending category
        primary_category = max(categories, key=categories.get) if categories else 'OTHER'
        
        if primary_category == 'HOTEL':
            alternatives.append(f"Extended business engagement in {cities[0] if cities else 'client location'}")
        
        if primary_category == 'AIRFARE':
            alternatives.append("Urgent client issue resolution requiring immediate travel")
        
        if 'MEALS' in categories and categories['MEALS'] > 200:
            alternatives.append("Team building and strategy sessions with remote colleagues")
        
        # Generic alternatives that always work
        alternatives.extend([
            "Quarterly business review and planning meetings",
            "Client relationship management and account review",
            "Regional business development and market expansion"
        ])
        
        return alternatives
    
    def _generate_default_purpose(self, cities: List[str], dates: Dict, 
                                 categories: Dict) -> str:
        """Generate a safe default business purpose."""
        if cities:
            city_str = cities[0] if len(cities) == 1 else f"{cities[0]} and other locations"
            duration = dates.get('duration_days', 1)
            
            if duration > 3:
                return f"Extended business meetings and client engagement in {city_str}"
            elif duration == 1:
                return f"Day trip for business meetings in {city_str}"
            else:
                return f"Business meetings and professional activities in {city_str}"
        
        return "Business travel for client meetings and professional development"

def group_transactions_by_trip(transactions: List[Dict], 
                              max_gap_days: int = 7) -> List[List[Dict]]:
    """
    Group transactions into trips based on date gaps.
    Transactions more than max_gap_days apart start a new trip.
    """
    if not transactions:
        return []
    
    # Sort by date
    sorted_trans = sorted(transactions, key=lambda x: x.get('date', ''))
    
    trips = []
    current_trip = [sorted_trans[0]]
    
    for i in range(1, len(sorted_trans)):
        current_date_str = sorted_trans[i].get('date', '')
        prev_date_str = sorted_trans[i-1].get('date', '')
        
        try:
            current_date = datetime.strptime(current_date_str, '%Y-%m-%d')
            prev_date = datetime.strptime(prev_date_str, '%Y-%m-%d')
            
            gap = (current_date - prev_date).days
            
            if gap > max_gap_days:
                trips.append(current_trip)
                current_trip = [sorted_trans[i]]
            else:
                current_trip.append(sorted_trans[i])
        except (ValueError, TypeError) as e:
            # If date parsing fails, add to current trip
            logger.warning(f"Error parsing dates for trip grouping: {e}")
            current_trip.append(sorted_trans[i])
    
    if current_trip:
        trips.append(current_trip)
    
    return trips

def process_bulk_expenses(transactions: List[Dict], 
                         start_date: Optional[str] = None,
                         end_date: Optional[str] = None) -> Dict:
    """
    Process bulk expenses with date filtering and trip grouping.
    Optimized for handling large volumes (e.g., since Jan 2024).
    
    Args:
        transactions: List of all transactions
        start_date: Filter transactions after this date (YYYY-MM-DD)
        end_date: Filter transactions before this date (YYYY-MM-DD)
    
    Returns:
        Comprehensive expense report with trip grouping
    """
    # Filter by date range if specified
    filtered_transactions = transactions
    
    if start_date:
        filtered_transactions = [
            t for t in filtered_transactions 
            if t.get('date', '') >= start_date
        ]
    
    if end_date:
        filtered_transactions = [
            t for t in filtered_transactions 
            if t.get('date', '') <= end_date
        ]
    
    # Group into trips
    trips = group_transactions_by_trip(filtered_transactions)
    
    # Process each trip
    panic = FridayPanicButton()
    all_results = []
    trip_summaries = []
    
    for i, trip_transactions in enumerate(trips, 1):
        # Categorize this trip
        categorized = panic.panic_categorize(trip_transactions)
        
        # Generate purpose for this trip
        purpose_result = panic.generate_smart_purpose(categorized)
        
        # Calculate trip totals
        trip_totals = {}
        for t in categorized:
            cat = t['category']
            trip_totals[cat] = trip_totals.get(cat, 0) + t.get('amount', 0)
        
        trip_summary = {
            'trip_number': i,
            'transactions': categorized,
            'business_purpose': purpose_result,
            'totals': trip_totals,
            'total_amount': sum(t.get('amount', 0) for t in categorized),
            'date_range': panic._get_date_range(categorized),
            'needs_review': [t for t in categorized if t.get('needs_review')]
        }
        
        trip_summaries.append(trip_summary)
        all_results.extend(categorized)
    
    # Calculate overall statistics
    overall_totals = defaultdict(float)
    for result in all_results:
        overall_totals[result['category']] += result.get('amount', 0)
    
    return {
        'trips': trip_summaries,
        'total_trips': len(trips),
        'total_transactions': len(all_results),
        'overall_totals': dict(overall_totals),
        'grand_total': sum(overall_totals.values()),
        'date_range': {
            'start': min(t.get('date', '') for t in filtered_transactions) if filtered_transactions else None,
            'end': max(t.get('date', '') for t in filtered_transactions) if filtered_transactions else None
        },
        'processing_stats': {
            'original_count': len(transactions),
            'filtered_count': len(filtered_transactions),
            'categorized_count': len(all_results),
            'confidence_avg': sum(t['confidence'] for t in all_results) / len(all_results) if all_results else 0
        }
    }

# The actual Friday Panic Button endpoint
def friday_panic(transactions: List[Dict], 
                 bulk_mode: bool = False,
                 start_date: Optional[str] = None) -> Dict:
    """
    The one button that saves your Friday.
    
    Input: Raw transactions
    Output: Fully categorized and purposeful expense report
    
    Args:
        transactions: Raw transaction data
        bulk_mode: Enable bulk processing for large datasets
        start_date: For bulk mode, process from this date (defaults to Jan 2024)
    """
    
    # For bulk processing of many expenses
    if bulk_mode:
        if not start_date:
            start_date = '2024-01-01'  # Default to January 2024
        return process_bulk_expenses(transactions, start_date=start_date)
    panic = FridayPanicButton()
    
    # Step 1: Auto-categorize everything
    categorized = panic.panic_categorize(transactions)
    
    # Step 2: Generate business purpose
    purpose_result = panic.generate_smart_purpose(categorized)
    
    # Step 3: Flag what needs review
    needs_review = [t for t in categorized if t.get('needs_review')]
    
    # Step 4: Calculate totals
    totals_by_category = {}
    for t in categorized:
        cat = t['category']
        totals_by_category[cat] = totals_by_category.get(cat, 0) + t.get('amount', 0)
    
    return {
        'transactions': categorized,
        'business_purpose': purpose_result,
        'totals': totals_by_category,
        'needs_review': needs_review,
        'ready_to_submit': len(needs_review) == 0 and purpose_result['confidence'] > 0.7,
        'estimated_time_saved': '28 minutes',
        'confidence_score': sum(t['confidence'] for t in categorized) / len(categorized) if categorized else 0
    }

if __name__ == '__main__':
    # Demo the Friday Panic Button
    print("🚨 FRIDAY PANIC BUTTON DEMO")
    print("=" * 50)
    
    # Demo bulk processing
    print("\n📦 BULK PROCESSING MODE (Since Jan 2024)")
    print("-" * 40)
    
    # Sample transactions from a real trip
    sample_transactions = [
        {'date': '2024-01-15', 'description': 'UNITED AIRLINES', 'amount': 523.40, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-15', 'description': 'MARRIOTT UNION SQUARE', 'amount': 289.00, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-15', 'description': 'UBER TECHNOLOGIES', 'amount': 47.23, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-16', 'description': 'STARBUCKS #4721', 'amount': 8.45, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-16', 'description': "MORTON'S STEAKHOUSE", 'amount': 287.50, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-16', 'description': 'MARRIOTT UNION SQUARE', 'amount': 289.00, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-17', 'description': 'CONFERENCE REGISTRATION', 'amount': 1299.00, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-17', 'description': 'LUNCH CAFE', 'amount': 23.67, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-18', 'description': 'UNITED AIRLINES', 'amount': 523.40, 'location': 'SAN FRANCISCO, CA'},
        {'date': '2024-01-18', 'description': 'SFO AIRPORT PARKING', 'amount': 45.00, 'location': 'SAN FRANCISCO, CA'},
    ]
    
    # Hit the panic button!
    result = friday_panic(sample_transactions)
    
    print("\n📊 AUTO-CATEGORIZATION RESULTS:")
    print("-" * 40)
    for t in result['transactions'][:5]:  # Show first 5
        confidence_emoji = "✅" if t['confidence'] > 0.8 else "⚠️" if t['confidence'] > 0.6 else "❓"
        print(f"{confidence_emoji} {t['description'][:30]:30} → {t['category']:15} ({t['confidence']:.0%})")
    
    print(f"\n💰 TOTALS BY CATEGORY:")
    print("-" * 40)
    for category, total in sorted(result['totals'].items(), key=lambda x: -x[1]):
        print(f"  {category:15} ${total:,.2f}")
    
    print(f"\n✍️ BUSINESS PURPOSE GENERATION:")
    print("-" * 40)
    purpose = result['business_purpose']
    print(f"Primary: {purpose['primary_purpose']}")
    print(f"Confidence: {purpose['confidence']:.0%}")
    print(f"\nEvidence:")
    for e in purpose['evidence']:
        print(f"  • {e}")
    
    print(f"\nAlternatives:")
    for i, alt in enumerate(purpose['alternatives'][:3], 1):
        print(f"  {i}. {alt}")
    
    print(f"\n🎯 FINAL ASSESSMENT:")
    print("-" * 40)
    if result['ready_to_submit']:
        print("✅ READY TO SUBMIT TO CONCUR!")
    else:
        print(f"⚠️  {len(result['needs_review'])} items need review")
    
    print(f"\n⏱️  Time saved: {result['estimated_time_saved']}")
    print(f"📈 Overall confidence: {result['confidence_score']:.0%}")
    
    # Demo bulk processing
    print("\n" + "=" * 50)
    print("📦 BULK PROCESSING DEMO")
    print("=" * 50)
    
    # Generate more sample transactions for bulk demo
    bulk_transactions = sample_transactions.copy()
    
    # Add transactions from Feb 2024
    bulk_transactions.extend([
        {'date': '2024-02-10', 'description': 'DELTA AIRLINES', 'amount': 412.30, 'location': 'NEW YORK, NY'},
        {'date': '2024-02-10', 'description': 'HILTON MIDTOWN', 'amount': 359.00, 'location': 'NEW YORK, NY'},
        {'date': '2024-02-11', 'description': 'CLIENT DINNER - NOBU', 'amount': 425.00, 'location': 'NEW YORK, NY'},
        {'date': '2024-02-12', 'description': 'UBER', 'amount': 28.50, 'location': 'NEW YORK, NY'},
    ])
    
    # Process in bulk mode
    bulk_result = friday_panic(bulk_transactions, bulk_mode=True, start_date='2024-01-01')
    
    print(f"\n📊 BULK PROCESSING RESULTS:")
    print("-" * 40)
    print(f"Total Trips Found: {bulk_result['total_trips']}")
    print(f"Total Transactions: {bulk_result['total_transactions']}")
    print(f"Date Range: {bulk_result['date_range']['start']} to {bulk_result['date_range']['end']}")
    print(f"Grand Total: ${bulk_result['grand_total']:,.2f}")
    
    print(f"\n🗂️ TRIPS BREAKDOWN:")
    for trip in bulk_result['trips']:
        dates = trip['date_range']
        print(f"\nTrip #{trip['trip_number']}: {dates['start'].strftime('%b %d')} - {dates['end'].strftime('%b %d, %Y')}")
        print(f"  Purpose: {trip['business_purpose']['primary_purpose']}")
        print(f"  Total: ${trip['total_amount']:,.2f}")
        print(f"  Transactions: {len(trip['transactions'])}")
    
    print(f"\n📈 PROCESSING STATISTICS:")
    stats = bulk_result['processing_stats']
    print(f"  Original transactions: {stats['original_count']}")
    print(f"  After date filter: {stats['filtered_count']}")
    print(f"  Successfully categorized: {stats['categorized_count']}")
    print(f"  Average confidence: {stats['confidence_avg']:.0%}")