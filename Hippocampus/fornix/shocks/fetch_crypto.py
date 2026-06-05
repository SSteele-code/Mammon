"""
Hippocampus/Fornix/Shocks: Fetch Crypto
Downloads 5 years of 1-minute OHLCV from Alpaca for the 16 target crypto symbols,
cleans the data, and injects it into DuckPond market_tape.

Requires: alpaca-py  (pip install alpaca-py)
Auth:     ALPACA_API_KEY and ALPACA_API_SECRET environment variables
          (or a .env file in repo root — dotenv loaded automatically if present)

Run order:
    python fetch_crypto.py --check          # verify all 16 symbols exist on Alpaca
    python fetch_crypto.py --fetch          # download all symbols to crypto/raw/
    python fetch_crypto.py --fetch --id ETH/USD   # single symbol
    python fetch_crypto.py --inject         # clean + inject all to market_tape
    python fetch_crypto.py --verify         # row counts per symbol in market_tape
    python fetch_crypto.py --all            # full pipeline: fetch + inject

Target: ~2.5M bars total (16 symbols × ~5yr × ~31k bars/yr ≈ 2.5M)
        = 25% of the 10M DuckPond bar cap.
"""

import logging
logger = logging.getLogger(__name__)
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CRYPTO_SYMBOLS = [
    "ETH/USD",    # Layer 1 — essential, second most liquid
    "SOL/USD",    # Layer 1 — high momentum, distinct cycles
    "AVAX/USD",   # Layer 1 — volatile, strong regime swings
    "NEAR/USD",   # Layer 1 — sharding narrative, distinct character
    "ALGO/USD",   # Layer 1 — pure PoS, different rhythm
    "BCH/USD",    # Payments — OG fork, separate cycle from BTC
    "LINK/USD",   # DeFi / Oracle — news-driven spikes
    "AAVE/USD",   # DeFi — protocol-driven vol
    "UNI/USD",    # DeFi / DEX — governance event vol
    "TRX/USD",    # Payments — high vol, independent pattern
    "LTC/USD",    # Payments / OG — older coin, different rhythm
    "DOGE/USD",   # Meme — pure volatility, teaches chaos
    "MATIC/USD",  # Layer 2 — scaling narrative cycles
    "MKR/USD",    # DeFi — governance-driven, low BTC corr
    "GRT/USD",    # Infrastructure — indexing protocol
    "BAT/USD",    # Utility — browser/ad market, quiet mover
]

FETCH_START = "2020-01-01"               # 5 years back from launch
FETCH_END = datetime.now(timezone.utc).strftime("%Y-%m-%d")

HERE = Path(__file__).parent
CRYPTO_RAW_DIR = HERE / "crypto" / "raw"
CRYPTO_RAW_DIR.mkdir(parents=True, exist_ok=True)

DUCK_DB_PATH = Path(__file__).parents[3] / "Hospital" / "Memory_care" / "duck.db"

# Gap threshold: contiguous missing bars above this → drop the whole gap
GAP_DROP_THRESHOLD = 10
# Rolling window for volume fill
VOL_FILL_WINDOW = 30


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _load_env() -> tuple[str, str]:
    """Load ALPACA_API_KEY / ALPACA_API_SECRET from env or .env file."""
    try:
        from dotenv import load_dotenv
        repo_root = Path(__file__).parents[3]
        env_file = repo_root / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            log.info("Loaded .env from %s", env_file)
    except ImportError:
        pass  # dotenv optional

    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_API_SECRET", "")
    if not key or not secret:
        raise EnvironmentError(
            "ALPACA_API_KEY and ALPACA_API_SECRET must be set in environment or .env file."
        )
    return key, secret


def _get_client():
    """Return an authenticated Alpaca CryptoHistoricalDataClient."""
    from alpaca.data.historical import CryptoHistoricalDataClient
    key, secret = _load_env()
    return CryptoHistoricalDataClient(key, secret)


# ---------------------------------------------------------------------------
# Symbol availability check
# ---------------------------------------------------------------------------

def check_symbols() -> dict[str, bool]:
    """
    Ping Alpaca for 1 bar of each symbol to verify availability.
    Returns dict of symbol → available.
    """
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = _get_client()
    results = {}
    log.info("Checking %d symbols on Alpaca...", len(CRYPTO_SYMBOLS))

    for sym in CRYPTO_SYMBOLS:
        try:
            req = CryptoBarsRequest(
                symbol_or_symbols=sym,
                timeframe=TimeFrame.Minute,
                start="2023-01-01",
                end="2023-01-02",
                limit=5,
            )
            bars = client.get_crypto_bars(req)
            df = bars.df
            available = not df.empty
        except Exception as exc:
            log.warning("  %s — ERROR: %s", sym, exc)
            available = False

        status = "OK" if available else "UNAVAILABLE"
        log.info("  %s  →  %s", sym, status)
        results[sym] = available
        time.sleep(0.2)

    ok = sum(results.values())
    log.info("Available: %d/%d", ok, len(CRYPTO_SYMBOLS))
    unavailable = [s for s, v in results.items() if not v]
    if unavailable:
        log.warning("Unavailable symbols: %s", unavailable)
    return results


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def _symbol_to_filename(symbol: str) -> str:
    """ETH/USD → ETH_USD"""
    return symbol.replace("/", "_")


def fetch_one(symbol: str, start: str = FETCH_START, end: str = FETCH_END) -> Path:
    """
    Download 1-minute bars for one symbol from Alpaca.
    Saves to crypto/raw/<SYMBOL>.csv.
    Alpaca returns data in pages — we handle pagination automatically.
    """
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame

    fname = _symbol_to_filename(symbol)
    out_path = CRYPTO_RAW_DIR / f"{fname}.csv"

    if out_path.exists() and out_path.stat().st_size > 10_000:
        log.info("[SKIP] %s — already downloaded (%s)", symbol, out_path.name)
        return out_path

    log.info("[FETCH] %s  %s → %s", symbol, start, end)
    client = _get_client()

    req = CryptoBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
    )

    bars = client.get_crypto_bars(req)
    df = bars.df

    if df.empty:
        log.warning("[EMPTY] %s — no data returned", symbol)
        return out_path

    # Flatten multi-index if present (alpaca-py returns (symbol, timestamp) index)
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol") if symbol in df.index.get_level_values("symbol") else df.droplevel(0)

    df.index.name = "ts"
    df = df.rename(columns={
        "open": "open", "high": "high", "low": "low", "close": "close",
        "volume": "volume", "trade_count": "trade_count", "vwap": "vwap",
    })

    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep]
    df["symbol"] = symbol

    df.to_csv(out_path)
    log.info("  Saved %d bars → %s", len(df), out_path.name)
    return out_path


def fetch_all(symbols: list[str] = None, force: bool = False) -> dict[str, Path]:
    """Fetch all symbols. Returns dict of symbol → path."""
    if symbols is None:
        symbols = CRYPTO_SYMBOLS

    if force:
        log.info("Force mode — clearing raw crypto data")
        for f in CRYPTO_RAW_DIR.glob("*.csv"):
            f.unlink()

    results = {}
    for sym in symbols:
        try:
            path = fetch_one(sym)
            results[sym] = path
        except Exception as exc:
            log.error("[ERROR] %s: %s", sym, exc, exc_info=True)
            results[sym] = None
        time.sleep(0.3)  # polite rate limiting

    ok = sum(1 for p in results.values() if p and p.exists())
    log.info("Fetch complete — %d/%d symbols", ok, len(symbols))
    return results


# ---------------------------------------------------------------------------
# Data cleaning
# ---------------------------------------------------------------------------

def clean_one(symbol: str) -> pd.DataFrame:
    """
    Load raw CSV, apply all cleaning rules from PLAN.md:
    1. Drop contiguous gap periods (>GAP_DROP_THRESHOLD missing bars)
    2. Forward-fill isolated gaps (1-2 bar gaps): carry last close as OHLC
    3. Volume fill: rolling 30-bar mean for zero/missing volume bars
    4. Deduplicate on ts
    5. Sort ascending by ts
    6. Validate: open > 0, high >= open, low <= open, close > 0, volume >= 0
    """
    fname = _symbol_to_filename(symbol)
    raw_path = CRYPTO_RAW_DIR / f"{fname}.csv"

    if not raw_path.exists() or raw_path.stat().st_size < 100:
        log.warning("[SKIP] %s — raw CSV missing", symbol)
        return pd.DataFrame()

    df = pd.read_csv(raw_path, index_col="ts", parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()

    if "symbol" not in df.columns:
        df["symbol"] = symbol
    else:
        df["symbol"] = symbol  # normalise in case of mismatches

    original_len = len(df)

    # --- Step 4: deduplicate ---
    df = df[~df.index.duplicated(keep="first")]

    # --- Step 5: sort (already done above) ---

    # --- Identify gaps: build a complete 1-minute index over the range ---
    full_idx = pd.date_range(df.index.min(), df.index.max(), freq="1min", tz="UTC")
    df = df.reindex(full_idx)
    df.index.name = "ts"

    # --- Step 1: drop large contiguous gaps ---
    is_missing = df["close"].isna()
    # Label consecutive missing runs
    gap_group = (is_missing != is_missing.shift()).cumsum()
    gap_sizes = is_missing.groupby(gap_group).transform("sum")
    large_gaps = is_missing & (gap_sizes > GAP_DROP_THRESHOLD)
    df = df[~large_gaps]

    # --- Step 2: forward-fill isolated small gaps (1-2 bars) ---
    # After dropping large gaps, remaining NaNs are short gaps → ffill
    ohlc_cols = ["open", "high", "low", "close"]
    df[ohlc_cols] = df[ohlc_cols].ffill(limit=2)

    # For isolated gaps filled with ffill, OHLC = previous close (flat bar)
    # This is already handled by the ffill above.

    # --- Step 3: volume fill ---
    if "volume" in df.columns:
        rolling_vol = df["volume"].rolling(VOL_FILL_WINDOW, min_periods=1).mean()
        df["volume"] = df["volume"].where(df["volume"] > 0, rolling_vol)
        df["volume"] = df["volume"].fillna(0.0)
    else:
        df["volume"] = 0.0

    # --- Drop rows still missing OHLC after ffill (at the very start) ---
    df = df.dropna(subset=ohlc_cols)

    # --- Step 6: validate ---
    before_validate = len(df)
    df = df[df["close"] > 0]
    df = df[df["open"] > 0]
    df = df[df["high"] >= df[["open", "close"]].max(axis=1) * 0.999]
    df = df[df["low"] <= df[["open", "close"]].min(axis=1) * 1.001]
    df = df[df["volume"] >= 0]

    # Clamp high/low to valid range (floating point edge cases from validation above)
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)

    dropped = original_len - len(df)
    if dropped > 0:
        log.info("  %s — cleaned: %d → %d bars (dropped %d)", symbol, original_len, len(df), dropped)
    else:
        log.info("  %s — clean: %d bars", symbol, len(df))

    # Reset ts to column for DuckPond insertion
    df = df.reset_index().rename(columns={"index": "ts"})
    df["ts"] = df["ts"].dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    return df[["ts", "symbol", "open", "high", "low", "close", "volume"]]


# ---------------------------------------------------------------------------
# Inject into DuckPond
# ---------------------------------------------------------------------------

def _get_duck_conn():
    import duckdb
    if not DUCK_DB_PATH.exists():
        raise FileNotFoundError(f"DuckDB not found: {DUCK_DB_PATH}")
    return duckdb.connect(str(DUCK_DB_PATH))


def inject_one_crypto(symbol: str, conn=None, force: bool = False) -> int:
    """Clean and inject one crypto symbol into market_tape."""
    close_after = conn is None
    if conn is None:
        conn = _get_duck_conn()

    try:
        existing = conn.execute(
            "SELECT COUNT(*) FROM market_tape WHERE symbol = ?", [symbol]
        ).fetchone()[0]

        if existing > 0 and not force:
            log.info("[SKIP] %s — %d rows already in market_tape", symbol, existing)
            return 0

        if existing > 0 and force:
            conn.execute("DELETE FROM market_tape WHERE symbol = ?", [symbol])
            log.info("  Wiped %d rows for %s", existing, symbol)

        df = clean_one(symbol)
        if df.empty:
            log.warning("[SKIP] %s — cleaning produced no data", symbol)
            return 0

        # Add shock-specific columns with neutral defaults (market_tape may have them)
        try:
            cols_in_table = {
                row[0].lower()
                for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'market_tape'"
                ).fetchall()
            }
            if "bid_ask_bps" in cols_in_table:
                df["bid_ask_bps"] = 3.0
            if "spread_regime" in cols_in_table:
                df["spread_regime"] = "NORMAL"
            if "source_shock_id" in cols_in_table:
                df["source_shock_id"] = None
        except Exception:
            pass  # columns may not exist yet — inject_shocks.py adds them

        # Save to temp parquet and INSERT BY NAME — handles column count mismatches cleanly
        import tempfile, os as _os
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            tmp = f.name
        try:
            df.to_parquet(tmp, index=False)
            conn.execute(f"INSERT INTO market_tape BY NAME SELECT * FROM read_parquet('{tmp}')")
        finally:
            _os.unlink(tmp)

        log.info("[OK] %s — inserted %d bars", symbol, len(df))
        return len(df)

    finally:
        if close_after:
            conn.close()


def inject_all_crypto(symbols: list[str] = None, force: bool = False) -> dict[str, int]:
    """Clean and inject all 16 crypto symbols."""
    if symbols is None:
        symbols = CRYPTO_SYMBOLS

    conn = _get_duck_conn()
    results = {}
    try:
        for sym in symbols:
            try:
                n = inject_one_crypto(sym, conn=conn, force=force)
                results[sym] = n
            except Exception as exc:
                log.error("[ERROR] %s: %s", sym, exc, exc_info=True)
                results[sym] = -1
    finally:
        conn.close()

    total = sum(n for n in results.values() if n > 0)
    ok = sum(1 for n in results.values() if n > 0)
    log.info("Inject complete — %d/%d symbols, %d total bars", ok, len(symbols), total)
    return results


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def verify_crypto() -> None:
    """Print row counts per crypto symbol in market_tape."""
    conn = _get_duck_conn()
    try:
        logger.info(f"\n{'Symbol':<15} {'Rows in market_tape':>20}  {'First bar':>22}  {'Last bar':>22}  Status")
        logger.info("-" * 95)
        total = 0
        for sym in CRYPTO_SYMBOLS:
            row = conn.execute(
                "SELECT COUNT(*), MIN(ts), MAX(ts) FROM market_tape WHERE symbol = ?", [sym]
            ).fetchone()
            count, first, last = row
            status = "OK" if count > 100_000 else ("PARTIAL" if count > 0 else "MISSING")
            logger.info(f"{sym:<15} {count:>20}  {str(first or ''):>22}  {str(last or ''):>22}  {status}")
            total += count
        logger.info(f"\nTotal real crypto bars in market_tape: {total:,}")
        print()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch and inject Alpaca crypto data into DuckPond")
    parser.add_argument("--check", action="store_true", help="Verify all 16 symbols are available on Alpaca")
    parser.add_argument("--fetch", action="store_true", help="Download raw 1-min bars from Alpaca")
    parser.add_argument("--inject", action="store_true", help="Clean raw CSVs and inject into market_tape")
    parser.add_argument("--verify", action="store_true", help="Print market_tape row counts and exit")
    parser.add_argument("--all", action="store_true", help="Full pipeline: fetch + inject")
    parser.add_argument("--force", action="store_true", help="Re-download / re-inject even if data exists")
    parser.add_argument("--id", metavar="SYMBOL", help="Process a single symbol (e.g. ETH/USD)")
    args = parser.parse_args()

    target = [args.id] if args.id else CRYPTO_SYMBOLS

    if args.check:
        check_symbols()

    elif args.verify:
        verify_crypto()

    elif args.fetch or args.all:
        fetch_all(symbols=target, force=args.force)
        if args.all:
            inject_all_crypto(symbols=target, force=args.force)

    elif args.inject:
        inject_all_crypto(symbols=target, force=args.force)

    else:
        parser.print_help()
