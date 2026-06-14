"""dashboard/views/overview.py — Overview: KPI summary + merchant context."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.settings import CATEGORY_DISPLAY, INDUSTRY_FRAUD_RATE
from dashboard import data
from dashboard.components import charts
from dashboard.components.kpi_cards import kpi_card, pct_delta
from dashboard.components import tables

PERIOD_DAYS = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90, "All time": 730}


def _nav(page: str):
    st.session_state["page"] = page
    st.rerun()


def render():
    merchant = st.session_state.get("selected_merchant", "All Merchants")
    days = PERIOD_DAYS.get(st.session_state.get("period", "Last 30 days"), 30)

    if not data.has_data():
        st.warning("No data yet. Run `python run_pipeline.py` first.")
        return

    # ── Merchant context header ───────────────────────────────────────────────
    if merchant != "All Merchants":
        mc = data.merchant_card(merchant)
        if not mc.empty:
            m = mc.iloc[0]
            fraud_ok = m["fraud_rate"] <= INDUSTRY_FRAUD_RATE * 1.5
            banner_cls = "alert-banner-ok" if fraud_ok else "alert-banner"
            fraud_vs = m["fraud_rate"] / max(INDUSTRY_FRAUD_RATE, 0.0001)
            st.markdown(
                f"""<div class="{banner_cls}">
                  <strong>{merchant}</strong> &nbsp;·&nbsp; {m['category']} &nbsp;·&nbsp;
                  {m['total_transactions']:,} transactions &nbsp;·&nbsp;
                  Fraud {m['fraud_rate']:.3%} ({fraud_vs:.1f}× industry avg) &nbsp;·&nbsp;
                  Avg risk score {m['risk_score_avg']:.0f}/100
                </div>""",
                unsafe_allow_html=True,
            )

    # ── Load time-series data ─────────────────────────────────────────────────
    if merchant != "All Merchants":
        df = data.merchant_kpi_daily(merchant)
        if df.empty:
            st.info(f"No data found for merchant '{merchant}'.")
            return
    else:
        df = data.kpi_daily(days)

    df = df.sort_values("date", ascending=False)
    latest = df.iloc[0]
    prior = df.iloc[1] if len(df) > 1 else df.iloc[0]

    st.markdown("## Overview")
    st.markdown(
        '<p class="section-desc" style="margin-top:2px">Your business at a glance — '
        'see how much revenue you processed, how healthy your transactions are, and whether fraud is under control, all in one place.</p>',
        unsafe_allow_html=True,
    )

    # ── KPI cards (with navigation buttons below) ─────────────────────────────
    st.markdown('<div class="section-header">Performance</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-desc">How much money your business processed — '
        'Gross Volume is the total customer spend, Net Volume is what you actually receive after card network fees are deducted.</p>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        d, t = pct_delta(latest.gross_volume, prior.gross_volume)
        kpi_card("Gross Volume", f"${latest.gross_volume:,.0f}", d, t)
        if st.button("→ Performance", key="nav_perf", use_container_width=True):
            _nav("Performance")

    with c2:
        d, t = pct_delta(latest.total_transactions, prior.total_transactions)
        kpi_card("Transactions", f"{int(latest.total_transactions):,}", d, t)
        if st.button("→ Explore", key="nav_txns", use_container_width=True):
            _nav("Transactions")

    with c3:
        d, t = pct_delta(latest.avg_ticket, prior.avg_ticket)
        kpi_card("Avg Ticket", f"${latest.avg_ticket:.2f}", d, t)
        if st.button("→ Transactions", key="nav_txns2", use_container_width=True):
            _nav("Transactions")

    with c4:
        net = latest.get("net_volume", latest.gross_volume * 0.98)
        fees = latest.get("processing_fees", latest.gross_volume * 0.02)
        kpi_card("Net Volume", f"${net:,.0f}", f"After ${fees:,.0f} fees", "flat")
        if st.button("→ Payouts", key="nav_payouts", use_container_width=True):
            _nav("Payouts")

    trend_grain = st.selectbox(
        "Trend granularity",
        ["Month", "Quarter", "Year"],
        index=0,
        key="overview_trend_grain",
    )

    st.markdown('<div class="section-header">Transaction Health</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-desc">Are your customers\' payments going through cleanly? '
        'A high decline count means customers are being turned away at checkout; chargebacks mean disputes you\'re liable for.</p>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        d, t = pct_delta(latest.approval_rate, prior.approval_rate)
        kpi_card("Approval Rate", f"{latest.approval_rate:.2%}", d, t)

    with c2:
        declined_n = int(latest.get("declined_count", 0))
        kpi_card(
            "Declined", f"{declined_n:,}",
            f"{declined_n / max(int(latest.total_transactions), 1):.2%} of txns",
            "down" if declined_n > int(prior.get("declined_count", 0)) else "up",
        )

    with c3:
        cb = int(latest.get("chargeback_count", 0))
        kpi_card(
            "Chargebacks", f"{cb:,}",
            "↑ vs prior" if cb > int(prior.get("chargeback_count", 0)) else "stable",
            "down" if cb > int(prior.get("chargeback_count", 0)) else "up",
        )

    with c4:
        fr = latest.fraud_rate
        ind_ok = fr <= INDUSTRY_FRAUD_RATE
        d, _ = pct_delta(fr, prior.fraud_rate)
        kpi_card("Fraud Rate", f"{fr:.4%}", d, "up" if ind_ok else "down")
        if st.button("→ Fraud & Risk", key="nav_fraud", use_container_width=True):
            _nav("Fraud & Risk")

    # ── Charts ────────────────────────────────────────────────────────────────
    chart_source = data.merchant_kpi_daily(merchant) if merchant != "All Merchants" else data.kpi_all()
    chart_df = charts.aggregate_kpi_timeseries(chart_source.sort_values("date"), trend_grain)

    left, right = st.columns([2, 1])
    with left:
        st.markdown("**Revenue & fraud trend**")
        st.markdown(
            '<p class="section-desc">Each bar is one period of revenue. '
            'The red line shows fraud activity for the same periods so you can see whether risk rises with growth or spikes on its own. '
            'If the fraud line sits at zero, no fraudulent payments were detected in that view.</p>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            charts.revenue_chart(chart_df, x="period_label", y="gross_volume"),
            use_container_width=True,
        )
    with right:
        if merchant == "All Merchants":
            cats = data.category_stats().head(6).copy()
            cats["display"] = cats["category"].map(CATEGORY_DISPLAY).fillna(cats["category"])
            st.markdown("**Top categories**")
            st.markdown(
                '<p class="section-desc">Which types of businesses generate the most payment volume — '
                'your highest-revenue categories are where you want to focus growth and fraud prevention equally.</p>',
                unsafe_allow_html=True,
            )
            st.plotly_chart(
                charts.hbar(cats, "pct_of_volume", "display", pct=True),
                use_container_width=True,
            )
        else:
            total_n = max(int(latest.total_transactions), 1)
            approved_n = int(latest.approval_rate * total_n)
            declined_n = total_n - approved_n
            st.markdown("**Approval mix (last period)**")
            st.markdown(
                '<p class="section-desc">How many of this merchant\'s payment attempts succeeded — '
                'a high decline share means customers are hitting checkout failures and potentially abandoning their purchase.</p>',
                unsafe_allow_html=True,
            )
            st.plotly_chart(
                charts.donut(
                    ["Approved", "Declined"],
                    [approved_n, declined_n],
                    colors=["#1a7f37", "#cf222e"],
                ),
                use_container_width=True,
            )

    # ── Recent transactions ───────────────────────────────────────────────────
    st.markdown('<div class="section-header">Recent Transactions</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-desc">Your 15 most recent transactions with their status and risk score — '
        'any entry showing a high risk score or "flagged" status should be reviewed for potential fraud.</p>',
        unsafe_allow_html=True,
    )

    txns = data.recent_transactions(
        15, merchant=merchant if merchant != "All Merchants" else ""
    )
    if txns.empty:
        st.info("No recent transactions.")
        return

    txns["Status"] = txns["txn_status"].apply(tables.status_pill)
    txns["Risk"] = txns["risk_score"].apply(tables.risk_badge)
    txns["Time"] = pd.to_datetime(txns["trans_at"]).dt.strftime("%b %d %H:%M")
    txns["Amount"] = txns["amt"].apply(tables.money)

    cols = {"merchant": "Merchant", "category": "Category", "Amount": "Amount",
            "card_network": "Network", "Status": "Status", "Risk": "Risk", "Time": "Time"}
    if merchant != "All Merchants":
        cols.pop("merchant", None)

    tables.render_transactions(txns, cols)

    if st.button("View all transactions →"):
        _nav("Transactions")
