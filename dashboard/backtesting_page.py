"""
Page 6: Historical Strategy Backtesting Engine UI.
Allows users to test Strategies A, B, C, and D across historical NSE data with realistic brokerage/STT/slippage
and compare cumulative returns against the Nifty 50 benchmark.
"""
from datetime import timedelta
import streamlit as st
import plotly.graph_objects as go
from data.database import DatabaseManager
from analysis.backtesting import run_strategy_backtest
from utils.helpers import format_inr, format_pct, now_ist


def render_backtesting_page(db: DatabaseManager) -> None:
    st.title("⏳ Historical Strategy Backtesting & Validation")
    st.caption(
        "Simulates historical signals using strictly next-bar open execution (zero look-ahead bias) "
        "and deducts realistic NSE delivery transaction charges and slippage."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        strategy_choice = st.selectbox(
            "Select Screening Strategy to Validate",
            [
                "Strategy A: Momentum Breakout",
                "Strategy B: Trend-Following",
                "Strategy C: Pullback Entry",
                "Strategy D: Early Momentum",
            ],
        )
        init_cap = st.number_input("Initial Backtest Capital (₹)", min_value=10000.0, value=100000.0, step=25000.0)
    with c2:
        default_start = now_ist().date() - timedelta(days=365)
        default_end = now_ist().date()
        start_dt = st.date_input("Start Date", value=default_start)
        end_dt = st.date_input("End Date", value=default_end)
    with c3:
        tx_cost = st.number_input("Round-Trip Transaction Cost & Taxes (%)", min_value=0.0, max_value=2.0, value=0.18, step=0.02)
        slippage = st.number_input("Slippage Per Side (%)", min_value=0.0, max_value=1.0, value=0.10, step=0.05)
        max_hold = st.slider("Max Holding Period (Trading Days)", 3, 30, 15)

    if st.button("▶️ Run Historical Backtest Across NSE Universe", type="primary"):
        with st.spinner(f"Running event-driven backtest for {strategy_choice}..."):
            stocks = db.get_active_stocks()
            histories = {s["symbol"]: db.get_historical_prices(s["symbol"], limit_days=600) for s in stocks}
            bench_df = db.get_historical_prices("NIFTY_50", limit_days=600)

            res = run_strategy_backtest(
                stock_histories=histories,
                strategy_name=strategy_choice,
                start_date=start_dt.strftime("%Y-%m-%d"),
                end_date=end_dt.strftime("%Y-%m-%d"),
                initial_capital=init_cap,
                risk_per_trade_pct=1.0,
                transaction_cost_pct=tx_cost,
                slippage_pct=slippage,
                max_holding_days=max_hold,
                benchmark_df=bench_df,
            )

        if res["total_trades"] == 0:
            st.warning("No historical signals triggered for the selected strategy and date range.")
            return

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Total Return", format_pct(res["total_return_pct"]), f"Final: {format_inr(res['final_capital'])}")
        m2.metric("Nifty 50 Benchmark", format_pct(res["benchmark_return_pct"]), f"Alpha: {format_pct(res['total_return_pct'] - res['benchmark_return_pct'])}")
        m3.metric("Win Rate", f"{res['win_rate_pct']:.1f}%", f"{res['total_trades']} trades")
        m4.metric("Profit Factor", f"{res['profit_factor']:.2f}")
        m5.metric("Avg Win / Avg Loss", f"+{res['avg_win_pct']:.2f}% / {res['avg_loss_pct']:.2f}%")
        m6.metric("Max Drawdown", f"-{res['max_drawdown_pct']:.2f}%")

        eq_df = res["equity_curve_df"]
        if not eq_df.empty:
            fig_eq = go.Figure()
            fig_eq.add_trace(
                go.Scatter(x=eq_df["date"], y=eq_df["equity"], mode="lines+markers", name="Strategy Equity (₹)", line=dict(color="#10b981", width=2))
            )
            fig_eq.update_layout(title="Simulated Portfolio Equity Curve (₹)", height=380, template="plotly_dark")
            st.plotly_chart(fig_eq, use_container_width=True)

        st.subheader("📋 Historical Trade Log")
        st.dataframe(res["trades_df"], use_container_width=True, hide_index=True)
