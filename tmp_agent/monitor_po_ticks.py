"""
Monitor PO bridge tick rate in real-time.
Run after reloading the extension to verify the PUSH fix works.
Usage: python monitor_po_ticks.py
"""
import json, time, sys
from pathlib import Path

FEED = Path(r"C:\AI_VAULT\tmp_agent\state\rooms\brain_binary_paper_pb04_demo_execution\browser_bridge_normalized_feed.json")

prev_count = 0
prev_time = time.time()
print("Monitoring PO tick rate... (Ctrl+C to stop)")
print(f"{'Time':>10}  {'Ticks':>6}  {'Rate':>10}  {'Last Price':>12}  {'Reason':>10}")
print("-" * 60)

while True:
    try:
        data = json.loads(FEED.read_text(encoding="utf-8"))
        rows = data.get("rows", [])
        count = len(rows)
        now = time.time()
        dt = now - prev_time
        
        if count != prev_count and dt > 0:
            new_ticks = count - prev_count if count > prev_count else count  # handle wrap
            rate = new_ticks / dt
            last = rows[-1] if rows else {}
            price = last.get("price", "?")
            # Check if runtime has reason field
            reason = "?"
            t = time.strftime("%H:%M:%S")
            print(f"{t:>10}  {new_ticks:>6}  {rate:>8.1f}/s  {price:>12}  {last.get('captured_utc','')[:19]}")
            prev_count = count
            prev_time = now
    except Exception as e:
        print(f"  err: {e}", file=sys.stderr)
    
    time.sleep(2)
