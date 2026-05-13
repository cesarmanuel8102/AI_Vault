#!/usr/bin/env python3
"""
Sistema de Trading AI_VAULT - Verificación de Estado Operativo
Integrado al flujo oficial de meta-mejora del Brain
"""

import json
import urllib.request
import socket
from pathlib import Path
from datetime import datetime

def check_brain_v9():
    """Verificar estado de Brain V9"""
    try:
        req = urllib.request.Request('http://localhost:8090/brain/health', timeout=5)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return {
                'healthy': data['services']['brain_v9']['healthy'],
                'overall': data['overall_status'],
                'timestamp': data['timestamp']
            }
    except Exception as e:
        return {'error': str(e)}

def check_ibkr():
    """Verificar IBKR Gateway"""
    # Verificar puerto
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    port_open = sock.connect_ex(('127.0.0.1', 4002)) == 0
    sock.close()
    
    # Verificar API
    try:
        req = urllib.request.Request('http://localhost:8090/trading/health', timeout=5)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            ibkr = data.get('ibkr', {})
            return {
                'port_open': port_open,
                'order_api_ready': ibkr.get('order_api_ready'),
                'managed_accounts': ibkr.get('managed_accounts'),
                'status': ibkr.get('status'),
                'market_data_ready': ibkr.get('market_data_api_ready')
            }
    except Exception as e:
        return {'port_open': port_open, 'error': str(e)}

def check_pocket_option():
    """Verificar Pocket Option Bridge"""
    try:
        req = urllib.request.Request('http://localhost:8765/health', timeout=5)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return {
                'status': data.get('status'),
                'connected': data.get('connected'),
                'current_symbol': data.get('current_symbol'),
                'payout_pct': data.get('payout_pct'),
                'ws_event_count': data.get('ws_event_count', 0)
            }
    except Exception as e:
        return {'error': str(e)}

def check_meta_improvement():
    """Verificar estado de meta-mejora"""
    meta_path = Path('state/brain_meta_roadmap_latest.json')
    if not meta_path.exists():
        return {'error': 'Meta-roadmap no encontrado'}
    
    with open(meta_path) as f:
        meta = json.load(f)
    
    top_item = meta.get('top_item', {})
    return {
        'work_status': meta.get('work_status'),
        'top_gap_id': top_item.get('gap_id'),
        'priority_score': top_item.get('priority_score'),
        'execution_mode': top_item.get('execution_mode'),
        'suggested_actions': top_item.get('suggested_actions', [])
    }

def check_signals():
    """Verificar señales técnicas disponibles"""
    signals_path = Path('state/strategy_engine/strategy_signal_snapshot_latest.json')
    if not signals_path.exists():
        return {'error': 'Signals no encontrados'}
    
    with open(signals_path) as f:
        signals = json.load(f)
    
    items = signals.get('items', [])
    valid_signals = [s for s in items if s.get('signal_valid') and s.get('execution_ready')]
    
    # Separar por venue
    po_signals = [s for s in valid_signals if s.get('venue') == 'pocket_option']
    ibkr_signals = [s for s in valid_signals if s.get('venue') == 'ibkr']
    
    return {
        'total': len(items),
        'valid': len(valid_signals),
        'po_valid': len(po_signals),
        'ibkr_valid': len(ibkr_signals),
        'po_signals': po_signals[:3],
        'ibkr_signals': ibkr_signals[:3]
    }

def check_sample_accumulator():
    """Verificar estado del SampleAccumulator"""
    acc_path = Path('state/sample_accumulator.json')
    if not acc_path.exists():
        return {'error': 'SampleAccumulator no inicializado'}
    
    with open(acc_path) as f:
        acc = json.load(f)
    
    return {
        'running': acc.get('running', False),
        'session_trades': acc.get('session_trades_count', 0),
        'last_trade': acc.get('last_trade_time'),
        'check_interval': acc.get('check_interval_minutes'),
        'cooldown': acc.get('cooldown_minutes')
    }

def check_trading_policy():
    """Verificar política de trading"""
    policy_path = Path('state/trading_autonomy_policy.json')
    if not policy_path.exists():
        return {'error': 'Trading policy no encontrada'}
    
    with open(policy_path) as f:
        policy = json.load(f)
    
    return {
        'paper_only': policy.get('global_rules', {}).get('paper_only'),
        'live_forbidden': policy.get('global_rules', {}).get('live_trading_forbidden'),
        'ibkr_mode': policy.get('platform_rules', {}).get('ibkr', {}).get('mode'),
        'po_mode': policy.get('platform_rules', {}).get('pocket_option', {}).get('mode')
    }

def main():
    """Ejecutar verificación completa"""
    print("=" * 80)
    print("AI_VAULT TRADING SYSTEM - ESTADO OPERATIVO")
    print("=" * 80)
    print()
    
    # 1. Brain V9
    print("1. BRAIN V9")
    brain = check_brain_v9()
    if 'error' in brain:
        print(f"   [ERROR] {brain['error']}")
    else:
        print(f"   [OK] Healthy: {brain['healthy']}")
        print(f"   Overall Status: {brain['overall']}")
    print()
    
    # 2. IBKR Gateway
    print("2. IBKR GATEWAY")
    ibkr = check_ibkr()
    if 'error' in ibkr:
        print(f"   [ERROR] {ibkr['error']}")
    else:
        status = "OK" if ibkr.get('order_api_ready') else "ERROR"
        print(f"   [{status}] Port Open: {ibkr.get('port_open')}")
        print(f"   Order API Ready: {ibkr.get('order_api_ready')}")
        print(f"   Managed Accounts: {ibkr.get('managed_accounts')}")
        print(f"   Status: {ibkr.get('status')}")
        print(f"   Market Data Ready: {ibkr.get('market_data_ready')}")
    print()
    
    # 3. Pocket Option
    print("3. POCKET OPTION BRIDGE")
    po = check_pocket_option()
    if 'error' in po:
        print(f"   [ERROR] {po['error']}")
    else:
        status = "OK" if po.get('connected') else "ERROR"
        print(f"   [{status}] Status: {po.get('status')}")
        print(f"   Connected: {po.get('connected')}")
        print(f"   Current Symbol: {po.get('current_symbol', 'N/A')}")
        print(f"   Payout %: {po.get('payout_pct', 'N/A')}")
    print()
    
    # 4. Meta-Improvement
    print("4. META-IMPROVEMENT (ROADMAP)")
    meta = check_meta_improvement()
    if 'error' in meta:
        print(f"   [ERROR] {meta['error']}")
    else:
        print(f"   [OK] Work Status: {meta.get('work_status')}")
        print(f"   Top Gap: {meta.get('top_gap_id')}")
        print(f"   Priority: {meta.get('priority_score')}")
        print(f"   Execution Mode: {meta.get('execution_mode')}")
        print(f"   Suggested Actions: {', '.join(meta.get('suggested_actions', []))}")
    print()
    
    # 5. Señales
    print("5. SEÑALES TECNICAS")
    signals = check_signals()
    if 'error' in signals:
        print(f"   [ERROR] {signals['error']}")
    else:
        print(f"   Total Signals: {signals.get('total')}")
        print(f"   Valid Signals: {signals.get('valid')}")
        print(f"   PO Valid: {signals.get('po_valid')}")
        print(f"   IBKR Valid: {signals.get('ibkr_valid')}")
        
        if signals.get('ibkr_signals'):
            print("   IBKR Signals:")
            for s in signals['ibkr_signals']:
                print(f"      → {s['strategy_id']}: {s['direction'].upper()} {s['symbol']} (conf: {s['confidence']:.2f})")
        
        if signals.get('po_signals'):
            print("   PO Signals:")
            for s in signals['po_signals']:
                print(f"      → {s['strategy_id']}: {s['direction'].upper()} {s['symbol']} (conf: {s['confidence']:.2f})")
    print()
    
    # 6. SampleAccumulator
    print("6. SAMPLE ACCUMULATOR AGENT")
    acc = check_sample_accumulator()
    if 'error' in acc:
        print(f"   [ERROR] {acc['error']}")
    else:
        status = "OK" if acc.get('running') else "PAUSED"
        print(f"   [{status}] Running: {acc.get('running')}")
        print(f"   Session Trades: {acc.get('session_trades')}")
        print(f"   Last Trade: {acc.get('last_trade', 'N/A')}")
        print(f"   Check Interval: {acc.get('check_interval')} min")
        print(f"   Cooldown: {acc.get('cooldown')} min")
    print()
    
    # 7. Trading Policy
    print("7. TRADING POLICY")
    policy = check_trading_policy()
    if 'error' in policy:
        print(f"   [ERROR] {policy['error']}")
    else:
        print(f"   Paper Only: {policy.get('paper_only')}")
        print(f"   Live Forbidden: {policy.get('live_forbidden')}")
        print(f"   IBKR Mode: {policy.get('ibkr_mode')}")
        print(f"   PO Mode: {policy.get('po_mode')}")
    print()
    
    # Resumen
    print("=" * 80)
    print("RESUMEN EJECUTIVO")
    print("=" * 80)
    
    all_ok = (
        brain.get('healthy') and
        ibkr.get('order_api_ready') and
        po.get('connected') and
        meta.get('work_status') == 'internal_execution_ready'
    )
    
    if all_ok:
        print("[OK] Sistema operativo y listo para ejecutar trades")
        print()
        print("Flujo de ejecucion:")
        print("  1. Meta-roadmap identifica gap 'strategy_sample_depth'")
        print("  2. Action Executor ejecuta 'increase_resolved_sample'")
        print("  3. Strategy Engine verifica senales tecnicas")
        print("  4. Selecciona venue (IBKR/PO) segun estrategia")
        print("  5. Ejecuta trades paper reales")
        print("  6. Actualiza scorecard y meta-execution ledger")
        print()
        print("Proxima accion: Esperando gap activo para ejecutar")
    else:
        print("[ATENCION] Algunos componentes requieren revision")
        if not brain.get('healthy'):
            print("  - Brain V9 no responde")
        if not ibkr.get('order_api_ready'):
            print("  - IBKR Order API no lista")
        if not po.get('connected'):
            print("  - PO Bridge desconectado")
    
    print()
    print(f"Verificado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

if __name__ == "__main__":
    main()
