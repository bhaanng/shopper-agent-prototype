"""
Quick test script for Sephora Agent
"""

import sys
import os
from pathlib import Path

# Add agent directory to path
sys.path.append(str(Path(__file__).parent / "core"))

from sephora_agent import SephoraAgent
from dotenv import load_dotenv

def test_agent():
    """Test the agent with a simple query"""

    print("💄 Sephora Agent - Quick Test")
    print("="*60)

    # Load API key
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY not found in .env")
        return

    # Initialize agent
    print("📦 Loading agent...")
    base_url = os.getenv("ANTHROPIC_BASE_URL")
    cimulate_api_url = os.getenv("CIMULATE_API_URL")
    cimulate_customer_id = os.getenv("CIMULATE_CUSTOMER_ID")
    cimulate_api_key = os.getenv("CIMULATE_API_KEY")

    agent = SephoraAgent(
        api_key,
        "data/products.json",
        base_url=base_url,
        cimulate_api_url=cimulate_api_url,
        cimulate_customer_id=cimulate_customer_id,
        cimulate_api_key=cimulate_api_key
    )

    if agent.use_cimulate_api:
        print(f"✅ Using Cimulate API: {cimulate_api_url}")
    else:
        print(f"✅ Loaded {len(agent.catalog)} products from local catalog")

    if base_url:
        print(f"🔗 Using custom endpoint: {base_url}\n")
    else:
        print()

    # Test query
    test_query = "Show me foundation for oily skin under $50"

    print(f"🧪 Testing query: '{test_query}'")
    print("-"*60)

    try:
        response = agent.chat(test_query)

        # Display response
        print("\n✅ Agent Response:")
        print("="*60)

        if 'thought' in response:
            print(f"\n💭 Thought:\n{response['thought']}\n")

        if 'response' in response:
            for block in response['response']:
                if block['type'] == 'markdown':
                    print(block['content'])
                    print()

        if 'follow_up' in response and response['follow_up']:
            print(f"❓ Follow-up: {response['follow_up']}\n")

        if 'suggestions' in response and response['suggestions']:
            print("💡 Suggestions:")
            for i, suggestion in enumerate(response['suggestions'], 1):
                print(f"   {i}. {suggestion}")

        print("\n" + "="*60)
        print("✅ Test successful!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_agent()
