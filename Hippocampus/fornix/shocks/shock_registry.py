"""
Hippocampus/Fornix/Shocks: Shock Registry
The authoritative definition of all 20 historical market events.
Every downstream script pulls from here. Nothing is hardcoded elsewhere.
"""

from dataclasses import dataclass, field
from typing import List
import logging
logger = logging.getLogger(__name__)


@dataclass
class ShockEvent:
    id: str                  # Unique identifier — becomes the symbol prefix
    name: str                # Human-readable name
    category: str            # CRASH or BOOM
    start: str               # YYYY-MM-DD
    end: str                 # YYYY-MM-DD
    ticker: str              # Yahoo Finance ticker for source data
    source_note: str         # Where data comes from / any caveats
    character: str           # Description of regime shape
    vol_multiplier: float    # Rough intraday vol multiplier vs normal (for spread/volume modeling)
    spread_regime: str       # TIGHT | NORMAL | WIDE | PANIC
    volume_multiplier: float # Volume vs normal crypto volume (1.0 = same)
    symbol: str = field(init=False)  # market_tape symbol name (set post-init)

    def __post_init__(self):
        self.symbol = f"SHOCK_{self.id}/USD"


SHOCK_REGISTRY: List[ShockEvent] = [

    # ------------------------------------------------------------------ #
    #  CRASHES                                                            #
    # ------------------------------------------------------------------ #

    ShockEvent(
        id="1929_CRASH",
        name="Great Depression Crash",
        category="CRASH",
        start="1929-10-01",
        end="1932-06-30",
        ticker="^DJI",
        source_note="DJIA daily from Stooq (pre-Yahoo). Shiller data as fallback.",
        character="89% drawdown over 3 years. Relentless, no dead-cat bounces of significance. "
                  "Teaches the survival model what a true secular collapse looks like.",
        vol_multiplier=3.5,
        spread_regime="PANIC",
        volume_multiplier=6.0,
    ),

    ShockEvent(
        id="1937_DOUBLEDIP",
        name="1937 Double-Dip Recession",
        category="CRASH",
        start="1937-03-01",
        end="1938-04-30",
        ticker="^DJI",
        source_note="DJIA daily from Stooq.",
        character="Recovery that wasn't. -49% after partial Great Depression rebound. "
                  "Teaches false-recovery regime transitions.",
        vol_multiplier=2.8,
        spread_regime="WIDE",
        volume_multiplier=4.0,
    ),

    ShockEvent(
        id="1962_KENNEDY",
        name="1962 Kennedy Slide",
        category="CRASH",
        start="1962-01-01",
        end="1962-10-31",
        ticker="^GSPC",
        source_note="S&P 500 daily from Yahoo Finance.",
        character="-28% sharp and fast with a clean recovery. "
                  "Good template for sharp corrections that don't become bear markets.",
        vol_multiplier=2.2,
        spread_regime="WIDE",
        volume_multiplier=3.0,
    ),

    ShockEvent(
        id="1973_OILSHOCK",
        name="1973-74 Oil Shock / Stagflation",
        category="CRASH",
        start="1973-01-01",
        end="1974-12-31",
        ticker="^GSPC",
        source_note="S&P 500 daily from Yahoo Finance.",
        character="-48% over two years of slow suffocation. "
                  "Stagflation vol pattern: grinding down with periodic relief rallies. "
                  "Unique regime the engine will only learn here.",
        vol_multiplier=2.0,
        spread_regime="WIDE",
        volume_multiplier=2.5,
    ),

    ShockEvent(
        id="1987_BLACKMON",
        name="Black Monday",
        category="CRASH",
        start="1987-10-01",
        end="1987-12-31",
        ticker="^GSPC",
        source_note="S&P 500 daily from Yahoo Finance.",
        character="-22% in a single session on Oct 19. "
                  "Teaches the single-day shock pattern: gap open, no recovery that day, "
                  "then gradual normalization. Vol spike is the key signal.",
        vol_multiplier=8.0,
        spread_regime="PANIC",
        volume_multiplier=10.0,
    ),

    ShockEvent(
        id="1997_ASIAN",
        name="1997 Asian Financial Crisis",
        category="CRASH",
        start="1997-07-01",
        end="1998-01-31",
        ticker="^GSPC",
        source_note="S&P 500 daily from Yahoo Finance. Contagion visible in US data.",
        character="Contagion spread from Southeast Asia. Rolling panic across markets. "
                  "Teaches sequential regime breakdown pattern.",
        vol_multiplier=2.5,
        spread_regime="WIDE",
        volume_multiplier=3.5,
    ),

    ShockEvent(
        id="1998_LTCM",
        name="Russian Default / LTCM",
        category="CRASH",
        start="1998-07-01",
        end="1998-11-30",
        ticker="^GSPC",
        source_note="S&P 500 daily from Yahoo Finance.",
        character="Liquidity seizure. Credit markets freeze. -20% in 6 weeks. "
                  "Teaches the liquidity-driven panic — spreads blow out, volume spikes, "
                  "fast recovery once backstop arrives.",
        vol_multiplier=4.0,
        spread_regime="PANIC",
        volume_multiplier=5.0,
    ),

    ShockEvent(
        id="2000_DOTCOM",
        name="Dot-com Unwind",
        category="CRASH",
        start="2000-03-01",
        end="2002-10-31",
        ticker="^IXIC",
        source_note="Nasdaq Composite from Yahoo Finance. Nasdaq better captures tech unwind than S&P.",
        character="-78% over 2.5 years. Euphoria to ruin. Long duration teaches the engine "
                  "sustained bear regimes that cryptos 2022 winter only approximates.",
        vol_multiplier=3.0,
        spread_regime="WIDE",
        volume_multiplier=4.0,
    ),

    ShockEvent(
        id="2001_911",
        name="9/11 Shock",
        category="CRASH",
        start="2001-09-10",
        end="2001-10-15",
        ticker="^GSPC",
        source_note="S&P 500 daily from Yahoo Finance. Exchange closed Sep 11-14, gap on reopen.",
        character="Exogenous shock. Market closed then gap-opened -5% on Sep 17. "
                  "Teaches circuit-breaker style gap events and post-shock recovery pattern.",
        vol_multiplier=5.0,
        spread_regime="PANIC",
        volume_multiplier=7.0,
    ),

    ShockEvent(
        id="2008_CRISIS",
        name="Global Financial Crisis",
        category="CRASH",
        start="2007-10-01",
        end="2009-03-31",
        ticker="^GSPC",
        source_note="S&P 500 daily from Yahoo Finance.",
        character="-57% over 17 months. The real thing. Lehman, bank runs, "
                  "credit freeze. This is the benchmark every risk model is measured against.",
        vol_multiplier=5.0,
        spread_regime="PANIC",
        volume_multiplier=8.0,
    ),

    ShockEvent(
        id="2010_FLASH",
        name="2010 Flash Crash",
        category="CRASH",
        start="2010-05-06",
        end="2010-05-06",
        ticker="^GSPC",
        source_note="S&P 500 daily from Yahoo Finance. Single day event. "
                    "Intraday -9% in 36 minutes, full recovery same session.",
        character="Intraday only. The fastest crash and recovery in history. "
                  "Tests the engine's ability to handle extreme intraday vol "
                  "that resolves within the same bar window.",
        vol_multiplier=12.0,
        spread_regime="PANIC",
        volume_multiplier=15.0,
    ),

    ShockEvent(
        id="2011_EUROCRISIS",
        name="European Debt Crisis",
        category="CRASH",
        start="2011-07-01",
        end="2011-12-31",
        ticker="^GSPC",
        source_note="S&P 500 daily from Yahoo Finance.",
        character="Rolling sovereign panic across Greece, Italy, Spain. "
                  "-21% with repeated relief rallies that fail. "
                  "Teaches the false-recovery-in-a-downtrend pattern.",
        vol_multiplier=3.0,
        spread_regime="WIDE",
        volume_multiplier=3.5,
    ),

    ShockEvent(
        id="2015_CHINA",
        name="Chinese Circuit Breakers",
        category="CRASH",
        start="2015-06-01",
        end="2016-02-29",
        ticker="000001.SS",
        source_note="Shanghai Composite from Yahoo Finance.",
        character="Halt-triggered gap-down cascades. Circuit breakers made it worse. "
                  "-45% with extreme intraday gap patterns. Good for gap regime training.",
        vol_multiplier=4.5,
        spread_regime="PANIC",
        volume_multiplier=6.0,
    ),

    ShockEvent(
        id="2018_VOLMAGEDDON",
        name="Volmageddon",
        category="CRASH",
        start="2018-02-05",
        end="2018-02-09",
        ticker="^VIX",
        source_note="VIX from Yahoo Finance + S&P 500 for price. "
                    "VIX used to model spread/vol texture. S&P for returns.",
        character="Vol product implosion. VIX doubled in a day. -10% in 2 sessions. "
                  "Teaches vol-of-vol regime: when vol itself becomes the crash driver.",
        vol_multiplier=10.0,
        spread_regime="PANIC",
        volume_multiplier=12.0,
    ),

    ShockEvent(
        id="2020_COVID",
        name="COVID Crash",
        category="CRASH",
        start="2020-02-19",
        end="2020-03-23",
        ticker="^GSPC",
        source_note="S&P 500 daily from Yahoo Finance.",
        character="-35% in 33 days. Fastest crash from ATH to bear market ever. "
                  "Then completely gone within months. "
                  "Teaches speed-of-crash and the V-recovery that follows.",
        vol_multiplier=7.0,
        spread_regime="PANIC",
        volume_multiplier=9.0,
    ),

    # ------------------------------------------------------------------ #
    #  BOOMS                                                              #
    # ------------------------------------------------------------------ #

    ShockEvent(
        id="1942_WW2BOOM",
        name="WW2 Industrial Boom",
        category="BOOM",
        start="1942-04-01",
        end="1945-08-31",
        ticker="^DJI",
        source_note="DJIA daily from Stooq.",
        character="+130% over 3.5 years with almost no pullbacks. "
                  "Relentless, conviction-driven uptrend unlike anything in crypto history. "
                  "Teaches the engine what a true sustained directional regime looks like.",
        vol_multiplier=0.6,
        spread_regime="TIGHT",
        volume_multiplier=1.5,
    ),

    ShockEvent(
        id="1949_POSTWAR",
        name="Post-War Secular Bull",
        category="BOOM",
        start="1949-06-01",
        end="1966-02-28",
        ticker="^DJI",
        source_note="DJIA daily from Stooq.",
        character="+500% over 17 years at low volatility. "
                  "Slow, steady, very low vol grind. The opposite of crypto. "
                  "Teaches the engine to recognize and hold through quiet uptrends.",
        vol_multiplier=0.4,
        spread_regime="TIGHT",
        volume_multiplier=1.2,
    ),

    ShockEvent(
        id="1995_DOTCOM_UP",
        name="Dot-com Melt-Up",
        category="BOOM",
        start="1995-01-01",
        end="2000-03-10",
        ticker="^IXIC",
        source_note="Nasdaq Composite from Yahoo Finance. Melt-up phase only.",
        character="+575% parabolic run. Teaches the melt-up regime: "
                  "momentum compounds, dips are bought instantly, "
                  "ADX stays pinned high for years.",
        vol_multiplier=1.5,
        spread_regime="NORMAL",
        volume_multiplier=2.0,
    ),

    ShockEvent(
        id="2009_QE_BULL",
        name="QE Bull Market",
        category="BOOM",
        start="2009-03-09",
        end="2020-02-19",
        ticker="^GSPC",
        source_note="S&P 500 daily from Yahoo Finance.",
        character="+530% over 11 years. Longest bull in history. "
                  "QE-distorted vol: unusually low, persistent. "
                  "Teaches the engine what central-bank-suppressed vol looks like.",
        vol_multiplier=0.5,
        spread_regime="TIGHT",
        volume_multiplier=1.3,
    ),

    ShockEvent(
        id="2020_VRECOVERY",
        name="COVID V-Recovery",
        category="BOOM",
        start="2020-03-23",
        end="2020-09-01",
        ticker="^GSPC",
        source_note="S&P 500 daily from Yahoo Finance.",
        character="+60% in 5 months. Fastest bull recovery ever recorded. "
                  "Comes immediately after the COVID crash — the full arc "
                  "(crash + V-recovery together) is the most complete "
                  "regime transition pair in the set.",
        vol_multiplier=2.5,
        spread_regime="NORMAL",
        volume_multiplier=3.0,
    ),
]


# ------------------------------------------------------------------ #
#  ACCESSORS                                                          #
# ------------------------------------------------------------------ #

def get_all() -> List[ShockEvent]:
    return SHOCK_REGISTRY


def get_crashes() -> List[ShockEvent]:
    return [s for s in SHOCK_REGISTRY if s.category == "CRASH"]


def get_booms() -> List[ShockEvent]:
    return [s for s in SHOCK_REGISTRY if s.category == "BOOM"]


def get_by_id(shock_id: str) -> ShockEvent:
    for s in SHOCK_REGISTRY:
        if s.id == shock_id:
            return s
    raise KeyError(f"No shock with id={shock_id!r}")


def all_symbols() -> List[str]:
    return [s.symbol for s in SHOCK_REGISTRY]


if __name__ == "__main__":
    logger.info(f"Shock Registry — {len(SHOCK_REGISTRY)} events\n")
    for s in SHOCK_REGISTRY:
        logger.info(f"  [{s.category:5}] {s.symbol:<30} {s.start} → {s.end}")
        logger.info(f"           {s.name}")
        print()
