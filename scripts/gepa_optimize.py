"""
GEPA optimizer for per-site prompt overlays.

Usage:
    python scripts/gepa_optimize.py --site NTOManaged
    python scripts/gepa_optimize.py --site shiseido_us --max-evals 100

What it does:
- Loads the site's current overlay as the seed candidate
- Runs GEPA to iteratively improve the overlay using a test dataset
- Writes the best overlay back to agents/{site_id}/config.yaml
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

from site_config import (
    get_system_prompt_for_site,
    save_site_overlay,
    _load_site_yaml,
    _OVERLAY_SECTION,
)
from system_prompt import get_system_prompt as base_prompt
from nto_agent import NTOAgent

try:
    from gepa.optimize_anything import GEPAConfig, EngineConfig, ReflectionConfig, optimize_anything
except ImportError:
    print("❌  GEPA not installed. Run: pip install gepa pyyaml")
    sys.exit(1)


DEFAULT_EXAMPLES = [
    {
        "input": "I need waterproof hiking boots for a Pacific Northwest trip",
        "criteria": ["waterproof", "boot", "product"],
    },
    {
        "input": "What's a good lightweight jacket for hiking?",
        "criteria": ["jacket", "lightweight", "product"],
    },
    {
        "input": "I'm hiking the Enchantments in October, what gear do I need?",
        "criteria": ["layer", "waterproof", "boot"],
    },
    {
        "input": "Show me camping tents under $200",
        "criteria": ["tent", "price", "product"],
    },
    {
        "input": "What's the difference between down and synthetic insulation?",
        "criteria": ["down", "synthetic", "temperature"],
    },
    {
        "input": "I need gear for a beginner backpacking trip",
        "criteria": ["pack", "tent", "sleep"],
    },
    {
        "input": "Do you have sustainable or recycled outdoor gear?",
        "criteria": ["recycled", "sustainable", "eco"],
    },
    {
        "input": "I want to build a full hiking kit under $300",
        "criteria": ["jacket", "boot", "pack"],
    },
]


def _make_agent(site_id: str, overlay: str) -> NTOAgent:
    """Spin up an agent with the given candidate overlay injected."""
    from site_config import load_site_scapi_env
    senv = load_site_scapi_env(site_id)

    agent = NTOAgent(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url=os.getenv("ANTHROPIC_BASE_URL"),
        scapi_token_url=senv.get("SCAPI_TOKEN_URL") or os.getenv("SCAPI_TOKEN_URL"),
        scapi_client_credentials=senv.get("SCAPI_CLIENT_CREDENTIALS") or os.getenv("SCAPI_CLIENT_CREDENTIALS"),
        scapi_search_url=senv.get("SCAPI_SEARCH_URL") or os.getenv("SCAPI_SEARCH_URL"),
        scapi_site_id=senv.get("SCAPI_SITE_ID") or os.getenv("SCAPI_SITE_ID", site_id),
        site_id=None,  # inject prompt manually below
    )
    # Use site's base prompt + candidate overlay
    data = _load_site_yaml(site_id)
    base = data.get("system_prompt") or base_prompt()
    agent.system_prompt = base + _OVERLAY_SECTION.format(overlay=overlay.strip())
    return agent


def _score_response(response: dict, criteria: list[str]) -> float:
    if not isinstance(response, dict) or "response" not in response:
        return 0.0

    score = 0.3  # valid structure

    response_text = " ".join(
        block.get("content", "")
        for block in response.get("response", [])
        if isinstance(block, dict) and block.get("type") == "markdown"
    ).lower()

    if response_text:
        hits = sum(1 for c in criteria if c.lower() in response_text)
        score += 0.7 * (hits / len(criteria))

    return round(score, 3)


def make_evaluator(site_id: str, examples: list[dict]):
    def evaluate(candidate_overlay: str, batch: list[dict]):
        scores = []
        logs = []

        for ex in batch:
            agent = _make_agent(site_id, candidate_overlay)
            t0 = time.monotonic()
            try:
                response = agent.chat(ex["input"], max_iterations=3)
                score = _score_response(response, ex["criteria"])
                elapsed = (time.monotonic() - t0) * 1000
                logs.append(f"[{score:.2f}] ({elapsed:.0f}ms) {ex['input'][:60]}")
            except Exception as e:
                score = 0.0
                logs.append(f"[0.00] ERROR: {e} | {ex['input'][:60]}")

            scores.append(score)

        avg = sum(scores) / len(scores)
        return avg, {
            "scores": {"accuracy": avg},
            "log": "\n".join(logs),
            "per_example_scores": scores,
        }

    return evaluate


def main():
    parser = argparse.ArgumentParser(description="Run GEPA optimization for a site overlay")
    parser.add_argument("--site", required=True, help="Site ID (e.g. NTOManaged, shiseido_us)")
    parser.add_argument("--max-evals", type=int, default=50)
    parser.add_argument("--examples", type=str, default=None, help="Path to JSON examples file")
    parser.add_argument("--reflection-lm", type=str, default="openai/gpt-4o")
    args = parser.parse_args()

    site_id = args.site

    if args.examples:
        with open(args.examples) as f:
            examples = json.load(f)
    else:
        examples = DEFAULT_EXAMPLES
        print(f"Using {len(examples)} built-in examples (pass --examples path.json to use your own)")

    seed_overlay = _load_site_yaml(site_id).get("overlay")
    if not seed_overlay:
        print(f"⚠️  No overlay found for '{site_id}', starting from empty seed.")
        seed_overlay = "- Provide helpful, accurate product recommendations."

    print(f"\n🚀  GEPA Optimizer — site: {site_id}")
    print(f"   Max evals: {args.max_evals} | Examples: {len(examples)}")
    print(f"   Reflection LM: {args.reflection_lm}")
    print(f"   Seed overlay ({len(seed_overlay)} chars):\n")
    print("   " + seed_overlay[:200].replace("\n", "\n   ") + ("..." if len(seed_overlay) > 200 else ""))
    print()

    evaluator = make_evaluator(site_id, examples)

    split = max(1, len(examples) * 3 // 4)
    trainset = examples[:split]
    valset = examples[split:]

    result = optimize_anything(
        seed_candidate=seed_overlay,
        evaluator=evaluator,
        objective=(
            "Improve the site-specific overlay so the agent gives more relevant, "
            "accurate, and helpful product recommendations. The overlay should add "
            "useful guidance without conflicting with the base prompt."
        ),
        dataset=trainset,
        valset=valset if valset else None,
        config=GEPAConfig(
            engine=EngineConfig(
                max_metric_calls=args.max_evals,
                parallel=False,
                capture_stdio=True,
            ),
            reflection=ReflectionConfig(
                reflection_lm=args.reflection_lm,
                reflection_minibatch_size=2,
            ),
        ),
    )

    best_overlay = result.best_candidate
    best_score = getattr(result, "best_score", None)

    print(f"\n✅  Optimization complete.")
    print(f"   Best score: {best_score}")
    print(f"   Best overlay:\n")
    print("   " + best_overlay[:400].replace("\n", "\n   "))

    save_site_overlay(
        site_id,
        best_overlay,
        metadata={
            "last_optimized": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "best_score": best_score,
            "optimization_runs": 1,
        },
    )
    print(f"\n💾  Saved to agents/{site_id}/config.yaml")


if __name__ == "__main__":
    main()
