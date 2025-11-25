#!/bin/bash

# ============================================================================
# Restore Script - Financial Agent
# ============================================================================
# Usage: ./scripts/restore.sh <backup_name>
# Example: ./scripts/restore.sh backup_2024-11-25_14-30-00
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================================================
# Check arguments
# ============================================================================
if [ -z "$1" ]; then
    log_error "Usage: $0 <backup_name>"
    log_info "Available backups:"
    ls -1 ./backups/ 2>/dev/null | grep "^backup_" || log_warning "No backups found"
    exit 1
fi

BACKUP_NAME="$1"
BACKUP_DIR="./backups"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

# Check if backup exists
if [ ! -d "${BACKUP_PATH}" ]; then
    log_error "Backup not found: ${BACKUP_PATH}"
    log_info "Available backups:"
    ls -1 "${BACKUP_DIR}" 2>/dev/null | grep "^backup_"
    exit 1
fi

# ============================================================================
# Warning
# ============================================================================
echo -e "${RED}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${RED}║                        ⚠️  WARNING ⚠️                           ║${NC}"
echo -e "${RED}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
log_warning "This will OVERWRITE current data with backup from:"
cat "${BACKUP_PATH}/metadata.json" 2>/dev/null | grep "date" || echo "Date: Unknown"
echo ""
read -p "Are you sure you want to continue? (yes/no) " -r
echo
if [[ ! $REPLY =~ ^yes$ ]]; then
    log_info "Restore cancelled"
    exit 0
fi

# ============================================================================
# Stop services
# ============================================================================
log_info "Stopping services..."
docker compose -f docker-compose.prod.yml down

# ============================================================================
# Restore PostgreSQL
# ============================================================================
log_info "Restoring PostgreSQL database..."

# Start only postgres
docker compose -f docker-compose.prod.yml up -d postgres
sleep 10

# Drop and recreate database
docker exec financial-agent-postgres psql -U financial_agent_user -d postgres \
    -c "DROP DATABASE IF EXISTS financial_agent;"

docker exec financial-agent-postgres psql -U financial_agent_user -d postgres \
    -c "CREATE DATABASE financial_agent OWNER financial_agent_user;"

# Restore dump
docker exec -i financial-agent-postgres pg_restore \
    -U financial_agent_user \
    -d financial_agent \
    --no-owner \
    --no-acl \
    < "${BACKUP_PATH}/postgres_financial_agent.dump"

log_success "PostgreSQL restored successfully"

# ============================================================================
# Restore Qdrant
# ============================================================================
log_info "Restoring Qdrant vector store..."

# Stop qdrant if running
docker compose -f docker-compose.prod.yml stop qdrant 2>/dev/null || true

# Remove old data
docker volume rm financial-agent-qdrant-data 2>/dev/null || true
docker volume create financial-agent-qdrant-data

# Restore data
docker run --rm \
    -v financial-agent-qdrant-data:/data \
    -v "$(pwd)/${BACKUP_PATH}":/backup \
    alpine tar xzf /backup/qdrant_data.tar.gz -C /data

log_success "Qdrant restored successfully"

# ============================================================================
# Restore Redis (optional)
# ============================================================================
log_info "Restoring Redis data..."

# Stop redis if running
docker compose -f docker-compose.prod.yml stop redis 2>/dev/null || true

# Remove old data
docker volume rm financial-agent-redis-data 2>/dev/null || true
docker volume create financial-agent-redis-data

# Restore data
docker run --rm \
    -v financial-agent-redis-data:/data \
    -v "$(pwd)/${BACKUP_PATH}":/backup \
    alpine tar xzf /backup/redis_data.tar.gz -C /data

log_success "Redis restored successfully"

# ============================================================================
# Start all services
# ============================================================================
log_info "Starting all services..."
docker compose -f docker-compose.prod.yml up -d

log_info "Waiting for services to be healthy..."
sleep 30

# ============================================================================
# Verify
# ============================================================================
log_info "Verifying restore..."

# Check PostgreSQL
DB_COUNT=$(docker exec financial-agent-postgres psql -U financial_agent_user -d financial_agent -tAc "SELECT COUNT(*) FROM users;" 2>/dev/null || echo "0")
log_info "Users in database: ${DB_COUNT}"

# Check health
if curl -f http://localhost/api/v1/health > /dev/null 2>&1; then
    log_success "Application health check passed"
else
    log_warning "Health check failed - services might still be starting"
fi

# ============================================================================
# Success
# ============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              RESTORE COMPLETED SUCCESSFULLY! ✓                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
log_info "Backup restored from: ${BACKUP_PATH}"
log_info "Application: http://192.168.1.150"
echo ""
