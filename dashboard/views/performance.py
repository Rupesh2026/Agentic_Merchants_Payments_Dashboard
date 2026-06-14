"""dashboard/views/performance.py — Revenue, category, geographic & demographic analytics."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.settings import CATEGORY_DISPLAY, INDUSTRY_FRAUD_RATE
from dashboard import data
from dashboard.components import charts


def render():
    merchant = st.session_state.get("selected_merchant", "All Merchants")
    st.markdown("## Performance")
    st.markdown(
        '<p class="section-desc" style="margin-top:2px">Deep dive into your business growth — '
        'see which product categories and regions drive the most revenue, how your approval rate is trending, and how you compare to similar businesses.</p>',
        unsafe_allow_html=True,
    )

    if not data.has_data():
        st.warning("No data yet. Run `python run_pipeline.py` first.")
        return

    trend_grain = st.selectbox(
        "Trend granularity",
        ["Month", "Quarter", "Year"],
        index=0,
        key="performance_trend_grain",
    )

    # ── Merchant mode ─────────────────────────────────────────────────────────
    if merchant != "All Merchants":
        mc = data.merchant_card(merchant)
        if mc.empty:
            st.warning(f"No data for merchant '{merchant}'.")
            return
        m = mc.iloc[0]
        mkpi = data.merchant_kpi_daily(merchant)
        port_kpi = data.kpi_all()
        port_fr = port_kpi["fraud_rate"].mean()
        port_ar = port_kpi["approval_rate"].mean()

        st.markdown(
            f'<div class="alert-banner-ok">Performance for <strong>{merchant}</strong> ({m["category"]})</div>',
            unsafe_allow_html=True,
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Volume", f"${m['total_volume']:,.0f}")
        c2.metric("Transactions", f"{int(m['total_transactions']):,}")
        c3.metric("Fraud Rate", f"{m['fraud_rate']:.3%}", f"Portfolio {port_fr:.3%}", delta_color="inverse")
        c4.metric("Approval Rate", f"{m['approval_rate']:.2%}", f"Portfolio {port_ar:.2%}")

        if m["fraud_rate"] > INDUSTRY_FRAUD_RATE * 2:
            st.markdown(
                f'<div class="alert-banner">⚠️ Fraud rate {m["fraud_rate"]:.3%} is '
                f'{m["fraud_rate"]/INDUSTRY_FRAUD_RATE:.1f}× the industry average (0.58%).</div>',
                unsafe_allow_html=True,
            )

        if not mkpi.empty:
            st.markdown('<div class="section-header">Revenue trend</div>', unsafe_allow_html=True)
            st.markdown(
                '<p class="section-desc">Each bar is one period of revenue. '
                'Hover for the exact amount. Use the period selector above to switch between month, quarter, and year views.</p>',
                unsafe_allow_html=True,
            )
            trend_df = charts.aggregate_kpi_timeseries(mkpi, trend_grain)
            st.plotly_chart(
                charts.time_bar_chart(trend_df, "period_label", "gross_volume", title_y="Revenue ($)"),
                use_container_width=True,
            )

            left, right = st.columns(2)
            with left:
                st.markdown('<div class="section-header">Payment success rate</div>', unsafe_allow_html=True)
                st.markdown(
                    '<p class="section-desc">Higher is better. This shows the share of payment attempts that were approved, so merchants can spot checkout failures before they lose sales.</p>',
                    unsafe_allow_html=True,
                )
                st.plotly_chart(
                    charts.time_bar_chart(
                        trend_df,
                        "period_label",
                        "approval_rate",
                        color="#1a7f37",
                        title_y="Payment success rate",
                        percent=True,
                    ),
                    use_container_width=True,
                )
            with right:
                st.markdown('<div class="section-header">Fraud share</div>', unsafe_allow_html=True)
                st.markdown(
                    '<p class="section-desc">Lower is better. This shows the share of payments flagged as fraud in the selected period. '
                    'If this stays at zero, no fraudulent payments were detected in the visible window.</p>',
                    unsafe_allow_html=True,
                )
                st.plotly_chart(
                    charts.time_bar_chart(
                        trend_df,
                        "period_label",
                        "fraud_rate",
                        color="#cf222e",
                        title_y="Fraud share",
                        percent=True,
                    ),
                    use_container_width=True,
                )

        # Peer comparison
        cat = m["category"]
        st.markdown(f'<div class="section-header">Peer comparison — {cat}</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="section-desc">How does this merchant compare to others in the same business category? '
            'Click any row to switch to that merchant and see their full performance side by side.</p>',
            unsafe_allow_html=True,
        )
        peers = data.merchant_stats(order_by="total_volume", limit=200)
        peers = peers[peers["category"] == cat].sort_values("total_volume", ascending=False).head(10)
        if not peers.empty:
            ev = st.dataframe(
                peers[["merchant", "total_volume", "total_transactions", "avg_ticket", "fraud_rate", "approval_rate", "risk_score_avg"]],
                use_container_width=True, hide_index=True,
                on_select="rerun", selection_mode="single-row",
                column_config={
                    "total_volume": st.column_config.NumberColumn("Volume", format="$%.0f"),
                    "avg_ticket": st.column_config.NumberColumn("Avg ticket", format="$%.2f"),
                    "fraud_rate": st.column_config.NumberColumn("Fraud rate", format="%.4f"),
                    "risk_score_avg": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%.0f"),
                },
            )
            if ev.selection.rows:
                peer_name = peers.iloc[ev.selection.rows[0]]["merchant"]
                if st.button(f"📊 Switch to '{peer_name}'"):
                    st.session_state["selected_merchant"] = peer_name
                    st.rerun()
        return

    # ── Portfolio mode ────────────────────────────────────────────────────────
    kpi = data.kpi_all()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Gross Volume", f"${kpi['gross_volume'].sum():,.0f}")
    c2.metric("Total Transactions", f"{int(kpi['total_transactions'].sum()):,}")
    c3.metric("Avg Approval Rate", f"{kpi['approval_rate'].mean():.2%}")

    st.markdown('<div class="section-header">Revenue trend</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-desc">Each bar is one period of revenue. '
        'Hover for the exact amount and use the period selector above to switch between month, quarter, and year views.</p>',
        unsafe_allow_html=True,
    )
    trend_df = charts.aggregate_kpi_timeseries(kpi, trend_grain)
    st.plotly_chart(
        charts.time_bar_chart(trend_df, "period_label", "gross_volume", title_y="Revenue ($)"),
        use_container_width=True,
    )

    left, right = st.columns(2)
    with left:
        st.markdown('<div class="section-header">Volume by category</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="section-desc">Which types of businesses are bringing in the most revenue — '
            'the longer the bar, the bigger the category; cross-reference with the Fraud page to see which also carry higher risk.</p>',
            unsafe_allow_html=True,
        )
        cats = data.category_stats().copy()
        cats["display"] = cats["category"].map(CATEGORY_DISPLAY).fillna(cats["category"])
        st.plotly_chart(charts.hbar(cats.sort_values("total_volume"), "total_volume", "display"), use_container_width=True)
    with right:
        st.markdown('<div class="section-header">Top states by volume</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="section-desc">Where your customers are located — '
            'the states with the most payments are your core markets; check the Fraud page to see if those same states have elevated dispute rates.</p>',
            unsafe_allow_html=True,
        )
        states = data.state_stats().head(12).sort_values("total_volume")
        st.plotly_chart(charts.hbar(states, "total_volume", "state"), use_container_width=True)

    st.markdown('<div class="section-header">Customer demographics</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-desc">Who is buying from your merchants — '
        'transaction counts by age group and gender show which customer segments are most active and help tailor your risk and marketing strategy.</p>',
        unsafe_allow_html=True,
    )
    demo = data.demographics()
    if not demo.empty:
        demo["gender"] = demo["gender"].fillna("?")
        st.plotly_chart(charts.grouped_bar(demo, "age_group", "tx", "gender"), use_container_width=True)

    st.markdown('<div class="section-header">Category detail</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-desc">A full breakdown of each business category — '
        'Avg Ticket is the typical purchase size, Fraud Rate shows how risky the category is, and % of Volume shows its share of total revenue.</p>',
        unsafe_allow_html=True,
    )
    cat_tbl = data.category_stats().copy()
    cat_tbl["category"] = cat_tbl["category"].map(CATEGORY_DISPLAY).fillna(cat_tbl["category"])
    st.dataframe(
        cat_tbl[["category", "total_volume", "total_transactions", "avg_ticket", "fraud_rate", "approval_rate", "pct_of_volume"]],
        use_container_width=True, hide_index=True,
        column_config={
            "total_volume": st.column_config.NumberColumn("Volume", format="$%.0f"),
            "avg_ticket": st.column_config.NumberColumn("Avg ticket", format="$%.2f"),
            "fraud_rate": st.column_config.NumberColumn("Fraud rate", format="%.4f"),
            "approval_rate": st.column_config.NumberColumn("Approval", format="%.4f"),
            "pct_of_volume": st.column_config.NumberColumn("% volume", format="%.3f"),
        },
    )

    st.markdown('<div class="section-header">Top merchants by volume</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-desc">Your 15 highest-revenue merchants — '
        'click any row to open that merchant\'s full profile including their payment trends, fraud exposure, and how they compare to competitors.</p>',
        unsafe_allow_html=True,
    )
    top_m = data.merchant_stats(order_by="total_volume", limit=15).copy()
    if not top_m.empty:
        ev = st.dataframe(
            top_m[["merchant", "category", "total_volume", "total_transactions", "avg_ticket", "fraud_rate", "risk_score_avg"]],
            use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            column_config={
                "total_volume": st.column_config.NumberColumn("Volume", format="$%.0f"),
                "avg_ticket": st.column_config.NumberColumn("Avg ticket", format="$%.2f"),
                "fraud_rate": st.column_config.NumberColumn("Fraud rate", format="%.4f"),
                "risk_score_avg": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%.0f"),
            },
        )
        if ev.selection.rows:
            selected_name = top_m.iloc[ev.selection.rows[0]]["merchant"]
            if st.button(f"Open '{selected_name}' dashboard"):
                st.session_state["selected_merchant"] = selected_name
                st.session_state["page"] = "Overview"
                st.rerun()
