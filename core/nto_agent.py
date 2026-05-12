"""
Northern Trail Outfitters (NTO) Shopping Agent
Uses Claude API with custom tools to search NTO's catalog via Salesforce Commerce Cloud (SCAPI)
"""

import json
import os
import re
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from anthropic import Anthropic
from duckduckgo_search import DDGS
from site_config import get_system_prompt_for_site, get_site_tools, get_site_locales


def _ms(start: float) -> str:
    return f"{(time.monotonic() - start) * 1000:.0f}ms"


class NTOAgent:
    def __init__(self, api_key: str, base_url: str = None,
                 scapi_token_url: str = None, scapi_client_credentials: str = None,
                 scapi_search_url: str = None, scapi_site_id: str = "NTOManaged",
                 scapi_locale: str = None,
                 site_id: str = None):

        if base_url:
            self.client = Anthropic(api_key=api_key, base_url=base_url)
            self.model = "us.anthropic.claude-sonnet-4-6"
        else:
            self.client = Anthropic(api_key=api_key)
            self.model = "claude-opus-4-7"

        # SCAPI configuration
        self.scapi_token_url = scapi_token_url
        self.scapi_client_credentials = scapi_client_credentials
        self.scapi_search_url = scapi_search_url
        self.scapi_site_id = scapi_site_id
        self.scapi_locale = scapi_locale  # site default locale

        # Per-session locale — set once on first user message via langdetect
        self._locale_config = get_site_locales(site_id)
        self._session_locale: Optional[str] = None  # None = not yet detected

        # Token cache — lock prevents concurrent threads from double-minting
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._token_lock = threading.Lock()

        # Product cache for details lookups
        self.product_cache: Dict[str, Dict] = {}

        self.site_id = site_id
        self.system_prompt = get_system_prompt_for_site(site_id)
        self._tool_config = get_site_tools(site_id)
        self._search_tool_name = self._tool_config.get("search_tool_name", "search_nto_products")
        self.conversation_history = []

    # ── SCAPI token management ──────────────────────────────────────────────

    def _get_access_token(self) -> str:
        """Return a valid bearer token, refreshing if within 60s of expiry."""
        with self._token_lock:
            if self._access_token and time.monotonic() < self._token_expires_at - 60:
                return self._access_token

            t0 = time.monotonic()
            resp = requests.post(
                self.scapi_token_url,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {self.scapi_client_credentials}",
                },
                data={
                    "grant_type": "client_credentials",
                    "channel_id": self.scapi_site_id,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires_at = time.monotonic() + data.get("expires_in", 1800)
            print(f"  ⏱  SCAPI token refresh: {_ms(t0)}")
            return self._access_token

    # ── Locale detection ────────────────────────────────────────────────────

    def _detect_and_set_locale(self, text: str, trace_fn=None) -> None:
        """Detect language from text and map to a supported locale (called once per session)."""
        if self._session_locale is not None:
            return
        try:
            from langdetect import detect
            lang = detect(text)  # e.g. 'ja', 'en', 'zh-cn'
        except Exception:
            self._session_locale = self._locale_config["default"]
            return

        # Build maps: full lang code (e.g. "zh-cn") and prefix (e.g. "zh") → locale
        full_map: dict[str, str] = {}
        prefix_map: dict[str, str] = {}
        for loc in self._locale_config["supported"]:
            # locale format: en_US, zh_CN — normalize to zh-cn for matching
            normalized = loc.replace("_", "-").lower()
            full_map[normalized] = loc
            prefix = normalized.split("-")[0]
            if prefix not in prefix_map:
                prefix_map[prefix] = loc

        lang_norm = lang.lower()
        lang_prefix = lang_norm.split("-")[0]
        resolved = (
            full_map.get(lang_norm)
            or prefix_map.get(lang_prefix)
            or self._locale_config["default"]
        )
        self._session_locale = resolved
        if resolved != self._locale_config["default"]:
            msg = f"🌐 Detected language `{lang}` → locale set to `{resolved}`"
            print(f"  {msg}")
            if trace_fn:
                trace_fn(msg)

    @property
    def _active_locale(self) -> Optional[str]:
        """Return the session locale if detected, else fall back to site default."""
        return self._session_locale or self.scapi_locale

    # ── SCAPI product detail ────────────────────────────────────────────────

    def fetch_product_detail(self, product_id: str) -> Dict:
        """Fetch rich product detail from SCAPI shopper-products API."""
        try:
            token = self._get_access_token()
            # Derive shopper-products base from search URL
            # search: .../search/shopper-search/v1/organizations/<org>/product-search
            # detail: .../product/shopper-products/v1/organizations/<org>/products/<id>
            base = re.sub(r"/search/shopper-search/.*", "", self.scapi_search_url)
            org = re.search(r"/organizations/([^/]+)/", self.scapi_search_url)
            org_id = org.group(1) if org else ""
            url = f"{base}/product/shopper-products/v1/organizations/{org_id}/products/{product_id}"
            params = {"siteId": self.scapi_site_id, "allImages": "true"}
            if self._active_locale:
                params["locale"] = self._active_locale.replace("_", "-")
            resp = requests.get(url, params=params,
                                headers={"Authorization": f"Bearer {token}"}, timeout=15)
            if resp.status_code != 200:
                return self.product_cache.get(product_id, {})
            data = resp.json()
            # Extract variation images keyed by color/size
            images = []
            for img_group in data.get("imageGroups", []):
                view = img_group.get("viewType", "")
                for img in img_group.get("images", []):
                    link = img.get("disBaseLink") or img.get("link", "")
                    if link:
                        images.append({
                            "url": link if link.startswith("http") else "https:" + link,
                            "alt": img.get("alt", ""),
                            "view": view,
                        })
            # Variation attributes (color, size, etc.)
            variations = []
            for va in data.get("variationAttributes", []):
                variations.append({
                    "name": va.get("name", ""),
                    "values": [v.get("name", v.get("value", "")) for v in va.get("values", [])],
                })
            detail = {**self.product_cache.get(product_id, {}),
                "description": self._clean_html(data.get("longDescription") or data.get("shortDescription", "")),
                "images": images,
                "variations": variations,
                "currency": data.get("currency", "USD"),
                "page_title": data.get("pageTitle", ""),
            }
            self.product_cache[product_id] = detail
            return detail
        except Exception as e:
            print(f"[WARN] fetch_product_detail {product_id}: {e}")
            return self.product_cache.get(product_id, {})

    # ── SCAPI product search ────────────────────────────────────────────────

    def _call_scapi_search(self, query_text: str, category: str = None,
                           min_price: float = 0, max_price: float = float("inf"),
                           max_results: int = 10) -> List[Dict]:
        """Call the SCAPI Shopper Search endpoint."""
        t0 = time.monotonic()
        try:
            token = self._get_access_token()

            params: Dict[str, Any] = {
                "q": query_text,
                "limit": max_results,
                "siteId": self.scapi_site_id,
            }
            if self._active_locale:
                params["locale"] = self._active_locale.replace("_", "-")
            if category:
                params["refine"] = f"cgid={category}"

            resp = requests.get(
                self.scapi_search_url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            resp.raise_for_status()
            print(f"  ⏱  SCAPI search '{query_text[:40]}': {_ms(t0)}")

            hits = resp.json().get("hits", [])
            products = []
            for hit in hits:
                price = hit.get("price")
                if price is not None:
                    if price < min_price or price > max_price:
                        continue

                raw_img = hit.get("c_imageUrl") or hit.get("image", {}).get("link", "")
                # Normalise protocol-relative URLs
                if raw_img and raw_img.startswith("//"):
                    raw_img = "https:" + raw_img
                product = {
                    "id": hit.get("productId", ""),
                    "name": hit.get("productName", ""),
                    "brand": "",
                    "price": price,
                    "category": self._extract_category(hit),
                    "description": self._clean_html(hit.get("c_description", hit.get("shortDescription", ""))),
                    "image_url": raw_img,
                    "rating": None,
                    "product_url": hit.get("c_productUrl", ""),
                }
                if not raw_img:
                    print(f"[DEBUG] No image for {product['id']} — hit keys: {list(hit.keys())}")
                products.append(product)
                if product["id"]:
                    self.product_cache[product["id"]] = product

            return products

        except Exception as e:
            print(f"⚠️  SCAPI search error ({_ms(t0)}): {e}")
            return []

    @staticmethod
    def _extract_category(hit: Dict) -> str:
        """Pull first category label from refinements hit data if present."""
        for ra in hit.get("variationAttributes", []):
            if ra.get("id") == "cgid":
                vals = ra.get("values", [])
                if vals:
                    return vals[0].get("name", "")
        return ""

    @staticmethod
    def _clean_html(text: str) -> str:
        """Strip basic HTML tags for clean description text."""
        import re
        return re.sub(r"<[^>]+>", " ", text).strip()[:300]

    # ── Agent tools ─────────────────────────────────────────────────────────

    def search_products(self, queries: List[Dict], trace_fn=None) -> Dict[str, Any]:
        """Search the catalog — all queries fired in parallel."""
        t0 = time.monotonic()
        n = len(queries)
        print(f"  ⏱  search_products: {n} quer{'y' if n == 1 else 'ies'} (parallel)")
        if trace_fn:
            trace_fn(f"🔎 Searching catalog — {n} quer{'y' if n == 1 else 'ies'} in parallel")
        results = {}

        def _run(i: int, query: Dict):
            qt0 = time.monotonic()
            q_text = query.get("q", "")
            matches = self._call_scapi_search(
                q_text,
                category=query.get("category") or None,
                min_price=query.get("min_price", 0),
                max_price=query.get("max_price", float("inf")),
                max_results=20,
            )
            if trace_fn:
                trace_fn(f"  ✅ `{q_text}` → {len(matches)} results ({_ms(qt0)})")
            return i, query, matches

        with ThreadPoolExecutor(max_workers=min(n, 5)) as executor:
            futures = [executor.submit(_run, i, q) for i, q in enumerate(queries)]
            for future in as_completed(futures):
                i, query, matches = future.result()
                results[f"query_{i}"] = {
                    "query": query,
                    "count": len(matches),
                    "products": matches[:10],
                }

        print(f"  ⏱  search_products total: {_ms(t0)}")
        return results

    def get_product_details(self, product_ids: List[str]) -> Dict[str, Any]:
        """Return cached product details."""
        return {
            pid: self.product_cache.get(pid, {"error": "Product not found"})
            for pid in product_ids
        }

    def _get_tools(self) -> List[Dict]:
        tc = self._tool_config
        return [
            {
                "name": "create_todo",
                "description": "Create a plan before executing tool calls.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "steps": {"type": "array", "items": {"type": "string"}},
                        "message": {"type": "string"},
                    },
                    "required": ["steps", "message"],
                },
            },
            {
                "name": self._search_tool_name,
                "description": tc["search_description"],
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "queries": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "q": {"type": "string", "description": "Keyword search (product type, brand, activity, feature)"},
                                    "category": {"type": "string", "description": tc["search_category_hint"]},
                                    "min_price": {"type": "number"},
                                    "max_price": {"type": "number"},
                                },
                            },
                        }
                    },
                    "required": ["queries"],
                },
            },
            {
                "name": "web_search",
                "description": tc["web_search_description"],
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        ]

    def _execute_tool(self, tool_name: str, tool_input: Dict, trace_fn=None) -> Any:
        if tool_name == self._search_tool_name:
            return self.search_products(tool_input.get("queries", []), trace_fn=trace_fn)
        elif tool_name == "create_todo":
            return {"status": "plan_created", "steps": tool_input.get("steps", []), "message": tool_input.get("message", "")}
        elif tool_name == "web_search":
            return self.web_search(tool_input.get("query", ""), min(tool_input.get("max_results", 5), 10))
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def web_search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        t0 = time.monotonic()
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            print(f"  ⏱  DuckDuckGo '{query[:40]}': {_ms(t0)} ({len(results)} results)")
            return {
                "query": query,
                "results": [{"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")} for r in results],
            }
        except Exception as e:
            print(f"  ⚠️  Web search error ({_ms(t0)}): {e}")
            return {"query": query, "results": [], "error": str(e)}

    def _analyze_image_and_create_query(self, image: bytes, user_message: str) -> tuple:
        """Use Claude's vision to analyze a gear image and create search queries."""
        try:
            import base64, re as _re

            image_base64 = base64.b64encode(image).decode("utf-8")
            if image[:4] == b"\x89PNG":
                media_type = "image/png"
            elif image[:4] == b"GIF8":
                media_type = "image/gif"
            elif image[:4] == b"RIFF" and image[8:12] == b"WEBP":
                media_type = "image/webp"
            else:
                media_type = "image/jpeg"

            vision_prompt = """Analyze this outdoor gear or apparel image CAREFULLY.

STEP 1 — READ ALL TEXT ON THE PRODUCT FIRST.
Read brand name, product name, product type, key features. Do not guess brand names — only use what is written.

STEP 2 — IDENTIFY EACH PRODUCT.
- Exact brand name (from label — DO NOT GUESS)
- Product type (hiking boot, rain jacket, tent, backpack, etc.)
- Key visible features (waterproof, insulated, etc.)

STEP 3 — BUILD SEARCH QUERIES. Brand first if readable.
Good: "Patagonia rain jacket", "Merrell hiking boot waterproof"
Bad: "outdoor jacket" (no brand)

Respond in this EXACT format:
DESCRIPTION: [what you see]
QUERIES: [comma-separated queries, one per product]"""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_base64}},
                        {"type": "text", "text": vision_prompt},
                    ],
                }],
            )

            response_text = next((b.text.strip() for b in response.content if b.type == "text"), "")
            description, queries = "", []
            for line in response_text.split("\n"):
                if line.startswith("DESCRIPTION:"):
                    description = line.replace("DESCRIPTION:", "").strip()
                elif line.startswith("QUERIES:"):
                    queries = [q.strip() for q in line.replace("QUERIES:", "").split(",") if q.strip()]

            if not queries:
                queries = ["outdoor gear"]
            if not description:
                description = "Outdoor product(s) in image"

            print(f"  🔍 Vision: {description} → {queries}")
            return queries, description, media_type, response_text

        except Exception as e:
            print(f"  ⚠️  Vision error: {e}")
            return ["outdoor gear"], "Outdoor product in image", "unknown", str(e)

    def _generate_follow_up(self, user_message: str, agent_response: str) -> str:
        """Generate a contextual follow-up question when JSON parsing fails."""
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=80,
                messages=[{
                    "role": "user",
                    "content": (
                        f"User asked: {user_message}\n\n"
                        f"You responded with product recommendations.\n\n"
                        f"Write ONE short follow-up question (max 20 words) to help refine "
                        f"what they're looking for. Be specific to their query. No preamble."
                    ),
                }],
            )
            return resp.content[0].text.strip()
        except Exception:
            return "What else can I help you find?"

    # ── Main chat loop ───────────────────────────────────────────────────────

    def chat(self, user_message: str, max_iterations: int = 5, image: bytes = None, trace_fn=None) -> Dict:
        def _trace(msg: str):
            print(f"  {msg}")
            if trace_fn:
                trace_fn(msg)

        image_analysis = None
        if image:
            queries, description, media_type, raw = self._analyze_image_and_create_query(image, user_message)
            image_analysis = {"description": description, "queries": queries, "media_type": media_type, "raw_vision_response": raw}
            user_note = user_message if user_message and user_message != "Visual search" else ""
            user_message = f"{user_note} — {', '.join(queries)}" if user_note else ", ".join(queries)

        self.conversation_history.append({"role": "user", "content": user_message})
        self._detect_and_set_locale(user_message, trace_fn=trace_fn)

        iteration, assistant_message, tool_call_log = 0, "", []
        search_calls = 0
        MAX_SEARCH_CALLS = 2
        chat_t0 = time.monotonic()

        while iteration < max_iterations:
            _trace(f"🤔 Thinking... (iteration {iteration + 1})")

            # Remove search tool once cap is reached so Claude writes the response
            available_tools = [
                t for t in self._get_tools()
                if not (t["name"] == self._search_tool_name and search_calls >= MAX_SEARCH_CALLS)
            ]

            # Keep last 10 messages (5 user+assistant turns) to limit input tokens
            trimmed_history = self.conversation_history[-10:] if len(self.conversation_history) > 10 else self.conversation_history

            claude_t0 = time.monotonic()
            response = self.client.messages.create(
                model=self.model,
                max_tokens=3500,
                system=[
                    {
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=available_tools,
                messages=trimmed_history,
            )
            u = response.usage
            cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
            cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
            cache_tag = f" 💾 cache_hit={cache_read}" if cache_read else (f" ✍️ cache_write={cache_write}" if cache_write else "")
            _trace(f"💬 Claude responded ({_ms(claude_t0)}, in={u.input_tokens} out={u.output_tokens} tokens{cache_tag})")

            assistant_message, tool_results, has_tool_use = "", [], False

            for block in response.content:
                if block.type == "text":
                    assistant_message = block.text
                elif block.type == "tool_use":
                    has_tool_use = True
                    t0 = time.monotonic()

                    if block.name == "create_todo":
                        _trace(f"📋 Plan: {block.input.get('message', '')}")
                    elif block.name == self._search_tool_name:
                        search_calls += 1
                        qs = block.input.get("queries", [])
                        _trace(f"🔎 Searching catalog — {len(qs)} quer{'y' if len(qs)==1 else 'ies'} in parallel")
                    elif block.name == "web_search":
                        _trace(f"🌐 Web search: \"{block.input.get('query', '')}\"")

                    result = self._execute_tool(block.name, block.input, trace_fn=trace_fn if block.name == self._search_tool_name else None)
                    duration = _ms(t0)
                    _trace(f"  ↳ {block.name} done ({duration})")
                    tool_call_log.append({"tool": block.name, "input": block.input, "duration": duration})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})

            self.conversation_history.append({"role": "assistant", "content": response.content})

            if not has_tool_use:
                _trace("✅ Composing final response...")
                break

            self.conversation_history.append({"role": "user", "content": tool_results})

            # create_todo is a free planning step — don't count it against the iteration budget
            only_todo = all(
                next((b.name for b in response.content if b.type == "tool_use" and b.id == r["tool_use_id"]), "") == "create_todo"
                for r in tool_results
            )
            if not only_todo:
                iteration += 1

        total = _ms(chat_t0)
        _trace(f"⏱ Total: {total} across {iteration} iteration(s)")
        print(f"\n⏱  TOTAL: {total} across {iteration} iteration(s)")

        # Extract JSON from response — handle prose prefix before ```json fence
        cleaned = assistant_message.strip()
        # 1. Fenced ```json ... ```
        m = re.search(r"```json\s*(.*?)```", cleaned, re.DOTALL)
        if m:
            cleaned = m.group(1).strip()
        else:
            # 2. Bare ``` ... ```
            m = re.search(r"```\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
            if m:
                cleaned = m.group(1).strip()
            else:
                # 3. Prose before the JSON object — find first { and last }
                start = cleaned.find('{')
                end = cleaned.rfind('}')
                if start != -1 and end != -1 and end > start:
                    cleaned = cleaned[start:end + 1]

        try:
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                raise ValueError("JSON root is not an object")
            if image_analysis:
                parsed["image_analysis"] = image_analysis
            parsed["tool_call_log"] = tool_call_log
            return parsed
        except (json.JSONDecodeError, ValueError):
            print(f"[WARN] JSON parse failed — raw assistant_message:\n{assistant_message[:400]}")
            follow_up = self._generate_follow_up(user_message, assistant_message)
            fallback = {
                "thought": "Raw response",
                "response": [{"type": "markdown", "content": assistant_message}],
                "follow_up": follow_up,
                "suggestions": [],
                "tool_call_log": tool_call_log,
            }
            if image_analysis:
                fallback["image_analysis"] = image_analysis
            return fallback

    def reset(self):
        self.conversation_history = []


def main():
    import argparse
    from dotenv import load_dotenv
    from site_config import load_site_scapi_env

    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default=None, help="Site ID (e.g. shiseido_us)")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not set")
        return

    senv = load_site_scapi_env(args.site) if args.site else {}
    agent = NTOAgent(
        api_key=api_key,
        base_url=os.getenv("ANTHROPIC_BASE_URL"),
        scapi_token_url=senv.get("SCAPI_TOKEN_URL") or os.getenv("SCAPI_TOKEN_URL"),
        scapi_client_credentials=senv.get("SCAPI_CLIENT_CREDENTIALS") or os.getenv("SCAPI_CLIENT_CREDENTIALS"),
        scapi_search_url=senv.get("SCAPI_SEARCH_URL") or os.getenv("SCAPI_SEARCH_URL"),
        scapi_site_id=senv.get("SCAPI_SITE_ID") or os.getenv("SCAPI_SITE_ID", "NTOManaged"),
        site_id=args.site,
    )

    print("🏔️  Northern Trail Outfitters Shopping Agent")
    print("="*60)
    print("💬 Type 'quit' to exit, 'reset' to start new conversation\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            print("👋 Thanks for shopping with Northern Trail Outfitters!")
            break
        if user_input.lower() == "reset":
            agent.reset()
            print("🔄 Conversation reset.\n")
            continue
        if not user_input:
            continue

        try:
            response = agent.chat(user_input)
            print("\n" + "="*60)
            print("NTO Trail Advisor:")
            print("="*60)
            if "thought" in response:
                print(f"\n💭 {response['thought']}\n")
            for block in response.get("response", []):
                if block["type"] == "markdown":
                    print(block["content"])
            if response.get("follow_up"):
                print(f"\n❓ {response['follow_up']}")
            if response.get("suggestions"):
                print("\n💡 " + " | ".join(response["suggestions"]))
            print()
        except Exception as e:
            import traceback
            print(f"❌ {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
