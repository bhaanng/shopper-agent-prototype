---
name: demo-shopper-agent
description: |
  Scaffold, configure, and launch a branded shopper agent demo in minutes. Clones an
  existing agent (NTOManaged or shiseido_us), sets up SCAPI credentials, customises
  branding, and starts the Streamlit UI. Use this skill whenever the user wants to:
  create a new demo, onboard a new brand, clone an agent, set up credentials, launch
  an agent, or list available agents.
compatibility: |
  Must be run from the nto-agent repo root (scripts/new_agent.py must exist).
  Requires Python 3.10+, pyyaml, and streamlit installed (pip install -r requirements.txt).
  SCAPI credentials (token URL, client credentials, search URL) must be provided by the user.
---

# Demo Shopper Agent Skill

Scaffold and launch a branded shopper agent demo for any SFCC/SCAPI storefront.

## What This Skill Does

Walks the user through three stages:

1. **Scaffold** — clone an existing agent into `agents/<new_id>/`
2. **Configure** — fill in SCAPI credentials and brand identity
3. **Launch** — start the Streamlit UI and verify it's running

---

## ⚙️ Config

Read `config/defaults.yaml` (sibling of this SKILL.md) for defaults:
- `default_source` — which agent to clone from by default
- `available_sources` — list of cloneable agents
- `required_env_vars` — SCAPI fields the user must supply
- `base_port` — starting port for the UI

---

## Primary Workflow: Create a New Agent

### Triggers
- "create a new agent for <brand>"
- "scaffold a demo for <brand>"
- "clone the shiseido agent for <brand>"
- "onboard <brand>"
- "set up a new demo"

### Step 1 — Gather inputs

Ask the user for:
1. **Agent ID** — short slug, no spaces (e.g. `acme_us`, `nordstrom_us`). Suggest `<brand>_<locale>` format.
2. **Source agent** — which existing agent to clone from (default: `NTOManaged`). Show the full list of available agents by running `ls agents/` — any agent with a `config.yaml` is a valid source. The user can pick any of them.
3. **Brand name** — full display name (e.g. "ACME Sports")
4. **Tagline** — one-line subtitle for the UI (e.g. "Your personal sports gear advisor")
5. **Icon emoji** — shown in the UI header (e.g. 🏃)

Then ask for SCAPI credentials. Explain what each is for:
- **SCAPI_TOKEN_URL** — OAuth token endpoint (e.g. `https://<shortcode>.api.commercecloud.salesforce.com/shopper/auth/v1/organizations/<org>/oauth2/token`)
- **SCAPI_CLIENT_CREDENTIALS** — base64-encoded `client_id:client_secret`
- **SCAPI_SEARCH_URL** — product search endpoint (e.g. `https://<shortcode>.api.commercecloud.salesforce.com/search/shopper-search/v1/organizations/<org>/product-search`)
- **SCAPI_SITE_ID** — the storefront site ID (often same as agent ID)

Say: *"I'll need SCAPI credentials to connect to the storefront. Do you have them handy, or should I scaffold first and you can fill them in later?"*

If they want to fill in later: proceed to Step 2 with blank credentials.

### Step 2 — Run the scaffold script

Run `ls agents/` to confirm the source exists, then:

```bash
python scripts/new_agent.py <agent_id> --from <source> --non-interactive
```

Then update branding in `agents/<agent_id>/config.yaml`:
- Set `ui.title` to the brand name + "Advisor" (e.g. "ACME Sports Advisor")
- Set `ui.subtitle` to the tagline
- Set `ui.icon` to the emoji
- Set `tools.search_tool_name` to `search_<agent_id>_products`

Use the Edit tool to apply these changes directly — do not ask the user to edit manually.

### Step 3 — Write SCAPI credentials

Write to `agents/<agent_id>/config.env`:
```
SCAPI_TOKEN_URL=<value or blank>
SCAPI_CLIENT_CREDENTIALS=<value or blank>
SCAPI_SEARCH_URL=<value or blank>
SCAPI_SITE_ID=<agent_id>
SCAPI_LOCALE=en_US
```

If credentials were provided, fill them in. If not, leave blank and remind the user to fill them before launching.

### Step 4 — Verify before launch

Check that:
- `agents/<agent_id>/config.yaml` exists and has `ui.title` set
- `agents/<agent_id>/config.env` has at least `SCAPI_SITE_ID` set
- If any credential is blank, warn: *"SCAPI credentials are missing — the agent will launch but product search will fail until you fill in `agents/<agent_id>/config.env`."*

### Step 5 — Launch

Ask: *"Ready to launch? I'll start the agent on the next available port."*

Run:
```bash
./start.sh <agent_id>
```

Report back the URL (e.g. `http://localhost:8502`) and PID. Tell the user to open it in their browser.

### Output Report

```markdown
## ✅ Agent Created: <agent_id>

| Field | Value |
|-------|-------|
| Agent ID | <agent_id> |
| Cloned from | <source> |
| Config | agents/<agent_id>/config.yaml |
| Credentials | agents/<agent_id>/config.env |
| URL | http://localhost:<port> |

### Next Steps
- [ ] Fill in SCAPI credentials (if not done): `agents/<agent_id>/config.env`
- [ ] Customise the system prompt: edit `system_prompt:` in `agents/<agent_id>/config.yaml`
- [ ] Add eval cases: `agents/<agent_id>/eval_dataset.json`
- [ ] Commit: `git add agents/<agent_id>/ && git commit -m "Add <agent_id> agent"`
```

---

## Secondary Workflows

### List available agents
Trigger: "what agents exist", "list agents", "what demos do we have"

```bash
ls agents/
```

Show a table: Agent ID | Title (from config.yaml ui.title) | Port (alphabetical from 8501).

### Launch an existing agent
Trigger: "launch <agent_id>", "start <agent_id>", "run the shiseido demo"

Run `./start.sh <agent_id>` and report the URL.

### Check agent status
Trigger: "is <agent_id> running", "what's running"

```bash
pgrep -a python | grep streamlit
```

Show running agents and their ports.

### Stop all agents
Trigger: "stop all agents", "kill the demos"

Run: `pkill -f 'streamlit run'`

### Update credentials
Trigger: "update credentials for <agent_id>", "change SCAPI config for <agent_id>"

Read the current `agents/<agent_id>/config.env`, ask for the new values, write back.

---

## Troubleshooting

**"No agents found in agents/"**
- Check you're in the repo root: `ls agents/` should show at least `NTOManaged`
- If missing, the repo may not be fully cloned

**"Product search returns empty"**
- SCAPI credentials are likely wrong or blank — open `agents/<agent_id>/config.env`
- Verify SCAPI_TOKEN_URL format: must end in `/oauth2/token`
- Verify SCAPI_SEARCH_URL: must include the org ID

**"Agent crashes on startup"**
- Check logs: `cat logs/<agent_id>.log`
- Common cause: missing `pyyaml` or `streamlit` — run `pip install -r requirements.txt`

**"Port already in use"**
- Run `./start.sh <agent_id> <custom_port>` with a free port

**"Config.yaml looks wrong after scaffold"**
- The scaffold copies from source — check `ui:` and `tools:` sections are correct
- The search_tool_name must match the function name Claude uses: `search_<agent_id>_products`
