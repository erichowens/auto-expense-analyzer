#!/usr/bin/env python3
"""
Application configuration management.
"""

import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    """Application configuration."""
    
    # Database settings
    DATABASE_PATH: str = os.getenv('DATABASE_PATH', 'data/expenses.db')
    DATABASE_POOL_SIZE: int = int(os.getenv('DATABASE_POOL_SIZE', '5'))
    DATABASE_MAX_OVERFLOW: int = int(os.getenv('DATABASE_MAX_OVERFLOW', '10'))
    DATABASE_TIMEOUT: int = int(os.getenv('DATABASE_TIMEOUT', '30'))
    
    # Friday Panic Button settings
    DEFAULT_START_DATE: str = os.getenv('DEFAULT_START_DATE', '2024-01-01')
    BATCH_SIZE: int = int(os.getenv('BATCH_SIZE', '100'))
    CONFIDENCE_THRESHOLD: float = float(os.getenv('CONFIDENCE_THRESHOLD', '0.7'))
    MAX_GAP_DAYS: int = int(os.getenv('MAX_GAP_DAYS', '7'))
    MAX_TRANSACTIONS_PER_REQUEST: int = int(os.getenv('MAX_TRANSACTIONS_PER_REQUEST', '10000'))
    
    # Rate limiting settings
    RATE_LIMIT_ENABLED: bool = os.getenv('RATE_LIMIT_ENABLED', 'true').lower() == 'true'
    RATE_LIMIT_DEFAULT: str = os.getenv('RATE_LIMIT_DEFAULT', '200 per day, 50 per hour')
    RATE_LIMIT_PANIC_BUTTON: str = os.getenv('RATE_LIMIT_PANIC_BUTTON', '10 per hour')
    RATE_LIMIT_BULK: str = os.getenv('RATE_LIMIT_BULK', '5 per hour')
    RATE_LIMIT_STORAGE_URL: str = os.getenv('RATE_LIMIT_STORAGE_URL', 'memory://')
    
    # Security settings
    SECRET_KEY: str = os.getenv('SECRET_KEY', os.urandom(24).hex())
    SESSION_COOKIE_SECURE: bool = os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = 'Lax'
    MAX_CONTENT_LENGTH: int = int(os.getenv('MAX_CONTENT_LENGTH', str(16 * 1024 * 1024)))  # 16MB
    
    # Logging settings
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_FILE: Optional[str] = os.getenv('LOG_FILE', None)
    
    # API settings
    API_VERSION: str = 'v1'
    API_PREFIX: str = '/api'
    PAGINATION_DEFAULT: int = int(os.getenv('PAGINATION_DEFAULT', '20'))
    PAGINATION_MAX: int = int(os.getenv('PAGINATION_MAX', '100'))
    
    # Task processing settings
    TASK_TIMEOUT: int = int(os.getenv('TASK_TIMEOUT', '300'))  # 5 minutes
    TASK_CLEANUP_INTERVAL: int = int(os.getenv('TASK_CLEANUP_INTERVAL', '3600'))  # 1 hour
    TASK_MAX_AGE: int = int(os.getenv('TASK_MAX_AGE', '86400'))  # 24 hours
    
    # File upload settings
    UPLOAD_FOLDER: str = os.getenv('UPLOAD_FOLDER', 'uploads')
    ALLOWED_EXTENSIONS: set = None  # Will be set in __post_init__
    
    # External service settings
    PLAID_CLIENT_ID: str = os.getenv('PLAID_CLIENT_ID', '')
    PLAID_SECRET: str = os.getenv('PLAID_SECRET', '')
    PLAID_ENV: str = os.getenv('PLAID_ENV', 'sandbox')
    
    CONCUR_CLIENT_ID: str = os.getenv('CONCUR_CLIENT_ID', '')
    CONCUR_CLIENT_SECRET: str = os.getenv('CONCUR_CLIENT_SECRET', '')
    CONCUR_API_URL: str = os.getenv('CONCUR_API_URL', 'https://api.concursolutions.com')
    
    def __post_init__(self):
        """Initialize mutable defaults after instance creation."""
        if self.ALLOWED_EXTENSIONS is None:
            self.ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif'}
    
    @classmethod
    def from_env(cls):
        """Create config from environment variables."""
        instance = cls()
        return instance
    
    def validate(self):
        """Validate configuration settings."""
        errors = []
        
        # Check required paths exist
        if not os.path.exists(os.path.dirname(self.DATABASE_PATH) or '.'):
            errors.append(f"Database directory does not exist: {os.path.dirname(self.DATABASE_PATH)}")
        
        if not os.path.exists(self.UPLOAD_FOLDER):
            try:
                os.makedirs(self.UPLOAD_FOLDER, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create upload folder: {e}")
        
        # Validate numeric ranges
        if self.BATCH_SIZE < 1 or self.BATCH_SIZE > 10000:
            errors.append(f"BATCH_SIZE must be between 1 and 10000, got {self.BATCH_SIZE}")
        
        if self.CONFIDENCE_THRESHOLD < 0 or self.CONFIDENCE_THRESHOLD > 1:
            errors.append(f"CONFIDENCE_THRESHOLD must be between 0 and 1, got {self.CONFIDENCE_THRESHOLD}")
        
        if self.DATABASE_POOL_SIZE < 1:
            errors.append(f"DATABASE_POOL_SIZE must be at least 1, got {self.DATABASE_POOL_SIZE}")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")
        
        return True

# Create a global config instance
config = Config.from_env()

# Development config override
class DevelopmentConfig(Config):
    """Development-specific configuration."""
    LOG_LEVEL: str = 'DEBUG'
    RATE_LIMIT_ENABLED: bool = False
    SESSION_COOKIE_SECURE: bool = False

# Production config override
class ProductionConfig(Config):
    """Production-specific configuration."""
    LOG_LEVEL: str = 'WARNING'
    RATE_LIMIT_ENABLED: bool = True
    SESSION_COOKIE_SECURE: bool = True
    
    def __init__(self):
        super().__init__()
        # Require certain settings in production
        if not self.SECRET_KEY or self.SECRET_KEY == os.urandom(24).hex():
            raise ValueError("SECRET_KEY must be explicitly set in production")

# Testing config override
class TestingConfig(Config):
    """Testing-specific configuration."""
    DATABASE_PATH: str = ':memory:'
    RATE_LIMIT_ENABLED: bool = False
    LOG_LEVEL: str = 'ERROR'
    TASK_TIMEOUT: int = 5

def get_config(env: str = None) -> Config:
    """
    Get configuration based on environment.
    
    Args:
        env: Environment name (development, production, testing)
    
    Returns:
        Config instance
    """
    if env is None:
        env = os.getenv('FLASK_ENV', 'development')
    
    configs = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
        'testing': TestingConfig
    }
    
    config_class = configs.get(env, Config)
    return config_class()