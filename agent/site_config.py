"""
Per-site configuration loader.

Each site lives in sites/<site_id>/ and has:
  config.yaml  — system_prompt, overlay, examples, gepa metadata
  config.env   — SCAPI_TOKEN_URL, SCAPI_CLIENT_CREDENTIALS,
                 SCAPI_SEARCH_URL, SCAPI_SITE_ID
  eval_dataset.json — eval cases for this site

One org (e.g. f_ecom_bbsk_040) can host multiple sites
(e.g. shiseido_us, shiseido_uk) — each gets its own agent instance.
"""

import os
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

from system_prompt import get_system_prompt

SITES_DIR = Path(__file__).parent.parent / "sites"

_OVERLAY_SECTION = """
---

SECTION 5: SITE-SPECIFIC INSTRUCTIONS

The following instructions are specific to this site deployment. They take
precedence over general guidance above where there is a conflict, but they
should not override safety or quality constraints.

{overlay}
"""

_EXAMPLES_SECTION = """
---

SECTION 6: EXAMPLE CONVERSATIONS

The following examples show the expected tone, style, and response quality
for this site. Use them as a reference when crafting your responses.

{examples}
"""

_EXAMPLE_TEMPLATE = """Example {n}:
User: {input}
Assistant: {response}"""


def _load_site_yaml(site_id: str) -> dict:
    if yaml is None:
        raise ImportError("pyyaml is required: pip install pyyaml")
    path = SITES_DIR / site_id / "config.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _render_examples(examples: list) -> str:
    return "\n\n".join(
        _EXAMPLE_TEMPLATE.format(n=i + 1, input=ex["input"], response=ex["response"].strip())
        for i, ex in enumerate(examples)
    )


def get_site_tools(site_id: Optional[str] = None) -> dict:
    """Return tool description overrides for a site.

    Keys: search_description, search_category_hint, details_description, web_search_description.
    Falls back to NTO defaults if not defined.
    """
    defaults = {
        "search_tool_name": "search_nto_products",
        "search_description": "Search the Northern Trail Outfitters catalog for outdoor gear, apparel, and footwear.",
        "search_category_hint": "Category filter: men, women, kids, gear",
        "details_description": "Fetch full details for up to 5 NTO product IDs.",
        "web_search_description": "Search the web for gear reviews, trail conditions, or activity tips.",
    }
    if not site_id:
        return defaults
    data = _load_site_yaml(site_id)
    return {**defaults, **data.get("tools", {})}


def get_site_ui(site_id: Optional[str] = None) -> dict:
    """Return UI branding for a site.

    Keys: title, subtitle, icon, search_label, about, starter_queries.
    Falls back to NTO defaults if not defined.
    """
    defaults = {
        "title": "NTO Trail Advisor",
        "subtitle": "Gear up for your next adventure — hiking, camping, climbing & more",
        "icon": "🏔️",
        "search_label": "🔍 Searching catalog...",
        "about": "Your shopping advisor.",
        "starter_queries": [],
        "chat_placeholder": "Ask me anything...",
    }
    if not site_id:
        return defaults
    data = _load_site_yaml(site_id)
    ui = data.get("ui", {})
    return {**defaults, **ui}


def get_system_prompt_for_site(site_id: Optional[str] = None) -> str:
    """Return the full system prompt for a site.

    If config.yaml has a `system_prompt` key it replaces the shared base prompt.
    Overlay and examples are always appended after.
    """
    if not site_id:
        return get_system_prompt()

    data = _load_site_yaml(site_id)
    result = data.get("system_prompt") or get_system_prompt()

    overlay = data.get("overlay")
    if overlay:
        result += _OVERLAY_SECTION.format(overlay=overlay.strip())

    examples = data.get("examples")
    if examples:
        result += _EXAMPLES_SECTION.format(examples=_render_examples(examples))

    return result


def load_site_scapi_env(site_id: str) -> dict:
    """Load SCAPI credentials from sites/<site_id>/config.env.

    Returns a dict with SCAPI_TOKEN_URL, SCAPI_CLIENT_CREDENTIALS,
    SCAPI_SEARCH_URL, SCAPI_SITE_ID. Falls back to os.environ if file missing.
    """
    path = SITES_DIR / site_id / "config.env"
    if not path.exists():
        return {}
    if dotenv_values is not None:
        return dict(dotenv_values(path))
    # Manual parser fallback
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        values[k.strip()] = v.strip()
    return values


def get_site_locales(site_id: Optional[str] = None) -> dict:
    """Return locale config for a site.

    Returns dict with 'default' (str) and 'supported' (list[str]).
    Falls back to a single-locale config using SCAPI_LOCALE env var or 'en_US'.
    """
    fallback_default = os.environ.get("SCAPI_LOCALE", "en_US")
    fallback = {"default": fallback_default, "supported": [fallback_default]}
    if not site_id:
        return fallback
    data = _load_site_yaml(site_id)
    locales = data.get("locales")
    if not locales:
        return fallback
    default = locales.get("default", fallback_default)
    supported = locales.get("supported", [default])
    return {"default": default, "supported": supported}


def list_sites() -> list[str]:
    """Return all site IDs that have a config directory."""
    if not SITES_DIR.exists():
        return []
    return [p.name for p in sorted(SITES_DIR.iterdir())
            if p.is_dir() and (p / "config.yaml").exists()]


def save_site_overlay(site_id: str, overlay: str, metadata: dict = None) -> None:
    """Write (or overwrite) a site overlay. Used by the GEPA optimizer."""
    if yaml is None:
        raise ImportError("pyyaml is required: pip install pyyaml")

    site_dir = SITES_DIR / site_id
    site_dir.mkdir(parents=True, exist_ok=True)
    path = site_dir / "config.yaml"

    existing = {}
    if path.exists():
        with open(path) as f:
            existing = yaml.safe_load(f) or {}

    existing["overlay"] = overlay
    if metadata:
        existing.setdefault("gepa", {}).update(metadata)

    with open(path, "w") as f:
        yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)
