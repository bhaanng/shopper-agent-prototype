#!/usr/bin/env python3
"""Extract comprehensive facet metadata for Shiseido by searching skincare/beauty terms"""
import sys
import json
import os
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent / "core"))

from site_config import load_site_scapi_env
from shopper_agent import ShopperAgent

if Path('.env').exists():
    __import__('dotenv').load_dotenv('.env')

site_id = "shiseido_us"
env = load_site_scapi_env(site_id)

agent = ShopperAgent(
    api_key=os.getenv('ANTHROPIC_API_KEY'),
    base_url=os.getenv('ANTHROPIC_BASE_URL'),
    scapi_token_url=env['SCAPI_TOKEN_URL'],
    scapi_client_credentials=env['SCAPI_CLIENT_CREDENTIALS'],
    scapi_search_url=env['SCAPI_SEARCH_URL'],
    scapi_site_id=env['SCAPI_SITE_ID'],
    scapi_locale=env['SCAPI_LOCALE'],
    site_id=site_id
)

token = agent._get_access_token()

print(f"\n{'='*60}")
print(f"SHISEIDO COMPREHENSIVE FACET EXTRACTION")
print('='*60)

# Search by categories and popular beauty terms to get comprehensive facets
search_queries = [
    # Categories
    {'refine': 'cgid=skincare'},
    {'refine': 'cgid=makeup'},
    {'refine': 'cgid=fragrance'},
    {'refine': 'cgid=sets'},
    {'refine': 'cgid=mens'},
    # Product types - skincare
    {'q': 'serum'},
    {'q': 'moisturizer'},
    {'q': 'cleanser'},
    {'q': 'eye cream'},
    {'q': 'mask'},
    {'q': 'toner'},
    {'q': 'essence'},
    {'q': 'sunscreen'},
    {'q': 'treatment'},
    # Product types - makeup
    {'q': 'foundation'},
    {'q': 'lipstick'},
    {'q': 'mascara'},
    {'q': 'eyeshadow'},
    {'q': 'blush'},
    # Concerns
    {'q': 'anti-aging'},
    {'q': 'hydrating'},
    {'q': 'brightening'},
    {'q': 'firming'},
    # Collections
    {'q': 'ultimune'},
    {'q': 'benefiance'},
    {'q': 'essential energy'},
    {'q': 'vital perfection'},
]

all_facets = defaultdict(lambda: {
    'label': '',
    'values': {}
})

import requests

for query in search_queries:
    label = query.get('q') or query.get('refine', 'unknown')
    print(f"\n[{label}] Searching...")

    params = {
        'siteId': env['SCAPI_SITE_ID'],
        'limit': 20
    }
    if 'q' in query:
        params['q'] = query['q']
    if 'refine' in query:
        params['refine'] = query['refine']

    resp = requests.get(
        env['SCAPI_SEARCH_URL'],
        params=params,
        headers={'Authorization': f'Bearer {token}'},
        timeout=15
    )

    if resp.status_code != 200:
        print(f"  ❌ Failed: {resp.status_code}")
        continue

    data = resp.json()
    refinements = data.get('refinements', [])

    if not refinements:
        print(f"  (no refinements)")
        continue

    # Merge refinements
    for ref in refinements:
        attr_id = ref.get('attributeId', 'unknown')
        label = ref.get('label', '')
        values = ref.get('values', [])

        if not all_facets[attr_id]['label']:
            all_facets[attr_id]['label'] = label

        # Merge values
        for v in values:
            val_id = v.get('value')
            val_label = v.get('label', val_id)
            val_count = v.get('hitCount', 0)

            if val_id not in all_facets[attr_id]['values']:
                all_facets[attr_id]['values'][val_id] = {
                    'label': val_label,
                    'total_count': val_count
                }
            else:
                all_facets[attr_id]['values'][val_id]['total_count'] += val_count

    print(f"  ✓ {len(refinements)} refinement types")

# Display summary
print(f"\n{'='*60}")
print("COMPREHENSIVE FACET SUMMARY")
print('='*60)

for attr_id in sorted(all_facets.keys()):
    facet = all_facets[attr_id]
    values = facet['values']
    print(f"\n[{attr_id}] {facet['label']}")
    print(f"  Values: {len(values)}")
    for val_id in list(values.keys())[:10]:
        val = values[val_id]
        print(f"    - {val_id} | {val['label']} ({val['total_count']} products)")
    if len(values) > 10:
        print(f"    ... and {len(values) - 10} more")

# Save
output = {
    'site_id': site_id,
    'facets': {
        attr_id: {
            'label': facet['label'],
            'values': [
                {
                    'value': val_id,
                    'label': val['label'],
                    'total_count': val['total_count']
                }
                for val_id, val in facet['values'].items()
            ]
        }
        for attr_id, facet in all_facets.items()
    }
}

output_file = Path(__file__).parent / 'agents' / site_id / 'comprehensive_facets.json'
with open(output_file, 'w') as f:
    json.dump(output, f, indent=2)

print(f"\n✓ Comprehensive facets saved to: {output_file}")
print(f"✓ Total facets: {len(all_facets)}")
