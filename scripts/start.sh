#!/bin/bash
set -e

if [ ! -f .env ]; then
  cp .env.example .env
  # Generate a real secret key so it works out of the box
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i.bak "s/SECRET_KEY=changeme/SECRET_KEY=$SECRET/" .env && rm -f .env.bak
  echo ".env created from .env.example"
else
  # Add any keys present in .env.example that are missing from .env
  while IFS= read -r line; do
    [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
    key="${line%%=*}"
    if ! grep -q "^${key}=" .env; then
      echo "$line" >> .env
      echo "Added missing key to .env: $key"
    fi
  done < .env.example
fi

git config core.hooksPath .githooks

docker compose up --build --wait "$@"

echo "Seeding users..."
docker compose exec backend python seed_users.py

echo "Seeding raw tables (run Airflow DAGs at http://localhost:8080 to ingest)..."
docker compose exec backend python seed_raw.py

echo ""
echo "========================================"
echo "  Databridge is ready"
echo "========================================"
echo ""
echo "  Frontend   http://localhost:5173"
echo "  API docs   http://localhost:8000/docs"
echo "  Airflow    http://localhost:8080  (admin / admin)"
echo "  Mailpit    http://localhost:8025"
echo ""
echo "  Login credentials:"
echo "    admin@databridge.io  /  admin"
echo "    demo@databridge.io   /  demo"
echo ""
echo "  Trigger the Airflow DAGs to populate data:"
echo "    1. ingest_customers"
echo "    2. ingest_products"
echo "    3. ingest_orders"
echo "    4. ingest_warehouse_stock"
echo "    5. compute_stock_projections"
echo ""
