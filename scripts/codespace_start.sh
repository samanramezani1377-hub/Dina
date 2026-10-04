#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export DATABASE_URL="postgresql+psycopg://dina:dina_codespace@localhost:5432/dina"
export SECRET_KEY="${SECRET_KEY:-$(python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)}"
export ENVIRONMENT="${ENVIRONMENT:-codespace}"
export JWT_ALGORITHM="${JWT_ALGORITHM:-HS256}"
export JWT_EXPIRE_MINUTES="${JWT_EXPIRE_MINUTES:-60}"

docker compose -f docker-compose.codespaces.yml up -d postgres

echo "Waiting for PostgreSQL..."
for _ in {1..60}; do
  if docker compose -f docker-compose.codespaces.yml exec -T postgres pg_isready -U dina -d dina >/dev/null 2>&1; then break; fi
  sleep 2
done

docker compose -f docker-compose.codespaces.yml exec -T postgres pg_isready -U dina -d dina >/dev/null

echo "Applying Dina migrations..."
for migration in database/migrations/*.sql; do
  echo "  -> $migration"
  PGPASSWORD=dina_codespace psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$migration" >/dev/null
done

python -m pip install -q -r backend/requirements.txt

cat > .env <<EOF
ENVIRONMENT=$ENVIRONMENT
SECRET_KEY=$SECRET_KEY
JWT_ALGORITHM=$JWT_ALGORITHM
JWT_EXPIRE_MINUTES=$JWT_EXPIRE_MINUTES
DATABASE_URL=$DATABASE_URL
EOF

pkill -f "uvicorn src.main:app" >/dev/null 2>&1 || true
nohup python -m uvicorn src.main:app --app-dir backend --host 0.0.0.0 --port 8000 > /tmp/dina-backend.log 2>&1 &

echo "Waiting for Dina API..."
for _ in {1..60}; do
  if curl -fsS http://127.0.0.1:8000/health/ready >/dev/null 2>&1; then
    echo "Dina API is ready on port 8000."
    exit 0
  fi
  sleep 2
done

tail -n 80 /tmp/dina-backend.log
exit 1
