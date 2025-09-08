# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Travel Expense Analyzer application that processes Chase bank transactions to identify and categorize business travel expenses for Concur reporting. The system features a Flask web application with a "Friday Panic Button" for automated expense processing.

## Key Commands

### Running the Application
```bash
# Start the Flask web app
python expense_web_app.py

# Enhanced OAuth version with Gmail and Per Diem
python oauth_enhanced.py

# Alternative start methods
python start_app.py
python simple_app.py  # Minimal version
python oauth_app.py  # OAuth dashboard
```

### Testing
```bash
# Run integration tests
python -m pytest tests/test_integration.py -v

# Run specific test classes
python -m pytest tests/test_integration.py::FridayPanicButtonTest -v

# Run all test files
python test_improvements.py
python test_end_to_end_workflow.py
python test_plaid_integration.py
```

### Development Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your credentials

# Initialize database
python -c "from database_pool import get_db; get_db()"
```

## Architecture

### Core Components

1. **expense_web_app.py**: Main Flask application with API endpoints and rate limiting
   - Uses Flask-Limiter for rate control
   - Implements standardized API responses via APIResponse class
   - Handles file uploads, expense processing, and dashboard rendering

2. **friday_panic_button.py**: Automated expense categorization engine
   - FridayPanicButton class with intelligent categorization rules
   - Confidence scoring system for expense classification
   - Batch processing capabilities for bulk operations

3. **database_pool.py**: Database connection pooling implementation
   - Manages 5 persistent + 10 overflow SQLite connections
   - Automatic transaction management with commit/rollback

4. **config.py**: Centralized configuration management
   - Environment-based configs (DevelopmentConfig, ProductionConfig, TestingConfig)
   - Validates settings on startup
   - All hardcoded values extracted here

### Service Layer (services.py)
- **ExpenseProcessingService**: Business logic for expense handling
- **TaskService**: Background task management
- **BusinessPurposeService**: Purpose validation and generation

### Data Validation (validators.py)
- Pydantic models for request validation
- FridayPanicRequest, BulkProcessRequest, BusinessPurposeInput models

### External Integrations
- **plaid_integration.py**: Plaid API for bank account sync
- **concur_api_client.py**: SAP Concur API integration
- **hotel_folio_retriever.py**: Automated hotel receipt retrieval
- **oauth_enhanced.py**: Enhanced OAuth with Gmail integration
- **per_diem_tracker.py**: Per diem expense tracking and analysis

## Key Configuration

Environment variables (set in .env):
- `DATABASE_PATH`: SQLite database location (default: data/expenses.db)
- `FLASK_ENV`: development/production/testing
- `RATE_LIMIT_ENABLED`: Enable/disable rate limiting
- `DEFAULT_START_DATE`: Default date for expense processing (2024-01-01)
- `BATCH_SIZE`: Transaction batch size (default: 100)
- `CONFIDENCE_THRESHOLD`: Categorization confidence threshold (0.7)
- `DAILY_FOOD_ALLOWANCE`: Per diem daily allowance (default: 75.00)
- `GOOGLE_CLIENT_ID`: Google OAuth client ID for Gmail integration
- `GOOGLE_CLIENT_SECRET`: Google OAuth client secret

## Database Structure

SQLite database at `data/expenses.db` with connection pooling. Tables include:
- Transactions table with expense records
- Categories and trip groupings
- Business purpose mappings
- Background task tracking

## API Endpoints

Key routes in expense_web_app.py:
- `/api/friday-panic`: Automated expense processing
- `/api/bulk-process`: Background bulk processing
- `/api/expenses`: CRUD operations for expenses
- `/api/business-purpose`: Purpose management
- `/dashboard`: Main UI interface

OAuth and Per Diem routes (oauth_enhanced.py):
- `/auth/google/authorize`: Initiate Gmail OAuth
- `/auth/plaid/link-token`: Create Plaid Link token
- `/auth/concur/authorize`: Initiate Concur OAuth
- `/api/gmail/trips`: Fetch Concur trip emails from Gmail
- `/api/per-diem/analyze`: Analyze expenses vs per diem allowances
- `/api/per-diem/config`: Get/set per diem configuration

## Error Handling

The application implements comprehensive error handling:
- Specific exception catching (no bare except clauses)
- Transaction rollback on database failures
- Structured logging with context
- Standardized API error responses with timestamps

## Security Features

- Input validation with Pydantic models
- HTML/script tag sanitization
- Rate limiting on all API endpoints
- SQL injection prevention via parameterized queries
- Session security with HTTPOnly cookies
- OAuth 2.0 authentication for external services
- Secure token storage and refresh
- Read-only Gmail access (no write permissions)

## Testing Approach

Tests use unittest framework (not pytest). Key test files:
- `tests/test_integration.py`: End-to-end workflow tests
- `test_improvements.py`: Validation of recent improvements
- `test_end_to_end_workflow.py`: User journey testing

Run individual test classes with:
```bash
python -m pytest tests/test_integration.py::ClassName -v
```