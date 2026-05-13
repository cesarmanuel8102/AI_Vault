"""Extract all 27 QC metrics from every raw backtest JSON we have."""
import json, os, glob

RAW_DIR = "C:/AI_VAULT/tmp_agent/strategies/yoel_options"

# All raw files
raw_files = glob.glob(os.path.join(RAW_DIR, "*_raw.json"))

# Also load complete_comparison_data.json
comp_file = os.path.join(RAW_DIR, "complete_comparison_data.json")

results = {}

# From complete_comparison_data.json (already has clean stats)
with open(comp_file, "r") as f:
    comp = json.load(f)
for label, stats in comp.items():
    results[label] = stats

# From raw JSON files
for rf in sorted(raw_files):
    fname = os.path.basename(rf)
    with open(rf, "r") as f:
        data = json.load(f)
    
    # Navigate to statistics
    bt = data.get("backtest", data)
    stats = bt.get("statistics", {})
    name = bt.get("name", fname)
    bt_id = bt.get("backtestId", "?")
    start = bt.get("backtestStart", "?")
    end = bt.get("backtestEnd", "?")
    
    if not stats:
        print(f"SKIP (no stats): {fname} -> {name}")
        continue
    
    label = f"{name} [{bt_id[:8]}]"
    results[label] = {
        "file": fname,
        "bt_id": bt_id,
        "period": f"{start[:10]} to {end[:10]}",
        **stats
    }

# Print master table
print("=" * 120)
print("MASTER BACKTEST RESULTS TABLE - ALL VARIANTS")
print("=" * 120)

# Define the metrics we care about (all 27 QC metrics)
METRICS = [
    "Net Profit", "Compounding Annual Return", "Sharpe Ratio", "Sortino Ratio",
    "Probabilistic Sharpe Ratio", "Drawdown", "Expectancy", "Win Rate", "Loss Rate",
    "Profit-Loss Ratio", "Average Win", "Average Loss", "Total Orders",
    "Alpha", "Beta", "Annual Standard Deviation", "Annual Variance",
    "Information Ratio", "Tracking Error", "Treynor Ratio",
    "Total Fees", "Estimated Strategy Capacity", "Portfolio Turnover",
    "Drawdown Recovery", "Start Equity", "End Equity",
    "Lowest Capacity Asset"
]

# Print each variant
for label in sorted(results.keys()):
    stats = results[label]
    print(f"\n--- {label} ---")
    if "period" in stats:
        print(f"  Period: {stats['period']}")
    if "bt_id" in stats:
        print(f"  BT ID: {stats['bt_id']}")
    for m in METRICS:
        val = stats.get(m, "N/A")
        print(f"  {m:35s}: {val}")

# Now print a condensed comparison table for the key metrics
print(f"\n\n{'='*140}")
print("CONDENSED COMPARISON TABLE")
print(f"{'='*140}")

KEY_METRICS = [
    ("Net Profit", 12), ("CAGR", 10), ("Sharpe", 8), ("Sortino", 8),
    ("PSR", 8), ("DD", 8), ("Expect", 8), ("WR", 6), ("P/L", 6),
    ("AvgW", 7), ("AvgL", 7), ("Orders", 7), ("InfoR", 7),
    ("Turnover", 9), ("Capacity", 12), ("Recovery", 9), ("EndEq", 10),
    ("AnnVol", 8), ("Fees", 10)
]

header = f"{'Variant':<35s}"
for name, width in KEY_METRICS:
    header += f"{name:>{width}s}"
print(header)
print("-" * len(header))

METRIC_MAP = {
    "Net Profit": "Net Profit",
    "CAGR": "Compounding Annual Return",
    "Sharpe": "Sharpe Ratio",
    "Sortino": "Sortino Ratio",
    "PSR": "Probabilistic Sharpe Ratio",
    "DD": "Drawdown",
    "Expect": "Expectancy",
    "WR": "Win Rate",
    "P/L": "Profit-Loss Ratio",
    "AvgW": "Average Win",
    "AvgL": "Average Loss",
    "Orders": "Total Orders",
    "InfoR": "Information Ratio",
    "Turnover": "Portfolio Turnover",
    "Capacity": "Estimated Strategy Capacity",
    "Recovery": "Drawdown Recovery",
    "EndEq": "End Equity",
    "AnnVol": "Annual Standard Deviation",
    "Fees": "Total Fees",
}

for label in sorted(results.keys()):
    stats = results[label]
    row = f"{label[:35]:<35s}"
    for name, width in KEY_METRICS:
        qc_key = METRIC_MAP[name]
        val = str(stats.get(qc_key, "N/A"))
        # Shorten
        val = val.replace("$", "").replace(",", "").strip()
        if len(val) > width:
            val = val[:width]
        row += f"{val:>{width}s}"
    print(row)

# Save everything
output = {
    "all_results": results,
}
with open(os.path.join(RAW_DIR, "master_all_backtests.json"), "w") as f:
    json.dump(output, f, indent=2, default=str)

print(f"\n\nSaved to master_all_backtests.json")
