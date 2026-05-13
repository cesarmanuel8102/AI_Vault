for ($i=1; $i -le 10; $i++) {
    Write-Host "--- Check $i at $(Get-Date -Format 'HH:mm:ss') ---"
    python C:/AI_VAULT/tmp_agent/check_po_pipeline.py
    
    # Also check the latest autonomy cycle for trade attempts
    $cycle = python -c "
import json
try:
    d=json.load(open('C:/AI_VAULT/tmp_agent/state/autonomy/autonomy_cycle_latest.json'))
    res = d.get('execution',{}).get('actions_results', [])
    for r in res:
        inner = r.get('result',{}).get('result',{})
        trades = inner.get('trades_executed', 0)
        error = ''
        results = inner.get('results',[]) if isinstance(inner.get('results'), list) else []
        if results:
            error = results[0].get('error','')
        print(f'  Cycle #{d.get(\"cycle_count\",\"?\")} at {d.get(\"completed_utc\",\"?\")}: trades={trades}, error={error}')
except: pass
"
    Write-Host $cycle
    
    # Check paper execution ledger for new entries
    $ledger = python -c "
import json
try:
    d=json.load(open('C:/AI_VAULT/tmp_agent/state/strategy_engine/signal_paper_execution_ledger.json'))
    entries = d.get('entries',[])
    if entries:
        last = entries[-1]
        print(f'  Last trade: {last.get(\"strategy_id\",\"?\")} {last.get(\"direction\",\"?\")} at {last.get(\"entry_utc\",\"?\")} result={last.get(\"result\",\"?\")}')
    print(f'  Total entries: {len(entries)}')
except: pass
"
    Write-Host $ledger
    
    if ($i -lt 10) { Start-Sleep -Seconds 180 }
}
