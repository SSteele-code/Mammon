# Architecture Ownership Map
Date: 2026-03-09
Status: Active authority map

## Goal
Define hard ownership boundaries so mode, execution, and persistence behavior remain coherent across modules.

## Ownership Matrix

### Brain Stem
Owns:
- execution adapter routing and order fire/cancel mechanics
- execution lifecycle transitions and telemetry
- secondary execution safety gates (risk/valuation/conviction)
- Pons execution cost (TCA estimation: half-spread + impact + volatility)
- Valuation surface hydration (mean/std_dev/z_distance)

Does not own:
- alpha/signal generation
- final policy threshold decisions

### Medulla
Owns:
- final command policy gate (`Gatekeeper`)
- mode-scoped money ledgers (`TreasuryGland`) with composite-key isolation
- AllocationGland (mean-reversion position sizing sized by z_distance and penalized by cost)

Does not own:
- broker fire mechanics
- market ingestion

### Thalamus
Owns:
- source market fetch and normalization
- bid/ask passthrough via `get_snapshot()`
- pulse material generation via `SmartGland` (`SEED`/`ACTION`/`MINT` markers)
- broadcast to Optical Tract

Does not own:
- pulse cadence authority
- strategy scoring
- policy approval
- execution firing

### Cerebellum/Soul/Council
Owns:
- orchestration order and shared frame lifecycle
- environment confidence computation
- Spread assessment (5th Council indicator via SpreadEngine)
- pulse cadence authority and lobe sequencing legality
- 30s ACTION->MINT timing guard authority

Does not own:
- broker execution adapter
- final approval thresholds

### Left Hemisphere
Owns:
- risk prior painting and Monte survival outputs on `frame.risk`
- deterministic shock/fallback policy under Soul cadence

Does not own:
- pulse schedule ownership
- command/policy/execution mutations

### Corpus
Owns:
- tier synthesis bridge (`Callosum`)
- payload fan-out transport (`OpticalTract`)

Does not own:
- final policy approval
- broker execution

### Hippocampus
Owns:
- persistence gateways and schema control
- centralized SQL connection factory (`Librarian.get_connection`)
- async write queue durability (`Telepathy` V5 with Redis Stream routing for both DuckDB and TimescaleDB)
- startup schema preflight and periodic drift checks (`schema_guard`)
- historical replay conduit (`Fornix`)
- memory hygiene finalization (`Pineal`)
- Param DB (`Ecosystem_Params.db`) — full parameter genealogy (Gold/Silver/Platinum/Titanium/Bronze)    
- Dual-mode Crawler (`ParamCrawler`): MINE mode (Silver population from historical replay) and PROMOTE mode (Titanium → Gold promotion via soak window)

Does not own:
- direct strategy decisions
- broker execution behavior

### Pituitary
Owns:
- Platinum promotion (`secrete_platinum()`), Bronze retirement (`_retire_to_bronze()`)
- Hormonal integrity validation (`validate_hormonal_integrity()`)
- DiamondGland (ML pipeline): derives Safety Rails from Silver + Platinum data, synthesizes Titanium candidates
- GP mutation is ARCHIVED (`Pituitary/archived/gp_mutation_v3.py`)

Does not own:
- Gold installation (owned by Crawler PROMOTE)
- direct strategy or execution decisions

### Hospital
Owns:
- 5 domain-specific split optimizers (Risk, Strategy, Council, Synthesis, Execution)
- Volume Furnace orchestration (`VolumeFurnaceOrchestrator`) on 15-minute cadence
- Platinum discovery within Diamond-derived safety rails
- Fitness scoring and candidate evaluation

Does not own:
- Gold installation or promotion decisions
- direct broker execution

### Scripts/Operations
Owns:
- offline rotation/backtest operations (`scripts/rotate_backtest.py`)
- N95 hardware-aware backtest constraints (DuckDB memory/threads)
- cohort rotation tracker updates and vault promotion safety (backup/rollback)

Does not own:
- live runtime orchestration authority
- direct policy/execution decisions

## Mode System Contract
- Runtime mode authority originates at dashboard/runtime state.
- Mode must be propagated consistently to Gatekeeper/Treasury/Trigger/optimizer paths.
- Mode transitions must trigger rebind/rebuild of mode-sensitive components.

## Contract Sync Ledger
Last reconciled: 2026-03-10
Reconciled updates:
- 2026-03-10: v4.1 audit — Integrated V5 Telepathy for asynchronous, non-blocking DuckDB and TimescaleDB routing.
- 2026-03-09: v4.0 audit — added Pituitary (Diamond/Titanium), Hospital (Split Optimizers), Hippocampus (Crawler/ParamDB) ownership sections.
- 2026-02-20: README/Internal Logic concurrency sweep — Soul cadence ownership explicitly reinforced in Thalamus docs.
- 2026-02-20: Control-plane docs synchronized to current runtime hardening: bearer-auth bootstrap requirement in UI and authenticated SSE stream contract.

## Known Cross-Cut Risks
- UI appears non-functional when API/admin tokens are not bootstrapped in browser storage (`localStorage`) because all control/status endpoints are bearer-protected.
- SSE transport requires authenticated stream contract; if token bootstrap is absent, signal log and live diagnostics appear stale/non-functional.
