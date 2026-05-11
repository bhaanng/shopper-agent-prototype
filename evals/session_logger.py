"""
Session logger for live UI conversations.

Each browser session gets a JSONL file under:
  logs/sessions/<site_id>/<session_id>.jsonl

One record per assistant turn:
  {
    "session_id":   "...",
    "site_id":      "shiseido_us",
    "turn":         1,
    "timestamp":    "2026-05-10T14:22:01Z",
    "query":        "user's message",
    "response":     "agent's markdown text (first 2000 chars)",
    "locale":       "en-US",
    "tool_calls":   [{"tool": "search_nto_products", "duration": "320ms"}]
  }

Cleanup: files older than TTL_DAYS are deleted on logger init.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

TTL_DAYS = int(os.getenv("SESSION_LOG_TTL_DAYS", "30"))

_SESSIONS_DIR = Path(__file__).parent.parent / "logs" / "sessions"


def _cleanup(site_dir: Path, ttl_days: int) -> None:
    """Delete session files older than ttl_days in the given site directory."""
    if not site_dir.exists():
        return
    cutoff = time.time() - ttl_days * 86400
    removed = 0
    for f in site_dir.glob("*.jsonl"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            pass
    if removed:
        print(f"  🗑  Session log cleanup: removed {removed} file(s) older than {ttl_days}d from {site_dir.name}/")


class SessionLogger:
    """One instance per browser session. Call log_turn() after each agent reply."""

    def __init__(self, site_id: str, session_id: str = None, ttl_days: int = TTL_DAYS):
        self.site_id = site_id or "base"
        self.session_id = session_id or uuid.uuid4().hex
        self.ttl_days = ttl_days
        self.turn = 0

        self._dir = _SESSIONS_DIR / self.site_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / f"{self.session_id}.jsonl"

        _cleanup(self._dir, self.ttl_days)

    def log_turn(self, query: str, response: dict, locale: str = None) -> None:
        """Append one turn record to the session file."""
        self.turn += 1

        # Extract plain text from the structured response
        response_text = "\n\n".join(
            block.get("content", "")
            for block in response.get("response", [])
            if isinstance(block, dict) and block.get("type") == "markdown"
        )
        if response.get("follow_up"):
            response_text += f"\n\n{response['follow_up']}"

        tool_calls = [
            {"tool": c["tool"], "duration": c.get("duration", "")}
            for c in response.get("tool_call_log", [])
        ]

        record = {
            "session_id": self.session_id,
            "site_id": self.site_id,
            "turn": self.turn,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query": query,
            "response": response_text[:2000],
            "locale": locale,
            "tool_calls": tool_calls,
        }

        with open(self._path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def path(self) -> Path:
        return self._path


def load_session(path) -> list[dict]:
    """Load all turn records from a session JSONL file."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def list_sessions(site_id: str = None, limit: int = 50) -> list[Path]:
    """Return session files sorted newest-first, optionally filtered by site."""
    base = _SESSIONS_DIR
    if site_id:
        base = base / site_id
    if not base.exists():
        return []
    files = sorted(base.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:limit]
