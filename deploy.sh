#!/bin/bash
# Deployment script for production server

set -e

echo "🚀 Deploying Beauty Chatbots to Production"
echo "==========================================="

# Configuration
REMOTE_SERVER="root@chat.wax-baby.one"
WAX_BABY_PATH="/root/chatbot"
EUNOIA_PATH="/root/chatbot-eunoia"

# Function to deploy a specific chatbot
deploy_chatbot() {
    local local_file=$1
    local remote_path=$2
    local service_name=$3

    echo "📤 Deploying $service_name..."

    # Backup current version
    ssh $REMOTE_SERVER "cp $remote_path/chatbot_api.py $remote_path/chatbot_api.py.backup.$(date +%Y%m%d_%H%M%S)"

    # Copy new version
    scp $local_file $REMOTE_SERVER:$remote_path/chatbot_api.py

    # Restart service
    ssh $REMOTE_SERVER "systemctl restart $service_name"

    # Check status
    ssh $REMOTE_SERVER "systemctl is-active $service_name" && echo "✅ $service_name deployed successfully" || echo "❌ $service_name deployment failed"
}

# Deploy WAX! Baby
if [ -f "wax-baby-chatbot_api.py" ]; then
    deploy_chatbot "wax-baby-chatbot_api.py" "$WAX_BABY_PATH" "gunicorn-wax"
else
    echo "⚠️  WAX! Baby chatbot file not found"
fi

# Deploy EUNOIA
if [ -f "eunoia/chatbot_api.py" ]; then
    deploy_chatbot "eunoia/chatbot_api.py" "$EUNOIA_PATH" "gunicorn-eunoia"
else
    echo "⚠️  EUNOIA chatbot file not found"
fi

echo ""
echo "🏥 Health Check"
echo "==============="

# Test endpoints
echo "Testing WAX! Baby..."
ssh $REMOTE_SERVER 'curl -s http://localhost:8000/health' && echo " ✅" || echo " ❌"

echo "Testing EUNOIA..."
ssh $REMOTE_SERVER 'curl -s http://localhost:8001/health' && echo " ✅" || echo " ❌"

echo ""
echo "✅ Deployment complete!"
echo "Monitor services: ssh $REMOTE_SERVER 'systemctl status gunicorn-wax gunicorn-eunoia'"