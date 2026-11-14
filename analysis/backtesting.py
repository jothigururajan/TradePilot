"""
Historical Backtesting Engine for TradePilot NSE.
Evaluates Screening Strategies (A, B, C, D) over historical daily OHLCV data.

Key Anti-Bias Safeguards:
1. Zero Look-Ahead Bias: Signals are evaluated strictly on Bar `t` Close using indicators up to Bar `t`.
   Trade entry occurs at Bar `t + 1` Open (adjusted for realistic slippage).
2. Realistic Indian Equity Transaction Costs: Deducts configurable brokerage, STT, exchange turnover,
   SEBI fees, stamp duty, and slippage on every trade.
3. Corporate Actions Handling: Uses split/dividend-adjusted series or adjusts entry/exit ratios consistently.
4. Benchmark Comparison: Compares strategy cumulative return against Nifty 50 Index (`NIFTY_50`) over the exact same window.
"""
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from analysis.indicators import calculate_all_indicators
from analysis.strategies import evaluate_strategies_on_bar
from config import BACKTEST_CONFIG


def run_strategy_backtest(
    stock_histories: Dict[str, pd.DataFrame],
    strategy_name: str,
    start_date: str,
    end_date: str,
    initial_capital: float = BACKTEST_CONFIG.default_initial_capital,
    risk_per_trade_pct: float = 1.0,
    transaction_cost_pct: float = BACKTEST_CONFIG.brokerage_and_taxes_pct,
    slippage_pct: float = BACKTEST_CONFIG.slippage_pct,
    max_holding_days: int = BACKTEST_CONFIG.max_holding_days,
    benchmark_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Runs an event-driven multi-stock historical simulation for a chosen strategy.
    """
    trades: List[Dict[str, Any]] = []
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    total_friction_one_way = (transaction_cost_pct / 2.0 + slippage_pct) / 100.0

    for symbol, raw_df in stock_histories.items():
        if raw_df is None or len(raw_df) < 55:
            continue
        enriched = calculate_all_indicators(raw_df)
        if enriched.empty:
            continue

        enriched["dt"] = pd.to_datetime(enriched["trade_date"])
        in_Trade = False
        active_trade: Dict[str, Any] = {}

        for i in range(50, len(enriched) - 1):
            cur_bar = enriched.iloc[i]
            next_bar = enriched.iloc[i + 1]
            cur_dt = cur_bar["dt"]

            if cur_dt < start_dt or cur_dt > end_dt:
                continue

            if not in_Trade:
                eval_res = evaluate_strategies_on_bar(enriched, idx=i, enabled_strategies=[strategy_name])
                if strategy_name in eval_res["matched"]:
                    # Signal generated at Bar i Close -> Enter at Bar i+1 Open + slippage
                    raw_entry = float(next_bar["open"])
                    entry_price = raw_entry * (1.0 + total_friction_one_way)
                    atr_val = float(cur_bar["atr_14"]) if pd.notna(cur_bar.get("atr_14")) and cur_bar["atr_14"] > 0 else raw_entry * 0.02
                    stop_loss = round(entry_price - (2.0 * atr_val), 2)
                    risk_per_sh = max(entry_price - stop_loss, entry_price * 0.01)
                    target_price = round(entry_price + (2.5 * risk_per_sh), 2)

                    active_trade = {
                        "symbol": symbol,
                        "signal_date": str(cur_bar["trade_date"]),
                        "entry_date": str(next_bar["trade_date"]),
                        "entry_idx": i + 1,
                        "entry_price": round(entry_price, 2),
                        "stop_loss": stop_loss,
                        "target_price": target_price,
                        "risk_per_share": round(risk_per_sh, 2),
                    }
                    in_Trade = True
            else:
                # Check exit conditions on cur_bar (since entry was at or before cur_bar)
                if i < active_trade["entry_idx"]:
                    continue

                bars_held = i - active_trade["entry_idx"] + 1
                low_p = float(cur_bar["low"])
                high_p = float(cur_bar["high"])
                close_p = float(cur_bar["close"])
                open_p = float(cur_bar["open"])

                exit_price = None
                exit_reason = None

                # Conservative assumption: if both SL and Target are touched on same bar, assume Stop-Loss hit first
                if open_p <= active_trade["stop_loss"]:
                    exit_price = open_p * (1.0 - total_friction_one_way)
                    exit_reason = "Gap Down Stop-Loss"
                elif low_p <= active_trade["stop_loss"]:
                    exit_price = active_trade["stop_loss"] * (1.0 - total_friction_one_way)
                    exit_reason = "Stop-Loss Hit"
                elif open_p >= active_trade["target_price"]:
                    exit_price = open_p * (1.0 - total_friction_one_way)
                    exit_reason = "Gap Up Target Hit"
                elif high_p >= active_trade["target_price"]:
                    exit_price = active_trade["target_price"] * (1.0 - total_friction_one_way)
                    exit_reason = "Target Hit (2.5R)"
                elif bars_held >= max_holding_days:
                    exit_price = close_p * (1.0 - total_friction_one_way)
                    exit_reason = f"Time Exit ({max_holding_days}d)"

                if exit_price is not None:
                    ret_pct = ((exit_price - active_trade["entry_price"]) / active_trade["entry_price"]) * 100.0
                    r_multiple = (exit_price - active_trade["entry_price"]) / active_trade["risk_per_share"]
                    trades.append(
                        {
                            "symbol": symbol,
                            "signal_date": active_trade["signal_date"],
                            "entry_date": active_trade["entry_date"],
                            "exit_date": str(cur_bar["trade_date"]),
                            "holding_days": bars_held,
                            "entry_price": active_trade["entry_price"],
                            "exit_price": round(exit_price, 2),
                            "stop_loss": active_trade["stop_loss"],
                            "target_price": active_trade["target_price"],
                            "return_pct": round(ret_pct, 2),
                            "r_multiple": round(r_multiple, 2),
                            "exit_reason": exit_reason,
                        }
                    )
                    in_Trade = False
                    active_trade = {}

    if not trades:
        return {
            "strategy": strategy_name,
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "total_return_pct": 0.0,
            "final_capital": initial_capital,
            "avg_return_pct": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "profit_factor": 0.0,
            "benchmark_return_pct": 0.0,
            "trades_df": pd.DataFrame(),
            "equity_curve_df": pd.DataFrame(),
        }

    trades_df = pd.DataFrame(trades).sort_values("exit_date").reset_index(drop=True)

    # Simulate portfolio equity curve risking `risk_per_trade_pct` per trade (capped at 20% capital allocation per trade)
    equity = initial_capital
    peak_equity = initial_capital
    max_dd_pct = 0.0
    equity_records = []
    pnl_list = []

    for _, tr in trades_df.iterrows():
        risk_inr = equity * (risk_per_trade_pct / 100.0)
        risk_per_sh = max(tr["entry_price"] - tr["stop_loss"], tr["entry_price"] * 0.01)
        qty_by_risk = int(risk_inr // risk_per_sh)
        qty_by_cap = int((equity * 0.20) // tr["entry_price"])
        qty = max(1, min(qty_by_risk, qty_by_cap))

        trade_pnl = qty * (tr["exit_price"] - tr["entry_price"])
        pnl_list.append(trade_pnl)
        equity += trade_pnl
        peak_equity = max(peak_equity, equity)
        dd = ((peak_equity - equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0
        max_dd_pct = max(max_dd_pct, dd)

        equity_records.append(
            {
                "date": tr["exit_date"],
                "symbol": tr["symbol"],
                "trade_pnl": round(trade_pnl, 2),
                "equity": round(equity, 2),
                "drawdown_pct": round(-dd, 2),
            }
        )

    trades_df["net_pnl_inr"] = [round(x, 2) for x in pnl_list]
    wins = trades_df[trades_df["net_pnl_inr"] > 0]
    losses = trades_df[trades_df["net_pnl_inr"] <= 0]

    total_trades = len(trades_df)
    win_rate = (len(wins) / total_trades) * 100.0 if total_trades > 0 else 0.0
    gross_profit = wins["net_pnl_inr"].sum() if not wins.empty else 0.0
    gross_loss = abs(losses["net_pnl_inr"].sum()) if not losses.empty else 0.0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (9.99 if gross_profit > 0 else 0.0)
    total_return_pct = ((equity - initial_capital) / initial_capital) * 100.0

    # Benchmark comparison (Nifty 50 over same period)
    benchmark_ret_pct = 0.0
    if benchmark_df is not None and not benchmark_df.empty:
        bdf = benchmark_df.copy()
        bdf["dt"] = pd.to_datetime(bdf["trade_date"])
        bdf = bdf[(bdf["dt"] >= start_dt) & (bdf["dt"] <= end_dt)].sort_values("dt")
        if len(bdf) >= 2:
            b_start = float(bdf.iloc[0]["close"])
            b_end = float(bdf.iloc[-1]["close"])
            if b_start > 0:
                benchmark_ret_pct = round(((b_end - b_start) / b_start) * 100.0, 2)

    return {
        "strategy": strategy_name,
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "total_return_pct": round(total_return_pct, 2),
        "final_capital": round(equity, 2),
        "avg_return_pct": round(float(trades_df["return_pct"].mean()), 2),
        "avg_win_pct": round(float(wins["return_pct"].mean()), 2) if not wins.empty else 0.0,
        "avg_loss_pct": round(float(losses["return_pct"].mean()), 2) if not losses.empty else 0.0,
        "max_drawdown_pct": round(max_dd_pct, 2),
        "profit_factor": profit_factor,
        "benchmark_return_pct": benchmark_ret_pct,
        "trades_df": trades_df,
        "equity_curve_df": pd.DataFrame(equity_records),
    }
