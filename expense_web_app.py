#!/usr/bin/env python3
"""
Expense Tracker Web Application
A Flask web app for reviewing, editing, and submitting travel expenses to Concur.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import os
import json
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
import uuid
import threading
import logging
from typing import Dict, List, Optional, Any

# Import new modules
from config import get_config
from api_response import APIResponse, handle_api_errors
from validators import (
    FridayPanicRequest, BulkProcessRequest, BusinessPurposeInput,
    validate_json, validate_request_data
)
from services import get_expense_service, get_task_service, get_purpose_service
from database_pool import get_db

# Import our existing modules
try:
    from chase_travel_expense_analyzer import ChaseAnalyzer, Transaction
    from hotel_folio_retriever import HotelFolioRetriever
    from concur_api_client import ConcurAPIClient, convert_trip_to_concur_report
    from database import get_database, init_database
    from friday_panic_button import friday_panic, process_bulk_expenses
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some modules not available: {e}")
    MODULES_AVAILABLE = False

# Load configuration
config = get_config()

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
app.config['SESSION_COOKIE_SECURE'] = config.SESSION_COOKIE_SECURE
app.config['SESSION_COOKIE_HTTPONLY'] = config.SESSION_COOKIE_HTTPONLY
app.config['SESSION_COOKIE_SAMESITE'] = config.SESSION_COOKIE_SAMESITE

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[config.RATE_LIMIT_DEFAULT] if config.RATE_LIMIT_ENABLED else [],
    storage_uri=config.RATE_LIMIT_STORAGE_URL
)

# Ensure required directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('data', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)

# Initialize database with connection pooling
if MODULES_AVAILABLE:
    try:
        db = get_db()
        logger.info("Database initialized with connection pooling")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        db = None
else:
    db = None

# Initialize services
task_service = get_task_service()
expense_service = get_expense_service()
purpose_service = get_purpose_service()

# Global state for the application (now backed by database)
app_state = {
    'processing_status': 'idle',
    'current_session_id': None
}

# Allowed file extensions for uploads
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Background task management
background_tasks = {}

class BackgroundTask:
    def __init__(self, task_id: str, description: str):
        self.task_id = task_id
        self.description = description
        self.status = 'running'
        self.progress = 0
        self.result = None
        self.error = None
        self.started_at = datetime.now()

def run_background_task(task_id: str, task_func, *args, **kwargs):
    """Run a function in the background and track its progress."""
    task = background_tasks.get(task_id)
    if not task:
        return
    
    try:
        result = task_func(*args, **kwargs)
        task.status = 'completed'
        task.progress = 100
        task.result = result
    except Exception as e:
        task.status = 'error'
        task.error = str(e)

@app.route('/')
def index():
    """Main dashboard page."""
    if not db:
        return render_template('dashboard.html', trips=[], last_analysis=None, processing_status='error')
    
    try:
        trips = db.get_trips(limit=10)  # Get recent trips
        stats = db.get_dashboard_stats()
        
        return render_template('dashboard.html', 
                             trips=trips,
                             last_analysis=stats.get('last_analysis'),
                             processing_status=app_state['processing_status'],
                             stats=stats)
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}")
        return render_template('dashboard.html', trips=[], last_analysis=None, processing_status='error')

@app.route('/setup')
def setup():
    """Configuration and setup page."""
    return render_template('setup.html')

@app.route('/api/analyze-transactions', methods=['POST'])
def analyze_transactions():
    """Analyze transactions from Plaid or CSV files."""
    if not MODULES_AVAILABLE:
        return jsonify({'error': 'Required modules not available'}), 500
    
    task_id = str(uuid.uuid4())
    task = BackgroundTask(task_id, "Analyzing transactions and identifying trips")
    background_tasks[task_id] = task
    
    def analyze():
        analyzer = ChaseAnalyzer()
        
        # Get configuration from request
        config = request.get_json()
        use_plaid = config.get('use_plaid', False)
        years = config.get('years', 2)
        
        task.progress = 10
        
        if use_plaid:
            # Use Plaid API
            if not db:
                raise Exception("Database not available for Plaid token storage")
            
            access_token = db.get_setting('plaid_access_token')
            if not access_token:
                raise Exception("No Plaid access token found. Please connect your bank first.")
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365 * years)
            
            task.progress = 30
            transactions = analyzer.get_transactions_from_plaid(access_token, start_date, end_date)
        else:
            # Use uploaded CSV files
            csv_files = config.get('csv_files', [])
            transactions = []
            
            for file_path in csv_files:
                file_transactions = analyzer.parse_chase_csv(file_path)
                transactions.extend(file_transactions)
            
            transactions = analyzer.filter_by_date_range(transactions, years)
        
        task.progress = 60
        
        # Group into trips
        trips = analyzer.group_trips(transactions)
        trip_summaries = analyzer.summarize_trips(trips)
        
        task.progress = 80
        
        # Store results
        app_state['transactions'] = transactions
        app_state['trips'] = trip_summaries
        app_state['last_analysis'] = datetime.now().isoformat()
        app_state['processing_status'] = 'completed'
        
        task.progress = 100
        
        return {
            'transaction_count': len(transactions),
            'trip_count': len(trips),
            'total_amount': sum(t.amount for t in transactions)
        }
    
    # Start background task
    thread = threading.Thread(target=run_background_task, args=(task_id, analyze))
    thread.start()
    
    return jsonify({'task_id': task_id})

@app.route('/api/task-status/<task_id>')
def task_status(task_id):
    """Get status of a background task."""
    task = background_tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    return jsonify({
        'task_id': task_id,
        'description': task.description,
        'status': task.status,
        'progress': task.progress,
        'result': task.result,
        'error': task.error,
        'started_at': task.started_at.isoformat()
    })

@app.route('/trips')
def trips():
    """Trip review and editing page."""
    if not db:
        return render_template('trips.html', trips=[])
    
    try:
        trips_data = db.get_trips()
        return render_template('trips.html', trips=trips_data)
    except Exception as e:
        logger.error(f"Error loading trips: {e}")
        return render_template('trips.html', trips=[])

@app.route('/api/trips/<int:trip_id>')
def get_trip(trip_id):
    """Get details for a specific trip."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        trip = db.get_trip_by_id(trip_id)
        if not trip:
            return jsonify({'error': 'Trip not found'}), 404
        return jsonify(trip)
    except Exception as e:
        logger.error(f"Error getting trip {trip_id}: {e}")
        return jsonify({'error': 'Failed to get trip'}), 500

@app.route('/api/trips/<int:trip_id>', methods=['PUT'])
def update_trip(trip_id):
    """Update trip details."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        updates = request.get_json()
        if not updates:
            return jsonify({'error': 'No update data provided'}), 400
        
        # Check if trip exists
        trip = db.get_trip_by_id(trip_id)
        if not trip:
            return jsonify({'error': 'Trip not found'}), 404
        
        # Update allowed fields
        allowed_fields = ['business_purpose', 'primary_location', 'start_date', 'end_date']
        update_data = {field: updates[field] for field in allowed_fields if field in updates}
        
        if not update_data:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        # Update trip in database
        db.update_trip(trip_id, update_data)
        
        # Return updated trip
        updated_trip = db.get_trip_by_id(trip_id)
        return jsonify(updated_trip)
    except Exception as e:
        logger.error(f"Error updating trip {trip_id}: {e}")
        return jsonify({'error': 'Failed to update trip'}), 500

@app.route('/api/transactions/<int:trip_id>/<int:transaction_id>', methods=['PUT'])
def update_transaction(trip_id, transaction_id):
    """Update individual transaction details."""
    if trip_id < 1 or trip_id > len(app_state['trips']):
        return jsonify({'error': 'Trip not found'}), 404
    
    trip = app_state['trips'][trip_id - 1]
    transactions = trip.get('transactions', [])
    
    if transaction_id < 0 or transaction_id >= len(transactions):
        return jsonify({'error': 'Transaction not found'}), 404
    
    updates = request.get_json()
    transaction = transactions[transaction_id]
    
    # Update allowed fields
    allowed_fields = ['category', 'business_purpose', 'vendor_name', 'amount']
    for field in allowed_fields:
        if field in updates:
            setattr(transaction, field, updates[field])
    
    # Recalculate trip totals
    trip['total_amount'] = sum(t.amount for t in transactions)
    category_totals = {}
    for t in transactions:
        category_totals[t.category] = category_totals.get(t.category, 0) + t.amount
    trip['category_breakdown'] = category_totals
    
    return jsonify({'status': 'updated'})

@app.route('/receipts')
def receipts():
    """Receipt and folio management page."""
    if not db:
        return render_template('receipts.html', trips=[])
    
    try:
        trips_data = db.get_trips()
        return render_template('receipts.html', trips=trips_data)
    except Exception as e:
        logger.error(f"Error loading trips for receipts: {e}")
        return render_template('receipts.html', trips=[])

@app.route('/api/upload-receipt', methods=['POST'])
def upload_receipt():
    """Upload a receipt image."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file:
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        return jsonify({
            'filename': filename,
            'path': file_path,
            'size': os.path.getsize(file_path)
        })

@app.route('/api/retrieve-folios', methods=['POST'])
def retrieve_folios():
    """Retrieve hotel folios automatically."""
    if not MODULES_AVAILABLE:
        return jsonify({'error': 'Required modules not available'}), 500
    
    task_id = str(uuid.uuid4())
    task = BackgroundTask(task_id, "Retrieving hotel folios")
    background_tasks[task_id] = task
    
    def retrieve():
        config = request.get_json()
        retriever = HotelFolioRetriever()
        
        hotel_stays = []
        task.progress = 25
        
        # Search email if configured
        if config.get('search_email') and config.get('email_config'):
            email_stays = retriever.search_email_for_hotel_confirmations(config['email_config'])
            hotel_stays.extend(email_stays)
        
        task.progress = 50
        
        # Download folios if configured
        if config.get('download_folios') and config.get('hotel_credentials'):
            for stay in hotel_stays:
                if stay.chain:
                    folio_path = retriever.retrieve_folio_from_website(stay, config['hotel_credentials'])
                    if folio_path:
                        stay.folio_path = folio_path
        
        task.progress = 75
        
        app_state['hotel_stays'] = hotel_stays
        task.progress = 100
        
        return {'retrieved_count': len(hotel_stays)}
    
    thread = threading.Thread(target=run_background_task, args=(task_id, retrieve))
    thread.start()
    
    return jsonify({'task_id': task_id})

@app.route('/concur')
def concur():
    """Concur submission page."""
    if not db:
        return render_template('concur.html', trips=[], reports=[])
    
    try:
        trips_data = db.get_trips()
        # Get concur reports if they exist
        reports = []  # TODO: Implement get_concur_reports() in database
        return render_template('concur.html', trips=trips_data, reports=reports)
    except Exception as e:
        logger.error(f"Error loading data for concur: {e}")
        return render_template('concur.html', trips=[], reports=[])

@app.route('/api/create-concur-reports', methods=['POST'])
def create_concur_reports():
    """Create expense reports in Concur."""
    if not MODULES_AVAILABLE:
        return jsonify({'error': 'Required modules not available'}), 500
    
    task_id = str(uuid.uuid4())
    task = BackgroundTask(task_id, "Creating Concur expense reports")
    background_tasks[task_id] = task
    
    def create_reports():
        config = request.get_json()
        selected_trips = config.get('trip_ids', [])
        
        if not selected_trips:
            selected_trips = list(range(len(app_state['trips'])))
        
        concur_client = ConcurAPIClient()
        created_reports = []
        
        for i, trip_index in enumerate(selected_trips):
            if trip_index < len(app_state['trips']):
                trip = app_state['trips'][trip_index]
                
                try:
                    concur_report = convert_trip_to_concur_report(trip)
                    report_id = concur_client.create_expense_report(concur_report)
                    
                    created_reports.append({
                        'trip_id': trip_index,
                        'report_id': report_id,
                        'trip_location': trip['primary_location'],
                        'amount': trip['total_amount'],
                        'status': 'created'
                    })
                    
                    # Submit if requested
                    if config.get('submit_reports'):
                        success = concur_client.submit_expense_report(report_id)
                        created_reports[-1]['status'] = 'submitted' if success else 'created'
                    
                except Exception as e:
                    created_reports.append({
                        'trip_id': trip_index,
                        'error': str(e),
                        'trip_location': trip['primary_location'],
                        'status': 'error'
                    })
                
                task.progress = int((i + 1) / len(selected_trips) * 100)
        
        app_state['concur_reports'] = created_reports
        return {'created_count': len([r for r in created_reports if r.get('report_id')])}
    
    thread = threading.Thread(target=run_background_task, args=(task_id, create_reports))
    thread.start()
    
    return jsonify({'task_id': task_id})

@app.route('/api/test-concur-connection', methods=['POST'])
def test_concur_connection():
    """Test Concur API connection."""
    if not MODULES_AVAILABLE:
        return jsonify({'error': 'Required modules not available'}), 500
    
    try:
        concur_client = ConcurAPIClient()
        
        if concur_client.authenticate():
            user_profile = concur_client.get_user_profile()
            return jsonify({
                'status': 'success',
                'user': f"{user_profile.get('firstName', '')} {user_profile.get('lastName', '')}",
                'user_id': user_profile.get('id')
            })
        else:
            return jsonify({'status': 'error', 'message': 'Authentication failed'}), 401
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/create-link-token', methods=['POST'])
def create_link_token():
    """Create a Plaid Link token for client-side integration."""
    try:
        from plaid_integration import create_plaid_link_token
        
        data = request.get_json()
        user_id = data.get('user_id', 'default_user')
        
        token_response = create_plaid_link_token(user_id)
        if token_response:
            return jsonify(token_response)
        else:
            return jsonify({'error': 'Failed to create link token. Check Plaid credentials.'}), 500
    
    except ImportError:
        return jsonify({'error': 'Plaid integration not available. Install plaid-python.'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/exchange-public-token', methods=['POST'])
def exchange_public_token():
    """Exchange Plaid public token for access token."""
    try:
        from plaid_integration import exchange_plaid_token
        
        data = request.get_json()
        public_token = data.get('public_token')
        metadata = data.get('metadata', {})
        
        if not public_token:
            return jsonify({'error': 'Missing public_token'}), 400
        
        token_response = exchange_plaid_token(public_token)
        if token_response:
            # Store access token in database for future use
            if db:
                try:
                    db.set_setting('plaid_access_token', token_response['access_token'])
                    db.set_setting('plaid_item_id', token_response['item_id'])
                    db.set_setting('plaid_institution', metadata.get('institution', {}).get('name', 'Unknown'))
                except Exception as e:
                    logger.warning(f"Failed to save Plaid tokens to database: {e}")
            
            return jsonify(token_response)
        else:
            return jsonify({'error': 'Token exchange failed'}), 500
    
    except ImportError:
        return jsonify({'error': 'Plaid integration not available'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-plaid-connection', methods=['POST'])
def test_plaid_connection():
    """Test Plaid API connection using stored access token."""
    try:
        from plaid_integration import get_plaid_manager
        
        if not db:
            return jsonify({'error': 'Database not available'}), 500
        
        access_token = db.get_setting('plaid_access_token')
        if not access_token:
            return jsonify({'error': 'No Plaid access token found. Please connect your bank first.'}), 400
        
        manager = get_plaid_manager()
        if not manager:
            return jsonify({'error': 'Plaid manager not available'}), 500
        
        if manager.validate_access_token(access_token):
            accounts = manager.get_accounts(access_token)
            return jsonify({
                'status': 'success',
                'accounts': len(accounts),
                'institution': db.get_setting('plaid_institution', 'Unknown')
            })
        else:
            return jsonify({'error': 'Access token is invalid or expired'}), 401
    
    except ImportError:
        return jsonify({'error': 'Plaid integration not available'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/business-purpose-suggestions/<int:trip_id>')
def get_business_purpose_suggestions(trip_id):
    """Get smart business purpose suggestions for a trip."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        # Get trip data
        trip = db.get_trip_by_id(trip_id)
        if not trip:
            return jsonify({'error': 'Trip not found'}), 404
        
        # Import business purpose manager
        from business_purpose_templates import suggest_business_purpose
        
        suggestions = suggest_business_purpose(trip)
        return jsonify(suggestions)
    
    except ImportError:
        return jsonify({'error': 'Business purpose system not available'}), 500
    except Exception as e:
        logger.error(f"Error getting business purpose suggestions: {e}")
        return jsonify({'error': 'Failed to get suggestions'}), 500

@app.route('/api/business-purpose-templates')
def get_business_purpose_templates():
    """Get all available business purpose templates."""
    try:
        from business_purpose_templates import get_business_purpose_templates
        templates = get_business_purpose_templates()
        return jsonify({'templates': templates})
    except ImportError:
        return jsonify({'error': 'Business purpose system not available'}), 500

@app.route('/api/validate-business-purpose', methods=['POST'])
def validate_business_purpose_api():
    """Validate a business purpose."""
    try:
        data = request.get_json()
        purpose = data.get('purpose', '')
        
        from business_purpose_templates import validate_business_purpose
        result = validate_business_purpose(purpose)
        return jsonify(result)
    
    except ImportError:
        return jsonify({'error': 'Business purpose system not available'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/trips/<int:trip_id>/set-business-purpose', methods=['POST'])
def set_trip_business_purpose(trip_id):
    """Set business purpose for a trip and optionally apply to all transactions."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        data = request.get_json()
        purpose = data.get('purpose', '').strip()
        apply_to_all = data.get('apply_to_all', True)
        
        if not purpose:
            return jsonify({'error': 'Business purpose is required'}), 400
        
        # Validate business purpose
        from business_purpose_templates import validate_business_purpose
        validation = validate_business_purpose(purpose)
        if not validation['valid']:
            return jsonify({
                'error': validation['message'],
                'suggestions': validation.get('suggestions', [])
            }), 400
        
        # Update trip
        success = db.update_trip(trip_id, {'business_purpose': purpose})
        if not success:
            return jsonify({'error': 'Failed to update trip'}), 500
        
        # Optionally mark all transactions as business expenses
        if apply_to_all:
            # TODO: Implement mark_trip_transactions_as_business
            pass
        
        return jsonify({
            'success': True,
            'message': 'Business purpose set successfully'
        })
    
    except ImportError:
        return jsonify({'error': 'Business purpose system not available'}), 500
    except Exception as e:
        logger.error(f"Error setting business purpose: {e}")
        return jsonify({'error': 'Failed to set business purpose'}), 500

@app.route('/api/friday-panic', methods=['POST'])
@limiter.limit(config.RATE_LIMIT_PANIC_BUTTON)
@handle_api_errors
@validate_json(FridayPanicRequest)
def friday_panic_endpoint():
    """
    The Friday Panic Button - auto-categorize and generate business purposes.
    One click to make everything ready for submission.
    """
    if not expense_service:
        return APIResponse.server_error("Service not available")
    
    # Get validated request data
    panic_request = request.validated_data
    
    # Process transactions
    success, result, error = expense_service.process_transactions(panic_request)
    
    if not success:
        return APIResponse.error(error or "Processing failed", status_code=400)
    
    # Return standardized response
    return APIResponse.success(
        data=result,
        message=f"Processed {len(result.get('transactions', []))} transactions successfully"
    )

@app.route('/api/friday-panic-bulk', methods=['POST'])
@limiter.limit(config.RATE_LIMIT_BULK)
@handle_api_errors
@validate_json(BulkProcessRequest)
def friday_panic_bulk_endpoint():
    """
    Bulk process all expenses since a specific date (e.g., January 2024).
    Handles large volumes of transactions efficiently.
    """
    if not expense_service:
        return APIResponse.server_error("Service not available")
    
    # Get validated request data
    bulk_request = request.validated_data
    
    # Start bulk processing in background
    task_id = expense_service.process_bulk(bulk_request)
    
    # Return accepted response with task ID
    return APIResponse.accepted(
        task_id=task_id,
        message=f"Started bulk processing for expenses since {bulk_request.start_date}",
        status_url=f"/api/task-status/{task_id}"
    )

@app.route('/api/task-status/<task_id>')
@handle_api_errors
def get_task_status(task_id):
    """Get status of a background task."""
    if not task_service:
        return APIResponse.server_error("Service not available")
    
    # Validate task ID format
    import re
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    if not re.match(uuid_pattern, task_id.lower()):
        return APIResponse.error("Invalid task ID format", status_code=400)
    
    task = task_service.get_task(task_id)
    if not task:
        return APIResponse.not_found("Task", task_id)
    
    # Format response based on task status
    response_data = {
        'task_id': task_id,
        'description': task['description'],
        'status': task['status'],
        'progress': task['progress'],
        'created_at': task['created_at'].isoformat(),
        'updated_at': task['updated_at'].isoformat()
    }
    
    if task['status'] == 'completed':
        response_data['result'] = task['result']
    elif task['status'] == 'error':
        response_data['error'] = task['error']
    
    return APIResponse.success(data=response_data)

@app.route('/api/health')
def health_check():
    """Health check endpoint for load balancers and monitoring."""
    try:
        # Check database connection
        if db:
            db.get_setting('health_check', 'ok')
            database_status = 'healthy'
        else:
            database_status = 'unavailable'
        
        # Check Plaid availability
        from plaid_integration import PLAID_AVAILABLE
        plaid_status = 'available' if PLAID_AVAILABLE else 'unavailable'
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0',
            'components': {
                'database': database_status,
                'plaid': plaid_status,
                'modules': 'available' if MODULES_AVAILABLE else 'unavailable'
            }
        })
    
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/export-data')
def export_data():
    """Export all data as JSON."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        export_data = db.export_data()
        
        filename = f"expense_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join('data', filename)
        
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        return send_file(filepath, as_attachment=True, download_name=filename)
    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        return jsonify({'error': 'Export failed'}), 500

# ====================
# MISSING API ENDPOINTS
# ====================

@app.route('/api/upload-receipts', methods=['POST'])
def upload_receipts():
    """Upload multiple receipt files."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    trip_id = request.form.get('trip_id', type=int)
    transaction_id = request.form.get('transaction_id', type=int)
    
    uploads = []
    
    try:
        for file in files:
            if file.filename == '':
                continue
            
            if file and allowed_file(file.filename):
                # Generate secure filename
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                unique_filename = f"{timestamp}_{filename}"
                
                # Save file
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                
                # Determine file type
                file_type = 'pdf' if filename.lower().endswith('.pdf') else 'image'
                
                # Save to database
                receipt_data = {
                    'transaction_id': transaction_id,
                    'trip_id': trip_id,
                    'filename': filename,
                    'file_path': file_path,
                    'file_type': file_type,
                    'file_size': os.path.getsize(file_path),
                    'upload_source': 'manual'
                }
                
                receipt_id = db.save_receipt(receipt_data)
                
                uploads.append({
                    'receipt_id': receipt_id,
                    'filename': filename,
                    'file_path': file_path,
                    'file_type': file_type,
                    'size': receipt_data['file_size'],
                    'url': f'/api/receipt-file/{receipt_id}',
                    'thumbnail_url': f'/api/receipt-thumbnail/{receipt_id}' if file_type == 'image' else None
                })
        
        return jsonify({
            'success': True,
            'uploads': uploads,
            'message': f'Successfully uploaded {len(uploads)} files'
        })
    
    except Exception as e:
        logger.error(f"Error uploading receipts: {e}")
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/bulk-upload-receipts', methods=['POST'])
def bulk_upload_receipts():
    """Bulk upload receipts for automatic matching."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    uploads = []
    
    try:
        for file in files:
            if file.filename == '' or not allowed_file(file.filename):
                continue
            
            # Generate secure filename
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{timestamp}_{filename}"
            
            # Save file
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            
            # Determine file type
            file_type = 'pdf' if filename.lower().endswith('.pdf') else 'image'
            
            # Save to database (unmatched initially)
            receipt_data = {
                'transaction_id': None,
                'trip_id': None,
                'filename': filename,
                'file_path': file_path,
                'file_type': file_type,
                'file_size': os.path.getsize(file_path),
                'upload_source': 'bulk'
            }
            
            receipt_id = db.save_receipt(receipt_data)
            
            uploads.append({
                'receipt_id': receipt_id,
                'filename': filename,
                'size': receipt_data['file_size']
            })
        
        return jsonify({
            'success': True,
            'uploads': uploads,
            'message': f'Successfully uploaded {len(uploads)} files'
        })
    
    except Exception as e:
        logger.error(f"Error bulk uploading receipts: {e}")
        return jsonify({'error': f'Bulk upload failed: {str(e)}'}), 500

@app.route('/api/receipt-file/<int:receipt_id>')
def serve_receipt_file(receipt_id):
    """Serve a receipt file by ID."""
    if not db:
        return abort(404)
    
    try:
        # Get receipt info from database
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,))
            receipt = cursor.fetchone()
        
        if not receipt:
            return abort(404)
        
        file_path = receipt['file_path']
        if not os.path.exists(file_path):
            return abort(404)
        
        # Determine mimetype
        mimetype = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        
        return send_file(file_path, mimetype=mimetype)
    
    except Exception as e:
        logger.error(f"Error serving receipt file: {e}")
        return abort(500)

@app.route('/api/receipt-thumbnail/<int:receipt_id>')
def serve_receipt_thumbnail(receipt_id):
    """Serve a thumbnail for image receipts."""
    # For now, just serve the original file
    # In production, you'd generate actual thumbnails
    return serve_receipt_file(receipt_id)

@app.route('/api/receipts/<int:trip_id>/<int:transaction_id>')
def get_receipts_for_transaction(trip_id, transaction_id):
    """Get receipts for a specific transaction."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        receipts = db.get_receipts_for_transaction(transaction_id)
        
        # Add URLs to receipt data
        for receipt in receipts:
            receipt['url'] = f'/api/receipt-file/{receipt["id"]}'
            if receipt['file_type'] == 'image':
                receipt['thumbnail_url'] = f'/api/receipt-thumbnail/{receipt["id"]}'
        
        return jsonify({'receipts': receipts})
    
    except Exception as e:
        logger.error(f"Error getting receipts: {e}")
        return jsonify({'error': 'Failed to load receipts'}), 500

@app.route('/api/receipts/<int:trip_id>/<int:transaction_id>/rotate', methods=['POST'])
def rotate_receipt(trip_id, transaction_id):
    """Rotate a receipt image."""
    # Placeholder - would implement actual image rotation
    return jsonify({'success': True, 'message': 'Receipt rotated (placeholder)'})

@app.route('/api/receipts/<int:trip_id>/<int:transaction_id>/ocr', methods=['POST'])
def ocr_receipt(trip_id, transaction_id):
    """Extract text from receipt using OCR."""
    # Placeholder - would implement actual OCR
    return jsonify({
        'text': 'Sample extracted text from receipt (placeholder)',
        'confidence': 0.85
    })

@app.route('/api/receipts/<int:trip_id>/<int:transaction_id>/flag', methods=['POST'])
def flag_receipt(trip_id, transaction_id):
    """Flag a receipt for manual review."""
    data = request.get_json()
    issue = data.get('issue', 'No details provided')
    
    # Placeholder - would save flag to database
    logger.info(f"Receipt flagged for trip {trip_id}, transaction {transaction_id}: {issue}")
    
    return jsonify({'success': True, 'message': 'Receipt flagged for review'})

@app.route('/api/receipts/<int:trip_id>/<int:transaction_id>', methods=['DELETE'])
def delete_receipt(trip_id, transaction_id):
    """Delete a receipt."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        # Get receipts for this transaction
        receipts = db.get_receipts_for_transaction(transaction_id)
        
        for receipt in receipts:
            # Delete file from filesystem
            file_path = receipt['file_path']
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # Delete from database
            db.delete_receipt(receipt['id'])
        
        return jsonify({'success': True, 'message': 'Receipts deleted'})
    
    except Exception as e:
        logger.error(f"Error deleting receipt: {e}")
        return jsonify({'error': 'Failed to delete receipt'}), 500

@app.route('/api/receipt-stats')
def get_receipt_stats():
    """Get receipt statistics."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        stats = db.get_receipt_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting receipt stats: {e}")
        return jsonify({'error': 'Failed to load stats'}), 500

@app.route('/api/auto-match-receipts', methods=['POST'])
def auto_match_receipts():
    """Automatically match unassigned receipts to transactions."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        # Placeholder implementation
        # In real implementation, would use ML/heuristics to match receipts
        matches = 0
        
        # Get unmatched receipts
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM receipts WHERE transaction_id IS NULL")
            unmatched_receipts = cursor.fetchall()
        
        # Simple matching logic (placeholder)
        # Would implement more sophisticated matching in production
        
        return jsonify({
            'success': True,
            'matches': matches,
            'message': f'Matched {matches} receipts to transactions'
        })
    
    except Exception as e:
        logger.error(f"Error auto-matching receipts: {e}")
        return jsonify({'error': 'Auto-matching failed'}), 500

@app.route('/api/trips/<int:trip_id>/transactions/<int:transaction_id>')
def get_transaction_details(trip_id, transaction_id):
    """Get detailed information about a transaction."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM transactions WHERE id = ? AND trip_id = ?", 
                         (transaction_id, trip_id))
            transaction = cursor.fetchone()
        
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404
        
        return jsonify(dict(transaction))
    
    except Exception as e:
        logger.error(f"Error getting transaction details: {e}")
        return jsonify({'error': 'Failed to load transaction'}), 500

@app.route('/api/validate-trips', methods=['POST'])
def validate_trips():
    """Validate selected trips for Concur submission."""
    data = request.get_json()
    trip_ids = data.get('trip_ids', [])
    
    if not trip_ids:
        return jsonify({'error': 'No trips provided'}), 400
    
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        errors = []
        warnings = []
        
        for trip_id in trip_ids:
            trip = db.get_trip_by_id(trip_id)
            if not trip:
                errors.append(f"Trip {trip_id} not found")
                continue
            
            # Check for business purpose
            if not trip.get('business_purpose'):
                errors.append(f"Trip to {trip['primary_location']} missing business purpose")
            
            # Check for uncategorized transactions
            uncategorized = [t for t in trip['transactions'] if t['category'] == 'OTHER']
            if uncategorized:
                warnings.append(f"Trip to {trip['primary_location']} has {len(uncategorized)} uncategorized expenses")
            
            # Check for missing receipts
            transactions_with_receipts = 0
            for transaction in trip['transactions']:
                receipts = db.get_receipts_for_transaction(transaction['id'])
                if receipts:
                    transactions_with_receipts += 1
            
            missing_receipts = len(trip['transactions']) - transactions_with_receipts
            if missing_receipts > 0:
                warnings.append(f"Trip to {trip['primary_location']} missing {missing_receipts} receipts")
        
        return jsonify({
            'has_errors': len(errors) > 0,
            'has_warnings': len(warnings) > 0,
            'errors': errors,
            'warnings': warnings
        })
    
    except Exception as e:
        logger.error(f"Error validating trips: {e}")
        return jsonify({'error': 'Validation failed'}), 500

@app.route('/api/preview-concur-reports', methods=['POST'])
def preview_concur_reports():
    """Preview what Concur reports will look like."""
    data = request.get_json()
    trip_ids = data.get('trip_ids', [])
    
    if not trip_ids or not db:
        return jsonify({'error': 'Invalid request'}), 400
    
    try:
        reports = []
        
        for trip_id in trip_ids:
            trip = db.get_trip_by_id(trip_id)
            if not trip:
                continue
            
            expenses = []
            for transaction in trip['transactions']:
                receipts = db.get_receipts_for_transaction(transaction['id'])
                
                expenses.append({
                    'date': transaction['date'],
                    'expense_type': transaction['category'],
                    'vendor': transaction['description'][:30],
                    'amount': transaction['amount'],
                    'has_receipt': len(receipts) > 0
                })
            
            reports.append({
                'name': f"Travel - {trip['primary_location']} ({trip['start_date']} - {trip['end_date']})",
                'business_purpose': trip.get('business_purpose', f"Business travel to {trip['primary_location']}"),
                'total_amount': trip['total_amount'],
                'expense_count': len(expenses),
                'expenses': expenses
            })
        
        return jsonify({'reports': reports})
    
    except Exception as e:
        logger.error(f"Error previewing reports: {e}")
        return jsonify({'error': 'Preview failed'}), 500

@app.route('/api/submission-history')
def get_submission_history():
    """Get history of Concur submissions."""
    if not db:
        return jsonify({'error': 'Database not available'}), 500
    
    try:
        reports = db.get_concur_reports(limit=20)
        
        # Group by submission date
        submissions = {}
        for report in reports:
            date_key = report['created_at'][:10]  # YYYY-MM-DD
            if date_key not in submissions:
                submissions[date_key] = {
                    'id': f"submission_{date_key}",
                    'date': date_key,
                    'report_count': 0,
                    'total_amount': 0.0,
                    'status': 'completed'
                }
            
            submissions[date_key]['report_count'] += 1
            submissions[date_key]['total_amount'] += report['total_amount']
        
        return jsonify({'submissions': list(submissions.values())})
    
    except Exception as e:
        logger.error(f"Error getting submission history: {e}")
        return jsonify({'error': 'Failed to load history'}), 500

@app.route('/api/export-concur-data')
def export_concur_data():
    """Export trip data in format suitable for manual Concur entry."""
    trip_ids = request.args.get('trip_ids', '').split(',')
    trip_ids = [int(id.strip()) for id in trip_ids if id.strip().isdigit()]
    
    if not trip_ids or not db:
        return jsonify({'error': 'Invalid request'}), 400
    
    try:
        export_data = []
        
        for trip_id in trip_ids:
            trip = db.get_trip_by_id(trip_id)
            if not trip:
                continue
            
            for transaction in trip['transactions']:
                export_data.append({
                    'Date': transaction['date'],
                    'Description': transaction['description'],
                    'Amount': transaction['amount'],
                    'Category': transaction['category'],
                    'Location': transaction.get('location', ''),
                    'Business Purpose': trip.get('business_purpose', ''),
                    'Trip': f"{trip['primary_location']} ({trip['start_date']} - {trip['end_date']})"
                })
        
        # Create CSV
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=export_data[0].keys())
        writer.writeheader()
        writer.writerows(export_data)
        
        # Create response
        from flask import Response
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=concur_expenses.csv'}
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Error exporting Concur data: {e}")
        return jsonify({'error': 'Export failed'}), 500

@app.route('/api/export-submission-report')
def export_submission_report():
    """Export a summary report of the last submission."""
    # Placeholder - would generate detailed submission report
    return jsonify({'message': 'Submission report export not yet implemented'})

# Error handlers
@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 16MB.'}), 413

@app.errorhandler(404)
def handle_not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint not found'}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def handle_server_error(e):
    logger.error(f"Server error: {e}")
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    app.run(debug=True, host='0.0.0.0', port=5000)