"""
Per-customer prompt overlay system.

The base system prompt (system_prompt.py) is shared across all customers and
never modified by GEPA. Each customer has an optional YAML file in customers/
that defines a small overlay injected at the end of the base prompt.

GEPA only evolves the overlay text — the base is always preserved.
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

CUSTOMERS_DIR = Path(__file__).parent.parent / "customers"

_OVERLAY_SECTION = """
---

SECTION 5: CUSTOMER-SPECIFIC INSTRUCTIONS

The following instructions are specific to this customer deployment. They take
precedence over general guidance above where there is a conflict, but they
should not override safety or quality constraints.

{overlay}
"""

_EXAMPLES_SECTION = """
---

SECTION 6: CUSTOMER EXAMPLE CONVERSATIONS

The following examples show the expected tone, style, and response quality
for this customer. Use them as a reference when crafting your responses.

{examples}
"""

_EXAMPLE_TEMPLATE = """Example {n}:
User: {input}
Assistant: {response}"""


def _load_customer_data(customer_id: str) -> dict:
    """Load the full YAML data for a customer. Returns empty dict if not found."""
    if yaml is None:
        raise ImportError("pyyaml is required for customer overlays: pip install pyyaml")

    path = CUSTOMERS_DIR / f"{customer_id}.yaml"
    if not path.exists():
        return {}

    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def load_customer_overlay(customer_id: str) -> Optional[str]:
    """Load the overlay text for a customer. Returns None if no file found."""
    return _load_customer_data(customer_id).get("overlay")


def load_customer_examples(customer_id: str) -> Optional[list]:
    """Load the few-shot examples for a customer. Returns None if none defined."""
    examples = _load_customer_data(customer_id).get("examples")
    return examples if examples else None


def _render_examples(examples: list) -> str:
    """Format a list of {input, response} dicts into prompt text."""
    return "\n\n".join(
        _EXAMPLE_TEMPLATE.format(n=i + 1, input=ex["input"], response=ex["response"].strip())
        for i, ex in enumerate(examples)
    )


def get_system_prompt_for_customer(customer_id: Optional[str] = None) -> str:
    """Return the full system prompt for a customer.

    If the customer YAML contains a `system_prompt` key, that is used as the
    base instead of the shared NTO prompt — enabling fully custom agent personas
    (e.g. Hibbett) without touching the NTO base prompt file.

    Overlay and examples are appended regardless of which base is used.
    """
    if not customer_id:
        return get_system_prompt()

    data = _load_customer_data(customer_id)

    # Customer-specific base prompt overrides the shared NTO prompt
    base = data.get("system_prompt") or get_system_prompt()
    result = base

    overlay = data.get("overlay")
    if overlay:
        result += _OVERLAY_SECTION.format(overlay=overlay.strip())

    examples = data.get("examples")
    if examples:
        result += _EXAMPLES_SECTION.format(examples=_render_examples(examples))

    return result


def load_customer_scapi_env(customer_id: str) -> dict:
    """Load SCAPI credentials from customers/<customer_id>.env.

    Returns a dict with keys: SCAPI_TOKEN_URL, SCAPI_CLIENT_CREDENTIALS,
    SCAPI_SEARCH_URL, SCAPI_SITE_ID. Values are None if the file is missing
    or the key is absent — callers should fall back to os.environ as needed.
    """
    path = CUSTOMERS_DIR / f"{customer_id}.env"
    if not path.exists():
        return {}
    if dotenv_values is None:
        # Manual parser fallback
        values = {}
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip()
        return values
    return dict(dotenv_values(path))


def list_customers() -> list[str]:
    """Return all customer IDs that have a config file."""
    if not CUSTOMERS_DIR.exists():
        return []
    return [p.stem for p in sorted(CUSTOMERS_DIR.glob("*.yaml"))]


def save_customer_overlay(customer_id: str, overlay: str, metadata: dict = None) -> None:
    """Write (or overwrite) a customer overlay file. Used by the GEPA optimizer."""
    if yaml is None:
        raise ImportError("pyyaml is required: pip install pyyaml")

    CUSTOMERS_DIR.mkdir(parents=True, exist_ok=True)
    path = CUSTOMERS_DIR / f"{customer_id}.yaml"

    existing = {}
    if path.exists():
        with open(path, "r") as f:
            existing = yaml.safe_load(f) or {}

    existing["overlay"] = overlay
    if metadata:
        existing.setdefault("gepa", {}).update(metadata)

    with open(path, "w") as f:
        yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)
