#!/bin/bash
# ============================================================================
# GitHub Actions Runner Verification Script
# ============================================================================

set -e

RUNNER_DIR="/opt/actions-runner"
RUNNER_USER="github-runner"

echo "============================================================================"
echo "GitHub Actions Runner - Verification"
echo "============================================================================"
echo ""

# Check if runner directory exists
if [ -d "$RUNNER_DIR" ]; then
    echo "✅ Runner directory exists: $RUNNER_DIR"
else
    echo "❌ Runner directory not found: $RUNNER_DIR"
    exit 1
fi

# Check if runner user exists
if id "$RUNNER_USER" &>/dev/null; then
    echo "✅ Runner user exists: $RUNNER_USER"
else
    echo "❌ Runner user not found: $RUNNER_USER"
    exit 1
fi

# Check if user is in docker group
if groups $RUNNER_USER | grep -q docker; then
    echo "✅ User is in docker group"
else
    echo "❌ User is NOT in docker group"
fi

# Check if runner is configured
if [ -f "$RUNNER_DIR/.runner" ]; then
    echo "✅ Runner is configured"
    cat "$RUNNER_DIR/.runner" | jq '.'
else
    echo "⚠️  Runner is NOT configured yet"
fi

# Check service status
echo ""
echo "Service Status:"
if systemctl is-active --quiet actions.runner.* 2>/dev/null; then
    systemctl status actions.runner.* --no-pager
    echo "✅ Runner service is active"
else
    echo "⚠️  Runner service is not active or not installed"
fi

# Check runner logs
echo ""
echo "Recent Runner Logs:"
if [ -f "$RUNNER_DIR/_diag/Runner_*.log" ]; then
    tail -n 20 $RUNNER_DIR/_diag/Runner_*.log | tail -n 10
else
    echo "⚠️  No logs found yet"
fi

echo ""
echo "============================================================================"
echo "Docker Access Test:"
echo "============================================================================"
sudo -u $RUNNER_USER docker ps &>/dev/null && echo "✅ Runner can access Docker" || echo "❌ Runner CANNOT access Docker"

echo ""
echo "============================================================================"
