#!/usr/bin/env python3
"""Test that Shiseido agent uses waterfall strategy with SCAPI refinements"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "core"))

from shopper_agent import ShopperAgent
from site_config import load_site_scapi_env
from dotenv import load_dotenv

load_dotenv()

TEST_QUERIES = [
    "Show me anti-aging serums for dry skin",
    "Moisturizer under $100",
    "Vitamin C brightening products",
]

def test_waterfall_strategy(query: str):
    """Test that agent uses waterfall queries with refinements."""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL")
    env = load_site_scapi_env("shiseido_us")

    agent = ShopperAgent(
        api_key=anthropic_key,
        base_url=anthropic_base_url,
        scapi_token_url=env["SCAPI_TOKEN_URL"],
        scapi_client_credentials=env["SCAPI_CLIENT_CREDENTIALS"],
        scapi_search_url=env["SCAPI_SEARCH_URL"],
        scapi_site_id=env["SCAPI_SITE_ID"],
        scapi_locale=env["SCAPI_LOCALE"],
        site_id="shiseido_us"
    )

    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print('='*60)

    response = agent.chat(query, max_iterations=5)

    tool_log = response.get('tool_call_log', [])

    # Find search calls
    search_calls = [c for c in tool_log if c['tool'] == 'search_shiseido_products']

    if not search_calls:
        print("❌ No search calls found")
        return False

    print(f"\n📊 Search calls: {len(search_calls)}")

    success = True
    for i, call in enumerate(search_calls):
        queries = call.get('input', {}).get('queries', [])
        print(f"\n  Search call {i+1}: {len(queries)} queries")

        has_refinements = False
        for j, q in enumerate(queries):
            q_text = q.get('q', '')
            refine = q.get('refine', '')
            if refine:
                has_refinements = True
                print(f"    Query {j+1}: q='{q_text}', refine='{refine}'")
            else:
                print(f"    Query {j+1}: q='{q_text}' (no refinements)")

        if not has_refinements:
            print(f"  ⚠️  No refinements used in this search call")
            success = False

    # Check if get_product_details was called
    get_details_calls = [c for c in tool_log if c['tool'] == 'get_product_details']
    print(f"\n📷 get_product_details calls: {len(get_details_calls)}")

    if success and has_refinements:
        print(f"\n✅ PASS: Waterfall strategy with refinements working")
    else:
        print(f"\n❌ FAIL: Refinements not being used properly")

    return success


def main():
    print("="*60)
    print("SHISEIDO WATERFALL STRATEGY TEST")
    print("="*60)

    results = []
    for query in TEST_QUERIES:
        success = test_waterfall_strategy(query)
        results.append({
            'query': query,
            'success': success
        })

    # Summary
    print("\n\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    passed = sum(1 for r in results if r['success'])
    total = len(results)

    print(f"\nTests passed: {passed}/{total}")

    for r in results:
        status = "✅" if r['success'] else "❌"
        print(f"  {status} {r['query']}")

    if passed == total:
        print("\n✅ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
