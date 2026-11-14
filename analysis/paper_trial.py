"""
1-Month Automated Paper Trading & Forward-Test Journal Engine for TradePilot NSE.
Manages a dedicated ₹50,000 (configurable + top-up) forward-testing trial:
1. Checks all OPEN paper trial positions against the latest EOD bar for Stop-Loss, Target, or Time Exits.
2. Scans today's BUY WATCH signals sorted by Overall Score (highest first) and enters up to 1-3 top stocks.
3. If zero stocks have a BUY WATCH signal, records 0 entries for the day.
4. Logs every daily run, entry, exit, charges (0.18% round-trip), net P&L, and realized R-multiple in SQLite.
"""
from datetime import timedelta
from typing import Any, Dict, List, Optional
import math
import pandas as pd

from data.database import DatabaseManager
from utils.helpers import now_ist
from utils.logging_config import get_logger

logger = get_logger("paper_trial")


def init_paper_trial_tables(db: DatabaseManager) -> None:
    with db.get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trial_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                initial_capital REAL NOT NULL DEFAULT 50000.0,
                added_capital REAL NOT NULL DEFAULT 0.0,
                max_daily_entries INTEGER NOT NULL DEFAULT 3,
                max_open_positions INTEGER NOT NULL DEFAULT 6,
                risk_per_trade_pct REAL NOT NULL DEFAULT 1.5,
                max_holding_days INTEGER NOT NULL DEFAULT 15,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trial_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                signal_date TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                entry_price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                stop_loss REAL NOT NULL,
                target_price REAL NOT NULL,
                risk_per_share REAL NOT NULL,
                planned_rr REAL NOT NULL,
                overall_score REAL NOT NULL,
                matched_strategies TEXT,
                exit_date TEXT,
                exit_price REAL,
                exit_reason TEXT,
                gross_pnl REAL DEFAULT 0.0,
                charges REAL DEFAULT 0.0,
                net_pnl REAL DEFAULT 0.0,
                return_pct REAL DEFAULT 0.0,
                realized_r REAL DEFAULT 0.0,
                notes TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trial_daily_logs (
                run_date TEXT PRIMARY KEY,
                buy_signals_count INTEGER NOT NULL,
                entries_taken INTEGER NOT NULL,
                exits_triggered INTEGER NOT NULL,
                equity_inr REAL NOT NULL,
                cash_inr REAL NOT NULL,
                summary_note TEXT NOT NULL
            )
        """)
        conn.commit()

    # Seed default 1-month trial config if empty (starting next Monday or today)
    with db.get_connection() as conn:
        row = conn.execute("SELECT id FROM paper_trial_config WHERE id = 1").fetchone()
        if not row:
            today = now_ist().date()
            # Default start date: upcoming Monday if weekend, else today
            days_until_mon = (7 - today.weekday()) % 7
            start_dt = today + timedelta(days=days_until_mon) if today.weekday() >= 5 else today
            end_dt = start_dt + timedelta(days=30)
            conn.execute(
                """
                INSERT INTO paper_trial_config
                (id, start_date, end_date, initial_capital, added_capital, max_daily_entries,
                 max_open_positions, risk_per_trade_pct, max_holding_days, is_active)
                VALUES (1, ?, ?, 50000.0, 0.0, 3, 6, 1.5, 15, 1)
                """,
                (start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")),
            )
            conn.commit()


def get_paper_trial_config(db: DatabaseManager) -> Dict[str, Any]:
    init_paper_trial_tables(db)
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM paper_trial_config WHERE id = 1").fetchone()
        return dict(row)


def update_paper_trial_config(
    db: DatabaseManager,
    start_date: str,
    end_date: str,
    initial_capital: float,
    max_daily_entries: int,
    max_open_positions: int,
    risk_per_trade_pct: float,
    max_holding_days: int,
    is_active: bool = True,
) -> None:
    init_paper_trial_tables(db)
    with db.get_connection() as conn:
        conn.execute(
            """
            UPDATE paper_trial_config
            SET start_date = ?, end_date = ?, initial_capital = ?, max_daily_entries = ?,
                max_open_positions = ?, risk_per_trade_pct = ?, max_holding_days = ?, is_active = ?
            WHERE id = 1
            """,
            (
                start_date,
                end_date,
                float(initial_capital),
                int(max_daily_entries),
                int(max_open_positions),
                float(risk_per_trade_pct),
                int(max_holding_days),
                1 if is_active else 0,
            ),
        )
        conn.commit()


def add_trial_capital(db: DatabaseManager, amount_inr: float) -> None:
    init_paper_trial_tables(db)
    if amount_inr <= 0:
        return
    with db.get_connection() as conn:
        conn.execute("UPDATE paper_trial_config SET added_capital = added_capital + ? WHERE id = 1", (float(amount_inr),))
        conn.commit()


def reset_paper_trial(db: DatabaseManager, initial_capital: float = 50000.0, start_date: Optional[str] = None) -> None:
    init_paper_trial_tables(db)
    today = now_ist().date()
    s_dt = pd.to_datetime(start_date).date() if start_date else today
    e_dt = s_dt + timedelta(days=30)
    with db.get_connection() as conn:
        conn.execute("DELETE FROM paper_trial_trades")
        conn.execute("DELETE FROM paper_trial_daily_logs")
        conn.execute(
            """
            UPDATE paper_trial_config
            SET start_date = ?, end_date = ?, initial_capital = ?, added_capital = 0.0, is_active = 1
            WHERE id = 1
            """,
            (s_dt.strftime("%Y-%m-%d"), e_dt.strftime("%Y-%m-%d"), float(initial_capital)),
        )
        conn.commit()


def run_daily_paper_trial_step(db: DatabaseManager, run_date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes one daily paper-trading cycle:
    1. Checks OPEN positions against latest market bar for exits (Stop-Loss, Target, or Time Exit).
    2. Checks today's BUY WATCH signals sorted by Overall Score descending and enters top 1-3 stocks.
    3. If 0 BUY WATCH signals exist, takes 0 entries.
    """
    init_paper_trial_tables(db)
    cfg = get_paper_trial_config(db)
    if not cfg.get("is_active", 1):
        return {"skipped": True, "reason": "Paper trial is currently paused in settings."}

    screen_df = db.get_all_screening_results()
    if screen_df.empty:
        return {"skipped": True, "reason": "No screening results in database yet."}

    latest_bar_date = str(screen_df["trade_date"].max())
    eff_date = run_date_str or latest_bar_date

    # 1. Process Exits on OPEN positions
    exits_triggered = 0
    exit_notes: List[str] = []

    with db.get_connection() as conn:
        open_rows = conn.execute("SELECT * FROM paper_trial_trades WHERE status = 'OPEN'").fetchall()

    for row in open_rows:
        pos = dict(row)
        sym = pos["symbol"]
        # Do not exit on the exact same bar it was entered
        if pos["entry_date"] >= eff_date:
            continue

        hist = db.get_historical_prices(sym, limit_days=30)
        if hist.empty:
            continue

        # Check latest bar (or bars since entry)
        recent_bars = hist[hist["trade_date"] > pos["entry_date"]]
        if recent_bars.empty:
            continue

        last_bar = recent_bars.iloc[-1]
        bar_dt = str(last_bar["trade_date"])
        low_p = float(last_bar["low"])
        high_p = float(last_bar["high"])
        close_p = float(last_bar["close"])
        open_p = float(last_bar["open"])
        bars_held = len(recent_bars)

        exit_px = None
        exit_reason = None

        if open_p <= pos["stop_loss"]:
            exit_px = open_p
            exit_reason = "Gap-Down Stop-Loss"
        elif low_p <= pos["stop_loss"]:
            exit_px = pos["stop_loss"]
            exit_reason = "Stop-Loss Hit"
        elif open_p >= pos["target_price"]:
            exit_px = open_p
            exit_reason = "Gap-Up Target Hit"
        elif high_p >= pos["target_price"]:
            exit_px = pos["target_price"]
            exit_reason = "Target 2 Hit"
        elif bars_held >= int(cfg["max_holding_days"]):
            exit_px = close_p
            exit_reason = f"Time Exit ({cfg['max_holding_days']}d)"

        if exit_px is not None:
            qty = int(pos["quantity"])
            gross_pnl = (exit_px - pos["entry_price"]) * qty
            charges = (pos["entry_price"] + exit_px) * qty * 0.0018  # 0.18% realistic delivery STT/brokerage
            net_pnl = gross_pnl - charges
            invested = pos["entry_price"] * qty
            ret_pct = (net_pnl / invested) * 100.0 if invested > 0 else 0.0
            realized_r = (exit_px - pos["entry_price"]) / pos["risk_per_share"] if pos["risk_per_share"] > 0 else 0.0

            with db.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE paper_trial_trades
                    SET status = 'CLOSED', exit_date = ?, exit_price = ?, exit_reason = ?,
                        gross_pnl = ?, charges = ?, net_pnl = ?, return_pct = ?, realized_r = ?
                    WHERE trade_id = ?
                    """,
                    (
                        bar_dt,
                        round(exit_px, 2),
                        exit_reason,
                        round(gross_pnl, 2),
                        round(charges, 2),
                        round(net_pnl, 2),
                        round(ret_pct, 2),
                        round(realized_r, 2),
                        pos["trade_id"],
                    ),
                )
                conn.commit()
            exits_triggered += 1
            exit_notes.append(f"EXIT {sym} @ ₹{exit_px:,.2f} ({exit_reason}, Net ₹{net_pnl:+,.2f})")

    # 2. Compute available cash & current open count before entries
    analytics = get_paper_trial_analytics(db)
    cash_available = analytics["cash_available"]
    current_equity = analytics["current_equity"]
    open_symbols = set(analytics["open_df"]["symbol"].tolist()) if not analytics["open_df"].empty else set()
    open_count = len(open_symbols)

    # 3. Scan BUY WATCH signals ordered by highest score
    buy_df = screen_df[screen_df["signal"] == "BUY WATCH"].sort_values("overall_score", ascending=False)
    buy_signals_count = len(buy_df)

    entries_taken = 0
    entry_notes: List[str] = []
    max_new = int(cfg["max_daily_entries"])
    max_open = int(cfg["max_open_positions"])
    risk_pct = float(cfg["risk_per_trade_pct"])

    if buy_signals_count == 0:
        entry_notes.append("No BUY WATCH signals today — 0 entries taken.")
    else:
        for _, cand in buy_df.iterrows():
            if entries_taken >= max_new or open_count >= max_open:
                break
            sym = cand["symbol"]
            if sym in open_symbols:
                continue

            entry_px = float(cand["close_price"])
            sl_px = float(cand["stop_loss"])
            tgt_px = float(cand["target_2"])
            risk_per_sh = max(entry_px - sl_px, entry_px * 0.01)

            # Position sizing: risk_pct of equity, capped at 35% of total equity and available cash
            max_risk_inr = current_equity * (risk_pct / 100.0)
            qty_by_risk = math.floor(max_risk_inr / risk_per_sh)
            qty_by_alloc = math.floor((current_equity * 0.35) / entry_px)
            qty_by_cash = math.floor(cash_available / entry_px)
            qty = min(qty_by_risk if qty_by_risk > 0 else qty_by_alloc, qty_by_alloc, qty_by_cash)

            if qty <= 0:
                continue

            cost = qty * entry_px
            planned_rr = round((tgt_px - entry_px) / risk_per_sh, 2)

            with db.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO paper_trial_trades
                    (symbol, status, signal_date, entry_date, entry_price, quantity, stop_loss, target_price,
                     risk_per_share, planned_rr, overall_score, matched_strategies, notes)
                    VALUES (?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sym,
                        str(cand["trade_date"]),
                        eff_date,
                        round(entry_px, 2),
                        int(qty),
                        round(sl_px, 2),
                        round(tgt_px, 2),
                        round(risk_per_sh, 2),
                        planned_rr,
                        round(float(cand["overall_score"]), 2),
                        str(cand.get("matched_strategies", "")),
                        f"Auto-entry Rank #{entries_taken + 1} (Score {cand['overall_score']:.1f})",
                    ),
                )
                conn.commit()

            cash_available -= cost
            open_symbols.add(sym)
            open_count += 1
            entries_taken += 1
            entry_notes.append(f"ENTRY {sym}: {qty} sh @ ₹{entry_px:,.2f} (SL ₹{sl_px:,.2f}, T2 ₹{tgt_px:,.2f})")

        if entries_taken == 0 and buy_signals_count > 0:
            entry_notes.append(
                f"{buy_signals_count} BUY WATCH signals found, but 0 new entries taken (already open, max positions {max_open} reached, or insufficient cash ₹{cash_available:,.0f})."
            )

    # 4. Refresh analytics & save daily log
    post_analytics = get_paper_trial_analytics(db)
    all_notes = " | ".join(exit_notes + entry_notes)

    with db.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO paper_trial_daily_logs
            (run_date, buy_signals_count, entries_taken, exits_triggered, equity_inr, cash_inr, summary_note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_date) DO UPDATE SET
                buy_signals_count = excluded.buy_signals_count,
                entries_taken = excluded.entries_taken,
                exits_triggered = excluded.exits_triggered,
                equity_inr = excluded.equity_inr,
                cash_inr = excluded.cash_inr,
                summary_note = excluded.summary_note
            """,
            (
                eff_date,
                buy_signals_count,
                entries_taken,
                exits_triggered,
                round(post_analytics["current_equity"], 2),
                round(post_analytics["cash_available"], 2),
                all_notes,
            ),
        )
        conn.commit()

    return {
        "skipped": False,
        "run_date": eff_date,
        "buy_signals_count": buy_signals_count,
        "entries_taken": entries_taken,
        "exits_triggered": exits_triggered,
        "summary_note": all_notes,
    }


def get_paper_trial_analytics(db: DatabaseManager) -> Dict[str, Any]:
    init_paper_trial_tables(db)
    cfg = get_paper_trial_config(db)

    with db.get_connection() as conn:
        open_df = pd.read_sql_query(
            """
            SELECT p.*, s.close_price as current_price, s.daily_pct_change
            FROM paper_trial_trades p
            LEFT JOIN screening_results s ON p.symbol = s.symbol
            WHERE p.status = 'OPEN'
            ORDER BY p.entry_date DESC, p.trade_id DESC
            """,
            conn,
        )
        closed_df = pd.read_sql_query(
            "SELECT * FROM paper_trial_trades WHERE status = 'CLOSED' ORDER BY exit_date DESC, trade_id DESC",
            conn,
        )
        logs_df = pd.read_sql_query("SELECT * FROM paper_trial_daily_logs ORDER BY run_date DESC", conn)

    base_capital = float(cfg["initial_capital"]) + float(cfg["added_capital"])
    realized_pnl = float(closed_df["net_pnl"].sum()) if not closed_df.empty else 0.0

    deployed_cost = 0.0
    unrealized_pnl = 0.0
    if not open_df.empty:
        open_df["current_price"] = open_df["current_price"].fillna(open_df["entry_price"])
        open_df["invested_inr"] = (open_df["entry_price"] * open_df["quantity"]).round(2)
        open_df["unrealized_pnl"] = ((open_df["current_price"] - open_df["entry_price"]) * open_df["quantity"]).round(2)
        open_df["unrealized_pct"] = (((open_df["current_price"] - open_df["entry_price"]) / open_df["entry_price"]) * 100.0).round(2)
        open_df["current_r"] = ((open_df["current_price"] - open_df["entry_price"]) / open_df["risk_per_share"]).round(2)
        deployed_cost = float(open_df["invested_inr"].sum())
        unrealized_pnl = float(open_df["unrealized_pnl"].sum())

    cash_available = base_capital + realized_pnl - deployed_cost
    current_equity = base_capital + realized_pnl + unrealized_pnl
    total_pnl = realized_pnl + unrealized_pnl
    total_return_pct = (total_pnl / base_capital) * 100.0 if base_capital > 0 else 0.0

    win_rate = 0.0
    profit_factor = 0.0
    avg_r = 0.0
    if not closed_df.empty:
        wins = closed_df[closed_df["net_pnl"] > 0]
        losses = closed_df[closed_df["net_pnl"] <= 0]
        win_rate = (len(wins) / len(closed_df)) * 100.0
        gp = float(wins["net_pnl"].sum()) if not wins.empty else 0.0
        gl = abs(float(losses["net_pnl"].sum())) if not losses.empty else 0.0
        profit_factor = round(gp / gl, 2) if gl > 0 else (9.99 if gp > 0 else 0.0)
        avg_r = round(float(closed_df["realized_r"].mean()), 2)

    return {
        "config": cfg,
        "initial_capital": float(cfg["initial_capital"]),
        "added_capital": float(cfg["added_capital"]),
        "total_capital": round(base_capital, 2),
        "cash_available": round(cash_available, 2),
        "deployed_capital": round(deployed_cost, 2),
        "current_equity": round(current_equity, 2),
        "realized_pnl": round(realized_pnl, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "total_return_pct": round(total_return_pct, 2),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": profit_factor,
        "avg_realized_r": avg_r,
        "open_df": open_df,
        "closed_df": closed_df,
        "logs_df": logs_df,
    }
