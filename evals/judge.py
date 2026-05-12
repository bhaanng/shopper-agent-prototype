"""
LLM-as-judge for NTO agent evals.

Three scoring modes depending on METRIC_SCALES:

  binary  (objective):  Yes/No/NA + one-sentence reason
  likert  (subjective): 1-5 quality score + summary + improvement comment for < 5
  ndcg    (relevancy):  per-product scoring → NDCG@3
"""

import math
import os
import re
import time
from typing import Optional

from anthropic import Anthropic

# ── Binary judge ─────────────────────────────────────────────────────────────

_BINARY_SYSTEM = """\
You are an expert evaluator assessing the quality of an AI shopping assistant for {brand}.

You will be given:
1. The user's query
2. The agent's response
3. A behaviour definition to check for

Determine whether the described behaviour is present in the agent's response.

Reply with EXACTLY this format (no other text):
VERDICT: <Yes|No|NA>
REASON: <one sentence explaining your verdict>

Use NA only when the proxy genuinely cannot be assessed from the response \
(e.g., a multi-turn proxy on a single-turn response).
"""

_BINARY_USER = """\
USER QUERY:
{query}

AGENT RESPONSE:
{response}

BEHAVIOUR TO CHECK:
{definition}
"""

# ── Likert judge ──────────────────────────────────────────────────────────────

_LIKERT_SYSTEM = """\
You are an expert evaluator assessing the quality of an AI shopping assistant for {brand}.

Score the response on this 1–5 scale:
  5 = Exemplary — fully satisfies the dimension, no improvement needed
  4 = Good — mostly satisfies it, one minor improvement possible
  3 = Adequate — partially satisfies it, clear room for improvement
  2 = Poor — barely satisfies it, significant improvement needed
  1 = Very poor or absent

Reply with EXACTLY this format (no other text):
SCORE: <1|2|3|4|5>
SUMMARY: <one sentence describing what the agent did or didn't do>
IMPROVEMENT: <one concrete suggestion, or "None" if score is 5>
"""

_LIKERT_USER = """\
USER QUERY:
{query}

AGENT RESPONSE:
{response}

QUALITY DIMENSION TO ASSESS:
{definition}
"""

# ── NDCG judge ────────────────────────────────────────────────────────────────

_NDCG_SYSTEM = """\
You are a product relevance evaluator for {brand}.

Given a user query and up to 3 products from the agent's response, score each product on:

1. TITLE_SIMILARITY  (0.0–1.0): How closely does the product name/type match what was asked?
2. PRICE_MATCH       (0.0–1.0): Does the price fit the stated budget? (1.0 if no budget stated)
3. FEATURE_OVERLAP   (0.0–1.0): How many key features/attributes from the query are present?
4. RELATIONSHIP      (exact|substitute|complement|irrelevant):
   - exact:       This is precisely what was asked for
   - substitute:  A valid alternative that serves the same need
   - complement:  A related item that pairs well but doesn't fulfill the primary need
   - irrelevant:  Does not address the query at all

Output EXACTLY this format — one PRODUCT block per found product (up to 3), nothing else:

PRODUCT_1:
TITLE_SIMILARITY: <0.0-1.0>
PRICE_MATCH: <0.0-1.0>
FEATURE_OVERLAP: <0.0-1.0>
RELATIONSHIP: <exact|substitute|complement|irrelevant>

PRODUCT_2:
TITLE_SIMILARITY: <0.0-1.0>
...

If fewer than 3 products are shown, only output the blocks that exist.
If no products are shown at all, output: NO_PRODUCTS
"""

_NDCG_USER = """\
USER QUERY:
{query}

AGENT RESPONSE (showing up to first 3 products mentioned):
{response}
"""

# Relationship weights
_REL_WEIGHTS = {
    "exact": 1.0,
    "substitute": 0.9,
    "complement": 0.65,
    "irrelevant": 0.0,
}


_BRAND_DESCRIPTIONS = {
    "NTOManaged": "Northern Trail Outfitters (NTO), an outdoor gear retailer specialising in hiking, camping, climbing, and trail sports",
    "shiseido_us": "Shiseido, a prestige Japanese beauty brand specialising in skincare, makeup, and fragrance",
    "hibbett": "Hibbett Sports, an athletic footwear and sportswear retailer",
}


class LLMJudge:
    def __init__(self, api_key: str = None, base_url: str = None,
                 model: str = "claude-opus-4-7", site_id: str = None):
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if base_url:
            self.client = Anthropic(api_key=api_key, base_url=base_url)
        else:
            self.client = Anthropic(api_key=api_key)
        self.model = model
        self.brand = _BRAND_DESCRIPTIONS.get(site_id, f"a retail brand ({site_id or 'unknown'})")

    def judge(self, query: str, agent_response: str, proxy_definition: str,
              scale: str = "binary") -> dict:
        """Dispatch to the right judge. Returns a scale-appropriate dict."""
        if scale == "likert":
            return self._judge_likert(query, agent_response, proxy_definition)
        if scale == "ndcg":
            return self._judge_ndcg(query, agent_response)
        return self._judge_binary(query, agent_response, proxy_definition)

    def _judge_binary(self, query: str, agent_response: str,
                      proxy_definition: str) -> dict:
        raw = self._call(
            _BINARY_SYSTEM.format(brand=self.brand),
            _BINARY_USER.format(query=query, response=agent_response[:3000],
                                definition=proxy_definition),
            max_tokens=256,
        )
        verdict, reason = _parse_binary(raw)
        return {"verdict": verdict, "reason": reason, "raw": raw}

    def _judge_likert(self, query: str, agent_response: str,
                      proxy_definition: str) -> dict:
        raw = self._call(
            _LIKERT_SYSTEM.format(brand=self.brand),
            _LIKERT_USER.format(query=query, response=agent_response[:3000],
                                definition=proxy_definition),
            max_tokens=384,
        )
        score, summary, improvement = _parse_likert(raw)
        return {"score": score, "summary": summary,
                "improvement": improvement, "raw": raw}

    def _judge_ndcg(self, query: str, agent_response: str) -> dict:
        raw = self._call(
            _NDCG_SYSTEM.format(brand=self.brand),
            _NDCG_USER.format(query=query, response=agent_response[:3000]),
            max_tokens=512,
        )
        product_scores = _parse_ndcg(raw)
        ndcg = _compute_ndcg(product_scores, k=3)
        return {"product_scores": product_scores, "ndcg": ndcg, "raw": raw}

    def _call(self, system: str, user: str, max_tokens: int) -> str:
        for attempt in range(5):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return response.content[0].text.strip()
            except Exception as e:
                if "429" in str(e) and attempt < 4:
                    wait = 2 ** attempt * 15  # 15s, 30s, 60s, 120s
                    print(f"  ⏳ Judge rate limit, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_binary(text: str) -> tuple[str, str]:
    verdict_match = re.search(r"VERDICT:\s*(Yes|No|NA)", text, re.IGNORECASE)
    reason_match = re.search(r"REASON:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    verdict = verdict_match.group(1).capitalize() if verdict_match else "NA"
    reason = reason_match.group(1).strip().split("\n")[0] if reason_match else ""
    return verdict, reason


def _parse_likert(text: str) -> tuple[Optional[int], str, Optional[str]]:
    score_match = re.search(r"SCORE:\s*([1-5])", text)
    summary_match = re.search(r"SUMMARY:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    imp_match = re.search(r"IMPROVEMENT:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    score = int(score_match.group(1)) if score_match else None
    summary = summary_match.group(1).strip().split("\n")[0] if summary_match else ""
    raw_imp = imp_match.group(1).strip().split("\n")[0] if imp_match else None
    improvement = None if (raw_imp or "").lower() == "none" else raw_imp
    return score, summary, improvement


def _parse_ndcg(text: str) -> list[dict]:
    """Parse up to 3 PRODUCT_N blocks into a list of score dicts."""
    if "NO_PRODUCTS" in text.upper():
        return []

    products = []
    for i in range(1, 4):
        block_match = re.search(
            rf"PRODUCT_{i}:(.*?)(?=PRODUCT_{i+1}:|$)", text,
            re.DOTALL | re.IGNORECASE,
        )
        if not block_match:
            continue
        block = block_match.group(1)

        def _float(field: str) -> float:
            m = re.search(rf"{field}:\s*([0-9.]+)", block, re.IGNORECASE)
            return float(m.group(1)) if m else 0.0

        def _str(field: str) -> str:
            m = re.search(rf"{field}:\s*(\w+)", block, re.IGNORECASE)
            return m.group(1).lower() if m else "irrelevant"

        products.append({
            "title_similarity": _float("TITLE_SIMILARITY"),
            "price_match": _float("PRICE_MATCH"),
            "feature_overlap": _float("FEATURE_OVERLAP"),
            "relationship": _str("RELATIONSHIP"),
        })

    return products


def _compute_ndcg(product_scores: list[dict], k: int = 3) -> float:
    """
    NDCG@k where relevance_i = mean(title_sim, price_match, feature_overlap)
                                * relationship_weight

    Ideal DCG assumes all k slots have relevance 1.0.
    Returns 0.0 if no products were found.
    """
    if not product_scores:
        return 0.0

    def _rel(p: dict) -> float:
        base = (p["title_similarity"] + p["price_match"] + p["feature_overlap"]) / 3.0
        weight = _REL_WEIGHTS.get(p["relationship"], 0.0)
        return base * weight

    dcg = sum(
        _rel(p) / math.log2(i + 2)
        for i, p in enumerate(product_scores[:k])
    )
    ideal_dcg = sum(1.0 / math.log2(i + 2) for i in range(min(k, len(product_scores))))
    return round(dcg / ideal_dcg, 4) if ideal_dcg > 0 else 0.0


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_verdict(verdict: str, proxy_type: str) -> Optional[float]:
    """Binary: positive+Yes→1.0, positive+No→0.0, negative+No→1.0, NA→None."""
    if verdict == "NA":
        return None
    if proxy_type == "positive":
        return 1.0 if verdict == "Yes" else 0.0
    return 1.0 if verdict == "No" else 0.0


def score_likert(score: Optional[int]) -> Optional[float]:
    """Likert 1-5 → [0.0, 1.0] via (score-1)/4."""
    if score is None:
        return None
    return (score - 1) / 4.0


def score_ndcg(judgment: dict) -> Optional[float]:
    """Return the pre-computed NDCG value, or None if no products found."""
    ndcg = judgment.get("ndcg")
    return ndcg if ndcg is not None else None
