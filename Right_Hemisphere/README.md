# Right Hemisphere (Technical Structure)

## Purpose
The Right Hemisphere serves as the primary technical structure and breakout engine. It is responsible for identifying dynamic price boundaries (highs/lows) and generating Tier 1 breakout signals based on active market "gears."

## Components

### 1. `SnappingTurtle` (Snapping_Turtle/engine/service.py)
The active Tier 1 breakout engine.
- `on_data_received()`: Processes market pulses to identify `active_hi` (high water mark) and `active_lo` (low water mark) within the current gear window.
- **Breakout Detection**: Generates a `tier1_signal` (1) if the current close exceeds the previous window's high.
- **Gold Mirror Adherence**: Strictly pulls its lookback window (`active_gear`) from the `BrainFrame.standards` provided by the `Orchestrator`.

### 2. Future Tier Stubs (Archived)
The architecture reserves slots for:
- **Tier 2 (Momentum)**: MACD Reversal acceleration.
- **Tier 3 (Velocity)**: Bollinger Band expansion speed.
- **Tier 4 (Levels)**: Pivot and whole-round price level mapping.

## Inputs & Outputs
- **Inputs**: `pd.DataFrame` (Market Pulse) and `BrainFrame` from `Cerebellum`.
- **Outputs**: Direct zero-copy updates to `BrainFrame.structure` (`price`, `active_hi`, `active_lo`, `gear`, `tier1_signal`).

## Dependencies
- `Cerebellum.Soul`: BrainFrame contract and timing gate.
- `Hippocampus.Archivist`: Parameter vault access via Soul standards.