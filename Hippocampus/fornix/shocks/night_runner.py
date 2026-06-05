"""
Hippocampus/Fornix/Shocks: Midnight Night Runner
Stops Mammon at midnight, runs Fornix on tonight's scheduled symbol pair, resumes trading.

Usage:
    python night_runner.py             # run tonight's next scheduled pair
    python night_runner.py --dry-run   # show tonight's symbols without running
    python night_runner.py --status    # print schedule and completion state
    python night_runner.py --night N   # force run a specific night (1-20)

Schedule: 20 nights — 1 crypto + 1 shock per night (nights 17-20: shock only).
State:     night_runner_state.json — tracks which nights are complete.
API:       Stops Mammon via /api/stop, resumes via /api/start with same mode.
SSE:       Posts fornix_start / fornix_complete events to /api/event so the
           dashboard stream shows Fornix progress alongside live trading.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parents[3] / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HERE = Path(__file__).parent
STATE_FILE = HERE / "night_runner_state.json"

MAMMON_HOST = os.environ.get("MAMMON_HOST", "http://localhost")
MAMMON_PORT = int(os.environ.get("MAMMON_DASHBOARD_PORT", 5000))
MAMMON_BASE = f"{MAMMON_HOST}:{MAMMON_PORT}"
MAMMON_TOKEN = os.environ.get("MAMMON_API_TOKEN", "dev-token")

# 50% fidelity, 6hr cap — fills the night without overrunning market open
NIGHT_PULSE = {
    "monte_scale": 0.50,
    "paths_per_lane": 5000,
    "risk_gate_paths_per_lane": 167,
    "valuation_paths": 5000,
    "max_hours": 6,
    "checkpoint_interval": 500,
    "optimizer_interval_bars": 75,
    "chunk_size": 500,
}

# 20-night schedule: (crypto_symbol_or_None, shock_symbol)
# Ordered smallest→largest to build confidence early and catch bugs with cheap runs first.
NIGHT_SCHEDULE = [
    # Nights 1-16: 1 crypto + 1 shock
    ("ETH/USD",   "SHOCK_2010_FLASH/USD"),       # Flash Crash: 1,460 bars
    ("SOL/USD",   "SHOCK_2018_VOLMAGEDDON/USD"),  # Volmageddon: 7,220 bars
    ("AVAX/USD",  "SHOCK_2020_COVID/USD"),
    ("NEAR/USD",  "SHOCK_2020_VRECOVERY/USD"),
    ("ALGO/USD",  "SHOCK_1987_BLACKMON/USD"),
    ("BCH/USD",   "SHOCK_1998_LTCM/USD"),
    ("LINK/USD",  "SHOCK_2001_911/USD"),
    ("AAVE/USD",  "SHOCK_2011_EUROCRISIS/USD"),
    ("UNI/USD",   "SHOCK_2008_CRISIS/USD"),
    ("TRX/USD",   "SHOCK_2015_CHINA/USD"),
    ("LTC/USD",   "SHOCK_2000_DOTCOM/USD"),
    ("DOGE/USD",  "SHOCK_1973_OILSHOCK/USD"),
    ("MATIC/USD", "SHOCK_1997_ASIAN/USD"),
    ("MKR/USD",   "SHOCK_2009_QE_BULL/USD"),
    ("GRT/USD",   "SHOCK_1995_DOTCOM_UP/USD"),
    ("BAT/USD",   "SHOCK_1962_KENNEDY/USD"),
    # Nights 17-20: shock only (all crypto already replayed)
    (None,        "SHOCK_1942_WW2BOOM/USD"),
    (None,        "SHOCK_1949_POSTWAR/USD"),
    (None,        "SHOCK_1937_DOUBLEDIP/USD"),
    (None,        "SHOCK_1929_CRASH/USD"),
]


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"completed_nights": [], "last_run": None}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _next_night(state: dict):
    completed = set(state.get("completed_nights", []))
    for i in range(1, len(NIGHT_SCHEDULE) + 1):
        if i not in completed:
            return i
    return None


# ---------------------------------------------------------------------------
# Mammon API
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {"Authorization": f"Bearer {MAMMON_TOKEN}"}


def _mammon_state() -> dict:
    try:
        import requests
        r = requests.get(f"{MAMMON_BASE}/api/state", headers=_headers(), timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("Mammon API unreachable: %s", e)
        return {}


def _mammon_stop() -> bool:
    """Stop Mammon. Returns True if stopped (or wasn't running)."""
    import requests
    st = _mammon_state()
    if not st.get("running"):
        log.info("Mammon not running — nothing to stop")
        return True

    log.info("Stopping Mammon trading...")
    try:
        r = requests.post(f"{MAMMON_BASE}/api/stop", headers=_headers(), timeout=10)
        r.raise_for_status()
    except Exception as e:
        log.error("Failed to stop Mammon: %s", e)
        return False

    for _ in range(30):
        time.sleep(1)
        st = _mammon_state()
        if not st.get("running"):
            log.info("Mammon stopped")
            return True

    log.error("Mammon did not stop within 30s")
    return False


def _sse_push(event_type: str, data: dict) -> None:
    """Fire-and-forget SSE event to the dashboard stream. Silently skips if unreachable."""
    import requests
    try:
        requests.post(
            f"{MAMMON_BASE}/api/event",
            headers=_headers(),
            json={"type": event_type, "data": data},
            timeout=3,
        )
    except Exception:
        pass  # Dashboard may not be running — don't let this block Fornix


def _mammon_start(mode: str, symbols: list) -> bool:
    """Resume Mammon trading."""
    import requests
    try:
        r = requests.post(
            f"{MAMMON_BASE}/api/start",
            headers=_headers(),
            json={"mode": mode, "symbols": symbols},
            timeout=10,
        )
        if r.status_code == 409:
            log.info("Mammon already running")
            return True
        r.raise_for_status()
        log.info("Mammon resumed — mode=%s symbols=%s", mode, symbols)
        return True
    except Exception as e:
        log.error("Failed to resume Mammon: %s", e)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_night(night_num: int, dry_run: bool = False) -> bool:
    idx = night_num - 1
    if not (0 <= idx < len(NIGHT_SCHEDULE)):
        log.error("Night %d out of range (1-%d)", night_num, len(NIGHT_SCHEDULE))
        return False

    crypto_sym, shock_sym = NIGHT_SCHEDULE[idx]
    symbols = [s for s in [crypto_sym, shock_sym] if s is not None]

    log.info("=== Night %d / %d ===", night_num, len(NIGHT_SCHEDULE))
    log.info("Symbols: %s", symbols)

    if dry_run:
        log.info("[DRY RUN] Would process: %s", symbols)
        return True

    # Capture current Mammon state before touching it
    prev = _mammon_state()
    was_running = prev.get("running", False)
    prev_mode = prev.get("mode", "DRY_RUN")
    prev_symbols = prev.get("symbols", ["BTC/USD"])

    if was_running:
        stopped = _mammon_stop()
        if not stopped:
            log.error("Cannot proceed — failed to stop Mammon")
            return False

    try:
        from Hippocampus.fornix.service import Fornix

        _sse_push("fornix_start", {
            "msg": f"Fornix night {night_num}/20 started",
            "night": night_num,
            "symbols": symbols,
        })
        log.info("Starting Fornix replay — %s", symbols)

        fornix = Fornix(test_pulse=NIGHT_PULSE, headless=False)
        fornix.run(symbols=symbols, resume=True)

        _sse_push("fornix_complete", {
            "msg": f"Fornix night {night_num}/20 complete",
            "night": night_num,
            "symbols": symbols,
            "bars": fornix.total_bars_processed,
            "mints": fornix.total_mints,
            "trades": fornix.total_trades,
        })
        log.info(
            "Night %d complete — %d bars | %d MINTs | %d trades",
            night_num, fornix.total_bars_processed, fornix.total_mints, fornix.total_trades,
        )
        return fornix.total_bars_processed > 0

    finally:
        if was_running:
            log.info("Resuming Mammon (mode=%s)...", prev_mode)
            _mammon_start(mode=prev_mode, symbols=prev_symbols)


def print_status() -> None:
    state = _load_state()
    completed = set(state.get("completed_nights", []))
    next_n = _next_night(state)

    print(f"\n{'#':<5} {'Crypto':<12} {'Shock':<35} Status")
    print("-" * 70)
    for i, (crypto, shock) in enumerate(NIGHT_SCHEDULE, 1):
        if i in completed:
            status = "DONE"
        elif i == next_n:
            status = "NEXT"
        else:
            status = "pending"
        c = crypto or "(shock only)"
        print(f"  {i:<3} {c:<12} {shock:<35} {status}")

    done = len(completed)
    print(f"\n{done}/{len(NIGHT_SCHEDULE)} nights complete. Last run: {state.get('last_run', 'never')}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Midnight Fornix night runner — 20-night replay schedule")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show tonight's symbols without running anything")
    parser.add_argument("--status", action="store_true",
                        help="Print full schedule and completion state")
    parser.add_argument("--night", type=int, metavar="N",
                        help="Force-run a specific night number (1-20)")
    args = parser.parse_args()

    if args.status:
        print_status()
        sys.exit(0)

    state = _load_state()

    if args.night:
        night_num = args.night
    else:
        night_num = _next_night(state)
        if night_num is None:
            log.info("All 20 nights complete. Fornix schedule exhausted.")
            sys.exit(0)

    success = run_night(night_num, dry_run=args.dry_run)

    if success and not args.dry_run:
        state["completed_nights"] = sorted(set(state.get("completed_nights", []) + [night_num]))
        state["last_run"] = datetime.now().isoformat()
        _save_state(state)
        log.info("Night %d marked complete.", night_num)
    elif not success:
        log.error("Night %d FAILED — not marking complete", night_num)
        sys.exit(1)
