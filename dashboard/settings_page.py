"""
Page 7: Custom Settings, NSE Stock Universe & Telegram Alert Manager.
Allows users to configure trading horizon, minimum score, liquidity thresholds, 100-point category weights,
add/remove custom NSE stock tickers, and configure/test daily Telegram BUY WATCH notifications.
"""
import streamlit as st
import pandas as pd
from data.database import DatabaseManager
from analysis.pipeline import run_full_screening_pipeline
from utils.telegram_notifier import (
    resolve_telegram_credentials,
    format_eod_telegram_message,
    send_telegram_message,
    dispatch_eod_telegram_alert,
)


def render_settings_page(db: DatabaseManager) -> None:
    st.title("⚙️ Custom Screening Settings, Universe & Telegram Alerts")

    tab_cfg, tab_weights, tab_univ, tab_tg = st.tabs(
        [
            "🎛️ Screening Thresholds",
            "⚖️ 100-Point Scoring Weights",
            "🏢 Manage NSE Stock Universe",
            "📲 Telegram EOD Alerts",
        ]
    )

    with tab_cfg:
        st.subheader("Short-Term Screening Parameters")
        with st.form("screener_settings_form"):
            c1, c2 = st.columns(2)
            with c1:
                horizon_opts = ["3-5 Days", "1-2 Weeks", "2-6 Weeks"]
                cur_h = db.get_setting("trading_horizon", "1-2 Weeks")
                h_idx = horizon_opts.index(cur_h) if cur_h in horizon_opts else 1
                new_horizon = st.selectbox("Default Trading Horizon", horizon_opts, index=h_idx)
                new_min_score = st.slider("Default Minimum Score", 0.0, 90.0, float(db.get_setting("min_overall_score", 60.0)), 2.5)
                new_min_vol = st.number_input("Minimum 20D Average Volume", 10000, 5000000, int(db.get_setting("min_avg_volume_20d", 150000)), 25000)
                new_min_rr = st.number_input("Minimum Risk/Reward Ratio", 1.0, 5.0, float(db.get_setting("min_risk_reward", 2.0)), 0.1)
            with c2:
                new_rsi_min = st.number_input("Minimum RSI (14)", 10.0, 60.0, float(db.get_setting("rsi_min", 40.0)), 1.0)
                new_rsi_max = st.number_input("Maximum RSI (14)", 55.0, 95.0, float(db.get_setting("rsi_max", 75.0)), 1.0)
                new_adx_min = st.number_input("Minimum ADX (14)", 5.0, 40.0, float(db.get_setting("adx_min", 18.0)), 1.0)
                all_strats = [
                    "Strategy A: Momentum Breakout",
                    "Strategy B: Trend-Following",
                    "Strategy C: Pullback Entry",
                    "Strategy D: Early Momentum",
                ]
                cur_strats = db.get_setting("enabled_strategies", all_strats)
                new_strats = st.multiselect("Enabled Screening Strategies", all_strats, default=cur_strats)

            if st.form_submit_button("💾 Save Settings & Re-Run Screener"):
                db.save_setting("trading_horizon", new_horizon)
                db.save_setting("min_overall_score", new_min_score)
                db.save_setting("min_avg_volume_20d", new_min_vol)
                db.save_setting("min_risk_reward", new_min_rr)
                db.save_setting("rsi_min", new_rsi_min)
                db.save_setting("rsi_max", new_rsi_max)
                db.save_setting("adx_min", new_adx_min)
                db.save_setting("enabled_strategies", new_strats)
                run_full_screening_pipeline(db)
                st.success("Settings saved and universe re-scored!")

    with tab_weights:
        st.subheader("Configure 100-Point Scoring Model Allocation")
        cur_w = db.get_setting(
            "scoring_weights",
            {
                "trend_strength": 20.0,
                "momentum": 20.0,
                "volume_confirmation": 15.0,
                "breakout_potential": 15.0,
                "fundamental_strength": 15.0,
                "risk_reward_suitability": 15.0,
            },
        )
        with st.form("weights_form"):
            w1, w2, w3 = st.columns(3)
            wt_trend = w1.number_input("Trend Strength Weight", 5.0, 50.0, float(cur_w.get("trend_strength", 20.0)), 1.0)
            wt_mom = w1.number_input("Momentum Weight", 5.0, 50.0, float(cur_w.get("momentum", 20.0)), 1.0)
            wt_vol = w2.number_input("Volume Confirmation Weight", 5.0, 40.0, float(cur_w.get("volume_confirmation", 15.0)), 1.0)
            wt_brk = w2.number_input("Breakout Potential Weight", 5.0, 40.0, float(cur_w.get("breakout_potential", 15.0)), 1.0)
            wt_fund = w3.number_input("Fundamental Strength Weight", 0.0, 40.0, float(cur_w.get("fundamental_strength", 15.0)), 1.0)
            wt_rr = w3.number_input("Risk/Reward Suitability Weight", 5.0, 40.0, float(cur_w.get("risk_reward_suitability", 15.0)), 1.0)

            if st.form_submit_button("⚖️ Update Scoring Weights"):
                total_w = wt_trend + wt_mom + wt_vol + wt_brk + wt_fund + wt_rr
                if abs(total_w - 100.0) > 0.01:
                    st.warning(f"Note: Your weights sum to {total_w:.1f} (Engine will automatically normalize to 100%).")
                db.save_setting(
                    "scoring_weights",
                    {
                        "trend_strength": wt_trend,
                        "momentum": wt_mom,
                        "volume_confirmation": wt_vol,
                        "breakout_potential": wt_brk,
                        "fundamental_strength": wt_fund,
                        "risk_reward_suitability": wt_rr,
                    },
                )
                run_full_screening_pipeline(db)
                st.success("Scoring weights updated and rankings recalculated!")

    with tab_univ:
        st.subheader("Add Custom NSE Stock to Universe")
        with st.form("add_stock_form"):
            u1, u2, u3, u4 = st.columns(4)
            new_sym = u1.text_input("NSE Symbol (e.g., ZOMATO, IRCTC)")
            new_name = u2.text_input("Company Name")
            new_sec = u3.text_input("Sector", "General")
            new_mcap = u4.selectbox("Market Cap Category", ["Large Cap", "Mid Cap", "Small Cap"])
            if st.form_submit_button("➕ Add Stock to Universe"):
                if new_sym.strip() and new_name.strip():
                    db.add_or_update_stock(new_sym, new_name, new_sec, new_mcap, 1)
                    st.success(f"Added {new_sym.upper()} ({new_sym.upper()}.NS) to stock master! Click Smart Sync to fetch its data.")
                    st.rerun()
                else:
                    st.error("Please provide both NSE Symbol and Company Name.")

        st.subheader("Active NSE Stock Universe")
        stocks_df = pd.DataFrame(db.get_active_stocks())
        st.dataframe(stocks_df, use_container_width=True, hide_index=True)

    with tab_tg:
        st.subheader("📲 Automated Telegram EOD BUY WATCH Alerts")
        st.caption(
            "Configure your Telegram Bot Token and Chat ID below (or via `TRADEPILOT_TELEGRAM_BOT_TOKEN` and "
            "`TRADEPILOT_TELEGRAM_CHAT_ID` in `.env`) so `eod_auto_update.py` automatically sends daily BUY WATCH setups to your phone."
        )

        cur_tg = resolve_telegram_credentials(db)
        with st.form("telegram_settings_form"):
            t1, t2 = st.columns(2)
            with t1:
                tg_enabled = st.checkbox("Enable Automated EOD Telegram Alerts", value=cur_tg["enabled"])
                tg_token = st.text_input("Telegram Bot Token (from @BotFather)", value=cur_tg["bot_token"], type="password")
                tg_chat_id = st.text_input("Telegram Chat ID (from @userinfobot or getUpdates)", value=cur_tg["chat_id"])
            with t2:
                tg_max = st.slider("Max BUY WATCH Setups Per Message", 1, 15, int(cur_tg["max_alerts"]))
                tg_fallback = st.checkbox(
                    "Include top 3 HOLD WATCH candidates if 0 BUY WATCH stocks trigger",
                    value=cur_tg["include_hold_if_empty"],
                )

            if st.form_submit_button("💾 Save Telegram Alert Settings"):
                db.save_setting(
                    "telegram_config",
                    {
                        "enabled": tg_enabled,
                        "bot_token": tg_token.strip(),
                        "chat_id": tg_chat_id.strip(),
                        "max_alerts": int(tg_max),
                        "include_hold_if_empty": tg_fallback,
                    },
                )
                st.success("Telegram configuration saved to SQLite database!")

        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("📨 Send Instant EOD BUY WATCH Alert Now", use_container_width=True):
                res = dispatch_eod_telegram_alert(db, force_send=True)
                if res.get("ok"):
                    st.success("✅ EOD BUY WATCH summary sent to your Telegram!")
                else:
                    st.error(f"❌ Could not send alert: {res.get('error') or res.get('reason')}")

        with btn_c2:
            if st.button("👁️ Preview Formatted Telegram Alert Message", use_container_width=True):
                df_screen = db.get_all_screening_results()
                preview_html = format_eod_telegram_message(
                    df_screen,
                    max_alerts=cur_tg["max_alerts"],
                    include_hold_if_empty=cur_tg["include_hold_if_empty"],
                )
                st.code(preview_html, language="html")
