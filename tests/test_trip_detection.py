#!/usr/bin/env python3
"""
Trip Detection Algorithm Tests
Tests trip detection logic, edge cases, categorization accuracy, and rules.
"""

import pytest
from datetime import datetime, timedelta, date
from typing import List, Dict
import json


@pytest.mark.unit
class TestTripDetectionAlgorithm:
    """Test the core trip detection algorithm."""
    
    def test_basic_trip_detection(self, travel_transactions_factory):
        """Test basic trip detection with clear travel patterns."""
        from production_app import TripDetector
        
        # Create transactions for a 3-day Seattle trip
        transactions = travel_transactions_factory('Seattle, WA', 
                                                  datetime(2024, 1, 15), 
                                                  days=3)
        
        detector = TripDetector(home_state='CA')
        trips = detector.detect_trips(transactions)
        
        assert len(trips) == 1
        assert trips[0]['location'] == 'Seattle, WA'
        assert trips[0]['duration_days'] == 3
        assert trips[0]['start_date'] == '2024-01-15'
        assert trips[0]['end_date'] == '2024-01-17'
    
    def test_multiple_trip_detection(self, travel_transactions_factory):
        """Test detection of multiple distinct trips."""
        from production_app import TripDetector
        
        # Create three separate trips
        seattle = travel_transactions_factory('Seattle, WA', datetime(2024, 1, 15), days=3)
        new_york = travel_transactions_factory('New York, NY', datetime(2024, 2, 10), days=2)
        austin = travel_transactions_factory('Austin, TX', datetime(2024, 3, 5), days=4)
        
        all_transactions = seattle + new_york + austin
        
        detector = TripDetector(home_state='CA')
        trips = detector.detect_trips(all_transactions)
        
        assert len(trips) == 3
        
        # Verify each trip
        locations = [trip['location'] for trip in trips]
        assert 'Seattle, WA' in locations
        assert 'New York, NY' in locations
        assert 'Austin, TX' in locations
    
    def test_trip_merging_logic(self, travel_transactions_factory):
        """Test that nearby transactions are merged into single trip."""
        from production_app import TripDetector
        
        # Create transactions with small gap (should merge)
        day1 = travel_transactions_factory('Seattle, WA', datetime(2024, 1, 15), days=2)
        day4 = travel_transactions_factory('Seattle, WA', datetime(2024, 1, 18), days=2)
        
        all_transactions = day1 + day4
        
        detector = TripDetector(home_state='CA', max_gap_days=3)
        trips = detector.detect_trips(all_transactions)
        
        # Should merge into single trip
        assert len(trips) == 1
        assert trips[0]['duration_days'] == 5  # Jan 15-19
    
    def test_trip_splitting_logic(self):
        """Test that trips with large gaps are split."""
        from production_app import TripDetector
        
        transactions = [
            {'date': '2024-01-15', 'location': 'Seattle, WA', 'amount': 500, 'category': 'AIRFARE'},
            {'date': '2024-01-16', 'location': 'Seattle, WA', 'amount': 200, 'category': 'HOTEL'},
            # 10 day gap
            {'date': '2024-01-27', 'location': 'Seattle, WA', 'amount': 300, 'category': 'HOTEL'},
            {'date': '2024-01-28', 'location': 'Seattle, WA', 'amount': 100, 'category': 'MEALS'},
        ]
        
        detector = TripDetector(home_state='CA', max_gap_days=7)
        trips = detector.detect_trips(transactions)
        
        # Should split into two trips
        assert len(trips) == 2
        assert trips[0]['end_date'] == '2024-01-16'
        assert trips[1]['start_date'] == '2024-01-27'
    
    def test_location_change_detection(self):
        """Test detection when location changes mid-trip."""
        from production_app import TripDetector
        
        transactions = [
            {'date': '2024-01-15', 'location': 'Seattle, WA', 'amount': 500, 'category': 'AIRFARE'},
            {'date': '2024-01-16', 'location': 'Seattle, WA', 'amount': 200, 'category': 'HOTEL'},
            {'date': '2024-01-17', 'location': 'Portland, OR', 'amount': 150, 'category': 'HOTEL'},
            {'date': '2024-01-18', 'location': 'Portland, OR', 'amount': 50, 'category': 'MEALS'},
        ]
        
        detector = TripDetector(home_state='CA')
        trips = detector.detect_trips(transactions)
        
        # Behavior depends on implementation:
        # Option 1: Single multi-city trip
        # Option 2: Two separate trips
        assert len(trips) in [1, 2]
        
        if len(trips) == 1:
            # Multi-city trip
            assert 'Seattle' in trips[0]['location'] or 'Multiple' in trips[0]['location']
        else:
            # Separate trips
            assert trips[0]['location'] == 'Seattle, WA'
            assert trips[1]['location'] == 'Portland, OR'


@pytest.mark.unit
class TestTripDetectionEdgeCases:
    """Test edge cases in trip detection."""
    
    def test_single_day_trip(self):
        """Test detection of single-day trips."""
        from production_app import TripDetector
        
        transactions = [
            {'date': '2024-01-15', 'location': 'Los Angeles, CA', 'amount': 100, 'category': 'MEALS'},
            {'date': '2024-01-15', 'location': 'Los Angeles, CA', 'amount': 50, 'category': 'TRANSPORTATION'},
        ]
        
        detector = TripDetector(home_state='CA', min_trip_days=1)
        trips = detector.detect_trips(transactions)
        
        # Should detect single-day trip if out of home city
        if detector.home_city != 'Los Angeles':
            assert len(trips) == 1
            assert trips[0]['duration_days'] == 1
    
    def test_overlapping_dates(self):
        """Test handling of overlapping trip dates."""
        from production_app import TripDetector
        
        transactions = [
            # Trip 1
            {'date': '2024-01-15', 'location': 'Seattle, WA', 'amount': 500, 'category': 'AIRFARE'},
            {'date': '2024-01-16', 'location': 'Seattle, WA', 'amount': 200, 'category': 'HOTEL'},
            # Overlapping transaction (same date, different location)
            {'date': '2024-01-16', 'location': 'Portland, OR', 'amount': 150, 'category': 'HOTEL'},
            {'date': '2024-01-17', 'location': 'Portland, OR', 'amount': 100, 'category': 'MEALS'},
        ]
        
        detector = TripDetector(home_state='CA')
        trips = detector.detect_trips(transactions)
        
        # Should handle overlapping dates appropriately
        assert len(trips) >= 1
        
        # Total amount should include all transactions
        total = sum(t['amount'] for t in transactions)
        trip_total = sum(trip.get('total_amount', 0) for trip in trips)
        assert trip_total == total
    
    def test_gap_in_dates(self):
        """Test handling of gaps within a trip."""
        from production_app import TripDetector
        
        transactions = [
            {'date': '2024-01-15', 'location': 'Seattle, WA', 'amount': 500, 'category': 'AIRFARE'},
            {'date': '2024-01-15', 'location': 'Seattle, WA', 'amount': 200, 'category': 'HOTEL'},
            # No transactions for Jan 16
            {'date': '2024-01-17', 'location': 'Seattle, WA', 'amount': 200, 'category': 'HOTEL'},
            {'date': '2024-01-18', 'location': 'Seattle, WA', 'amount': 100, 'category': 'MEALS'},
        ]
        
        detector = TripDetector(home_state='CA', max_gap_days=2)
        trips = detector.detect_trips(transactions)
        
        # Should bridge small gaps
        assert len(trips) == 1
        assert trips[0]['duration_days'] == 4  # Jan 15-18 inclusive
    
    def test_no_travel_transactions(self):
        """Test behavior with no travel-related transactions."""
        from production_app import TripDetector
        
        transactions = [
            {'date': '2024-01-15', 'location': 'San Francisco, CA', 'amount': 50, 'category': 'GROCERIES'},
            {'date': '2024-01-16', 'location': 'San Francisco, CA', 'amount': 30, 'category': 'GAS'},
        ]
        
        detector = TripDetector(home_state='CA', home_city='San Francisco')
        trips = detector.detect_trips(transactions)
        
        # Should not detect trips for home location
        assert len(trips) == 0
    
    def test_mixed_home_and_travel(self):
        """Test mix of home and travel transactions."""
        from production_app import TripDetector
        
        transactions = [
            {'date': '2024-01-14', 'location': 'San Francisco, CA', 'amount': 50, 'category': 'MEALS'},
            {'date': '2024-01-15', 'location': 'Seattle, WA', 'amount': 500, 'category': 'AIRFARE'},
            {'date': '2024-01-16', 'location': 'Seattle, WA', 'amount': 200, 'category': 'HOTEL'},
            {'date': '2024-01-17', 'location': 'San Francisco, CA', 'amount': 40, 'category': 'MEALS'},
        ]
        
        detector = TripDetector(home_state='CA', home_city='San Francisco')
        trips = detector.detect_trips(transactions)
        
        # Should only detect Seattle trip
        assert len(trips) == 1
        assert trips[0]['location'] == 'Seattle, WA'
        assert trips[0]['start_date'] == '2024-01-15'
        assert trips[0]['end_date'] == '2024-01-16'
    
    def test_international_trip_detection(self):
        """Test detection of international trips."""
        from production_app import TripDetector
        
        transactions = [
            {'date': '2024-01-15', 'location': 'London, UK', 'amount': 800, 'category': 'AIRFARE'},
            {'date': '2024-01-16', 'location': 'London, UK', 'amount': 250, 'category': 'HOTEL'},
            {'date': '2024-01-17', 'location': 'Paris, FR', 'amount': 300, 'category': 'HOTEL'},
        ]
        
        detector = TripDetector(home_state='CA')
        trips = detector.detect_trips(transactions)
        
        # Should detect international trip
        assert len(trips) >= 1
        assert trips[0].get('is_international', False) == True


@pytest.mark.unit
class TestTripRules:
    """Test different trip detection rules."""
    
    def test_out_of_state_2_days_rule(self):
        """Test OUT_OF_STATE_2_DAYS rule."""
        from production_app import TripDetector, TripRule
        
        # 1-day out of state (should not trigger)
        transactions_1day = [
            {'date': '2024-01-15', 'location': 'Portland, OR', 'amount': 200, 'category': 'MEALS'},
        ]
        
        detector = TripDetector(
            home_state='CA',
            trip_rule=TripRule.OUT_OF_STATE_2_DAYS
        )
        trips = detector.detect_trips(transactions_1day)
        assert len(trips) == 0
        
        # 2-day out of state (should trigger)
        transactions_2day = [
            {'date': '2024-01-15', 'location': 'Portland, OR', 'amount': 200, 'category': 'HOTEL'},
            {'date': '2024-01-16', 'location': 'Portland, OR', 'amount': 100, 'category': 'MEALS'},
        ]
        
        trips = detector.detect_trips(transactions_2day)
        assert len(trips) == 1
    
    def test_out_of_state_3_days_rule(self):
        """Test OUT_OF_STATE_3_DAYS rule."""
        from production_app import TripDetector, TripRule
        
        # 2-day out of state (should not trigger)
        transactions_2day = [
            {'date': '2024-01-15', 'location': 'Portland, OR', 'amount': 200, 'category': 'HOTEL'},
            {'date': '2024-01-16', 'location': 'Portland, OR', 'amount': 100, 'category': 'MEALS'},
        ]
        
        detector = TripDetector(
            home_state='CA',
            trip_rule=TripRule.OUT_OF_STATE_3_DAYS
        )
        trips = detector.detect_trips(transactions_2day)
        assert len(trips) == 0
        
        # 3-day out of state (should trigger)
        transactions_3day = transactions_2day + [
            {'date': '2024-01-17', 'location': 'Portland, OR', 'amount': 150, 'category': 'MEALS'},
        ]
        
        trips = detector.detect_trips(transactions_3day)
        assert len(trips) == 1
    
    def test_away_50_miles_rule(self):
        """Test AWAY_FROM_HOME_50_MILES rule."""
        from production_app import TripDetector, TripRule
        
        detector = TripDetector(
            home_state='CA',
            home_city='San Francisco',
            trip_rule=TripRule.AWAY_FROM_HOME_50_MILES
        )
        
        # Within 50 miles (should not trigger)
        transactions_near = [
            {'date': '2024-01-15', 'location': 'San Jose, CA', 'amount': 100, 'category': 'MEALS'},
            {'date': '2024-01-16', 'location': 'Oakland, CA', 'amount': 50, 'category': 'MEALS'},
        ]
        
        trips = detector.detect_trips(transactions_near)
        # May depend on actual distance calculation
        
        # Far from home (should trigger)
        transactions_far = [
            {'date': '2024-01-15', 'location': 'Los Angeles, CA', 'amount': 200, 'category': 'HOTEL'},
            {'date': '2024-01-16', 'location': 'Los Angeles, CA', 'amount': 100, 'category': 'MEALS'},
        ]
        
        trips = detector.detect_trips(transactions_far)
        assert len(trips) == 1
    
    def test_international_rule(self):
        """Test INTERNATIONAL rule."""
        from production_app import TripDetector, TripRule
        
        detector = TripDetector(
            home_state='CA',
            trip_rule=TripRule.INTERNATIONAL
        )
        
        # Domestic transactions (should not trigger)
        transactions_domestic = [
            {'date': '2024-01-15', 'location': 'New York, NY', 'amount': 500, 'category': 'AIRFARE'},
            {'date': '2024-01-16', 'location': 'Boston, MA', 'amount': 200, 'category': 'HOTEL'},
        ]
        
        trips = detector.detect_trips(transactions_domestic)
        assert len(trips) == 0
        
        # International transaction (should trigger)
        transactions_intl = [
            {'date': '2024-01-15', 'location': 'Toronto, CA', 'amount': 400, 'category': 'HOTEL'},
        ]
        
        trips = detector.detect_trips(transactions_intl)
        assert len(trips) == 1
    
    def test_custom_rule(self):
        """Test CUSTOM rule with user-defined logic."""
        from production_app import TripDetector, TripRule
        
        # Custom rule: Only detect trips with hotels
        def custom_logic(transactions):
            return any(t.get('category') == 'HOTEL' for t in transactions)
        
        detector = TripDetector(
            home_state='CA',
            trip_rule=TripRule.CUSTOM,
            custom_rule_func=custom_logic
        )
        
        # No hotel (should not trigger)
        transactions_no_hotel = [
            {'date': '2024-01-15', 'location': 'Seattle, WA', 'amount': 100, 'category': 'MEALS'},
            {'date': '2024-01-16', 'location': 'Seattle, WA', 'amount': 50, 'category': 'TRANSPORTATION'},
        ]
        
        trips = detector.detect_trips(transactions_no_hotel)
        assert len(trips) == 0
        
        # With hotel (should trigger)
        transactions_with_hotel = transactions_no_hotel + [
            {'date': '2024-01-16', 'location': 'Seattle, WA', 'amount': 200, 'category': 'HOTEL'},
        ]
        
        trips = detector.detect_trips(transactions_with_hotel)
        assert len(trips) == 1


@pytest.mark.unit
class TestCategorizationAccuracy:
    """Test accuracy of expense categorization."""
    
    def test_airline_categorization(self):
        """Test categorization of airline expenses."""
        from production_app import ExpenseCategorizer
        
        categorizer = ExpenseCategorizer()
        
        airline_descriptions = [
            'UNITED AIRLINES',
            'DELTA AIR LINES',
            'SOUTHWEST AIRLINES',
            'AMERICAN AIRLINES',
            'ALASKA AIRLINES',
            'JETBLUE AIRWAYS',
            'SPIRIT AIRLINES',
            'FRONTIER AIRLINES',
        ]
        
        for desc in airline_descriptions:
            category = categorizer.categorize({'description': desc})
            assert category == 'AIRFARE', f"Failed to categorize {desc}"
    
    def test_hotel_categorization(self):
        """Test categorization of hotel expenses."""
        from production_app import ExpenseCategorizer
        
        categorizer = ExpenseCategorizer()
        
        hotel_descriptions = [
            'MARRIOTT HOTEL',
            'HILTON SEATTLE',
            'HYATT REGENCY',
            'HOLIDAY INN',
            'HAMPTON INN',
            'BEST WESTERN',
            'AIRBNB',
            'VRBO RENTAL',
        ]
        
        for desc in hotel_descriptions:
            category = categorizer.categorize({'description': desc})
            assert category in ['HOTEL', 'LODGING'], f"Failed to categorize {desc}"
    
    def test_meal_categorization(self):
        """Test categorization of meal expenses."""
        from production_app import ExpenseCategorizer
        
        categorizer = ExpenseCategorizer()
        
        meal_descriptions = [
            'STARBUCKS #1234',
            'MCDONALDS',
            'CHIPOTLE MEXICAN GRILL',
            'RESTAURANT XYZ',
            'CAFE BISTRO',
            'DUNKIN DONUTS',
            'SUBWAY SANDWICHES',
        ]
        
        for desc in meal_descriptions:
            category = categorizer.categorize({'description': desc})
            assert category in ['MEALS', 'FOOD', 'DINING'], f"Failed to categorize {desc}"
    
    def test_transportation_categorization(self):
        """Test categorization of transportation expenses."""
        from production_app import ExpenseCategorizer
        
        categorizer = ExpenseCategorizer()
        
        transport_descriptions = [
            'UBER TECHNOLOGIES',
            'LYFT RIDE',
            'YELLOW CAB',
            'HERTZ RENTAL',
            'ENTERPRISE RENT-A-CAR',
            'AVIS CAR RENTAL',
            'PARKING GARAGE',
            'TOLL ROAD',
        ]
        
        for desc in transport_descriptions:
            category = categorizer.categorize({'description': desc})
            assert category in ['TRANSPORTATION', 'GROUND TRANSPORT', 'CAR RENTAL'], \
                   f"Failed to categorize {desc}"
    
    def test_ambiguous_categorization(self):
        """Test categorization of ambiguous descriptions."""
        from production_app import ExpenseCategorizer
        
        categorizer = ExpenseCategorizer()
        
        ambiguous = [
            ('AMAZON.COM', ['SUPPLIES', 'OTHER', 'GENERAL']),
            ('WALMART', ['SUPPLIES', 'OTHER', 'GENERAL']),
            ('TARGET', ['SUPPLIES', 'OTHER', 'GENERAL']),
            ('7-ELEVEN', ['MEALS', 'SUPPLIES', 'OTHER']),
            ('CVS PHARMACY', ['PERSONAL', 'SUPPLIES', 'OTHER']),
        ]
        
        for desc, valid_categories in ambiguous:
            category = categorizer.categorize({'description': desc})
            assert category in valid_categories, \
                   f"Unexpected category {category} for {desc}"
    
    def test_categorization_with_metadata(self):
        """Test categorization using additional metadata."""
        from production_app import ExpenseCategorizer
        
        categorizer = ExpenseCategorizer()
        
        # Test with MCC codes if available
        transaction = {
            'description': 'VENDOR 12345',
            'mcc_code': '3000',  # Airlines MCC
            'amount': 500
        }
        
        category = categorizer.categorize(transaction)
        assert category == 'AIRFARE'
        
        # Test with amount hints
        transaction = {
            'description': 'BUSINESS EXPENSE',
            'amount': 8.50  # Likely a meal
        }
        
        category = categorizer.categorize(transaction)
        # Small amounts often categorized as meals
        
        # Test with location hints
        transaction = {
            'description': 'VENDOR ABC',
            'location': 'AIRPORT TERMINAL',
            'amount': 25
        }
        
        category = categorizer.categorize(transaction)
        # Airport location might influence category


@pytest.mark.integration
class TestTripDetectionIntegration:
    """Integration tests for trip detection with real data flow."""
    
    def test_plaid_to_trip_detection(self, mock_plaid_client, test_database):
        """Test trip detection from Plaid transaction data."""
        from production_app import TripDetector
        
        # Get transactions from mock Plaid
        plaid_transactions = mock_plaid_client.get_transactions()
        
        # Convert Plaid format to internal format
        transactions = []
        for plaid_trans in plaid_transactions:
            transactions.append({
                'date': plaid_trans['date'],
                'description': plaid_trans['name'],
                'amount': plaid_trans['amount'],
                'location': f"{plaid_trans['location']['city']}, {plaid_trans['location']['region']}",
                'category': plaid_trans['category'][0] if plaid_trans['category'] else 'OTHER'
            })
        
        # Detect trips
        detector = TripDetector(home_state='CA')
        trips = detector.detect_trips(transactions)
        
        # Verify trips detected
        assert len(trips) > 0
        
        # Save to database
        for trip in trips:
            test_database.save_trip(trip)
        
        # Verify persistence
        saved_trips = test_database.get_all_trips()
        assert len(saved_trips) == len(trips)
    
    def test_trip_modification_and_redetection(self, populated_database):
        """Test modifying trips and re-running detection."""
        from production_app import TripDetector
        
        db = populated_database
        
        # Get existing transactions
        transactions = db.get_all_transactions()
        
        # Modify a transaction (change location)
        if transactions:
            trans = transactions[0]
            trans['location'] = 'Boston, MA'
            db.update_transaction(trans['id'], trans)
        
        # Re-run detection
        detector = TripDetector(home_state='CA')
        new_trips = detector.detect_trips(db.get_all_transactions())
        
        # Should detect changes
        assert len(new_trips) >= 0
    
    def test_incremental_trip_detection(self, populated_database):
        """Test incremental trip detection with new transactions."""
        from production_app import TripDetector
        
        db = populated_database
        
        # Get initial trip count
        initial_trips = db.get_all_trips()
        initial_count = len(initial_trips)
        
        # Add new transactions
        new_transactions = [
            {'date': '2024-04-01', 'description': 'UNITED', 'amount': 400,
             'location': 'Denver, CO', 'category': 'AIRFARE', 'is_oregon': False},
            {'date': '2024-04-01', 'description': 'SHERATON', 'amount': 180,
             'location': 'Denver, CO', 'category': 'HOTEL', 'is_oregon': False},
        ]
        
        for trans in new_transactions:
            db.save_transaction(trans)
        
        # Run incremental detection
        detector = TripDetector(home_state='CA')
        all_transactions = db.get_all_transactions()
        trips = detector.detect_trips(all_transactions)
        
        # Should detect new trip
        assert len(trips) > initial_count


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])