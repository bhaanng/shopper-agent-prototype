"""
Scaffold a new branded agent from an existing one.

Usage:
    python scripts/new_agent.py <new_agent_id> [--from <source_agent_id>]

Examples:
    python scripts/new_agent.py acme_us
    python scripts/new_agent.py acme_us --from shiseido_us
    python scripts/new_agent.py acme_us --from NTOManaged --non-interactive

What it does:
  1. Copies agents/<source>/ → agents/<new_agent_id>/
  2. Clears out SCAPI credentials in config.env (must be filled in)
  3. Prompts for basic branding (title, subtitle, icon) to update config.yaml
  4. Prints next steps
"""

import argparse
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ pyyaml required: pip install pyyaml")
    sys.exit(1)

AGENTS_DIR = Path(__file__).parent.parent / "agents"
DEFAULT_SOURCE = "shiseido_us"


def list_agents():
    if not AGENTS_DIR.exists():
        return []
    return [p.name for p in sorted(AGENTS_DIR.iterdir())
            if p.is_dir() and (p / "config.yaml").exists()]


def prompt(question, default=None):
    suffix = f" [{default}]" if default else ""
    answer = input(f"{question}{suffix}: ").strip()
    return answer if answer else default


def scaffold(new_id: str, source_id: str, interactive: bool = True):
    source_dir = AGENTS_DIR / source_id
    target_dir = AGENTS_DIR / new_id

    if not source_dir.exists():
        print(f"❌ Source agent '{source_id}' not found in agents/")
        print(f"   Available: {list_agents()}")
        sys.exit(1)

    if target_dir.exists():
        print(f"❌ Agent '{new_id}' already exists at {target_dir}")
        sys.exit(1)

    # Copy source → target
    shutil.copytree(source_dir, target_dir)
    print(f"✅ Copied agents/{source_id}/ → agents/{new_id}/")

    # Clear SCAPI credentials
    env_path = target_dir / "config.env"
    env_path.write_text(
        f"SCAPI_TOKEN_URL=\n"
        f"SCAPI_CLIENT_CREDENTIALS=\n"
        f"SCAPI_SEARCH_URL=\n"
        f"SCAPI_SITE_ID={new_id}\n"
        f"SCAPI_LOCALE=en_US\n"
    )
    print(f"✅ Cleared credentials in agents/{new_id}/config.env")

    # Load config.yaml
    yaml_path = target_dir / "config.yaml"
    with open(yaml_path) as f:
        config = yaml.safe_load(f) or {}

    if interactive:
        print(f"\n── Brand your agent (press Enter to keep current value) ──\n")
        current_ui = config.get("ui", {})

        title = prompt("Agent title", current_ui.get("title", "My Shopping Advisor"))
        subtitle = prompt("Subtitle", current_ui.get("subtitle", "Your personal shopping assistant"))
        icon = prompt("Icon emoji", current_ui.get("icon", "🛍️"))
        about = prompt("About text (one line)", current_ui.get("about", "Your shopping advisor."))

        config.setdefault("ui", {})
        config["ui"]["title"] = title
        config["ui"]["subtitle"] = subtitle
        config["ui"]["icon"] = icon
        config["ui"]["about"] = about

        # Reset search tool name
        config.setdefault("tools", {})
        default_tool_name = f"search_{new_id}_products"
        tool_name = prompt("Search tool name", default_tool_name)
        config["tools"]["search_tool_name"] = tool_name

        # Reset gepa metadata
        config["gepa"] = {"last_optimized": None, "best_score": None, "optimization_runs": 0}

        with open(yaml_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        print(f"\n✅ Updated agents/{new_id}/config.yaml")

    else:
        # Non-interactive: just fix the tool name and clear gepa
        config.setdefault("tools", {})
        config["tools"]["search_tool_name"] = f"search_{new_id}_products"
        config["gepa"] = {"last_optimized": None, "best_score": None, "optimization_runs": 0}
        with open(yaml_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        print(f"✅ Updated agents/{new_id}/config.yaml (non-interactive)")

    # Clear eval dataset
    eval_path = target_dir / "eval_dataset.json"
    eval_path.write_text("[]")
    print(f"✅ Cleared agents/{new_id}/eval_dataset.json (add your own eval cases)")

    print(f"""
── Next steps ──────────────────────────────────────────────

1. Fill in SCAPI credentials:
   agents/{new_id}/config.env

2. Customise your system prompt and overlay:
   agents/{new_id}/config.yaml

3. Launch your agent:
   ./start.sh {new_id}

4. (Optional) Add eval cases:
   agents/{new_id}/eval_dataset.json

────────────────────────────────────────────────────────────
""")


def main():
    parser = argparse.ArgumentParser(description="Scaffold a new branded agent")
    parser.add_argument("agent_id", help="New agent ID (e.g. acme_us)")
    parser.add_argument("--from", dest="source", default=DEFAULT_SOURCE,
                        help=f"Source agent to clone from (default: {DEFAULT_SOURCE})")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Skip prompts — just copy and fix tool name")
    args = parser.parse_args()

    available = list_agents()
    if not available:
        print("❌ No agents found in agents/. Make sure you're in the repo root.")
        sys.exit(1)

    if args.source not in available:
        print(f"❌ Source '{args.source}' not found. Available: {available}")
        sys.exit(1)

    print(f"\n🚀 Creating agent '{args.agent_id}' from '{args.source}'...\n")
    scaffold(args.agent_id, args.source, interactive=not args.non_interactive)


if __name__ == "__main__":
    main()
