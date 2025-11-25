#!/bin/bash

# ============================================================================
# Backup Script - Financial Agent
# ============================================================================
# Backs up:
# - PostgreSQL database
# - Qdrant vector store
# - Redis data
# - Configuration files
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
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Configuration
BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_NAME="backup_${TIMESTAMP}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

# Retention (days)
RETENTION_DAYS=30

# ============================================================================
# Create backup directory
# ============================================================================
log_info "Creating backup directory: ${BACKUP_PATH}"
mkdir -p "${BACKUP_PATH}"

# ============================================================================
# Backup PostgreSQL
# ============================================================================
log_info "Backing up PostgreSQL database..."

docker exec financial-agent-postgres pg_dump \
    -U financial_agent_user \
    -d financial_agent \
    --format=custom \
    --compress=9 \
    > "${BACKUP_PATH}/postgres_financial_agent.dump"

log_success "PostgreSQL backup completed: $(du -h "${BACKUP_PATH}/postgres_financial_agent.dump" | cut -f1)"

# ============================================================================
# Backup Qdrant
# ============================================================================
log_info "Backing up Qdrant vector store..."

# Create snapshot via API
docker exec financial-agent-qdrant sh -c \
    'curl -X POST "http://localhost:6333/collections/artigos_glpi/snapshots"' \
    > /dev/null 2>&1 || log_warning "Qdrant snapshot creation might have failed"

# Copy Qdrant data
docker run --rm \
    -v financial-agent-qdrant-data:/data:ro \
    -v "$(pwd)/${BACKUP_PATH}":/backup \
    alpine tar czf /backup/qdrant_data.tar.gz -C /data .

log_success "Qdrant backup completed: $(du -h "${BACKUP_PATH}/qdrant_data.tar.gz" | cut -f1)"

# ============================================================================
# Backup Redis (optional - can be regenerated)
# ============================================================================
log_info "Backing up Redis data..."

docker exec financial-agent-redis redis-cli SAVE > /dev/null 2>&1 || true

docker run --rm \
    -v financial-agent-redis-data:/data:ro \
    -v "$(pwd)/${BACKUP_PATH}":/backup \
    alpine tar czf /backup/redis_data.tar.gz -C /data .

log_success "Redis backup completed: $(du -h "${BACKUP_PATH}/redis_data.tar.gz" | cut -f1)"

# ============================================================================
# Backup Configuration Files
# ============================================================================
log_info "Backing up configuration files..."

mkdir -p "${BACKUP_PATH}/config"
cp .env.production "${BACKUP_PATH}/config/" 2>/dev/null || log_warning ".env.production not found"
cp docker-compose.prod.yml "${BACKUP_PATH}/config/" 2>/dev/null || true
cp nginx/nginx.conf "${BACKUP_PATH}/config/" 2>/dev/null || true

log_success "Configuration files backed up"

# ============================================================================
# Create metadata file
# ============================================================================
log_info "Creating backup metadata..."

cat > "${BACKUP_PATH}/metadata.json" <<EOF
{
    "timestamp": "${TIMESTAMP}",
    "date": "$(date)",
    "hostname": "$(hostname)",
    "services": {
        "postgres": "$(docker exec financial-agent-postgres psql -U financial_agent_user -d financial_agent -tAc 'SELECT version();' 2>/dev/null | head -n1)",
        "backend": "$(docker exec financial-agent-backend python -c 'import app; print(app.main.settings.app_version)' 2>/dev/null || echo 'unknown')"
    },
    "sizes": {
        "postgres": "$(du -h "${BACKUP_PATH}/postgres_financial_agent.dump" | cut -f1)",
        "qdrant": "$(du -h "${BACKUP_PATH}/qdrant_data.tar.gz" | cut -f1)",
        "redis": "$(du -h "${BACKUP_PATH}/redis_data.tar.gz" | cut -f1)",
        "total": "$(du -sh "${BACKUP_PATH}" | cut -f1)"
    }
}
EOF

log_success "Metadata created"

# ============================================================================
# Cleanup old backups
# ============================================================================
log_info "Cleaning up backups older than ${RETENTION_DAYS} days..."

find "${BACKUP_DIR}" -maxdepth 1 -name "backup_*" -type d -mtime +${RETENTION_DAYS} -exec rm -rf {} \; 2>/dev/null || true

# ============================================================================
# Success
# ============================================================================
TOTAL_SIZE=$(du -sh "${BACKUP_PATH}" | cut -f1)

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              BACKUP COMPLETED SUCCESSFULLY! ✓                  ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
log_info "Backup location: ${BACKUP_PATH}"
log_info "Total size: ${TOTAL_SIZE}"
log_info "To restore this backup: ./scripts/restore.sh ${BACKUP_NAME}"
echo ""

# List backups
log_info "Available backups:"
ls -lht "${BACKUP_DIR}" | grep "^d" | head -n 5
echo ""
