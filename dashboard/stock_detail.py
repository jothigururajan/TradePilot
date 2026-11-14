"""
Page 3: Stock Detail Analysis & Position-Sizing Calculator.
Displays multi-panel interactive Candlestick + EMA + Bollinger + Support/Resistance + Volume + RSI + MACD chart,
transparent 100-point score breakdown, fundamental metrics, entry/SL/targets, and interactive Risk Calculator.
"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from data.database import DatabaseManager
from analysis.indicators import calculate_all_indicators
from analysis.risk_management import calculate_position_size
from utils.helpers import format_inr, format_pct


def render_stock_detail_page(db: DatabaseManager) -> None:
    st.title("🔬 Stock Detail & Technical / Fundamental Deep-Dive")

    results_df = db.get_all_screening_results()
    if results_df.empty:
        st.warning("No stock data available. Run **⚡ Smart Sync** from the sidebar.")
        return

    symbols = results_df["symbol"].tolist()
    col_sel1, col_sel2 = st.columns([2, 1])
    with col_sel1:
        selected_sym = st.selectbox(
            "Select NSE Stock",
            options=symbols,
            format_func=lambda s: f"{s} — {results_df.loc[results_df['symbol'] == s, 'company_name'].values[0]} "
            f"(Score: {results_df.loc[results_df['symbol'] == s, 'overall_score'].values[0]:.1f} | "
            f"{results_df.loc[results_df['symbol'] == s, 'signal'].values[0]})",
        )
    with col_sel2:
        lookback_bars = st.selectbox("Chart Lookback Window", [90, 150, 250, 400], index=1)

    row = results_df[results_df["symbol"] == selected_sym].iloc[0]
    hist_df = db.get_historical_prices(selected_sym, limit_days=400)
    enriched_df = calculate_all_indicators(hist_df)
    plot_df = enriched_df.tail(lookback_bars)

    # Top Summary Metrics
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Last Close", format_inr(row["close_price"]), format_pct(row["daily_pct_change"]))
    m2.metric("Overall Score", f"{row['overall_score']:.1f} / 100", f"Coverage: {row['data_coverage_pct']:.0f}%")
    m3.metric("Trading Signal", row["signal"], row["opportunity_category"])
    m4.metric("Stop-Loss (ATR/Sup)", format_inr(row["stop_loss"]), f"-{row['downside_pct']:.2f}% risk")
    m5.metric("Primary Target (T2)", format_inr(row["target_2"]), f"+{row['upside_pct']:.2f}% upside")
    m6.metric("Risk / Reward", f"1 : {row['risk_reward_ratio']:.2f}", f"Risk/sh: ₹{row['risk_per_share']:.2f}")

    # Quick Add to Watchlist button
    if st.button(f"⭐ Add {selected_sym} to Watchlist with Calculated Levels"):
        db.add_to_watchlist(
            symbol=selected_sym,
            target_entry=float(row["close_price"]),
            planned_stop_loss=float(row["stop_loss"]),
            planned_target=float(row["target_2"]),
            strategy_tag=str(row["matched_strategies"]),
            notes=str(row["score_reasons"]),
        )
        st.success(f"Added {selected_sym} to Watchlist!")

    # Interactive Multi-Panel Plotly Chart (Candlestick + EMA 20/50/200 + S/R + Volume + RSI + MACD)
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.50, 0.15, 0.17, 0.18],
        subplot_titles=(
            f"{selected_sym} Daily Price, EMA (20/50/200), Support/Resistance & Trade Levels",
            "Volume & 20D SMA",
            "RSI (14)",
            "MACD (12, 26, 9)",
        ),
    )

    # 1. Candlesticks & EMAs
    fig.add_trace(
        go.Candlestick(
            x=plot_df["trade_date"],
            open=plot_df["open"],
            high=plot_df["high"],
            low=plot_df["low"],
            close=plot_df["close"],
            name="OHLC",
        ),
        row=1,
        col=1,
    )
    for ema_col, label, color in [
        ("ema_20", "EMA 20", "#38bdf8"),
        ("ema_50", "EMA 50", "#f59e0b"),
        ("ema_200", "EMA 200", "#a855f7"),
    ]:
        if ema_col in plot_df.columns:
            fig.add_trace(
                go.Scatter(x=plot_df["trade_date"], y=plot_df[ema_col], name=label, line=dict(color=color, width=1.5)),
                row=1,
                col=1,
            )

    # Horizontal lines for Stop-Loss and Target 2
    fig.add_hline(y=float(row["stop_loss"]), line_dash="dash", line_color="#ef4444", annotation_text="Stop-Loss", row=1, col=1)
    fig.add_hline(y=float(row["target_2"]), line_dash="dash", line_color="#10b981", annotation_text="Target 2", row=1, col=1)

    # 2. Volume
    vol_colors = ["#10b981" if c >= o else "#ef4444" for c, o in zip(plot_df["close"], plot_df["open"])]
    fig.add_trace(
        go.Bar(x=plot_df["trade_date"], y=plot_df["volume"], name="Volume", marker_color=vol_colors),
        row=2,
        col=1,
    )
    if "vol_sma_20" in plot_df.columns:
        fig.add_trace(
            go.Scatter(x=plot_df["trade_date"], y=plot_df["vol_sma_20"], name="Vol SMA 20", line=dict(color="#facc15", width=1.2)),
            row=2,
            col=1,
        )

    # 3. RSI 14
    fig.add_trace(
        go.Scatter(x=plot_df["trade_date"], y=plot_df["rsi_14"], name="RSI 14", line=dict(color="#38bdf8", width=1.6)),
        row=3,
        col=1,
    )
    fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#10b981", row=3, col=1)

    # 4. MACD
    macd_cols = ["#10b981" if h >= 0 else "#ef4444" for h in plot_df["macd_hist"].fillna(0)]
    fig.add_trace(
        go.Bar(x=plot_df["trade_date"], y=plot_df["macd_hist"], name="MACD Hist", marker_color=macd_cols),
        row=4,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=plot_df["trade_date"], y=plot_df["macd"], name="MACD", line=dict(color="#38bdf8", width=1.3)),
        row=4,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=plot_df["trade_date"], y=plot_df["macd_signal"], name="Signal", line=dict(color="#f97316", width=1.3)),
        row=4,
        col=1,
    )

    fig.update_layout(height=820, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=15, r=15, t=35, b=15))
    st.plotly_chart(fig, use_container_width=True)

    # Detailed Breakdown Columns
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🎯 Entry, Stop-Loss & Targets Breakdown")
        st.markdown(
            f"""
            - **Suggested Entry Zone:** `₹{row['entry_low']:,.2f} – ₹{row['entry_high']:,.2f}`
            - **Technical Stop-Loss:** `₹{row['stop_loss']:,.2f}` (`-{row['downside_pct']:.2f}%` | Risk/Share: `₹{row['risk_per_share']:.2f}`)
            - **Target 1 (Conservative 1.5R):** `₹{row['target_1']:,.2f}`
            - **Target 2 (Primary 2.5R):** `₹{row['target_2']:,.2f}` (`+{row['upside_pct']:.2f}%` | Reward/Share: `₹{row['reward_per_share_t2']:.2f}`)
            - **Target 3 (Swing Extension 3.5R):** `₹{row['target_3']:,.2f}`
            - **20-Day Support / Resistance:** Support `₹{row['support_20d'] or 0:,.2f}` | Resistance `₹{row['resistance_20d'] or 0:,.2f}`
            """
        )
        st.info(f"**Methodology:** {row['price_methodology']}")

    with c2:
        st.subheader("🧮 100-Point Scoring Model Breakdown")
        score_df = pd.DataFrame(
            {
                "Category": [
                    "Trend Strength (Max 20)",
                    "Momentum (Max 20)",
                    "Volume Confirmation (Max 15)",
                    "Breakout Potential (Max 15)",
                    "Fundamental Strength (Max 15)",
                    "Risk/Reward Suitability (Max 15)",
                ],
                "Points Earned": [
                    row["trend_score"],
                    row["momentum_score"],
                    row["volume_score"],
                    row["breakout_score"],
                    row["fundamental_score"],
                    row["risk_reward_score"],
                ],
            }
        )
        st.dataframe(score_df, use_container_width=True, hide_index=True)
        st.markdown(f"**Matched Screening Strategies:** `{row['matched_strategies']}`")
        st.markdown(f"**Key Score Drivers:** {row['score_reasons']}")
        if row["missing_data_warnings"] != "Complete":
            st.caption(f"⚠️ **Data Coverage Note:** {row['missing_data_warnings']}")

    st.divider()

    # Fundamental Metrics Section
    st.subheader("🏛️ Fundamental Analysis & Financial Health")
    fund_data = db.get_fundamental_data(selected_sym)
    if not fund_data or fund_data.get("metrics_available_count", 0) == 0:
        st.info(
            "Detailed fundamental metrics are currently unavailable from the free Yahoo Finance feed for this ticker. "
            "The stock is NOT rejected; its overall score is normalized across technical and risk/reward categories."
        )
    else:
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        f_col1.metric("Fundamental Classification", fund_data.get("fundamental_class", "N/A"))
        f_col2.metric("ROE / ROCE Proxy", f"{fund_data.get('roe_pct') or 0:.1f}%", f"ROA/ROCE: {fund_data.get('roce_pct') or 0:.1f}%")
        f_col3.metric("P/E & P/B Ratio", f"P/E: {fund_data.get('pe_ratio') or 0:.1f}x", f"P/B: {fund_data.get('pb_ratio') or 0:.2f}x")
        f_col4.metric("Debt-to-Equity", f"{fund_data.get('debt_to_equity') or 0:.2f}x", f"Rev Growth: {fund_data.get('revenue_growth_pct') or 0:.1f}%")
        st.caption(f"**Fundamental Notes:** {fund_data.get('notes', '')}")

    st.divider()

    # Interactive Position-Sizing Calculator (Section 9)
    st.subheader("🛡️ Position-Sizing & Risk Management Calculator")
    st.caption("Enter your own trading capital and risk tolerance below to compute exact share quantity.")
    rc1, rc2, rc3, rc4 = st.columns(4)
    with rc1:
        user_capital = st.number_input("Total Trading Capital (₹)", min_value=1000.0, value=100000.0, step=10000.0)
    with rc2:
        user_risk_pct = st.number_input("Risk % Per Trade", min_value=0.1, max_value=10.0, value=1.0, step=0.25)
    with rc3:
        calc_entry = st.number_input("Planned Entry Price (₹)", min_value=1.0, value=float(row["close_price"]), step=1.0)
    with rc4:
        calc_sl = st.number_input("Planned Stop-Loss Price (₹)", min_value=0.5, value=float(row["stop_loss"]), step=1.0)

    open_pos_df = db.get_open_positions()
    pos_res = calculate_position_size(
        total_capital=user_capital,
        risk_pct_per_trade=user_risk_pct,
        entry_price=calc_entry,
        stop_loss_price=calc_sl,
        target_price=float(row["target_2"]),
        current_open_positions=len(open_pos_df),
    )

    if "error" in pos_res:
        st.error(pos_res["error"])
    else:
        p1, p2, p3, p4, p5 = st.columns(5)
        p1.metric("Max Acceptable Loss", format_inr(pos_res["max_acceptable_loss"]))
        p2.metric("Quantity to Buy", f"{pos_res['quantity']} shares")
        p3.metric("Total Investment", format_inr(pos_res["total_investment"]), f"{pos_res['capital_allocation_pct']:.1f}% of capital")
        p4.metric("Potential Loss (at SL)", format_inr(pos_res["potential_loss"]))
        p5.metric("Potential Profit (at T2)", format_inr(pos_res["potential_profit"]), f"R:R 1:{pos_res['risk_reward_ratio']:.2f}")

        for w_msg in pos_res["warnings"]:
            st.warning(w_msg)
