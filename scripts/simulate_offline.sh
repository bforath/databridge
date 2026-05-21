#!/usr/bin/env bash
# End-to-end ingestion resilience demo.
#
# Shows partial batch commits + mid-load failure + watermark-based recovery:
#   1. Adds 1500 customers + 10 products + 500 orders to raw tables
#   2. Triggers ingest_customers + ingest_products (independent — no FK deps)
#   3. Polls customers.customers — locks it after 500 rows committed (~10 batches)
#   4. ingest_customers blocks mid-load, watermark frozen at last committed batch
#   5. Blocked session killed → ingest_customers fails with partial progress
#   6. On retry: picks up from last_raw_id, processes only the remaining ~1000
#   7. Once customers are fully loaded, triggers ingest_orders + ingest_warehouse_stock
#      — both complete with 0 skipped because all FK dependencies are now satisfied
#
# ingest_orders is deliberately held back until step 7: if it ran alongside
# ingest_customers, it would skip orders whose customer emails hadn't been
# loaded yet, and those skips are permanent (the watermark advances past them).
#
# Usage:
#   ./scripts/simulate_offline.sh        # lock fires after 500 rows (default)
#   ./scripts/simulate_offline.sh 300    # lock fires after 300 rows

set -euo pipefail

LOCK_AFTER_ROWS=${1:-500}
LOCK_HOLD=60

AIRFLOW_URL="http://localhost:8080/api/v1"
AIRFLOW_CREDS="admin:admin"
SMTP_HOST="localhost"
SMTP_PORT="1025"
ALERT_FROM="alerts@databridge.io"
ALERT_TO="admin@databridge.io"

# ── helpers ────────────────────────────────────────────────────────────────────

db_exec() {
    docker compose exec -T db psql -U databridge -d databridge -c "$1" -q
}

wait_for_backend() {
    echo "    Waiting for backend ..."
    local attempts=0
    until docker compose exec -T backend python -c \
        "import psycopg2, os; psycopg2.connect(os.environ['DATABASE_URL'].replace('+psycopg2',''))" \
        2>/dev/null; do
        attempts=$((attempts + 1))
        if [[ $attempts -ge 60 ]]; then
            echo "    Backend not ready after 60s — check: docker compose logs backend"
            exit 1
        fi
        sleep 1
    done
    echo "    ✓ Backend is healthy"
}

# Unpause, trigger, and print the run_id to stdout (last line).
# Progress messages go to stderr so callers can capture the run_id cleanly.
unpause_and_trigger() {
    local dag_id="$1"
    local run_id="sim_$(date +%s)_${dag_id}"
    curl -s -o /dev/null -X PATCH "${AIRFLOW_URL}/dags/${dag_id}" \
        -H "Content-Type: application/json" \
        -u "${AIRFLOW_CREDS}" \
        -d '{"is_paused": false}'
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "${AIRFLOW_URL}/dags/${dag_id}/dagRuns" \
        -H "Content-Type: application/json" \
        -u "${AIRFLOW_CREDS}" \
        -d "{\"dag_run_id\": \"${run_id}\"}")
    if [[ "$code" == "200" ]]; then
        echo "    ✓ ${dag_id} triggered (run_id=${run_id})" >&2
        echo "$run_id"
    else
        echo "    ✗ ${dag_id} (HTTP ${code}) — is Airflow running at http://localhost:8080?" >&2
        echo ""
    fi
}

# Poll the Airflow API until a DAG run reaches success or failed.
wait_for_dag_run() {
    local dag_id="$1"
    local run_id="$2"
    local attempts=0
    while true; do
        local state
        state=$(curl -s -u "${AIRFLOW_CREDS}" \
            "${AIRFLOW_URL}/dags/${dag_id}/dagRuns/${run_id}" | \
            python3 -c "import sys,json; print(json.load(sys.stdin).get('state',''))" 2>/dev/null)
        if [[ "$state" == "success" || "$state" == "failed" ]]; then
            echo "    ${dag_id}: ${state}"
            return 0
        fi
        attempts=$((attempts + 1))
        if [[ $attempts -ge 180 ]]; then
            echo "    Timed out waiting for ${dag_id}"
            return 1
        fi
        sleep 2
    done
}

pause_dag() {
    curl -s -o /dev/null -X PATCH "${AIRFLOW_URL}/dags/$1" \
        -H "Content-Type: application/json" \
        -u "${AIRFLOW_CREDS}" \
        -d '{"is_paused": true}'
}

send_alert() {
    local subject="$1"
    local body="$2"
    python3 - <<PYEOF
import smtplib
from email.mime.text import MIMEText
msg = MIMEText("""${body}""")
msg["Subject"] = "${subject}"
msg["From"] = "${ALERT_FROM}"
msg["To"] = "${ALERT_TO}"
try:
    with smtplib.SMTP("${SMTP_HOST}", ${SMTP_PORT}) as s:
        s.send_message(msg)
    print("    Email sent → http://localhost:8025")
except Exception as e:
    print(f"    SMTP unavailable ({e}) — skipping email")
PYEOF
}

countdown() {
    local label="$1"
    local seconds=$2
    local remaining=$seconds
    while [[ $remaining -gt 0 ]]; do
        local progress
        progress=$(docker compose exec -T db psql -U databridge -d databridge -t -q \
            -c "SELECT source || '  ' || status || '  processed=' || processed || '/' || total FROM workers.ingestion_runs ORDER BY started_at DESC LIMIT 4;" 2>/dev/null | tr -d ' ' | paste -sd '  ' - || echo "")
        printf "\r    %-6ds  %s  [%s]" "$remaining" "$label" "$progress"
        sleep 1
        remaining=$((remaining - 1))
    done
    printf "\n"
}

# ── preflight ─────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           DataBridge — Resilience Demo                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "─── Preflight: ensuring clean state ────────────────────────────"
echo ""
db_exec "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query LIKE '%pg_sleep%' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true
db_exec "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE wait_event_type = 'Lock' AND usename = 'databridge' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true
wait_for_backend

echo "    Resetting tables and run history ..."
db_exec "TRUNCATE workers.ingestion_runs, workers.ingestion_watermarks;" > /dev/null
db_exec "TRUNCATE customers.customers, inventory.products, sales.orders, stores.stock, stores.locations CASCADE;" > /dev/null
db_exec "TRUNCATE raw.crm_customers, raw.wms_inventory, raw.oms_transactions, raw.warehouse_stock;" > /dev/null
echo "    ✓ Clean state confirmed"
echo ""

# ── step 1: add raw source data ───────────────────────────────────────────────

echo "─── STEP 1 of 6: Add raw source data ───────────────────────────"
echo ""
docker compose exec -T backend python add_raw_batch.py --customers 1500 --products 10 --orders 500
echo ""

# ── step 2: trigger independent DAGs only ────────────────────────────────────

echo "─── STEP 2 of 6: Trigger independent DAGs ──────────────────────"
echo ""
echo "    Triggering ingest_customers + ingest_products only."
echo "    ingest_orders + ingest_warehouse_stock are held back — they resolve"
echo "    customer and product FKs. If they ran now, orders for not-yet-loaded"
echo "    customers would be permanently skipped."
echo ""
customers_run_id=$(unpause_and_trigger "ingest_customers")
unpause_and_trigger "ingest_products" > /dev/null
echo ""
echo "    Lock fires once ${LOCK_AFTER_ROWS} rows land in customers.customers (~$(( LOCK_AFTER_ROWS / 50 )) batches)."
echo ""

# ── step 3: data-driven lock ──────────────────────────────────────────────────

echo "─── STEP 3 of 6: Waiting for customers to land, then locking ───"
echo ""
echo "    Background session polling customers.customers ..."
echo "    Watching ingestion_runs while batches commit:"
echo ""

docker exec -d databridge-db-1 psql -U databridge -d databridge -c "
DO \$\$
DECLARE cnt INT := 0;
BEGIN
  WHILE cnt < ${LOCK_AFTER_ROWS} LOOP
    SELECT COUNT(*) INTO cnt FROM customers.customers;
    PERFORM pg_sleep(0.1);
  END LOOP;
END \$\$;
BEGIN;
LOCK TABLE customers.customers IN ACCESS EXCLUSIVE MODE;
SELECT pg_sleep(${LOCK_HOLD});
COMMIT;
"

sleep 1

echo "    ✗ customers.customers: LOCKED"
echo ""
echo "    ingest_customers is now blocked mid-load. Watch processed count freeze:"
echo "      docker compose exec db psql -U databridge -d databridge \\"
echo "        -c 'SELECT source, status, total, processed FROM workers.ingestion_runs ORDER BY started_at DESC;'"
echo ""

send_alert \
    "[DataBridge] Partial ingestion failure — customer table unavailable" \
    "Alert: customers.customers became unavailable at $(date -u '+%Y-%m-%dT%H:%M:%SZ').

ingest_customers is blocked mid-load at ~${LOCK_AFTER_ROWS} rows.
Committed batches have advanced the watermark to last_raw_id=${LOCK_AFTER_ROWS}.
On recovery, Airflow will retry from that watermark — only remaining rows processed.

ingest_orders and ingest_warehouse_stock are queued and will run after customers are fully loaded."

echo "    Holding lock for 30s so you can observe the frozen state ..."
countdown "lock held" 30

echo ""
echo "    Killing blocked sessions ..."
db_exec "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE wait_event_type = 'Lock' AND usename = 'databridge' AND pid <> pg_backend_pid();" > /dev/null
echo "    Releasing lock ..."
db_exec "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query LIKE '%pg_sleep%' AND pid <> pg_backend_pid();" > /dev/null
echo "    ✓ customers.customers unlocked"
echo ""

# ── step 4: show failure state ────────────────────────────────────────────────

echo "─── STEP 4 of 6: Failure state ─────────────────────────────────"
echo ""
echo "    ingestion_runs:"
db_exec "SELECT source, status, message, total, processed FROM workers.ingestion_runs ORDER BY started_at DESC LIMIT 6;"
echo ""
echo "    watermarks (last_raw_id is where the retry will resume from):"
db_exec "SELECT source, last_raw_id FROM workers.ingestion_watermarks;"
echo ""
echo "    → crm_customers: status=failed, processed=~${LOCK_AFTER_ROWS} (interrupted mid-load)"
echo "    → wms_inventory: complete (no dependency on customers)"
echo ""

send_alert \
    "[DataBridge] customers.customers restored — retrying ingest_customers" \
    "Recovery: customers.customers unlocked at $(date -u '+%Y-%m-%dT%H:%M:%SZ').

Airflow will retry ingest_customers within 30s.
Retry resumes from last_raw_id — only the remaining ~$((1500 - LOCK_AFTER_ROWS)) rows fetched.
Already-committed batches will not be re-run."

# ── step 5: wait for customers retry ─────────────────────────────────────────

echo "─── STEP 5 of 6: Waiting for ingest_customers retry ────────────"
echo ""
echo "    Airflow retries ingest_customers in ~30s ..."
echo "    Polling Airflow until the DAG run succeeds ..."
echo ""

wait_for_dag_run "ingest_customers" "$customers_run_id"
printf "\n"

echo ""
echo "    crm_customers retry complete. All 1500 customers now loaded."
echo ""
echo "    ingestion_runs (crm_customers — both runs):"
db_exec "SELECT source, status, message, total, processed FROM workers.ingestion_runs WHERE source = 'crm_customers' ORDER BY started_at DESC LIMIT 2;"
echo ""

# ── step 6: trigger dependent DAGs ───────────────────────────────────────────

echo "─── STEP 6 of 6: Trigger dependent DAGs ────────────────────────"
echo ""
echo "    All 1500 customers + 10 products loaded. Triggering orders + warehouse."
echo ""
orders_run_id=$(unpause_and_trigger "ingest_orders")
warehouse_run_id=$(unpause_and_trigger "ingest_warehouse_stock")
echo ""
echo "    Waiting for both to complete ..."
wait_for_dag_run "ingest_orders" "$orders_run_id"
wait_for_dag_run "ingest_warehouse_stock" "$warehouse_run_id"
echo ""
echo "    Triggering compute_stock_projections ..."
projections_run_id=$(unpause_and_trigger "compute_stock_projections")
wait_for_dag_run "compute_stock_projections" "$projections_run_id"
echo ""

# Pause all DAGs so scheduled runs don't fire after the demo and create noise.
for dag in ingest_customers ingest_products ingest_orders ingest_warehouse_stock compute_stock_projections; do
    pause_dag "$dag"
done
echo "    DAGs paused — no further scheduled runs until next demo."
echo ""
echo "    Final ingestion_runs state:"
db_exec "SELECT source, status, message, total, processed, skipped FROM workers.ingestion_runs ORDER BY started_at DESC LIMIT 8;"
echo ""
echo "    The two crm_customers rows together account for all 1500 customers:"
echo "      first run:  status=failed,   processed=~${LOCK_AFTER_ROWS}  (partial)"
echo "      retry:      status=complete, processed=~$((1500 - LOCK_AFTER_ROWS)) (remainder)"
echo ""
echo "    oms_transactions + warehouse_stock: complete with skipped=0"
echo "    (all FKs resolved — customers were fully loaded before they ran)"
echo ""
echo "    Check emails: http://localhost:8025"
echo ""
