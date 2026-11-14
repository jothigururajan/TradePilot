"""
Pluggable Market Data Provider Interface for TradePilot NSE.
Supports:
1. YahooFinanceProvider (Free EOD & delayed NSE data via `yfinance` for `.NS` tickers)
2. NSECSVImportProvider (Local NSE Bhavcopy / OHLCV CSV folder ingestion when offline)
3. PaidBrokerAPIStub (Extensible interface ready for Zerodha Kite Connect / Upstox / AngelOne SmartAPI)

Strictly adheres to zero-fabrication rules: never invents prices or fundamental metrics in production.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from config import MARKET_DATA_CONFIG, DATA_DIR
from data.database import DatabaseManager
from data.stock_universe import INDEX_UNIVERSE
from utils.logging_config import get_logger
from utils.helpers import now_ist

logger = get_logger("market_data")


class BaseMarketDataProvider(ABC):
    """Abstract interface for replaceable NSE market data providers."""

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, yahoo_symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        pass

    @abstractmethod
    def fetch_fundamentals(self, symbol: str, yahoo_symbol: str) -> Dict[str, Any]:
        pass


class YahooFinanceProvider(BaseMarketDataProvider):
    """
    Retrieves NSE stock OHLCV and fundamental metrics via Yahoo Finance (`yfinance`).
    Note: Yahoo Finance free data for NSE (.NS) is End-of-Day / delayed by ~15 mins during market hours
    and may lack promoter pledging metrics (which are gracefully marked as None/Unavailable).
    """

    def fetch_ohlcv(self, symbol: str, yahoo_symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        try:
            import yfinance as yf

            ticker = yf.Ticker(yahoo_symbol)
            df = ticker.history(start=start_date, end=end_date, interval="1d", auto_adjust=False)
            if df is None or df.empty:
                logger.warning(f"YahooFinance returned empty OHLCV for {yahoo_symbol}")
                return pd.DataFrame()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            df.index = pd.to_datetime(df.index).tz_localize(None)
            required_cols = ["Open", "High", "Low", "Close", "Volume"]
            for col in required_cols:
                if col not in df.columns:
                    return pd.DataFrame()
            if "Adj Close" not in df.columns:
                df["Adj Close"] = df["Close"]
            return df[["Open", "High", "Low", "Close", "Adj Close", "Volume"]].dropna(subset=["Close"])
        except Exception as exc:
            logger.error(f"Error fetching OHLCV for {yahoo_symbol}: {exc}")
            return pd.DataFrame()

    def fetch_fundamentals(self, symbol: str, yahoo_symbol: str) -> Dict[str, Any]:
        try:
            import yfinance as yf

            info = yf.Ticker(yahoo_symbol).info or {}
            if not info:
                return {}

            def safe_pct(val: Any) -> Optional[float]:
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    return None
                try:
                    return float(val) * 100.0
                except (ValueError, TypeError):
                    return None

            def safe_float(val: Any) -> Optional[float]:
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    return None
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return None

            mcap = safe_float(info.get("marketCap"))
            mcap_cr = (mcap / 1e7) if mcap else None

            # Debt-to-equity in yfinance is often reported as a percentage (e.g. 45.0 for 0.45x)
            raw_de = safe_float(info.get("debtToEquity"))
            de_ratio = (raw_de / 100.0) if (raw_de is not None and raw_de > 5.0) else raw_de

            return {
                "symbol": symbol,
                "revenue_growth_pct": safe_pct(info.get("revenueGrowth")),
                "profit_growth_pct": safe_pct(info.get("earningsGrowth")),
                "eps_growth_pct": safe_pct(info.get("earningsQuarterlyGrowth")),
                "roe_pct": safe_pct(info.get("returnOnEquity")),
                "roce_pct": safe_pct(info.get("returnOnAssets")),  # Proxy when ROCE not directly exposed in free feed
                "debt_to_equity": de_ratio,
                "current_ratio": safe_float(info.get("currentRatio")),
                "operating_margin_pct": safe_pct(info.get("operatingMargins")),
                "net_margin_pct": safe_pct(info.get("profitMargins")),
                "pe_ratio": safe_float(info.get("trailingPE") or info.get("forwardPE")),
                "pb_ratio": safe_float(info.get("priceToBook")),
                "promoter_holding_pct": safe_pct(info.get("heldPercentInsiders")),
                "promoter_pledging_pct": None,  # Not provided by free Yahoo feed; requires NSE corporate filing CSV
                "institutional_holding_pct": safe_pct(info.get("heldPercentInstitutions")),
                "market_cap_cr": mcap_cr,
            }
        except Exception as exc:
            logger.error(f"Error fetching fundamentals for {yahoo_symbol}: {exc}")
            return {}


class LocalCSVProvider(BaseMarketDataProvider):
    """
    Reads local CSV OHLCV files from `data_store/csv_import/<SYMBOL>.csv` for offline or NSE Bhavcopy imports.
    """

    def __init__(self, csv_dir: Path = DATA_DIR / "csv_import"):
        self.csv_dir = Path(csv_dir)
        self.csv_dir.mkdir(parents=True, exist_ok=True)

    def fetch_ohlcv(self, symbol: str, yahoo_symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        csv_file = self.csv_dir / f"{symbol}.csv"
        if not csv_file.exists():
            return pd.DataFrame()
        try:
            df = pd.read_csv(csv_file)
            date_col = next((c for c in df.columns if c.lower() in ("date", "trade_date", "timestamp")), None)
            if not date_col:
                return pd.DataFrame()
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.set_index(date_col).sort_index()
            col_map = {c.lower(): c for c in df.columns}
            out = pd.DataFrame(index=df.index)
            for target in ["Open", "High", "Low", "Close", "Volume"]:
                src = col_map.get(target.lower())
                if src:
                    out[target] = pd.to_numeric(df[src], errors="coerce")
            out["Adj Close"] = out["Close"]
            return out.dropna(subset=["Close"])
        except Exception as exc:
            logger.error(f"Error reading CSV for {symbol}: {exc}")
            return pd.DataFrame()

    def fetch_fundamentals(self, symbol: str, yahoo_symbol: str) -> Dict[str, Any]:
        return {}


class PaidBrokerAPIProvider(BaseMarketDataProvider):
    """
    Adapter template for Paid Indian Broker / Market Data APIs (Zerodha Kite Connect, Upstox v2, TrueData).
    """

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def fetch_ohlcv(self, symbol: str, yahoo_symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(
            "PaidBrokerAPIProvider requires active API credentials in .env (TRADEPILOT_API_KEY) and broker SDK token."
        )

    def fetch_fundamentals(self, symbol: str, yahoo_symbol: str) -> Dict[str, Any]:
        return {}


class MarketDataService:
    """
    Coordinates incremental updates, caching in SQLite, rate-limit protection, and automatic after-close checks.
    """

    def __init__(self, db: DatabaseManager, provider: Optional[BaseMarketDataProvider] = None):
        self.db = db
        if provider is not None:
            self.provider = provider
        elif MARKET_DATA_CONFIG.provider == "local_csv":
            self.provider = LocalCSVProvider()
        else:
            self.provider = YahooFinanceProvider()

    def is_refresh_needed(self, symbol: str) -> bool:
        """
        Avoids redundant API calls if today's EOD data (or Friday's data on weekends) is already cached.
        """
        last_date_str = self.db.get_latest_trade_date(symbol)
        if not last_date_str:
            return True
        last_dt = pd.to_datetime(last_date_str).date()
        now = now_ist()
        today = now.date()

        # Determine most recent completed NSE trading day
        target_eod = today
        if today.weekday() == 5:  # Saturday
            target_eod = today - timedelta(days=1)
        elif today.weekday() == 6:  # Sunday
            target_eod = today - timedelta(days=2)
        elif now.hour < MARKET_DATA_CONFIG.market_close_hour_ist or (
            now.hour == MARKET_DATA_CONFIG.market_close_hour_ist and now.minute < MARKET_DATA_CONFIG.market_close_minute_ist
        ):
            # Before 15:45 IST, previous business day is the latest completed EOD bar
            prev_day = today - timedelta(days=1)
            if prev_day.weekday() == 5:
                prev_day -= timedelta(days=1)
            elif prev_day.weekday() == 6:
                prev_day -= timedelta(days=2)
            target_eod = prev_day

        return last_dt < target_eod

    def refresh_stock_universe(
        self, force: bool = False, fetch_fundamentals: bool = True, progress_callback=None
    ) -> Dict[str, Any]:
        stocks = self.db.get_active_stocks()
        started_at = now_ist().isoformat()
        succeeded = 0
        failed = 0
        skipped = 0
        errors: List[str] = []

        end_dt = (now_ist().date() + timedelta(days=1)).strftime("%Y-%m-%d")
        default_start_dt = (
            now_ist().date() - timedelta(days=365 * MARKET_DATA_CONFIG.default_history_years + 30)
        ).strftime("%Y-%m-%d")

        # Also include Nifty 50 and Nifty Bank index symbols for benchmark & regime analysis
        all_items = stocks + [
            {"symbol": idx["symbol"], "yahoo_symbol": idx["Yahoo_Symbol"], "is_index": True}
            for idx in INDEX_UNIVERSE
        ]
        total = len(all_items)

        for i, item in enumerate(all_items):
            sym = item["symbol"]
            ysym = item["yahoo_symbol"]
            if progress_callback:
                progress_callback(i + 1, total, sym)

            if not force and not self.is_refresh_needed(sym):
                skipped += 1
                succeeded += 1
                continue

            last_dt = self.db.get_latest_trade_date(sym)
            if last_dt and not force:
                # Fetch small overlap window to accurately compute prev_close and adjust for splits
                start_dt = (pd.to_datetime(last_dt).date() - timedelta(days=7)).strftime("%Y-%m-%d")
            else:
                start_dt = default_start_dt

            df = self.provider.fetch_ohlcv(sym, ysym, start_dt, end_dt)
            if not df.empty:
                self.db.save_historical_prices(sym, df, source=MARKET_DATA_CONFIG.provider)
                succeeded += 1
            else:
                failed += 1
                errors.append(sym)

            if fetch_fundamentals and not item.get("is_index", False):
                fund_raw = self.provider.fetch_fundamentals(sym, ysym)
                if fund_raw:
                    from analysis.fundamental import evaluate_fundamentals

                    evaluated = evaluate_fundamentals(sym, fund_raw)
                    self.db.save_fundamental_data(evaluated)

        completed_at = now_ist().isoformat()
        status = "SUCCESS" if failed == 0 else ("PARTIAL" if succeeded > 0 else "FAILED")
        details = f"Updated: {succeeded - skipped}, Cached/Skipped: {skipped}, Failed: {failed}"
        if errors:
            details += f" | Failed symbols: {', '.join(errors[:10])}"

        self.db.log_data_update(
            started_at=started_at,
            completed_at=completed_at,
            update_type="MANUAL_FORCE" if force else "INCREMENTAL_EOD",
            provider=MARKET_DATA_CONFIG.provider,
            requested=total,
            succeeded=succeeded,
            failed=failed,
            status=status,
            details=details,
        )

        return {
            "status": status,
            "requested": total,
            "succeeded": succeeded,
            "skipped": skipped,
            "failed": failed,
            "details": details,
            "completed_at": completed_at,
        }
