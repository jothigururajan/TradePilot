"""
Page 1: Main Dashboard (NSE Market Overview, Nifty 50 & Nifty Bank Regime, Breadth & Top Setups).
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from data.database import DatabaseManager
from data.market_data import MarketDataService
from analysis.indicators import calculate_all_indicators
from utils.helpers import format_inr, format_pct, evaluate_data_freshness


def _get_index_summary(db: DatabaseManager, index_symbol: str, label: str) -> dict:
    df = db.get_historical_prices(index_symbol, limit_days=250)
    if df.empty:
        return {"label": label, "available": False}
    enriched = calculate_all_indicators(df)
    last = enriched.iloc[-1] if not enriched.empty else df.iloc[-1]
    close = float(last["close"])
    pct = float(last["daily_pct_change"]) if pd.notna(last.get("daily_pct_change")) else 0.0
    ema50 = last.get("ema_50")
    ema200 = last.get("ema_200")
    rsi = last.get("rsi_14")

    if pd.notna(ema50) and pd.notna(ema200):
        if close > ema50 and ema50 > ema200:
            trend = "BULLISH UPTREND"
        elif close < ema50 and close > ema200:
            trend = "PULLBACK / CONSOLIDATION"
        else:
            trend = "BEARISH / BELOW EMA200"
    else:
        trend = "NEUTRAL"

    return {
        "label": label,
        "available": True,
        "close": close,
        "pct": pct,
        "rsi": float(rsi) if pd.notna(rsi) else None,
        "trend": trend,
        "trade_date": str(last["trade_date"]),
        "df": df.tail(90),
    }


def render_overview_page(db: DatabaseManager, market_service: MarketDataService) -> None:
    st.title("📊 TradePilot NSE — Market Overview & Executive Summary")

    results_df = db.get_all_screening_results()
    active_stocks = db.get_active_stocks()

    if results_df.empty:
        st.info(
            "No screening results found in local SQLite database yet. Click **⚡ Smart Sync** or **🔁 Force Refresh** "
            "in the left sidebar to download NSE historical OHLCV data and run the screening engine."
        )
        return

    # Index summaries
    nifty = _get_index_summary(db, "NIFTY_50", "Nifty 50 (^NSEI)")
    banknifty = _get_index_summary(db, "NIFTY_BANK", "Nifty Bank (^NSEBANK)")

    col_idx1, col_idx2, col_regime = st.columns([1.2, 1.2, 1.6])
    with col_idx1:
        if nifty["available"]:
            st.metric(
                label=f"{nifty['label']} ({nifty['trade_date']})",
                value=f"{nifty['close']:,.2f}",
                delta=format_pct(nifty["pct"]),
            )
            st.caption(f"Regime: **{nifty['trend']}** | RSI(14): `{nifty['rsi']:.1f}`" if nifty["rsi"] else f"Regime: **{nifty['trend']}**")
        else:
            st.metric(label="Nifty 50 (^NSEI)", value="Not Synced", delta="Run Sync")

    with col_idx2:
        if banknifty["available"]:
            st.metric(
                label=f"{banknifty['label']} ({banknifty['trade_date']})",
                value=f"{banknifty['close']:,.2f}",
                delta=format_pct(banknifty["pct"]),
            )
            st.caption(
                f"Regime: **{banknifty['trend']}** | RSI(14): `{banknifty['rsi']:.1f}`"
                if banknifty["rsi"]
                else f"Regime: **{banknifty['trend']}**"
            )
        else:
            st.metric(label="Nifty Bank (^NSEBANK)", value="Not Synced", delta="Run Sync")

    # Universe Breadth Statistics
    total_scanned = len(results_df)
    bullish_count = int((results_df["signal"] == "BUY WATCH").sum())
    hold_count = int((results_df["signal"] == "HOLD WATCH").sum())
    bearish_count = int((results_df["signal"] == "AVOID").sum())
    breakout_count = int(results_df["matched_strategies"].str.contains("Momentum Breakout", na=False).sum())
    above_ema50_pct = (
        (results_df["close_price"] > results_df["ema_50"]).mean() * 100.0
        if "ema_50" in results_df.columns and total_scanned > 0
        else 0.0
    )

    with col_regime:
        market_mood = "BULLISH EXPANSION" if above_ema50_pct >= 60 else ("SELECTIVE / ROTATIONAL" if above_ema50_pct >= 40 else "DEFENSIVE / RISK-OFF")
        st.metric("NSE Universe Breadth (% > EMA 50)", f"{above_ema50_pct:.1f}%", delta=market_mood)
        latest_bar = results_df["trade_date"].max()
        fresh_status, _ = evaluate_data_freshness(latest_bar)
        st.caption(f"Last Bar: `{latest_bar}` ({fresh_status}) | Configured Universe: `{len(active_stocks)}` stocks")

    st.divider()

    # KPI Row
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Stocks Scanned", f"{total_scanned}")
    k2.metric("🟢 BUY WATCH (Bullish)", f"{bullish_count}")
    k3.metric("🚀 Breakout Setups", f"{breakout_count}")
    k4.metric("🟡 HOLD WATCH", f"{hold_count}")
    k5.metric("🔴 AVOID (Bearish/Weak)", f"{bearish_count}")

    # Charts Row: Top Ranked Bar Chart & Signal Distribution
    c_left, c_right = st.columns([1.6, 1.0])
    with c_left:
        st.subheader("🏆 Top 10 Highest-Scoring NSE Stocks Today")
        top10 = results_df.head(10).copy()
        colors = ["#10b981" if s == "BUY WATCH" else ("#f59e0b" if s == "HOLD WATCH" else "#ef4444") for s in top10["signal"]]
        fig_bar = go.Figure(
            go.Bar(
                x=top10["overall_score"],
                y=top10["symbol"],
                orientation="h",
                marker_color=colors,
                text=[f"{sc:.1f} pts ({sig})" for sc, sig in zip(top10["overall_score"], top10["signal"])],
                textposition="auto",
            )
        )
        fig_bar.update_layout(
            yaxis=dict(autorange="reversed"),
            xaxis_title="Overall Score (out of 100)",
            height=360,
            margin=dict(l=10, r=20, t=10, b=30),
            template="plotly_dark",
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with c_right:
        st.subheader("🧭 Signal Breakdown & Sector Leaders")
        fig_pie = go.Figure(
            go.Pie(
                labels=["BUY WATCH", "HOLD WATCH", "AVOID"],
                values=[bullish_count, hold_count, bearish_count],
                hole=0.55,
                marker=dict(colors=["#10b981", "#f59e0b", "#ef4444"]),
            )
        )
        fig_pie.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark")
        st.plotly_chart(fig_pie, use_container_width=True)

    # Actionable Summary Table
    st.subheader("⚡ Top Short-Term Actionable Setups (BUY WATCH)")
    buy_df = results_df[results_df["signal"] == "BUY WATCH"].head(8)
    if buy_df.empty:
        st.warning("No stocks currently meet strict BUY WATCH criteria. Check '2. Stock Screener' for HOLD WATCH candidates.")
    else:
        display_cols = pd.DataFrame(
            {
                "Symbol": buy_df["symbol"],
                "Company": buy_df["company_name"],
                "Sector": buy_df["sector"],
                "Close (₹)": buy_df["close_price"].map(lambda x: f"₹{x:,.2f}"),
                "1D Change": buy_df["daily_pct_change"].map(lambda x: format_pct(x)),
                "Score (100)": buy_df["overall_score"].map(lambda x: f"{x:.1f}"),
                "Strategy Match": buy_df["matched_strategies"],
                "Entry Zone": [f"₹{l:,.2f} – ₹{h:,.2f}" for l, h in zip(buy_df["entry_low"], buy_df["entry_high"])],
                "Stop-Loss": buy_df["stop_loss"].map(lambda x: f"₹{x:,.2f}"),
                "Target 2 (Primary)": buy_df["target_2"].map(lambda x: f"₹{x:,.2f}"),
                "R:R Ratio": buy_df["risk_reward_ratio"].map(lambda x: f"1 : {x:.2f}"),
            }
        )
        st.dataframe(display_cols, use_container_width=True, hide_index=True)

    with st.expander("📜 View Recent Data Update Logs"):
        logs_df = db.get_update_logs(limit=15)
        st.dataframe(logs_df, use_container_width=True, hide_index=True)
