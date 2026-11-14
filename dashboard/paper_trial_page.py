"""
Page 8: 1-Month Paper Trial Journal & Automated Forward-Testing Analytics.
Tracks daily automated entries (top 1-3 BUY WATCH stocks by score) and exits (SL/Target/Time),
starting from ₹50,000 capital with optional top-ups and full P&L / Risk-Reward analytics.
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from data.database import DatabaseManager
from analysis.paper_trial import (
    get_paper_trial_analytics,
    run_daily_paper_trial_step,
    add_trial_capital,
    update_paper_trial_config,
    reset_paper_trial,
)
from utils.helpers import format_inr, format_pct


def render_paper_trial_page(db: DatabaseManager) -> None:
    st.title("🧪 1-Month Automated Paper Trial & Forward-Test Journal")
    st.caption(
        "Automatically enters the top 1–3 BUY WATCH stocks by score each trading day (0 entries when no BUY WATCH triggers), "
        "monitors Stop-Loss / Target 2 / Time exits daily, and tracks real P&L & Risk/Reward."
    )

    data = get_paper_trial_analytics(db)
    cfg = data["config"]

    # Top Action Bar
    a1, a2, a3, a4 = st.columns([1.4, 1.4, 1.2, 1.2])
    with a1:
        st.info(f"📅 **Trial Window:** `{cfg['start_date']}` to `{cfg['end_date']}`")
    with a2:
        if st.button("▶️ Run Today's Paper Trial Step Now", type="primary", use_container_width=True):
            res = run_daily_paper_trial_step(db)
            if res.get("skipped"):
                st.warning(res.get("reason"))
            else:
                st.success(
                    f"Completed for {res['run_date']}: {res['entries_taken']} entries, {res['exits_triggered']} exits. "
                    f"({res['summary_note']})"
                )
                st.rerun()
    with a3:
        with st.popover("💵 Add Capital (Top-Up)", use_container_width=True):
            topup = st.number_input("Add Capital Amount (₹)", min_value=1000.0, value=25000.0, step=5000.0)
            if st.button("Confirm Add Capital"):
                add_trial_capital(db, topup)
                st.success(f"Added ₹{topup:,.2f} to Paper Trial capital!")
                st.rerun()
    with a4:
        with st.popover("⚙️ Trial Rules & Reset", use_container_width=True):
            with st.form("trial_cfg_form"):
                new_start = st.date_input("Start Date", value=pd.to_datetime(cfg["start_date"]).date())
                new_end = st.date_input("End Date", value=pd.to_datetime(cfg["end_date"]).date())
                new_init_cap = st.number_input("Starting Capital (₹)", min_value=10000.0, value=float(cfg["initial_capital"]), step=5000.0)
                new_max_daily = st.slider("Max New Entries Per Day (1–3)", 1, 5, int(cfg["max_daily_entries"]))
                new_max_open = st.slider("Max Concurrent Open Positions", 1, 12, int(cfg["max_open_positions"]))
                new_risk_pct = st.number_input("Risk % Per Trade", 0.5, 5.0, float(cfg["risk_per_trade_pct"]), 0.25)
                new_hold = st.slider("Max Holding Days", 5, 30, int(cfg["max_holding_days"]))
                new_active = st.checkbox("Trial Active (Auto-run in EOD)", value=bool(cfg["is_active"]))
                if st.form_submit_button("💾 Save Trial Rules"):
                    update_paper_trial_config(
                        db,
                        new_start.strftime("%Y-%m-%d"),
                        new_end.strftime("%Y-%m-%d"),
                        new_init_cap,
                        new_max_daily,
                        new_max_open,
                        new_risk_pct,
                        new_hold,
                        new_active,
                    )
                    st.success("Paper Trial rules updated!")
                    st.rerun()
            st.divider()
            if st.button("🔄 Reset 1-Month Trial to ₹50,000", type="secondary"):
                reset_paper_trial(db, initial_capital=50000.0)
                st.warning("Paper Trial journal reset to ₹50,000!")
                st.rerun()

    st.divider()

    # KPI Row 1: Capital & P&L
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Funded Capital", format_inr(data["total_capital"]), f"Base ₹{data['initial_capital']:,.0f} + Added ₹{data['added_capital']:,.0f}")
    k2.metric("Current Trial Equity", format_inr(data["current_equity"]), format_pct(data["total_return_pct"]))
    k3.metric("Available Cash", format_inr(data["cash_available"]), f"Deployed: {format_inr(data['deployed_capital'])}")
    k4.metric("Realized Net P&L", format_inr(data["realized_pnl"]), f"Unrealized: {format_inr(data['unrealized_pnl'])}")
    k5.metric("Win Rate & Avg R:R", f"{data['win_rate_pct']:.1f}%", f"PF: {data['profit_factor']:.2f} | Avg {data['avg_realized_r']:+.2f}R")

    # Equity Curve Chart
    logs_df = data["logs_df"]
    if not logs_df.empty:
        plot_logs = logs_df.sort_values("run_date")
        fig_eq = go.Figure()
        fig_eq.add_trace(
            go.Scatter(
                x=plot_logs["run_date"],
                y=plot_logs["equity_inr"],
                mode="lines+markers",
                name="Paper Trial Equity (₹)",
                line=dict(color="#10b981", width=2.5),
            )
        )
        fig_eq.add_hline(y=data["total_capital"], line_dash="dot", line_color="#9ca3af", annotation_text="Funded Capital")
        fig_eq.update_layout(title="1-Month Paper Trial Equity Curve (₹)", height=320, template="plotly_dark", margin=dict(l=15, r=15, t=40, b=20))
        st.plotly_chart(fig_eq, use_container_width=True)

    # Tabs for Open Positions, Closed Trades, Daily Run Log
    tab_open, tab_closed, tab_logs = st.tabs(["📂 Open Trial Positions", "📜 Closed Trades & R:R Analysis", "🗓️ Daily Signal & Execution Log"])

    with tab_open:
        open_df = data["open_df"]
        if open_df.empty:
            st.info("No open paper trial positions right now.")
        else:
            st.dataframe(open_df, use_container_width=True, hide_index=True)

    with tab_closed:
        closed_df = data["closed_df"]
        if closed_df.empty:
            st.info("No closed paper trial trades yet. Trades close automatically when Stop-Loss, Target 2, or Max Holding Days is reached.")
        else:
            st.dataframe(closed_df, use_container_width=True, hide_index=True)
            csv_bytes = closed_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Export Closed Trial Trades (CSV)",
                data=csv_bytes,
                file_name="tradepilot_paper_trial_trades.csv",
                mime="text/csv",
            )

    with tab_logs:
        if logs_df.empty:
            st.info("No daily trial logs yet. Click **Run Today's Paper Trial Step Now** or let the 16:15 IST scheduler run.")
        else:
            st.dataframe(logs_df, use_container_width=True, hide_index=True)
