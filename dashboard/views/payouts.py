"""dashboard/views/payouts.py — Payout schedule + fee breakdown + CSV export."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard import data
from dashboard.components import charts


def render():
    merchant = st.session_state.get("selected_merchant", "All Merchants")
    st.markdown("## Payouts & Fees")
    st.markdown(
        '<p class="section-desc" style="margin-top:2px">Track every payout you\'ve received and understand exactly where your fees go — '
        'see your net earnings history, the breakdown of card network charges, and an estimate of your next payout.</p>',
        unsafe_allow_html=True,
    )

    if not data.has_data():
        st.warning("No data yet. Run `python run_pipeline.py` first.")
        return

    # ── Branch: merchant vs portfolio ────────────────────────────────────────
    if merchant != "All Merchants":
        _render_merchant(merchant)
    else:
        _render_portfolio()


def _render_merchant(merchant: str):
    payouts = data.merchant_payout_weekly(merchant)

    st.markdown(
        f'<div class="alert-banner-ok">Showing payout data for <strong>{merchant}</strong> (approved transactions only)</div>',
        unsafe_allow_html=True,
    )

    if payouts.empty:
        st.info(f"No approved transactions found for {merchant}.")
        return

    gross = payouts["gross_amount"].sum()
    interchange = payouts["interchange_fee"].sum()
    processing = payouts["processing_fee"].sum()
    network = payouts["network_fee"].sum()
    scheme = payouts["scheme_fee"].sum()
    total_fees = interchange + processing + network + scheme
    net = payouts["net_payout"].sum()
    eff_rate = total_fees / max(gross, 1)
    avg_weekly_net = payouts["net_payout"].tail(8).mean()

    last_payout = payouts.sort_values("payout_date").iloc[-1]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Gross Settled", f"${gross:,.0f}")
    c2.metric("Total Fees", f"${total_fees:,.0f}")
    c3.metric("Net Payout", f"${net:,.0f}")
    c4.metric("Effective Fee Rate", f"{eff_rate:.2%}")
    c5.metric("Avg Weekly Net", f"${avg_weekly_net:,.0f}", "Last 8 weeks")

    st.markdown(
        f'<div class="alert-banner-ok">'
        f'Last payout: <strong>${last_payout["net_payout"]:,.0f}</strong> '
        f'on {last_payout["payout_date"]} &nbsp;·&nbsp; '
        f'Next estimated: ~<strong>${avg_weekly_net:,.0f}</strong>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.download_button(
        "⬇ Export Payout CSV",
        payouts.to_csv(index=False),
        file_name=f"payout_{merchant.replace(' ', '_')}.csv",
        mime="text/csv",
    )

    st.markdown('<div class="section-header">Payouts over time</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-desc">Your weekly net payout history — '
        'the bar height shows what landed in your account each week after all fees were deducted.</p>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(charts.payout_bar(payouts), use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.markdown('<div class="section-header">Fee mix</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="section-desc">Where your processing costs go — '
            'Interchange (paid to the card-issuing bank) is typically the largest slice.</p>',
            unsafe_allow_html=True,
        )
        labels = ["Interchange", "Processing", "Network", "Scheme"]
        values = [interchange, processing, network, scheme]
        st.plotly_chart(
            charts.donut(labels, values, colors=["#9b8cff", "#c4b5fd", "#ba7517", "#e2c7a0"]),
            use_container_width=True,
        )
    with right:
        st.markdown('<div class="section-header">Fees by card network</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="section-desc">Which card types cost you the most in fees — '
            'Amex and premium cards typically carry higher rates.</p>',
            unsafe_allow_html=True,
        )
        fees = data.merchant_fee_by_network(merchant)
        if not fees.empty:
            st.plotly_chart(charts.vbar(fees, "card_network", "fees"), use_container_width=True)

    st.markdown('<div class="section-header">Payout detail</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-desc">Week-by-week payout record — '
        'each row shows your gross collections, every fee category deducted, and the final net amount deposited; download as CSV for your accounting records.</p>',
        unsafe_allow_html=True,
    )
    st.dataframe(
        payouts[["payout_date", "gross_amount", "interchange_fee", "processing_fee",
                 "network_fee", "scheme_fee", "net_payout", "transaction_count"]],
        use_container_width=True, hide_index=True,
        column_config={
            "gross_amount": st.column_config.NumberColumn("Gross", format="$%.0f"),
            "interchange_fee": st.column_config.NumberColumn("Interchange", format="$%.0f"),
            "processing_fee": st.column_config.NumberColumn("Processing", format="$%.0f"),
            "network_fee": st.column_config.NumberColumn("Network", format="$%.0f"),
            "scheme_fee": st.column_config.NumberColumn("Scheme", format="$%.0f"),
            "net_payout": st.column_config.NumberColumn("Net Payout", format="$%.0f"),
            "transaction_count": st.column_config.NumberColumn("Txns", format="%d"),
        },
    )

    if st.button("Ask AI for payout analysis"):
        st.session_state["page"] = "AI Analyst"
        st.session_state["ai_prefill"] = (
            f"Give me a payout summary for merchant '{merchant}' — "
            f"gross ${gross:,.0f}, fees ${total_fees:,.0f}, net ${net:,.0f}, "
            f"effective rate {eff_rate:.2%}. Any observations?"
        )
        st.rerun()


def _render_portfolio():
    payouts = data.payout_history()
    if payouts.empty:
        st.info("No payout history yet — run the ETL aggregations.")
        return

    gross = payouts["gross_amount"].sum()
    total_fees = payouts[["interchange_fee", "processing_fee", "network_fee", "scheme_fee"]].sum().sum()
    net = payouts["net_payout"].sum()
    eff_rate = total_fees / max(gross, 1)
    last_payout = payouts.sort_values("payout_date").iloc[-1]
    avg_weekly_net = payouts["net_payout"].tail(8).mean()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Gross Settled", f"${gross:,.0f}")
    c2.metric("Total Fees", f"${total_fees:,.0f}")
    c3.metric("Net Payout", f"${net:,.0f}")
    c4.metric("Effective Fee Rate", f"{eff_rate:.2%}")
    c5.metric("Avg Weekly Net", f"${avg_weekly_net:,.0f}", "Last 8 weeks")

    st.markdown(
        f'<div class="alert-banner-ok">'
        f'Last payout: <strong>${last_payout["net_payout"]:,.0f}</strong> '
        f'on {last_payout["payout_date"]} &nbsp;·&nbsp; '
        f'Next estimated: ~<strong>${avg_weekly_net:,.0f}</strong>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.download_button(
        "⬇ Export Payout CSV",
        payouts.to_csv(index=False),
        file_name="payout_history.csv",
        mime="text/csv",
    )

    st.markdown('<div class="section-header">Payouts over time</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-desc">Your weekly net payout history — '
        'the bar height shows what landed in your account each week after all fees were deducted; dips may correspond to high-chargeback periods.</p>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(charts.payout_bar(payouts), use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.markdown('<div class="section-header">Fee mix</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="section-desc">Where your processing costs go — '
            'Interchange (paid to the card-issuing bank) is typically the largest slice; understanding this helps you evaluate card acceptance costs.</p>',
            unsafe_allow_html=True,
        )
        labels = ["Interchange", "Processing", "Network", "Scheme"]
        values = [payouts["interchange_fee"].sum(), payouts["processing_fee"].sum(),
                  payouts["network_fee"].sum(), payouts["scheme_fee"].sum()]
        st.plotly_chart(
            charts.donut(labels, values, colors=["#9b8cff", "#c4b5fd", "#ba7517", "#e2c7a0"]),
            use_container_width=True,
        )
    with right:
        st.markdown('<div class="section-header">Fees by card network</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="section-desc">Which card types cost you the most in fees — '
            'Amex and premium cards typically carry higher rates; this shows whether your customer card mix is driving up your overall fee burden.</p>',
            unsafe_allow_html=True,
        )
        fees = data.fee_by_network()
        if not fees.empty:
            st.plotly_chart(charts.vbar(fees, "card_network", "fees"), use_container_width=True)

    st.markdown('<div class="section-header">Payout detail</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-desc">Week-by-week payout record — '
        'each row shows your gross collections, every fee category deducted, and the final net amount deposited; download as CSV for your accounting records.</p>',
        unsafe_allow_html=True,
    )
    st.dataframe(
        payouts[["payout_date", "gross_amount", "interchange_fee", "processing_fee",
                 "network_fee", "scheme_fee", "net_payout", "transaction_count"]],
        use_container_width=True, hide_index=True,
        column_config={
            "gross_amount": st.column_config.NumberColumn("Gross", format="$%.0f"),
            "interchange_fee": st.column_config.NumberColumn("Interchange", format="$%.0f"),
            "processing_fee": st.column_config.NumberColumn("Processing", format="$%.0f"),
            "network_fee": st.column_config.NumberColumn("Network", format="$%.0f"),
            "scheme_fee": st.column_config.NumberColumn("Scheme", format="$%.0f"),
            "net_payout": st.column_config.NumberColumn("Net Payout", format="$%.0f"),
            "transaction_count": st.column_config.NumberColumn("Txns", format="%d"),
        },
    )

    if st.button("Ask AI for payout analysis"):
        st.session_state["page"] = "AI Analyst"
        st.session_state["ai_prefill"] = "Give me a payout summary for the last 4 weeks including fee breakdown."
        st.rerun()
