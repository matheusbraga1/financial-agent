#!/bin/bash
# ============================================================================
# Backup Current Deployment
# Creates a snapshot of the current running deployment for rollback
# ============================================================================

set -e

# When running in CI, use production directory for backup sources
# When running manually, use current directory
if [ -z "$CI" ]; then
    PROD_DIR="."
else
    PROD_DIR="/opt/financial-agent/financial-agent"
fi

BACKUP_DIR="$HOME/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/deployment-${TIMESTAMP}"

echo "============================================================================"
echo "Backup Current Deployment"
echo "============================================================================"

# Create backup directory
mkdir -p "$BACKUP_PATH"

echo "📦 Creating backup at: $BACKUP_PATH"

# Backup docker-compose configuration
if [ -f "${PROD_DIR}/docker-compose.prod.yml" ]; then
    cp "${PROD_DIR}/docker-compose.prod.yml" "${BACKUP_PATH}/"
    echo "✅ Backed up docker-compose.prod.yml"
fi

# Backup environment file
if [ -f "${PROD_DIR}/.env.production" ]; then
    cp "${PROD_DIR}/.env.production" "${BACKUP_PATH}/"
    echo "✅ Backed up .env.production"
fi

# Save current container states
docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}" > "${BACKUP_PATH}/containers.txt"
echo "✅ Saved container states"

# Save current image tags
docker images --format "{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.CreatedAt}}" | grep financial-agent > "${BACKUP_PATH}/images.txt" || true
echo "✅ Saved image information"

# Create metadata file
cat > "${BACKUP_PATH}/metadata.json" <<EOF
{
  "backup_time": "${TIMESTAMP}",
  "git_commit": "${GIT_SHA:-$(git rev-parse HEAD 2>/dev/null || echo 'unknown')}",
  "git_branch": "${GITHUB_REF_NAME:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')}",
  "docker_compose_version": "$(docker compose version --short)",
  "hostname": "$(hostname)"
}
EOF
echo "✅ Created metadata"

# Keep only last 5 backups
echo "🧹 Cleaning old backups (keeping last 5)..."
ls -t "$BACKUP_DIR" | tail -n +6 | xargs -I {} rm -rf "${BACKUP_DIR}/{}" 2>/dev/null || true

echo ""
echo "✅ Backup completed successfully!"
echo "📍 Backup location: $BACKUP_PATH"
echo ""
