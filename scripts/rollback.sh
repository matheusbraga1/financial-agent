#!/bin/bash
# ============================================================================
# Rollback Script
# Reverts to previous deployment from backup
# ============================================================================

set -e

BACKUP_DIR="$HOME/backups"
PROJECT_DIR="/opt/financial-agent/financial-agent"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "============================================================================"
echo "Rollback - Financial Agent"
echo "============================================================================"

# ============================================================================
# Find latest backup
# ============================================================================
echo ""
echo "🔍 Finding latest backup..."

LATEST_BACKUP=$(ls -t "$BACKUP_DIR" | head -n 1)

if [ -z "$LATEST_BACKUP" ]; then
    echo -e "${RED}❌ No backups found in $BACKUP_DIR${NC}"
    exit 1
fi

BACKUP_PATH="${BACKUP_DIR}/${LATEST_BACKUP}"
echo "📦 Latest backup: $BACKUP_PATH"

# Show backup metadata
if [ -f "${BACKUP_PATH}/metadata.json" ]; then
    echo ""
    echo "Backup Information:"
    cat "${BACKUP_PATH}/metadata.json" | jq '.'
fi

# ============================================================================
# Confirm rollback
# ============================================================================
echo ""
echo -e "${YELLOW}⚠️  WARNING: This will rollback to the previous deployment${NC}"
echo "Backup: $LATEST_BACKUP"
echo ""

# In CI/CD, auto-confirm. In manual mode, ask for confirmation
if [ -z "$CI" ]; then
    read -p "Continue with rollback? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Rollback cancelled"
        exit 0
    fi
fi

# ============================================================================
# Stop current containers
# ============================================================================
echo ""
echo "🛑 Stopping current deployment..."

cd "$PROJECT_DIR"
docker compose -f docker-compose.prod.yml down

echo "✅ Current deployment stopped"

# ============================================================================
# Restore backup files
# ============================================================================
echo ""
echo "📥 Restoring files from backup..."

# Restore docker-compose
if [ -f "${BACKUP_PATH}/docker-compose.prod.yml" ]; then
    cp "${BACKUP_PATH}/docker-compose.prod.yml" "$PROJECT_DIR/"
    echo "✅ Restored docker-compose.prod.yml"
fi

# Restore environment
if [ -f "${BACKUP_PATH}/.env" ]; then
    cp "${BACKUP_PATH}/.env" "$PROJECT_DIR/"
    echo "✅ Restored .env"
fi

# ============================================================================
# Restore previous images
# ============================================================================
echo ""
echo "🔄 Restoring previous Docker images..."

# Read previous image tags from backup
if [ -f "${BACKUP_PATH}/images.txt" ]; then
    echo "Previous images:"
    cat "${BACKUP_PATH}/images.txt"
else
    echo "⚠️  No image information in backup, using :latest tags"
fi

# ============================================================================
# Start previous deployment
# ============================================================================
echo ""
echo "🚀 Starting previous deployment..."

docker compose -f docker-compose.prod.yml --env-file .env.production up -d

echo "✅ Previous deployment started"

# ============================================================================
# Wait for services
# ============================================================================
echo ""
echo "⏳ Waiting for services to be healthy..."

sleep 15

# ============================================================================
# Verify rollback
# ============================================================================
echo ""
echo "🔍 Verifying rollback..."

# Check if health endpoint responds
MAX_WAIT=60
WAIT_COUNT=0

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if curl -sf http://localhost/api/v1/health/ready > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Rollback successful!${NC}"
        echo ""
        echo "============================================================================"
        echo "Rollback Summary"
        echo "============================================================================"
        echo "Restored from: $LATEST_BACKUP"
        echo "Rollback time: $(date)"
        echo "============================================================================"
        exit 0
    fi

    WAIT_COUNT=$((WAIT_COUNT + 5))
    echo "   Waiting... (${WAIT_COUNT}s / ${MAX_WAIT}s)"
    sleep 5
done

echo -e "${RED}❌ Rollback verification failed${NC}"
echo "Services did not become healthy within ${MAX_WAIT} seconds"
exit 1
