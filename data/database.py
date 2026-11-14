"""
SQLite Database Engine & Schema Management for TradePilot NSE.
Manages all 10 required tables with proper indexing, deduplication, and atomic transactions.
"""
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

from config import DB_PATH, SCREENER_DEFAULTS, SCORING_WEIGHTS
from data.stock_universe import DEFAULT_NSE_UNIVERSE
from utils.logging_config import get_logger
from utils.helpers import now_ist

logger = get_logger("database")


class DatabaseManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def init_db(self) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Stock Master
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_master (
                    symbol TEXT PRIMARY KEY,
                    yahoo_symbol TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    sector TEXT DEFAULT 'General',
                    market_cap_category TEXT DEFAULT 'Large Cap',
                    is_active INTEGER DEFAULT 1,
                    added_at TEXT NOT NULL
                )
            """)

            # 2. Historical Prices (Daily OHLCV)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historical_prices (
                    symbol TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    adj_close REAL,
                    volume INTEGER NOT NULL,
                    prev_close REAL,
                    daily_pct_change REAL,
                    data_source TEXT DEFAULT 'yfinance',
                    PRIMARY KEY (symbol, trade_date)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_hist_symbol_date ON historical_prices(symbol, trade_date DESC);")

            # 3. Technical Indicators (Latest Snapshot per Stock + Date)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS technical_indicators (
                    symbol TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    ema_9 REAL,
                    ema_20 REAL,
                    ema_50 REAL,
                    ema_100 REAL,
                    ema_200 REAL,
                    sma_20 REAL,
                    sma_50 REAL,
                    sma_200 REAL,
                    adx_14 REAL,
                    plus_di REAL,
                    minus_di REAL,
                    supertrend REAL,
                    supertrend_direction INTEGER,
                    rsi_14 REAL,
                    macd REAL,
                    macd_signal REAL,
                    macd_hist REAL,
                    stoch_rsi_k REAL,
                    stoch_rsi_d REAL,
                    roc_12 REAL,
                    atr_14 REAL,
                    bb_upper REAL,
                    bb_middle REAL,
                    bb_lower REAL,
                    bb_width_pct REAL,
                    hist_volatility_20d REAL,
                    vol_sma_20 REAL,
                    relative_volume REAL,
                    obv REAL,
                    vol_breakout INTEGER,
                    support_20d REAL,
                    resistance_20d REAL,
                    high_52w REAL,
                    low_52w REAL,
                    PRIMARY KEY (symbol, trade_date)
                )
            """)

            # 4. Fundamental Data
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fundamental_data (
                    symbol TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    revenue_growth_pct REAL,
                    profit_growth_pct REAL,
                    eps_growth_pct REAL,
                    roe_pct REAL,
                    roce_pct REAL,
                    debt_to_equity REAL,
                    current_ratio REAL,
                    operating_margin_pct REAL,
                    net_margin_pct REAL,
                    pe_ratio REAL,
                    pb_ratio REAL,
                    promoter_holding_pct REAL,
                    promoter_pledging_pct REAL,
                    institutional_holding_pct REAL,
                    market_cap_cr REAL,
                    fundamental_class TEXT,
                    fundamental_raw_score REAL,
                    metrics_available_count INTEGER,
                    notes TEXT
                )
            """)

            # 5. Screening Results & Ranks
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS screening_results (
                    symbol TEXT PRIMARY KEY,
                    trade_date TEXT NOT NULL,
                    computed_at TEXT NOT NULL,
                    close_price REAL,
                    daily_pct_change REAL,
                    trend_score REAL,
                    momentum_score REAL,
                    volume_score REAL,
                    breakout_score REAL,
                    fundamental_score REAL,
                    risk_reward_score REAL,
                    overall_score REAL,
                    data_coverage_pct REAL,
                    signal TEXT,
                    opportunity_category TEXT,
                    matched_strategies TEXT,
                    score_reasons TEXT,
                    missing_data_warnings TEXT,
                    entry_low REAL,
                    entry_high REAL,
                    stop_loss REAL,
                    target_1 REAL,
                    target_2 REAL,
                    target_3 REAL,
                    risk_per_share REAL,
                    reward_per_share_t2 REAL,
                    risk_reward_ratio REAL,
                    upside_pct REAL,
                    downside_pct REAL,
                    price_methodology TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_screen_score ON screening_results(overall_score DESC);")

            # 6. Watchlist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    symbol TEXT PRIMARY KEY,
                    added_at TEXT NOT NULL,
                    target_entry REAL,
                    planned_stop_loss REAL,
                    planned_target REAL,
                    strategy_tag TEXT,
                    notes TEXT
                )
            """)

            # 7. Portfolio (Active Hypothetical / Paper Positions)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio (
                    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    entry_date TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    stop_loss REAL NOT NULL,
                    target_price REAL NOT NULL,
                    strategy_used TEXT,
                    notes TEXT,
                    status TEXT DEFAULT 'OPEN'
                )
            """)

            # 8. Trade History (Closed Trades)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_history (
                    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    entry_date TEXT NOT NULL,
                    exit_date TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    stop_loss REAL,
                    target_price REAL,
                    gross_pnl REAL NOT NULL,
                    net_pnl REAL NOT NULL,
                    return_pct REAL NOT NULL,
                    strategy_used TEXT,
                    exit_reason TEXT,
                    notes TEXT
                )
            """)

            # 9. User Settings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # 10. Data Update Logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS data_update_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    update_type TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    symbols_requested INTEGER NOT NULL,
                    symbols_succeeded INTEGER NOT NULL,
                    symbols_failed INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT
                )
            """)

            conn.commit()

        self.seed_default_universe()
        self.seed_default_settings()

    def seed_default_universe(self) -> None:
        now_str = now_ist().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for item in DEFAULT_NSE_UNIVERSE:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO stock_master
                    (symbol, yahoo_symbol, company_name, sector, market_cap_category, is_active, added_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        item["symbol"],
                        item["Yahoo_Symbol"],
                        item["company_name"],
                        item["sector"],
                        item["market_cap_category"],
                        now_str,
                    ),
                )
            conn.commit()

    def seed_default_settings(self) -> None:
        defaults = {
            "trading_horizon": SCREENER_DEFAULTS.trading_horizon,
            "min_overall_score": SCREENER_DEFAULTS.min_overall_score,
            "min_avg_volume_20d": SCREENER_DEFAULTS.min_avg_volume_20d,
            "min_daily_turnover_cr": SCREENER_DEFAULTS.min_daily_turnover_cr,
            "rsi_min": SCREENER_DEFAULTS.rsi_min,
            "rsi_max": SCREENER_DEFAULTS.rsi_max,
            "adx_min": SCREENER_DEFAULTS.adx_min,
            "min_relative_volume": SCREENER_DEFAULTS.min_relative_volume,
            "min_risk_reward": SCREENER_DEFAULTS.min_risk_reward,
            "preferred_risk_reward": SCREENER_DEFAULTS.preferred_risk_reward,
            "market_cap_categories": SCREENER_DEFAULTS.market_cap_categories,
            "enabled_strategies": SCREENER_DEFAULTS.enabled_strategies,
            "scoring_weights": SCORING_WEIGHTS.as_dict(),
        }
        now_str = now_ist().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for k, v in defaults.items():
                cursor.execute(
                    "INSERT OR IGNORE INTO user_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                    (k, json.dumps(v), now_str),
                )
            conn.commit()

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.get_connection() as conn:
            row = conn.execute("SELECT setting_value FROM user_settings WHERE setting_key = ?", (key,)).fetchone()
            if row:
                try:
                    return json.loads(row["setting_value"])
                except Exception:
                    return row["setting_value"]
        return default

    def save_setting(self, key: str, value: Any) -> None:
        now_str = now_ist().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value), now_str),
            )
            conn.commit()

    def get_active_stocks(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT symbol, yahoo_symbol, company_name, sector, market_cap_category FROM stock_master WHERE is_active = 1 ORDER BY symbol"
            ).fetchall()
            return [dict(r) for r in rows]

    def add_or_update_stock(
        self, symbol: str, company_name: str, sector: str = "General", market_cap_category: str = "Mid Cap", is_active: int = 1
    ) -> None:
        clean_sym = symbol.strip().upper().replace(".NS", "")
        yahoo_sym = f"{clean_sym}.NS"
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO stock_master (symbol, yahoo_symbol, company_name, sector, market_cap_category, is_active, added_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    company_name = excluded.company_name,
                    sector = excluded.sector,
                    market_cap_category = excluded.market_cap_category,
                    is_active = excluded.is_active
                """,
                (clean_sym, yahoo_sym, company_name.strip(), sector.strip(), market_cap_category, is_active, now_ist().isoformat()),
            )
            conn.commit()

    def save_historical_prices(self, symbol: str, df: pd.DataFrame, source: str = "yfinance") -> int:
        if df is None or df.empty:
            return 0
        df = df.copy().sort_index()
        df["prev_close"] = df["Close"].shift(1)
        df["daily_pct_change"] = ((df["Close"] - df["prev_close"]) / df["prev_close"]) * 100.0

        records = []
        for idx, row in df.iterrows():
            trade_date = pd.to_datetime(idx).strftime("%Y-%m-%d")
            if pd.isna(row["Close"]) or pd.isna(row["Open"]):
                continue
            records.append(
                (
                    symbol,
                    trade_date,
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    float(row.get("Adj Close", row["Close"])),
                    int(row.get("Volume", 0) or 0),
                    None if pd.isna(row["prev_close"]) else float(row["prev_close"]),
                    None if pd.isna(row["daily_pct_change"]) else float(row["daily_pct_change"]),
                    source,
                )
            )

        with self.get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO historical_prices
                (symbol, trade_date, open, high, low, close, adj_close, volume, prev_close, daily_pct_change, data_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, trade_date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    adj_close = excluded.adj_close,
                    volume = excluded.volume,
                    prev_close = excluded.prev_close,
                    daily_pct_change = excluded.daily_pct_change,
                    data_source = excluded.data_source
                """,
                records,
            )
            conn.commit()
        return len(records)

    def get_historical_prices(self, symbol: str, limit_days: int = 500) -> pd.DataFrame:
        with self.get_connection() as conn:
            query = """
                SELECT trade_date, open, high, low, close, adj_close, volume, prev_close, daily_pct_change, data_source
                FROM historical_prices
                WHERE symbol = ?
                ORDER BY trade_date DESC
                LIMIT ?
            """
            df = pd.read_sql_query(query, conn, params=(symbol, limit_days))
        if df.empty:
            return df
        df = df.sort_values("trade_date").reset_index(drop=True)
        return df

    def get_latest_trade_date(self, symbol: str) -> Optional[str]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT MAX(trade_date) as max_dt FROM historical_prices WHERE symbol = ?", (symbol,)).fetchone()
            return row["max_dt"] if row and row["max_dt"] else None

    def save_technical_indicators(self, row_dict: Dict[str, Any]) -> None:
        columns = list(row_dict.keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)
        update_clause = ", ".join([f"{col} = excluded.{col}" for col in columns if col not in ("symbol", "trade_date")])

        with self.get_connection() as conn:
            conn.execute(
                f"""
                INSERT INTO technical_indicators ({col_names})
                VALUES ({placeholders})
                ON CONFLICT(symbol, trade_date) DO UPDATE SET
                    {update_clause}
                """,
                [row_dict[c] for c in columns],
            )
            conn.commit()

    def save_fundamental_data(self, row_dict: Dict[str, Any]) -> None:
        columns = list(row_dict.keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)
        update_clause = ", ".join([f"{col} = excluded.{col}" for col in columns if col != "symbol"])

        with self.get_connection() as conn:
            conn.execute(
                f"""
                INSERT INTO fundamental_data ({col_names})
                VALUES ({placeholders})
                ON CONFLICT(symbol) DO UPDATE SET
                    {update_clause}
                """,
                [row_dict[c] for c in columns],
            )
            conn.commit()

    def get_fundamental_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM fundamental_data WHERE symbol = ?", (symbol,)).fetchone()
            return dict(row) if row else None

    def save_screening_result(self, row_dict: Dict[str, Any]) -> None:
        columns = list(row_dict.keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)
        update_clause = ", ".join([f"{col} = excluded.{col}" for col in columns if col != "symbol"])

        with self.get_connection() as conn:
            conn.execute(
                f"""
                INSERT INTO screening_results ({col_names})
                VALUES ({placeholders})
                ON CONFLICT(symbol) DO UPDATE SET
                    {update_clause}
                """,
                [row_dict[c] for c in columns],
            )
            conn.commit()

    def get_all_screening_results(self) -> pd.DataFrame:
        with self.get_connection() as conn:
            query = """
                SELECT
                    s.*,
                    m.company_name,
                    m.sector,
                    m.market_cap_category,
                    t.rsi_14,
                    t.adx_14,
                    t.macd,
                    t.macd_signal,
                    t.macd_hist,
                    t.relative_volume,
                    t.vol_sma_20,
                    t.ema_20,
                    t.ema_50,
                    t.ema_200,
                    t.atr_14,
                    t.support_20d,
                    t.resistance_20d,
                    f.fundamental_class,
                    f.pe_ratio,
                    f.roe_pct,
                    f.debt_to_equity
                FROM screening_results s
                JOIN stock_master m ON s.symbol = m.symbol
                LEFT JOIN technical_indicators t ON s.symbol = t.symbol AND s.trade_date = t.trade_date
                LEFT JOIN fundamental_data f ON s.symbol = f.symbol
                WHERE m.is_active = 1
                ORDER BY s.overall_score DESC
            """
            return pd.read_sql_query(query, conn)

    def log_data_update(
        self,
        started_at: str,
        completed_at: str,
        update_type: str,
        provider: str,
        requested: int,
        succeeded: int,
        failed: int,
        status: str,
        details: str = "",
    ) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO data_update_logs
                (started_at, completed_at, update_type, provider, symbols_requested, symbols_succeeded, symbols_failed, status, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (started_at, completed_at, update_type, provider, requested, succeeded, failed, status, details),
            )
            conn.commit()

    def get_last_update_log(self) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM data_update_logs ORDER BY log_id DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def get_update_logs(self, limit: int = 25) -> pd.DataFrame:
        with self.get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM data_update_logs ORDER BY log_id DESC LIMIT ?", conn, params=(limit,))

    # Watchlist & Portfolio CRUD
    def add_to_watchlist(
        self, symbol: str, target_entry: float, planned_stop_loss: float, planned_target: float, strategy_tag: str = "", notes: str = ""
    ) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO watchlist (symbol, added_at, target_entry, planned_stop_loss, planned_target, strategy_tag, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    target_entry = excluded.target_entry,
                    planned_stop_loss = excluded.planned_stop_loss,
                    planned_target = excluded.planned_target,
                    strategy_tag = excluded.strategy_tag,
                    notes = excluded.notes
                """,
                (symbol.upper(), now_ist().isoformat(), target_entry, planned_stop_loss, planned_target, strategy_tag, notes),
            )
            conn.commit()

    def remove_from_watchlist(self, symbol: str) -> None:
        with self.get_connection() as conn:
            conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper(),))
            conn.commit()

    def get_watchlist(self) -> pd.DataFrame:
        with self.get_connection() as conn:
            query = """
                SELECT w.*, s.close_price, s.daily_pct_change, s.overall_score, s.signal
                FROM watchlist w
                LEFT JOIN screening_results s ON w.symbol = s.symbol
                ORDER BY w.added_at DESC
            """
            return pd.read_sql_query(query, conn)

    def add_portfolio_position(
        self,
        symbol: str,
        entry_date: str,
        entry_price: float,
        quantity: int,
        stop_loss: float,
        target_price: float,
        strategy_used: str = "",
        notes: str = "",
    ) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO portfolio (symbol, entry_date, entry_price, quantity, stop_loss, target_price, strategy_used, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
                """,
                (symbol.upper(), entry_date, entry_price, quantity, stop_loss, target_price, strategy_used, notes),
            )
            conn.commit()

    def close_portfolio_position(self, position_id: int, exit_date: str, exit_price: float, exit_reason: str = "Target/Manual") -> None:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM portfolio WHERE position_id = ?", (position_id,)).fetchone()
            if not row:
                return
            pos = dict(row)
            gross_pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
            turnover = (pos["entry_price"] + exit_price) * pos["quantity"]
            est_charges = turnover * 0.0018
            net_pnl = gross_pnl - est_charges
            invested = pos["entry_price"] * pos["quantity"]
            return_pct = (net_pnl / invested) * 100.0 if invested > 0 else 0.0

            conn.execute(
                """
                INSERT INTO trade_history
                (symbol, entry_date, exit_date, entry_price, exit_price, quantity, stop_loss, target_price,
                 gross_pnl, net_pnl, return_pct, strategy_used, exit_reason, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pos["symbol"],
                    pos["entry_date"],
                    exit_date,
                    pos["entry_price"],
                    exit_price,
                    pos["quantity"],
                    pos["stop_loss"],
                    pos["target_price"],
                    gross_pnl,
                    net_pnl,
                    return_pct,
                    pos["strategy_used"],
                    exit_reason,
                    pos["notes"],
                ),
            )
            conn.execute("DELETE FROM portfolio WHERE position_id = ?", (position_id,))
            conn.commit()

    def get_open_positions(self) -> pd.DataFrame:
        with self.get_connection() as conn:
            query = """
                SELECT p.*, s.close_price as current_price, s.signal as current_signal
                FROM portfolio p
                LEFT JOIN screening_results s ON p.symbol = s.symbol
                WHERE p.status = 'OPEN'
                ORDER BY p.entry_date DESC
            """
            return pd.read_sql_query(query, conn)

    def get_trade_history(self) -> pd.DataFrame:
        with self.get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM trade_history ORDER BY exit_date DESC, trade_id DESC", conn)
