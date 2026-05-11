#!/bin/bash
# Install the demo-shopper-agent Claude Code skill.
#
# Run once after cloning the repo:
#   ./scripts/install_skill.sh
#
# What it does:
#   Symlinks .claude/skills/demo-shopper-agent → ~/.claude/skills/demo-shopper-agent
#   so Claude Code picks up the /demo-shopper-agent slash command.

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SKILL_SRC="$REPO_DIR/.claude/skills/demo-shopper-agent"
SKILL_DST="$HOME/.claude/skills/demo-shopper-agent"

if [ ! -d "$SKILL_SRC" ]; then
  echo "❌ Skill not found at $SKILL_SRC — are you running this from the repo root?"
  exit 1
fi

mkdir -p "$HOME/.claude/skills"

if [ -L "$SKILL_DST" ]; then
  echo "✅ Skill already installed at $SKILL_DST"
elif [ -d "$SKILL_DST" ]; then
  echo "⚠️  $SKILL_DST already exists and is not a symlink — leaving it as-is."
else
  ln -s "$SKILL_SRC" "$SKILL_DST"
  echo "✅ Installed: $SKILL_DST → $SKILL_SRC"
fi

echo ""
echo "Restart Claude Code, then type /demo-shopper-agent to scaffold a new agent."
