#!/bin/bash

# ============================================================================
# Deploy Script - Financial Agent
# ============================================================================
# Usage: ./scripts/deploy.sh
# ============================================================================

set -e  # Exit on error

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

# ============================================================================
# Pre-flight Checks
# ============================================================================
log_info "Starting deployment pre-flight checks..."

# Check if .env.production exists
if [ ! -f .env.production ]; then
    log_error ".env.production not found!"
    log_info "Copy .env to .env.production and adjust for production"
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    log_error "Docker is not running!"
    exit 1
fi

log_success "Pre-flight checks passed!"

# ============================================================================
# Backup Current State (if running)
# ============================================================================
log_info "Checking if services are already running..."

if docker compose -f docker-compose.prod.yml ps | grep -q "Up"; then
    log_warning "Services are currently running"
    read -p "Do you want to backup data before deploying? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Creating backup..."
        ./scripts/backup.sh || log_warning "Backup failed, continuing anyway..."
    fi
fi

# ============================================================================
# Pull Latest Code (if using git)
# ============================================================================
if [ -d .git ]; then
    log_info "Git repository detected"
    read -p "Pull latest changes from git? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Pulling latest changes..."
        git pull
        log_success "Code updated!"
    fi
fi

# ============================================================================
# Build Images
# ============================================================================
log_info "Building Docker images..."
docker compose -f docker-compose.prod.yml build --no-cache
log_success "Images built successfully!"

# ============================================================================
# Deploy Services
# ============================================================================
log_info "Deploying services..."

# Stop current services gracefully
log_info "Stopping current services..."
docker compose -f docker-compose.prod.yml down

# Start infrastructure services first
log_info "Starting infrastructure services (postgres, redis, qdrant)..."
docker compose -f docker-compose.prod.yml up -d postgres redis qdrant

# Wait for health checks
log_info "Waiting for infrastructure services to be healthy..."
sleep 30

# Check health
for service in postgres redis qdrant; do
    if docker compose -f docker-compose.prod.yml ps | grep $service | grep -q "healthy"; then
        log_success "$service is healthy"
    else
        log_warning "$service might not be fully ready yet"
    fi
done

# Start Ollama
log_info "Starting Ollama..."
docker compose -f docker-compose.prod.yml up -d ollama
sleep 20

# Check if model exists
log_info "Checking Ollama model..."
if ! docker exec financial-agent-ollama ollama list | grep -q "qwen2.5:3b"; then
    log_warning "Model qwen2.5:3b not found! Downloading..."
    docker exec financial-agent-ollama ollama pull qwen2.5:3b
    log_success "Model downloaded!"
else
    log_success "Model already exists"
fi

# Start backend
log_info "Starting backend application..."
docker compose -f docker-compose.prod.yml up -d backend
sleep 30

# Start nginx
log_info "Starting Nginx reverse proxy..."
docker compose -f docker-compose.prod.yml up -d nginx

# ============================================================================
# Health Check
# ============================================================================
log_info "Running health checks..."
sleep 10

# Check if all services are up
log_info "Service status:"
docker compose -f docker-compose.prod.yml ps

# Test health endpoint
log_info "Testing health endpoint..."
if curl -f http://localhost/api/v1/health > /dev/null 2>&1; then
    log_success "✓ Application is healthy!"
else
    log_error "✗ Health check failed!"
    log_info "Check logs: docker compose -f docker-compose.prod.yml logs backend"
    exit 1
fi

# ============================================================================
# Success
# ============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                DEPLOYMENT SUCCESSFUL! 🎉                       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
log_info "Application is running at: http://192.168.1.150"
log_info "Health check: http://192.168.1.150/api/v1/health"
echo ""
log_info "Useful commands:"
log_info "  - View logs: docker compose -f docker-compose.prod.yml logs -f"
log_info "  - Restart: docker compose -f docker-compose.prod.yml restart backend"
log_info "  - Stop: docker compose -f docker-compose.prod.yml down"
echo ""
