"""
Hippocampus/Fornix/Shocks: Normalize Shocks
Two-stage transform:
  1. Vol normalization — scale returns to match crypto vol profile
  2. Disaggregation — daily OHLCV → 1440 1-minute bars per day

Output: one CSV per shock in shocks/normalized/<shock_id>.csv
Each row is a 1-minute bar ready for DuckPond ingestion.

Column schema (matches market_tape):
  ts (UTC ISO), symbol, open, high, low, close, volume,
  bid_ask_bps, spread_regime, source_shock_id
"""

import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
RAW_DIR = HERE / "raw_data"
NORM_DIR = HERE / "normalized"
NORM_DIR.mkdir(exist_ok=True)

# Crypto vol target (annualised daily std of log-returns, ~80% annualised for BTC/mid-caps)
# We use a single representative target; inject_shocks can override per symbol.
CRYPTO_ANNUAL_VOL_TARGET = 0.80          # 80% annualised
TRADING_DAYS_PER_YEAR = 365              # crypto trades 365 days
CRYPTO_DAILY_VOL_TARGET = CRYPTO_ANNUAL_VOL_TARGET / np.sqrt(TRADING_DAYS_PER_YEAR)

MINUTES_PER_DAY = 1440                   # crypto = 24h


# ---------------------------------------------------------------------------
# Vol normalization
# ---------------------------------------------------------------------------

def _compute_scale_factor(df: pd.DataFrame) -> float:
    """
    scale = crypto_daily_vol_target / event_daily_vol
    Applied to log-returns before reconstructing prices.
    Capped to prevent degenerate scaling on very short or flat windows.
    """
    log_rets = np.log(df["close"] / df["close"].shift(1)).dropna()
    if len(log_rets) < 5:
        log.warning("  Too few bars to compute vol — using scale 1.0")
        return 1.0
    event_vol = log_rets.std()
    if event_vol < 1e-8:
        log.warning("  Event vol near-zero — using scale 1.0")
        return 1.0
    scale = CRYPTO_DAILY_VOL_TARGET / event_vol
    # Cap scale: don't let tiny vol events blow up to 20x crypto, nor massive events shrink to nothing
    scale = float(np.clip(scale, 0.05, 20.0))
    return scale


def _apply_vol_normalization(df: pd.DataFrame, scale: float) -> pd.DataFrame:
    """
    Scale log-returns, reconstruct price series anchored at the first close.
    OHLC proportions within each day are preserved.
    """
    df = df.copy().sort_index()
    close0 = df["close"].iloc[0]

    # Compute log-returns and scale
    log_rets = np.log(df["close"] / df["close"].shift(1)).fillna(0.0)
    scaled_log_rets = log_rets * scale

    # Reconstruct close series
    scaled_close = close0 * np.exp(scaled_log_rets.cumsum())

    # Scale OHLC proportionally: preserve the within-day shape
    ratio = scaled_close / df["close"]
    df["open"] = df["open"] * ratio
    df["high"] = df["high"] * ratio
    df["low"] = df["low"] * ratio
    df["close"] = scaled_close

    # Clamp: ensure OHLC sanity after scaling
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)

    return df


# ---------------------------------------------------------------------------
# Spread modeling
# ---------------------------------------------------------------------------

SPREAD_BPS = {
    "TIGHT":  (2.0, 4.0),
    "NORMAL": (4.0, 8.0),
    "WIDE":   (8.0, 20.0),
    "PANIC":  (15.0, 50.0),
}


def _spread_for_bar(spread_regime: str, bar_vol_z: float) -> float:
    """
    Spread in bps for a single bar.
    bar_vol_z: z-score of this bar's return magnitude relative to session mean.
    Higher vol bar → wider end of the regime range.
    """
    lo, hi = SPREAD_BPS[spread_regime]
    # Sigmoid blend: z_score 0 → lo, z_score 2+ → hi
    t = float(np.clip(bar_vol_z / 2.0, 0.0, 1.0))
    return lo + t * (hi - lo)


# ---------------------------------------------------------------------------
# Volume U-curve (intraday distribution)
# ---------------------------------------------------------------------------

def _volume_ucurve(n: int) -> np.ndarray:
    """
    Generate an intraday volume shape across n minutes.
    U-curve: higher at open/close, lower midday (standard market microstructure).
    Sums to 1.0.
    """
    t = np.linspace(0, 1, n)
    # U-curve via cosine: peaks at 0 and 1, trough at 0.5
    weights = 0.5 + 0.5 * np.cos(2 * np.pi * t - np.pi)
    # Small floor so no bar gets exactly zero volume
    weights = np.clip(weights, 0.05, None)
    return weights / weights.sum()


# ---------------------------------------------------------------------------
# Brownian bridge disaggregation
# ---------------------------------------------------------------------------

def _brownian_bridge(open_: float, close_: float, high_: float, low_: float,
                     n: int, rng: np.random.Generator) -> np.ndarray:
    """
    Generate n price points forming a Brownian bridge from open_ to close_,
    bounded within [low_, high_].

    Returns array of shape (n,) representing close prices of each 1-minute bar.
    """
    # Standard Brownian bridge: W(t) = t * W(1) + (W(t) - t * W(1))
    increments = rng.standard_normal(n)
    bridge = np.cumsum(increments)
    # Normalize so bridge[0]=0 and bridge[-1] = (close - open)
    if bridge[-1] != 0:
        bridge = bridge / bridge[-1] * (close_ - open_)
    bridge = bridge + open_

    # Clip to [low, high] bounds
    bridge = np.clip(bridge, low_, high_)

    # Nudge endpoints to exact open/close
    bridge[0] = open_
    bridge[-1] = close_

    return bridge


def _disaggregate_day(row: pd.Series, shock, rng: np.random.Generator,
                      session_mean_abs_ret: float, session_std_abs_ret: float
                      ) -> list[dict]:
    """
    Disaggregate one daily OHLCV bar into MINUTES_PER_DAY 1-minute bars.
    Returns list of dicts (one per minute bar).
    """
    date = row.name
    open_ = float(row["open"])
    high_ = float(row["high"])
    low_ = float(row["low"])
    close_ = float(row["close"])
    daily_vol = float(row.get("volume", 0))

    # Build intraday close path via Brownian bridge
    closes = _brownian_bridge(open_, close_, high_, low_, MINUTES_PER_DAY, rng)

    # OHLC per minute bar
    opens = np.empty(MINUTES_PER_DAY)
    opens[0] = open_
    opens[1:] = closes[:-1]

    # Per-bar vol z-score (for spread modeling)
    bar_abs_rets = np.abs(closes - opens)
    if session_std_abs_ret > 1e-12:
        bar_vol_z = (bar_abs_rets - session_mean_abs_ret) / session_std_abs_ret
    else:
        bar_vol_z = np.zeros(MINUTES_PER_DAY)

    # Volume distribution
    vol_weights = _volume_ucurve(MINUTES_PER_DAY)
    vol_multiplier = shock.volume_multiplier
    bar_volumes = vol_weights * daily_vol * vol_multiplier
    # If daily_vol is 0 (old data often has 0 volume), synthesize a flat base
    if daily_vol <= 0:
        bar_volumes = np.full(MINUTES_PER_DAY, 1000.0) * vol_weights * vol_multiplier

    # Build per-minute records
    bars = []
    for i in range(MINUTES_PER_DAY):
        minute_ts = pd.Timestamp(date, tz="UTC") + pd.Timedelta(minutes=i)
        o = float(opens[i])
        c = float(closes[i])
        h = max(o, c) * rng.uniform(1.0, 1.0 + (high_ - low_) / max(high_, 1e-8) * 0.5)
        l = min(o, c) * rng.uniform(1.0 - (high_ - low_) / max(high_, 1e-8) * 0.5, 1.0)
        h = float(np.clip(h, max(o, c), high_))
        l = float(np.clip(l, low_, min(o, c)))

        bps = _spread_for_bar(shock.spread_regime, float(bar_vol_z[i]))

        bars.append({
            "ts": minute_ts.isoformat(),
            "symbol": shock.symbol,
            "open": round(o, 8),
            "high": round(h, 8),
            "low": round(l, 8),
            "close": round(c, 8),
            "volume": round(float(bar_volumes[i]), 4),
            "bid_ask_bps": round(bps, 2),
            "spread_regime": shock.spread_regime,
            "source_shock_id": shock.id,
        })

    return bars


# ---------------------------------------------------------------------------
# Warm-up ramp
# ---------------------------------------------------------------------------

def _build_warmup_bars(first_bar: dict, n: int = 20) -> list[dict]:
    """
    Prepend n bars of flat/quiet price before the shock starts.
    Seeds ATR/ADX so indicators aren't cold on bar 1.
    Price = first bar's open. Vol = small noise.
    """
    first_ts = pd.Timestamp(first_bar["ts"])
    warmup = []
    price = first_bar["open"]
    for i in range(n, 0, -1):
        ts = first_ts - pd.Timedelta(minutes=i)
        warmup.append({
            "ts": ts.isoformat(),
            "symbol": first_bar["symbol"],
            "open": price,
            "high": price * 1.0001,
            "low": price * 0.9999,
            "close": price,
            "volume": first_bar["volume"] * 0.5,
            "bid_ask_bps": 3.0,
            "spread_regime": "NORMAL",
            "source_shock_id": first_bar["source_shock_id"],
        })
    return warmup


# ---------------------------------------------------------------------------
# Main normalize function
# ---------------------------------------------------------------------------

def normalize_one(shock, seed: int = 42) -> Path:
    """
    Full pipeline for one shock event:
      load raw CSV → vol normalize → disaggregate → save normalized CSV
    """
    out_path = NORM_DIR / f"{shock.id}.csv"
    raw_path = RAW_DIR / f"{shock.id}.csv"

    if not raw_path.exists() or raw_path.stat().st_size < 100:
        log.warning("[SKIP] %s — raw CSV missing or empty", shock.id)
        return out_path

    if out_path.exists() and out_path.stat().st_size > 100:
        log.info("[SKIP] %s — already normalized", shock.id)
        return out_path

    log.info("[NORM] %s (%s)", shock.id, shock.name)

    df = pd.read_csv(raw_path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)  # strip tz for comparison
    df = df.sort_index()
    df.columns = [c.lower() for c in df.columns]
    required = {"open", "high", "low", "close"}
    if not required.issubset(df.columns):
        log.error("[FAIL] %s — missing columns: %s", shock.id, required - set(df.columns))
        return out_path

    # Clip to event window (raw has buffer days)
    event_start = pd.Timestamp(shock.start)
    event_end = pd.Timestamp(shock.end)
    df = df.loc[event_start:event_end]
    if df.empty:
        log.error("[FAIL] %s — no data in event window %s→%s", shock.id, shock.start, shock.end)
        return out_path

    log.info("  Event window: %d daily bars (%s → %s)",
             len(df), df.index.min().date(), df.index.max().date())

    # Vol normalize
    scale = _compute_scale_factor(df)
    log.info("  Vol scale factor: %.4f  (event_vol → crypto_vol)", scale)
    df = _apply_vol_normalization(df, scale)

    # Disaggregate
    rng = np.random.default_rng(seed)
    # Pre-compute session-level bar vol stats for spread z-score
    # Use mean daily range as proxy
    daily_range = (df["high"] - df["low"]) / df["close"]
    session_mean = float(daily_range.mean() / MINUTES_PER_DAY)
    session_std = float(daily_range.std() / MINUTES_PER_DAY)

    all_bars = []
    for _, row in df.iterrows():
        bars = _disaggregate_day(row, shock, rng, session_mean, session_std)
        all_bars.extend(bars)

    if not all_bars:
        log.error("[FAIL] %s — disaggregation produced no bars", shock.id)
        return out_path

    # Prepend warm-up ramp
    warmup = _build_warmup_bars(all_bars[0])
    all_bars = warmup + all_bars

    out_df = pd.DataFrame(all_bars)
    out_df = out_df.sort_values("ts").reset_index(drop=True)

    out_df.to_csv(out_path, index=False)
    log.info("  Saved %d 1-min bars → %s", len(out_df), out_path.name)
    return out_path


def normalize_all(force: bool = False) -> dict[str, Path]:
    """Normalize all shocks. Returns dict of shock_id → csv_path."""
    from shock_registry import get_all

    if force:
        log.info("Force mode — clearing normalized output")
        for f in NORM_DIR.glob("*.csv"):
            f.unlink()

    results = {}
    shocks = get_all()
    log.info("Normalizing %d shocks → %s", len(shocks), NORM_DIR)

    for i, shock in enumerate(shocks):
        try:
            path = normalize_one(shock, seed=i * 137 + 42)
            results[shock.id] = path
        except Exception as exc:
            log.error("[ERROR] %s: %s", shock.id, exc, exc_info=True)
            results[shock.id] = None

    ok = sum(1 for p in results.values() if p and p.exists() and p.stat().st_size > 100)
    log.info("Done — %d/%d normalized", ok, len(results))
    return results


def verify_normalized() -> None:
    """Print a status table of normalized CSVs."""
    from shock_registry import get_all

    shocks = {s.id: s for s in get_all()}
    print(f"\n{'ID':<20} {'Status':<8} {'1-min bars':>10}  {'TS Start':>25}  {'TS End':>25}")
    print("-" * 100)
    for sid, shock in shocks.items():
        path = NORM_DIR / f"{sid}.csv"
        if not path.exists():
            print(f"{sid:<20} {'MISSING':<8}")
            continue
        try:
            df = pd.read_csv(path)
            start = df["ts"].min() if "ts" in df.columns else "?"
            end = df["ts"].max() if "ts" in df.columns else "?"
            status = "OK" if len(df) > 100 else "SPARSE"
            print(f"{sid:<20} {status:<8} {len(df):>10}  {str(start):>25}  {str(end):>25}")
        except Exception as exc:
            print(f"{sid:<20} {'ERROR':<8}  {exc}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Normalize shock event data")
    parser.add_argument("--force", action="store_true", help="Re-normalize even if output exists")
    parser.add_argument("--verify", action="store_true", help="Print status table and exit")
    parser.add_argument("--id", metavar="SHOCK_ID", help="Normalize a single shock by ID")
    args = parser.parse_args()

    if args.verify:
        verify_normalized()
    elif args.id:
        from shock_registry import get_by_id
        normalize_one(get_by_id(args.id), seed=42)
    else:
        normalize_all(force=args.force)
