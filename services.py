#!/usr/bin/env python3
"""
Service layer implementing business logic separate from API endpoints.
"""

import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import threading

from friday_panic_button import FridayPanicButton, friday_panic, process_bulk_expenses
from database_pool import DatabaseManager, get_db
from validators import TransactionInput, BulkProcessRequest, FridayPanicRequest
from config import config

logger = logging.getLogger(__name__)

class TaskService:
    """Service for managing background tasks."""
    
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._cleanup_old_tasks()
    
    def create_task(self, description: str) -> str:
        """Create a new background task."""
        task_id = str(uuid.uuid4())
        
        with self._lock:
            self.tasks[task_id] = {
                'id': task_id,
                'description': description,
                'status': 'pending',
                'progress': 0,
                'result': None,
                'error': None,
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }
        
        logger.info(f"Created task {task_id}: {description}")
        return task_id
    
    def update_task(self, task_id: str, status: str = None, progress: int = None, 
                   result: Any = None, error: str = None):
        """Update task status."""
        with self._lock:
            if task_id not in self.tasks:
                logger.warning(f"Attempted to update non-existent task: {task_id}")
                return False
            
            task = self.tasks[task_id]
            
            if status:
                task['status'] = status
            if progress is not None:
                task['progress'] = progress
            if result is not None:
                task['result'] = result
            if error:
                task['error'] = error
                task['status'] = 'error'
            
            task['updated_at'] = datetime.now()
        
        return True
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status."""
        with self._lock:
            return self.tasks.get(task_id)
    
    def _cleanup_old_tasks(self):
        """Remove old completed tasks."""
        def cleanup():
            with self._lock:
                now = datetime.now()
                to_remove = []
                
                for task_id, task in self.tasks.items():
                    age = (now - task['created_at']).total_seconds()
                    if age > config.TASK_MAX_AGE:
                        to_remove.append(task_id)
                
                for task_id in to_remove:
                    del self.tasks[task_id]
                
                if to_remove:
                    logger.info(f"Cleaned up {len(to_remove)} old tasks")
        
        # Schedule periodic cleanup
        timer = threading.Timer(config.TASK_CLEANUP_INTERVAL, self._cleanup_old_tasks)
        timer.daemon = True
        timer.start()
        
        # Run initial cleanup
        cleanup()

class ExpenseProcessingService:
    """Service for processing expenses with Friday Panic Button."""
    
    def __init__(self, db: DatabaseManager = None, task_service: TaskService = None):
        self.db = db or get_db()
        self.task_service = task_service or TaskService()
        self.panic_button = FridayPanicButton()
    
    def process_transactions(self, request: FridayPanicRequest) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Process transactions with Friday Panic Button.
        
        Returns:
            Tuple of (success, result, error_message)
        """
        try:
            # Get transactions
            if request.trip_id:
                trip = self.db.get_trip_by_id(request.trip_id)
                if not trip:
                    return False, None, f"Trip {request.trip_id} not found"
                transactions = trip.get('transactions', [])
            elif request.transactions:
                transactions = request.transactions
            else:
                # Get recent uncategorized transactions
                transactions = self._get_recent_uncategorized_transactions()
            
            if not transactions:
                return False, None, "No transactions to process"
            
            # Process with Friday Panic
            result = friday_panic(transactions)
            
            # Save results if requested and confidence is high
            if request.auto_save and result.get('ready_to_submit'):
                self._save_categorization_results(result, request.trip_id)
            
            return True, result, None
            
        except Exception as e:
            logger.error(f"Error processing transactions: {e}", exc_info=True)
            return False, None, str(e)
    
    def process_bulk(self, request: BulkProcessRequest) -> str:
        """
        Process bulk expenses in background.
        
        Returns:
            Task ID for tracking progress
        """
        task_id = self.task_service.create_task(
            f"Bulk processing expenses from {request.start_date}"
        )
        
        def process_in_background():
            try:
                self.task_service.update_task(task_id, status='running', progress=5)
                
                # Get all transactions in date range
                transactions = self.db.get_transactions_by_date_range(
                    request.start_date, 
                    request.end_date
                )
                
                if not transactions:
                    self.task_service.update_task(
                        task_id, 
                        status='completed',
                        progress=100,
                        result={'message': 'No transactions found in date range'}
                    )
                    return
                
                self.task_service.update_task(task_id, progress=20)
                
                # Convert to dictionaries
                trans_list = [dict(t) for t in transactions]
                
                # Process in bulk mode
                result = process_bulk_expenses(
                    trans_list, 
                    start_date=request.start_date,
                    end_date=request.end_date
                )
                
                self.task_service.update_task(task_id, progress=80)
                
                # Save results
                saved_count = self._save_bulk_results(result)
                
                # Update final result
                result['saved_count'] = saved_count
                
                self.task_service.update_task(
                    task_id,
                    status='completed',
                    progress=100,
                    result=result
                )
                
                logger.info(f"Bulk processing completed: {result['total_transactions']} transactions, "
                          f"{result['total_trips']} trips, {saved_count} saved")
                
            except Exception as e:
                logger.error(f"Bulk processing failed: {e}", exc_info=True)
                self.task_service.update_task(
                    task_id,
                    error=str(e)
                )
        
        # Start background thread
        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _get_recent_uncategorized_transactions(self, days: int = 30) -> List[Dict]:
        """Get recent transactions without categories."""
        query = """
            SELECT * FROM transactions 
            WHERE (category IS NULL OR category = 'OTHER')
            AND date >= date('now', ? || ' days')
            ORDER BY date DESC
        """
        
        results = self.db.pool.execute(query, (-days,), fetch='all')
        return [dict(r) for r in results] if results else []
    
    def _save_categorization_results(self, result: Dict, trip_id: Optional[int] = None):
        """Save categorization results to database."""
        try:
            updates = []
            
            for trans in result.get('transactions', []):
                if 'id' in trans and trans.get('confidence', 0) > config.CONFIDENCE_THRESHOLD:
                    updates.append((
                        trans['id'],
                        trans['category'],
                        trans['confidence']
                    ))
            
            if updates:
                saved = self.db.bulk_update_categories(updates)
                logger.info(f"Saved {saved} transaction categorizations")
            
            # Update trip business purpose if provided
            if trip_id and result.get('business_purpose'):
                purpose = result['business_purpose'].get('primary_purpose')
                if purpose:
                    with self.db.pool.transaction() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE trips 
                            SET business_purpose = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (purpose, trip_id))
                    logger.info(f"Updated trip {trip_id} business purpose")
                    
        except Exception as e:
            logger.error(f"Error saving categorization results: {e}")
            raise
    
    def _save_bulk_results(self, bulk_result: Dict) -> int:
        """Save bulk processing results."""
        saved_count = 0
        
        try:
            for trip in bulk_result.get('trips', []):
                # Create trip record
                trip_data = {
                    'start_date': trip['date_range']['start'].strftime('%Y-%m-%d') if isinstance(trip['date_range']['start'], datetime) else trip['date_range']['start'],
                    'end_date': trip['date_range']['end'].strftime('%Y-%m-%d') if isinstance(trip['date_range']['end'], datetime) else trip['date_range']['end'],
                    'business_purpose': trip['business_purpose'].get('primary_purpose'),
                    'total_amount': trip.get('total_amount', 0),
                    'status': 'ready' if not trip.get('needs_review') else 'needs_review'
                }
                
                # Save categorized transactions
                updates = []
                for trans in trip.get('transactions', []):
                    if 'id' in trans and trans.get('confidence', 0) > config.CONFIDENCE_THRESHOLD:
                        updates.append((
                            trans['id'],
                            trans['category'],
                            trans['confidence']
                        ))
                
                if updates:
                    saved = self.db.bulk_update_categories(updates)
                    saved_count += saved
                    
        except Exception as e:
            logger.error(f"Error saving bulk results: {e}")
        
        return saved_count

class BusinessPurposeService:
    """Service for managing business purposes."""
    
    def __init__(self, db: DatabaseManager = None):
        self.db = db or get_db()
    
    def set_trip_purpose(self, trip_id: int, purpose: str, apply_to_all: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Set business purpose for a trip.
        
        Returns:
            Tuple of (success, error_message)
        """
        try:
            with self.db.pool.transaction() as conn:
                cursor = conn.cursor()
                
                # Update trip
                cursor.execute("""
                    UPDATE trips 
                    SET business_purpose = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (purpose, trip_id))
                
                if cursor.rowcount == 0:
                    return False, f"Trip {trip_id} not found"
                
                # Optionally mark all transactions as business
                if apply_to_all:
                    cursor.execute("""
                        UPDATE transactions 
                        SET category = CASE 
                            WHEN category IS NULL OR category = 'OTHER' 
                            THEN 'BUSINESS' 
                            ELSE category 
                        END,
                        updated_at = CURRENT_TIMESTAMP
                        WHERE trip_id = ?
                    """, (trip_id,))
                    
                    logger.info(f"Updated {cursor.rowcount} transactions for trip {trip_id}")
                
                return True, None
                
        except Exception as e:
            logger.error(f"Error setting trip purpose: {e}")
            return False, str(e)
    
    def validate_purpose(self, purpose: str) -> Dict[str, Any]:
        """
        Validate and enhance business purpose.
        
        Returns:
            Dictionary with validation results and suggestions
        """
        result = {
            'valid': True,
            'message': 'Purpose is valid',
            'suggestions': []
        }
        
        # Check for common issues
        if len(purpose.split()) < 3:
            result['valid'] = False
            result['message'] = "Purpose is too brief. Please provide more detail."
            result['suggestions'] = [
                "Add specific meeting types (e.g., 'client meetings', 'training sessions')",
                "Include location context (e.g., 'regional office visit')",
                "Specify the business objective"
            ]
        
        # Check for vague terms
        vague_terms = ['business', 'work', 'stuff', 'things', 'various']
        purpose_lower = purpose.lower()
        
        if any(term in purpose_lower for term in vague_terms):
            result['message'] = "Purpose could be more specific"
            result['suggestions'].append("Replace vague terms with specific activities")
        
        # Suggest enhancements
        if 'meeting' in purpose_lower and 'client' not in purpose_lower:
            result['suggestions'].append("Consider specifying meeting type (client, team, vendor)")
        
        if 'travel' in purpose_lower and not any(city in purpose_lower for city in ['york', 'francisco', 'angeles', 'chicago']):
            result['suggestions'].append("Consider adding destination city")
        
        return result

# Global service instances
_task_service: Optional[TaskService] = None
_expense_service: Optional[ExpenseProcessingService] = None
_purpose_service: Optional[BusinessPurposeService] = None

def get_task_service() -> TaskService:
    """Get global task service instance."""
    global _task_service
    if _task_service is None:
        _task_service = TaskService()
    return _task_service

def get_expense_service() -> ExpenseProcessingService:
    """Get global expense processing service instance."""
    global _expense_service
    if _expense_service is None:
        _expense_service = ExpenseProcessingService(task_service=get_task_service())
    return _expense_service

def get_purpose_service() -> BusinessPurposeService:
    """Get global business purpose service instance."""
    global _purpose_service
    if _purpose_service is None:
        _purpose_service = BusinessPurposeService()
    return _purpose_service