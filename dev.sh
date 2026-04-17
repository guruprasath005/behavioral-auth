#!/usr/bin/env bash
# dev.sh — start the full Behavioral Auth stack and kill everything on Ctrl-C
#
# Usage:
#   ./dev.sh                     # prompts for user id
#   ./dev.sh --user alice        # skip the prompt
#   ./dev.sh --user alice --no-shell

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_DIR="$SCRIPT_DIR/dashboard"

PIDS=()

cleanup() {
  echo ""
  echo "[dev.sh] Shutting down…"
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait "${PIDS[@]}" 2>/dev/null || true
  echo "[dev.sh] All processes stopped."
}
trap cleanup INT TERM

cd "$SCRIPT_DIR"

# ── Load .env ───────────────────────────────────────────────────────────────
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  set -a
  source "$SCRIPT_DIR/.env"
  set +a
fi

# ── Activate venv if present ────────────────────────────────────────────────
if [[ -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
  source "$SCRIPT_DIR/.venv/bin/activate"
fi

# ── Resolve --user before spawning anything (input() won't work in bg) ──────
USER_ARG=""
EXTRA_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      USER_ARG="$2"
      shift 2
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ -z "$USER_ARG" ]]; then
  read -rp "Enter user ID (your name or any identifier): " USER_ARG
  if [[ -z "$USER_ARG" ]]; then
    echo "User ID cannot be empty." >&2
    exit 1
  fi
fi

# ── Clear stale processes on known ports ────────────────────────────────────
for port in 3000 8000; do
  pid=$(lsof -ti:"$port" 2>/dev/null || true)
  if [[ -n "$pid" ]]; then
    echo "[dev.sh] Killing stale process on port $port (pid $pid)"
    kill "$pid" 2>/dev/null || true
    sleep 0.3
  fi
done

# ── FastAPI server ──────────────────────────────────────────────────────────
echo "[dev.sh] Starting FastAPI on http://localhost:8000"
uvicorn api.server:app --reload --port 8000 &
PIDS+=($!)

# ── React dashboard ─────────────────────────────────────────────────────────
echo "[dev.sh] Starting React dashboard on http://localhost:3000"
(cd "$DASHBOARD_DIR" && npm run dev --silent) &
PIDS+=($!)

# Give servers a moment to bind their ports before the capture process starts
sleep 1

# ── Capture session (foreground — keeps script alive; Ctrl-C triggers cleanup) ─
echo "[dev.sh] Starting capture session for user: $USER_ARG"
echo "[dev.sh] Press Ctrl-C to stop everything."
echo ""
echo "┌─────────────────────────────────────────────────────────┐"
echo "│  Shell monitoring: commands are captured via zshrc hook  │"
echo "│                                                           │"
echo "│  First time setup:                                        │"
echo "│    python3 main.py --install-hook                         │"
echo "│    source ~/.zshrc                                        │"
echo "│                                                           │"
echo "│  Every terminal you open AFTER that will be captured.    │"
echo "│  Commands typed in THIS terminal are NOT captured         │"
echo "│  (open a new terminal tab to test shell monitoring).      │"
echo "└─────────────────────────────────────────────────────────┘"
echo ""
python3 main.py --user "$USER_ARG" ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} || true

cleanup
