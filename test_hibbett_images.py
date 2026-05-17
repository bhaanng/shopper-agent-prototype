#!/usr/bin/env python3
"""
Test that Hibbett agent returns product images after get_product_details enrichment.

Expected behavior:
1. Agent searches catalog (products may have no images)
2. Agent calls get_product_details on top 3-5 products
3. Final response includes products with image URLs from SCAPI Product endpoint
"""
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
    "Show me Jordans",
    "Running shoes under $100",
    "Nike Dunks",
]

def test_images_in_response(query: str):
    """Test that product images are included in final response."""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL")
    env = load_site_scapi_env("hibbett_us")

    agent = ShopperAgent(
        api_key=anthropic_key,
        base_url=anthropic_base_url,
        scapi_token_url=env["SCAPI_TOKEN_URL"],
        scapi_client_credentials=env["SCAPI_CLIENT_CREDENTIALS"],
        scapi_search_url=env["SCAPI_SEARCH_URL"],
        scapi_site_id=env["SCAPI_SITE_ID"],
        scapi_locale=env["SCAPI_LOCALE"],
        site_id="hibbett_us"
    )

    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print('='*60)

    response = agent.chat(query, max_iterations=5)

    tool_log = response.get('tool_call_log', [])

    # Check if get_product_details was called
    get_details_calls = [c for c in tool_log if c['tool'] == 'get_product_details']

    print(f"\n📊 Tool Calls:")
    for call in tool_log:
        print(f"  - {call['tool']}")

    # Parse the response to find product tables
    response_content = response.get('response', [])
    products_with_images = []
    products_without_images = []

    for item in response_content:
        if item.get('type') == 'product_table':
            products = item.get('content', {}).get('products', [])
            for prod in products:
                prod_id = prod.get('id')
                # Check cache for image
                cached = agent.product_cache.get(prod_id, {})
                image_url = cached.get('image_url', '')
                images = cached.get('images', [])

                if image_url or images:
                    products_with_images.append({
                        'id': prod_id,
                        'name': cached.get('name', ''),
                        'image_url': image_url,
                        'images_count': len(images)
                    })
                else:
                    products_without_images.append({
                        'id': prod_id,
                        'name': cached.get('name', '')
                    })

    total_products = len(products_with_images) + len(products_without_images)

    print(f"\n📷 Image Results:")
    print(f"  Total products: {total_products}")
    print(f"  Products with images: {len(products_with_images)}")
    print(f"  Products without images: {len(products_without_images)}")
    print(f"  get_product_details called: {len(get_details_calls)} times")

    if products_with_images:
        print(f"\n✅ Products with images:")
        for p in products_with_images[:3]:  # Show first 3
            print(f"    - {p['name'][:50]}")
            if p['image_url']:
                print(f"      Image URL: {p['image_url'][:60]}...")
            if p['images_count']:
                print(f"      Image count: {p['images_count']}")

    if products_without_images:
        print(f"\n⚠️  Products without images:")
        for p in products_without_images[:3]:  # Show first 3
            print(f"    - {p['id']}: {p['name'][:50]}")

    # Success criteria
    success = (
        len(get_details_calls) > 0 and  # get_product_details was called
        len(products_with_images) > 0 and  # at least some products have images
        len(products_with_images) / max(total_products, 1) >= 0.5  # at least 50% have images
    )

    if success:
        print(f"\n✅ PASS: Images are being fetched and displayed")
        return True
    else:
        print(f"\n❌ FAIL: Image enrichment not working properly")
        if len(get_details_calls) == 0:
            print("   - get_product_details was NOT called")
        if len(products_with_images) == 0:
            print("   - NO products have images")
        elif len(products_with_images) / max(total_products, 1) < 0.5:
            print(f"   - Only {len(products_with_images)}/{total_products} products have images")
        return False


def main():
    print("="*60)
    print("HIBBETT IMAGE ENRICHMENT TEST")
    print("="*60)

    results = []
    for query in TEST_QUERIES:
        success = test_images_in_response(query)
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
