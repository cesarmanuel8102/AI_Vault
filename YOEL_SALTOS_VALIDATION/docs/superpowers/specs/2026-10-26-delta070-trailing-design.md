# Delta 0.70 0DTE Trailing Profit Design

Replace the fixed 10% take-profit only when trailing parameters are enabled.
Activate trailing at +15% option return and exit after a five-percentage-point
drawdown from the highest observed return. At first activation this protects a
nominal +10%, while allowing stronger moves to continue.

The economics gate must use the initially protected return
(`activation - distance`), not the activation threshold. Preserve all signals,
sizing, costs, the one-shot 15-minute failure exit and the 15:55 close.

Validate with frozen 2025 discovery, unchanged 2026 validation and combined
confirmation. Compare against the accepted fixed-TP10 baseline.
