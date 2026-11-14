"""
Page 2: Interactive Stock Screener with Multi-Factor Filtering, Sorting, Search & CSV/Excel Export.
"""
import io
import streamlit as st
import pandas as pd
from data.database import DatabaseManager


def render_screener_page(db: DatabaseManager) -> None:
    st.title("🔍 Interactive NSE Stock Screener")

    df = db.get_all_screening_results()
    if df.empty:
        st.warning("No screening data available. Please click **⚡ Smart Sync** in the sidebar first.")
        return

    # Filter Controls
    with st.expander("⚙️ Screener Filters & Search Criteria", expanded=True):
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            search_query = st.text_input("Search Symbol or Company", "")
            signal_filter = st.multiselect(
                "Trading Signal",
                options=["BUY WATCH", "HOLD WATCH", "AVOID"],
                default=["BUY WATCH", "HOLD WATCH"],
            )
        with f2:
            min_score = st.slider("Minimum Overall Score", 0.0, 95.0, float(db.get_setting("min_overall_score", 50.0)), 2.5)
            min_rr = st.slider("Minimum Risk/Reward (R:R)", 1.0, 4.0, float(db.get_setting("min_risk_reward", 1.8)), 0.1)
        with f3:
            rsi_range = st.slider(
                "RSI (14) Range",
                0.0,
                100.0,
                (float(db.get_setting("rsi_min", 35.0)), float(db.get_setting("rsi_max", 78.0))),
                1.0,
            )
            min_adx = st.slider("Minimum ADX (14)", 0.0, 50.0, float(db.get_setting("adx_min", 15.0)), 1.0)
        with f4:
            all_sectors = sorted(df["sector"].dropna().unique().tolist())
            sector_filter = st.multiselect("NSE Sector", options=all_sectors, default=all_sectors)
            min_rvol = st.number_input("Min Relative Volume (x)", 0.0, 5.0, 0.5, 0.1)

    filtered = df.copy()
    if search_query.strip():
        q = search_query.strip().upper()
        filtered = filtered[
            filtered["symbol"].str.upper().str.contains(q, na=False)
            | filtered["company_name"].str.upper().str.contains(q, na=False)
        ]
    if signal_filter:
        filtered = filtered[filtered["signal"].isin(signal_filter)]
    if sector_filter:
        filtered = filtered[filtered["sector"].isin(sector_filter)]

    filtered = filtered[filtered["overall_score"] >= min_score]
    filtered = filtered[filtered["risk_reward_ratio"] >= min_rr]
    filtered = filtered[
        (filtered["rsi_14"].isna()) | ((filtered["rsi_14"] >= rsi_range[0]) & (filtered["rsi_14"] <= rsi_range[1]))
    ]
    filtered = filtered[(filtered["adx_14"].isna()) | (filtered["adx_14"] >= min_adx)]
    filtered = filtered[(filtered["relative_volume"].isna()) | (filtered["relative_volume"] >= min_rvol)]

    st.markdown(f"**Showing `{len(filtered)}` of `{len(df)}` NSE stocks matching criteria**")

    # Prepare display DataFrame with required columns
    filtered["tech_score_85"] = (
        filtered["trend_score"]
        + filtered["momentum_score"]
        + filtered["volume_score"]
        + filtered["breakout_score"]
        + filtered["risk_reward_score"]
    ).round(1)

    filtered["macd_status"] = filtered.apply(
        lambda r: "Bullish (+Hist)"
        if pd.notna(r.get("macd_hist")) and r["macd_hist"] > 0
        else ("Bearish (-Hist)" if pd.notna(r.get("macd_hist")) else "N/A"),
        axis=1,
    )

    table_df = pd.DataFrame(
        {
            "Symbol": filtered["symbol"],
            "Company Name": filtered["company_name"],
            "Sector": filtered["sector"],
            "Close (₹)": filtered["close_price"].round(2),
            "Daily %": filtered["daily_pct_change"].round(2),
            "RSI (14)": filtered["rsi_14"].round(1),
            "ADX (14)": filtered["adx_14"].round(1),
            "MACD Status": filtered["macd_status"],
            "Rel Vol (x)": filtered["relative_volume"].round(2),
            "Tech Score (/85)": filtered["tech_score_85"],
            "Fund Score (/15)": filtered["fundamental_score"].round(1),
            "Overall Score (/100)": filtered["overall_score"].round(1),
            "Signal": filtered["signal"],
            "Entry Zone": [f"₹{l:.2f}-₹{h:.2f}" for l, h in zip(filtered["entry_low"], filtered["entry_high"])],
            "Stop-Loss (₹)": filtered["stop_loss"].round(2),
            "Target 2 (₹)": filtered["target_2"].round(2),
            "R:R": filtered["risk_reward_ratio"].round(2),
            "Strategies": filtered["matched_strategies"],
        }
    )

    st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Overall Score (/100)": st.column_config.ProgressColumn(
                "Overall Score (/100)",
                help="Normalized 0-100 composite score",
                format="%.1f",
                min_value=0,
                max_value=100,
            ),
        },
    )

    # Export Buttons (CSV and Excel)
    exp_col1, exp_col2, _ = st.columns([1, 1, 3])
    with exp_col1:
        csv_bytes = table_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Export Filtered to CSV",
            data=csv_bytes,
            file_name="tradepilot_nse_screener.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with exp_col2:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            table_df.to_excel(writer, index=False, sheet_name="NSE_Screener")
        st.download_button(
            label="📊 Export Filtered to Excel (.xlsx)",
            data=buffer.getvalue(),
            file_name="tradepilot_nse_screener.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
