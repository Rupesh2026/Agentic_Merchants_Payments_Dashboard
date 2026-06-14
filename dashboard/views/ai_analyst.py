"""dashboard/views/ai_analyst.py — AI Analyst chat with merchant context injection."""

import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from rag.prompts import SUGGESTED_PROMPTS
    from rag.security import SAFE_REFUSAL
    from rag.security import sanitize_user_input
except Exception:
    SUGGESTED_PROMPTS = [
        "What are the top 3 fraud patterns in the last 30 days?",
        "Give me a payout summary for the last 4 weeks",
        "Which merchants should I monitor for fraud?",
        "Which states have the most fraudulent transactions?",
    ]
    SAFE_REFUSAL = "I cannot help with that request."

    def sanitize_user_input(text):  # type: ignore[no-redef]
        return type("Result", (), {"text": text, "blocked": False, "canary_hits": ()})()


def _merchant_context_prefix(merchant: str) -> str:
    """Build a context prefix for queries when a merchant is selected."""
    if not merchant or merchant == "All Merchants":
        return ""
    return f"[Context: focusing on merchant '{merchant}'] "


def render():
    merchant = st.session_state.get("selected_merchant", "All Merchants")

    st.markdown("## AI Analyst")

    # ── Merchant context badge ────────────────────────────────────────────────
    if merchant != "All Merchants":
        st.markdown(
            f'<div class="alert-banner-ok">'
            f'Focused on <strong>{merchant}</strong> — '
            f'all questions will be answered in the context of this merchant. '
            f'Switch to "All Merchants" in the sidebar to ask about the full portfolio.'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<p class="section-desc" style="margin-top:2px">Your personal payments analyst — '
            'ask any business question in plain English and get an answer backed by your live transaction data. '
            'No spreadsheets, no SQL, just ask.</p>',
            unsafe_allow_html=True,
        )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "ai_session_id" not in st.session_state:
        st.session_state.ai_session_id = f"dash-{uuid.uuid4().hex[:8]}"

    # ── Merchant-specific quick prompts ───────────────────────────────────────
    if merchant != "All Merchants":
        merchant_prompts = [
            f"What is the fraud pattern for '{merchant}'?",
            f"Compare '{merchant}' to peers in their category",
            f"What are the top risk factors for '{merchant}'?",
            f"Show me recent high-risk transactions for '{merchant}'",
        ]
        st.markdown("**Quick questions about this merchant:**")
        cols = st.columns(4)
        for i, prompt in enumerate(merchant_prompts):
            if cols[i].button(prompt, key=f"mprompt_{i}", use_container_width=True):
                st.session_state.pending_prompt = _merchant_context_prefix(merchant) + prompt
    else:
        st.markdown("**Try asking:**")
        cols = st.columns(4)
        for i, prompt in enumerate(SUGGESTED_PROMPTS[:8]):
            if cols[i % 4].button(prompt, key=f"prompt_{i}", use_container_width=True):
                st.session_state.pending_prompt = prompt

    st.markdown("---")

    # ── Chat history ──────────────────────────────────────────────────────────
    for turn in st.session_state.chat_history:
        avatar = None if turn["role"] == "user" else "🤖"
        with st.chat_message(turn["role"], avatar=avatar):
            st.markdown(turn["content"])

    # ── Handle prefill from other pages ───────────────────────────────────────
    if "ai_prefill" in st.session_state:
        prefill = st.session_state.pop("ai_prefill")
        _process_message(prefill, merchant)
        st.rerun()

    if "pending_prompt" in st.session_state:
        _process_message(st.session_state.pop("pending_prompt"), merchant)
        st.rerun()

    # ── Chat input ────────────────────────────────────────────────────────────
    placeholder = (
        f"Ask about '{merchant}'…" if merchant != "All Merchants"
        else "Ask about any transaction, merchant, pattern, or metric…"
    )
    user_input = st.chat_input(placeholder)
    if user_input:
        full_input = _merchant_context_prefix(merchant) + user_input
        _process_message(full_input, merchant)
        st.rerun()

    # ── Sidebar controls ──────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("---")
        if st.button("Clear conversation"):
            st.session_state.chat_history = []
            st.session_state.ai_session_id = f"dash-{uuid.uuid4().hex[:8]}"
            st.rerun()


def _process_message(user_input: str, merchant: str = ""):
    sanitized = sanitize_user_input(user_input)
    st.session_state.chat_history.append({"role": "user", "content": sanitized.text})
    with st.spinner("Analyzing…"):
        try:
            from rag.agent import ask
            if sanitized.blocked:
                response = SAFE_REFUSAL
            else:
                response = ask(sanitized.text, session_id=st.session_state.ai_session_id)
        except ImportError:
            response = (
                "⚠️ RAG agent unavailable. Install deps and run "
                "`python run_pipeline.py --phase rag`."
            )
        except Exception as e:
            response = f"Error: {e}"
    st.session_state.chat_history.append({"role": "assistant", "content": response})
