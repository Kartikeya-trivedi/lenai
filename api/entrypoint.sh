#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════╗"
echo "║  LenAI API Server — Starting up...           ║"
echo "╚══════════════════════════════════════════════╝"

# Wait for database to be ready
echo "⏳ Waiting for database..."
for i in $(seq 1 30); do
    if python -c "
import asyncio, sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
async def check():
    try:
        engine = create_async_engine('$DATABASE_URL', pool_pre_ping=True)
        async with engine.connect() as conn:
            await conn.execute(text('SELECT 1'))
        await engine.dispose()
        return True
    except Exception:
        return False
result = asyncio.run(check())
sys.exit(0 if result else 1)
" 2>/dev/null; then
        echo "✅ Database is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Database not ready after 30 attempts, proceeding anyway..."
    fi
    sleep 2
done

# Run database migrations
echo "🔄 Running database migrations..."
cd /app
alembic upgrade head || echo "⚠️  Migration failed or already up to date"

# Start uvicorn
echo "🚀 Starting API server on ${API_HOST:-0.0.0.0}:${API_PORT:-8000}..."
exec uvicorn app.main:app \
    --host "${API_HOST:-0.0.0.0}" \
    --port "${API_PORT:-8000}" \
    --workers "${API_WORKERS:-1}" \
    --log-level "${LOG_LEVEL:-info}" \
    --access-log \
    --proxy-headers \
    --forwarded-allow-ips='*'
