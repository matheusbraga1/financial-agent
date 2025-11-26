#!/bin/bash
# ============================================================================
# Blue-Green Deployment Script
# Zero-downtime deployment for Financial Agent
# ============================================================================

set -e

PROJECT_DIR="/opt/financial-agent/financial-agent"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.production"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "============================================================================"
echo "Blue-Green Deployment - Financial Agent"
echo "============================================================================"

cd "$PROJECT_DIR"

# ============================================================================
# Step 1: Build new images (with new tags)
# ============================================================================
echo ""
echo "🔨 Step 1/7: Building new Docker images..."

# Use GIT_SHA from environment if available (GitHub Actions), otherwise use git
if [ -n "$GIT_SHA" ]; then
    SHORT_SHA="${GIT_SHA:0:7}"
else
    SHORT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
fi

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
NEW_TAG="prod-${SHORT_SHA}-${TIMESTAMP}"

echo "   Building with tag: $NEW_TAG"

# Build backend
docker build -t financial-agent-backend:${NEW_TAG} \
             -t financial-agent-backend:latest \
             -f Dockerfile .

# Build nginx
docker build -t financial-agent-nginx:${NEW_TAG} \
             -t financial-agent-nginx:latest \
             -f nginx/Dockerfile nginx/

echo "✅ Images built successfully"

# ============================================================================
# Step 2: Start new containers (green environment)
# ============================================================================
echo ""
echo "🟢 Step 2/7: Starting GREEN environment..."

# Scale up new containers (they will run alongside old ones temporarily)
docker compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d --no-deps --scale backend=2 backend

echo "✅ GREEN environment started"

# ============================================================================
# Step 3: Wait for new containers to be healthy
# ============================================================================
echo ""
echo "⏳ Step 3/7: Waiting for GREEN environment to be healthy..."

MAX_WAIT=120
WAIT_COUNT=0

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    # Check if new backend is responding
    if curl -sf http://localhost:8000/api/v1/health/ready > /dev/null 2>&1; then
        echo "✅ GREEN environment is healthy"
        break
    fi

    WAIT_COUNT=$((WAIT_COUNT + 5))
    echo "   Waiting... (${WAIT_COUNT}s / ${MAX_WAIT}s)"
    sleep 5
done

if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
    echo -e "${RED}❌ GREEN environment failed to become healthy${NC}"
    echo "   Rolling back..."
    docker compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d --scale backend=1 backend
    exit 1
fi

# ============================================================================
# Step 4: Run health checks on GREEN
# ============================================================================
echo ""
echo "🏥 Step 4/7: Running health checks on GREEN environment..."

# Test critical endpoints
HEALTH_RESPONSE=$(curl -s http://localhost:8000/api/v1/health/ready)
if echo "$HEALTH_RESPONSE" | grep -q '"status":"ready"'; then
    echo "✅ Health check passed"
else
    echo -e "${RED}❌ Health check failed${NC}"
    exit 1
fi

# ============================================================================
# Step 5: Switch traffic to GREEN (update nginx)
# ============================================================================
echo ""
echo "🔄 Step 5/7: Switching traffic to GREEN environment..."

# Recreate nginx to pick up new backend containers
docker compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d --force-recreate nginx

sleep 5
echo "✅ Traffic switched to GREEN"

# ============================================================================
# Step 6: Stop old BLUE containers
# ============================================================================
echo ""
echo "🔵 Step 6/7: Stopping BLUE environment..."

# Scale down to single backend instance (removes old containers)
docker compose -f $COMPOSE_FILE --env-file $ENV_FILE up -d --scale backend=1 backend

echo "✅ BLUE environment stopped"

# ============================================================================
# Step 7: Cleanup old images
# ============================================================================
echo ""
echo "🧹 Step 7/7: Cleaning up old images..."

# Keep only last 3 versions of each image
docker images financial-agent-backend --format "{{.ID}} {{.CreatedAt}}" | \
    awk '{print $1}' | tail -n +4 | xargs -r docker rmi -f 2>/dev/null || true

docker images financial-agent-nginx --format "{{.ID}} {{.CreatedAt}}" | \
    awk '{print $1}' | tail -n +4 | xargs -r docker rmi -f 2>/dev/null || true

# Remove dangling images
docker image prune -f

echo "✅ Cleanup completed"

# ============================================================================
# Final verification
# ============================================================================
echo ""
echo "🔍 Final verification..."

FINAL_CHECK=$(curl -s http://localhost/api/v1/health/ready)
if echo "$FINAL_CHECK" | grep -q '"status":"ready"'; then
    echo -e "${GREEN}✅ Deployment successful!${NC}"
    echo ""
    echo "============================================================================"
    echo "Deployment Summary"
    echo "============================================================================"
    echo "Git Commit: $(git rev-parse HEAD)"
    echo "Image Tag: $NEW_TAG"
    echo "Deployment Time: $(date)"
    echo "============================================================================"
else
    echo -e "${RED}❌ Final verification failed${NC}"
    exit 1
fi
