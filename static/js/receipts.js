// Receipts Management JavaScript

class ReceiptManager {
    constructor() {
        this.currentTrip = null;
        this.currentTransaction = null;
        this.uploadedFiles = [];
        this.receiptCache = new Map();
        
        this.initializeEventListeners();
    }

    initializeEventListeners() {
        // Global drag and drop prevention
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            document.body.addEventListener(eventName, (e) => {
                if (!e.target.closest('.drop-zone')) {
                    e.preventDefault();
                    e.stopPropagation();
                }
            });
        });

        // Receipt search and filtering
        const searchInput = document.getElementById('receipt-search');
        if (searchInput) {
            let searchTimeout;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    this.filterReceipts();
                }, 300);
            });
        }

        // Filter dropdowns
        const filterSelects = ['receipt-filter', 'trip-filter'];
        filterSelects.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('change', () => this.filterReceipts());
            }
        });
    }

    // File Upload Management
    async uploadFiles(files, tripId = null, transactionId = null) {
        const formData = new FormData();
        
        Array.from(files).forEach(file => {
            if (this.validateFile(file)) {
                formData.append('files', file);
            }
        });

        if (tripId) formData.append('trip_id', tripId);
        if (transactionId) formData.append('transaction_id', transactionId);

        try {
            const response = await fetch('/api/upload-receipts', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`Upload failed: ${response.statusText}`);
            }

            const result = await response.json();
            this.handleUploadSuccess(result);
            return result;
        } catch (error) {
            this.handleUploadError(error);
            throw error;
        }
    }

    validateFile(file) {
        const maxSize = 16 * 1024 * 1024; // 16MB
        const allowedTypes = ['image/jpeg', 'image/png', 'application/pdf'];

        if (file.size > maxSize) {
            this.showError(`File "${file.name}" is too large. Maximum size is 16MB.`);
            return false;
        }

        if (!allowedTypes.includes(file.type)) {
            this.showError(`File "${file.name}" is not a supported format. Use JPG, PNG, or PDF.`);
            return false;
        }

        return true;
    }

    handleUploadSuccess(result) {
        if (result.uploads && result.uploads.length > 0) {
            this.showSuccess(`Successfully uploaded ${result.uploads.length} file(s).`);
            this.refreshReceiptCounts();
            
            // Update UI for uploaded receipts
            result.uploads.forEach(upload => {
                this.updateReceiptUI(upload);
            });
        }
    }

    handleUploadError(error) {
        console.error('Upload error:', error);
        this.showError(`Upload failed: ${error.message}`);
    }

    updateReceiptUI(upload) {
        // Update expense card to show receipt attached
        if (upload.trip_id && upload.transaction_id) {
            const expenseCard = document.querySelector(
                `[data-trip="${upload.trip_id}"][data-transaction="${upload.transaction_id}"]`
            );
            
            if (expenseCard) {
                expenseCard.classList.remove('missing-receipt');
                expenseCard.classList.add('has-receipt');
                
                const statusElement = expenseCard.querySelector('.folio-status');
                if (statusElement) {
                    statusElement.innerHTML = '<span class="text-success"><i class="fas fa-check"></i> Receipt attached</span>';
                }

                // Update thumbnail if present
                const thumbnailContainer = expenseCard.querySelector('.receipt-thumbnail-container');
                if (thumbnailContainer) {
                    thumbnailContainer.innerHTML = `
                        <img src="${upload.thumbnail_url}" alt="Receipt" class="receipt-thumbnail">
                    `;
                }
            }
        }
    }

    // Receipt Viewing and Management
    async showReceiptViewer(tripId, transactionId) {
        this.currentTrip = tripId;
        this.currentTransaction = transactionId;

        try {
            // Load expense details
            const expenseData = await this.loadExpenseDetails(tripId, transactionId);
            this.populateExpenseInfo(expenseData);

            // Load receipt data
            const receiptData = await this.loadReceiptData(tripId, transactionId);
            this.displayReceipt(receiptData);

            // Show modal
            const modal = new bootstrap.Modal(document.getElementById('receiptViewerModal'));
            modal.show();
        } catch (error) {
            this.showError(`Failed to load receipt: ${error.message}`);
        }
    }

    async loadExpenseDetails(tripId, transactionId) {
        const cacheKey = `expense-${tripId}-${transactionId}`;
        
        if (this.receiptCache.has(cacheKey)) {
            return this.receiptCache.get(cacheKey);
        }

        const response = await fetch(`/api/trips/${tripId}/transactions/${transactionId}`);
        if (!response.ok) {
            throw new Error('Failed to load expense details');
        }

        const data = await response.json();
        this.receiptCache.set(cacheKey, data);
        return data;
    }

    async loadReceiptData(tripId, transactionId) {
        const response = await fetch(`/api/receipts/${tripId}/${transactionId}`);
        if (!response.ok) {
            throw new Error('Failed to load receipt data');
        }

        return await response.json();
    }

    populateExpenseInfo(expenseData) {
        const infoElement = document.getElementById('expense-info');
        if (infoElement) {
            infoElement.innerHTML = `
                <div class="expense-details">
                    <p><strong>Vendor:</strong> ${expenseData.description}</p>
                    <p><strong>Amount:</strong> $${expenseData.amount.toFixed(2)}</p>
                    <p><strong>Date:</strong> ${this.formatDate(expenseData.date)}</p>
                    <p><strong>Category:</strong> 
                        <span class="badge bg-secondary">${expenseData.category}</span>
                    </p>
                    ${expenseData.location ? `<p><strong>Location:</strong> ${expenseData.location}</p>` : ''}
                    ${expenseData.business_purpose ? `<p><strong>Business Purpose:</strong> ${expenseData.business_purpose}</p>` : ''}
                </div>
            `;
        }
    }

    displayReceipt(receiptData) {
        const imgElement = document.getElementById('receipt-image');
        const pdfElement = document.getElementById('receipt-pdf');
        const placeholderElement = document.getElementById('receipt-placeholder');

        // Hide all elements first
        [imgElement, pdfElement, placeholderElement].forEach(el => {
            if (el) el.style.display = 'none';
        });

        if (receiptData.receipts && receiptData.receipts.length > 0) {
            const receipt = receiptData.receipts[0];
            
            if (receipt.file_type === 'pdf') {
                pdfElement.src = receipt.url;
                pdfElement.style.display = 'block';
            } else {
                imgElement.src = receipt.url;
                imgElement.style.display = 'block';
            }
        } else {
            placeholderElement.style.display = 'block';
        }
    }

    // Receipt Actions
    async rotateReceipt() {
        if (this.currentTrip === null || this.currentTransaction === null) return;

        try {
            const response = await fetch(
                `/api/receipts/${this.currentTrip}/${this.currentTransaction}/rotate`,
                { method: 'POST' }
            );

            if (response.ok) {
                const receiptData = await this.loadReceiptData(this.currentTrip, this.currentTransaction);
                this.displayReceipt(receiptData);
                this.showSuccess('Receipt rotated successfully');
            }
        } catch (error) {
            this.showError(`Failed to rotate receipt: ${error.message}`);
        }
    }

    async deleteReceipt() {
        if (!confirm('Are you sure you want to delete this receipt?')) return;
        if (this.currentTrip === null || this.currentTransaction === null) return;

        try {
            const response = await fetch(
                `/api/receipts/${this.currentTrip}/${this.currentTransaction}`,
                { method: 'DELETE' }
            );

            if (response.ok) {
                this.displayReceipt({ receipts: [] });
                this.updateExpenseReceiptStatus(this.currentTrip, this.currentTransaction, false);
                this.showSuccess('Receipt deleted successfully');
            }
        } catch (error) {
            this.showError(`Failed to delete receipt: ${error.message}`);
        }
    }

    async performOCR() {
        if (this.currentTrip === null || this.currentTransaction === null) return;

        try {
            this.showLoading('Extracting text from receipt...');
            
            const response = await fetch(
                `/api/receipts/${this.currentTrip}/${this.currentTransaction}/ocr`,
                { method: 'POST' }
            );

            const result = await response.json();
            
            if (result.text) {
                this.showOCRResults(result.text, result.confidence);
            } else {
                this.showError('No text could be extracted from this receipt');
            }
        } catch (error) {
            this.showError(`OCR failed: ${error.message}`);
        } finally {
            this.hideLoading();
        }
    }

    showOCRResults(text, confidence) {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Extracted Text</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="alert alert-info">
                            <i class="fas fa-info-circle me-2"></i>
                            Confidence: ${Math.round(confidence * 100)}%
                        </div>
                        <div class="border rounded p-3" style="white-space: pre-wrap; font-family: monospace;">
${text}
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        <button type="button" class="btn btn-primary" onclick="copyToClipboard('${text.replace(/'/g, "\\'")}')">
                            <i class="fas fa-copy me-1"></i>Copy Text
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }

    // Filtering and Search
    filterReceipts() {
        const searchTerm = document.getElementById('receipt-search')?.value.toLowerCase() || '';
        const receiptFilter = document.getElementById('receipt-filter')?.value || 'all';
        const tripFilter = document.getElementById('trip-filter')?.value || 'all';

        const expenseCards = document.querySelectorAll('.expense-item');
        const tripSections = document.querySelectorAll('.trip-section');

        expenseCards.forEach(card => {
            const tripId = card.dataset.trip;
            const description = card.querySelector('.card-title')?.textContent.toLowerCase() || '';
            const amount = card.querySelector('.card-text')?.textContent.toLowerCase() || '';
            
            let showCard = true;

            // Search filter
            if (searchTerm && !description.includes(searchTerm) && !amount.includes(searchTerm)) {
                showCard = false;
            }

            // Receipt status filter
            if (receiptFilter !== 'all') {
                const hasReceipt = card.classList.contains('has-receipt');
                const isHotel = card.querySelector('.badge')?.textContent === 'HOTEL';
                
                switch (receiptFilter) {
                    case 'missing':
                        if (hasReceipt) showCard = false;
                        break;
                    case 'complete':
                        if (!hasReceipt) showCard = false;
                        break;
                    case 'hotels':
                        if (!isHotel) showCard = false;
                        break;
                }
            }

            // Trip filter
            if (tripFilter !== 'all' && tripId !== tripFilter) {
                showCard = false;
            }

            card.style.display = showCard ? 'block' : 'none';
        });

        // Hide trip sections with no visible cards
        tripSections.forEach(section => {
            const visibleCards = section.querySelectorAll('.expense-item[style*="block"], .expense-item:not([style*="none"])');
            section.style.display = visibleCards.length > 0 ? 'block' : 'none';
        });
    }

    // Auto-matching functionality
    async autoMatchReceipts() {
        try {
            this.showLoading('Matching receipts to expenses...');
            
            const response = await fetch('/api/auto-match-receipts', {
                method: 'POST'
            });

            const result = await response.json();
            
            if (result.matches > 0) {
                this.showSuccess(`Successfully matched ${result.matches} receipts to expenses.`);
                setTimeout(() => location.reload(), 2000);
            } else {
                this.showInfo('No additional matches found.');
            }
        } catch (error) {
            this.showError(`Auto-matching failed: ${error.message}`);
        } finally {
            this.hideLoading();
        }
    }

    // Hotel folio management
    async retrieveHotelFolios() {
        try {
            this.showLoading('Retrieving hotel folios...');
            
            const response = await fetch('/api/retrieve-folios', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    search_email: true,
                    download_folios: true
                })
            });

            const result = await response.json();
            
            if (result.task_id) {
                this.pollTaskProgress(result.task_id, (result) => {
                    if (result.retrieved_count > 0) {
                        this.showSuccess(`Retrieved ${result.retrieved_count} hotel folios.`);
                        setTimeout(() => location.reload(), 2000);
                    } else {
                        this.showInfo('No hotel folios found.');
                    }
                });
            }
        } catch (error) {
            this.showError(`Failed to retrieve folios: ${error.message}`);
            this.hideLoading();
        }
    }

    async pollTaskProgress(taskId, onComplete) {
        try {
            const response = await fetch(`/api/task-status/${taskId}`);
            const data = await response.json();
            
            if (data.status === 'running') {
                setTimeout(() => this.pollTaskProgress(taskId, onComplete), 2000);
            } else if (data.status === 'completed') {
                this.hideLoading();
                onComplete(data.result);
            } else if (data.status === 'error') {
                this.hideLoading();
                this.showError(`Task failed: ${data.error}`);
            }
        } catch (error) {
            this.hideLoading();
            this.showError(`Failed to check task status: ${error.message}`);
        }
    }

    // Utility methods
    updateExpenseReceiptStatus(tripId, transactionId, hasReceipt) {
        const expenseCard = document.querySelector(
            `[data-trip="${tripId}"][data-transaction="${transactionId}"]`
        );
        
        if (expenseCard) {
            if (hasReceipt) {
                expenseCard.classList.remove('missing-receipt');
                expenseCard.classList.add('has-receipt');
            } else {
                expenseCard.classList.remove('has-receipt');
                expenseCard.classList.add('missing-receipt');
            }
        }
    }

    async refreshReceiptCounts() {
        try {
            const response = await fetch('/api/receipt-stats');
            const data = await response.json();
            
            const elements = {
                'receipts-complete': data.complete || 0,
                'receipts-missing': data.missing || 0,
                'folios-retrieved': data.folios || 0,
                'total-attachments': data.total || 0
            };

            Object.entries(elements).forEach(([id, value]) => {
                const element = document.getElementById(id);
                if (element) element.textContent = value;
            });
        } catch (error) {
            console.error('Failed to refresh receipt counts:', error);
        }
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    }

    // Notification methods
    showSuccess(message) {
        this.showNotification(message, 'success');
    }

    showError(message) {
        this.showNotification(message, 'danger');
    }

    showInfo(message) {
        this.showNotification(message, 'info');
    }

    showNotification(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast position-fixed top-0 end-0 m-3`;
        toast.innerHTML = `
            <div class="toast-header">
                <i class="fas fa-${this.getIconForType(type)} text-${type} me-2"></i>
                <strong class="me-auto">${this.getTitleForType(type)}</strong>
                <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        `;
        
        document.body.appendChild(toast);
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();
        
        setTimeout(() => {
            if (document.body.contains(toast)) {
                document.body.removeChild(toast);
            }
        }, 5000);
    }

    getIconForType(type) {
        const icons = {
            'success': 'check-circle',
            'danger': 'exclamation-circle',
            'warning': 'exclamation-triangle',
            'info': 'info-circle'
        };
        return icons[type] || 'info-circle';
    }

    getTitleForType(type) {
        const titles = {
            'success': 'Success',
            'danger': 'Error',
            'warning': 'Warning',
            'info': 'Information'
        };
        return titles[type] || 'Notification';
    }

    showLoading(message = 'Loading...') {
        const loadingElement = document.getElementById('loading-overlay') || this.createLoadingOverlay();
        loadingElement.querySelector('.loading-message').textContent = message;
        loadingElement.style.display = 'flex';
    }

    hideLoading() {
        const loadingElement = document.getElementById('loading-overlay');
        if (loadingElement) {
            loadingElement.style.display = 'none';
        }
    }

    createLoadingOverlay() {
        const overlay = document.createElement('div');
        overlay.id = 'loading-overlay';
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `
            <div class="loading-content">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <div class="loading-message">Loading...</div>
            </div>
        `;
        
        const styles = `
            .loading-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.7);
                display: none;
                align-items: center;
                justify-content: center;
                z-index: 9999;
            }
            
            .loading-content {
                text-align: center;
                color: white;
                background: rgba(0, 0, 0, 0.8);
                padding: 2rem;
                border-radius: 0.5rem;
            }
        `;
        
        const styleSheet = document.createElement('style');
        styleSheet.textContent = styles;
        document.head.appendChild(styleSheet);
        
        document.body.appendChild(overlay);
        return overlay;
    }
}

// Global utility functions
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        receiptManager.showSuccess('Text copied to clipboard');
    });
}

// Initialize when DOM is ready
let receiptManager;
document.addEventListener('DOMContentLoaded', function() {
    receiptManager = new ReceiptManager();
});

// Global functions for template compatibility
function showReceiptModal(tripId, transactionId) {
    receiptManager.showReceiptViewer(tripId, transactionId);
}

function uploadForExpense(tripId, transactionId) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.jpg,.jpeg,.png,.pdf';
    input.multiple = true;
    input.onchange = (e) => {
        receiptManager.uploadFiles(e.target.files, tripId, transactionId);
    };
    input.click();
}

function retrieveFoliosForTrip(tripId) {
    receiptManager.retrieveHotelFolios();
}

function retrieveAllFolios() {
    receiptManager.retrieveHotelFolios();
}

function autoMatchReceipts() {
    receiptManager.autoMatchReceipts();
}

function rotateReceipt() {
    receiptManager.rotateReceipt();
}

function deleteReceipt() {
    receiptManager.deleteReceipt();
}

function ocrReceipt() {
    receiptManager.performOCR();
}

function enhanceReceipt() {
    receiptManager.showInfo('Receipt enhancement feature coming soon!');
}

function flagReceiptIssue() {
    const issue = prompt('What issue would you like to report with this receipt?');
    if (issue && receiptManager.currentTrip !== null && receiptManager.currentTransaction !== null) {
        fetch(`/api/receipts/${receiptManager.currentTrip}/${receiptManager.currentTransaction}/flag`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({issue: issue})
        })
        .then(() => receiptManager.showSuccess('Receipt flagged for review'));
    }
}

function saveReceiptChanges() {
    receiptManager.showSuccess('Receipt changes saved');
    bootstrap.Modal.getInstance(document.getElementById('receiptViewerModal')).hide();
}