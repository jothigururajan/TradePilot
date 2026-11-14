"""
Page 4: Trading Opportunities Categorized View.
Groups screened stocks into:
- Strong Bullish
- Momentum Breakout
- Pullback Opportunity
- Early Momentum
- Watchlist
- Avoid
"""
import streamlit as st
import pandas as pd
from data.database import DatabaseManager
from utils.helpers import format_inr, format_pct


def render_opportunities_page(db: DatabaseManager) -> None:
    st.title("🚀 Categorized Short-Term Trading Opportunities")

    df = db.get_all_screening_results()
    if df.empty:
        st.warning("No screening results available. Run **⚡ Smart Sync** from the sidebar.")
        return

    categories = [
        ("Momentum Breakout", "🔥 Strategy A: High-Volume Resistance Breakouts"),
        ("Strong Bullish", "📈 Strategy B: Established Institutional Uptrends"),
        ("Pullback Opportunity", "🎯 Strategy C: Value Retracements to Moving Average Support"),
        ("Early Momentum", "🌱 Strategy D: Fresh EMA 20 Reclaims & MACD Inflections"),
        ("Watchlist", "👀 Watchlist: Developing Setups Awaiting Trigger"),
        ("Avoid", "🛑 Avoid: Bearish Alignment or Unfavorable Risk/Reward"),
    ]

    tabs = st.tabs([c[0] for c in categories])

    for tab, (cat_key, cat_desc) in zip(tabs, categories):
        with tab:
            st.subheader(cat_desc)
            sub_df = df[df["opportunity_category"] == cat_key].copy()
            if sub_df.empty:
                st.info(f"No stocks currently classified under **{cat_key}**.")
                continue

            for _, row in sub_df.iterrows():
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([1.5, 1.5, 1.5, 2.5])
                    with c1:
                        st.markdown(f"### {row['symbol']}")
                        st.caption(f"{row['company_name']} ({row['sector']})")
                        st.markdown(f"**Signal:** `{row['signal']}`")
                    with c2:
                        st.metric("Close Price", format_inr(row["close_price"]), format_pct(row["daily_pct_change"]))
                        st.caption(f"Overall Score: **{row['overall_score']:.1f} / 100**")
                    with c3:
                        st.markdown(
                            f"**Entry Zone:** `₹{row['entry_low']:,.2f} – ₹{row['entry_high']:,.2f}`\n\n"
                            f"**Stop-Loss:** `₹{row['stop_loss']:,.2f}` (`-{row['downside_pct']:.1f}%`)\n\n"
                            f"**Target 2:** `₹{row['target_2']:,.2f}` (`+{row['upside_pct']:.1f}%` | **1:{row['risk_reward_ratio']:.2f}**)"
                        )
                    with c4:
                        st.markdown(f"**Strategies Matched:** `{row['matched_strategies']}`")
                        st.markdown(f"**Selection Rationale:** {row['score_reasons']}")
                        if st.button(f"➕ Add {row['symbol']} to Watchlist", key=f"opp_wl_{row['symbol']}"):
                            db.add_to_watchlist(
                                symbol=row["symbol"],
                                target_entry=float(row["close_price"]),
                                planned_stop_loss=float(row["stop_loss"]),
                                planned_target=float(row["target_2"]),
                                strategy_tag=str(row["matched_strategies"]),
                                notes=str(row["score_reasons"]),
                            )
                            st.toast(f"Added {row['symbol']} to Watchlist!")
