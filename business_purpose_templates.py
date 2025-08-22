#!/usr/bin/env python3
"""
Business Purpose Templates for Quick Expense Reporting
Provides common business purposes and smart suggestions.
"""

from typing import List, Dict, Optional

# Common business purpose templates
BUSINESS_PURPOSE_TEMPLATES = {
    "client_meeting": {
        "title": "Client Meeting",
        "template": "Client meeting with {client_name} in {location}",
        "keywords": ["client", "meeting", "sales", "presentation"],
        "categories": ["AIRFARE", "HOTEL", "MEALS", "TRANSPORTATION"]
    },
    "conference": {
        "title": "Professional Conference",
        "template": "Attending {conference_name} conference for professional development",
        "keywords": ["conference", "training", "summit", "convention"],
        "categories": ["AIRFARE", "HOTEL", "MEALS"]
    },
    "training": {
        "title": "Training/Education",
        "template": "Professional training: {training_topic}",
        "keywords": ["training", "education", "workshop", "certification"],
        "categories": ["AIRFARE", "HOTEL", "MEALS"]
    },
    "trade_show": {
        "title": "Trade Show/Exhibition",
        "template": "Attending {event_name} trade show for business development",
        "keywords": ["trade", "show", "exhibition", "expo"],
        "categories": ["AIRFARE", "HOTEL", "MEALS", "TRANSPORTATION"]
    },
    "company_meeting": {
        "title": "Company Meeting",
        "template": "Company meeting at {office_location}",
        "keywords": ["company", "corporate", "office", "headquarters"],
        "categories": ["AIRFARE", "HOTEL", "MEALS", "TRANSPORTATION"]
    },
    "site_visit": {
        "title": "Site Visit/Inspection",
        "template": "Site visit and inspection at {site_location}",
        "keywords": ["site", "visit", "inspection", "field"],
        "categories": ["AIRFARE", "HOTEL", "MEALS", "TRANSPORTATION"]
    },
    "business_development": {
        "title": "Business Development",
        "template": "Business development activities in {location}",
        "keywords": ["business", "development", "partnership", "vendor"],
        "categories": ["AIRFARE", "HOTEL", "MEALS", "TRANSPORTATION"]
    }
}

# Location-based business purpose suggestions
LOCATION_BUSINESS_SUGGESTIONS = {
    "seattle": ["Microsoft partnership meeting", "Amazon vendor meeting", "Tech conference"],
    "san_francisco": ["Silicon Valley client meetings", "Tech startup meetings", "VC meetings"],
    "new_york": ["Financial client meetings", "Corporate headquarters visit", "Media meetings"],
    "chicago": ["Manufacturing client visit", "Logistics meeting", "Central office visit"],
    "los_angeles": ["Entertainment industry meeting", "West Coast client visit", "Media production"],
    "atlanta": ["Southeast region meeting", "Delta Airlines partnership", "Logistics hub visit"],
    "dallas": ["Energy sector meeting", "Southwest region meeting", "Oil & gas client visit"],
    "boston": ["Healthcare client meeting", "Biotech conference", "University partnership"],
    "austin": ["Tech startup meeting", "SXSW conference", "Music industry meeting"],
    "denver": ["Mountain region meeting", "Outdoor industry conference", "Mining client visit"]
}

class BusinessPurposeManager:
    """Manages business purpose templates and suggestions."""
    
    def __init__(self):
        self.templates = BUSINESS_PURPOSE_TEMPLATES
        self.location_suggestions = LOCATION_BUSINESS_SUGGESTIONS
    
    def get_templates(self) -> List[Dict]:
        """Get all business purpose templates."""
        return [
            {
                'id': key,
                'title': template['title'],
                'template': template['template'],
                'keywords': template['keywords']
            }
            for key, template in self.templates.items()
        ]
    
    def suggest_by_location(self, location: str) -> List[str]:
        """Suggest business purposes based on location."""
        if not location:
            return []
        
        location_lower = location.lower()
        suggestions = []
        
        # Check for direct city matches
        for city, city_suggestions in self.location_suggestions.items():
            if city in location_lower:
                suggestions.extend(city_suggestions)
        
        # Add generic suggestions based on keywords
        if any(keyword in location_lower for keyword in ['silicon valley', 'tech', 'software']):
            suggestions.extend(["Tech industry meeting", "Software development meeting"])
        
        if any(keyword in location_lower for keyword in ['financial', 'wall street', 'banking']):
            suggestions.extend(["Financial services meeting", "Banking client visit"])
        
        return list(set(suggestions))  # Remove duplicates
    
    def suggest_by_expenses(self, expenses: List[Dict]) -> List[str]:
        """Suggest business purposes based on expense patterns."""
        suggestions = []
        
        # Analyze expense categories
        categories = set()
        locations = set()
        merchants = []
        
        for expense in expenses:
            if expense.get('category'):
                categories.add(expense['category'])
            if expense.get('location'):
                locations.add(expense['location'])
            if expense.get('description'):
                merchants.append(expense['description'].lower())
        
        # Conference indicators
        if any(keyword in ' '.join(merchants) for keyword in ['convention', 'conference', 'summit']):
            suggestions.append("Professional development conference")
        
        # Hotel chains indicate business travel
        hotel_chains = ['hilton', 'marriott', 'hyatt', 'sheraton', 'holiday inn']
        if any(chain in ' '.join(merchants) for chain in hotel_chains):
            suggestions.append("Business travel accommodation")
        
        # Airlines indicate longer trips
        if 'AIRFARE' in categories:
            suggestions.extend([
                "Client meeting requiring air travel",
                "Multi-day business conference",
                "Regional business meeting"
            ])
        
        # Multiple meal expenses indicate multi-day trip
        if merchants.count('meals') >= 3 or len([m for m in merchants if 'restaurant' in m or 'starbucks' in m]) >= 3:
            suggestions.append("Multi-day business trip")
        
        return suggestions
    
    def generate_smart_purpose(self, trip_data: Dict) -> Optional[str]:
        """Generate a smart business purpose suggestion based on trip data."""
        location = trip_data.get('primary_location', '')
        expenses = trip_data.get('transactions', [])
        duration = trip_data.get('duration_days', 0)
        
        # Try location-based suggestion first
        location_suggestions = self.suggest_by_location(location)
        if location_suggestions:
            return location_suggestions[0]
        
        # Try expense pattern-based suggestion
        expense_suggestions = self.suggest_by_expenses(expenses)
        if expense_suggestions:
            return expense_suggestions[0]
        
        # Default based on duration and location
        if location:
            city = location.split(',')[0].strip()
            if duration > 2:
                return f"Multi-day business meeting in {city}"
            else:
                return f"Business meeting in {city}"
        
        # Fallback
        if duration > 2:
            return "Multi-day business trip"
        else:
            return "Business meeting"
    
    def validate_business_purpose(self, purpose: str) -> Dict[str, any]:
        """Validate and provide feedback on business purpose."""
        if not purpose or len(purpose.strip()) < 5:
            return {
                'valid': False,
                'message': 'Business purpose must be at least 5 characters long'
            }
        
        # Check for vague purposes that might be rejected
        vague_keywords = ['meeting', 'trip', 'travel', 'business']
        if purpose.lower().strip() in vague_keywords:
            return {
                'valid': False,
                'message': 'Business purpose is too vague. Please be more specific.',
                'suggestions': [
                    'Client meeting with [client name]',
                    'Professional development training',
                    'Trade show attendance for business development'
                ]
            }
        
        # Check for personal indicators
        personal_keywords = ['vacation', 'personal', 'family', 'leisure', 'fun']
        if any(keyword in purpose.lower() for keyword in personal_keywords):
            return {
                'valid': False,
                'message': 'Business purpose cannot contain personal activity indicators'
            }
        
        # Good business purpose
        return {
            'valid': True,
            'message': 'Business purpose looks good'
        }

# Global instance
business_purpose_manager = BusinessPurposeManager()

def get_business_purpose_templates() -> List[Dict]:
    """Get all available business purpose templates."""
    return business_purpose_manager.get_templates()

def suggest_business_purpose(trip_data: Dict) -> Dict:
    """Get smart business purpose suggestions for a trip."""
    smart_suggestion = business_purpose_manager.generate_smart_purpose(trip_data)
    location_suggestions = business_purpose_manager.suggest_by_location(
        trip_data.get('primary_location', '')
    )
    expense_suggestions = business_purpose_manager.suggest_by_expenses(
        trip_data.get('transactions', [])
    )
    
    return {
        'smart_suggestion': smart_suggestion,
        'location_based': location_suggestions[:3],  # Top 3
        'expense_based': expense_suggestions[:3],    # Top 3
        'templates': business_purpose_manager.get_templates()
    }

def validate_business_purpose(purpose: str) -> Dict:
    """Validate a business purpose."""
    return business_purpose_manager.validate_business_purpose(purpose)

if __name__ == '__main__':
    # Test the business purpose system
    print("🎯 Business Purpose Template System Test")
    print("=" * 40)
    
    # Test templates
    templates = get_business_purpose_templates()
    print(f"Available templates: {len(templates)}")
    for template in templates[:3]:
        print(f"- {template['title']}: {template['template']}")
    
    # Test smart suggestions
    test_trip = {
        'primary_location': 'Seattle, WA',
        'duration_days': 3,
        'transactions': [
            {'category': 'AIRFARE', 'description': 'DELTA AIR'},
            {'category': 'HOTEL', 'description': 'HILTON SEATTLE'},
            {'category': 'MEALS', 'description': 'STARBUCKS'}
        ]
    }
    
    suggestions = suggest_business_purpose(test_trip)
    print(f"\nSmart suggestion: {suggestions['smart_suggestion']}")
    print(f"Location suggestions: {suggestions['location_based']}")
    
    # Test validation
    validations = [
        "Client meeting with Microsoft",
        "meeting",
        "Vacation trip",
        "Professional development conference"
    ]
    
    print("\nValidation tests:")
    for purpose in validations:
        result = validate_business_purpose(purpose)
        status = "✅" if result['valid'] else "❌"
        print(f"{status} '{purpose}' - {result['message']}")