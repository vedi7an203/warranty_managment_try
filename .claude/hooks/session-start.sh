#!/bin/bash
set -euo pipefail

# Only run in remote (Claude Code on the web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo '{"async": true, "asyncTimeout": 300000}'

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

# ── Install Python dependencies ──────────────────────────────────────────────
echo "[session-start] Installing Python dependencies…"
pip install -r requirements.txt --quiet

# ── Initialise database (idempotent — skips existing rows) ───────────────────
echo "[session-start] Initialising database…"
FLASK_APP=app.py flask init-db

# ── Seed sample warranty data if DB is empty ─────────────────────────────────
echo "[session-start] Seeding sample warranty data…"
FLASK_APP=app.py flask seed-warranties

echo "[session-start] Done. App ready — run: flask run --host=0.0.0.0 --port=5000"
