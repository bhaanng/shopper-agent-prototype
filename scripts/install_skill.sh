#!/bin/bash
# One-command setup for the demo-shopper-agent Claude Code skill.
#
# Usage (run this from anywhere):
#   curl -fsSL https://raw.githubusercontent.com/bhaanng/shopper-agent-prototype/main/scripts/install_skill.sh | bash

set -e

REPO_URL="https://github.com/bhaanng/shopper-agent-prototype.git"
REPO_DIR="$HOME/shopper-agent-prototype"
SKILL_DST="$HOME/.claude/skills/demo-shopper-agent"
ENV_FILE="$REPO_DIR/.env"

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
  echo "✅ Skill installed"
fi

# ── Step 4: Collect and validate credentials ─────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Credential Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Load existing .env if present so we can show current values
if [ -f "$ENV_FILE" ]; then
  source "$ENV_FILE" 2>/dev/null || true
fi

prompt_value() {
  local var_name="$1"
  local description="$2"
  local hint="$3"
  local current_val="${!var_name}"

  echo ""
  echo "  $description"
  if [ -n "$hint" ]; then echo "  ($hint)"; fi
  if [ -n "$current_val" ]; then
    echo -n "  $var_name [current: set, press Enter to keep]: "
  else
    echo -n "  $var_name: "
  fi
  read -r input
  if [ -n "$input" ]; then
    eval "$var_name=\"$input\""
  fi
}

echo ""
echo "  You'll need two sets of credentials:"
echo ""
echo "  [1] Anthropic / Bedrock Gateway — to run Claude"
echo "  [2] SCAPI — to connect to your Salesforce storefront"
echo ""
echo "  Press Enter to keep any value already set."

# ── Anthropic credentials
echo ""
echo "  ── Anthropic / Bedrock Gateway ──────────────────────"
prompt_value "ANTHROPIC_API_KEY" \
  "API key for Claude (direct Anthropic key or Bedrock gateway token)" \
  "Salesforce colleagues: get this from the Bedrock gateway or eng-ai-model-gateway"

prompt_value "ANTHROPIC_BASE_URL" \
  "Bedrock gateway base URL (leave blank if using direct Anthropic API)" \
  "Salesforce: https://eng-ai-model-gateway.sfproxy.devx-preprod.aws-esvc1-useast2.aws.sfdc.cl"

# ── SCAPI credentials
echo ""
echo "  ── SCAPI (Salesforce Commerce Cloud) ────────────────"
prompt_value "SCAPI_TOKEN_URL" \
  "OAuth token endpoint for your storefront" \
  "e.g. https://prd.us1.shopper.commercecloud.salesforce.com/api/v1/organizations/<org_id>/oauth2/token"

prompt_value "SCAPI_CLIENT_CREDENTIALS" \
  "Base64-encoded client_id:client_secret" \
  "Generate with: echo -n 'client_id:client_secret' | base64"

prompt_value "SCAPI_SEARCH_URL" \
  "SCAPI product search endpoint" \
  "e.g. https://<shortcode>.api.commercecloud.salesforce.com/search/shopper-search/v1/organizations/<org_id>/product-search"

prompt_value "SCAPI_SITE_ID" \
  "Storefront site ID" \
  "e.g. NTOManaged, shiseido_us — must match the site ID in Business Manager"

# ── Step 5: Validate ─────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Validating credentials..."
ERRORS=0

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "  ❌ ANTHROPIC_API_KEY is required"
  ERRORS=$((ERRORS + 1))
else
  echo "  ✅ ANTHROPIC_API_KEY is set"
fi

if [ -n "$ANTHROPIC_BASE_URL" ]; then
  if [[ "$ANTHROPIC_BASE_URL" == https://* ]]; then
    echo "  ✅ ANTHROPIC_BASE_URL is set (Bedrock gateway)"
  else
    echo "  ⚠️  ANTHROPIC_BASE_URL doesn't look like a URL — double-check it"
  fi
else
  echo "  ℹ️  ANTHROPIC_BASE_URL not set (using direct Anthropic API)"
fi

if [ -z "$SCAPI_TOKEN_URL" ]; then
  echo "  ❌ SCAPI_TOKEN_URL is required"
  ERRORS=$((ERRORS + 1))
elif [[ "$SCAPI_TOKEN_URL" != *oauth2/token* ]]; then
  echo "  ⚠️  SCAPI_TOKEN_URL doesn't end in oauth2/token — double-check it"
else
  echo "  ✅ SCAPI_TOKEN_URL looks good"
fi

if [ -z "$SCAPI_CLIENT_CREDENTIALS" ]; then
  echo "  ❌ SCAPI_CLIENT_CREDENTIALS is required"
  ERRORS=$((ERRORS + 1))
else
  echo "  ✅ SCAPI_CLIENT_CREDENTIALS is set"
fi

if [ -z "$SCAPI_SEARCH_URL" ]; then
  echo "  ❌ SCAPI_SEARCH_URL is required"
  ERRORS=$((ERRORS + 1))
elif [[ "$SCAPI_SEARCH_URL" != *product-search* ]]; then
  echo "  ⚠️  SCAPI_SEARCH_URL doesn't contain 'product-search' — double-check it"
else
  echo "  ✅ SCAPI_SEARCH_URL looks good"
fi

if [ -z "$SCAPI_SITE_ID" ]; then
  echo "  ❌ SCAPI_SITE_ID is required"
  ERRORS=$((ERRORS + 1))
else
  echo "  ✅ SCAPI_SITE_ID = $SCAPI_SITE_ID"
fi

# ── Step 6: Write .env ────────────────────────────────────────────────────────
if [ "$ERRORS" -eq 0 ]; then
  cat > "$ENV_FILE" <<EOF
# Anthropic / Bedrock Gateway
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
ANTHROPIC_BASE_URL=$ANTHROPIC_BASE_URL

# Salesforce Commerce Cloud (SCAPI) — default storefront
SCAPI_TOKEN_URL=$SCAPI_TOKEN_URL
SCAPI_CLIENT_CREDENTIALS=$SCAPI_CLIENT_CREDENTIALS
SCAPI_SEARCH_URL=$SCAPI_SEARCH_URL
SCAPI_SITE_ID=$SCAPI_SITE_ID
EOF
  echo ""
  echo "  💾 Credentials saved to $ENV_FILE"
else
  echo ""
  echo "  ⚠️  $ERRORS required value(s) missing — .env not written."
  echo "  Edit $ENV_FILE manually and re-run to validate."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$ERRORS" -eq 0 ]; then
  echo "  ✅ Setup complete! Next steps:"
  echo ""
  echo "  1. Restart Claude Code"
  echo "  2. Open Claude Code in: $REPO_DIR"
  echo "  3. Type: /demo-shopper-agent"
else
  echo "  ⚠️  Setup incomplete — fix the errors above, then re-run."
  echo "  curl -fsSL https://raw.githubusercontent.com/bhaanng/shopper-agent-prototype/main/scripts/install_skill.sh | bash"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
