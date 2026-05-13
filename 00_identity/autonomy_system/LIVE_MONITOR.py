#!/usr/bin/env python3
"""
AI_VAULT LIVE MONITOR
Monitor en tiempo real de la actividad del sistema
"""

import subprocess
import time
import requests
import sys
from datetime import datetime

def check_services():
    """Verificar estado de servicios"""
    services = {
        8000: "Brain",
        8010: "Advisor", 
        8030: "Chat",
        8040: "Dashboard"
    }
    
    results = {}
    for port, name in services.items():
        try:
            response = requests.get(f"http://127.0.0.1:{port}/", timeout=2)
            results[name] = ("OK", response.status_code)
        except:
            results[name] = ("FAIL", "No response")
    
    return results

def check_phase_manager_activity():
    """Verificar actividad del Phase Manager"""
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if 'python' in proc.info['name'].lower() and proc.info['cmdline']:
                if 'autonomy_phases.py' in ' '.join(proc.info['cmdline']):
                    return proc.info['pid'], "Running"
        return None, "Not found"
    except:
        return None, "Cannot check"

def main():
    print("=" * 70)
    print("AI_VAULT LIVE MONITOR")
    print("Supervisor: OpenCode Agent")
    print("=" * 70)
    print()
    
    iteration = 0
    
    while True:
        iteration += 1
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n[{timestamp}] Ciclo #{iteration}")
        print("-" * 70)
        
        # Verificar servicios
        services = check_services()
        print("SERVICIOS:")
        for name, (status, code) in services.items():
            symbol = "[OK]" if status == "OK" else "[FAIL]"
            print(f"  {symbol} {name}: {status} (HTTP {code})")
        
        # Verificar Phase Manager
        pid, status = check_phase_manager_activity()
        print(f"\nPHASE MANAGER: {status}" + (f" (PID: {pid})" if pid else ""))
        
        # Estado de fase
        try:
            import json
            from pathlib import Path
            state_file = Path(r"C:\AI_VAULT\00_identity\autonomy_system\autonomy_state.json")
            if state_file.exists():
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    phase = state.get("current_phase", 0)
                    metrics = state.get("metrics_count", 0)
                    print(f"\nESTADO AUTONOMIA:")
                    print(f"  Fase actual: {phase}/6")
                    print(f"  Metricas recolectadas: {metrics}")
                    
                    phases_names = ["INIT", "MONITOR", "SELF-AWARE", "SELF-HEAL", "LEARN", "EVOLVE", "AUTONOMY"]
                    if phase < len(phases_names):
                        print(f"  Fase actual: {phases_names[phase]}")
        except Exception as e:
            print(f"\nESTADO AUTONOMIA: Error leyendo estado - {e}")
        
        print("\n" + "=" * 70)
        time.sleep(10)

if __name__ == "__main__":
    main()
