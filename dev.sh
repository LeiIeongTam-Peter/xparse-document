#!/usr/bin/env bash
# =============================================================================
# Xparse Local Dev — backend stack management
# =============================================================================
# Usage:
#   ./dev.sh up           → Start all backend services (MVP + Audit + Fleet)
#   ./dev.sh up-guardrails → Start backend services + guardrail sidecar
#   ./dev.sh guardrails   → Start/rebuild only the guardrail sidecar
#   ./dev.sh down         → Stop all services
#   ./dev.sh restart      → Restart all services
#   ./dev.sh restart iam  → Restart a specific service
#   ./dev.sh logs         → Follow all logs
#   ./dev.sh logs gateway → Follow a specific service log
#   ./dev.sh status       → Show container health
#   ./dev.sh clean        → Remove stopped containers + dangling images
#   ./dev.sh fix-db       → Fix SQLite readonly error (chmod 666 on DB files)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../xparse" && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILES=(-f docker-compose.mvp.yml -f docker-compose.mvp-audit.yml -f docker-compose.mvp-fleet.yml)
GUARDRAILS_COMPOSE_FILES=("${COMPOSE_FILES[@]}" -f docker-compose.guardrails-local.yml)
COMPOSE=(docker compose "${COMPOSE_FILES[@]}")
COMPOSE_GUARDRAILS=(docker compose --profile guardrails "${GUARDRAILS_COMPOSE_FILES[@]}")

print_urls() {
  echo ""
  echo "Services ready:"
  echo "  Console + API : https://localhost:3000"
  echo "  Keycloak Admin: http://localhost:8180/auth"
  echo "  Audit API     : http://localhost:8001"
  echo "  Fleet API     : http://localhost:8090  (or https://localhost:3000/fleet/)"
  echo ""
  echo "Frontend dev (hot-reload):"
  echo "  cd frontend/console-app && pnpm dev"
  echo "  → http://localhost:5173"
}

print_guardrail_note() {
  echo ""
  echo "Guardrails:"
  echo "  Sidecar       : xparse-guardrails:8400 (Docker-internal)"
  echo "  Health check  : docker exec xparse-guardrails python -c \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8400/health').read().decode())\""
  echo "  Note          : regex/injection rails do not need a judge endpoint; low/medium/high content safety needs XPARSE_GUARDRAIL_JUDGE_BASE_URL and XPARSE_GUARDRAIL_JUDGE_API_KEY in .env."
}

ensure_guardrails_submodule() {
  if [[ -f 3rd/Guardrails/pyproject.toml || -f 3rd/Guardrails/setup.py ]]; then
    return
  fi

  echo "Initializing 3rd/Guardrails submodule for local guardrail image build..."
  git submodule update --init --recursive 3rd/Guardrails

  if [[ ! -f 3rd/Guardrails/pyproject.toml && ! -f 3rd/Guardrails/setup.py ]]; then
    echo "ERROR: 3rd/Guardrails is still not installable after submodule init." >&2
    exit 1
  fi
}

case "${1:-help}" in
  up)
    echo "Starting Xparse backend stack (MVP + Audit + Fleet)..."
    "${COMPOSE[@]}" up -d --build
    print_urls
    ;;
  up-guardrails)
    echo "Starting Xparse backend stack with guardrail sidecar..."
    ensure_guardrails_submodule
    "${COMPOSE_GUARDRAILS[@]}" up -d --build
    print_urls
    print_guardrail_note
    ;;
  guardrails)
    echo "Starting/rebuilding xparse-guardrails sidecar..."
    ensure_guardrails_submodule
    "${COMPOSE_GUARDRAILS[@]}" up -d --build xparse-guardrails
    print_guardrail_note
    ;;
  down)
    echo "Stopping Xparse..."
    "${COMPOSE_GUARDRAILS[@]}" down
    ;;
  restart)
    if [[ -n "${2:-}" ]]; then
      "${COMPOSE_GUARDRAILS[@]}" restart "$2"
    else
      "${COMPOSE_GUARDRAILS[@]}" restart
    fi
    ;;
  logs)
    if [[ -n "${2:-}" ]]; then
      "${COMPOSE_GUARDRAILS[@]}" logs -f "$2"
    else
      "${COMPOSE_GUARDRAILS[@]}" logs -f
    fi
    ;;
  status)
    "${COMPOSE_GUARDRAILS[@]}" ps
    ;;
  clean)
    echo "Removing stopped containers and dangling images..."
    docker container prune -f
    docker image prune -f
    echo "Done. For a deeper clean (unused images/volumes), run:"
    echo "  docker image prune -a    # removes ALL unused images (~37 GB)"
    echo "  docker builder prune -f  # removes build cache (~15 GB)"
    echo "  docker volume prune      # removes unused volumes (check first!)"
    ;;
  fix-db)
    echo "Fixing SQLite database permissions..."
    docker run --rm -v xparse_xparse-data:/data alpine \
      chmod 666 /data/xparse_iam.db /data/xparse_iam.db-shm /data/xparse_iam.db-wal /data/.migration.lock 2>/dev/null || true
    docker restart xparse-iam
    echo "Done. IAM restarted."
    ;;
  *)
    echo "Usage: $0 {up|up-guardrails|guardrails|down|restart [service]|logs [service]|status|clean|fix-db}"
    exit 1
    ;;
esac
