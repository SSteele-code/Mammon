"""
Run via:  docker exec mammon-dashboard python /mammon/scripts/tools/track.py
"""
import sqlite3
import duckdb
import json
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/mammon")
MONEY_DB   = ROOT / "runtime" / ".tmp_test_local" / "compat_librarian.db"
TMP        = ROOT / "runtime" / ".tmp_test_local"
PARAMS_DB  = ROOT / "Hippocampus" / "data" / "ecosystem_params.duckdb"
PARAMS_STABLE = TMP / "ecosystem_params_stable.duckdb"
SYNAPSE_DB     = ROOT / "Hippocampus" / "data" / "ecosystem_synapse.duckdb"
SYNAPSE_STABLE = TMP / "ecosystem_synapse_stable.duckdb"
SYNAPSE_SQLITE = ROOT / "Hippocampus" / "Archivist" / "Ecosystem_Synapse.db"

SEP = "=" * 60

def ts(t):
    if not t:
        return "—"
    return datetime.fromtimestamp(float(t), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def money(v):
    return f"${float(v or 0):+.2f}"

def pct(v):
    return f"{float(v or 0):+.2f}%"

# ── MONEY DB ─────────────────────────────────────────────────────────────────

def read_money():
    if not MONEY_DB.exists():
        return None
    conn = sqlite3.connect(str(MONEY_DB))
    conn.row_factory = sqlite3.Row

    positions = [dict(r) for r in conn.execute(
        "SELECT * FROM money_positions ORDER BY qty DESC"
    ).fetchall()]

    fills = [dict(r) for r in conn.execute(
        "SELECT * FROM money_fills ORDER BY ts ASC"
    ).fetchall()]

    orders = [dict(r) for r in conn.execute(
        "SELECT status, COUNT(*) as c FROM money_orders GROUP BY status"
    ).fetchall()]

    pnl_snap = conn.execute(
        "SELECT net_pnl FROM money_pnl_snapshots ORDER BY ts DESC LIMIT 1"
    ).fetchone()

    realized_total = conn.execute(
        "SELECT COALESCE(SUM(realized_pnl),0) AS r FROM money_positions"
    ).fetchone()["r"]

    unrealized_total = conn.execute(
        "SELECT COALESCE(SUM(unrealized_pnl),0) AS u FROM money_positions WHERE qty > 0"
    ).fetchone()["u"]

    conn.close()
    return dict(
        positions=positions,
        fills=fills,
        orders={r["status"]: r["c"] for r in orders},
        realized=realized_total,
        unrealized=unrealized_total,
    )

# ── PARAMS (Pituitary JSON vault) ────────────────────────────────────────────

VAULT_JSON = ROOT / "Hippocampus" / "hormonal_vault.json"

def read_params():
    try:
        gold = None
        silver_count = 0
        bronze_count = 0
        if VAULT_JSON.exists():
            vault = json.loads(VAULT_JSON.read_text())
            g = vault.get("gold", {})
            if g:
                gold = dict(
                    fitness=float(g.get("fitness_snapshot") or g.get("fitness") or 0),
                    coronated_at=g.get("coronated_at", ""),
                    origin=g.get("origin", ""),
                    params=g.get("params", {}),
                )
            silver = vault.get("silver", [])
            silver_count = len(silver) if isinstance(silver, list) else (1 if silver else 0)
            bronze = vault.get("bronze", [])
            bronze_count = len(bronze) if isinstance(bronze, list) else (1 if bronze else 0)
        return dict(gold=gold, silver=silver_count, bronze=bronze_count)
    except Exception as e:
        return dict(gold=None, silver="?", bronze="?", error=str(e))

# ── SYNAPSE DB ───────────────────────────────────────────────────────────────

def read_synapse():
    # Try DuckDB first, fall back to SQLite silo
    try:
        try:
            conn = duckdb.connect(str(SYNAPSE_DB), read_only=True)
        except Exception:
            conn = duckdb.connect(str(SYNAPSE_STABLE), read_only=True) if SYNAPSE_STABLE.exists() else None
        if conn:
            tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
            if "synapse_mint" in tables:
                bar_count = conn.execute("SELECT COUNT(*) FROM synapse_mint").fetchone()[0]
                first = conn.execute("SELECT MIN(ts) FROM synapse_mint").fetchone()[0]
                last  = conn.execute("SELECT MAX(ts) FROM synapse_mint").fetchone()[0]
                conn.close()
                return dict(bar_count=bar_count, first_bar=first, last_bar=last, source="duckdb")
            conn.close()
    except Exception:
        pass

    # SQLite silo fallback
    try:
        if SYNAPSE_SQLITE.exists():
            sc = sqlite3.connect(str(SYNAPSE_SQLITE))
            sc.row_factory = sqlite3.Row
            tables = [r[0] for r in sc.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            tbl = "synapse_mint" if "synapse_mint" in tables else (tables[0] if tables else None)
            if tbl:
                bar_count = sc.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                first = sc.execute(f"SELECT MIN(ts) FROM {tbl}").fetchone()[0]
                last  = sc.execute(f"SELECT MAX(ts) FROM {tbl}").fetchone()[0]
                sc.close()
                return dict(bar_count=bar_count, first_bar=first, last_bar=last, source="sqlite")
            sc.close()
    except Exception:
        pass

    return dict(bar_count=0, first_bar=None, last_bar=None)

# ── RENDER ───────────────────────────────────────────────────────────────────

def render():
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{SEP}")
    print(f"  MAMMON TRACKER  —  {now}")
    print(SEP)

    # ── Positions ──
    m = read_money()
    print("\n  POSITIONS")
    print(f"  {'Symbol':<12} {'Qty':>10} {'Entry':>8} {'Market':>8} {'Unreal':>10} {'Realized':>10}")
    print(f"  {'-'*12} {'-'*10} {'-'*8} {'-'*8} {'-'*10} {'-'*10}")
    if m:
        active = [p for p in m["positions"] if float(p.get("qty") or 0) > 0]
        if active:
            for p in active:
                unreal_pct = ((float(p["market_price"]) - float(p["avg_price"])) / float(p["avg_price"]) * 100) if float(p["avg_price"]) > 0 else 0
                print(f"  {p['symbol']:<12} {float(p['qty']):>10.4f} {float(p['avg_price']):>8.3f} {float(p['market_price']):>8.3f} {money(p['unrealized_pnl']):>10} {money(p['realized_pnl']):>10}  ({pct(unreal_pct)})")
        else:
            print("  No open positions")

    # ── PnL Summary ──
    print(f"\n  PNL SUMMARY")
    if m:
        net = float(m["realized"]) + float(m["unrealized"])
        print(f"  Realized:    {money(m['realized'])}")
        print(f"  Unrealized:  {money(m['unrealized'])}")
        print(f"  Net:         {money(net)}")

    # ── Trade History ──
    print(f"\n  TRADE HISTORY")
    if m:
        fills = m["fills"]
        buys  = [f for f in fills if f["side"] == "BUY"]
        sells = [f for f in fills if f["side"] == "SELL"]
        print(f"  Total fills: {len(fills)}  (Buys: {len(buys)}  Sells: {len(sells)})")

        if fills:
            print(f"\n  {'#':<3} {'Symbol':<12} {'Side':<5} {'Qty':>10} {'Price':>8} {'Slippage':>10} {'Fee':>8}")
            print(f"  {'-'*3} {'-'*12} {'-'*5} {'-'*10} {'-'*8} {'-'*10} {'-'*8}")
            for i, f in enumerate(fills, 1):
                print(f"  {i:<3} {f['symbol']:<12} {f['side']:<5} {float(f['qty']):>10.4f} {float(f['fill_price']):>8.3f} {money(f.get('slippage_cost',0)):>10} {money(f.get('fee',0)):>8}")

        orders = m["orders"]
        if orders:
            print(f"\n  Order states: " + "  ".join(f"{k}={v}" for k, v in orders.items()))

    # ── Pulse Coverage ──
    s = read_synapse()
    print(f"\n  PULSE COVERAGE")
    print(f"  Bars recorded: {s['bar_count']:,}")
    if s["first_bar"]:
        print(f"  First bar:     {ts(s['first_bar'])}")
        print(f"  Last bar:      {ts(s['last_bar'])}")

    # ── Optimizer ──
    p = read_params()
    print(f"\n  OPTIMIZER VAULT")
    print(f"  Silver pool:   {p['silver']}")
    print(f"  Bronze pool:   {p['bronze']}")
    if p.get("gold"):
        g = p["gold"]
        gp = g["params"]
        crowned = g.get("coronated_at") or ""
        print(f"  Gold fitness:  {float(g['fitness']):.4f}  (crowned {crowned[:19] if crowned else '—'})")
        print(f"  Gold key params:")
        for k in ["active_gear", "brain_stem_min_risk", "gatekeeper_min_monte", "gatekeeper_min_council"]:
            v = gp.get(k)
            if v is not None:
                print(f"    {k:<30} {float(v):.4f}")
    elif p.get("error"):
        print(f"  Params DB error: {p['error']}")

    print(f"\n{SEP}\n")

if __name__ == "__main__":
    render()
