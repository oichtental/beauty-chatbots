#!/bin/bash

echo "🚀 Starting deployment process..."

# Optional: Clear Redis keys if needed
# echo "🧹 Clearing Redis keys..."
# redis-cli DEL chatbot_greeted:guest
# redis-cli DEL chat_history:guest

echo "♻️ Restarting Redis server..."
sudo systemctl restart redis
sleep 2

echo "🔄 Restarting Gunicorn..."
sudo systemctl restart gunicorn
sleep 2

echo "🔄 Restarting PM2 processes (if any)..."
pm2 restart all --update-env
sleep 1

echo "✅ Deployment complete! 🎉"
