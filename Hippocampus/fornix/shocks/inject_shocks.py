"""
Hippocampus/Fornix/Shocks: Inject Shocks
Reads normalized 1-minute CSVs and inserts them into DuckPond market_tape.

Each shock symbol (SHOCK_1929_CRASH/USD, etc.) is treated as its own asset —
fully isolated from real crypto in the tape, cleanly separable at any time.

Usage:
    python inject_shocks.py                  # inject all (skip existing)
    python inject_shocks.py --force          # wipe and re-inject all
    python inject_shocks.py --id 2020_COVID  # inject a single shock
    python inject_shocks.py --verify         # check counts in market_tape
    python inject_shocks.py --wipe           # remove all SHOCK_* rows (dry-run safe reset)
"""

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
NORM_DIR = HERE / "normalized"

# DuckPond DB path
DUCK_DB_PATH = Path(__file__).parents[3] / "Hospital" / "Memory_care" / "duck.db"


# ---------------------------------------------------------------------------
# DuckPond connection
# ---------------------------------------------------------------------------

def _get_conn():
    """Open a DuckDB connection to duck.db."""
    import duckdb
    if not DUCK_DB_PATH.exists():
        raise FileNotFoundError(f"DuckDB not found: {DUCK_DB_PATH}")
    return duckdb.connect(str(DUCK_DB_PATH))


def _ensure_market_tape_columns(conn) -> None:
    """
    market_tape may not have the shock-specific columns (bid_ask_bps, spread_regime,
    source_shock_id). Add them if missing — DuckDB ALTER TABLE ADD COLUMN IF NOT EXISTS
    is safe to call repeatedly.
    """
    existing = {row[0].lower() for row in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'market_tape'"
    ).fetchall()}

    additions = {
        "bid_ask_bps": "DOUBLE DEFAULT 3.0",
        "spread_regime": "VARCHAR DEFAULT 'NORMAL'",
        "source_shock_id": "VARCHAR DEFAULT NULL",
    }
    for col, typedef in additions.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE market_tape ADD COLUMN {col} {typedef}")
            log.info("  Added column market_tape.%s", col)


# ---------------------------------------------------------------------------
# Inject one shock
# ---------------------------------------------------------------------------

def inject_one(shock, conn=None, force: bool = False) -> int:
    """
    Insert one shock's normalized 1-min bars into market_tape.
    Returns number of rows inserted.
    """
    norm_path = NORM_DIR / f"{shock.id}.csv"
    if not norm_path.exists() or norm_path.stat().st_size < 100:
        log.warning("[SKIP] %s — normalized CSV missing or empty (run normalize_shocks.py first)", shock.id)
        return 0

    close_after = conn is None
    if conn is None:
        conn = _get_conn()

    try:
        _ensure_market_tape_columns(conn)

        symbol = shock.symbol

        # Check existing rows for this symbol
        existing_count = conn.execute(
            "SELECT COUNT(*) FROM market_tape WHERE symbol = ?", [symbol]
        ).fetchone()[0]

        if existing_count > 0 and not force:
            log.info("[SKIP] %s — %d rows already in market_tape (use --force to overwrite)",
                     shock.id, existing_count)
            return 0

        if existing_count > 0 and force:
            conn.execute("DELETE FROM market_tape WHERE symbol = ?", [symbol])
            log.info("  Wiped %d existing rows for %s", existing_count, symbol)

        # Load normalized CSV
        df = pd.read_csv(norm_path)
        if df.empty:
            log.warning("[SKIP] %s — normalized CSV is empty", shock.id)
            return 0

        # Ensure required columns present with defaults
        if "bid_ask_bps" not in df.columns:
            df["bid_ask_bps"] = 3.0
        if "spread_regime" not in df.columns:
            df["spread_regime"] = "NORMAL"
        if "source_shock_id" not in df.columns:
            df["source_shock_id"] = shock.id

        # Select and order columns to match market_tape insert
        insert_cols = ["ts", "symbol", "open", "high", "low", "close", "volume",
                       "bid_ask_bps", "spread_regime", "source_shock_id"]
        # Only include columns that exist in df
        insert_cols = [c for c in insert_cols if c in df.columns]
        df = df[insert_cols]

        # Save to temp parquet and INSERT BY NAME — handles column count mismatches cleanly
        import tempfile, os as _os
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            tmp = f.name
        try:
            df.to_parquet(tmp, index=False)
            conn.execute(f"INSERT INTO market_tape BY NAME SELECT * FROM read_parquet('{tmp}')")
        finally:
            _os.unlink(tmp)

        inserted = len(df)
        log.info("[OK] %s — inserted %d bars → market_tape (%s)",
                 shock.id, inserted, symbol)
        return inserted

    finally:
        if close_after:
            conn.close()


# ---------------------------------------------------------------------------
# Inject all
# ---------------------------------------------------------------------------

def inject_all(force: bool = False) -> dict[str, int]:
    """Inject all 20 shocks. Returns dict of shock_id → rows_inserted."""
    from shock_registry import get_all

    shocks = get_all()
    log.info("Injecting %d shocks into market_tape", len(shocks))

    conn = _get_conn()
    results = {}
    try:
        for shock in shocks:
            try:
                n = inject_one(shock, conn=conn, force=force)
                results[shock.id] = n
            except Exception as exc:
                log.error("[ERROR] %s: %s", shock.id, exc, exc_info=True)
                results[shock.id] = -1
    finally:
        conn.close()

    total = sum(n for n in results.values() if n > 0)
    ok = sum(1 for n in results.values() if n > 0)
    log.info("Done — %d/%d shocks injected, %d total bars", ok, len(results), total)
    return results


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def verify_injection() -> None:
    """Print a table of row counts per shock symbol in market_tape."""
    from shock_registry import get_all

    shocks = {s.id: s for s in get_all()}
    conn = _get_conn()
    try:
        print(f"\n{'ID':<20} {'Symbol':<30} {'Rows in market_tape':>20}  Status")
        print("-" * 90)
        total = 0
        for sid, shock in shocks.items():
            count = conn.execute(
                "SELECT COUNT(*) FROM market_tape WHERE symbol = ?", [shock.symbol]
            ).fetchone()[0]
            status = "OK" if count > 1000 else ("SPARSE" if count > 0 else "MISSING")
            print(f"{sid:<20} {shock.symbol:<30} {count:>20}  {status}")
            total += count
        print(f"\nTotal shock bars in market_tape: {total:,}")
        print()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Wipe
# ---------------------------------------------------------------------------

def wipe_all_shocks() -> int:
    """Remove all SHOCK_* rows from market_tape. Returns rows deleted."""
    conn = _get_conn()
    try:
        result = conn.execute(
            "DELETE FROM market_tape WHERE symbol LIKE 'SHOCK_%'"
        )
        deleted = result.fetchone()
        deleted_count = deleted[0] if deleted else 0
        log.info("Wiped %d shock rows from market_tape", deleted_count)
        return deleted_count
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inject normalized shock data into DuckPond market_tape")
    parser.add_argument("--force", action="store_true", help="Delete and re-inject existing shock rows")
    parser.add_argument("--verify", action="store_true", help="Print row counts per shock and exit")
    parser.add_argument("--wipe", action="store_true", help="Remove ALL SHOCK_* rows from market_tape")
    parser.add_argument("--id", metavar="SHOCK_ID", help="Inject a single shock by ID")
    args = parser.parse_args()

    if args.verify:
        verify_injection()
    elif args.wipe:
        confirm = input("Wipe ALL shock data from market_tape? [yes/no]: ").strip().lower()
        if confirm == "yes":
            wipe_all_shocks()
        else:
            print("Aborted.")
    elif args.id:
        from shock_registry import get_by_id
        inject_one(get_by_id(args.id), force=args.force)
    else:
        inject_all(force=args.force)
