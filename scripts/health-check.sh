#!/bin/bash

# ============================================================================
# Health Check Script - Financial Agent
# ============================================================================
# Checks health of all services
# ============================================================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║           Financial Agent - Health Check Report               ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# Check Docker
# ============================================================================
log_info "Checking Docker..."
if docker info > /dev/null 2>&1; then
    log_success "Docker is running"
else
    log_error "Docker is not running!"
    exit 1
fi

# ============================================================================
# Check Containers
# ============================================================================
echo ""
log_info "Checking containers..."

CONTAINERS=("financial-agent-postgres" "financial-agent-redis" "financial-agent-qdrant" "financial-agent-ollama" "financial-agent-backend" "financial-agent-nginx")

for container in "${CONTAINERS[@]}"; do
    if docker ps | grep -q "$container"; then
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "running")
        if [ "$STATUS" = "healthy" ] || [ "$STATUS" = "running" ]; then
            log_success "$container - $STATUS"
        else
            log_warning "$container - $STATUS"
        fi
    else
        log_error "$container - NOT RUNNING"
    fi
done

# ============================================================================
# Check Endpoints
# ============================================================================
echo ""
log_info "Checking API endpoints..."

# Health endpoint
if curl -s -f http://localhost/api/v1/health > /dev/null 2>&1; then
    log_success "Health endpoint: http://localhost/api/v1/health"
else
    log_error "Health endpoint: FAILED"
fi

# Liveness
if curl -s -f http://localhost/api/v1/health/live > /dev/null 2>&1; then
    log_success "Liveness probe: OK"
else
    log_error "Liveness probe: FAILED"
fi

# Readiness
if curl -s -f http://localhost/api/v1/health/ready > /dev/null 2>&1; then
    log_success "Readiness probe: OK"
else
    log_warning "Readiness probe: NOT READY"
fi

# ============================================================================
# Check Database
# ============================================================================
echo ""
log_info "Checking PostgreSQL..."

DB_CONNECTIONS=$(docker exec financial-agent-postgres psql -U financial_agent_user -d financial_agent -tAc "SELECT count(*) FROM pg_stat_activity WHERE datname='financial_agent';" 2>/dev/null || echo "0")
DB_SIZE=$(docker exec financial-agent-postgres psql -U financial_agent_user -d financial_agent -tAc "SELECT pg_size_pretty(pg_database_size('financial_agent'));" 2>/dev/null || echo "unknown")
USER_COUNT=$(docker exec financial-agent-postgres psql -U financial_agent_user -d financial_agent -tAc "SELECT COUNT(*) FROM users;" 2>/dev/null || echo "0")

log_info "Database size: ${DB_SIZE}"
log_info "Active connections: ${DB_CONNECTIONS}"
log_info "Total users: ${USER_COUNT}"

# ============================================================================
# Check Qdrant
# ============================================================================
echo ""
log_info "Checking Qdrant..."

QDRANT_RESPONSE=$(curl -s http://localhost:6333/collections/artigos_glpi 2>/dev/null || echo "{}")
VECTOR_COUNT=$(echo "$QDRANT_RESPONSE" | grep -o '"vectors_count":[0-9]*' | cut -d: -f2 || echo "0")

if [ "$VECTOR_COUNT" != "0" ]; then
    log_info "Vectors indexed: ${VECTOR_COUNT}"
else
    log_warning "No vectors indexed in collection 'artigos_glpi'"
fi

# ============================================================================
# Check Redis
# ============================================================================
echo ""
log_info "Checking Redis..."

REDIS_KEYS=$(docker exec financial-agent-redis redis-cli DBSIZE 2>/dev/null | grep -o '[0-9]*' || echo "0")
REDIS_MEM=$(docker exec financial-agent-redis redis-cli INFO memory 2>/dev/null | grep "used_memory_human" | cut -d: -f2 | tr -d '\r' || echo "unknown")

log_info "Cached keys: ${REDIS_KEYS}"
log_info "Memory used: ${REDIS_MEM}"

# ============================================================================
# Check Ollama
# ============================================================================
echo ""
log_info "Checking Ollama..."

if docker exec financial-agent-ollama ollama list 2>/dev/null | grep -q "qwen2.5:3b"; then
    log_success "Model qwen2.5:3b is loaded"
else
    log_warning "Model qwen2.5:3b not found"
fi

# ============================================================================
# Resource Usage
# ============================================================================
echo ""
log_info "Resource usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep financial-agent

# ============================================================================
# Summary
# ============================================================================
echo ""
log_info "System access:"
log_info "  - Main app: http://192.168.1.150"
log_info "  - Health: http://192.168.1.150/api/v1/health"
log_info "  - Qdrant UI: http://192.168.1.150:6333/dashboard (if exposed)"
echo ""
