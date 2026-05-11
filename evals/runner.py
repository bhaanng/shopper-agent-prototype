"""
Eval runner for the NTO Shopper Agent.

For each test case:
  1. Optionally runs setup_queries to build conversation history (multi-turn)
  2. Runs the agent on the target query
  3. Sends to LLM judge using the metric's scale (binary / likert / ndcg)
  4. Scores and aggregates by metric

Dataset schema per entry:
  {
    "conversation_id": "NTO_001",
    "query": "I need waterproof hiking boots",
    "setup_queries": ["I hike in the Pacific Northwest", "I prefer mid-cut boots"],  # optional
    "semantic_category": "Basic Search",
    "persona": "novice",
    "proxy": "constrained_choice_framing",
    "proxy_type": "positive",
    "metric": "cognitive_load"
  }

Usage (from nto-agent/ root):
    python scripts/run_evals.py
    python scripts/run_evals.py --customer NTOManaged --dataset data/nto_eval_dataset.json
"""

import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))

from nto_agent import NTOAgent
from site_config import load_site_scapi_env
from evals.metrics import PROXY_INDEX, METRIC_SCALES
from evals.judge import LLMJudge, score_verdict, score_likert, score_ndcg


def _extract_text(response: dict) -> str:
    """Pull markdown text blocks out of the agent's structured response."""
    if not isinstance(response, dict):
        return str(response)
    parts = [
        block.get("content", "")
        for block in response.get("response", [])
        if isinstance(block, dict) and block.get("type") == "markdown"
    ]
    if response.get("follow_up"):
        parts.append(response["follow_up"])
    return "\n\n".join(parts)


def run_evals(
    dataset: list[dict],
    site_id: Optional[str] = None,
    max_workers: int = 3,
    agent_kwargs: dict = None,
) -> dict:
    agent_kwargs = agent_kwargs or {}
    judge = LLMJudge(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url=os.getenv("ANTHROPIC_BASE_URL"),
    )

    def _build_agent():
        senv = load_site_scapi_env(site_id) if site_id else {}
        return NTOAgent(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            base_url=os.getenv("ANTHROPIC_BASE_URL"),
            scapi_token_url=senv.get("SCAPI_TOKEN_URL") or os.getenv("SCAPI_TOKEN_URL"),
            scapi_client_credentials=senv.get("SCAPI_CLIENT_CREDENTIALS") or os.getenv("SCAPI_CLIENT_CREDENTIALS"),
            scapi_search_url=senv.get("SCAPI_SEARCH_URL") or os.getenv("SCAPI_SEARCH_URL"),
            scapi_site_id=senv.get("SCAPI_SITE_ID") or os.getenv("SCAPI_SITE_ID", "NTOManaged"),
            scapi_locale=senv.get("SCAPI_LOCALE") or os.getenv("SCAPI_LOCALE"),
            site_id=site_id,
            **agent_kwargs,
        )

    def _run_case(case: dict) -> dict:
        proxy_name = case["proxy"]
        proxy_type = case["proxy_type"]
        metric = case["metric"]
        query = case["query"]
        setup_queries = case.get("setup_queries", [])

        if proxy_name not in PROXY_INDEX:
            return {**case, "error": f"Unknown proxy: {proxy_name}", "score": None}

        _, proxy_def = PROXY_INDEX[proxy_name]
        definition = proxy_def["definition"]
        scale = METRIC_SCALES.get(metric, "binary")

        agent = _build_agent()
        t0 = time.monotonic()
        agent_error = None

        try:
            # Run setup turns silently to build conversation history
            for setup_q in setup_queries:
                agent.chat(setup_q, max_iterations=2)

            # Evaluated turn
            raw_response = agent.chat(query, max_iterations=3)
            agent_text = _extract_text(raw_response)
        except Exception as e:
            agent_text = ""
            agent_error = str(e)

        agent_ms = int((time.monotonic() - t0) * 1000)

        # Judge
        improvement = None
        if agent_text:
            judgment = judge.judge(query, agent_text, definition, scale=scale)

            if scale == "binary":
                verdict = judgment["verdict"]
                reason = judgment["reason"]
                score = score_verdict(verdict, proxy_type)

            elif scale == "likert":
                raw_score = judgment["score"]
                verdict = str(raw_score) if raw_score is not None else "NA"
                reason = judgment["summary"]
                improvement = judgment["improvement"]
                score = score_likert(raw_score)

            elif scale == "ndcg":
                verdict = f"ndcg={judgment['ndcg']:.3f}"
                reason = f"{len(judgment['product_scores'])} products scored"
                score = score_ndcg(judgment)

            else:
                verdict, reason, score = "NA", "Unknown scale", None

        else:
            verdict = "NA"
            reason = f"Agent error: {agent_error}"
            score = None

        return {
            "conversation_id": case.get("conversation_id", ""),
            "query": query,
            "setup_queries": setup_queries,
            "semantic_category": case.get("semantic_category", ""),
            "persona": case.get("persona", ""),
            "metric": metric,
            "scale": scale,
            "proxy": proxy_name,
            "proxy_type": proxy_type,
            "agent_response": agent_text[:500],
            "verdict": verdict,
            "reason": reason,
            "improvement": improvement,
            "score": score,
            "agent_ms": agent_ms,
            "agent_error": agent_error,
        }

    t_start = time.monotonic()
    results = []

    print(f"Running {len(dataset)} eval cases (max_workers={max_workers})...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_case, case): case for case in dataset}
        done = 0
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            done += 1
            score_str = f"{result['score']:.3f}" if result["score"] is not None else "NA"
            multi = f" [{len(result['setup_queries'])}+1 turns]" if result["setup_queries"] else ""
            print(
                f"  [{done}/{len(dataset)}] {result['conversation_id']}"
                f"{multi} | {result['proxy']} | {result['verdict']} | score={score_str}"
            )

    runtime = time.monotonic() - t_start

    # Aggregate
    metric_buckets: dict[str, list[float]] = defaultdict(list)
    proxy_buckets: dict[str, list[float]] = defaultdict(list)
    all_scores = []

    for r in results:
        if r["score"] is not None:
            metric_buckets[r["metric"]].append(r["score"])
            proxy_buckets[r["proxy"]].append(r["score"])
            all_scores.append(r["score"])

    metric_scores = {m: round(sum(v) / len(v), 3) for m, v in metric_buckets.items()}
    proxy_scores = {p: round(sum(v) / len(v), 3) for p, v in proxy_buckets.items()}
    overall = round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0

    return {
        "results": results,
        "metric_scores": metric_scores,
        "proxy_scores": proxy_scores,
        "overall": overall,
        "total_cases": len(dataset),
        "scored_cases": len(all_scores),
        "runtime_seconds": round(runtime, 1),
    }


def print_report(eval_output: dict) -> None:
    print("\n" + "=" * 60)
    print("NTO AGENT EVAL REPORT")
    print("=" * 60)
    print(f"Overall score : {eval_output['overall']:.1%}  "
          f"({eval_output['scored_cases']}/{eval_output['total_cases']} cases scored)")
    print(f"Runtime       : {eval_output['runtime_seconds']}s\n")

    print("── Scores by metric ──")
    for metric, score in sorted(eval_output["metric_scores"].items(),
                                key=lambda x: x[1]):
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"  {metric:<28} {bar} {score:.1%}")

    print("\n── Bottom 10 proxies (needs attention) ──")
    sorted_proxies = sorted(eval_output["proxy_scores"].items(), key=lambda x: x[1])
    for proxy, score in sorted_proxies[:10]:
        print(f"  {proxy:<48} {score:.1%}")

    print("\n── Top 10 proxies ──")
    for proxy, score in reversed(sorted_proxies[-10:]):
        print(f"  {proxy:<48} {score:.1%}")

    # Surface improvement suggestions for likert cases
    improvements = [
        r for r in eval_output["results"]
        if r.get("improvement") and r["scale"] == "likert"
    ]
    if improvements:
        print(f"\n── Improvement suggestions (likert, score < 5) — top 10 ──")
        for r in sorted(improvements, key=lambda x: x["score"] or 0)[:10]:
            print(f"  [{r['proxy']}] {r['improvement']}")

    print()
