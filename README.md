# Shopper Agent Prototype

A multi-brand AI shopping advisor built on Claude and Salesforce Commerce Cloud (SCAPI). Clone an existing agent, drop in SCAPI credentials, and have a branded demo running in minutes.

## Repo Structure

```
shopper-agent-prototype/
├── agent/                        # Shared runtime (all agents use this)
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
│   ├── install_skill.sh          # Install the Claude Code skill
│   ├── run_evals.py              # Run evals from CLI
│   └── gepa_optimize.py          # GEPA prompt optimizer
├── .claude/skills/
│   └── demo-shopper-agent/       # Claude Code /demo-shopper-agent skill
├── start.sh                      # Launch one or all agents
└── requirements.txt
```

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env              # add your ANTHROPIC_API_KEY
./start.sh NTOManaged             # start NTO demo
```

Open the URL printed in the terminal (ports assigned alphabetically from 8501).

## Creating a New Branded Agent

### Option A — CLI

```bash
python scripts/new_agent.py acme_us --from shiseido_us
```

Copies the source agent, clears credentials, and prompts for branding. Then fill in `agents/acme_us/config.env` and run `./start.sh acme_us`.

### Option B — Claude Code skill

Install once after cloning:

```bash
./scripts/install_skill.sh
```

Then type `/demo-shopper-agent` in Claude Code and follow the interactive prompts.

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
