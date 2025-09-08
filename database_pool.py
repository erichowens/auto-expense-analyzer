#!/usr/bin/env python3
"""
Database connection pooling and transaction management.
"""

import sqlite3
from contextlib import contextmanager
from queue import Queue, Empty
import threading
import logging
from typing import Optional, Any
import time

logger = logging.getLogger(__name__)

class ConnectionPool:
    """Thread-safe SQLite connection pool with transaction support."""
    
    def __init__(self, database_path: str, pool_size: int = 5, max_overflow: int = 10, timeout: int = 30):
        """
        Initialize connection pool.
        
        Args:
            database_path: Path to SQLite database
            pool_size: Number of persistent connections
            max_overflow: Maximum overflow connections
            timeout: Connection timeout in seconds
        """
        self.database_path = database_path
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.timeout = timeout
        
        self._pool = Queue(maxsize=pool_size)
        self._overflow = 0
        self._overflow_lock = threading.Lock()
        
        # Initialize the pool with connections
        for _ in range(pool_size):
            conn = self._create_connection()
            self._pool.put(conn)
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection."""
        conn = sqlite3.connect(
            self.database_path,
            timeout=self.timeout,
            check_same_thread=False,
            isolation_level=None  # Use autocommit mode by default
        )
        conn.row_factory = sqlite3.Row
        
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Optimize for concurrent access
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        
        return conn
    
    def get_connection(self, timeout: Optional[float] = None) -> sqlite3.Connection:
        """
        Get a connection from the pool.
        
        Args:
            timeout: Maximum time to wait for a connection
        
        Returns:
            Database connection
        
        Raises:
            TimeoutError: If no connection available within timeout
        """
        timeout = timeout or self.timeout
        
        try:
            # Try to get from pool
            conn = self._pool.get(block=False)
            
            # Verify connection is still valid
            try:
                conn.execute("SELECT 1")
            except sqlite3.Error:
                logger.warning("Stale connection detected, creating new one")
                conn = self._create_connection()
            
            return conn
            
        except Empty:
            # Pool is empty, try to create overflow connection
            with self._overflow_lock:
                if self._overflow < self.max_overflow:
                    self._overflow += 1
                    try:
                        return self._create_connection()
                    except Exception:
                        self._overflow -= 1
                        raise
            
            # Wait for a connection to become available
            try:
                conn = self._pool.get(block=True, timeout=timeout)
                
                # Verify connection
                try:
                    conn.execute("SELECT 1")
                except sqlite3.Error:
                    conn = self._create_connection()
                
                return conn
                
            except Empty:
                raise TimeoutError(f"No database connection available within {timeout} seconds")
    
    def return_connection(self, conn: sqlite3.Connection, close_overflow: bool = False):
        """
        Return a connection to the pool.
        
        Args:
            conn: Connection to return
            close_overflow: Whether to close overflow connections
        """
        if conn is None:
            return
        
        try:
            # Check if this is an overflow connection
            if close_overflow or self._pool.full():
                with self._overflow_lock:
                    if self._overflow > 0:
                        conn.close()
                        self._overflow -= 1
                        return
            
            # Return to pool
            self._pool.put_nowait(conn)
            
        except Exception as e:
            logger.error(f"Error returning connection to pool: {e}")
            try:
                conn.close()
            except Exception:
                pass
    
    @contextmanager
    def get_connection_context(self):
        """
        Context manager for database connections.
        
        Usage:
            with pool.get_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
        """
        conn = None
        try:
            conn = self.get_connection()
            yield conn
        finally:
            if conn:
                self.return_connection(conn)
    
    @contextmanager
    def transaction(self, conn: Optional[sqlite3.Connection] = None):
        """
        Context manager for database transactions.
        
        Usage:
            with pool.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO table VALUES (?)", (value,))
                # Automatically commits on success, rolls back on exception
        """
        own_connection = conn is None
        if own_connection:
            conn = self.get_connection()
        
        try:
            # Begin transaction
            conn.execute("BEGIN")
            yield conn
            # Commit on success
            conn.execute("COMMIT")
        except Exception as e:
            # Rollback on error
            try:
                conn.execute("ROLLBACK")
            except Exception as rollback_error:
                logger.error(f"Error during rollback: {rollback_error}")
            raise e
        finally:
            if own_connection:
                self.return_connection(conn)
    
    def execute(self, query: str, params: tuple = (), fetch: str = None) -> Any:
        """
        Execute a query with automatic connection management.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            fetch: 'one', 'all', or None
        
        Returns:
            Query result or None
        """
        with self.get_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if fetch == 'one':
                return cursor.fetchone()
            elif fetch == 'all':
                return cursor.fetchall()
            else:
                return cursor.lastrowid
    
    def execute_many(self, query: str, params_list: list):
        """
        Execute multiple queries efficiently.
        
        Args:
            query: SQL query to execute
            params_list: List of parameter tuples
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            return cursor.rowcount
    
    def close_all(self):
        """Close all connections in the pool."""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Empty:
                break
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
        
        logger.info("All pool connections closed")

class DatabaseManager:
    """Enhanced database manager with connection pooling and transactions."""
    
    def __init__(self, database_path: str, pool_size: int = 5):
        """Initialize database manager with connection pool."""
        self.pool = ConnectionPool(database_path, pool_size=pool_size)
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize database schema if needed."""
        with self.pool.transaction() as conn:
            cursor = conn.cursor()
            
            # Create tables if they don't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    description TEXT NOT NULL,
                    amount REAL NOT NULL,
                    location TEXT,
                    category TEXT,
                    confidence REAL,
                    trip_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    primary_location TEXT,
                    business_purpose TEXT,
                    total_amount REAL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_trip ON transactions(trip_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_status ON trips(status)")
    
    def get_transactions_by_date_range(self, start_date: str, end_date: Optional[str] = None) -> list:
        """Get transactions within a date range."""
        query = "SELECT * FROM transactions WHERE date >= ?"
        params = [start_date]
        
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        
        query += " ORDER BY date"
        
        return self.pool.execute(query, tuple(params), fetch='all')
    
    def update_transaction_category(self, transaction_id: int, category: str, confidence: float = None):
        """Update transaction category with proper transaction handling."""
        with self.pool.transaction() as conn:
            cursor = conn.cursor()
            
            if confidence is not None:
                cursor.execute("""
                    UPDATE transactions 
                    SET category = ?, confidence = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (category, confidence, transaction_id))
            else:
                cursor.execute("""
                    UPDATE transactions 
                    SET category = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (category, transaction_id))
            
            return cursor.rowcount > 0
    
    def bulk_update_categories(self, updates: list):
        """
        Bulk update transaction categories efficiently.
        
        Args:
            updates: List of (transaction_id, category, confidence) tuples
        """
        query = """
            UPDATE transactions 
            SET category = ?, confidence = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        
        # Reorder parameters for the query
        params_list = [(cat, conf, tid) for tid, cat, conf in updates]
        
        return self.pool.execute_many(query, params_list)
    
    def create_trip(self, trip_data: dict) -> int:
        """Create a new trip with transaction management."""
        with self.pool.transaction() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO trips (start_date, end_date, primary_location, business_purpose, total_amount, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                trip_data.get('start_date'),
                trip_data.get('end_date'),
                trip_data.get('primary_location'),
                trip_data.get('business_purpose'),
                trip_data.get('total_amount', 0),
                trip_data.get('status', 'pending')
            ))
            
            trip_id = cursor.lastrowid
            
            # Update associated transactions
            if 'transaction_ids' in trip_data:
                cursor.executemany(
                    "UPDATE transactions SET trip_id = ? WHERE id = ?",
                    [(trip_id, tid) for tid in trip_data['transaction_ids']]
                )
            
            return trip_id
    
    def get_trip_by_id(self, trip_id: int) -> Optional[dict]:
        """Get trip with all its transactions."""
        with self.pool.get_connection_context() as conn:
            cursor = conn.cursor()
            
            # Get trip
            cursor.execute("SELECT * FROM trips WHERE id = ?", (trip_id,))
            trip = cursor.fetchone()
            
            if not trip:
                return None
            
            # Get associated transactions
            cursor.execute("SELECT * FROM transactions WHERE trip_id = ?", (trip_id,))
            transactions = cursor.fetchall()
            
            # Convert to dictionary
            trip_dict = dict(trip)
            trip_dict['transactions'] = [dict(t) for t in transactions]
            
            return trip_dict
    
    def close(self):
        """Close all database connections."""
        self.pool.close_all()

# Global database instance (will be initialized in the app)
_db_instance: Optional[DatabaseManager] = None

def get_db() -> DatabaseManager:
    """Get the global database instance."""
    global _db_instance
    if _db_instance is None:
        from config import config
        _db_instance = DatabaseManager(
            config.DATABASE_PATH,
            pool_size=config.DATABASE_POOL_SIZE
        )
    return _db_instance