#!/bin/bash
# ============================================================================
# Blue-Green Deployment Script
# Zero-downtime deployment for Financial Agent
# ============================================================================

set -e

# When running in CI, use current directory (GitHub Actions checkout)
# When running manually, use production directory
if [ -z "$CI" ]; then
    PROJECT_DIR="/opt/financial-agent/financial-agent"
    cd "$PROJECT_DIR"
else
    # In CI, create symlink to production .env file
    PROD_ENV="/opt/financial-agent/financial-agent/.env"
    if [ -f "$PROD_ENV" ]; then
        # Docker Compose looks for .env for variable substitution in YAML
        ln -sf "$PROD_ENV" .env
        echo "✅ Linked .env from production directory"
    else
        echo "❌ Production .env not found at $PROD_ENV"
        exit 1
    fi
fi

COMPOSE_FILE="docker-compose.prod.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "============================================================================"
echo "Blue-Green Deployment - Financial Agent"
echo "============================================================================"
echo "Working directory: $(pwd)"

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
             -f nginx/Dockerfile.nginx nginx/

echo "✅ Images built successfully"

# ============================================================================
# Step 2: Start GREEN environment (scale backend to 2)
# ============================================================================
echo ""
echo "🚀 Step 2/7: Starting GREEN environment..."

# Scale backend to 2 instances (BLUE + GREEN running simultaneously)
# Note: First scale starts dependencies (postgres, redis, qdrant, etc)
docker compose -f $COMPOSE_FILE up -d --scale backend=2 backend

echo "✅ GREEN environment started (2 backends running)"

# ============================================================================
# Step 3: Wait for services to be healthy
# ============================================================================
echo ""
echo "⏳ Step 3/7: Waiting for services to be healthy..."

MAX_WAIT=120
WAIT_COUNT=0

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    # Check Docker healthcheck status of backend containers
    HEALTHY_COUNT=$(docker ps --filter "name=financial-agent-backend" --filter "health=healthy" --format "{{.Names}}" | wc -l)

    if [ "$HEALTHY_COUNT" -ge 1 ]; then
        echo "✅ Services are healthy ($HEALTHY_COUNT backends)"
        break
    fi

    WAIT_COUNT=$((WAIT_COUNT + 5))
    echo "   Waiting... (${WAIT_COUNT}s / ${MAX_WAIT}s)"
    sleep 5
done

if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
    echo -e "${RED}❌ Services failed to become healthy${NC}"
    exit 1
fi

# ============================================================================
# Step 4: Run health checks
# ============================================================================
echo ""
echo "🏥 Step 4/7: Running health checks..."

# Get a healthy backend container name
BACKEND_CONTAINER=$(docker ps --filter "name=financial-agent-backend" --filter "health=healthy" --format "{{.Names}}" | head -n 1)

if [ -z "$BACKEND_CONTAINER" ]; then
    echo -e "${RED}❌ No healthy backend container found${NC}"
    exit 1
fi

# Test critical endpoint from inside the container
HEALTH_RESPONSE=$(docker exec "$BACKEND_CONTAINER" curl -s http://localhost:8000/api/v1/health/ready)
if echo "$HEALTH_RESPONSE" | grep -q '"status":"ready"'; then
    echo "✅ Health check passed"
else
    echo -e "${RED}❌ Health check failed${NC}"
    exit 1
fi

# ============================================================================
# Step 5: Switch traffic to GREEN (recreate nginx)
# ============================================================================
echo ""
echo "🔄 Step 5/7: Switching traffic to GREEN environment..."

# Recreate nginx to load balance across both backends
# IMPORTANT: Keep --scale backend=2 to prevent premature scale down
docker compose -f $COMPOSE_FILE up -d --force-recreate --scale backend=2 nginx

echo "✅ Traffic switched to GREEN"

# ============================================================================
# Step 6: Scale down to 1 backend (remove BLUE)
# ============================================================================
echo ""
echo "🔽 Step 6/7: Scaling down to 1 backend..."

sleep 5  # Brief pause to ensure traffic has switched

# Get list of backend containers and remove one
BACKEND_CONTAINERS=$(docker ps --filter "name=financial-agent-backend" --format "{{.Names}}" | sort)
CONTAINER_COUNT=$(echo "$BACKEND_CONTAINERS" | wc -l)

if [ "$CONTAINER_COUNT" -gt 1 ]; then
    # Remove the last container in the list (keeps naming consistent)
    CONTAINER_TO_REMOVE=$(echo "$BACKEND_CONTAINERS" | tail -n 1)
    echo "   Removing: $CONTAINER_TO_REMOVE"
    docker stop "$CONTAINER_TO_REMOVE" > /dev/null 2>&1
    docker rm "$CONTAINER_TO_REMOVE" > /dev/null 2>&1
fi

echo "✅ BLUE environment removed (1 backend running)"

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

# Wait for backend to be healthy and accessible via nginx
MAX_WAIT_FINAL=90
WAIT_COUNT_FINAL=0

while [ $WAIT_COUNT_FINAL -lt $MAX_WAIT_FINAL ]; do
    # Check if backend is healthy
    BACKEND_HEALTHY=$(docker ps --filter "name=financial-agent-backend" --filter "health=healthy" --format "{{.Names}}" | wc -l)

    # Check if nginx is healthy
    NGINX_HEALTHY=$(docker ps --filter "name=financial-agent-nginx" --filter "health=healthy" --format "{{.Names}}" | wc -l)

    if [ "$BACKEND_HEALTHY" -ge 1 ] && [ "$NGINX_HEALTHY" -ge 1 ]; then
        # Both backend and nginx are healthy, now test via nginx
        FINAL_CHECK=$(curl -s http://localhost/api/v1/health/ready)
        if echo "$FINAL_CHECK" | grep -q '"status":"ready"'; then
            echo -e "${GREEN}✅ Deployment successful!${NC}"
            echo ""
            echo "============================================================================"
            echo "Deployment Summary"
            echo "============================================================================"
            echo "Git Commit: $(git rev-parse HEAD 2>/dev/null || echo 'unknown')"
            echo "Image Tag: $NEW_TAG"
            echo "Deployment Time: $(date)"
            echo "============================================================================"
            exit 0
        fi
    fi

    WAIT_COUNT_FINAL=$((WAIT_COUNT_FINAL + 5))
    echo "   Waiting for final verification... (${WAIT_COUNT_FINAL}s / ${MAX_WAIT_FINAL}s) [Backend: $BACKEND_HEALTHY, Nginx: $NGINX_HEALTHY]"
    sleep 5
done

echo -e "${RED}❌ Final verification failed${NC}"
exit 1
