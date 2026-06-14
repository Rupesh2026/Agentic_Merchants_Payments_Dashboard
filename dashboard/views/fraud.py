"""dashboard/views/fraud.py — Fraud & risk: heatmap, alerts, row-level SHAP, watchlist."""

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.settings import INDUSTRY_FRAUD_RATE
from dashboard import data
from dashboard.components import charts, tables


def _shap_inline(detail: dict):
    shap_raw = detail.get("top_shap_features")
    prob = detail.get("fraud_probability")
    risk = detail.get("risk_score")
    if prob is not None:
        st.metric("Fraud probability", f"{float(prob):.2%}", f"Risk {int(risk)}/100")
    if shap_raw:
        shap = json.loads(shap_raw) if isinstance(shap_raw, str) else shap_raw
        for f in (shap or [])[:3]:
            val = f.get("shap_value", 0)
            cls = "shap-feature-positive" if val > 0 else "shap-feature-negative"
            sign = "↑" if val > 0 else "↓"
            st.markdown(
                f'<div style="padding:3px 0"><span class="{cls}">{sign}</span> '
                f'{f.get("explanation", f.get("feature","?"))}</div>',
                unsafe_allow_html=True,
            )


def render():
    merchant = st.session_state.get("selected_merchant", "All Merchants")
    wl = st.session_state.setdefault("watchlist", set())

    st.markdown("## Fraud & Risk")
    st.markdown(
        '<p class="section-desc" style="margin-top:2px">Understand and act on fraud before it costs you — '
        'see which payments look suspicious, when fraud tends to happen, which merchants are most at risk, and what specifically made each transaction look like fraud.</p>',
        unsafe_allow_html=True,
    )

    if not data.has_data():
        st.warning("No data yet. Run `python run_pipeline.py` first.")
        return

    # ── Portfolio-level or merchant-level header metrics ──────────────────────
    if merchant != "All Merchants":
        mc = data.merchant_card(merchant)
        if mc.empty:
            st.warning(f"No data for merchant '{merchant}'.")
            return
        m = mc.iloc[0]
        fraud_vs = m["fraud_rate"] / max(INDUSTRY_FRAUD_RATE, 0.0001)
        banner_cls = "alert-banner" if fraud_vs > 1.5 else "alert-banner-warn" if fraud_vs > 0.8 else "alert-banner-ok"
        st.markdown(
            f'<div class="{banner_cls}"><strong>{merchant}</strong> — '
            f'Fraud rate {m["fraud_rate"]:.3%} ({fraud_vs:.1f}× industry avg) · '
            f'Chargebacks: {int(m["chargeback_count"])} · '
            f'Approval rate: {m["approval_rate"]:.2%} · '
            f'Avg risk score: {m["risk_score_avg"]:.0f}/100</div>',
            unsafe_allow_html=True,
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Fraud transactions", f"{int(m['fraud_count']):,}")
        c2.metric("Fraud rate", f"{m['fraud_rate']:.4%}", f"{fraud_vs:.1f}× industry", delta_color="inverse")
        c3.metric("Chargebacks", f"{int(m['chargeback_count']):,}")
        c4.metric("Avg risk score", f"{m['risk_score_avg']:.1f}/100")

        # Watchlist toggle
        in_wl = merchant in wl
        wl_lbl = "👁 Remove from Watchlist" if in_wl else "👁 Add to Watchlist"
        col_a, col_b = st.columns([1, 5])
        with col_a:
            if st.button(wl_lbl):
                wl.discard(merchant) if in_wl else wl.add(merchant)
                st.rerun()
        with col_b:
            if st.button("Ask AI about this merchant's fraud patterns"):
                st.session_state["page"] = "AI Analyst"
                st.session_state["ai_prefill"] = (
                    f"Analyze the fraud patterns for merchant '{merchant}'. "
                    f"Their fraud rate is {m['fraud_rate']:.3%} ({fraud_vs:.1f}× industry). "
                    f"What are the main risk factors and what should I watch out for?"
                )
                st.rerun()

        # Fraud transactions for this merchant
        st.markdown('<div class="section-header">Fraud transactions</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="section-desc">Every confirmed fraudulent payment for this merchant, ranked by how suspicious they looked — '
            'click a row to understand what triggered the alert.</p>',
            unsafe_allow_html=True,
        )
        fr = data.top_fraud_transactions(50, merchant=merchant)
        if fr.empty:
            st.info("No fraud transactions found for this merchant.")
            return

    else:
        # Portfolio summary
        kpi = data.kpi_all()
        total_tx = int(kpi["total_transactions"].sum())
        total_fraud = int(kpi["fraud_count"].sum())
        fraud_rate = total_fraud / max(total_tx, 1)

        if fraud_rate > INDUSTRY_FRAUD_RATE * 1.5:
            st.markdown(
                f'<div class="alert-banner">🚨 Portfolio fraud rate {fraud_rate:.4%} is '
                f'{fraud_rate/INDUSTRY_FRAUD_RATE:.1f}× the industry average.</div>',
                unsafe_allow_html=True,
            )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total fraud txns", f"{total_fraud:,}")
        c2.metric("Fraud rate", f"{fraud_rate:.4%}", f"{fraud_rate/INDUSTRY_FRAUD_RATE:.1f}× industry", delta_color="inverse")
        c3.metric("Chargebacks", f"{int(kpi['chargeback_count'].sum()):,}")
        risk = data.risk_distribution()
        flagged = int((risk["risk_score"] >= 70).sum()) if not risk.empty else 0
        c4.metric("High-risk txns (≥70)", f"{flagged:,}")

        # Watchlist panel
        if wl:
            st.markdown('<div class="section-header">Your watchlist</div>', unsafe_allow_html=True)
            st.markdown(
                '<p class="section-desc">Merchants you\'ve flagged for closer monitoring — '
                'add any merchant from any page using the "Add to Watchlist" button to track them here.</p>',
                unsafe_allow_html=True,
            )
            wl_cols = st.columns(min(len(wl), 4))
            for i, m_name in enumerate(sorted(wl)):
                with wl_cols[i % 4]:
                    mc = data.merchant_card(m_name)
                    if not mc.empty:
                        mr = mc.iloc[0]
                        st.markdown(
                            f'<div class="kpi-card">'
                            f'<div class="kpi-label">{mr["category"]}</div>'
                            f'<div class="kpi-value" style="font-size:15px">{m_name}</div>'
                            f'<div class="kpi-delta-down">Fraud {mr["fraud_rate"]:.3%}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        if st.button(f"Open {m_name[:20]}", key=f"wl_{i}"):
                            st.session_state["selected_merchant"] = m_name
                            st.session_state["page"] = "Overview"
                            st.rerun()

        left, right = st.columns([3, 2])
        with left:
            st.markdown('<div class="section-header">Fraud rate by hour × day</div>', unsafe_allow_html=True)
            st.markdown(
                '<p class="section-desc">When do fraudulent payments most often occur? '
                'Darker cells mean higher fraud rates — use this to decide when to apply stricter verification or increase monitoring.</p>',
                unsafe_allow_html=True,
            )
            hm = data.fraud_heatmap()
            if not hm.empty:
                st.plotly_chart(charts.fraud_heatmap_fig(hm), use_container_width=True)
        with right:
            st.markdown('<div class="section-header">Risk score distribution</div>', unsafe_allow_html=True)
            st.markdown(
                '<p class="section-desc">How risk is spread across all your payments — '
                'most transactions should cluster near 0 (safe); a tall bar on the right means many high-risk payments that need review.</p>',
                unsafe_allow_html=True,
            )
            if not risk.empty:
                st.plotly_chart(charts.risk_histogram(risk), use_container_width=True)

        # Highest-risk merchants with watchlist button
        st.markdown('<div class="section-header">Highest-risk merchants</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="section-desc">The 10 merchants with the highest proportion of fraudulent payments — '
            'the "× industry" column shows how many times above the normal baseline their fraud rate is; click a row to dig in or add them to your watchlist.</p>',
            unsafe_allow_html=True,
        )
        hot = data.merchant_stats(order_by="fraud_rate", limit=10).copy()
        if not hot.empty:
            hot["x_industry"] = hot["fraud_rate"] / INDUSTRY_FRAUD_RATE
            ev = st.dataframe(
                hot[["merchant", "category", "total_transactions", "fraud_count", "fraud_rate", "x_industry", "risk_score_avg"]],
                use_container_width=True, hide_index=True,
                on_select="rerun", selection_mode="single-row",
                column_config={
                    "fraud_rate": st.column_config.NumberColumn("Fraud rate", format="%.4f"),
                    "x_industry": st.column_config.NumberColumn("× industry", format="%.1fx"),
                    "risk_score_avg": st.column_config.ProgressColumn("Avg risk", min_value=0, max_value=100, format="%.0f"),
                },
            )
            if ev.selection.rows:
                sel_merchant = hot.iloc[ev.selection.rows[0]]["merchant"]
                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button(f"Open '{sel_merchant}'"):
                        st.session_state["selected_merchant"] = sel_merchant
                        st.session_state["page"] = "Overview"
                        st.rerun()
                with b2:
                    in_wl = sel_merchant in wl
                    if st.button("👁 Remove from Watchlist" if in_wl else "👁 Add to Watchlist", key="wl_hot"):
                        wl.discard(sel_merchant) if in_wl else wl.add(sel_merchant)
                        st.rerun()
                with b3:
                    if st.button("Ask AI about this merchant", key="ai_hot"):
                        st.session_state["page"] = "AI Analyst"
                        st.session_state["ai_prefill"] = f"Analyze fraud risk for merchant '{sel_merchant}'."
                        st.rerun()

        fr = data.top_fraud_transactions(50)

    # ── Fraud transactions table (shared between merchant and portfolio mode) ──
    st.markdown('<div class="section-header">Top fraud transactions</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-desc">The highest-risk confirmed fraudulent payments — '
        'click any row to see exactly which factors made it suspicious and get a plain-English explanation of the risk drivers.</p>',
        unsafe_allow_html=True,
    )

    if fr.empty:
        st.info("No scored fraud transactions yet.")
        return

    display = fr[["trans_num", "trans_at", "merchant", "category", "amt",
                  "state", "risk_score", "risk_tier", "fraud_probability"]].copy()
    display["trans_at"] = pd.to_datetime(display["trans_at"]).dt.strftime("%Y-%m-%d %H:%M")
    display["amt"] = display["amt"].apply(lambda x: round(float(x), 2))
    display["risk_score"] = display["risk_score"].fillna(0).astype(int)
    display["fraud_probability"] = display["fraud_probability"].apply(
        lambda x: round(float(x), 4) if pd.notna(x) else 0.0
    )

    ev = st.dataframe(
        display,
        use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "amt": st.column_config.NumberColumn("Amount", format="$%.2f"),
            "risk_score": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%d"),
            "fraud_probability": st.column_config.NumberColumn("Fraud prob", format="%.2%"),
        },
    )

    if ev.selection.rows:
        row = display.iloc[ev.selection.rows[0]]
        trans_num = row["trans_num"]
        st.markdown(f'<div class="section-header">Why was this payment flagged? — {trans_num}</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<p class="section-desc">Red arrows (↑) are the reasons this payment looked fraudulent; '
            'green arrows (↓) are what made it look more legitimate. Use "Full AI explanation" for a plain-English narrative.</p>',
            unsafe_allow_html=True,
        )
        detail = data.transaction_detail(trans_num)
        if detail:
            _shap_inline(detail)
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Full AI explanation", use_container_width=True):
                    st.session_state["page"] = "AI Analyst"
                    st.session_state["ai_prefill"] = (
                        f"Explain why transaction {trans_num} at '{detail.get('merchant')}' "
                        f"for ${float(detail.get('amt',0)):.2f} is flagged as fraud. "
                        f"Risk score: {detail.get('risk_score','?')}/100."
                    )
                    st.rerun()
            with b2:
                m_name = detail.get("merchant", "")
                in_wl = m_name in wl
                if st.button("👁 Remove from Watchlist" if in_wl else "👁 Watch Merchant", use_container_width=True, key="wl_fr"):
                    wl.discard(m_name) if in_wl else wl.add(m_name)
                    st.rerun()
