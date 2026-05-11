#!/bin/bash
# Launch each site agent on its own port.
# Usage: ./start.sh [site_id]
#   ./start.sh              — start all sites
#   ./start.sh shiseido_us  — start one site only

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

get_port() {
  case "$1" in
    NTOManaged)  echo 8501 ;;
    shiseido_us) echo 8502 ;;
    hibbett)     echo 8503 ;;
    *)           echo 8500 ;;
  esac
}

start_site() {
  local site=$1
  local port
  port=$(get_port "$site")
  mkdir -p logs
  echo "▶ Starting $site on port $port..."
  python3 -m streamlit run ui/app.py \
    --server.port "$port" \
    --server.headless true \
    -- --site "$site" \
    > "logs/${site}.log" 2>&1 &
  echo "  http://localhost:$port  (PID $!)"
}

if [ -n "$1" ]; then
  start_site "$1"
else
  start_site NTOManaged
  start_site shiseido_us
  start_site hibbett
fi

echo ""
echo "Logs: logs/<site>.log"
echo "Stop all: pkill -f 'streamlit run'"
