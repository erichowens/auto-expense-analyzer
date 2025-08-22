// Concur Submission JavaScript

class ConcurManager {
    constructor() {
        this.selectedTrips = [];
        this.submissionInProgress = false;
        this.currentTaskId = null;
        this.validationResults = null;
        
        this.initializeEventListeners();
    }

    initializeEventListeners() {
        // Trip selection click handlers
        document.addEventListener('click', (e) => {
            if (e.target.closest('.trip-preview')) {
                const tripCard = e.target.closest('.trip-preview');
                const tripId = parseInt(tripCard.dataset.trip);
                if (tripId && !e.target.matches('input[type="checkbox"]')) {
                    this.toggleTripSelection(tripId);
                }
            }
        });

        // Checkbox change handlers
        document.addEventListener('change', (e) => {
            if (e.target.matches('input[data-trip]')) {
                const tripId = parseInt(e.target.dataset.trip);
                this.handleCheckboxChange(tripId, e.target.checked);
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                switch (e.key) {
                    case 'a':
                        if (e.target === document.body) {
                            e.preventDefault();
                            this.selectAllTrips();
                        }
                        break;
                    case 'Enter':
                        if (this.selectedTrips.length > 0) {
                            e.preventDefault();
                            this.startSubmissionFlow();
                        }
                        break;
                }
            }
        });
    }

    // Trip Selection Management
    toggleTripSelection(tripId) {
        const checkbox = document.getElementById(`trip-${tripId}`);
        const tripCard = document.querySelector(`[data-trip="${tripId}"]`);
        
        if (!checkbox || !tripCard) return;

        if (this.selectedTrips.includes(tripId)) {
            this.deselectTrip(tripId);
        } else {
            this.selectTrip(tripId);
        }
    }

    selectTrip(tripId) {
        if (!this.selectedTrips.includes(tripId)) {
            this.selectedTrips.push(tripId);
            this.updateTripUI(tripId, true);
            this.updateSelectionSummary();
            this.validateSelectionIfNeeded();
        }
    }

    deselectTrip(tripId) {
        const index = this.selectedTrips.indexOf(tripId);
        if (index > -1) {
            this.selectedTrips.splice(index, 1);
            this.updateTripUI(tripId, false);
            this.updateSelectionSummary();
            this.clearValidationIfNeeded();
        }
    }

    handleCheckboxChange(tripId, checked) {
        if (checked && !this.selectedTrips.includes(tripId)) {
            this.selectTrip(tripId);
        } else if (!checked && this.selectedTrips.includes(tripId)) {
            this.deselectTrip(tripId);
        }
    }

    updateTripUI(tripId, selected) {
        const checkbox = document.getElementById(`trip-${tripId}`);
        const tripCard = document.querySelector(`[data-trip="${tripId}"]`);
        
        if (checkbox) checkbox.checked = selected;
        if (tripCard) {
            tripCard.classList.toggle('selected', selected);
        }
    }

    selectAllTrips() {
        const allTripCards = document.querySelectorAll('[data-trip]');
        allTripCards.forEach(card => {
            const tripId = parseInt(card.dataset.trip);
            if (!this.selectedTrips.includes(tripId)) {
                this.selectTrip(tripId);
            }
        });
    }

    selectAllReadyTrips() {
        const readyTripCards = document.querySelectorAll('[data-trip] .badge-success');
        readyTripCards.forEach(badge => {
            const tripCard = badge.closest('[data-trip]');
            const tripId = parseInt(tripCard.dataset.trip);
            if (!this.selectedTrips.includes(tripId)) {
                this.selectTrip(tripId);
            }
        });
    }

    clearAllSelections() {
        [...this.selectedTrips].forEach(tripId => {
            this.deselectTrip(tripId);
        });
    }

    // Selection Summary and Step Management
    updateSelectionSummary() {
        this.updateStepIndicators();
        this.updateActionButtons();
        this.updateSelectionStats();
    }

    updateStepIndicators() {
        const step1 = document.getElementById('step-1');
        const step1Indicator = step1?.querySelector('.step-indicator');
        
        if (step1 && step1Indicator) {
            if (this.selectedTrips.length > 0) {
                step1.classList.add('completed');
                step1.classList.remove('active');
                step1Indicator.classList.add('completed');
                step1Indicator.innerHTML = '<i class="fas fa-check"></i>';
            } else {
                step1.classList.remove('completed');
                step1.classList.add('active');
                step1Indicator.classList.remove('completed');
                step1Indicator.textContent = '1';
            }
        }
    }

    updateActionButtons() {
        const hasSelection = this.selectedTrips.length > 0;
        
        // Enable/disable buttons based on selection
        const buttons = document.querySelectorAll('[data-requires-selection]');
        buttons.forEach(button => {
            button.disabled = !hasSelection;
        });
    }

    updateSelectionStats() {
        const totalAmount = this.calculateTotalAmount();
        const readyCount = this.countReadyTrips();
        
        // Update any stats display elements
        const statsElements = document.querySelectorAll('[data-selection-stat]');
        statsElements.forEach(element => {
            const stat = element.dataset.selectionStat;
            switch (stat) {
                case 'count':
                    element.textContent = this.selectedTrips.length;
                    break;
                case 'total':
                    element.textContent = `$${totalAmount.toFixed(2)}`;
                    break;
                case 'ready':
                    element.textContent = readyCount;
                    break;
            }
        });
    }

    calculateTotalAmount() {
        return this.selectedTrips.reduce((total, tripId) => {
            const tripCard = document.querySelector(`[data-trip="${tripId}"]`);
            const amountElement = tripCard?.querySelector('.fw-bold.text-primary');
            if (amountElement) {
                const amount = parseFloat(amountElement.textContent.replace('$', '').replace(',', ''));
                return total + (isNaN(amount) ? 0 : amount);
            }
            return total;
        }, 0);
    }

    countReadyTrips() {
        return this.selectedTrips.filter(tripId => {
            const tripCard = document.querySelector(`[data-trip="${tripId}"]`);
            return tripCard?.querySelector('.badge-success');
        }).length;
    }

    // Validation Management
    async validateSelectionIfNeeded() {
        if (this.selectedTrips.length > 0) {
            await this.validateSelectedTrips();
        }
    }

    clearValidationIfNeeded() {
        if (this.selectedTrips.length === 0) {
            this.clearValidation();
        }
    }

    async validateSelectedTrips() {
        try {
            const response = await fetch('/api/validate-trips', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trip_ids: this.selectedTrips })
            });

            if (!response.ok) {
                throw new Error('Validation request failed');
            }

            this.validationResults = await response.json();
            this.displayValidationResults();
            this.updateValidationStep();

            if (!this.validationResults.has_errors) {
                await this.loadConcurPreview();
            }
        } catch (error) {
            this.showError(`Validation failed: ${error.message}`);
        }
    }

    displayValidationResults() {
        const validationSection = document.getElementById('validation-section');
        const resultsContainer = document.getElementById('validation-results');
        
        if (!validationSection || !resultsContainer) return;

        let html = '';
        const results = this.validationResults;

        if (results.errors && results.errors.length > 0) {
            html += this.createValidationAlert('danger', 'Errors (Must Fix)', results.errors);
        }

        if (results.warnings && results.warnings.length > 0) {
            html += this.createValidationAlert('warning', 'Warnings', results.warnings);
        }

        if (!results.has_errors && !results.has_warnings) {
            html += this.createValidationAlert('success', 'All Good!', ['Selected trips are ready for submission to Concur.']);
        }

        resultsContainer.innerHTML = html;
        validationSection.style.display = 'block';
    }

    createValidationAlert(type, title, items) {
        const alertClass = type === 'danger' ? 'validation-error' : 
                          type === 'warning' ? 'policy-warning' : 'submission-success';
        const iconClass = type === 'danger' ? 'times-circle' : 
                         type === 'warning' ? 'exclamation-triangle' : 'check-circle';

        return `
            <div class="${alertClass} p-3 rounded mb-3">
                <h6><i class="fas fa-${iconClass} me-2"></i>${title}</h6>
                <ul class="mb-0">
                    ${items.map(item => `<li>${item}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    updateValidationStep() {
        const step2 = document.getElementById('step-2');
        const step2Indicator = step2?.querySelector('.step-indicator');
        
        if (!step2 || !step2Indicator) return;

        // Clear previous states
        step2.classList.remove('active', 'completed', 'error');
        step2Indicator.classList.remove('active', 'completed', 'error');

        if (this.validationResults.has_errors) {
            step2.classList.add('error');
            step2Indicator.classList.add('error');
            step2Indicator.innerHTML = '<i class="fas fa-times"></i>';
        } else if (this.validationResults.has_warnings) {
            step2.classList.add('active');
            step2Indicator.classList.add('active');
            step2Indicator.innerHTML = '<i class="fas fa-exclamation"></i>';
        } else {
            step2.classList.add('completed');
            step2Indicator.classList.add('completed');
            step2Indicator.innerHTML = '<i class="fas fa-check"></i>';
        }
    }

    clearValidation() {
        const validationSection = document.getElementById('validation-section');
        const previewSection = document.getElementById('preview-section');
        
        if (validationSection) validationSection.style.display = 'none';
        if (previewSection) previewSection.style.display = 'none';
        
        this.validationResults = null;
    }

    // Preview Management
    async loadConcurPreview() {
        try {
            const response = await fetch('/api/preview-concur-reports', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trip_ids: this.selectedTrips })
            });

            if (!response.ok) {
                throw new Error('Failed to load preview');
            }

            const previewData = await response.json();
            this.displayConcurPreview(previewData);
            this.showPreviewSection();
        } catch (error) {
            this.showError(`Preview failed: ${error.message}`);
        }
    }

    displayConcurPreview(previewData) {
        const previewContent = document.getElementById('concur-preview-content');
        if (!previewContent) return;

        let html = '';

        previewData.reports.forEach((report, index) => {
            html += `
                <div class="concur-preview mb-4 p-3 rounded">
                    <div class="d-flex justify-content-between align-items-start mb-3">
                        <div>
                            <h6 class="mb-1">Report ${index + 1}: ${report.name}</h6>
                            <p class="text-muted mb-0">${report.business_purpose}</p>
                        </div>
                        <div class="text-end">
                            <div class="h5 mb-0 text-primary">$${report.total_amount.toFixed(2)}</div>
                            <small class="text-muted">${report.expense_count} expenses</small>
                        </div>
                    </div>
                    
                    <div class="table-responsive">
                        <table class="table table-sm">
                            <thead>
                                <tr>
                                    <th>Date</th>
                                    <th>Type</th>
                                    <th>Vendor</th>
                                    <th>Amount</th>
                                    <th>Receipt</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${report.expenses.map(expense => `
                                    <tr>
                                        <td>${this.formatDate(expense.date)}</td>
                                        <td>
                                            <span class="badge bg-light text-dark">${expense.expense_type}</span>
                                        </td>
                                        <td>${expense.vendor}</td>
                                        <td>$${expense.amount.toFixed(2)}</td>
                                        <td>
                                            ${expense.has_receipt ? 
                                                '<i class="fas fa-check text-success"></i>' : 
                                                '<i class="fas fa-times text-danger"></i>'
                                            }
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        });

        previewContent.innerHTML = html;
    }

    showPreviewSection() {
        const previewSection = document.getElementById('preview-section');
        if (previewSection) {
            previewSection.style.display = 'block';
            previewSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    // Submission Management
    async startSubmissionFlow() {
        if (this.submissionInProgress) return;
        if (this.selectedTrips.length === 0) {
            this.showError('Please select at least one trip to submit.');
            return;
        }

        // Check if validation has errors
        if (this.validationResults?.has_errors) {
            const proceed = confirm('There are validation errors. Do you want to try auto-fix first?');
            if (proceed) {
                await this.attemptAutoFix();
            }
            return;
        }

        await this.createConcurReports();
    }

    async createConcurReports() {
        if (this.submissionInProgress) return;

        const autoSubmit = document.getElementById('auto-submit-checkbox')?.checked || false;
        const attachReceipts = document.getElementById('attach-receipts-checkbox')?.checked || true;

        try {
            this.submissionInProgress = true;
            this.showProgressModal();

            const response = await fetch('/api/create-concur-reports', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    trip_ids: this.selectedTrips,
                    submit_reports: autoSubmit,
                    attach_receipts: attachReceipts
                })
            });

            if (!response.ok) {
                throw new Error('Submission request failed');
            }

            const result = await response.json();
            this.currentTaskId = result.task_id;
            
            if (result.task_id) {
                await this.pollSubmissionProgress();
            } else {
                // Immediate result
                this.handleSubmissionComplete(result);
            }
        } catch (error) {
            this.submissionInProgress = false;
            this.hideProgressModal();
            this.showError(`Submission failed: ${error.message}`);
        }
    }

    async pollSubmissionProgress() {
        if (!this.currentTaskId) return;

        try {
            const response = await fetch(`/api/task-status/${this.currentTaskId}`);
            const data = await response.json();

            this.updateProgressModal(data.progress || 0, data.description || 'Processing...');

            if (data.status === 'running') {
                setTimeout(() => this.pollSubmissionProgress(), 2000);
            } else if (data.status === 'completed') {
                this.handleSubmissionComplete(data.result);
            } else if (data.status === 'error') {
                this.handleSubmissionError(data.error);
            }
        } catch (error) {
            this.handleSubmissionError(`Progress check failed: ${error.message}`);
        }
    }

    handleSubmissionComplete(result) {
        this.submissionInProgress = false;
        this.hideProgressModal();
        this.displaySubmissionResults(result);
        this.updateSubmissionSteps(true);
        this.clearSelection();
    }

    handleSubmissionError(error) {
        this.submissionInProgress = false;
        this.hideProgressModal();
        this.updateSubmissionSteps(false);
        this.showError(`Submission failed: ${error}`);
    }

    displaySubmissionResults(results) {
        const resultsSection = document.getElementById('results-section');
        const resultsContent = document.getElementById('submission-results');
        
        if (!resultsSection || !resultsContent) return;

        let successCount = 0;
        let errorCount = 0;
        let html = '';

        if (results.created_reports) {
            results.created_reports.forEach(report => {
                const isSuccess = report.status === 'created' || report.status === 'submitted';
                
                if (isSuccess) {
                    successCount++;
                    html += this.createResultItem(report, 'success');
                } else {
                    errorCount++;
                    html += this.createResultItem(report, 'error');
                }
            });
        }

        // Add summary header
        const summaryHtml = this.createResultsSummary(successCount, errorCount, this.selectedTrips.length);
        resultsContent.innerHTML = summaryHtml + html;
        resultsSection.style.display = 'block';
        
        // Scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    createResultsSummary(successCount, errorCount, totalCount) {
        return `
            <div class="row mb-4">
                <div class="col-md-4">
                    <div class="text-center p-3 border rounded">
                        <h4 class="text-success mb-1">${successCount}</h4>
                        <small class="text-muted">Reports Created</small>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="text-center p-3 border rounded">
                        <h4 class="text-danger mb-1">${errorCount}</h4>
                        <small class="text-muted">Failed</small>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="text-center p-3 border rounded">
                        <h4 class="text-primary mb-1">${totalCount}</h4>
                        <small class="text-muted">Total Processed</small>
                    </div>
                </div>
            </div>
        `;
    }

    createResultItem(report, type) {
        const alertClass = type === 'success' ? 'submission-success' : 'validation-error';
        const badgeClass = type === 'success' ? 'success' : 'danger';
        const badgeText = report.status || (type === 'success' ? 'Created' : 'Failed');

        return `
            <div class="${alertClass} p-3 rounded mb-2 d-flex justify-content-between align-items-center">
                <div>
                    <strong>${report.trip_location}</strong>
                    ${report.report_id ? `<br><small>Report ID: ${report.report_id}</small>` : ''}
                    ${report.amount ? `<br><small>Amount: $${report.amount.toFixed(2)}</small>` : ''}
                    ${report.error ? `<br><small class="text-danger">Error: ${report.error}</small>` : ''}
                </div>
                <div>
                    <span class="badge bg-${badgeClass}">${badgeText}</span>
                </div>
            </div>
        `;
    }

    updateSubmissionSteps(success) {
        const step3 = document.getElementById('step-3');
        const step3Indicator = step3?.querySelector('.step-indicator');
        const step4 = document.getElementById('step-4');
        const step4Indicator = step4?.querySelector('.step-indicator');

        if (step3 && step3Indicator) {
            step3.classList.add('completed');
            step3Indicator.classList.add('completed');
            step3Indicator.innerHTML = '<i class="fas fa-check"></i>';
        }

        if (step4 && step4Indicator && success) {
            step4.classList.add('completed');
            step4Indicator.classList.add('completed');
            step4Indicator.innerHTML = '<i class="fas fa-check"></i>';
        }
    }

    // Progress Modal Management
    showProgressModal() {
        const modal = document.getElementById('progressModal');
        if (modal) {
            const bsModal = new bootstrap.Modal(modal, { backdrop: 'static', keyboard: false });
            bsModal.show();
        }
    }

    hideProgressModal() {
        const modal = document.getElementById('progressModal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        }
    }

    updateProgressModal(progress, message) {
        const progressBar = document.getElementById('modal-progress-bar');
        const progressText = document.getElementById('modal-progress-text');
        
        if (progressBar) {
            progressBar.style.width = `${Math.min(progress, 100)}%`;
            progressBar.setAttribute('aria-valuenow', progress);
        }
        
        if (progressText) {
            progressText.textContent = message;
        }
    }

    // Connection Testing
    async testConcurConnection() {
        const indicator = document.getElementById('connection-indicator');
        const message = document.getElementById('connection-message');
        
        if (indicator) {
            indicator.className = 'fas fa-spinner fa-spin text-primary';
        }
        if (message) {
            message.textContent = 'Testing connection...';
        }

        try {
            const response = await fetch('/api/test-concur-connection', { method: 'POST' });
            const data = await response.json();

            if (data.status === 'success') {
                if (indicator) indicator.className = 'fas fa-circle text-success';
                if (message) message.textContent = `Connected as: ${data.user}`;
            } else {
                if (indicator) indicator.className = 'fas fa-circle text-danger';
                if (message) message.textContent = `Connection failed: ${data.message}`;
            }
        } catch (error) {
            if (indicator) indicator.className = 'fas fa-circle text-danger';
            if (message) message.textContent = 'Connection test failed';
        }
    }

    // Utility Methods
    async attemptAutoFix() {
        try {
            this.showLoading('Attempting to fix validation issues...');
            
            const response = await fetch('/api/auto-fix-validation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trip_ids: this.selectedTrips })
            });

            const result = await response.json();
            
            if (result.fixes_applied > 0) {
                this.showSuccess(`Applied ${result.fixes_applied} automatic fixes. Please review and try again.`);
                await this.validateSelectedTrips();
            } else {
                this.showInfo('No automatic fixes could be applied. Please resolve issues manually.');
            }
        } catch (error) {
            this.showError(`Auto-fix failed: ${error.message}`);
        } finally {
            this.hideLoading();
        }
    }

    clearSelection() {
        this.selectedTrips = [];
        this.updateSelectionSummary();
        this.clearValidation();
        
        // Reset step indicators
        const steps = ['step-1', 'step-2', 'step-3', 'step-4'];
        steps.forEach((stepId, index) => {
            const step = document.getElementById(stepId);
            const indicator = step?.querySelector('.step-indicator');
            
            if (step && indicator) {
                step.className = 'submission-step p-3 h-100';
                indicator.className = 'step-indicator';
                indicator.textContent = index + 1;
                
                if (index === 0) {
                    step.classList.add('active');
                    indicator.classList.add('active');
                }
            }
        });
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric'
        });
    }

    // Notification Methods
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
        toast.className = 'toast position-fixed top-0 end-0 m-3';
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
        // Implementation similar to receiptManager
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
        overlay.style.cssText = `
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
        `;
        
        overlay.innerHTML = `
            <div style="text-align: center; color: white; background: rgba(0, 0, 0, 0.8); padding: 2rem; border-radius: 0.5rem;">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <div class="loading-message">Loading...</div>
            </div>
        `;
        
        document.body.appendChild(overlay);
        return overlay;
    }
}

// Global instance
let concurManager;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    concurManager = new ConcurManager();
    
    // Test connection on page load
    concurManager.testConcurConnection();
});

// Global functions for template compatibility
function toggleTripSelection(tripId) {
    concurManager.toggleTripSelection(tripId);
}

function selectAllTrips() {
    concurManager.selectAllTrips();
}

function clearAllSelections() {
    concurManager.clearAllSelections();
}

function testConcurConnection() {
    concurManager.testConcurConnection();
}

function refreshConnection() {
    concurManager.testConcurConnection();
}

function submitAllReady() {
    concurManager.selectAllReadyTrips();
    concurManager.startSubmissionFlow();
}

function createConcurReports() {
    concurManager.createConcurReports();
}

function fixIssuesAutomatically() {
    concurManager.attemptAutoFix();
}

function proceedWithWarnings() {
    concurManager.startSubmissionFlow();
}

function cancelSubmission() {
    concurManager.clearSelection();
}

function exportForManualEntry() {
    const tripIds = concurManager.selectedTrips.join(',');
    window.open(`/api/export-concur-data?trip_ids=${tripIds}`, '_blank');
}

function saveAsDraft() {
    concurManager.showInfo('Draft save feature coming soon!');
}

function viewInConcur() {
    window.open('https://www.concursolutions.com', '_blank');
}

function downloadSubmissionReport() {
    window.location.href = '/api/export-submission-report';
}

function createNewSubmission() {
    concurManager.clearSelection();
    concurManager.clearValidation();
    
    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function viewSubmission(submissionId) {
    concurManager.showInfo(`Viewing submission details: ${submissionId}`);
}