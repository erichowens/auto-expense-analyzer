#!/usr/bin/env python3
"""
Security Helper Functions
Provides secure implementations for common operations to prevent vulnerabilities.
"""

import os
import secrets
import hashlib
import hmac
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta
from functools import wraps
from flask import session, request, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import bleach


class SecurityConfig:
    """Security configuration and constants."""
    
    # Session configuration
    SESSION_LIFETIME_MINUTES = 30
    SESSION_RENEWAL_THRESHOLD = 5  # Renew if less than 5 minutes left
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15
    
    # Input validation limits
    MAX_STRING_LENGTH = 1000
    MAX_TEXT_LENGTH = 10000
    MAX_AMOUNT = 1000000.00
    MIN_AMOUNT = 0.00
    
    # CSRF token configuration
    CSRF_TOKEN_LENGTH = 32
    CSRF_HEADER_NAME = 'X-CSRF-Token'
    CSRF_FORM_FIELD = 'csrf_token'
    
    # SQL query timeout
    QUERY_TIMEOUT_SECONDS = 30
    
    # Allowed file extensions for uploads
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'csv'}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class SQLQueryBuilder:
    """Safe SQL query builder using parameterized queries."""
    
    @staticmethod
    def insert(table: str, data: Dict[str, Any]) -> Tuple[str, List]:
        """
        Build a safe INSERT query.
        
        Args:
            table: Table name (will be validated)
            data: Dictionary of column:value pairs
            
        Returns:
            Tuple of (query_string, parameters)
        """
        if not SQLQueryBuilder._validate_table_name(table):
            raise ValueError(f"Invalid table name: {table}")
        
        columns = []
        placeholders = []
        values = []
        
        for col, val in data.items():
            if not SQLQueryBuilder._validate_column_name(col):
                raise ValueError(f"Invalid column name: {col}")
            columns.append(col)
            placeholders.append('?')
            values.append(val)
        
        query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        return query, values
    
    @staticmethod
    def update(table: str, data: Dict[str, Any], where: Dict[str, Any]) -> Tuple[str, List]:
        """
        Build a safe UPDATE query.
        
        Args:
            table: Table name
            data: Dictionary of column:value pairs to update
            where: Dictionary of conditions
            
        Returns:
            Tuple of (query_string, parameters)
        """
        if not SQLQueryBuilder._validate_table_name(table):
            raise ValueError(f"Invalid table name: {table}")
        
        set_parts = []
        values = []
        
        for col, val in data.items():
            if not SQLQueryBuilder._validate_column_name(col):
                raise ValueError(f"Invalid column name: {col}")
            set_parts.append(f"{col} = ?")
            values.append(val)
        
        where_parts = []
        for col, val in where.items():
            if not SQLQueryBuilder._validate_column_name(col):
                raise ValueError(f"Invalid column name: {col}")
            where_parts.append(f"{col} = ?")
            values.append(val)
        
        query = f"UPDATE {table} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"
        return query, values
    
    @staticmethod
    def select(table: str, columns: List[str] = None, where: Dict[str, Any] = None, 
               order_by: str = None, limit: int = None) -> Tuple[str, List]:
        """
        Build a safe SELECT query.
        
        Args:
            table: Table name
            columns: List of column names (default: all)
            where: Dictionary of conditions
            order_by: Column to order by
            limit: Maximum number of results
            
        Returns:
            Tuple of (query_string, parameters)
        """
        if not SQLQueryBuilder._validate_table_name(table):
            raise ValueError(f"Invalid table name: {table}")
        
        # Build column list
        if columns:
            validated_columns = []
            for col in columns:
                if not SQLQueryBuilder._validate_column_name(col):
                    raise ValueError(f"Invalid column name: {col}")
                validated_columns.append(col)
            column_str = ', '.join(validated_columns)
        else:
            column_str = '*'
        
        query = f"SELECT {column_str} FROM {table}"
        values = []
        
        # Add WHERE clause
        if where:
            where_parts = []
            for col, val in where.items():
                if not SQLQueryBuilder._validate_column_name(col):
                    raise ValueError(f"Invalid column name: {col}")
                where_parts.append(f"{col} = ?")
                values.append(val)
            query += f" WHERE {' AND '.join(where_parts)}"
        
        # Add ORDER BY
        if order_by:
            if not SQLQueryBuilder._validate_column_name(order_by.replace(' DESC', '').replace(' ASC', '')):
                raise ValueError(f"Invalid order by column: {order_by}")
            query += f" ORDER BY {order_by}"
        
        # Add LIMIT
        if limit:
            if not isinstance(limit, int) or limit < 1 or limit > 10000:
                raise ValueError(f"Invalid limit: {limit}")
            query += f" LIMIT {limit}"
        
        return query, values
    
    @staticmethod
    def delete(table: str, where: Dict[str, Any]) -> Tuple[str, List]:
        """
        Build a safe DELETE query.
        
        Args:
            table: Table name
            where: Dictionary of conditions
            
        Returns:
            Tuple of (query_string, parameters)
        """
        if not SQLQueryBuilder._validate_table_name(table):
            raise ValueError(f"Invalid table name: {table}")
        
        if not where:
            raise ValueError("DELETE requires WHERE conditions")
        
        where_parts = []
        values = []
        
        for col, val in where.items():
            if not SQLQueryBuilder._validate_column_name(col):
                raise ValueError(f"Invalid column name: {col}")
            where_parts.append(f"{col} = ?")
            values.append(val)
        
        query = f"DELETE FROM {table} WHERE {' AND '.join(where_parts)}"
        return query, values
    
    @staticmethod
    def _validate_table_name(name: str) -> bool:
        """Validate table name against SQL injection."""
        pattern = r'^[a-zA-Z_][a-zA-Z0-9_]{0,63}$'
        return bool(re.match(pattern, name))
    
    @staticmethod
    def _validate_column_name(name: str) -> bool:
        """Validate column name against SQL injection."""
        pattern = r'^[a-zA-Z_][a-zA-Z0-9_]{0,63}$'
        return bool(re.match(pattern, name))


class SecureDatabase:
    """Secure database operations wrapper."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        
    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path, timeout=SecurityConfig.QUERY_TIMEOUT_SECONDS)
        self.conn.row_factory = sqlite3.Row
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
            self.conn.close()
    
    def execute(self, query: str, params: Union[List, Tuple] = None) -> sqlite3.Cursor:
        """Execute a parameterized query safely."""
        if not self.conn:
            raise RuntimeError("Database connection not established")
        
        cursor = self.conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor
    
    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """Safe insert operation."""
        query, params = SQLQueryBuilder.insert(table, data)
        cursor = self.execute(query, params)
        return cursor.lastrowid
    
    def update(self, table: str, data: Dict[str, Any], where: Dict[str, Any]) -> int:
        """Safe update operation."""
        query, params = SQLQueryBuilder.update(table, data, where)
        cursor = self.execute(query, params)
        return cursor.rowcount
    
    def select(self, table: str, **kwargs) -> List[sqlite3.Row]:
        """Safe select operation."""
        query, params = SQLQueryBuilder.select(table, **kwargs)
        cursor = self.execute(query, params)
        return cursor.fetchall()
    
    def delete(self, table: str, where: Dict[str, Any]) -> int:
        """Safe delete operation."""
        query, params = SQLQueryBuilder.delete(table, where)
        cursor = self.execute(query, params)
        return cursor.rowcount


class InputValidator:
    """Input validation and sanitization utilities."""
    
    @staticmethod
    def validate_string(value: str, max_length: int = None, 
                        pattern: str = None, name: str = "input") -> str:
        """
        Validate and sanitize string input.
        
        Args:
            value: Input string
            max_length: Maximum allowed length
            pattern: Regex pattern to match
            name: Field name for error messages
            
        Returns:
            Sanitized string
            
        Raises:
            ValueError: If validation fails
        """
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        
        # Strip whitespace
        value = value.strip()
        
        # Check length
        if max_length and len(value) > max_length:
            raise ValueError(f"{name} exceeds maximum length of {max_length}")
        
        # Check pattern
        if pattern and not re.match(pattern, value):
            raise ValueError(f"{name} contains invalid characters")
        
        # Sanitize HTML/script tags
        value = bleach.clean(value, tags=[], strip=True)
        
        return value
    
    @staticmethod
    def validate_email(email: str) -> str:
        """Validate email address."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        email = InputValidator.validate_string(email, max_length=255, pattern=pattern, name="email")
        return email.lower()
    
    @staticmethod
    def validate_amount(amount: Union[str, float], min_val: float = None, 
                       max_val: float = None) -> float:
        """Validate monetary amount."""
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            raise ValueError("Invalid amount format")
        
        if min_val is not None and amount < min_val:
            raise ValueError(f"Amount must be at least {min_val}")
        
        if max_val is not None and amount > max_val:
            raise ValueError(f"Amount must not exceed {max_val}")
        
        # Round to 2 decimal places
        return round(amount, 2)
    
    @staticmethod
    def validate_date(date_str: str, format: str = '%Y-%m-%d') -> datetime:
        """Validate date string."""
        try:
            return datetime.strptime(date_str, format)
        except ValueError:
            raise ValueError(f"Invalid date format. Expected {format}")
    
    @staticmethod
    def validate_state_code(state: str) -> str:
        """Validate US state code."""
        valid_states = {
            'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
            'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
            'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
            'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
            'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
        }
        
        state = state.upper().strip()
        if state not in valid_states:
            raise ValueError(f"Invalid state code: {state}")
        
        return state
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename for safe storage."""
        # Remove directory traversal attempts
        filename = os.path.basename(filename)
        
        # Remove dangerous characters
        filename = re.sub(r'[^\w\s.-]', '', filename)
        
        # Limit length
        name, ext = os.path.splitext(filename)
        if len(name) > 100:
            name = name[:100]
        
        return name + ext


class CSRFProtection:
    """CSRF token generation and validation."""
    
    @staticmethod
    def generate_token() -> str:
        """Generate a new CSRF token."""
        token = secrets.token_urlsafe(SecurityConfig.CSRF_TOKEN_LENGTH)
        session['csrf_token'] = token
        session['csrf_token_time'] = datetime.now().isoformat()
        return token
    
    @staticmethod
    def validate_token(token: str) -> bool:
        """Validate a CSRF token."""
        if not token:
            return False
        
        stored_token = session.get('csrf_token')
        if not stored_token:
            return False
        
        # Check token matches
        if not hmac.compare_digest(token, stored_token):
            return False
        
        # Check token age (max 1 hour)
        token_time = session.get('csrf_token_time')
        if token_time:
            token_dt = datetime.fromisoformat(token_time)
            if datetime.now() - token_dt > timedelta(hours=1):
                return False
        
        return True
    
    @staticmethod
    def get_token_from_request() -> Optional[str]:
        """Extract CSRF token from request."""
        # Check header first
        token = request.headers.get(SecurityConfig.CSRF_HEADER_NAME)
        if token:
            return token
        
        # Check form data
        if request.form:
            token = request.form.get(SecurityConfig.CSRF_FORM_FIELD)
            if token:
                return token
        
        # Check JSON data
        if request.is_json:
            data = request.get_json()
            if data:
                token = data.get(SecurityConfig.CSRF_FORM_FIELD)
                if token:
                    return token
        
        return None


def require_csrf(f):
    """Decorator to require CSRF token for state-changing operations."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip CSRF check for GET and HEAD requests
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return f(*args, **kwargs)
        
        token = CSRFProtection.get_token_from_request()
        if not CSRFProtection.validate_token(token):
            abort(403, description="Invalid or missing CSRF token")
        
        return f(*args, **kwargs)
    
    return decorated_function


class SessionManager:
    """Secure session management."""
    
    @staticmethod
    def create_session(user_id: str, extra_data: Dict = None) -> str:
        """Create a new secure session."""
        session.clear()
        session['user_id'] = user_id
        session['created_at'] = datetime.now().isoformat()
        session['last_activity'] = datetime.now().isoformat()
        session['session_id'] = secrets.token_urlsafe(32)
        
        if extra_data:
            for key, value in extra_data.items():
                session[key] = value
        
        # Generate CSRF token for the session
        CSRFProtection.generate_token()
        
        return session['session_id']
    
    @staticmethod
    def validate_session() -> bool:
        """Validate current session."""
        if 'user_id' not in session:
            return False
        
        # Check session age
        created_at = session.get('created_at')
        if not created_at:
            return False
        
        created_dt = datetime.fromisoformat(created_at)
        if datetime.now() - created_dt > timedelta(hours=24):
            return False
        
        # Check last activity
        last_activity = session.get('last_activity')
        if last_activity:
            last_dt = datetime.fromisoformat(last_activity)
            if datetime.now() - last_dt > timedelta(minutes=SecurityConfig.SESSION_LIFETIME_MINUTES):
                return False
        
        # Update last activity
        session['last_activity'] = datetime.now().isoformat()
        
        return True
    
    @staticmethod
    def destroy_session():
        """Securely destroy the current session."""
        session.clear()
    
    @staticmethod
    def regenerate_session_id():
        """Regenerate session ID to prevent fixation attacks."""
        if 'user_id' in session:
            session['session_id'] = secrets.token_urlsafe(32)
            session['regenerated_at'] = datetime.now().isoformat()


def require_session(f):
    """Decorator to require valid session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not SessionManager.validate_session():
            abort(401, description="Invalid or expired session")
        return f(*args, **kwargs)
    
    return decorated_function


class RateLimiter:
    """Simple rate limiting implementation."""
    
    # In-memory storage (in production, use Redis or similar)
    _attempts = {}
    
    @staticmethod
    def check_rate_limit(identifier: str, max_attempts: int = 60, 
                         window_minutes: int = 1) -> bool:
        """
        Check if rate limit is exceeded.
        
        Args:
            identifier: Unique identifier (e.g., IP address, user ID)
            max_attempts: Maximum attempts allowed
            window_minutes: Time window in minutes
            
        Returns:
            True if within limit, False if exceeded
        """
        now = datetime.now()
        window_start = now - timedelta(minutes=window_minutes)
        
        # Clean old entries
        if identifier in RateLimiter._attempts:
            RateLimiter._attempts[identifier] = [
                t for t in RateLimiter._attempts[identifier]
                if t > window_start
            ]
        
        # Check current attempts
        current_attempts = len(RateLimiter._attempts.get(identifier, []))
        if current_attempts >= max_attempts:
            return False
        
        # Record this attempt
        if identifier not in RateLimiter._attempts:
            RateLimiter._attempts[identifier] = []
        RateLimiter._attempts[identifier].append(now)
        
        return True
    
    @staticmethod
    def reset_limit(identifier: str):
        """Reset rate limit for an identifier."""
        if identifier in RateLimiter._attempts:
            del RateLimiter._attempts[identifier]


def rate_limit(max_attempts: int = 60, window_minutes: int = 1):
    """Decorator to apply rate limiting."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            identifier = request.remote_addr
            if not RateLimiter.check_rate_limit(identifier, max_attempts, window_minutes):
                abort(429, description="Rate limit exceeded")
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Environment variable management
def get_env_var(name: str, default: str = None, required: bool = False) -> Optional[str]:
    """
    Safely get environment variable.
    
    Args:
        name: Environment variable name
        default: Default value if not found
        required: Whether the variable is required
        
    Returns:
        Environment variable value
        
    Raises:
        RuntimeError: If required variable is missing
    """
    value = os.getenv(name, default)
    
    if required and not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    
    return value


# Export all security utilities
__all__ = [
    'SecurityConfig',
    'SQLQueryBuilder',
    'SecureDatabase',
    'InputValidator',
    'CSRFProtection',
    'SessionManager',
    'RateLimiter',
    'require_csrf',
    'require_session',
    'rate_limit',
    'get_env_var'
]