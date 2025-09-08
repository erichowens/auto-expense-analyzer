#!/usr/bin/env python3
"""
Standardized API response formats for consistency across all endpoints.
"""

from flask import jsonify
from typing import Any, Optional, Dict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class APIResponse:
    """Standardized API response builder."""
    
    @staticmethod
    def success(data: Any = None, message: str = None, status_code: int = 200):
        """
        Create a successful response.
        
        Args:
            data: The response data
            message: Optional success message
            status_code: HTTP status code (default 200)
        
        Returns:
            Flask JSON response
        """
        response = {
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
        }
        
        if data is not None:
            response['data'] = data
        
        if message:
            response['message'] = message
        
        return jsonify(response), status_code
    
    @staticmethod
    def error(message: str, status_code: int = 400, error_code: str = None, details: Any = None):
        """
        Create an error response.
        
        Args:
            message: Error message
            status_code: HTTP status code (default 400)
            error_code: Optional application-specific error code
            details: Optional additional error details
        
        Returns:
            Flask JSON response
        """
        response = {
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'message': message
        }
        
        if error_code:
            response['error_code'] = error_code
        
        if details:
            response['details'] = details
        
        # Log the error
        logger.error(f"API Error: {message} (code: {error_code}, status: {status_code})")
        
        return jsonify(response), status_code
    
    @staticmethod
    def validation_error(errors: Dict[str, str], message: str = "Validation failed"):
        """
        Create a validation error response.
        
        Args:
            errors: Dictionary of field errors
            message: Main error message
        
        Returns:
            Flask JSON response
        """
        return APIResponse.error(
            message=message,
            status_code=422,
            error_code='VALIDATION_ERROR',
            details={'validation_errors': errors}
        )
    
    @staticmethod
    def not_found(resource: str = "Resource", identifier: Any = None):
        """
        Create a not found response.
        
        Args:
            resource: Type of resource not found
            identifier: Resource identifier
        
        Returns:
            Flask JSON response
        """
        message = f"{resource} not found"
        if identifier:
            message += f" (id: {identifier})"
        
        return APIResponse.error(
            message=message,
            status_code=404,
            error_code='NOT_FOUND'
        )
    
    @staticmethod
    def unauthorized(message: str = "Unauthorized access"):
        """
        Create an unauthorized response.
        
        Returns:
            Flask JSON response
        """
        return APIResponse.error(
            message=message,
            status_code=401,
            error_code='UNAUTHORIZED'
        )
    
    @staticmethod
    def forbidden(message: str = "Access forbidden"):
        """
        Create a forbidden response.
        
        Returns:
            Flask JSON response
        """
        return APIResponse.error(
            message=message,
            status_code=403,
            error_code='FORBIDDEN'
        )
    
    @staticmethod
    def rate_limited(retry_after: int = None):
        """
        Create a rate limited response.
        
        Args:
            retry_after: Seconds until the client can retry
        
        Returns:
            Flask JSON response
        """
        response = APIResponse.error(
            message="Rate limit exceeded",
            status_code=429,
            error_code='RATE_LIMITED'
        )
        
        if retry_after:
            response[0].headers['Retry-After'] = str(retry_after)
        
        return response
    
    @staticmethod
    def server_error(message: str = "Internal server error", request_id: str = None):
        """
        Create a server error response.
        
        Args:
            message: Error message
            request_id: Optional request ID for tracking
        
        Returns:
            Flask JSON response
        """
        details = {}
        if request_id:
            details['request_id'] = request_id
        
        return APIResponse.error(
            message=message,
            status_code=500,
            error_code='SERVER_ERROR',
            details=details if details else None
        )
    
    @staticmethod
    def accepted(task_id: str, message: str = "Request accepted for processing", status_url: str = None):
        """
        Create an accepted response for async operations.
        
        Args:
            task_id: Task identifier
            message: Status message
            status_url: URL to check task status
        
        Returns:
            Flask JSON response
        """
        data = {
            'task_id': task_id,
            'status': 'processing'
        }
        
        if status_url:
            data['status_url'] = status_url
        
        return APIResponse.success(
            data=data,
            message=message,
            status_code=202
        )
    
    @staticmethod
    def paginated(items: list, page: int, per_page: int, total: int):
        """
        Create a paginated response.
        
        Args:
            items: List of items for current page
            page: Current page number
            per_page: Items per page
            total: Total number of items
        
        Returns:
            Flask JSON response
        """
        total_pages = (total + per_page - 1) // per_page
        
        data = {
            'items': items,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'total_pages': total_pages,
                'has_prev': page > 1,
                'has_next': page < total_pages
            }
        }
        
        return APIResponse.success(data=data)

# Error handler decorator
def handle_api_errors(f):
    """
    Decorator to handle API errors consistently.
    
    Usage:
        @app.route('/api/endpoint')
        @handle_api_errors
        def endpoint():
            # Your code here
    """
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            return APIResponse.error(str(e), status_code=400)
        except KeyError as e:
            return APIResponse.error(f"Missing required field: {e}", status_code=400)
        except PermissionError as e:
            return APIResponse.forbidden(str(e))
        except FileNotFoundError as e:
            return APIResponse.not_found("File", str(e))
        except Exception as e:
            logger.exception("Unhandled API error")
            return APIResponse.server_error(
                message="An unexpected error occurred",
                request_id=str(id(e))  # Simple request tracking
            )
    
    wrapper.__name__ = f.__name__
    return wrapper