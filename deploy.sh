#!/bin/bash

# Travel Expense Analyzer - Deployment Script
# This script helps deploy the application in various environments

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    log_info "Checking dependencies..."
    
    # Check Python
    if command -v python3 &> /dev/null; then
        log_success "Python 3 found: $(python3 --version)"
    else
        log_error "Python 3 not found. Please install Python 3.8 or higher."
        exit 1
    fi
    
    # Check pip
    if command -v pip3 &> /dev/null; then
        log_success "pip3 found"
    else
        log_error "pip3 not found. Please install pip."
        exit 1
    fi
    
    # Check Docker (optional)
    if command -v docker &> /dev/null; then
        log_success "Docker found: $(docker --version)"
        DOCKER_AVAILABLE=true
    else
        log_warning "Docker not found. Docker deployment will not be available."
        DOCKER_AVAILABLE=false
    fi
}

install_python_deps() {
    log_info "Installing Python dependencies..."
    pip3 install -r requirements.txt
    log_success "Python dependencies installed"
}

setup_environment() {
    log_info "Setting up environment..."
    
    # Create .env file if it doesn't exist
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            cp .env.example .env
            log_warning ".env file created from template. Please edit it with your API credentials."
        else
            log_error ".env.example not found. Cannot create .env file."
            exit 1
        fi
    else
        log_success ".env file already exists"
    fi
    
    # Create required directories
    mkdir -p data uploads static/css static/js templates
    log_success "Required directories created"
}

deploy_development() {
    log_info "Deploying in development mode..."
    
    check_dependencies
    install_python_deps
    setup_environment
    
    log_success "Development deployment complete!"
    log_info "To start the application, run: python run_web_app.py"
    log_info "Access the application at: http://localhost:5000"
}

deploy_production() {
    log_info "Deploying in production mode..."
    
    check_dependencies
    install_python_deps
    setup_environment
    
    # Set production environment
    export FLASK_ENV=production
    
    log_success "Production deployment complete!"
    log_info "To start the application, run: FLASK_ENV=production python run_web_app.py"
    log_info "Or use the Docker deployment for better production setup."
}

deploy_docker() {
    if [ "$DOCKER_AVAILABLE" = false ]; then
        log_error "Docker is not available. Please install Docker first."
        exit 1
    fi
    
    log_info "Deploying with Docker..."
    
    setup_environment
    
    # Check if docker-compose is available
    if command -v docker-compose &> /dev/null; then
        log_info "Using Docker Compose..."
        docker-compose up -d
        log_success "Docker deployment complete!"
        log_info "Application is running at: http://localhost:5000"
        log_info "To view logs: docker-compose logs -f"
        log_info "To stop: docker-compose down"
    else
        log_info "Using Docker directly..."
        docker build -t expense-analyzer .
        docker run -d -p 5000:5000 \
            -v "$(pwd)/.env:/app/.env" \
            -v "$(pwd)/data:/app/data" \
            -v "$(pwd)/uploads:/app/uploads" \
            --name expense-analyzer \
            expense-analyzer
        log_success "Docker deployment complete!"
        log_info "Application is running at: http://localhost:5000"
        log_info "To view logs: docker logs -f expense-analyzer"
        log_info "To stop: docker stop expense-analyzer"
    fi
}

cleanup() {
    log_info "Cleaning up previous deployments..."
    
    # Stop and remove Docker containers
    if [ "$DOCKER_AVAILABLE" = true ]; then
        if command -v docker-compose &> /dev/null; then
            docker-compose down 2>/dev/null || true
        fi
        docker stop expense-analyzer 2>/dev/null || true
        docker rm expense-analyzer 2>/dev/null || true
    fi
    
    log_success "Cleanup complete"
}

show_help() {
    echo "Travel Expense Analyzer - Deployment Script"
    echo ""
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  dev        Deploy in development mode"
    echo "  prod       Deploy in production mode"
    echo "  docker     Deploy using Docker"
    echo "  cleanup    Clean up previous deployments"
    echo "  help       Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 dev           # Development deployment"
    echo "  $0 docker        # Docker deployment"
    echo "  $0 cleanup       # Clean up containers"
    echo ""
}

# Main script
main() {
    case "$1" in
        "dev"|"development")
            deploy_development
            ;;
        "prod"|"production")
            deploy_production
            ;;
        "docker")
            deploy_docker
            ;;
        "cleanup")
            cleanup
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            log_error "Invalid option: $1"
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"