#!/bin/bash
# ============================================================================
# GitHub Actions Self-Hosted Runner Setup Script
# Financial Agent - CI/CD Infrastructure
# ============================================================================

set -e

RUNNER_VERSION="2.311.0"
RUNNER_USER="github-runner"
RUNNER_DIR="/opt/actions-runner"

echo "============================================================================"
echo "GitHub Actions Runner Setup - Financial Agent"
echo "============================================================================"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (sudo)"
    exit 1
fi

echo ""
echo "📦 Step 1/6: Installing dependencies..."
dnf install -y curl wget tar git jq

echo ""
echo "👤 Step 2/6: Creating dedicated user for GitHub runner..."
if id "$RUNNER_USER" &>/dev/null; then
    echo "   User $RUNNER_USER already exists"
else
    useradd -m -s /bin/bash $RUNNER_USER
    echo "   User $RUNNER_USER created"
fi

# Add user to docker group
usermod -aG docker $RUNNER_USER
echo "   User added to docker group"

echo ""
echo "📂 Step 3/6: Creating runner directory..."
mkdir -p $RUNNER_DIR
cd $RUNNER_DIR

echo ""
echo "⬇️  Step 4/6: Downloading GitHub Actions Runner v${RUNNER_VERSION}..."
if [ ! -f "actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" ]; then
    curl -o actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz \
        -L https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz
    echo "   Downloaded successfully"
else
    echo "   Already downloaded"
fi

echo ""
echo "📦 Step 5/6: Extracting runner..."
tar xzf ./actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

echo ""
echo "🔐 Step 6/6: Setting permissions..."
chown -R $RUNNER_USER:$RUNNER_USER $RUNNER_DIR

echo ""
echo "✅ Runner installation complete!"
echo ""
echo "============================================================================"
echo "NEXT STEPS - Configure the runner:"
echo "============================================================================"
echo ""
echo "1. Get registration token from GitHub:"
echo "   https://github.com/YOUR_USERNAME/financial-agent/settings/actions/runners/new"
echo ""
echo "2. Switch to runner user and configure:"
echo "   sudo su - github-runner"
echo "   cd /opt/actions-runner"
echo "   ./config.sh --url https://github.com/YOUR_USERNAME/financial-agent --token YOUR_TOKEN"
echo ""
echo "3. Install as service (as root):"
echo "   cd /opt/actions-runner"
echo "   ./svc.sh install github-runner"
echo "   ./svc.sh start"
echo "   ./svc.sh status"
echo ""
echo "4. Verify runner appears in GitHub repo settings"
echo ""
echo "============================================================================"
