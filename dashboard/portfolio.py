"""
Page 5: Portfolio & Watchlist Manager.
Allows users to manage their Watchlist, enter hypothetical/paper trades, monitor live stop-loss/target distances,
close positions to record realized P&L in Trade History, and export portfolio records.
"""
import streamlit as st
import pandas as pd
from data.database import DatabaseManager
from utils.helpers import format_inr, format_pct, now_ist


def render_portfolio_page(db: DatabaseManager) -> None:
    st.title("💼 Portfolio Tracker & Watchlist Manager")

    tab_wl, tab_open, tab_hist = st.tabs(["⭐ Watchlist", "📂 Active Paper Portfolio", "📜 Closed Trade History"])

    # -------------------------------------------------------------------------
    # TAB 1: WATCHLIST
    # -------------------------------------------------------------------------
    with tab_wl:
        st.subheader("⭐ Monitored Watchlist Stocks")
        wl_df = db.get_watchlist()
        if wl_df.empty:
            st.info("Your watchlist is currently empty. Add stocks from 'Stock Detail' or 'Trading Opportunities'.")
        else:
            st.dataframe(wl_df, use_container_width=True, hide_index=True)
            rem_col1, rem_col2 = st.columns([2, 1])
            with rem_col1:
                sym_to_remove = st.selectbox("Select Symbol to Remove from Watchlist", wl_df["symbol"].tolist())
            with rem_col2:
                st.write("")
                if st.button("🗑️ Remove Selected Symbol"):
                    db.remove_from_watchlist(sym_to_remove)
                    st.success(f"Removed {sym_to_remove} from Watchlist.")
                    st.rerun()

    # -------------------------------------------------------------------------
    # TAB 2: ACTIVE PORTFOLIO
    # -------------------------------------------------------------------------
    with tab_open:
        st.subheader("➕ Log New Hypothetical / Paper Trade")
        stocks = [s["symbol"] for s in db.get_active_stocks()]
        with st.form("add_position_form"):
            f1, f2, f3, f4, f5 = st.columns(5)
            p_sym = f1.selectbox("Symbol", stocks)
            p_entry = f2.number_input("Entry Price (₹)", min_value=1.0, value=1000.0, step=5.0)
            p_qty = f3.number_input("Quantity", min_value=1, value=10, step=1)
            p_sl = f4.number_input("Stop-Loss (₹)", min_value=0.5, value=950.0, step=5.0)
            p_tgt = f5.number_input("Target Price (₹)", min_value=1.0, value=1120.0, step=5.0)
            p_notes = st.text_input("Strategy / Trade Notes", "Momentum Breakout setup")
            submitted = st.form_submit_button("📥 Record Open Position")
            if submitted:
                db.add_portfolio_position(
                    symbol=p_sym,
                    entry_date=now_ist().strftime("%Y-%m-%d"),
                    entry_price=p_entry,
                    quantity=int(p_qty),
                    stop_loss=p_sl,
                    target_price=p_tgt,
                    strategy_used="Manual/Screener",
                    notes=p_notes,
                )
                st.success(f"Added open position for {p_sym} ({p_qty} shares @ ₹{p_entry:.2f}).")
                st.rerun()

        st.subheader("📂 Open Positions & Stop-Loss Monitor")
        open_df = db.get_open_positions()
        if open_df.empty:
            st.info("No open positions currently recorded.")
        else:
            open_df["current_price"] = open_df["current_price"].fillna(open_df["entry_price"])
            open_df["invested_inr"] = (open_df["entry_price"] * open_df["quantity"]).round(2)
            open_df["unrealized_pnl"] = ((open_df["current_price"] - open_df["entry_price"]) * open_df["quantity"]).round(2)
            open_df["unrealized_pct"] = (((open_df["current_price"] - open_df["entry_price"]) / open_df["entry_price"]) * 100.0).round(2)
            open_df["status_alert"] = open_df.apply(
                lambda r: "🚨 STOP-LOSS BREACHED"
                if r["current_price"] <= r["stop_loss"]
                else ("🎯 TARGET REACHED" if r["current_price"] >= r["target_price"] else "✅ ACTIVE"),
                axis=1,
            )

            tot_inv = open_df["invested_inr"].sum()
            tot_upnl = open_df["unrealized_pnl"].sum()
            k1, k2, k3 = st.columns(3)
            k1.metric("Open Positions Count", f"{len(open_df)}")
            k2.metric("Total Capital Deployed", format_inr(tot_inv))
            k3.metric("Total Unrealized P&L", format_inr(tot_upnl), format_pct((tot_upnl / tot_inv * 100) if tot_inv > 0 else 0))

            st.dataframe(open_df, use_container_width=True, hide_index=True)

            st.markdown("#### 🔒 Close an Open Position")
            c_id, c_px, c_rsn, c_btn = st.columns([1.5, 1.5, 2, 1.5])
            pos_id_to_close = c_id.selectbox(
                "Position ID",
                open_df["position_id"].tolist(),
                format_func=lambda pid: f"#{pid} - {open_df.loc[open_df['position_id'] == pid, 'symbol'].values[0]}",
            )
            default_exit_px = float(open_df.loc[open_df["position_id"] == pos_id_to_close, "current_price"].values[0])
            exit_px = c_px.number_input("Exit Price (₹)", min_value=0.5, value=default_exit_px, step=1.0)
            exit_rsn = c_rsn.selectbox("Exit Reason", ["Target Reached", "Stop-Loss Hit", "Trailing Stop", "Manual Exit"])
            c_btn.write("")
            if c_btn.button("✅ Close Trade"):
                db.close_portfolio_position(
                    position_id=int(pos_id_to_close),
                    exit_date=now_ist().strftime("%Y-%m-%d"),
                    exit_price=exit_px,
                    exit_reason=exit_rsn,
                )
                st.success(f"Closed position #{pos_id_to_close} and logged to Trade History.")
                st.rerun()

    # -------------------------------------------------------------------------
    # TAB 3: TRADE HISTORY & EXPORT
    # -------------------------------------------------------------------------
    with tab_hist:
        st.subheader("📜 Realized Trade History")
        hist_df = db.get_trade_history()
        if hist_df.empty:
            st.info("No closed trades recorded yet.")
        else:
            total_net = hist_df["net_pnl"].sum()
            win_rate = (hist_df["net_pnl"] > 0).mean() * 100.0
            h1, h2, h3 = st.columns(3)
            h1.metric("Closed Trades", f"{len(hist_df)}")
            h2.metric("Realized Win Rate", f"{win_rate:.1f}%")
            h3.metric("Total Net Realized P&L (After Charges)", format_inr(total_net))

            st.dataframe(hist_df, use_container_width=True, hide_index=True)
            csv_data = hist_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Export Trade History to CSV",
                data=csv_data,
                file_name="tradepilot_nse_trade_history.csv",
                mime="text/csv",
            )
