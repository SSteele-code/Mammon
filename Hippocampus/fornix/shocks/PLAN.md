# Fornix Shock Augmentation Plan
# Mammon — Historical Regime Injection

---

## The Core Idea

Crypto has 14 years of history. That is not enough to train a survival engine.
The goal: download real historical financial data for the world's 20 most extreme
market events, normalize it to crypto volatility scale, disaggregate it into
1-minute OHLCV bars, and inject it into the DuckPond market_tape alongside real
crypto. The Fornix replays it all — real and shock — through the same pipeline.
Diamond trains on the full shape of human financial history, not just 2022.

No synthetic generation. No GBM. Real event data, molded to fit.

---

## Crypto Symbol List (~16 symbols, 5 years each)

Target: ~2.5M bars total = 25% of the 10M bar cap.
Source: Alpaca historical API (crypto, 1-minute bars, 2020-01-01 to present).

| Symbol    | Category         | Notes                                              |
|-----------|------------------|----------------------------------------------------|
| ETH/USD   | Layer 1          | Essential. Second most liquid.                     |
| SOL/USD   | Layer 1          | High momentum, distinct cycles.                    |
| AVAX/USD  | Layer 1          | Volatile, strong regime swings.                    |
| NEAR/USD  | Layer 1          | Sharding narrative, distinct character.            |
| ALGO/USD  | Layer 1          | Pure PoS, different rhythm.                        |
| BCH/USD   | Payments         | OG fork, separate cycle from BTC.                  |
| LINK/USD  | DeFi / Oracle    | News-driven spikes, mid-cap.                       |
| AAVE/USD  | DeFi             | Protocol-driven vol.                               |
| UNI/USD   | DeFi / DEX       | Governance event vol.                              |
| TRX/USD   | Payments         | High vol, independent pattern.                     |
| LTC/USD   | Payments / OG    | Older coin, different rhythm.                      |
| DOGE/USD  | Meme             | Pure volatility. Teaches chaos.                    |
| MATIC/USD | Layer 2          | Scaling narrative cycles.                          |
| MKR/USD   | DeFi             | Governance-driven vol, low BTC corr.               |
| GRT/USD   | Infrastructure   | Indexing protocol, low BTC corr.                   |
| BAT/USD   | Utility          | Browser/ad market, quiet mover.                    |

Confirmed available on Alpaca (2025-05-01). Replaced ADA, DOT, ATOM, XRP, FIL.

---

## Data Cleaning (per symbol, before ingestion)

1. Drop full gap periods (exchange downtime, API failures >10 bars contiguous).
2. Forward-fill isolated missing bars (1-2 bar gaps): carry last close as OHLC.
3. Volume fill: use rolling 30-bar average volume for missing volume bars.
4. Deduplicate on (symbol, ts).
5. Sort ascending by ts.
6. All bars must pass: open > 0, high >= open, low <= open, close > 0, volume >= 0.

---

## The 20 Shock Events

Real historical data downloaded from Yahoo Finance / FRED / Shiller dataset.
Sources cover S&P 500, DJIA, Nasdaq, VIX from 1928 onward.

### Crashes — Teach Survival Math the Real Floor

| # | Event                        | Date Range          | Index / Source     | Character                          |
|---|------------------------------|---------------------|--------------------|------------------------------------|
| 1 | Great Depression Crash       | 1929-10 to 1932-06  | DJIA               | 89% over 3 years. Relentless.      |
| 2 | 1937 Double Dip              | 1937-03 to 1938-04  | DJIA               | Recovery that wasn't.              |
| 3 | 1962 Kennedy Slide           | 1962-01 to 1962-10  | S&P 500            | Sharp, fast, clean recovery.       |
| 4 | 1973-74 Oil Shock            | 1973-01 to 1974-12  | S&P 500            | Slow suffocation. Stagflation vol. |
| 5 | 1987 Black Monday            | 1987-10-01 to 1987-12-31 | S&P 500      | Single session -22%. Never again.  |
| 6 | 1997 Asian Financial Crisis  | 1997-07 to 1998-01  | S&P 500 / Hang Seng| Contagion spread pattern.          |
| 7 | 1998 Russian Default / LTCM  | 1998-07 to 1998-11  | S&P 500            | Liquidity seizure. Credit freeze.  |
| 8 | 2000-2002 Dot-com Unwind     | 2000-03 to 2002-10  | Nasdaq             | Euphoria → -78% over 2.5 years.    |
| 9 | 2001 9/11 Shock              | 2001-09-10 to 2001-10-15 | S&P 500     | Gap open. Circuit-breaker style.   |
|10 | 2007-2009 Financial Crisis   | 2007-10 to 2009-03  | S&P 500            | The real thing. Full arc.          |
|11 | 2010 Flash Crash             | 2010-05-06 (1 day)  | S&P 500 / E-mini   | -9% in 36 minutes. Full recovery.  |
|12 | 2011 European Debt Crisis    | 2011-07 to 2011-12  | S&P 500 / Euro Stoxx| Rolling sovereign panic.          |
|13 | 2015 China Circuit Breakers  | 2015-06 to 2016-02  | Shanghai Composite | Halt → gap-down cascades.          |
|14 | 2018 Volmageddon             | 2018-02-05 to 2018-02-09 | VIX / S&P 500| Vol product implosion.             |
|15 | 2020 COVID Crash             | 2020-02-19 to 2020-03-23 | S&P 500     | -35% in 33 days. Then gone.        |

### Booms — Teach Trend-Following What a Real Trend Feels Like

| # | Event                        | Date Range          | Index / Source     | Character                          |
|---|------------------------------|---------------------|--------------------|------------------------------------|
|16 | WW2 Industrial Boom          | 1942-04 to 1945-08  | DJIA               | Relentless uptrend. No pullbacks.  |
|17 | 1949-1966 Post-War Secular Bull | 1949-06 to 1966-02 | DJIA / S&P 500   | Slow grind. Very low vol.          |
|18 | 1995-1999 Dot-com Melt-up    | 1995-01 to 2000-03  | Nasdaq             | Parabola. Teaches melt-up shape.   |
|19 | 2009-2019 QE Bull            | 2009-03 to 2020-02  | S&P 500            | Longest bull. QE-distorted vol.    |
|20 | 2020 V-Recovery              | 2020-03-23 to 2020-09-01 | S&P 500    | Fastest bull recovery ever.        |

---

## Shock Data Pipeline

### Step 1 — Download
- DJIA 1928+: Robert Shiller dataset (daily OHLC) or Stooq
- S&P 500: Yahoo Finance `^GSPC` (daily)
- Nasdaq: Yahoo Finance `^IXIC` (daily)
- VIX: Yahoo Finance `^VIX` (daily, 1990+)
- Shanghai Composite: Yahoo Finance `000001.SS`

### Step 2 — Vol Normalization
For each shock event:
- Compute event daily vol = std(daily returns) over event window
- Compute target crypto daily vol = std(daily returns) over last 90 days
- Scale factor = target_vol / event_vol
- Apply: scaled_returns = raw_returns * scale_factor
- Reconstruct price series from scaled returns starting at crypto's last close

Shape is preserved. Magnitude fits crypto. A 1929 crash looks like a crypto winter,
not a stock market crash.

### Step 3 — Disaggregate Daily → 1-Minute
For each daily bar (open, high, low, close, volume):
- Generate 1440 1-minute bars (crypto = 24h)
- Use OHLC as boundary constraints:
  - Bar opens at daily open
  - Intraday high/low bound the range
  - Bar closes at daily close
- Fill intraday path with scaled Brownian bridge between open and close,
  bounded by high/low
- Volume: distribute daily volume across 1440 bars with realistic intraday
  U-curve (higher at open/close, lower midday)

### Step 4 — Spread Blowout Modeling
During crash events, bid/ask spreads expand. Inject realistic spread data:
- Normal regime: bid_ask_bps = 2-4 bps
- Stress regime: bid_ask_bps = 15-40 bps (panic = 10x normal)
- Model spread as function of intraday vol: higher vol bar = wider spread
- This feeds spread_regime (TIGHT / NORMAL / WIDE) and exec_total_cost_bps correctly

### Step 5 — Volume Panic Modeling
Crash events have 5-10x normal volume. Boom events have sustained elevated volume.
- Crash: volume multiplier = 3-8x base crypto volume (random, skewed high)
- Boom: volume multiplier = 1.5-2.5x base
- Flash Crash (intraday): spike volume 10-20x in the panic window

### Step 6 — Warm-Up Ramp
Prepend 20 bars of normal crypto data before each shock injection.
This seeds ATR and ADX so indicators aren't cold when the shock hits.
Without this, the first 14 bars of every shock produce garbage indicator readings.

### Step 7 — Labeling
Shock events enter market_tape as separate symbols:
  SHOCK_1929_CRASH/USD
  SHOCK_1987_BLACKMON/USD
  SHOCK_2008_CRISIS/USD
  SHOCK_2020_COVID/USD
  etc.

This keeps real and synthetic cleanly separated.
Diamond sees them as symbols. Audit trail is clean.
You can pull any shock symbol out of training at any time.

### Step 8 — Diamond Weighting
Shock symbols should not dominate regime stats.
Recommended: weight shock MINTs at 25% relative to real crypto MINTs in Diamond scoring.
Enough to reshape the survival floor. Not enough to override what real crypto actually does.

---

## Files to Build

| File | Purpose |
|------|---------|
| `shocks/fetch_shocks.py` | Downloads historical event data from Yahoo/Shiller/FRED |
| `shocks/normalize_shocks.py` | Vol normalization + disaggregation to 1-minute bars |
| `shocks/inject_shocks.py` | Feeds normalized shock bars into DuckPond market_tape |
| `shocks/shock_registry.py` | Defines all 20 events: dates, source, index, character |
| `shocks/PLAN.md` | This file |

---

## What Diamond Gets Out the Other End

Regime training data that includes:
- Every crash shape in modern financial history
- Secular bulls that crypto has never seen
- Intraday shock patterns (Flash Crash) at 1-minute resolution
- Spread blowout regimes where cost dominates signal
- Vol regimes from quiet post-war grind to full panic

The vault params that emerge are hardened against scenarios that would wipe
most algos. worst_survival floor is set by 1929, not 2022.
gatekeeper_min_monte is calibrated against real black swans.

---

## Status

- [x] Confirm 16 crypto symbols available on Alpaca (11/16 original; 5 swapped — see table above)
- [x] Build shock_registry.py (event definitions)
- [x] Build fetch_shocks.py (data download)
- [x] Build normalize_shocks.py (vol norm + disaggregation)
- [x] Build inject_shocks.py (DuckPond ingestion)
- [x] Build fetch_crypto.py (Alpaca 5yr pull + clean + inject)
- [ ] Crypto 5yr data pull from Alpaca (run: fetch_crypto.py --fetch)
- [ ] Data cleaning pass (automatic — built into fetch_crypto.py --inject)
- [ ] Shock data download (run: fetch_shocks.py)
- [ ] Shock normalization (run: normalize_shocks.py)
- [ ] Full DuckPond ingestion (fetch_crypto.py --inject + inject_shocks.py)
- [ ] Fornix first run (TEST_PULSE_25)
- [ ] Diamond run on history_synapse
- [ ] Vault promotion of Diamond params
