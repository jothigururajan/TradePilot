"""
Main Streamlit Entry Point for TradePilot NSE.
Run locally via:
    streamlit run app.py
Accessible at:
    http://localhost:8501
"""
import streamlit as st
from config import DISCLAIMER_TEXT
from data.database import DatabaseManager
from data.market_data import MarketDataService
from analysis.pipeline import run_full_screening_pipeline
from utils.helpers import evaluate_data_freshness

from dashboard.overview import render_overview_page
from dashboard.screener import render_screener_page
from dashboard.stock_detail import render_stock_detail_page
from dashboard.opportunities import render_opportunities_page
from dashboard.portfolio import render_portfolio_page
from dashboard.backtesting_page import render_backtesting_page
from dashboard.settings_page import render_settings_page
from dashboard.paper_trial_page import render_paper_trial_page

st.set_page_config(
    page_title="TradePilot NSE | Short-Term Equity Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_db() -> DatabaseManager:
    return DatabaseManager()


def apply_custom_css(theme_mode: str = "Dark") -> None:
    if theme_mode == "Dark":
        bg_card = "#111827"
        border_col = "#1f2937"
        text_col = "#f3f4f6"
    else:
        bg_card = "#ffffff"
        border_col = "#e5e7eb"
        text_col = "#111827"

    st.markdown(
        f"""
        <style>
        .tp-card {{
            background-color: {bg_card};
            border: 1px solid {border_col};
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 12px;
            color: {text_col};
        }}
        .badge-buy {{
            background-color: rgba(16, 185, 129, 0.18);
            color: #10b981;
            border: 1px solid #10b981;
            padding: 3px 10px;
            border-radius: 999px;
            font-weight: 700;
            font-size: 0.8rem;
        }}
        .badge-hold {{
            background-color: rgba(245, 158, 11, 0.18);
            color: #f59e0b;
            border: 1px solid #f59e0b;
            padding: 3px 10px;
            border-radius: 999px;
            font-weight: 700;
            font-size: 0.8rem;
        }}
        .badge-avoid {{
            background-color: rgba(239, 68, 68, 0.18);
            color: #ef4444;
            border: 1px solid #ef4444;
            padding: 3px 10px;
            border-radius: 999px;
            font-weight: 700;
            font-size: 0.8rem;
        }}
        .disclaimer-box {{
            font-size: 0.78rem;
            opacity: 0.85;
            border-left: 3px solid #f59e0b;
            padding-left: 10px;
            margin-top: 16px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    db = get_db()
    market_service = MarketDataService(db)

    with st.sidebar:
        st.markdown("## 📈 TradePilot NSE")
        st.caption("Systematic Short-Term NSE Stock Screening & Risk Engine")

        theme_choice = st.radio("UI Theme Accent", ["Dark", "Light"], horizontal=True, index=0)
        apply_custom_css(theme_choice)

        page = st.radio(
            "Navigation",
            [
                "1. Main Dashboard",
                "2. Stock Screener",
                "3. Stock Detail Analysis",
                "4. Trading Opportunities",
                "5. Portfolio & Watchlist",
                "6. Strategy Backtesting",
                "7. Custom Settings & Universe",
                "8. 1-Month Paper Trial Journal",
            ],
        )

        st.divider()
        st.subheader("🔄 Market Data Controls")

        last_log = db.get_last_update_log()
        latest_dt = db.get_latest_trade_date("RELIANCE")
        fresh_label, fresh_color = evaluate_data_freshness(latest_dt)
        st.markdown(f"**Data Status:** :{fresh_color}[**{fresh_label}**]")
        if latest_dt:
            st.caption(f"Latest NSE Bar Date: `{latest_dt}`")
        if last_log:
            st.caption(f"Last Sync: `{last_log['completed_at'][:19].replace('T', ' ')}`")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("⚡ Smart Sync", use_container_width=True, help="Fetches EOD updates only if newer bars exist"):
                prog = st.progress(0, text="Checking NSE EOD data...")
                res = market_service.refresh_stock_universe(
                    force=False,
                    fetch_fundamentals=True,
                    progress_callback=lambda cur, tot, sym: prog.progress(cur / tot, text=f"Syncing {sym} ({cur}/{tot})"),
                )
                prog.progress(1.0, text="Running indicator & scoring engine...")
                run_full_screening_pipeline(db)
                prog.empty()
                st.success(f"Sync complete! {res['details']}")
                st.rerun()

        with col_btn2:
            if st.button("🔁 Force Refresh", use_container_width=True, help="Forces full re-download & re-scoring"):
                prog = st.progress(0, text="Forcing full NSE download...")
                res = market_service.refresh_stock_universe(
                    force=True,
                    fetch_fundamentals=True,
                    progress_callback=lambda cur, tot, sym: prog.progress(cur / tot, text=f"Downloading {sym} ({cur}/{tot})"),
                )
                prog.progress(1.0, text="Recomputing indicators & rankings...")
                run_full_screening_pipeline(db)
                prog.empty()
                st.success(f"Full refresh complete! {res['details']}")
                st.rerun()

        if st.button("🧮 Re-Score Universe Only", use_container_width=True, help="Recalculates indicators and scores from local SQLite DB"):
            with st.spinner("Recalculating technicals, strategies, and 100-pt scores..."):
                stats = run_full_screening_pipeline(db)
            st.success(f"Scored {stats['processed']} NSE stocks.")
            st.rerun()

        st.markdown(f'<div class="disclaimer-box">{DISCLAIMER_TEXT}</div>', unsafe_allow_html=True)

    # Route to selected page
    if page.startswith("1."):
        render_overview_page(db, market_service)
    elif page.startswith("2."):
        render_screener_page(db)
    elif page.startswith("3."):
        render_stock_detail_page(db)
    elif page.startswith("4."):
        render_opportunities_page(db)
    elif page.startswith("5."):
        render_portfolio_page(db)
    elif page.startswith("6."):
        render_backtesting_page(db)
    elif page.startswith("7."):
        render_settings_page(db)
    elif page.startswith("8."):
        render_paper_trial_page(db)


if __name__ == "__main__":
    main()
