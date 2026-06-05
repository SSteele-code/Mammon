"""
Hippocampus/Fornix/Shocks: Fetch Shocks
Downloads raw historical OHLCV data for every event in the shock registry.
Output: one CSV per shock in shocks/raw_data/<shock_id>.csv

Sources:
  - Yahoo Finance (yfinance) — S&P 500, Nasdaq, VIX, Shanghai Composite, post-1950 DJIA
  - Stooq (pandas_datareader) — DJIA pre-1950 (1929, 1937, 1942, 1949)
  - Shiller (CSV download) — fallback for very early DJIA if Stooq fails

Run from repo root:
    python -m Hippocampus.fornix.shocks.fetch_shocks
Or directly:
    python fetch_shocks.py
"""

import os
import sys
import time
import logging
logger = logging.getLogger(__name__)
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

# Allow direct execution (python fetch_shocks.py) as well as module execution
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).parent
RAW_DIR = HERE / "raw_data"
RAW_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Stooq tickers (used for pre-1950 DJIA — Yahoo doesn't have it)
# ---------------------------------------------------------------------------
STOOQ_TICKER_MAP = {
    "^DJI": "^DJI",   # pandas_datareader maps this to Stooq automatically
}

# Buffer: download this many extra days on each side so the window is fully covered
BUFFER_DAYS = 30


def _date_range(start: str, end: str) -> tuple[str, str]:
    """Expand start/end by BUFFER_DAYS."""
    s = datetime.strptime(start, "%Y-%m-%d") - timedelta(days=BUFFER_DAYS)
    e = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=BUFFER_DAYS)
    return s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")


def _fetch_yahoo(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Download daily OHLCV from Yahoo Finance via yfinance."""
    log.info("  yfinance  %s  %s → %s", ticker, start, end)
    df = yf.download(
        ticker,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=True,
        progress=False,
        actions=False,
    )
    if df.empty:
        raise ValueError(f"yfinance returned empty dataframe for {ticker} {start}→{end}")
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index.name = "Date"
    df.columns = ["open", "high", "low", "close", "volume"]
    df = df.dropna(subset=["open", "close"])
    df = df[df["close"] > 0]
    return df


_FRED_DJIA_CACHE = RAW_DIR / "_djia_fred.csv"
_FRED_UNAVAILABLE = False  # set to True after first failed download to skip retries


def _get_fred_djia_cached() -> pd.DataFrame:
    """
    Download the full FRED DJIA series (1896–present) once and cache locally.
    Subsequent calls load from the cached CSV instantly.
    """
    import requests
    from io import StringIO

    global _FRED_UNAVAILABLE
    if _FRED_UNAVAILABLE:
        raise ConnectionError("FRED previously failed — skipping to next fallback")

    if _FRED_DJIA_CACHE.exists() and _FRED_DJIA_CACHE.stat().st_size > 1000:
        log.info("  FRED      loading cached DJIA → %s", _FRED_DJIA_CACHE.name)
        df = pd.read_csv(_FRED_DJIA_CACHE, index_col="Date", parse_dates=True)
        return df

    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DJIA"
    log.info("  FRED      downloading full DJIA series (1896–present)...")
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception:
        _FRED_UNAVAILABLE = True
        raise

    df = pd.read_csv(StringIO(resp.text), parse_dates=["DATE"], index_col="DATE")
    df.index.name = "Date"
    df.columns = ["close"]
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna()

    # Synthesize OHLV from close-only (no intraday in FRED daily data)
    df["open"] = df["close"].shift(1).fillna(df["close"])
    df["high"] = df[["open", "close"]].max(axis=1)
    df["low"] = df[["open", "close"]].min(axis=1)
    df["volume"] = 0.0
    df = df[["open", "high", "low", "close", "volume"]]

    df.to_csv(_FRED_DJIA_CACHE)
    log.info("  FRED      saved %d rows → %s", len(df), _FRED_DJIA_CACHE.name)
    return df


def _fetch_fred_djia(start: str, end: str) -> pd.DataFrame:
    """Slice the cached FRED DJIA series to the requested window."""
    df = _get_fred_djia_cached()
    df.index = pd.to_datetime(df.index)
    sliced = df.loc[start:end].copy()
    if sliced.empty:
        raise ValueError(f"FRED DJIA cache has no data for {start}→{end}")
    log.info("  FRED      sliced %d rows  %s → %s", len(sliced), start, end)
    return sliced


def _needs_fred(ticker: str, start: str) -> bool:
    """Yahoo Finance doesn't have pre-1985 DJIA. Use FRED for all early ^DJI events."""
    year = int(start[:4])
    return ticker == "^DJI" and year < 1985


def _gspc_fallback(start: str, end: str) -> pd.DataFrame:
    """
    Use ^GSPC (S&P 500) as a stand-in when ^DJI is unavailable.
    Yahoo Finance has reconstructed ^GSPC data back to 1927.
    Regime shape is nearly identical to DJIA for pre-1985 periods.
    """
    log.info("  gspc_fallback  ^GSPC  %s → %s  (^DJI unavailable on Yahoo)", start, end)
    return _fetch_yahoo("^GSPC", start, end)


def fetch_one(shock) -> Path:
    """
    Fetch raw data for a single ShockEvent.
    Returns the path to the saved CSV.
    Skips if the file already exists and is non-empty.
    """
    out_path = RAW_DIR / f"{shock.id}.csv"

    if out_path.exists() and out_path.stat().st_size > 100:
        log.info("[SKIP] %s — already fetched (%s)", shock.id, out_path.name)
        return out_path

    log.info("[FETCH] %s (%s)", shock.id, shock.name)
    start, end = _date_range(shock.start, shock.end)

    df = None
    errors = []

    # --- Pre-1985 DJIA: Yahoo doesn't have it; try FRED then ^GSPC fallback ---
    if _needs_fred(shock.ticker, shock.start):
        try:
            df = _fetch_fred_djia(shock.start, shock.end)
        except Exception as exc:
            errors.append(f"fred: {exc}")
            log.warning("  FRED failed (%s) — falling back to ^GSPC", exc)
        if df is None or df.empty:
            try:
                df = _gspc_fallback(start, end)
            except Exception as exc:
                errors.append(f"gspc_fallback: {exc}")

    # --- Standard path: Yahoo primary, GSPC fallback ---
    else:
        try:
            df = _fetch_yahoo(shock.ticker, start, end)
        except Exception as exc:
            errors.append(f"yahoo: {exc}")
            log.warning("  Yahoo failed: %s", exc)

        if df is None or df.empty:
            try:
                df = _gspc_fallback(start, end)
            except Exception as exc:
                errors.append(f"gspc_fallback: {exc}")

    if df is None or df.empty:
        log.error("[FAIL] %s — all sources exhausted: %s", shock.id, errors)
        return out_path  # empty / missing — normalize_shocks will skip it

    # Trim to the actual event window (+ buffer is fine, normalizer clips to event window)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # Basic sanity check
    bad = df[(df["close"] <= 0) | (df["high"] < df["low"])]
    if not bad.empty:
        log.warning("  Dropping %d malformed rows", len(bad))
        df = df.drop(bad.index)

    df.to_csv(out_path)
    log.info("  Saved %d rows → %s", len(df), out_path.name)
    return out_path


def fetch_all(force: bool = False) -> dict[str, Path]:
    """
    Fetch all 20 shock events. Returns dict of shock_id → csv_path.
    Set force=True to re-download even if CSVs already exist.
    """
    from shock_registry import get_all

    if force:
        log.info("Force mode — re-downloading all shocks")
        for f in RAW_DIR.glob("*.csv"):
            f.unlink()

    results = {}
    shocks = get_all()
    log.info("Fetching %d shock events → %s", len(shocks), RAW_DIR)

    for shock in shocks:
        try:
            path = fetch_one(shock)
            results[shock.id] = path
        except Exception as exc:
            log.error("[ERROR] %s: %s", shock.id, exc)
            results[shock.id] = None
        # Polite pause between Yahoo requests to avoid rate-limiting
        time.sleep(0.5)

    # Summary
    ok = sum(1 for p in results.values() if p and p.exists() and p.stat().st_size > 100)
    fail = len(results) - ok
    log.info("Done — %d/%d fetched successfully, %d failed", ok, len(results), fail)
    if fail:
        failed_ids = [sid for sid, p in results.items() if not (p and p.exists() and p.stat().st_size > 100)]
        log.warning("Failed: %s", failed_ids)

    return results


def verify_raw() -> None:
    """Print a status table of all raw CSVs."""
    from shock_registry import get_all

    shocks = {s.id: s for s in get_all()}
    logger.info(f"\n{'ID':<20} {'Status':<8} {'Rows':>6}  {'Start':>12}  {'End':>12}  File")
    logger.info("-" * 85)
    for sid, shock in shocks.items():
        path = RAW_DIR / f"{sid}.csv"
        if not path.exists():
            logger.info(f"{sid:<20} {'MISSING':<8} {'':>6}  {'':>12}  {'':>12}")
            continue
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            start = df.index.min().strftime("%Y-%m-%d") if not df.empty else "?"
            end = df.index.max().strftime("%Y-%m-%d") if not df.empty else "?"
            status = "OK" if len(df) > 10 else "SPARSE"
            logger.info(f"{sid:<20} {status:<8} {len(df):>6}  {start:>12}  {end:>12}  {path.name}")
        except Exception as exc:
            logger.info(f"{sid:<20} {'ERROR':<8}  {exc}")
    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch shock event raw data")
    parser.add_argument("--force", action="store_true", help="Re-download even if CSVs exist")
    parser.add_argument("--verify", action="store_true", help="Print status table and exit")
    parser.add_argument("--id", metavar="SHOCK_ID", help="Fetch a single shock by ID")
    args = parser.parse_args()

    if args.verify:
        verify_raw()
    elif args.id:
        from shock_registry import get_by_id
        shock = get_by_id(args.id)
        fetch_one(shock)
    else:
        fetch_all(force=args.force)
