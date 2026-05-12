"""
Shopper Agent UI — mobile-frame chat + contextual trace panel
"""

import queue
import threading
import time
import streamlit as st
import sys
import os
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "core"))

from nto_agent import NTOAgent
from site_config import list_sites, load_site_scapi_env, get_site_ui
from evals.session_logger import SessionLogger
from dotenv import load_dotenv

load_dotenv()
try:
    for key, val in st.secrets.items():
        if key not in os.environ:
            os.environ[key] = str(val)
except Exception:
    pass

_PINNED_SITE = None
if "--site" in sys.argv:
    _idx = sys.argv.index("--site")
    if _idx + 1 < len(sys.argv):
        _PINNED_SITE = sys.argv[_idx + 1]

_early_ui = get_site_ui(_PINNED_SITE)
st.set_page_config(
    page_title=_early_ui["title"],
    page_icon=_early_ui["icon"],
    layout="wide"
)

st.markdown("""
<style>
/* ── Layout ─────────────────────────────────────────────── */
.block-container { padding-top: 1rem !important; padding-bottom: 0 !important; }
[data-testid="stHeader"] { display: none !important; }

/* ── Phone frame ─────────────────────────────────────────── */
.phone-container {
    max-width: 460px;
    margin: 0 auto;
    background: white;
    border-radius: 36px;
    box-shadow: 0 24px 80px rgba(0,0,0,0.18), 0 0 0 1px rgba(0,0,0,0.06);
    overflow: hidden;
}

.phone-header {
    background: rgba(255,255,255,0.96);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid #f1f5f9;
    padding: 16px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
}

.phone-bot-avatar {
    width: 42px;
    height: 42px;
    background: #1a1a1a;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    flex-shrink: 0;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}

.phone-title { font-size: 14px; font-weight: 800; color: #1a1a1a; letter-spacing: -0.3px; }
.phone-subtitle { font-size: 11px; color: #94a3b8; font-weight: 500; margin-top: 1px; }

.phone-status-dot {
    width: 8px; height: 8px; background: #22c55e;
    border-radius: 50%; display: inline-block;
    box-shadow: 0 0 6px rgba(34,197,94,0.6);
    margin-right: 5px;
}

/* ── Chat bubbles ─────────────────────────────────────────── */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"])
    [data-testid="stChatMessageContent"] {
    background: #2563eb !important;
    color: white !important;
    border-radius: 20px 4px 20px 20px !important;
    padding: 12px 16px !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"])
    [data-testid="stChatMessageContent"] p { color: white !important; }

[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"])
    [data-testid="stChatMessageContent"] {
    background: #f4f4f4 !important;
    border-radius: 4px 20px 20px 20px !important;
    padding: 12px 16px !important;
}

/* ── Suggestion chips ──────────────────────────────────────── */
div[data-testid="stHorizontalBlock"] .stButton > button {
    border-radius: 24px !important;
    font-size: 12px !important;
    padding: 6px 14px !important;
    border: 2px solid #e5e7eb !important;
    background: white !important;
    color: #1a1a1a !important;
    font-weight: 600 !important;
    transition: all 0.15s ease !important;
}
div[data-testid="stHorizontalBlock"] .stButton > button:hover {
    border-color: #1a1a1a !important;
    background: #1a1a1a !important;
    color: white !important;
}

/* ── Product cards ─────────────────────────────────────────── */
.product-scroll {
    display: flex;
    gap: 14px;
    overflow-x: auto;
    padding: 8px 2px 16px;
    scrollbar-width: none;
    -ms-overflow-style: none;
}
.product-scroll::-webkit-scrollbar { display: none; }

.product-card {
    min-width: 190px;
    background: white;
    border: 1px solid #f1f5f9;
    border-radius: 24px;
    padding: 16px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.07);
    flex-shrink: 0;
}
.product-card-brand { font-size: 9px; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.15em; color: #94a3b8; margin-bottom: 4px; }
.product-card-name { font-size: 12px; font-weight: 700; color: #1a1a1a;
    margin-bottom: 8px; line-height: 1.3; }
.product-card-price { font-size: 18px; font-weight: 900; color: #1a1a1a;
    letter-spacing: -0.5px; }
.product-card-rating { font-size: 11px; color: #64748b; margin-top: 4px; }

/* ── Trace panel ───────────────────────────────────────────── */
.trace-outer {
    background: #0a0a0a;
    border-radius: 20px;
    overflow: hidden;
    min-height: 560px;
}
.trace-header {
    background: rgba(0,0,0,0.5);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(255,255,255,0.06);
    padding: 18px 22px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.trace-header-title {
    font-size: 10px; font-weight: 900; text-transform: uppercase;
    letter-spacing: 0.25em; color: #60a5fa;
}
.trace-header-sub { font-size: 9px; color: #475569; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.1em; margin-top: 3px; }
.trace-zap { font-size: 16px; }

.trace-body { padding: 18px 22px; }
.trace-section-label {
    font-size: 9px; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.2em; color: #334155; margin-bottom: 12px;
    display: flex; align-items: center; gap: 6px;
}
.trace-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 14px 16px;
    margin-bottom: 10px;
}
.trace-card-label {
    font-size: 10px; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.15em; color: white; margin-bottom: 5px;
}
.trace-card-value { font-size: 11px; color: #475569; font-style: italic; }
.trace-card-value.blue { color: #60a5fa; font-weight: 600; }
.trace-footer {
    padding: 14px 22px;
    background: rgba(0,0,0,0.5);
    border-top: 1px solid rgba(255,255,255,0.05);
    font-size: 9px; color: #1e293b; font-family: monospace;
    display: flex; align-items: center; justify-content: space-between;
    text-transform: uppercase; letter-spacing: 0.05em;
}
.status-online { color: #22c55e; }

/* ── Input bar ─────────────────────────────────────────────── */
.stTextInput input {
    border-radius: 24px !important;
    border: 2px solid #f1f5f9 !important;
    padding: 12px 20px !important;
    font-size: 14px !important;
    background: #f8fafc !important;
}
.stTextInput input:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.1) !important;
}

/* ── Sticky input at bottom of chat column ─────────────────── */
[data-testid="stColumn"]:has(.phone-container) [data-testid="stForm"] {
    position: sticky;
    bottom: 0;
    background: white;
    z-index: 100;
    padding-top: 10px;
    border-top: 1px solid #f1f5f9;
    margin-top: 8px;
}

/* ── Responsive: mobile (≤768px) ──────────────────────────────── */
@media (max-width: 768px) {
    /* Hide sidebar and its toggle button */
    [data-testid="stSidebar"],
    [data-testid="collapsedControl"] { display: none !important; }

    /* Hide the trace column — identified by its .trace-footer child */
    [data-testid="stColumn"]:has(.trace-footer) { display: none !important; }

    /* Expand the chat column to full width */
    [data-testid="stColumn"]:has(.phone-container) {
        flex: 0 0 100% !important;
        width: 100% !important;
        min-width: 100% !important;
    }

    /* On a real mobile screen strip the phone-frame chrome */
    .phone-container {
        max-width: 100% !important;
        border-radius: 0 !important;
        box-shadow: none !important;
    }

    /* Tighten side padding so content fills edge-to-edge */
    .block-container { padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
}
</style>
""", unsafe_allow_html=True)


def _build_agent(site_id: str) -> NTOAgent:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("❌ ANTHROPIC_API_KEY not found! Please set it in .env file.")
        st.stop()

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


def _render_product_cards(products, product_cache, accent_color="#1a1a1a"):
    if not products:
        return
    product_ids = [p.get('id') for p in products if p.get('id')]
    display_products = [product_cache.get(pid) for pid in product_ids[:6] if pid in product_cache]
    if not display_products:
        return

    cards_html = '<div class="product-scroll">'
    for details in display_products:
        name = details.get('name', 'Unknown Product')
        brand = details.get('brand', '')
        price = details.get('price')
        rating = details.get('rating')
        price_str = f"${int(price)}" if price else "—"
        rating_str = f"⭐ {rating}" if rating else ""
        cards_html += f"""
        <div class="product-card">
            <div class="product-card-brand">{brand}</div>
            <div class="product-card-name">{name[:55]}{'…' if len(name) > 55 else ''}</div>
            <div class="product-card-price" style="color:{accent_color}">{price_str}</div>
            <div class="product-card-rating">{rating_str}</div>
        </div>"""
    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)


# ── Session state ──────────────────────────────────────────────────────────────
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
    st.session_state.message_responses = []
if 'staged_image' not in st.session_state:
    st.session_state.staged_image = None
if 'session_logger' not in st.session_state:
    st.session_state.session_logger = SessionLogger(
        site_id=_PINNED_SITE or os.getenv("SCAPI_SITE_ID", "NTOManaged")
    )
if 'eval_report' not in st.session_state:
    st.session_state.eval_report = None
if 'last_tool_calls' not in st.session_state:
    st.session_state.last_tool_calls = []
if 'last_trace_lines' not in st.session_state:
    st.session_state.last_trace_lines = []

_site_ui = get_site_ui(_PINNED_SITE or st.session_state.site_id)

# ── Left sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("About")
    st.markdown(_site_ui["about"])
    st.divider()

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
    cache_size = len(st.session_state.agent.product_cache)
    st.metric("Products Cached", cache_size)

    if st.button("🔄 Reset Conversation"):
        st.session_state.agent.reset()
        st.session_state.messages = []
        st.session_state.suggestions = []
        st.session_state.staged_image = None
        st.session_state.last_tool_calls = []
        st.session_state.last_trace_lines = []
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
    st.caption("Powered by Claude AI")


# ── Main layout ────────────────────────────────────────────────────────────────
col_chat, col_trace = st.columns([6, 4])

# ── Right trace panel ─────────────────────────────────────────────────────────
with col_trace:
    active_locale = getattr(st.session_state.agent, "_active_locale", "en_US") if hasattr(st.session_state, 'agent') else "en_US"
    turns = st.session_state.session_logger.turn if hasattr(st.session_state.get("session_logger", object()), "turn") else 0

    # Live trace — collapsible, at the top
    with st.expander("🔍 Live Trace", expanded=False):
        live_trace_placeholder = st.empty()
        if st.session_state.get("last_trace_lines"):
            trace_md = "\n\n".join(st.session_state.last_trace_lines)
            live_trace_placeholder.markdown(
                f'<div style="background:#0a0a0a;padding:12px 16px;border-radius:8px;">'
                f'<div style="font-size:11px;color:#60a5fa;font-family:monospace;'
                f'line-height:1.6;">{trace_md}</div></div>',
                unsafe_allow_html=True
            )

    st.markdown('<div class="trace-body">', unsafe_allow_html=True)

    # Tool calls from last turn
    if st.session_state.get("last_tool_calls"):
        st.markdown('<div class="trace-section-label" style="margin-top:16px">🔧 Last Tool Calls</div>', unsafe_allow_html=True)
        for call in st.session_state.last_tool_calls:
            inp = call.get("input", {})
            tool = call["tool"]
            duration = call["duration"]
            if tool.startswith("search_"):
                queries = inp.get("queries", [])
                detail = " · ".join(f"`{q.get('q','')}`" for q in queries[:2])
            elif tool == "web_search":
                detail = inp.get("query", "")[:60]
            elif tool == "create_todo":
                detail = inp.get("message", "")[:60]
            else:
                detail = str(inp)[:60]
            st.markdown(f"""
            <div class="trace-card">
                <div class="trace-card-label">{tool} · {duration}</div>
                <div class="trace-card-value blue">{detail}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ── Handle pending suggestion ──────────────────────────────────────────────────
user_input_from_suggestion = None
if st.session_state.pending_input:
    user_input_from_suggestion = st.session_state.pending_input
    st.session_state.pending_input = None
    st.session_state.suggestions = []


# ── Chat column ────────────────────────────────────────────────────────────────
with col_chat:
    # Phone header
    st.markdown(f"""
    <div class="phone-container">
        <div class="phone-header">
            <div class="phone-bot-avatar">{_site_ui["icon"]}</div>
            <div>
                <div class="phone-title">{_site_ui["title"]}</div>
                <div class="phone-subtitle">
                    <span class="phone-status-dot"></span>{_site_ui["subtitle"][:50]}
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Chat history
    assistant_message_count = 0
    for idx, message in enumerate(st.session_state.messages):
        if message["role"] == "user":
            with st.chat_message("user", avatar="👤"):
                if "image" in message and message["image"]:
                    st.image(message["image"], width=200)
                st.markdown(message["content"])
        else:
            with st.chat_message("assistant", avatar=_site_ui["icon"]):
                if assistant_message_count < len(st.session_state.message_responses):
                    response_data = st.session_state.message_responses[assistant_message_count]
                    if response_data and isinstance(response_data, dict) and 'response' in response_data:
                        for block in response_data['response']:
                            if not isinstance(block, dict):
                                continue
                            if block['type'] == 'markdown':
                                content = block['content'].replace('$', '\\$')
                                st.markdown(content)
                            elif block['type'] == 'product_table':
                                table_data = block.get('content', {})
                                title = table_data.get('title', 'Products')
                                products = table_data.get('products', [])
                                if products:
                                    st.markdown(f"**{title}**")
                                    _render_product_cards(
                                        products,
                                        st.session_state.agent.product_cache
                                    )
                        if response_data.get('follow_up'):
                            st.markdown(f"\n❓ **{response_data['follow_up']}**")
                    else:
                        content = response_data if isinstance(response_data, str) else message["content"]
                        st.markdown(content)
                else:
                    st.markdown(message["content"])
                assistant_message_count += 1

    # Suggestions
    if st.session_state.suggestions and not user_input_from_suggestion:
        st.markdown("**💡 Quick actions:**")
        cols = st.columns(min(len(st.session_state.suggestions), 3))
        for i, suggestion in enumerate(st.session_state.suggestions):
            if cols[i % 3].button(suggestion, key=f"sug_{i}", use_container_width=True):
                st.session_state.pending_input = suggestion
                st.rerun()

    # Starter queries
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

    # Input form
    user_input = None
    image_data_to_send = None

    if user_input_from_suggestion:
        user_input = user_input_from_suggestion
    else:
        with st.form("input_form", clear_on_submit=True):
            typed_text = st.text_input(
                _site_ui["chat_placeholder"],
                label_visibility="collapsed",
                placeholder=_site_ui["chat_placeholder"]
            )
            with st.expander("📸 Attach image"):
                uploaded_file = st.file_uploader("Upload image", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
                if uploaded_file:
                    st.image(uploaded_file, width=120, caption="Image ready — hit Send")
            submitted = st.form_submit_button("Send ✨", use_container_width=True)

        if submitted and (typed_text.strip() or uploaded_file):
            user_input = typed_text.strip() or "Visual search"
            if uploaded_file:
                image_data_to_send = uploaded_file.getvalue()
                st.session_state.staged_image = {"data": image_data_to_send, "name": uploaded_file.name}


# ── Agent execution ────────────────────────────────────────────────────────────
if user_input:
    if image_data_to_send is None and st.session_state.staged_image:
        image_data_to_send = st.session_state.staged_image["data"]
        st.session_state.staged_image = None

    if image_data_to_send:
        st.session_state.messages.append({"role": "user", "content": user_input, "image": image_data_to_send})
    else:
        st.session_state.messages.append({"role": "user", "content": user_input})

    trace_queue = queue.Queue()
    result_box = {}
    agent = st.session_state.agent

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

    trace_lines = []
    with col_chat:
        with st.spinner(_site_ui["search_label"]):
            while thread.is_alive() or not trace_queue.empty():
                updated = False
                while True:
                    try:
                        msg = trace_queue.get_nowait()
                        trace_lines.append(msg)
                        updated = True
                    except queue.Empty:
                        break
                if updated:
                    trace_md = "\n\n".join(trace_lines)
                    live_trace_placeholder.markdown(
                        f'<div style="background:#0a0a0a;padding:12px 16px;border-radius:8px;">'
                        f'<div style="font-size:11px;color:#60a5fa;font-family:monospace;'
                        f'line-height:1.6;">{trace_md}</div></div>',
                        unsafe_allow_html=True
                    )
                time.sleep(0.1)

    thread.join()

    if "error" in result_box:
        with col_chat:
            st.error(f"Error: {result_box['error']}")
            import traceback as tb
            st.code("".join(tb.format_exception(
                type(result_box["error"]), result_box["error"],
                result_box["error"].__traceback__
            )))
        st.stop()

    response = result_box["response"]
    if not isinstance(response, dict):
        response = {
            "response": [{"type": "markdown", "content": str(response)}],
            "follow_up": "",
            "suggestions": [],
            "tool_call_log": [],
        }

    with col_chat:
        with st.chat_message("assistant", avatar=_site_ui["icon"]):
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
                            st.markdown(f"**{title}**")
                            _render_product_cards(products, st.session_state.agent.product_cache)
                            response_text_for_history += f"\n\n**{title}** ({len(products)} products)\n"

            if response.get('follow_up'):
                st.markdown(f"\n❓ **{response['follow_up']}**")
                response_text_for_history += f"\n\n❓ {response['follow_up']}"

    st.session_state.messages.append({"role": "assistant", "content": response_text_for_history})
    st.session_state.message_responses.append(response)
    st.session_state.suggestions = response.get('suggestions', [])
    st.session_state.last_tool_calls = response.get('tool_call_log', [])
    st.session_state.last_trace_lines = trace_lines

    active_locale = getattr(st.session_state.agent, "_active_locale", None)
    st.session_state.session_logger.log_turn(user_input, response, locale=active_locale)

    st.rerun()
