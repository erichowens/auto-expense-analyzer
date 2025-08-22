#!/usr/bin/env python3
"""
Hotel Folio Retriever
Automatically identifies hotel stays and retrieves folios from various sources.
"""

import re
import os
import json
import email
import imaplib
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
import argparse
from pathlib import Path

try:
    import requests
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from bs4 import BeautifulSoup
    import PyPDF2
    from dotenv import load_dotenv
    AUTOMATION_AVAILABLE = True
except ImportError:
    AUTOMATION_AVAILABLE = False

@dataclass
class HotelStay:
    hotel_name: str
    check_in: datetime
    check_out: datetime
    confirmation_number: Optional[str] = None
    email_subject: Optional[str] = None
    folio_url: Optional[str] = None
    folio_path: Optional[str] = None
    total_amount: Optional[float] = None
    chain: Optional[str] = None
    location: Optional[str] = None

@dataclass
class FolioData:
    hotel_name: str
    confirmation_number: str
    check_in: datetime
    check_out: datetime
    room_charges: List[Dict]
    tax_charges: List[Dict]
    total_amount: float
    guest_name: Optional[str] = None
    room_number: Optional[str] = None

class HotelFolioRetriever:
    def __init__(self):
        load_dotenv()
        
        self.hotel_chains = {
            'marriott': {
                'names': ['marriott', 'courtyard', 'residence inn', 'fairfield', 'springhill', 'towneplace'],
                'login_url': 'https://www.marriott.com/loyalty/login/default.mi',
                'folio_base': 'https://www.marriott.com'
            },
            'hilton': {
                'names': ['hilton', 'hampton', 'embassy', 'doubletree', 'homewood', 'home2'],
                'login_url': 'https://www.hilton.com/en/hilton-honors/sign-in/',
                'folio_base': 'https://www.hilton.com'
            },
            'hyatt': {
                'names': ['hyatt', 'grand hyatt', 'park hyatt', 'andaz'],
                'login_url': 'https://world.hyatt.com/content/gp/en/member/sign-in.html',
                'folio_base': 'https://world.hyatt.com'
            },
            'ihg': {
                'names': ['holiday inn', 'crowne plaza', 'intercontinental', 'staybridge'],
                'login_url': 'https://www.ihg.com/rewardsclub/content/us/en/member/sign-in',
                'folio_base': 'https://www.ihg.com'
            }
        }
        
        self.email_patterns = {
            'confirmation_numbers': [
                r'confirmation\s*(?:number|#)?\s*:?\s*([A-Z0-9]{6,12})',
                r'reservation\s*(?:number|#)?\s*:?\s*([A-Z0-9]{6,12})',
                r'booking\s*(?:number|#)?\s*:?\s*([A-Z0-9]{6,12})'
            ],
            'check_in_dates': [
                r'check[-\s]?in\s*:?\s*(\w+\s+\d{1,2},?\s+\d{4})',
                r'arrival\s*:?\s*(\w+\s+\d{1,2},?\s+\d{4})'
            ],
            'check_out_dates': [
                r'check[-\s]?out\s*:?\s*(\w+\s+\d{1,2},?\s+\d{4})',
                r'departure\s*:?\s*(\w+\s+\d{1,2},?\s+\d{4})'
            ]
        }

    def identify_hotel_stays_from_transactions(self, transactions) -> List[HotelStay]:
        """Identify hotel stays from transaction data."""
        hotel_stays = []
        
        for transaction in transactions:
            if transaction.category == 'HOTEL':
                hotel_name = self._extract_hotel_name(transaction.description)
                chain = self._identify_hotel_chain(hotel_name)
                
                hotel_stay = HotelStay(
                    hotel_name=hotel_name,
                    check_in=transaction.date,
                    check_out=transaction.date + timedelta(days=1),  # Estimate
                    total_amount=transaction.amount,
                    chain=chain,
                    location=transaction.location
                )
                hotel_stays.append(hotel_stay)
        
        return hotel_stays

    def search_email_for_hotel_confirmations(self, email_config: Dict) -> List[HotelStay]:
        """Search email for hotel confirmation emails."""
        if not AUTOMATION_AVAILABLE:
            print("Email automation not available. Install requirements.")
            return []
        
        hotel_stays = []
        
        try:
            # Connect to email
            mail = imaplib.IMAP4_SSL(email_config['imap_server'])
            mail.login(email_config['username'], email_config['password'])
            mail.select('inbox')
            
            # Search for hotel-related emails
            search_terms = [
                'FROM "marriott"',
                'FROM "hilton"', 
                'FROM "hyatt"',
                'FROM "ihg"',
                'SUBJECT "confirmation"',
                'SUBJECT "reservation"'
            ]
            
            for term in search_terms:
                typ, data = mail.search(None, term)
                
                for num in data[0].split():
                    typ, data = mail.fetch(num, '(RFC822)')
                    email_body = data[0][1]
                    email_message = email.message_from_bytes(email_body)
                    
                    hotel_stay = self._parse_hotel_email(email_message)
                    if hotel_stay:
                        hotel_stays.append(hotel_stay)
            
            mail.close()
            mail.logout()
            
        except Exception as e:
            print(f"Error accessing email: {e}")
        
        return hotel_stays

    def retrieve_folio_from_website(self, hotel_stay: HotelStay, credentials: Dict) -> Optional[str]:
        """Retrieve folio PDF from hotel website."""
        if not AUTOMATION_AVAILABLE:
            print("Web automation not available. Install requirements.")
            return None
        
        if not hotel_stay.chain or hotel_stay.chain not in self.hotel_chains:
            print(f"Unsupported hotel chain: {hotel_stay.chain}")
            return None
        
        chain_info = self.hotel_chains[hotel_stay.chain]
        
        try:
            # Setup headless browser
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            driver = webdriver.Chrome(options=chrome_options)
            
            # Login to hotel website
            driver.get(chain_info['login_url'])
            
            # Fill login credentials (implementation varies by chain)
            if hotel_stay.chain == 'marriott':
                folio_path = self._retrieve_marriott_folio(driver, hotel_stay, credentials)
            elif hotel_stay.chain == 'hilton':
                folio_path = self._retrieve_hilton_folio(driver, hotel_stay, credentials)
            # Add other chains as needed
            
            driver.quit()
            return folio_path
            
        except Exception as e:
            print(f"Error retrieving folio for {hotel_stay.hotel_name}: {e}")
            return None

    def _retrieve_marriott_folio(self, driver, hotel_stay: HotelStay, credentials: Dict) -> Optional[str]:
        """Retrieve folio from Marriott website."""
        try:
            # Login
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "sign-in-email-text-input"))
            )
            username_field.send_keys(credentials['username'])
            
            password_field = driver.find_element(By.ID, "sign-in-password-text-input")
            password_field.send_keys(credentials['password'])
            
            login_button = driver.find_element(By.ID, "sign-in-btn")
            login_button.click()
            
            # Navigate to reservations
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "account-menu"))
            )
            
            driver.get("https://www.marriott.com/loyalty/reservations/default.mi")
            
            # Find reservation and download folio
            # This is a simplified implementation - actual implementation would need
            # to handle the specific UI elements and workflows
            
            # Look for confirmation number
            if hotel_stay.confirmation_number:
                # Implementation would search for the specific reservation
                # and download the folio PDF
                pass
            
            return None  # Placeholder
            
        except Exception as e:
            print(f"Error with Marriott folio retrieval: {e}")
            return None

    def parse_folio_pdf(self, folio_path: str) -> Optional[FolioData]:
        """Parse hotel folio PDF to extract structured data."""
        if not AUTOMATION_AVAILABLE:
            print("PDF parsing not available. Install requirements.")
            return None
        
        try:
            with open(folio_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                
                for page in pdf_reader.pages:
                    text += page.extract_text()
            
            # Parse the text to extract structured data
            folio_data = self._parse_folio_text(text)
            return folio_data
            
        except Exception as e:
            print(f"Error parsing PDF {folio_path}: {e}")
            return None

    def _extract_hotel_name(self, description: str) -> str:
        """Extract clean hotel name from transaction description."""
        # Remove common transaction prefixes/suffixes
        cleaned = re.sub(r'^(TST\*|SQ \*|)', '', description)
        cleaned = re.sub(r'\s+\d{2}/\d{2}$', '', cleaned)  # Remove date suffixes
        cleaned = re.sub(r'\s+[A-Z]{2}$', '', cleaned)      # Remove state codes
        
        # Extract hotel name (everything before location indicators)
        hotel_match = re.match(r'^([^#\d]+?)(?:\s+#|\s+\d+|\s+[A-Z]{2}\s*$)', cleaned)
        if hotel_match:
            return hotel_match.group(1).strip()
        
        return cleaned.strip()

    def _identify_hotel_chain(self, hotel_name: str) -> Optional[str]:
        """Identify hotel chain from hotel name."""
        hotel_lower = hotel_name.lower()
        
        for chain, info in self.hotel_chains.items():
            for name in info['names']:
                if name in hotel_lower:
                    return chain
        
        return None

    def _parse_hotel_email(self, email_message) -> Optional[HotelStay]:
        """Parse hotel confirmation email to extract stay details."""
        subject = email_message.get('Subject', '')
        from_addr = email_message.get('From', '')
        
        # Get email body
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
        else:
            body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
        
        # Extract information using patterns
        confirmation_number = self._extract_with_patterns(body, self.email_patterns['confirmation_numbers'])
        check_in_str = self._extract_with_patterns(body, self.email_patterns['check_in_dates'])
        check_out_str = self._extract_with_patterns(body, self.email_patterns['check_out_dates'])
        
        if not confirmation_number:
            return None
        
        # Parse dates
        check_in = self._parse_date_string(check_in_str) if check_in_str else None
        check_out = self._parse_date_string(check_out_str) if check_out_str else None
        
        # Extract hotel name from email
        hotel_name = self._extract_hotel_name_from_email(from_addr, subject, body)
        chain = self._identify_hotel_chain(hotel_name) if hotel_name else None
        
        if hotel_name and confirmation_number:
            return HotelStay(
                hotel_name=hotel_name,
                check_in=check_in or datetime.now(),
                check_out=check_out or datetime.now(),
                confirmation_number=confirmation_number,
                email_subject=subject,
                chain=chain
            )
        
        return None

    def _extract_with_patterns(self, text: str, patterns: List[str]) -> Optional[str]:
        """Extract information using regex patterns."""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _parse_date_string(self, date_str: str) -> Optional[datetime]:
        """Parse various date string formats."""
        if not date_str:
            return None
        
        date_formats = [
            '%B %d, %Y',
            '%b %d, %Y', 
            '%m/%d/%Y',
            '%Y-%m-%d'
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        
        return None

    def _extract_hotel_name_from_email(self, from_addr: str, subject: str, body: str) -> Optional[str]:
        """Extract hotel name from email metadata."""
        # Try to extract from sender domain
        if '@marriott' in from_addr:
            return 'Marriott'
        elif '@hilton' in from_addr:
            return 'Hilton'
        elif '@hyatt' in from_addr:
            return 'Hyatt'
        elif '@ihg' in from_addr:
            return 'Holiday Inn'
        
        # Try to extract from subject line
        hotel_patterns = [
            r'(marriott|hilton|hyatt|holiday inn|crowne plaza)',
            r'your\s+reservation\s+at\s+([^,\n]+)',
            r'booking\s+confirmation\s+for\s+([^,\n]+)'
        ]
        
        for pattern in hotel_patterns:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                return match.group(1).title()
        
        return None

    def _parse_folio_text(self, text: str) -> Optional[FolioData]:
        """Parse folio text to extract structured data."""
        # This is a simplified implementation
        # Real implementation would need to handle various folio formats
        
        lines = text.split('\n')
        
        # Extract basic information
        hotel_name = None
        confirmation_number = None
        guest_name = None
        room_number = None
        check_in = None
        check_out = None
        total_amount = 0.0
        
        room_charges = []
        tax_charges = []
        
        for line in lines:
            line = line.strip()
            
            # Extract dates
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', line)
            if date_match and 'check' in line.lower():
                date_str = date_match.group(1)
                try:
                    date_obj = datetime.strptime(date_str, '%m/%d/%Y')
                    if 'in' in line.lower():
                        check_in = date_obj
                    elif 'out' in line.lower():
                        check_out = date_obj
                except ValueError:
                    pass
            
            # Extract charges
            charge_match = re.search(r'(.+?)\s+\$?([\d,]+\.\d{2})', line)
            if charge_match:
                description = charge_match.group(1).strip()
                amount = float(charge_match.group(2).replace(',', ''))
                
                if 'room' in description.lower():
                    room_charges.append({'description': description, 'amount': amount})
                elif 'tax' in description.lower():
                    tax_charges.append({'description': description, 'amount': amount})
                
                if 'total' in description.lower():
                    total_amount = amount
        
        if confirmation_number and hotel_name:
            return FolioData(
                hotel_name=hotel_name or "Unknown",
                confirmation_number=confirmation_number or "Unknown",
                check_in=check_in or datetime.now(),
                check_out=check_out or datetime.now(),
                room_charges=room_charges,
                tax_charges=tax_charges,
                total_amount=total_amount,
                guest_name=guest_name,
                room_number=room_number
            )
        
        return None

    def save_hotel_stays(self, hotel_stays: List[HotelStay], filename: str):
        """Save hotel stays to JSON file."""
        data = [asdict(stay, default=str) for stay in hotel_stays]
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)

def main():
    parser = argparse.ArgumentParser(description='Retrieve hotel folios automatically')
    parser.add_argument('--email-config', help='Email configuration JSON file')
    parser.add_argument('--hotel-credentials', help='Hotel website credentials JSON file')
    parser.add_argument('--transactions-file', help='Transactions JSON file from expense analyzer')
    parser.add_argument('--output-dir', default='folios', help='Output directory for folios')
    parser.add_argument('--search-email', action='store_true', help='Search email for confirmations')
    parser.add_argument('--download-folios', action='store_true', help='Download folios from websites')
    
    args = parser.parse_args()
    
    if not AUTOMATION_AVAILABLE:
        print("Missing dependencies. Install with: pip install selenium beautifulsoup4 PyPDF2")
        return
    
    retriever = HotelFolioRetriever()
    hotel_stays = []
    
    # Load transactions if provided
    if args.transactions_file:
        with open(args.transactions_file, 'r') as f:
            # This would need to be integrated with the expense analyzer
            pass
    
    # Search email for confirmations
    if args.search_email and args.email_config:
        with open(args.email_config, 'r') as f:
            email_config = json.load(f)
        
        print("Searching email for hotel confirmations...")
        email_stays = retriever.search_email_for_hotel_confirmations(email_config)
        hotel_stays.extend(email_stays)
        print(f"Found {len(email_stays)} hotel stays in email")
    
    # Download folios
    if args.download_folios and args.hotel_credentials:
        with open(args.hotel_credentials, 'r') as f:
            credentials = json.load(f)
        
        os.makedirs(args.output_dir, exist_ok=True)
        
        for stay in hotel_stays:
            if stay.chain and stay.chain in credentials:
                print(f"Retrieving folio for {stay.hotel_name}...")
                folio_path = retriever.retrieve_folio_from_website(stay, credentials[stay.chain])
                if folio_path:
                    stay.folio_path = folio_path
    
    # Save results
    if hotel_stays:
        retriever.save_hotel_stays(hotel_stays, 'hotel_stays.json')
        print(f"Saved {len(hotel_stays)} hotel stays to hotel_stays.json")
    
    print("Hotel folio retrieval complete!")

if __name__ == "__main__":
    main()