# Shopper Agent Prototype

A Claude Code skill that lets you spin up a branded AI shopping advisor for any Salesforce Commerce Cloud (SCAPI) storefront in minutes — no coding required.

## What It Does

Once installed, you get a `/demo-shopper-agent` command in Claude Code that walks you through creating a fully working shopping advisor demo: clone an existing agent, customise the branding, add SCAPI credentials, and launch — all from a single conversation.

The advisor itself is a conversational product discovery agent. Shoppers describe what they're looking for in natural language, and it searches the live SCAPI catalog, surfaces relevant products with pricing, and guides the conversation with follow-up questions. It auto-detects the shopper's language and switches locale accordingly (e.g. Japanese input → `ja_JP` catalog queries).

Every session is logged and can be scored against quality metrics (relevance, tone, product accuracy, cognitive load) with one click — so you can measure and improve the experience over time.

## Get Started

Run this one command in your terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/bhaanng/shopper-agent-prototype/main/scripts/install_skill.sh | bash
```

This clones the repo to `~/shopper-agent-prototype`, installs dependencies, and wires up the Claude Code skill. Then:

1. Restart Claude Code
2. Open Claude Code in `~/shopper-agent-prototype`
3. Type `/demo-shopper-agent`

Claude will ask for your brand name and SCAPI credentials and have your agent running in a browser within minutes.

## Included Agents

| Agent | Brand | Description |
|-------|-------|-------------|
| `NTOManaged` | Northern Trail Outfitters | Outdoor gear, hiking, camping, climbing — base demo |
| `shiseido_us` | Shiseido | Prestige Japanese beauty — skincare, makeup, fragrance |
| `hibbett` | Hibbett Sports | Athletic footwear, sneakers, apparel, team sports gear |

Each agent has its own system prompt, branding, locales, and eval dataset in `agents/<id>/config.yaml`.

## Repo Structure

```
shopper-agent-prototype/
├── core/                         # Shared runtime (all agents use this)
│   ├── nto_agent.py              # ReAct loop, SCAPI calls, response parsing
│   ├── site_config.py            # Per-agent config loader
│   └── system_prompt.py          # Base system prompt
├── agents/                       # One folder per brand
│   ├── NTOManaged/               # Northern Trail Outfitters (base demo)
│   ├── shiseido_us/              # Shiseido beauty advisor
│   └── hibbett/                  # Hibbett sports
│       ├── config.yaml           # Branding, system prompt, tools, locales, examples
│       ├── config.env            # SCAPI credentials (not committed)
│       └── eval_dataset.json     # Eval cases for this agent
├── ui/
│   └── app.py                    # Streamlit UI (shared across all agents)
├── evals/
│   ├── runner.py                 # Parallel LLM judge
│   ├── proxies.py                # Eval metrics
│   └── session_logger.py         # Per-session JSONL logging (30-day TTL)
├── scripts/
│   ├── new_agent.py              # Scaffold a new branded agent
│   ├── install_skill.sh          # One-command install (clone + deps + skill)
│   ├── run_evals.py              # Run evals from CLI
│   └── gepa_optimize.py          # GEPA prompt optimizer
├── .claude/skills/
│   └── demo-shopper-agent/       # Claude Code /demo-shopper-agent skill
├── start.sh                      # Launch one or all agents
└── requirements.txt
```

## Agent Configuration

Each agent is fully self-contained in `agents/<id>/`:

**`config.yaml`**
```yaml
ui:
  title: "ACME Advisor"
  subtitle: "Your personal gear expert"
  icon: "🏃"
  about: |
    Your ACME advisor...
  starter_queries:
    - label: "Running shoes"
      query: "Show me running shoes under $120"

tools:
  search_tool_name: search_acme_products
  search_description: "Search the ACME catalog."

locales:
  default: en_US
  supported: [en_US, es_ES]

system_prompt: |    # replaces base prompt entirely (optional)
overlay: |          # appended to base prompt as site-specific instructions
examples:           # few-shot examples shown to the agent
```

**`config.env`** (never committed)
```
SCAPI_TOKEN_URL=https://<shortcode>.api.commercecloud.salesforce.com/.../oauth2/token
SCAPI_CLIENT_CREDENTIALS=<base64 client_id:secret>
SCAPI_SEARCH_URL=https://<shortcode>.api.commercecloud.salesforce.com/.../product-search
SCAPI_SITE_ID=acme_us
SCAPI_LOCALE=en_US
```

## How It Works

Each response follows a ReAct loop (max 5 iterations, max 2 search calls):

1. **`create_todo`** — plan steps, show a warm message to the shopper
2. **`search_<site>_products`** — parallel queries against SCAPI
3. **`web_search`** — optional, for reviews, ingredients, or context
4. **Final response** — JSON parsed into product cards + markdown

```json
{
  "thought": "...",
  "response": [
    {"type": "markdown", "content": "..."},
    {"type": "product_table", "content": {"title": "...", "products": [{"id": "..."}]}}
  ],
  "follow_up": "...",
  "suggestions": ["Option 1", "Option 2"]
}
```

## Evals

```bash
# Run evals from CLI
python scripts/run_evals.py --site shiseido_us
python scripts/run_evals.py --site NTOManaged --sample 20 --metric cognitive_load

# Or click "📊 Eval This Session" in the sidebar after a conversation
```

Sessions are logged to `logs/sessions/<site_id>/` as JSONL files and cleaned up after 30 days.

## Port Assignment

Ports assigned alphabetically from 8501:

| Agent | Port |
|-------|------|
| hibbett | 8501 |
| NTOManaged | 8502 |
| shiseido_us | 8503 |

Override: `./start.sh NTOManaged 8510`

## Requirements

- Python 3.10+
- Anthropic API key (Claude via AWS Bedrock or direct API)
- SCAPI credentials for the target SFCC storefront
