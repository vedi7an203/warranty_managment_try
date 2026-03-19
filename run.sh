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

# Install dependencies (non-fatal — handles offline / proxy-restricted environments)
if ! python3 -c "import flask, flask_sqlalchemy, flask_login, werkzeug" 2>/dev/null; then
  echo "[*] Installing Python dependencies…"
  pip install -r requirements.txt -q || true
  if ! python3 -c "import flask, flask_sqlalchemy, flask_login, werkzeug" 2>/dev/null; then
    echo "[!] Error: required packages could not be installed."
    echo "    Run manually: pip install -r requirements.txt"
    exit 1
  fi
else
  echo "[*] Python dependencies already satisfied."
fi

export FLASK_APP=app.py
export FLASK_DEBUG=1

echo "[*] Initialising database…"
flask init-db

# Only seed if the database has no warranty records yet
WARRANTY_COUNT=$(python3 -c "
from app import app, db
from app import Warranty
with app.app_context():
    print(Warranty.query.count())
" 2>/dev/null || echo "0")

if [ "$WARRANTY_COUNT" -eq "0" ]; then
  echo "[*] Seeding sample warranty data…"
  flask seed-warranties
else
  echo "[*] Database already contains $WARRANTY_COUNT warranty record(s) — skipping seed."
fi

echo ""
echo "✓ Ready! Open http://localhost:5000 in your browser."
echo "  Admin    : admin / Admin123!"
echo "  Engineer : j.smith / Engineer1!"
echo ""
flask run --host=0.0.0.0 --port=5000
