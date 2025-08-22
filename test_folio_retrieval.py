#!/usr/bin/env python3
"""
Test script for hotel folio retrieval functionality.
"""

from hotel_folio_retriever import HotelFolioRetriever, HotelStay
from datetime import datetime
import json

def test_hotel_identification():
    """Test hotel chain identification."""
    retriever = HotelFolioRetriever()
    
    test_cases = [
        ("MARRIOTT COURTYARD SEATTLE WA", "marriott"),
        ("HILTON GARDEN INN CHICAGO IL", "hilton"), 
        ("HOLIDAY INN EXPRESS DENVER CO", "ihg"),
        ("HYATT REGENCY SAN FRANCISCO CA", "hyatt"),
        ("INDEPENDENT HOTEL NYC NY", None)
    ]
    
    print("Testing hotel chain identification:")
    print("-" * 40)
    
    for hotel_name, expected_chain in test_cases:
        clean_name = retriever._extract_hotel_name(hotel_name)
        identified_chain = retriever._identify_hotel_chain(clean_name)
        
        status = "✓" if identified_chain == expected_chain else "✗"
        print(f"{status} {hotel_name}")
        print(f"   Clean name: {clean_name}")
        print(f"   Expected: {expected_chain}, Got: {identified_chain}")
        print()

def test_email_parsing():
    """Test email pattern matching."""
    retriever = HotelFolioRetriever()
    
    sample_email_text = """
    Dear Guest,
    
    Thank you for your reservation at Marriott Courtyard Seattle.
    
    Confirmation Number: ABC123XYZ
    Check-in: March 15, 2024
    Check-out: March 17, 2024
    
    We look forward to your stay.
    """
    
    print("Testing email parsing:")
    print("-" * 40)
    
    confirmation = retriever._extract_with_patterns(
        sample_email_text, 
        retriever.email_patterns['confirmation_numbers']
    )
    print(f"Confirmation Number: {confirmation}")
    
    check_in = retriever._extract_with_patterns(
        sample_email_text,
        retriever.email_patterns['check_in_dates'] 
    )
    print(f"Check-in Date: {check_in}")
    
    check_out = retriever._extract_with_patterns(
        sample_email_text,
        retriever.email_patterns['check_out_dates']
    )
    print(f"Check-out Date: {check_out}")

def create_sample_hotel_stays():
    """Create sample hotel stays for testing."""
    sample_stays = [
        HotelStay(
            hotel_name="Marriott Courtyard Seattle",
            check_in=datetime(2024, 3, 15),
            check_out=datetime(2024, 3, 17),
            confirmation_number="ABC123XYZ",
            chain="marriott",
            location="Seattle WA",
            total_amount=245.67
        ),
        HotelStay(
            hotel_name="Hilton Garden Inn Chicago",
            check_in=datetime(2024, 4, 10),
            check_out=datetime(2024, 4, 12),
            confirmation_number="HIL456DEF",
            chain="hilton", 
            location="Chicago IL",
            total_amount=198.50
        )
    ]
    
    retriever = HotelFolioRetriever()
    retriever.save_hotel_stays(sample_stays, 'sample_hotel_stays.json')
    
    print("Sample hotel stays saved to sample_hotel_stays.json")
    
    # Display the sample data
    with open('sample_hotel_stays.json', 'r') as f:
        data = json.load(f)
    
    print("\nSample Hotel Stays:")
    print("-" * 40)
    for stay in data:
        print(f"Hotel: {stay['hotel_name']}")
        print(f"Chain: {stay['chain']}")
        print(f"Dates: {stay['check_in']} to {stay['check_out']}")
        print(f"Confirmation: {stay['confirmation_number']}")
        print(f"Amount: ${stay['total_amount']}")
        print()

if __name__ == "__main__":
    print("Hotel Folio Retrieval Test Suite")
    print("=" * 50)
    print()
    
    test_hotel_identification()
    print()
    test_email_parsing()
    print()
    create_sample_hotel_stays()