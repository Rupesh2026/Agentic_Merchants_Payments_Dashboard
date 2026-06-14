"""dashboard/views/transactions.py — Transaction explorer with row selection + SHAP detail."""

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard import data
from dashboard.components import tables


def _shap_panel(detail: dict):
    risk = detail.get("risk_score")
    prob = detail.get("fraud_probability")
    tier = str(detail.get("risk_tier", "")).upper()
    shap_raw = detail.get("top_shap_features")

    col1, col2, col3 = st.columns(3)
    col1.metric("Risk Score", f"{int(risk)}/100" if risk is not None else "—", tier)
    col2.metric("Fraud Probability", f"{float(prob):.2%}" if prob is not None else "—")
    col3.metric("Status", str(detail.get("txn_status", "—")).title())

    if shap_raw:
        shap = json.loads(shap_raw) if isinstance(shap_raw, str) else shap_raw
        st.markdown("**Top contributing factors:**")
        for f in (shap or [])[:3]:
            val = f.get("shap_value", 0)
            direction = "shap-feature-positive" if val > 0 else "shap-feature-negative"
            sign = "↑ increases" if val > 0 else "↓ decreases"
            st.markdown(
                f'<div style="padding:4px 0">'
                f'<span class="{direction}">{sign} risk</span> &nbsp;·&nbsp; '
                f'{f.get("explanation", f.get("feature", "?"))}'
                f'</div>',
                unsafe_allow_html=True,
            )

    info_cols = st.columns(4)
    info_cols[0].markdown(f"**Merchant**<br>{detail.get('merchant','—')}", unsafe_allow_html=True)
    info_cols[1].markdown(f"**Category**<br>{detail.get('category','—')}", unsafe_allow_html=True)
    info_cols[2].markdown(f"**Location**<br>{detail.get('city','?')}, {detail.get('state','?')}", unsafe_allow_html=True)
    info_cols[3].markdown(f"**Network**<br>{detail.get('card_network','—')}", unsafe_allow_html=True)

    if detail.get("has_chargeback"):
        st.markdown('<div class="alert-banner">⚠️ This transaction has an associated chargeback.</div>', unsafe_allow_html=True)
    elif detail.get("is_fraud"):
        st.markdown('<div class="alert-banner-warn">🚨 Flagged as fraudulent in the dataset.</div>', unsafe_allow_html=True)


def render():
    merchant = st.session_state.get("selected_merchant", "All Merchants")
    st.markdown("## Transaction Explorer")
    st.markdown(
        '<p class="section-desc" style="margin-top:2px">Search every payment in your history — '
        'filter by business type, state, status, or risk level to find exactly what you\'re looking for, then click any row to understand why it was flagged or approved.</p>',
        unsafe_allow_html=True,
    )

    if not data.has_data():
        st.warning("No data yet. Run `python run_pipeline.py` first.")
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    opts = data.filter_options()
    fc = st.columns(5)
    category  = fc[0].selectbox("Category", [""] + opts["categories"])
    state     = fc[1].selectbox("State", [""] + opts["states"])
    status    = fc[2].selectbox("Status", ["", "approved", "declined", "flagged"])
    risk_tier = fc[3].selectbox("Risk tier", ["", "low", "medium", "high", "critical"])
    min_amt   = fc[4].number_input("Min amount ($)", min_value=0.0, value=0.0, step=50.0)

    limit = st.slider("Max rows", 50, 2000, 200, step=50)

    if merchant != "All Merchants":
        st.markdown(
            f'<div class="alert-banner-warn">Showing <strong>{merchant}</strong> only — '
            f'select "All Merchants" in sidebar to see portfolio.</div>',
            unsafe_allow_html=True,
        )

    df = data.transactions(
        category=category, state=state, status=status,
        risk_tier=risk_tier, min_amt=min_amt, limit=limit,
        merchant=merchant,
    )

    # ── Summary metrics ───────────────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Shown", f"{len(df):,}")
    m2.metric("Volume", f"${df['amt'].sum():,.0f}" if not df.empty else "—")
    m3.metric("Avg ticket", f"${df['amt'].mean():,.2f}" if not df.empty else "—")
    fraud_n = int(df["is_fraud"].sum()) if "is_fraud" in df.columns and not df.empty else 0
    m4.metric("Fraud rows", f"{fraud_n:,}")
    avg_risk = df["risk_score"].dropna().mean() if not df.empty else float("nan")
    m5.metric("Avg risk", f"{avg_risk:.0f}" if not pd.isna(avg_risk) else "—")

    if df.empty:
        st.info("No transactions match these filters.")
        return

    # ── Export ────────────────────────────────────────────────────────────────
    st.download_button(
        "⬇ Export CSV", df.to_csv(index=False),
        file_name="transactions_export.csv", mime="text/csv",
    )

    # ── Selectable table ──────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">Transaction table</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="section-desc">Each row is one payment — the Risk column (0–100) shows how suspicious that transaction looks; '
        'anything above 70 is worth a closer look. Click a row to see exactly what raised the concern.</p>',
        unsafe_allow_html=True,
    )

    display = df[["trans_num", "trans_at", "merchant", "category", "amt",
                  "state", "card_network", "txn_status", "risk_score", "risk_tier"]].copy()
    display["trans_at"] = pd.to_datetime(display["trans_at"]).dt.strftime("%Y-%m-%d %H:%M")
    display["amt"] = display["amt"].apply(lambda x: round(float(x), 2))
    display["risk_score"] = display["risk_score"].fillna(0).astype(int)

    event = st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "trans_num": st.column_config.TextColumn("Transaction", width="medium"),
            "trans_at": st.column_config.TextColumn("Time"),
            "amt": st.column_config.NumberColumn("Amount", format="$%.2f"),
            "risk_score": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%d"),
            "txn_status": st.column_config.TextColumn("Status"),
        },
    )

    # ── Detail panel ──────────────────────────────────────────────────────────
    if event.selection.rows:
        row = display.iloc[event.selection.rows[0]]
        trans_num = row["trans_num"]

        st.markdown(
            f'<div class="section-header">Risk detail — {trans_num}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<p class="section-desc">Why was this payment considered risky? '
            'Red arrows (↑) show factors that raised the suspicion level; green arrows (↓) show what made it look more legitimate.</p>',
            unsafe_allow_html=True,
        )

        detail = data.transaction_detail(trans_num)
        if detail:
            _shap_panel(detail)

            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("🤖 Ask AI to explain this transaction", use_container_width=True):
                    q = (
                        f"Explain the fraud risk for transaction {trans_num} "
                        f"at '{detail.get('merchant')}' for ${float(detail.get('amt',0)):.2f}. "
                        f"Risk score {detail.get('risk_score','N/A')}/100."
                    )
                    st.session_state["page"] = "AI Analyst"
                    st.session_state["ai_prefill"] = q
                    st.rerun()
            with b2:
                m_name = detail.get("merchant", "")
                wl = st.session_state.setdefault("watchlist", set())
                in_wl = m_name in wl
                lbl = "👁 Remove from Watchlist" if in_wl else "👁 Add to Watchlist"
                if st.button(lbl, use_container_width=True):
                    wl.discard(m_name) if in_wl else wl.add(m_name)
                    st.rerun()
            with b3:
                if st.button("Drill into Merchant", use_container_width=True):
                    st.session_state["selected_merchant"] = m_name
                    st.session_state["page"] = "Overview"
                    st.rerun()
        else:
            st.warning("Transaction detail not found.")
