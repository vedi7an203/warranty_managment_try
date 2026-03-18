#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
# WAM — Warranty Adjudication Management
# Quick-start script
# ─────────────────────────────────────────────────────
set -e

echo "══════════════════════════════════════════════"
echo "  WAM — Warranty Adjudication Management"
echo "  Aerospace Part 145 MRO"
echo "══════════════════════════════════════════════"

# Install dependencies if needed
if ! python3 -c "import flask" 2>/dev/null; then
  echo "[*] Installing Python dependencies…"
  pip install -r requirements.txt
fi

export FLASK_APP=app.py
export FLASK_ENV=development

# PostgreSQL is required. Set DATABASE_URL before running this script, e.g.:
#   export DATABASE_URL=postgresql://localhost/warranty_db
if [ -z "$DATABASE_URL" ]; then
  echo "[!] DATABASE_URL is not set. Defaulting to postgresql://localhost/warranty_db"
  export DATABASE_URL=postgresql://localhost/warranty_db
fi

echo "[*] Initialising database…"
flask init-db

echo "[*] Seeding sample warranty data…"
flask seed-warranties

echo ""
echo "✓ Ready! Open http://localhost:5000 in your browser."
echo "  Admin    : admin / Admin123!"
echo "  Engineer : j.smith / Engineer1!"
echo ""
flask run --host=0.0.0.0 --port=5000
