#!/usr/bin/env python3
"""
Database management for Travel Expense Analyzer
SQLite database with proper schema and relationships
"""

import sqlite3
import json
from datetime import datetime, date
from typing import List, Dict, Optional, Any
from pathlib import Path
import logging
from contextlib import contextmanager
from dataclasses import dataclass, asdict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DatabaseTransaction:
    id: Optional[int]
    date: str
    description: str
    amount: float
    location: Optional[str]
    category: str
    is_oregon: bool
    trip_id: Optional[int] = None
    business_purpose: Optional[str] = None
    vendor_name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class DatabaseTrip:
    id: Optional[int]
    trip_number: int
    primary_location: str
    start_date: str
    end_date: str
    duration_days: int
    total_amount: float
    business_purpose: Optional[str]
    status: str = 'pending'
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class DatabaseReceipt:
    id: Optional[int]
    transaction_id: Optional[int]
    trip_id: Optional[int]
    filename: str
    file_path: str
    file_type: str
    file_size: int
    upload_source: str = 'manual'
    created_at: Optional[str] = None

@dataclass
class DatabaseHotelStay:
    id: Optional[int]
    trip_id: Optional[int]
    hotel_name: str
    check_in: str
    check_out: str
    confirmation_number: Optional[str]
    chain: Optional[str]
    folio_path: Optional[str]
    total_amount: Optional[float]
    created_at: Optional[str] = None

@dataclass
class DatabaseConcurReport:
    id: Optional[int]
    trip_id: int
    report_id: str
    report_name: str
    status: str
    total_amount: float
    submitted_at: Optional[str]
    created_at: Optional[str] = None

class DatabaseManager:
    def __init__(self, db_path: str = "data/expense_tracker.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections with proper error handling."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def init_database(self):
        """Initialize database schema with all required tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create trips table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trip_number INTEGER UNIQUE NOT NULL,
                    primary_location TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    duration_days INTEGER NOT NULL,
                    total_amount REAL NOT NULL DEFAULT 0.0,
                    business_purpose TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create transactions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    description TEXT NOT NULL,
                    amount REAL NOT NULL,
                    location TEXT,
                    category TEXT NOT NULL,
                    is_oregon BOOLEAN NOT NULL DEFAULT 0,
                    trip_id INTEGER,
                    business_purpose TEXT,
                    vendor_name TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE SET NULL
                )
            """)

            # Create receipts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id INTEGER,
                    trip_id INTEGER,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    upload_source TEXT DEFAULT 'manual',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (transaction_id) REFERENCES transactions (id) ON DELETE CASCADE,
                    FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE CASCADE
                )
            """)

            # Create hotel_stays table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hotel_stays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trip_id INTEGER,
                    hotel_name TEXT NOT NULL,
                    check_in TEXT NOT NULL,
                    check_out TEXT NOT NULL,
                    confirmation_number TEXT,
                    chain TEXT,
                    folio_path TEXT,
                    total_amount REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE CASCADE
                )
            """)

            # Create concur_reports table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS concur_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trip_id INTEGER NOT NULL,
                    report_id TEXT NOT NULL,
                    report_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_amount REAL NOT NULL,
                    submitted_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE CASCADE
                )
            """)

            # Create analysis_sessions table for tracking analysis runs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analysis_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_name TEXT,
                    data_source TEXT NOT NULL,
                    date_range_start TEXT,
                    date_range_end TEXT,
                    total_transactions INTEGER,
                    total_trips INTEGER,
                    total_amount REAL,
                    analysis_config TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create user_settings table for app configuration
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    setting_key TEXT UNIQUE NOT NULL,
                    setting_value TEXT NOT NULL,
                    setting_type TEXT DEFAULT 'string',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indices for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_trip_id ON transactions(trip_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_receipts_transaction_id ON receipts(transaction_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_receipts_trip_id ON receipts(trip_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_hotel_stays_trip_id ON hotel_stays(trip_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_concur_reports_trip_id ON concur_reports(trip_id)")

            logger.info("Database initialized successfully")

    # Trip Management
    def save_trips(self, trips: List[Dict]) -> List[int]:
        """Save multiple trips to database and return their IDs."""
        trip_ids = []
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for trip in trips:
                # Convert trip data to database format
                db_trip = DatabaseTrip(
                    id=trip.get('id'),
                    trip_number=trip['trip_number'],
                    primary_location=trip['primary_location'],
                    start_date=trip['start_date'],
                    end_date=trip['end_date'],
                    duration_days=trip['duration_days'],
                    total_amount=trip['total_amount'],
                    business_purpose=trip.get('business_purpose'),
                    status=trip.get('status', 'pending')
                )
                
                if db_trip.id:
                    # Update existing trip
                    cursor.execute("""
                        UPDATE trips SET 
                            primary_location = ?, start_date = ?, end_date = ?, 
                            duration_days = ?, total_amount = ?, business_purpose = ?, 
                            status = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (
                        db_trip.primary_location, db_trip.start_date, db_trip.end_date,
                        db_trip.duration_days, db_trip.total_amount, db_trip.business_purpose,
                        db_trip.status, db_trip.id
                    ))
                    trip_ids.append(db_trip.id)
                else:
                    # Insert new trip
                    cursor.execute("""
                        INSERT INTO trips (
                            trip_number, primary_location, start_date, end_date,
                            duration_days, total_amount, business_purpose, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        db_trip.trip_number, db_trip.primary_location, db_trip.start_date,
                        db_trip.end_date, db_trip.duration_days, db_trip.total_amount,
                        db_trip.business_purpose, db_trip.status
                    ))
                    trip_ids.append(cursor.lastrowid)
        
        logger.info(f"Saved {len(trips)} trips to database")
        return trip_ids

    def get_trips(self, limit: Optional[int] = None) -> List[Dict]:
        """Get all trips from database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM trips ORDER BY start_date DESC"
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            trips = []
            for row in rows:
                trip = dict(row)
                # Get associated transactions
                trip['transactions'] = self.get_transactions_for_trip(trip['id'])
                # Calculate category breakdown
                trip['category_breakdown'] = self.get_trip_category_breakdown(trip['id'])
                # Get transaction count
                trip['transaction_count'] = len(trip['transactions'])
                trips.append(trip)
            
            return trips

    def get_trip_by_id(self, trip_id: int) -> Optional[Dict]:
        """Get a specific trip by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trips WHERE id = ?", (trip_id,))
            row = cursor.fetchone()
            
            if row:
                trip = dict(row)
                trip['transactions'] = self.get_transactions_for_trip(trip_id)
                trip['category_breakdown'] = self.get_trip_category_breakdown(trip_id)
                trip['transaction_count'] = len(trip['transactions'])
                return trip
            
            return None

    def update_trip(self, trip_id: int, update_data: Dict) -> bool:
        """Update a trip with new data."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build dynamic UPDATE query
            fields = []
            values = []
            
            allowed_fields = ['business_purpose', 'primary_location', 'start_date', 'end_date', 'status']
            for field in allowed_fields:
                if field in update_data:
                    fields.append(f"{field} = ?")
                    values.append(update_data[field])
            
            if not fields:
                return False
            
            # Add timestamp and trip_id
            fields.append("updated_at = CURRENT_TIMESTAMP")
            values.append(trip_id)
            
            query = f"UPDATE trips SET {', '.join(fields)} WHERE id = ?"
            
            cursor.execute(query, values)
            return cursor.rowcount > 0

    def get_trip_category_breakdown(self, trip_id: int) -> Dict[str, float]:
        """Get category breakdown for a trip."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT category, SUM(amount) as total
                FROM transactions 
                WHERE trip_id = ? 
                GROUP BY category
            """, (trip_id,))
            
            return {row['category']: row['total'] for row in cursor.fetchall()}

    # Transaction Management
    def save_transactions(self, transactions: List[Any], trip_id: Optional[int] = None) -> List[int]:
        """Save transactions to database."""
        transaction_ids = []
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for transaction in transactions:
                # Handle both dataclass and dict formats
                if hasattr(transaction, '__dict__'):
                    trans_dict = asdict(transaction)
                else:
                    trans_dict = transaction
                
                # Convert date to string if it's a datetime object
                trans_date = trans_dict['date']
                if isinstance(trans_date, (datetime, date)):
                    trans_date = trans_date.isoformat()
                
                cursor.execute("""
                    INSERT INTO transactions (
                        date, description, amount, location, category, 
                        is_oregon, trip_id, business_purpose, vendor_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trans_date,
                    trans_dict['description'],
                    trans_dict['amount'],
                    trans_dict.get('location'),
                    trans_dict['category'],
                    trans_dict['is_oregon'],
                    trip_id,
                    trans_dict.get('business_purpose'),
                    trans_dict.get('vendor_name')
                ))
                
                transaction_ids.append(cursor.lastrowid)
        
        logger.info(f"Saved {len(transactions)} transactions to database")
        return transaction_ids

    def get_transactions_for_trip(self, trip_id: int) -> List[Dict]:
        """Get all transactions for a specific trip."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM transactions 
                WHERE trip_id = ? 
                ORDER BY date ASC
            """, (trip_id,))
            
            return [dict(row) for row in cursor.fetchall()]

    def update_transaction(self, transaction_id: int, updates: Dict) -> bool:
        """Update a transaction with new data."""
        if not updates:
            return False
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build dynamic update query
            set_clauses = []
            values = []
            
            for key, value in updates.items():
                if key in ['category', 'business_purpose', 'vendor_name', 'amount']:
                    set_clauses.append(f"{key} = ?")
                    values.append(value)
            
            if not set_clauses:
                return False
            
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            query = f"UPDATE transactions SET {', '.join(set_clauses)} WHERE id = ?"
            values.append(transaction_id)
            
            cursor.execute(query, values)
            return cursor.rowcount > 0

    # Receipt Management
    def save_receipt(self, receipt_data: Dict) -> int:
        """Save receipt information to database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO receipts (
                    transaction_id, trip_id, filename, file_path, 
                    file_type, file_size, upload_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                receipt_data.get('transaction_id'),
                receipt_data.get('trip_id'),
                receipt_data['filename'],
                receipt_data['file_path'],
                receipt_data['file_type'],
                receipt_data['file_size'],
                receipt_data.get('upload_source', 'manual')
            ))
            
            receipt_id = cursor.lastrowid
            logger.info(f"Saved receipt {receipt_data['filename']} with ID {receipt_id}")
            return receipt_id

    def get_receipts_for_transaction(self, transaction_id: int) -> List[Dict]:
        """Get all receipts for a transaction."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM receipts 
                WHERE transaction_id = ? 
                ORDER BY created_at DESC
            """, (transaction_id,))
            
            return [dict(row) for row in cursor.fetchall()]

    def get_receipts_for_trip(self, trip_id: int) -> List[Dict]:
        """Get all receipts for a trip."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*, t.description as transaction_description
                FROM receipts r
                LEFT JOIN transactions t ON r.transaction_id = t.id
                WHERE r.trip_id = ? 
                ORDER BY r.created_at DESC
            """, (trip_id,))
            
            return [dict(row) for row in cursor.fetchall()]

    def delete_receipt(self, receipt_id: int) -> bool:
        """Delete a receipt from database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
            return cursor.rowcount > 0

    # Hotel Stay Management
    def save_hotel_stays(self, hotel_stays: List[Dict], trip_id: Optional[int] = None) -> List[int]:
        """Save hotel stays to database."""
        stay_ids = []
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for stay in hotel_stays:
                cursor.execute("""
                    INSERT INTO hotel_stays (
                        trip_id, hotel_name, check_in, check_out,
                        confirmation_number, chain, folio_path, total_amount
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trip_id or stay.get('trip_id'),
                    stay['hotel_name'],
                    stay['check_in'],
                    stay['check_out'],
                    stay.get('confirmation_number'),
                    stay.get('chain'),
                    stay.get('folio_path'),
                    stay.get('total_amount')
                ))
                
                stay_ids.append(cursor.lastrowid)
        
        logger.info(f"Saved {len(hotel_stays)} hotel stays to database")
        return stay_ids

    def get_hotel_stays_for_trip(self, trip_id: int) -> List[Dict]:
        """Get hotel stays for a trip."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM hotel_stays 
                WHERE trip_id = ? 
                ORDER BY check_in ASC
            """, (trip_id,))
            
            return [dict(row) for row in cursor.fetchall()]

    # Concur Report Management
    def save_concur_report(self, report_data: Dict) -> int:
        """Save Concur report information."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO concur_reports (
                    trip_id, report_id, report_name, status, 
                    total_amount, submitted_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                report_data['trip_id'],
                report_data['report_id'],
                report_data['report_name'],
                report_data['status'],
                report_data['total_amount'],
                report_data.get('submitted_at')
            ))
            
            return cursor.lastrowid

    def get_concur_reports(self, limit: Optional[int] = None) -> List[Dict]:
        """Get Concur report history."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT cr.*, t.primary_location, t.start_date, t.end_date
                FROM concur_reports cr
                JOIN trips t ON cr.trip_id = t.id
                ORDER BY cr.created_at DESC
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    # Analysis Session Management
    def save_analysis_session(self, session_data: Dict) -> int:
        """Save analysis session metadata."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO analysis_sessions (
                    session_name, data_source, date_range_start, date_range_end,
                    total_transactions, total_trips, total_amount, analysis_config
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_data.get('session_name'),
                session_data['data_source'],
                session_data.get('date_range_start'),
                session_data.get('date_range_end'),
                session_data.get('total_transactions'),
                session_data.get('total_trips'),
                session_data.get('total_amount'),
                json.dumps(session_data.get('analysis_config', {}))
            ))
            
            return cursor.lastrowid

    # Settings Management
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a user setting."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT setting_value, setting_type 
                FROM user_settings 
                WHERE setting_key = ?
            """, (key,))
            
            row = cursor.fetchone()
            if row:
                value = row['setting_value']
                setting_type = row['setting_type']
                
                # Convert based on type
                if setting_type == 'json':
                    return json.loads(value)
                elif setting_type == 'int':
                    return int(value)
                elif setting_type == 'float':
                    return float(value)
                elif setting_type == 'bool':
                    return value.lower() == 'true'
                else:
                    return value
            
            return default

    def set_setting(self, key: str, value: Any) -> None:
        """Set a user setting."""
        # Determine type and convert value
        if isinstance(value, dict) or isinstance(value, list):
            setting_type = 'json'
            setting_value = json.dumps(value)
        elif isinstance(value, bool):
            setting_type = 'bool'
            setting_value = 'true' if value else 'false'
        elif isinstance(value, int):
            setting_type = 'int'
            setting_value = str(value)
        elif isinstance(value, float):
            setting_type = 'float'
            setting_value = str(value)
        else:
            setting_type = 'string'
            setting_value = str(value)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO user_settings 
                (setting_key, setting_value, setting_type, updated_at) 
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (key, setting_value, setting_type))

    # Statistics and Reporting
    def get_receipt_stats(self) -> Dict[str, int]:
        """Get receipt statistics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Total transactions
            cursor.execute("SELECT COUNT(*) as total FROM transactions")
            total_transactions = cursor.fetchone()['total']
            
            # Transactions with receipts
            cursor.execute("""
                SELECT COUNT(DISTINCT t.id) as with_receipts
                FROM transactions t
                JOIN receipts r ON t.id = r.transaction_id
            """)
            with_receipts = cursor.fetchone()['with_receipts']
            
            # Hotel folios
            cursor.execute("SELECT COUNT(*) as folios FROM hotel_stays WHERE folio_path IS NOT NULL")
            folios = cursor.fetchone()['folios']
            
            # Total receipt files
            cursor.execute("SELECT COUNT(*) as total_receipts FROM receipts")
            total_receipts = cursor.fetchone()['total_receipts']
            
            return {
                'complete': with_receipts,
                'missing': total_transactions - with_receipts,
                'folios': folios,
                'total': total_receipts
            }

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get comprehensive dashboard statistics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Trip stats
            cursor.execute("SELECT COUNT(*) as trip_count, SUM(total_amount) as total_amount FROM trips")
            trip_stats = cursor.fetchone()
            
            # Transaction stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as transaction_count,
                    COUNT(CASE WHEN category = 'OTHER' THEN 1 END) as uncategorized_count
                FROM transactions
            """)
            transaction_stats = cursor.fetchone()
            
            # Recent analysis
            cursor.execute("""
                SELECT created_at FROM analysis_sessions 
                ORDER BY created_at DESC LIMIT 1
            """)
            last_analysis = cursor.fetchone()
            
            return {
                'trip_count': trip_stats['trip_count'] or 0,
                'total_amount': trip_stats['total_amount'] or 0.0,
                'transaction_count': transaction_stats['transaction_count'] or 0,
                'uncategorized_count': transaction_stats['uncategorized_count'] or 0,
                'last_analysis': last_analysis['created_at'] if last_analysis else None
            }

    # Data Export/Import
    def export_data(self) -> Dict[str, Any]:
        """Export all data for backup or analysis."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            data = {}
            
            # Export all tables
            tables = ['trips', 'transactions', 'receipts', 'hotel_stays', 'concur_reports']
            
            for table in tables:
                cursor.execute(f"SELECT * FROM {table}")
                data[table] = [dict(row) for row in cursor.fetchall()]
            
            data['exported_at'] = datetime.now().isoformat()
            return data

    def clear_all_data(self) -> None:
        """Clear all data from database (for testing/reset)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Delete in order to respect foreign keys
            tables = ['concur_reports', 'hotel_stays', 'receipts', 'transactions', 'trips', 'analysis_sessions']
            
            for table in tables:
                cursor.execute(f"DELETE FROM {table}")
            
            logger.warning("All data cleared from database")

# Global database instance
db = None

def get_database() -> DatabaseManager:
    """Get global database instance."""
    global db
    if db is None:
        db = DatabaseManager()
    return db

def init_database(db_path: str = None):
    """Initialize database with custom path."""
    global db
    if db_path:
        db = DatabaseManager(db_path)
    else:
        db = get_database()
    return db

if __name__ == "__main__":
    # Test the database functionality
    db = DatabaseManager("test_expense_tracker.db")
    
    print("Database initialized successfully!")
    print("Tables created and ready for use.")
    
    # Test basic functionality
    stats = db.get_dashboard_stats()
    print(f"Dashboard stats: {stats}")