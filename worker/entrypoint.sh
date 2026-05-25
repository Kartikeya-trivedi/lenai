#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════╗"
echo "║  LenAI Celery Worker — Starting up...        ║"
echo "╚══════════════════════════════════════════════╝"

# Wait for Redis to be ready
echo "⏳ Waiting for Redis..."
for i in $(seq 1 30); do
    if python -c "
import redis, sys, os
try:
    r = redis.from_url(os.environ.get('REDIS_URL', 'redis://redis:6379/0'))
    r.ping()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo "✅ Redis is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Redis not ready after 30 attempts, proceeding anyway..."
    fi
    sleep 2
done

# Wait for API to be healthy (ensures DB is migrated)
echo "⏳ Waiting for API service..."
for i in $(seq 1 60); do
    if curl -sf http://api:8000/health > /dev/null 2>&1; then
        echo "✅ API is healthy"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "⚠️  API not healthy after 60 attempts, starting worker anyway..."
    fi
    sleep 3
done

# Start Celery worker
echo "🚀 Starting Celery worker..."
exec celery -A app.workers.celery_app worker \
    --loglevel="${LOG_LEVEL:-info}" \
    --concurrency="${CELERY_CONCURRENCY:-2}" \
    -Q image,voice,webhook,cleanup \
    --without-gossip \
    --without-mingle \
    --without-heartbeat \
    -n "worker@%h"
