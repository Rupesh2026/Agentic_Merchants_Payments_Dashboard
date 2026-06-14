"""
dashboard/components/kpi_cards.py — reusable KPI card + delta helpers.
"""

from __future__ import annotations

import streamlit as st


def kpi_card(label: str, value: str, delta: str = "", delta_type: str = "flat") -> None:
    """Render a single Stripe-style KPI card (HTML)."""
    css = {"up": "kpi-delta-up", "down": "kpi-delta-down"}.get(delta_type, "kpi-delta-flat")
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value">{value}</div>
          <div class="{css}">{delta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def pct_delta(curr: float, prior: float) -> tuple[str, str]:
    """Return ('↑ 4.2% vs prior', 'up') style delta text + direction."""
    if prior in (0, None):
        return "—", "flat"
    change = (curr - prior) / abs(prior) * 100
    arrow = "↑" if change >= 0 else "↓"
    return f"{arrow} {abs(change):.1f}% vs prior", ("up" if change >= 0 else "down")
