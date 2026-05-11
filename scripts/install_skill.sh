#!/bin/bash
# One-command setup for the demo-shopper-agent Claude Code skill.
#
# Usage (run this from anywhere):
#   curl -fsSL https://raw.githubusercontent.com/bhaanng/shopper-agent-prototype/main/scripts/install_skill.sh | bash
#
# What it does:
#   1. Clones the repo to ~/shopper-agent-prototype (if not already there)
#   2. Installs Python dependencies
#   3. Symlinks the skill into ~/.claude/skills/ so Claude Code picks it up

set -e

REPO_URL="https://github.com/bhaanng/shopper-agent-prototype.git"
REPO_DIR="$HOME/shopper-agent-prototype"
SKILL_DST="$HOME/.claude/skills/demo-shopper-agent"

# ── Step 1: Clone or update the repo ─────────────────────────────────────────
if [ -d "$REPO_DIR/.git" ]; then
  echo "📦 Repo already exists at $REPO_DIR — pulling latest..."
  git -C "$REPO_DIR" pull --ff-only
else
  echo "📦 Cloning shopper-agent-prototype..."
  git clone "$REPO_URL" "$REPO_DIR"
fi

# ── Step 2: Install Python dependencies ──────────────────────────────────────
echo ""
echo "🐍 Installing Python dependencies..."
pip install -r "$REPO_DIR/requirements.txt" --quiet

# ── Step 3: Install the Claude Code skill ────────────────────────────────────
SKILL_SRC="$REPO_DIR/.claude/skills/demo-shopper-agent"
mkdir -p "$HOME/.claude/skills"

if [ -L "$SKILL_DST" ]; then
  echo ""
  echo "✅ Skill already installed at $SKILL_DST"
elif [ -d "$SKILL_DST" ]; then
  echo ""
  echo "⚠️  $SKILL_DST already exists and is not a symlink — leaving it as-is."
else
  ln -s "$SKILL_SRC" "$SKILL_DST"
  echo ""
  echo "✅ Skill installed: $SKILL_DST"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  All done! Next steps:"
echo ""
echo "  1. Restart Claude Code"
echo "  2. Open Claude Code in: $REPO_DIR"
echo "  3. Type: /demo-shopper-agent"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
