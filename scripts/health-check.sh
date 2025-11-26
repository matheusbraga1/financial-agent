#!/bin/bash
# ============================================================================
# Health Check Script
# Validates all services are running correctly
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAILED_CHECKS=0

echo "============================================================================"
echo "Health Check - Financial Agent"
echo "============================================================================"

# ============================================================================
# Check 1: Docker containers
# ============================================================================
echo ""
echo "🐳 Checking Docker containers..."

REQUIRED_CONTAINERS=(
    "financial-agent-backend"
    "financial-agent-nginx"
    "financial-agent-postgres"
    "financial-agent-redis"
    "financial-agent-qdrant"
)

for container in "${REQUIRED_CONTAINERS[@]}"; do
    # Find container by pattern (handles dynamic names like backend-1, backend-2, etc.)
    ACTUAL_CONTAINER=$(docker ps --format '{{.Names}}' | grep "^${container}" | head -n 1)

    if [ -n "$ACTUAL_CONTAINER" ]; then
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$ACTUAL_CONTAINER" 2>/dev/null || echo "running")
        if [ "$STATUS" = "healthy" ] || [ "$STATUS" = "running" ]; then
            echo -e "   ${GREEN}✅${NC} $container is ${STATUS}"
        else
            echo -e "   ${RED}❌${NC} $container status: ${STATUS}"
            FAILED_CHECKS=$((FAILED_CHECKS + 1))
        fi
    else
        echo -e "   ${RED}❌${NC} $container is not running"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
done

# ============================================================================
# Check 2: API Health endpoints
# ============================================================================
echo ""
echo "🏥 Checking API endpoints..."

# Health endpoint
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" http://localhost/api/v1/health/ready 2>/dev/null || echo "000")
HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -n1)
BODY=$(echo "$HEALTH_RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "   ${GREEN}✅${NC} /api/v1/health/ready (HTTP $HTTP_CODE)"
else
    echo -e "   ${RED}❌${NC} /api/v1/health/ready (HTTP $HTTP_CODE)"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# Live endpoint
LIVE_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/api/v1/health/live 2>/dev/null || echo "000")
if [ "$LIVE_CODE" = "200" ]; then
    echo -e "   ${GREEN}✅${NC} /api/v1/health/live (HTTP $LIVE_CODE)"
else
    echo -e "   ${RED}❌${NC} /api/v1/health/live (HTTP $LIVE_CODE)"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# ============================================================================
# Check 3: Database connectivity
# ============================================================================
echo ""
echo "🗄️  Checking databases..."

# PostgreSQL
POSTGRES_CONTAINER=$(docker ps --format '{{.Names}}' | grep "^financial-agent-postgres" | head -n 1)
if [ -n "$POSTGRES_CONTAINER" ] && docker exec "$POSTGRES_CONTAINER" pg_isready -U postgres > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅${NC} PostgreSQL is ready"
else
    echo -e "   ${RED}❌${NC} PostgreSQL is not ready"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# Redis
REDIS_CONTAINER=$(docker ps --format '{{.Names}}' | grep "^financial-agent-redis" | head -n 1)
if [ -n "$REDIS_CONTAINER" ] && docker exec "$REDIS_CONTAINER" redis-cli ping > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅${NC} Redis is responding"
else
    echo -e "   ${RED}❌${NC} Redis is not responding"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# ============================================================================
# Check 4: Qdrant vector database
# ============================================================================
echo ""
echo "🔍 Checking Qdrant..."

QDRANT_RESPONSE=$(curl -s http://localhost:6333/collections 2>/dev/null || echo "{}")
if echo "$QDRANT_RESPONSE" | grep -q "artigos_glpi"; then
    VECTOR_COUNT=$(echo "$QDRANT_RESPONSE" | jq -r '.result.collections[] | select(.name=="artigos_glpi") | .vectors_count' 2>/dev/null || echo "unknown")
    echo -e "   ${GREEN}✅${NC} Qdrant collection 'artigos_glpi' exists ($VECTOR_COUNT vectors)"
else
    echo -e "   ${RED}❌${NC} Qdrant collection 'artigos_glpi' not found"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# ============================================================================
# Check 5: Disk space
# ============================================================================
echo ""
echo "💾 Checking disk space..."

DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 90 ]; then
    echo -e "   ${GREEN}✅${NC} Disk usage: ${DISK_USAGE}%"
else
    echo -e "   ${YELLOW}⚠️${NC}  Disk usage: ${DISK_USAGE}% (high)"
fi

# ============================================================================
# Check 6: Memory usage
# ============================================================================
echo ""
echo "🧠 Checking memory..."

MEMORY_USAGE=$(free | awk 'NR==2 {printf "%.0f", $3/$2 * 100}')
if [ "$MEMORY_USAGE" -lt 90 ]; then
    echo -e "   ${GREEN}✅${NC} Memory usage: ${MEMORY_USAGE}%"
else
    echo -e "   ${YELLOW}⚠️${NC}  Memory usage: ${MEMORY_USAGE}% (high)"
fi

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "============================================================================"
if [ $FAILED_CHECKS -eq 0 ]; then
    echo -e "${GREEN}✅ All health checks passed!${NC}"
    echo "============================================================================"
    exit 0
else
    echo -e "${RED}❌ $FAILED_CHECKS health check(s) failed${NC}"
    echo "============================================================================"
    exit 1
fi
