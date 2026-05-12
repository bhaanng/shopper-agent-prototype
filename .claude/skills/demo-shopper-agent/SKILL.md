---
name: demo-shopper-agent
description: |
  Scaffold, configure, and launch a branded shopper agent demo in minutes. Gathers brand
  inputs, generates or clones a contextualised system prompt, sets up SCAPI credentials,
  and starts the Streamlit UI. Use this skill whenever the user wants to: create a new
  demo, onboard a new brand, clone an agent, set up credentials, launch an agent, or
  list available agents.
compatibility: |
  Must be run from the shopper-agent-prototype repo root (scripts/new_agent.py must exist).
  Requires Python 3.10+, pyyaml, and streamlit installed (pip install -r requirements.txt).
  SCAPI credentials (token URL, client credentials, search URL) must be provided by the user.
---

# Demo Shopper Agent Skill

Scaffold and launch a branded shopper agent demo for any SFCC/SCAPI storefront.

## What This Skill Does

Walks the user through four stages:

1. **Brand inputs** — learn about the brand to inform the system prompt
2. **System prompt** — either clone from a matching existing agent or generate fresh from inputs
3. **Configure** — fill in SCAPI credentials and branding
4. **Launch** — start the Streamlit UI

---

## ⚙️ Config

Read `config/defaults.yaml` (sibling of this SKILL.md) for defaults:
- `default_source` — which agent to clone from by default
- `base_port` — starting port for the UI

---

## Primary Workflow: Create a New Agent

### Triggers
- "create a new agent for <brand>"
- "scaffold a demo for <brand>"
- "onboard <brand>"
- "set up a new demo"

---

### Step 1 — Gather brand inputs

Ask these questions **one conversation turn** (not one at a time — batch them):

> *"Let's set up your branded agent. Tell me about the brand:*
> 1. *What's the brand name?*
> 2. *How would you describe the brand's voice and tone? (e.g. premium and expert, fun and youthful, practical and no-nonsense)*
> 3. *What's the agent ID you'd like to use?* (short slug, no spaces — e.g. `acme_us`)"

Use these inputs to infer the brand's domain and product focus. You don't need to ask about product categories or the storefront URL — infer them from the brand name and any context the user gives.

---

### Step 2 — Match to an existing agent or generate fresh

Run `ls agents/` to see what's available, then read each agent's `config.yaml` to understand its domain.

Based on the brand inputs, determine the closest domain match:

| Domain | Best source agent |
|--------|------------------|
| Outdoor gear, hiking, camping, apparel | `NTOManaged` |
| Beauty, skincare, makeup, fragrance, wellness | `shiseido_us` |
| Athletic footwear, sneakers, sportswear | `hibbett` |
| No clear match | Generate fresh |

Present your recommendation to the user:

> *"Based on what you've told me, **[source agent]** is the closest match — it's set up for [domain description] and has a proven system prompt structure we can adapt. Want to use it as the starting point, or would you prefer I write a completely fresh prompt for [brand name]?"*

If no existing agent fits the domain, skip the suggestion and say:
> *"I don't have an existing agent in the same space — I'll write a fresh system prompt tailored to [brand name]."*

#### Option A — Clone and adapt from existing agent

Run:
```bash
python scripts/new_agent.py <agent_id> --from <source> --non-interactive
```

Then **rewrite the system prompt** in `agents/<agent_id>/config.yaml` to be fully contextualised to the new brand. Do not leave the source brand's name, products, or tone in place. Use the brand inputs from Step 1 to rewrite:

- `system_prompt` — replace the role, brand identity, mission, voice, and product categories
- `overlay` — adapt the brand-specific instructions (shipping thresholds, consultation offers, etc.) to what's relevant for this brand
- `examples` — rewrite all few-shot examples using plausible queries and responses for this brand
- `ui.about` — rewrite the sidebar about text
- `ui.starter_queries` — generate 3 relevant starter queries for this brand

#### Option B — Generate fresh prompt from inputs

Do not clone any existing agent. Create `agents/<agent_id>/` manually with:

```bash
mkdir -p agents/<agent_id>
```

Then write `agents/<agent_id>/config.yaml` from scratch using the brand inputs. Structure it identically to existing agents but with all content specific to this brand. Generate:

- `system_prompt` — full prompt covering role, mission, brand voice, tools, response format, and operational constraints
- `overlay` — 4–6 brand-specific behavioural instructions
- `examples` — 2–3 few-shot examples with plausible queries and responses
- `ui` — title, subtitle, icon, about, starter_queries
- `tools` — search_tool_name (`search_<agent_id>_products`), search_description, search_category_hint
- `locales` — default `en_US`, supported list inferred from brand's markets
- `gepa` — `{last_optimized: null, best_score: null, optimization_runs: 0}`

**System prompt quality bar** — the generated prompt must:
- Name the brand and describe its value proposition clearly
- Define the agent's voice and tone in concrete terms (not just "helpful")
- List the tools available with correct tool names for this agent
- Specify the response format (JSON with `thought`, `response`, `follow_up`, `suggestions`)
- Include domain-specific response guidelines (equivalent to Shiseido's skincare guidelines or NTO's gear guidelines)

Show the user a summary of the generated prompt and ask: *"Does this capture the brand correctly? I can adjust the tone, add product categories, or change anything before we proceed."*

---

### Step 3 — Write SCAPI credentials

Say: *"I'll need SCAPI credentials to connect to the storefront. Do you have them handy, or should I proceed and you can fill them in later?"*

Write to `agents/<agent_id>/config.env`:
```
SCAPI_TOKEN_URL=<value or blank>
SCAPI_CLIENT_CREDENTIALS=<value or blank>
SCAPI_SEARCH_URL=<value or blank>
SCAPI_SITE_ID=<agent_id>
SCAPI_LOCALE=en_US
```

Explain what each is:
- **SCAPI_TOKEN_URL** — OAuth token endpoint, ends in `/oauth2/token`
- **SCAPI_CLIENT_CREDENTIALS** — base64-encoded `client_id:client_secret`
- **SCAPI_SEARCH_URL** — product search endpoint, contains `/product-search`
- **SCAPI_SITE_ID** — site ID as configured in Business Manager

If credentials are blank, warn: *"Product search will fail until credentials are filled in — edit `agents/<agent_id>/config.env` when ready."*

Also write `eval_dataset.json` as an empty array:
```bash
echo "[]" > agents/<agent_id>/eval_dataset.json
```

---

### Step 4 — Verify and launch

Check:
- `agents/<agent_id>/config.yaml` exists with `ui.title` and `system_prompt` set
- `agents/<agent_id>/config.env` has `SCAPI_SITE_ID`
- `tools.search_tool_name` is `search_<agent_id>_products`

Ask: *"Ready to launch?"*

Run:
```bash
./start.sh <agent_id>
```

Report the URL and PID.

---

### Output Report

```markdown
## ✅ Agent Created: <agent_id>

| Field | Value |
|-------|-------|
| Agent ID | <agent_id> |
| Brand | <brand name> |
| System prompt | <cloned from <source> and adapted / generated fresh> |
| Config | agents/<agent_id>/config.yaml |
| Credentials | agents/<agent_id>/config.env |
| URL | http://localhost:<port> |

### Next Steps
- [ ] Fill in SCAPI credentials (if not done): `agents/<agent_id>/config.env`
- [ ] Review and tweak the system prompt: `agents/<agent_id>/config.yaml`
- [ ] Add eval cases: `agents/<agent_id>/eval_dataset.json`
- [ ] Commit: `git add agents/<agent_id>/ && git commit -m "Add <agent_id> agent"`
```

---

## Secondary Workflows

### List available agents
Trigger: "what agents exist", "list agents", "what demos do we have"

Run `ls agents/` and read each `config.yaml`. Show:

| Agent ID | Brand | Domain | Port |
|----------|-------|--------|------|

### Launch an existing agent
Trigger: "launch <agent_id>", "start <agent_id>"

Run `./start.sh <agent_id>` and report the URL.

### Check agent status
Trigger: "is <agent_id> running", "what's running"

```bash
pgrep -a python | grep streamlit
```

### Stop all agents
Trigger: "stop all agents", "kill the demos"

```bash
pkill -f 'streamlit run'
```

### Update credentials
Trigger: "update credentials for <agent_id>"

Read current `agents/<agent_id>/config.env`, ask for new values, write back.

### Update system prompt
Trigger: "update the prompt for <agent_id>", "tweak the system prompt"

Read current `agents/<agent_id>/config.yaml`, show the existing `system_prompt` and `overlay`, ask what to change, apply edits directly.

---

## Troubleshooting

**"Product search returns empty"**
- SCAPI credentials wrong or blank — check `agents/<agent_id>/config.env`
- SCAPI_TOKEN_URL must end in `/oauth2/token`
- SCAPI_SEARCH_URL must contain `/product-search`

**"Agent shows wrong brand name or Shiseido content"**
- System prompt wasn't fully rewritten — open `agents/<agent_id>/config.yaml` and check `system_prompt:`, `overlay:`, and `examples:` for leftover source brand content

**"Port already in use"**
- Run `./start.sh <agent_id> <custom_port>`

**"Agent crashes on startup"**
- Check `cat logs/<agent_id>.log`
- Common cause: missing dependencies — run `pip install -r requirements.txt`

**"search_tool_name mismatch"**
- `tools.search_tool_name` in config.yaml must be exactly `search_<agent_id>_products`
- The system prompt must reference the same tool name
