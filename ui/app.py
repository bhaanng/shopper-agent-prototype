"""
Northern Trail Outfitters (NTO) Shopping Agent - Web UI
Simple Streamlit interface for the NTO outdoor shopping agent
"""

import queue
import threading
import time
import streamlit as st
import sys
import os
from pathlib import Path

# Add parent directory to path to import agent
sys.path.append(str(Path(__file__).parent.parent / "agent"))

from nto_agent import NTOAgent
from site_config import list_sites, load_site_scapi_env, get_site_ui
from evals.session_logger import SessionLogger
from dotenv import load_dotenv

# Load environment variables — local .env first, then Streamlit secrets
load_dotenv()
try:
    for key, val in st.secrets.items():
        if key not in os.environ:
            os.environ[key] = str(val)
except Exception:
    pass

# Pin to a specific site via: streamlit run ui/app.py -- --site shiseido_us
_PINNED_SITE = None
if "--site" in sys.argv:
    _idx = sys.argv.index("--site")
    if _idx + 1 < len(sys.argv):
        _PINNED_SITE = sys.argv[_idx + 1]

# Page config — read branding early from pinned site (before session state exists)
_early_ui = get_site_ui(_PINNED_SITE)
st.set_page_config(
    page_title=_early_ui["title"],
    page_icon=_early_ui["icon"],
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #000000;
        text-align: center;
        margin-bottom: 1rem;
        font-weight: bold;
    }
    .sub-header {
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .user-message {
        background-color: #F8E8F0;
    }
    .assistant-message {
        background-color: #FFF5F5;
    }
    .suggestion-button {
        margin: 0.25rem;
    }
</style>
""", unsafe_allow_html=True)

def _build_agent(site_id: str) -> NTOAgent:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("❌ ANTHROPIC_API_KEY not found! Please set it in .env file.")
        st.stop()

    # Load SCAPI creds from agents/<site_id>/config.env, fall back to root .env
    senv = load_site_scapi_env(site_id) if site_id else {}
    scapi_token_url = senv.get("SCAPI_TOKEN_URL") or os.getenv("SCAPI_TOKEN_URL")
    scapi_credentials = senv.get("SCAPI_CLIENT_CREDENTIALS") or os.getenv("SCAPI_CLIENT_CREDENTIALS")
    scapi_search_url = senv.get("SCAPI_SEARCH_URL") or os.getenv("SCAPI_SEARCH_URL")
    scapi_site_id = senv.get("SCAPI_SITE_ID") or os.getenv("SCAPI_SITE_ID", "NTOManaged")
    scapi_locale = senv.get("SCAPI_LOCALE") or os.getenv("SCAPI_LOCALE")

    if not all([scapi_token_url, scapi_credentials, scapi_search_url]):
        st.error("❌ SCAPI credentials not found. Check agents/{site_id}/config.env or root .env")
        st.stop()

    return NTOAgent(
        api_key=api_key,
        base_url=os.getenv("ANTHROPIC_BASE_URL"),
        scapi_token_url=scapi_token_url,
        scapi_client_credentials=scapi_credentials,
        scapi_search_url=scapi_search_url,
        scapi_site_id=scapi_site_id,
        scapi_locale=scapi_locale,
        site_id=site_id or None,
    )


# Initialize session state
if 'site_id' not in st.session_state:
    st.session_state.site_id = _PINNED_SITE or os.getenv("SCAPI_SITE_ID", "NTOManaged")

if 'agent' not in st.session_state:
    st.session_state.agent = _build_agent(st.session_state.site_id)

if 'messages' not in st.session_state:
    st.session_state.messages = []

if 'suggestions' not in st.session_state:
    st.session_state.suggestions = []

if 'pending_input' not in st.session_state:
    st.session_state.pending_input = None

if 'message_responses' not in st.session_state:
    st.session_state.message_responses = []  # Store full response structures

if 'staged_image' not in st.session_state:
    st.session_state.staged_image = None

if 'session_logger' not in st.session_state:
    st.session_state.session_logger = SessionLogger(
        site_id=_PINNED_SITE or os.getenv("SCAPI_SITE_ID", "NTOManaged")
    )

if 'eval_report' not in st.session_state:
    st.session_state.eval_report = None

if 'last_tool_calls' not in st.session_state:
    st.session_state.last_tool_calls = []  # tool_call_log from the most recent turn

# Resolve UI branding from pinned site or active session site
_site_ui = get_site_ui(_PINNED_SITE or st.session_state.site_id)

# Header
st.markdown(f'<div class="main-header">{_site_ui["icon"]} {_site_ui["title"]}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">{_site_ui["subtitle"]}</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("About")
    st.markdown(_site_ui["about"])

    st.divider()

    # Site selector — hidden when pinned via --site flag
    if _PINNED_SITE:
        st.caption(f"Site: **{_PINNED_SITE}**")
    else:
        sites = list_sites()
        site_options = ["(base — no overlay)"] + sites
        current_idx = (sites.index(st.session_state.site_id) + 1
                       if st.session_state.site_id in sites else 0)
        selected = st.selectbox("Site", site_options, index=current_idx)
        new_site_id = None if selected == "(base — no overlay)" else selected

        if new_site_id != st.session_state.site_id:
            st.session_state.site_id = new_site_id
            st.session_state.agent = _build_agent(new_site_id)
            st.session_state.messages = []
            st.session_state.suggestions = []
            st.session_state.message_responses = []
            st.session_state.session_logger = SessionLogger(site_id=new_site_id or "base")
            st.rerun()

    if st.session_state.site_id:
        st.caption(f"Site active: `{st.session_state.site_id}`")
    else:
        st.caption("Using base prompt only")

    st.divider()

    # Persistent tool calls from last turn
    if st.session_state.get("last_tool_calls"):
        st.subheader("🔧 Tool Calls")
        for call in st.session_state.last_tool_calls:
            with st.expander(f"`{call['tool']}` — {call['duration']}"):
                inp = call.get("input", {})
                if call["tool"] == "search_nto_products":
                    for q in inp.get("queries", []):
                        parts = [f"**q**: `{q.get('q', '')}`"]
                        if q.get("category"):
                            parts.append(f"**category**: {q['category']}")
                        if q.get("min_price") or q.get("max_price"):
                            parts.append(f"**price**: ${q.get('min_price', 0)}–${q.get('max_price', '∞')}")
                        st.markdown("  ·  ".join(parts))
                elif call["tool"] == "web_search":
                    st.markdown(f"**query**: {inp.get('query', '')}")
                elif call["tool"] == "create_todo":
                    st.markdown(inp.get("message", ""))
                    for step in inp.get("steps", []):
                        st.markdown(f"- {step}")
                else:
                    st.json(inp)
        st.divider()

    cache_size = len(st.session_state.agent.product_cache)
    st.metric("Products Cached", cache_size)

    if st.button("🔄 Reset Conversation"):
        st.session_state.agent.reset()
        st.session_state.messages = []
        st.session_state.suggestions = []
        st.session_state.staged_image = None
        st.session_state.last_tool_calls = []
        st.session_state.session_logger = SessionLogger(
            site_id=_PINNED_SITE or st.session_state.site_id
        )
        st.session_state.eval_report = None
        st.rerun()

    has_turns = st.session_state.session_logger.turn > 0
    log_path = st.session_state.session_logger.path()
    eval_ready = has_turns and log_path.exists()
    if st.button("📊 Eval This Session", disabled=not eval_ready,
                 help="Score this conversation against all quality metrics"):
        with st.spinner("Running eval — judging all proxies in parallel..."):
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent.parent))
            from scripts.eval_session import eval_session
            st.session_state.eval_report = eval_session(log_path)

    if st.session_state.get("eval_report"):
        report = st.session_state.eval_report
        st.divider()
        st.subheader("📊 Session Eval")
        st.metric("Overall", f"{report['overall']:.0%}",
                  help=f"{report['scored']} judgments across {report['turns']} turn(s)")

        st.markdown("**By metric**")
        for metric, score in sorted(report["metric_scores"].items(), key=lambda x: x[1]):
            st.progress(score, text=f"{metric}  {score:.0%}")

        with st.expander("Turn scores"):
            for turn, score in sorted(report["turn_scores"].items()):
                st.progress(score, text=f"Turn {turn}  {score:.0%}")

        low = [r for r in report["results"] if r["score"] is not None and r["score"] < 0.5]
        if low:
            with st.expander(f"⚠️ {len(low)} low-score findings"):
                for r in sorted(low, key=lambda x: x["score"])[:15]:
                    st.markdown(f"**Turn {r['turn']} · {r['proxy']}** ({r['verdict']})  \n{r['reason']}")

    st.divider()
    st.caption("Powered by Claude AI | Northern Trail Outfitters")

# Handle pending suggestion click FIRST (before rendering anything else)
user_input_from_suggestion = None
if 'pending_input' in st.session_state and st.session_state.pending_input:
    user_input_from_suggestion = st.session_state.pending_input
    st.session_state.pending_input = None
    # Clear suggestions so they don't show again
    st.session_state.suggestions = []

# Display chat messages using Streamlit's chat interface
assistant_message_count = 0
for idx, message in enumerate(st.session_state.messages):
    if message["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            # Show image if present
            if "image" in message and message["image"]:
                st.image(message["image"], width=200)
            st.markdown(message["content"])
    else:
        with st.chat_message("assistant", avatar="🏔️"):
            # Check if we have the full response structure stored
            if assistant_message_count < len(st.session_state.message_responses):
                response_data = st.session_state.message_responses[assistant_message_count]

                # Render the full response with product tables
                if response_data and 'response' in response_data:
                    for block in response_data['response']:
                        if not isinstance(block, dict):
                            continue
                        if block['type'] == 'markdown':
                            # Escape dollar signs to prevent LaTeX interpretation
                            content = block['content'].replace('$', '\\$')
                            st.markdown(content)
                        elif block['type'] == 'product_table':
                            table_data = block.get('content', {})
                            title = table_data.get('title', 'Products')
                            products = table_data.get('products', [])

                            if products:
                                st.markdown(f"### 🛍️ {title}")
                                product_ids = [p.get('id') for p in products if p.get('id')]

                                if product_ids and hasattr(st.session_state.agent, 'product_cache'):
                                    product_cache = st.session_state.agent.product_cache
                                    display_products = [product_cache.get(pid) for pid in product_ids[:6] if pid in product_cache]

                                    if display_products:
                                        num_cols = min(len(display_products), 3)
                                        cols = st.columns(num_cols)

                                        for pidx, details in enumerate(display_products):
                                            col = cols[pidx % num_cols]
                                            with col:
                                                name = details.get('name', 'Unknown Product')
                                                brand = details.get('brand', '')
                                                price = details.get('price')
                                                rating = details.get('rating')

                                                st.markdown(f"""
                                                <div style="
                                                    border: 1px solid #e0e0e0;
                                                    border-radius: 8px;
                                                    padding: 12px;
                                                    margin-bottom: 10px;
                                                    background-color: #fff;
                                                ">
                                                    <p style="margin: 0 0 4px 0; font-size: 11px; color: #999; text-transform: uppercase;">{brand}</p>
                                                    <p style="margin: 0 0 8px 0; font-weight: 600; color: #000; font-size: 14px;">{name[:50]}{'...' if len(name) > 50 else ''}</p>
                                                    <p style="margin: 0; font-size: 16px; color: #d4007a; font-weight: bold;">{'$' + str(int(price)) if price else 'Price varies'}</p>
                                                    {f'<p style="margin: 4px 0 0 0; font-size: 12px; color: #666;">⭐ {rating}</p>' if rating else ''}
                                                </div>
                                                """, unsafe_allow_html=True)

                    # Display follow-up
                    if response_data.get('follow_up'):
                        st.markdown(f"\n---\n\n❓ **{response_data['follow_up']}**")
                else:
                    # Fallback to text content
                    st.markdown(message["content"])
            else:
                # No structured response available, show text
                st.markdown(message["content"])

            assistant_message_count += 1

# Display suggestions from last response (only if no pending input)
if st.session_state.suggestions and not user_input_from_suggestion:
    st.write("**💡 Quick actions:**")
    cols = st.columns(min(len(st.session_state.suggestions), 3))
    for idx, suggestion in enumerate(st.session_state.suggestions):
        col = cols[idx % 3]
        if col.button(suggestion, key=f"sug_{idx}", use_container_width=True):
            # User clicked a suggestion - set pending and rerun
            st.session_state.pending_input = suggestion
            st.rerun()

# Input area — multimodal form (text + optional image, submitted together)
user_input = None
image_data_to_send = None

# Suggestion clicks bypass the form
if user_input_from_suggestion:
    user_input = user_input_from_suggestion
else:
    with st.form("input_form", clear_on_submit=True):
        text_col, img_col = st.columns([4, 1])
        with text_col:
            typed_text = st.text_input(_site_ui["chat_placeholder"], label_visibility="collapsed", placeholder=_site_ui["chat_placeholder"])
        with img_col:
            uploaded_file = st.file_uploader("📸", type=["png", "jpg", "jpeg"], label_visibility="collapsed")

        # Preview image while staged
        if uploaded_file:
            st.image(uploaded_file, width=120, caption="Image ready — add a note and hit Send")

        submitted = st.form_submit_button("Send ✨", use_container_width=True)

    if submitted and (typed_text.strip() or uploaded_file):
        user_input = typed_text.strip() or "Visual search"
        if uploaded_file:
            image_data_to_send = uploaded_file.getvalue()
            st.session_state.staged_image = {"data": image_data_to_send, "name": uploaded_file.name}

if user_input:
    # For non-form paths (suggestions), no image
    if image_data_to_send is None and st.session_state.staged_image is None:
        pass  # text-only
    elif image_data_to_send is None and st.session_state.staged_image:
        image_data_to_send = st.session_state.staged_image["data"]
        st.session_state.staged_image = None
    # Add user message to history (with image bytes if provided)
    if image_data_to_send:
        st.session_state.messages.append({"role": "user", "content": user_input, "image": image_data_to_send})
    else:
        st.session_state.messages.append({"role": "user", "content": user_input})

    # Display user message immediately
    with st.chat_message("user", avatar="👤"):
        if image_data_to_send:
            st.image(image_data_to_send, caption="Attached image", width=200)
        st.markdown(user_input)

    # Run agent in background thread; drain trace queue live on main thread
    trace_queue = queue.Queue()
    result_box = {}
    agent = st.session_state.agent  # capture before entering thread

    def _run_agent():
        try:
            result_box["response"] = agent.chat(
                user_input,
                image=image_data_to_send,
                trace_fn=lambda msg: trace_queue.put(msg),
            )
        except Exception as e:
            result_box["error"] = e

    thread = threading.Thread(target=_run_agent, daemon=True)
    thread.start()

    # Live trace + tool calls in sidebar
    st.sidebar.divider()
    st.sidebar.subheader("🔍 Agent Trace")
    trace_placeholder = st.sidebar.empty()
    tool_calls_placeholder = st.sidebar.empty()

    trace_lines = []
    with st.spinner(_site_ui["search_label"]):
        while thread.is_alive() or not trace_queue.empty():
            # Drain all available messages in one batch before re-rendering
            updated = False
            while True:
                try:
                    msg = trace_queue.get_nowait()
                    trace_lines.append(msg)
                    updated = True
                except queue.Empty:
                    break
            if updated:
                trace_placeholder.markdown("\n\n".join(trace_lines))
            time.sleep(0.1)

    thread.join()

    # Render tool calls in sidebar after agent finishes
    tool_log = result_box.get("response", {}).get("tool_call_log", []) if "response" in result_box else []
    if tool_log:
        tool_md = "**🔧 Tool Calls**\n\n"
        for call in tool_log:
            tool_md += f"**`{call['tool']}`** — {call['duration']}\n\n"
            inp = call.get("input", {})
            if call["tool"] == "search_nto_products":
                queries = inp.get("queries", [])
                for q in queries:
                    parts = [f"`{q.get('q', '')}`"]
                    if q.get("category"):
                        parts.append(q["category"])
                    if q.get("min_price") or q.get("max_price"):
                        parts.append(f"\\${q.get('min_price', 0)}–\\${q.get('max_price', '∞')}")
                    tool_md += "- " + "  ·  ".join(parts) + "\n"
            elif call["tool"] == "web_search":
                tool_md += f"- {inp.get('query', '')}\n"
            elif call["tool"] == "create_todo":
                tool_md += f"- {inp.get('message', '')}\n"
            tool_md += "\n"
        tool_calls_placeholder.markdown(tool_md)

    if "error" in result_box:
        st.error(f"Error: {result_box['error']}")
        import traceback as tb
        st.code("".join(tb.format_exception(type(result_box["error"]), result_box["error"], result_box["error"].__traceback__)))
        st.stop()

    response = result_box["response"]

    # Render assistant response cleanly
    with st.chat_message("assistant", avatar="🏔️"):
        response_text_for_history = ""

        if 'response' in response:
            for block in response['response']:
                if not isinstance(block, dict):
                    continue
                if block['type'] == 'markdown':
                    content = block['content'].replace('$', '\\$')
                    st.markdown(content)
                    response_text_for_history += block['content'] + "\n\n"
                elif block['type'] == 'product_table':
                    table_data = block.get('content', {})
                    title = table_data.get('title', 'Products')
                    products = table_data.get('products', [])

                    if products:
                        st.markdown(f"### 🛍️ {title}")
                        product_ids = [p.get('id') for p in products if p.get('id')]

                        if product_ids:
                            product_cache = st.session_state.agent.product_cache
                            display_products = [product_cache.get(pid) for pid in product_ids[:6] if pid in product_cache]

                            if display_products:
                                num_cols = min(len(display_products), 3)
                                cols = st.columns(num_cols)

                                for idx, details in enumerate(display_products):
                                    col = cols[idx % num_cols]
                                    with col:
                                        name = details.get('name', 'Unknown Product')
                                        brand = details.get('brand', '')
                                        price = details.get('price')
                                        rating = details.get('rating')
                                        st.markdown(f"""
                                        <div style="
                                            border: 1px solid #e0e0e0;
                                            border-radius: 8px;
                                            padding: 12px;
                                            margin-bottom: 10px;
                                            background-color: #fff;
                                        ">
                                            <p style="margin: 0 0 4px 0; font-size: 11px; color: #999; text-transform: uppercase;">{brand}</p>
                                            <p style="margin: 0 0 8px 0; font-weight: 600; color: #000; font-size: 14px;">{name[:50]}{'...' if len(name) > 50 else ''}</p>
                                            <p style="margin: 0; font-size: 16px; color: #2e7d32; font-weight: bold;">{'$' + str(int(price)) if price else 'Price varies'}</p>
                                            {f'<p style="margin: 4px 0 0 0; font-size: 12px; color: #666;">⭐ {rating}</p>' if rating else ''}
                                        </div>
                                        """, unsafe_allow_html=True)

                        response_text_for_history += f"\n\n**{title}** ({len(products)} products)\n"

        if 'follow_up' in response and response['follow_up']:
            follow_up = response['follow_up']
            st.markdown(f"\n---\n\n❓ **{follow_up}**")
            response_text_for_history += f"\n\n❓ {follow_up}"

    st.session_state.messages.append({"role": "assistant", "content": response_text_for_history})
    st.session_state.message_responses.append(response)
    st.session_state.suggestions = response.get('suggestions', [])
    st.session_state.last_tool_calls = response.get('tool_call_log', [])

    # Log this turn to disk for post-session eval
    active_locale = getattr(st.session_state.agent, "_active_locale", None)
    st.session_state.session_logger.log_turn(user_input, response, locale=active_locale)

    st.rerun()

# Example queries at the bottom if no messages yet
if not st.session_state.messages:
    starter_queries = _site_ui.get("starter_queries", [])
    if starter_queries:
        st.divider()
        st.subheader("Try asking:")
        cols = st.columns(len(starter_queries))
        for col, item in zip(cols, starter_queries):
            with col:
                if st.button(item["label"]):
                    st.session_state.pending_input = item["query"]
                    st.rerun()
