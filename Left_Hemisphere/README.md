# Left Hemisphere (Risk Trajectory)

## Purpose
The Left Hemisphere serves as the system's primary risk assessment engine. It converts environmental intelligence from the Council into statistical priors and executes high-velocity Monte Carlo simulations to determine the probability of a trade's survival against stop-loss levels.

## Components

### 1. `TurtleMonte` (Monte_Carlo/turtle/service.py)
The core risk simulator.
- `simulate()`: Runs vectorized survival simulations across three volatility lanes: Worst (2.0x), Neutral (1.0x), and Best (0.5x).
- **Survival Scoring**: Calculates the weighted average of survival probabilities across all lanes to produce the final `monte_score`.
- **Zero-Copy Performance**: Writes simulation outputs directly to the `BrainFrame.risk` slot.

### 2. `QuantizedGeometricWalk` (Monte_Carlo/walk/service.py)
The prior-painting engine.
- `build_seed()`: Derives trajectory priors (`mu`, `sigma`, `p_jump`) based on the current market Regime ID.
- **Shock Injection**: Discharges historical price shocks into the simulation to ensure trajectories are grounded in realistic market behavior.
- **Regime Identification**: Categorizes the market into a 16-character string (e.g., `D2_A1_V1_T1`) for calibrated parameter selection.

## Inputs & Outputs
- **Inputs**: `BrainFrame` containing current structure (price, stop levels) and environment (volatility, trend).
- **Outputs**: Direct updates to `BrainFrame.risk` (`mu`, `sigma`, `p_jump`, `monte_score`, `worst/neutral/best_survival`).

## Dependencies
- `Cerebellum.Soul`: BrainFrame contract and timing gate.
- `Hippocampus.Archivist`: Analytical persistence via the Librarian.