"""dashboard/app.py — Payments Dashboard."""

import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Streamlit Cloud stores secrets in st.secrets; bridge them into os.environ
# so config/settings.py (which uses os.getenv) picks them up automatically.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:
    pass

st.set_page_config(
    page_title="PayDash",
    page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>◈</text></svg>",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* ── App background ──────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"] { background: #f7f8fa; }

/* ── Sidebar — cream background matching Claude's palette ─────────────────── */
[data-testid="stSidebar"] {
    background: #f5f0e8 !important;
    border-right: 1px solid #e0d8cc !important;
}
[data-testid="stSidebarContent"] { padding: 20px 14px !important; }
/* Base text colour for everything in sidebar */
[data-testid="stSidebar"],
[data-testid="stSidebar"] * { color: #1a1a1a; }

/* ── Brand header ─────────────────────────────────────────────────────────── */
.sb-brand {
    font-size: 16px;
    font-weight: 700;
    color: #1a1a1a;
    letter-spacing: -0.03em;
    padding: 2px 4px 1px 4px;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 2px;
}
.sb-brand-accent {
    width: 7px; height: 7px;
    background: #4f46e5;
    border-radius: 2px;
    display: inline-block;
    flex-shrink: 0;
}
.sb-tagline {
    font-size: 10px;
    color: #8a7f76;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    padding: 0 4px 10px 4px;
}

/* ── Section labels ───────────────────────────────────────────────────────── */
.sb-section-label {
    font-size: 10px;
    font-weight: 600;
    color: #8a7f76;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 0 4px 5px 4px;
    margin-top: 10px;
}

/* ── Sidebar divider ─────────────────────────────────────────────────────── */
[data-testid="stSidebar"] hr {
    border: none !important;
    border-top: 1px solid #e0d8cc !important;
    margin: 10px 0 !important;
}

/* ── Selectbox — cream skin ───────────────────────────────────────────────── */
[data-testid="stSidebar"] .stSelectbox label {
    display: none !important;
}
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] {
    background-color: #ede7db !important;
    border: 1px solid #d0c8bc !important;
    border-radius: 7px !important;
}
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div {
    background-color: transparent !important;
    color: #1a1a1a !important;
    font-size: 13px !important;
}
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] * {
    color: #1a1a1a !important;
    background-color: transparent !important;
    font-size: 13px !important;
}
[data-testid="stSidebar"] .stSelectbox svg { opacity: 0.5; }
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"]:focus-within {
    border-color: #4f46e5 !important;
    box-shadow: 0 0 0 2px rgba(79,70,229,0.10) !important;
}

/* ── Dropdown popup (portal, outside sidebar) ────────────────────────────── */
[data-baseweb="popover"] {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    box-shadow: 0 8px 24px rgba(0,0,0,0.10) !important;
    overflow: hidden !important;
}
[data-baseweb="popover"] * {
    color: #1a202c !important;
    background: transparent !important;
    font-size: 13px !important;
}
[data-baseweb="popover"] li {
    padding: 8px 14px !important;
    border-bottom: 1px solid #f1f5f9 !important;
}
[data-baseweb="popover"] li:last-child { border-bottom: none !important; }
[data-baseweb="popover"] li:hover { background: #f8fafc !important; }
[data-baseweb="popover"] [aria-selected="true"] {
    background: #eef2ff !important;
    color: #4338ca !important;
    font-weight: 500 !important;
}
[data-baseweb="popover"] [aria-selected="true"] * { color: #4338ca !important; }

/* ── Nav radio — bordered items ──────────────────────────────────────────── */
[data-testid="stSidebar"] .stRadio { margin: 0 !important; }
[data-testid="stSidebar"] .stRadio > label { display: none !important; }
[data-testid="stSidebar"] .stRadio > div {
    gap: 4px !important;
    display: flex !important;
    flex-direction: column !important;
}
/* Hide the radio circle */
[data-testid="stSidebar"] .stRadio label > div:first-child {
    display: none !important;
}
/* Each nav item — bordered card */
[data-testid="stSidebar"] .stRadio label {
    display: flex !important;
    align-items: center !important;
    width: 100% !important;
    padding: 8px 12px !important;
    border-radius: 7px !important;
    border: 1px solid #d6cec4 !important;
    background: #ede7db !important;
    cursor: pointer !important;
    transition: background 0.1s, border-color 0.1s !important;
    margin: 0 !important;
}
[data-testid="stSidebar"] .stRadio label p,
[data-testid="stSidebar"] .stRadio label span {
    font-size: 13px !important;
    font-weight: 400 !important;
    color: #3d3530 !important;
    margin: 0 !important;
    line-height: 1.4 !important;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: #e4ddd3 !important;
    border-color: #b8b0a6 !important;
}
[data-testid="stSidebar"] .stRadio label:hover p,
[data-testid="stSidebar"] .stRadio label:hover span {
    color: #1a1a1a !important;
}
/* Active item */
[data-testid="stSidebar"] .stRadio label:has(input[type="radio"]:checked) {
    background: #e8e0f0 !important;
    border-color: #9b8ec4 !important;
}
[data-testid="stSidebar"] .stRadio label:has(input[type="radio"]:checked) p,
[data-testid="stSidebar"] .stRadio label:has(input[type="radio"]:checked) span {
    color: #3730a3 !important;
    font-weight: 600 !important;
}

/* ── Merchant context card ────────────────────────────────────────────────── */
.merchant-badge {
    background: #ede7db;
    border: 1px solid #d6cec4;
    border-radius: 8px;
    padding: 10px 12px;
    margin: 6px 0 4px;
}
.merchant-badge .mb-name { font-size: 12px; font-weight: 600; color: #1a1a1a; }
.merchant-badge .mb-meta { font-size: 11px; color: #5a5048; margin-top: 3px; line-height: 1.5; }

/* ── Watchlist pill ───────────────────────────────────────────────────────── */
.wl-badge {
    display: inline-flex; align-items: center; gap: 5px;
    background: #fff7ed; border: 1px solid #fed7aa;
    border-radius: 20px; padding: 3px 10px;
    font-size: 11px; color: #c2410c;
}

/* ── Sidebar buttons ─────────────────────────────────────────────────────── */
[data-testid="stSidebar"] .stButton button {
    background: #ede7db !important;
    border: 1px solid #d6cec4 !important;
    color: #3d3530 !important;
    border-radius: 7px !important;
    font-size: 12px !important;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: #e4ddd3 !important;
    border-color: #9b8ec4 !important;
    color: #1a1a1a !important;
}

/* ── Page headings (h2) ──────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"] h2 {
    font-size: 26px !important;
    font-weight: 700 !important;
    color: #0f172a !important;
    letter-spacing: -0.02em !important;
    margin-bottom: 4px !important;
}

/* ── General body text in main content ───────────────────────────────────── */
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] li,
[data-testid="stAppViewContainer"] span:not([class]) {
    color: #1e293b;
    font-size: 14px;
}

/* ── Main content KPI cards ──────────────────────────────────────────────── */
.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 12px;
    transition: box-shadow 0.15s ease, border-color 0.15s ease;
}
.kpi-card:hover { box-shadow: 0 4px 14px rgba(79,70,229,0.09); border-color: #a5b4fc; }
.kpi-label { font-size: 12px; color: #475569; text-transform: uppercase; letter-spacing: 0.07em; font-weight: 600; }
.kpi-value { font-size: 26px; font-weight: 700; color: #0f172a; margin: 6px 0 4px; letter-spacing: -0.02em; }
.kpi-delta-up   { font-size: 13px; color: #16a34a; }
.kpi-delta-down { font-size: 13px; color: #dc2626; }
.kpi-delta-flat { font-size: 13px; color: #64748b; }

/* ── Section headers ─────────────────────────────────────────────────────── */
.section-header {
    font-size: 12px; font-weight: 700; color: #334155;
    text-transform: uppercase; letter-spacing: 0.08em;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 7px; margin: 24px 0 5px;
}
/* ── Section description (one-liner below header) ────────────────────────── */
.section-desc {
    font-size: 13px; color: #475569; margin: 0 0 14px 0; line-height: 1.6;
}

/* ── Alert banners ───────────────────────────────────────────────────────── */
.alert-banner {
    background: #fef2f2; border: 1px solid #fecaca;
    border-radius: 8px; padding: 11px 16px; margin-bottom: 14px;
    font-size: 14px; color: #991b1b;
}
.alert-banner-warn {
    background: #fffbeb; border: 1px solid #fde68a;
    border-radius: 8px; padding: 11px 16px; margin-bottom: 14px;
    font-size: 14px; color: #92400e;
}
.alert-banner-ok {
    background: #f0fdf4; border: 1px solid #bbf7d0;
    border-radius: 8px; padding: 11px 16px; margin-bottom: 14px;
    font-size: 14px; color: #14532d;
}

/* ── Status pills ────────────────────────────────────────────────────────── */
.pill-approved { background:#f0fdf4; color:#15803d; padding:2px 8px; border-radius:20px; font-size:11px; font-weight:500; }
.pill-flagged  { background:#fef2f2; color:#b91c1c; padding:2px 8px; border-radius:20px; font-size:11px; font-weight:500; }
.pill-declined { background:#fffbeb; color:#b45309; padding:2px 8px; border-radius:20px; font-size:11px; font-weight:500; }

/* ── SHAP panel ──────────────────────────────────────────────────────────── */
.shap-panel { background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:16px; margin-top:12px; }
.shap-feature-positive { color: #991b1b; font-weight: 700; font-size: 14px; }
.shap-feature-negative { color: #14532d; font-weight: 700; font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div class="sb-brand"><span class="sb-brand-accent"></span>PayDash</div>'
        '<div class="sb-tagline">Merchant Intelligence</div>',
        unsafe_allow_html=True,
    )

    from dashboard import data

    # Merchant selector
    st.markdown('<div class="sb-section-label">Merchant</div>', unsafe_allow_html=True)
    ml = data.merchant_list()
    merchant_options = ["All Merchants"] + ml["merchant"].tolist()

    if "selected_merchant" not in st.session_state:
        st.session_state["selected_merchant"] = "All Merchants"

    current_merchant = st.session_state["selected_merchant"]
    current_idx = merchant_options.index(current_merchant) if current_merchant in merchant_options else 0

    selected_merchant = st.selectbox(
        "Merchant",
        merchant_options,
        index=current_idx,
        label_visibility="collapsed",
    )
    st.session_state["selected_merchant"] = selected_merchant

    # Merchant context
    if selected_merchant != "All Merchants" and not ml.empty:
        m_row = ml[ml["merchant"] == selected_merchant]
        if not m_row.empty:
            m = m_row.iloc[0]
            fraud_color = "color:#b91c1c" if m["fraud_rate"] > 0.0058 else "color:#15803d"
            st.markdown(
                f"""<div class="merchant-badge">
                  <div class="mb-name">{selected_merchant}</div>
                  <div class="mb-meta">
                    {m['category']}<br>
                    <span style="{fraud_color}">Fraud {m['fraud_rate']:.2%}</span>
                    &nbsp;·&nbsp; Risk {m['risk_score_avg']:.0f}/100
                  </div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # Navigation
    st.markdown('<div class="sb-section-label">Navigation</div>', unsafe_allow_html=True)

    _PAGES = ["Overview", "Transactions", "Performance", "Fraud & Risk", "Payouts", "AI Analyst"]
    if "page" not in st.session_state:
        st.session_state["page"] = "Overview"
    current_idx = _PAGES.index(st.session_state["page"]) if st.session_state["page"] in _PAGES else 0

    page = st.radio(
        "nav",
        _PAGES,
        index=current_idx,
        label_visibility="collapsed",
    )
    st.session_state["page"] = page

    st.markdown("---")

    # Period
    st.markdown('<div class="sb-section-label">Time Period</div>', unsafe_allow_html=True)
    _period_opts = ["Last 7 days", "Last 30 days", "Last 90 days", "All time"]
    _period_idx = _period_opts.index(st.session_state.get("period", "Last 30 days"))
    period = st.selectbox(
        "Period",
        _period_opts,
        index=_period_idx,
        label_visibility="collapsed",
    )
    st.session_state["period"] = period

    # Watchlist
    wl = st.session_state.get("watchlist", set())
    if wl:
        st.markdown(
            f'<div style="margin-top:8px"><span class="wl-badge">'
            f'Watching {len(wl)} merchant{"s" if len(wl) != 1 else ""}'
            f'</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div style="margin-top:14px;font-size:10px;color:#8a7f76;line-height:1.7">'
        'Sparkov dataset &nbsp;·&nbsp; 1.85M txns<br>Jan 2019 – Dec 2020</div>',
        unsafe_allow_html=True,
    )

# ── Route ──────────────────────────────────────────────────────────────────────
if page == "Overview":
    from dashboard.views import overview; overview.render()
elif page == "Transactions":
    from dashboard.views import transactions; transactions.render()
elif page == "Performance":
    from dashboard.views import performance; performance.render()
elif page == "Fraud & Risk":
    from dashboard.views import fraud; fraud.render()
elif page == "Payouts":
    from dashboard.views import payouts; payouts.render()
elif page == "AI Analyst":
    from dashboard.views import ai_analyst; ai_analyst.render()
