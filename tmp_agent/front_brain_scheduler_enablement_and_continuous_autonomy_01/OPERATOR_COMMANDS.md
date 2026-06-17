# OPERATOR_COMMANDS.md
## FRONT-BRAIN-SCHEDULER-ENABLEMENT-AND-CONTINUOUS-AUTONOMY-01

## Immediate Controls

### Pause Autonomy
```powershell
powershell -ExecutionPolicy Bypass -File "tools\brain_autonomy_pause.ps1"
```

### Resume Autonomy
```powershell
powershell -ExecutionPolicy Bypass -File "tools\brain_autonomy_resume.ps1"
```

### Stop Autonomy
```powershell
powershell -ExecutionPolicy Bypass -File "tools\brain_autonomy_stop.ps1"
```

### Check Status
```powershell
powershell -ExecutionPolicy Bypass -File "tools\brain_autonomy_status.ps1"
```

### Run Once (manual trigger)
```powershell
powershell -ExecutionPolicy Bypass -File "tools\brain_autonomy_run_once.ps1"
```

## Scheduler Management

### View Scheduled Task
```powershell
Get-ScheduledTask -TaskName "BrainGovernedAutonomy"
```

### Disable Scheduled Task
```powershell
Disable-ScheduledTask -TaskName "BrainGovernedAutonomy"
```

### Enable Scheduled Task
```powershell
Enable-ScheduledTask -TaskName "BrainGovernedAutonomy"
```

### Remove Scheduled Task
```powershell
Unregister-ScheduledTask -TaskName "BrainGovernedAutonomy" -Confirm:$false
```

## Service Checks

### Dashboard
```powershell
curl http://127.0.0.1:8092/
```

### Provider Health
```powershell
curl http://127.0.0.1:8091/health
```

## Memory Verification

### Check journal count
```powershell
python -c "print('journal:', sum(1 for line in open('memory/autonomous_journal.jsonl') if line.strip()))"
```

### Check canonical hashes
```powershell
python -c "import hashlib, os; [print(f'{f}: {hashlib.sha256(open(f,'rb').read(65536)).hexdigest()[:16]}') for f in ['memory/semantic/semantic_memory.jsonl','memory/semantic/semantic_memory_faiss.index','memory/semantic/semantic_memory_faiss_ids.json']]"
```

## Emergency Procedures

If autonomy behaves unexpectedly:
1. Run `brain_autonomy_stop.ps1` immediately
2. Disable scheduled task: `Disable-ScheduledTask -TaskName "BrainGovernedAutonomy"`
3. Check `memory/autonomous_journal.jsonl` for recent events
4. Review `tmp_agent/control/` for stray flags
