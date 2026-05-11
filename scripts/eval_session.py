"""
Post-session eval: score a recorded live session against all proxies.

Loads a session JSONL, runs each turn through the LLM judge for every
proxy defined in metrics.py, and prints a report.

Usage (from nto-agent/ root):
    # Score a specific session file
    python scripts/eval_session.py logs/sessions/shiseido_us/<session_id>.jsonl

    # Score the most recent session for a site
    python scripts/eval_session.py --site shiseido_us

    # List available sessions
    python scripts/eval_session.py --list [--site shiseido_us]
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from evals.session_logger import load_session, list_sessions
from evals.metrics import PROXY_INDEX, METRIC_SCALES
from evals.judge import LLMJudge, score_verdict, score_likert, score_ndcg


def eval_session(session_path, verbose: bool = False) -> dict:
    session_path = Path(session_path)
    if not session_path.exists():
        print(f"Session file not found: {session_path}")
        return {}
    turns = load_session(session_path)
    if not turns:
        print(f"No turns found in {session_path}")
        return {}

    site_id = turns[0].get("site_id", "unknown")
    session_id = turns[0].get("session_id", session_path.stem)
    print(f"\nEvaluating session {session_id[:12]}... ({len(turns)} turns, site={site_id})")

    judge = LLMJudge(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url=os.getenv("ANTHROPIC_BASE_URL"),
    )

    # Build all (turn, proxy) work items up front
    work_items = [
        (turn, proxy_name, metric, proxy_def)
        for turn in turns
        if turn.get("response")
        for proxy_name, (metric, proxy_def) in PROXY_INDEX.items()
    ]
    total = len(work_items)
    print(f"  {total} judge calls ({len(turns)} turns × {len(PROXY_INDEX)} proxies) — running in parallel...")

    def _judge_one(item):
        turn, proxy_name, metric, proxy_def = item
        proxy_type = proxy_def["type"]
        definition = proxy_def["definition"]
        scale = METRIC_SCALES.get(metric, "binary")
        query = turn["query"]
        response_text = turn["response"]

        judgment = judge.judge(query, response_text, definition, scale=scale)

        if scale == "binary":
            verdict = judgment["verdict"]
            reason = judgment["reason"]
            score = score_verdict(verdict, proxy_type)
        elif scale == "likert":
            raw_score = judgment["score"]
            verdict = str(raw_score) if raw_score is not None else "NA"
            reason = judgment["summary"]
            score = score_likert(raw_score)
        elif scale == "ndcg":
            verdict = f"ndcg={judgment['ndcg']:.3f}"
            reason = f"{len(judgment['product_scores'])} products scored"
            score = score_ndcg(judgment)
        else:
            verdict, reason, score = "NA", "Unknown scale", None

        return {
            "turn": turn["turn"],
            "query": query,
            "metric": metric,
            "proxy": proxy_name,
            "proxy_type": proxy_type,
            "scale": scale,
            "verdict": verdict,
            "reason": reason,
            "score": score,
        }

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_judge_one, item): item for item in work_items}
        for future in as_completed(futures):
            result = futures[future]
            try:
                results.append(future.result())
            except Exception as e:
                turn, proxy_name, *_ = result
                print(f"  ⚠️  Judge error turn={turn['turn']} {proxy_name}: {e}")
            done += 1
            if verbose:
                r = results[-1] if results else {}
                score_str = f"{r.get('score'):.3f}" if r.get('score') is not None else "NA"
                print(f"  [{done}/{total}] turn={r.get('turn')} {r.get('proxy')} | {r.get('verdict')} | {score_str}")

    # Aggregate
    metric_buckets: dict[str, list[float]] = defaultdict(list)
    proxy_buckets: dict[str, list[float]] = defaultdict(list)
    turn_buckets: dict[int, list[float]] = defaultdict(list)
    all_scores = []

    for r in results:
        if r["score"] is not None:
            metric_buckets[r["metric"]].append(r["score"])
            proxy_buckets[r["proxy"]].append(r["score"])
            turn_buckets[r["turn"]].append(r["score"])
            all_scores.append(r["score"])

    metric_scores = {m: round(sum(v) / len(v), 3) for m, v in metric_buckets.items()}
    proxy_scores = {p: round(sum(v) / len(v), 3) for p, v in proxy_buckets.items()}
    turn_scores = {t: round(sum(v) / len(v), 3) for t, v in turn_buckets.items()}
    overall = round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0

    return {
        "session_id": session_id,
        "site_id": site_id,
        "turns": len(turns),
        "results": results,
        "metric_scores": metric_scores,
        "proxy_scores": proxy_scores,
        "turn_scores": turn_scores,
        "overall": overall,
        "scored": len(all_scores),
    }


def print_report(output: dict) -> None:
    print("\n" + "=" * 60)
    print(f"SESSION EVAL REPORT — {output['session_id'][:16]}...")
    print(f"Site: {output['site_id']}  |  Turns: {output['turns']}")
    print("=" * 60)
    print(f"Overall score : {output['overall']:.1%}  ({output['scored']} judgments)\n")

    print("── Score by turn ──")
    for turn, score in sorted(output["turn_scores"].items()):
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"  Turn {turn:<3} {bar} {score:.1%}")

    print("\n── Score by metric ──")
    for metric, score in sorted(output["metric_scores"].items(), key=lambda x: x[1]):
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"  {metric:<28} {bar} {score:.1%}")

    print("\n── Lowest-scoring proxies ──")
    sorted_proxies = sorted(output["proxy_scores"].items(), key=lambda x: x[1])
    for proxy, score in sorted_proxies[:10]:
        print(f"  {proxy:<48} {score:.1%}")

    # Surface reasons for low scores
    low = [r for r in output["results"] if r["score"] is not None and r["score"] < 0.5]
    if low:
        print(f"\n── Low-score details (score < 50%) ──")
        for r in sorted(low, key=lambda x: x["score"])[:10]:
            print(f"  Turn {r['turn']} [{r['proxy']}] {r['verdict']} — {r['reason']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Evaluate a recorded live session")
    parser.add_argument("session_file", nargs="?", help="Path to session JSONL file")
    parser.add_argument("--site", help="Site ID — pick most recent session for this site")
    parser.add_argument("--list", action="store_true", help="List available sessions")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if args.list:
        sessions = list_sessions(site_id=args.site)
        if not sessions:
            print("No session files found.")
            return
        print(f"{'Path':<70} {'Size':>8}  Modified")
        for f in sessions:
            import datetime
            mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            print(f"  {str(f):<68} {f.stat().st_size:>8}B  {mtime}")
        return

    if args.session_file:
        path = Path(args.session_file)
    elif args.site:
        sessions = list_sessions(site_id=args.site, limit=1)
        if not sessions:
            print(f"No sessions found for site '{args.site}'")
            sys.exit(1)
        path = sessions[0]
        print(f"Using most recent session: {path}")
    else:
        parser.print_help()
        sys.exit(1)

    if not path.exists():
        print(f"Session file not found: {path}")
        sys.exit(1)

    output = eval_session(path, verbose=args.verbose)

    if args.as_json:
        print(json.dumps(output, indent=2))
    else:
        print_report(output)


if __name__ == "__main__":
    main()
