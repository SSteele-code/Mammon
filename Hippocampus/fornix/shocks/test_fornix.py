"""
Hippocampus/Fornix/Shocks: Smoke Test
Validates the full Fornix replay pipeline using the two smallest shocks.
Run this before committing to a full overnight Fornix run.

Usage:
    python test_fornix.py              # smoke run (SMOKE_PULSE, 10% fidelity)
    python test_fornix.py --full       # TEST_PULSE_25 (25% fidelity)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))
sys.path.insert(0, str(Path(__file__).parent))

import duckdb

SMOKE_PULSE = {
    "monte_scale": 0.10,
    "paths_per_lane": 1000,
    "risk_gate_paths_per_lane": 33,
    "valuation_paths": 1000,
    "max_hours": 2,
    "checkpoint_interval": 100,
    "optimizer_interval_bars": 75,
    "chunk_size": 500,
}

# Two smallest shocks: 1 day (1,460 bars) and 5 days (7,220 bars)
TEST_SYMBOLS = [
    "SHOCK_2010_FLASH/USD",        # Flash Crash 2010 — 1,460 bars
    "SHOCK_2018_VOLMAGEDDON/USD",  # Volmageddon 2018 — 7,220 bars
]

DUCK_DB_PATH = Path(__file__).parents[3] / "Hospital" / "Memory_care" / "duck.db"


def _verify_symbols(symbols: list) -> list:
    """Return symbols actually present in market_tape with bars."""
    conn = duckdb.connect(str(DUCK_DB_PATH), read_only=True)
    try:
        found = []
        for sym in symbols:
            count = conn.execute(
                "SELECT COUNT(*) FROM market_tape WHERE symbol = ?", [sym]
            ).fetchone()[0]
            status = f"{count:,} bars" if count > 0 else "MISSING — run inject_shocks.py first"
            print(f"  {sym:<38} {status}")
            if count > 0:
                found.append(sym)
        return found
    finally:
        conn.close()


def run_smoke_test(use_full: bool = False) -> bool:
    print("\n" + "=" * 60)
    print("FORNIX SMOKE TEST")
    print("=" * 60)

    print("\nVerifying test symbols in market_tape:")
    available = _verify_symbols(TEST_SYMBOLS)

    if not available:
        print("\n[FAIL] No test symbols found in market_tape.")
        return False

    missing = [s for s in TEST_SYMBOLS if s not in available]
    if missing:
        print(f"\n[WARN] Missing symbols (will skip): {missing}")

    from Hippocampus.fornix.service import Fornix

    pulse = SMOKE_PULSE if not use_full else None  # None → Fornix uses TEST_PULSE_25
    fidelity = "TEST_PULSE_25 (25%)" if use_full else "SMOKE_PULSE (10%)"
    print(f"\nFidelity: {fidelity}")
    print(f"Symbols:  {available}")
    print()

    t0 = time.time()
    fornix = Fornix(test_pulse=pulse, headless=False)
    fornix.run(symbols=available, resume=False)
    elapsed = time.time() - t0

    passed = fornix.total_mints > 0

    print("\n" + "=" * 60)
    print(f"SMOKE TEST {'PASSED' if passed else 'FAILED'}")
    print(f"  Elapsed:  {elapsed:.1f}s ({elapsed/60:.1f}m)")
    print(f"  Bars:     {fornix.total_bars_processed:,}")
    print(f"  MINTs:    {fornix.total_mints:,}")
    print(f"  Signals:  {fornix.total_signals:,}")
    print(f"  Trades:   {fornix.total_trades:,}")
    if not passed:
        print("\n  FAIL: Zero MINTs generated.")
        print("        Check SmartGland → Orchestrator chain for errors above.")
    print("=" * 60 + "\n")

    return passed


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Fornix smoke test — validates full pipeline in ~minutes before a 6-hour overnight run"
    )
    parser.add_argument("--full", action="store_true",
                        help="Use TEST_PULSE_25 (25%%) fidelity instead of 10%%")
    args = parser.parse_args()

    ok = run_smoke_test(use_full=args.full)
    sys.exit(0 if ok else 1)
