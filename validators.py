#!/usr/bin/env python3
"""
Input validation models using Pydantic for type safety and data validation.
"""

from pydantic import BaseModel, Field, validator, ValidationError
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
import re
import logging

logger = logging.getLogger(__name__)

class TransactionInput(BaseModel):
    """Validates individual transaction input."""
    date: str
    description: str
    amount: float = Field(gt=0, le=1000000)
    location: Optional[str] = None
    category: Optional[str] = None
    
    @validator('date')
    def validate_date(cls, v):
        """Ensure date is in correct format."""
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f"Date must be in YYYY-MM-DD format, got: {v}")
        return v
    
    @validator('description')
    def validate_description(cls, v):
        """Ensure description is not empty and sanitized."""
        if not v or not v.strip():
            raise ValueError("Description cannot be empty")
        # Remove any potential HTML/script tags
        cleaned = re.sub(r'<[^>]+>', '', v)
        return cleaned[:500]  # Limit length
    
    @validator('location')
    def validate_location(cls, v):
        """Sanitize location field."""
        if v:
            # Remove any potential HTML/script tags
            cleaned = re.sub(r'<[^>]+>', '', v)
            return cleaned[:200]
        return v

class BulkProcessRequest(BaseModel):
    """Validates bulk processing request."""
    start_date: str
    end_date: Optional[str] = None
    batch_size: int = Field(default=100, ge=1, le=1000)
    
    @validator('start_date')
    def validate_start_date(cls, v):
        """Ensure start date is valid and not too far in the past."""
        try:
            start = datetime.strptime(v, '%Y-%m-%d')
            # Don't allow dates before 2020
            if start.year < 2020:
                raise ValueError("Start date cannot be before 2020")
            # Don't allow future dates
            if start > datetime.now():
                raise ValueError("Start date cannot be in the future")
        except ValueError as e:
            if "time data" in str(e):
                raise ValueError(f"Start date must be in YYYY-MM-DD format, got: {v}")
            raise
        return v
    
    @validator('end_date')
    def validate_end_date(cls, v, values):
        """Ensure end date is valid and after start date."""
        if v:
            try:
                end = datetime.strptime(v, '%Y-%m-%d')
                if 'start_date' in values:
                    start = datetime.strptime(values['start_date'], '%Y-%m-%d')
                    if end < start:
                        raise ValueError("End date must be after start date")
                # Don't allow future dates
                if end > datetime.now():
                    raise ValueError("End date cannot be in the future")
            except ValueError as e:
                if "time data" in str(e):
                    raise ValueError(f"End date must be in YYYY-MM-DD format, got: {v}")
                raise
        return v

class FridayPanicRequest(BaseModel):
    """Validates Friday Panic button request."""
    trip_id: Optional[int] = Field(None, ge=1)
    transactions: Optional[List[Dict[str, Any]]] = None
    auto_save: bool = Field(default=False)
    
    @validator('transactions')
    def validate_transactions(cls, v):
        """Validate transaction list if provided."""
        if v is not None:
            if not isinstance(v, list):
                raise ValueError("Transactions must be a list")
            if len(v) > 10000:
                raise ValueError("Cannot process more than 10000 transactions at once")
            
            # Validate each transaction
            validated = []
            for i, trans in enumerate(v):
                try:
                    validated_trans = TransactionInput(**trans)
                    validated.append(validated_trans.dict())
                except ValidationError as e:
                    logger.warning(f"Invalid transaction at index {i}: {e}")
                    # Skip invalid transactions but log them
                    continue
            
            if not validated:
                raise ValueError("No valid transactions found")
            
            return validated
        return v

class BusinessPurposeInput(BaseModel):
    """Validates business purpose input."""
    purpose: str = Field(min_length=10, max_length=500)
    trip_id: Optional[int] = Field(None, ge=1)
    apply_to_all: bool = Field(default=False)
    
    @validator('purpose')
    def validate_purpose(cls, v):
        """Ensure business purpose is meaningful and sanitized."""
        # Remove any potential HTML/script tags
        cleaned = re.sub(r'<[^>]+>', '', v)
        
        # Check for minimum meaningful content
        words = cleaned.split()
        if len(words) < 3:
            raise ValueError("Business purpose must contain at least 3 words")
        
        # Check for suspicious patterns
        suspicious_patterns = [
            r'<script',
            r'javascript:',
            r'onclick',
            r'onerror',
            r'SELECT.*FROM',
            r'DROP\s+TABLE',
            r'INSERT\s+INTO'
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Business purpose contains invalid content")
        
        return cleaned

class TaskStatusRequest(BaseModel):
    """Validates task status request."""
    task_id: str = Field(min_length=36, max_length=36)  # UUID format
    
    @validator('task_id')
    def validate_task_id(cls, v):
        """Ensure task ID is a valid UUID."""
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        if not re.match(uuid_pattern, v.lower()):
            raise ValueError("Invalid task ID format")
        return v

def validate_request_data(data: dict, model_class: BaseModel) -> tuple[bool, Any, Optional[str]]:
    """
    Generic validation function for request data.
    
    Returns:
        tuple: (is_valid, validated_data, error_message)
    """
    try:
        validated = model_class(**data)
        return True, validated, None
    except ValidationError as e:
        error_messages = []
        for error in e.errors():
            field = '.'.join(str(x) for x in error['loc'])
            message = error['msg']
            error_messages.append(f"{field}: {message}")
        
        error_message = "; ".join(error_messages)
        logger.warning(f"Validation failed: {error_message}")
        return False, None, error_message
    except Exception as e:
        logger.error(f"Unexpected validation error: {e}")
        return False, None, str(e)

# Export validation decorators for Flask routes
def validate_json(model_class: BaseModel):
    """Decorator to validate JSON request data."""
    def decorator(f):
        def wrapper(*args, **kwargs):
            from flask import request, jsonify
            
            if not request.is_json:
                return jsonify({'error': 'Content-Type must be application/json'}), 400
            
            is_valid, validated_data, error = validate_request_data(
                request.get_json() or {}, 
                model_class
            )
            
            if not is_valid:
                return jsonify({'error': f'Validation failed: {error}'}), 400
            
            # Inject validated data into the function
            request.validated_data = validated_data
            return f(*args, **kwargs)
        
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator