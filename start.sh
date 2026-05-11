#!/bin/bash
# Launch agent(s). Each agent in agents/<id>/ gets its own port.
#
# Usage:
#   ./start.sh                  — start all agents
#   ./start.sh shiseido_us      — start one agent
#   ./start.sh shiseido_us 8510 — start on a specific port

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Assign ports sequentially starting at BASE_PORT, alphabetical order
BASE_PORT=8501

get_port() {
  local agent=$1
  local idx=0
  for dir in $(ls -d agents/*/  2>/dev/null | sort); do
    name=$(basename "$dir")
    if [ "$name" = "$agent" ]; then
      echo $((BASE_PORT + idx))
      return
    fi
    idx=$((idx + 1))
  done
  echo 8500  # fallback
}

start_agent() {
  local agent=$1
  local port=${2:-$(get_port "$agent")}
  mkdir -p logs
  echo "▶ Starting $agent on port $port..."
  python3 -m streamlit run ui/app.py \
    --server.port "$port" \
    --server.headless true \
    -- --site "$agent" \
    > "logs/${agent}.log" 2>&1 &
  echo "  http://localhost:$port  (PID $!)"
}

if [ -n "$1" ]; then
  start_agent "$1" "$2"
else
  # Start all agents found in agents/
  idx=0
  for dir in $(ls -d agents/*/  2>/dev/null | sort); do
    agent=$(basename "$dir")
    if [ -f "agents/$agent/config.yaml" ]; then
      start_agent "$agent" $((BASE_PORT + idx))
      idx=$((idx + 1))
    fi
  done
  if [ "$idx" -eq 0 ]; then
    echo "No agents found in agents/. Run: python scripts/new_agent.py <agent_id>"
  fi
fi

echo ""
echo "Logs: logs/<agent>.log"
echo "Stop all: pkill -f 'streamlit run'"
