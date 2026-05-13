import json
import time
import hashlib
import base64
import re
from datetime import datetime
from pathlib import Path
import requests

BASE = 'https://www.quantconnect.com/api/v2'
PROJECT_ID = 29652652
CODE_PATH = Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/main.py')
SECRETS_PATH = Path(r'C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json')
OUT_JSON = Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/live_safety_regression_2026-04-14.json')
OUT_TXT = Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/live_safety_regression_2026-04-14.txt')


def load_creds():
    d = json.loads(SECRETS_PATH.read_text(encoding='utf-8'))
    uid = str(d.get('user_id') or d.get('userId') or '').strip()
    tok = str(d.get('api_token') or d.get('apiToken') or d.get('token') or '').strip()
    if not uid or not tok:
        raise RuntimeError('Credenciales QC inválidas')
    return uid, tok


def headers(uid, tok, ts=None):
    ts = int(ts or time.time())
    sig = hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest()
    basic = base64.b64encode(f"{uid}:{sig}".encode()).decode()
    return {
        'Authorization': f'Basic {basic}',
        'Timestamp': str(ts),
        'Content-Type': 'application/json'
    }


def api_post(uid, tok, endpoint, payload, timeout=90):
    ts = int(time.time())
    r = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts), json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if data.get('success', False):
        return data
    errs = ' '.join(data.get('errors') or [])
    m = re.search(r'Server Time:\s*(\d+)', errs)
    if m:
        ts2 = int(m.group(1)) - 1
        r2 = requests.post(f"{BASE}/{endpoint}", headers=headers(uid, tok, ts2), json=payload, timeout=timeout)
        r2.raise_for_status()
        return r2.json()
    return data


def parse_float(x):
    try:
        return float(str(x).replace('%', '').replace('$', '').replace(',', '').strip())
    except Exception:
        return None


def get_rt_value(rt, key):
    if isinstance(rt, dict):
        return rt.get(key)
    if isinstance(rt, list):
        for item in rt:
            if not isinstance(item, dict):
                continue
            name = item.get('name') or item.get('Name')
            if str(name) == key:
                return item.get('value') or item.get('Value')
    return None


def get_project_params(uid, tok):
    pr = api_post(uid, tok, 'projects/read', {'projectId': PROJECT_ID}, timeout=60)
    projects = pr.get('projects') or []
    if not projects:
        raise RuntimeError(f'No se pudo leer project {PROJECT_ID}')
    params = {}
    for p in projects[0].get('parameters') or []:
        k = p.get('key')
        v = p.get('value')
        if k:
            params[str(k)] = '' if v is None else str(v)
    return params


def set_params(uid, tok, params):
    payload = {
        'projectId': PROJECT_ID,
        'parameters': [{'key': k, 'value': str(v)} for k, v in params.items()]
    }
    resp = api_post(uid, tok, 'projects/update', payload, timeout=60)
    if not resp.get('success', False):
        raise RuntimeError(f'projects/update failed: {resp}')


def upload_code(uid, tok):
    code = CODE_PATH.read_text(encoding='utf-8')
    up = api_post(uid, tok, 'files/update', {'projectId': PROJECT_ID, 'name': 'main.py', 'content': code}, timeout=120)
    if not up.get('success', False):
        raise RuntimeError(f'files/update failed: {up}')


def compile_project(uid, tok):
    c = api_post(uid, tok, 'compile/create', {'projectId': PROJECT_ID}, timeout=90)
    cid = c.get('compileId')
    if not cid:
        raise RuntimeError(f'compile/create failed: {c}')
    for _ in range(120):
        r = api_post(uid, tok, 'compile/read', {'projectId': PROJECT_ID, 'compileId': cid}, timeout=60)
        st = r.get('state', '')
        if st in ('BuildSuccess', 'BuildWarning', 'BuildError', 'BuildAborted'):
            if st != 'BuildSuccess':
                raise RuntimeError(f'Compile no exitoso: {st} | {r}')
            return cid
        time.sleep(2)
    raise RuntimeError('compile timeout')


def run_backtest(uid, tok, cid, name):
    bt = api_post(uid, tok, 'backtests/create', {'projectId': PROJECT_ID, 'compileId': cid, 'backtestName': name}, timeout=90)
    bid = ((bt.get('backtest') or {}).get('backtestId'))
    if not bid:
        raise RuntimeError(f'backtests/create failed: {bt}')

    for _ in range(240):
        rd = api_post(uid, tok, 'backtests/read', {'projectId': PROJECT_ID, 'backtestId': bid}, timeout=90)
        b = rd.get('backtest') or {}
        st = str(b.get('status', ''))
        if 'Completed' in st:
            stats = b.get('statistics') or {}
            rt = b.get('runtimeStatistics') or {}
            return {
                'name': name,
                'backtest_id': bid,
                'status': st,
                'np_pct': parse_float(stats.get('Net Profit')),
                'dd_pct': parse_float(stats.get('Drawdown')),
                'sharpe': parse_float(stats.get('Sharpe Ratio')),
                'dbr': parse_float(get_rt_value(rt, 'DailyLossBreaches')),
                'tbr': parse_float(get_rt_value(rt, 'TrailingBreaches')),
                'orders': parse_float(stats.get('Total Orders')),
            }
        if ('Error' in st) or ('Runtime' in st) or ('Aborted' in st):
            return {
                'name': name,
                'backtest_id': bid,
                'status': st,
                'error': (b.get('error') or b.get('message') or 'backtest failed')
            }
        time.sleep(15)
    return {'name': name, 'backtest_id': bid, 'status': 'Timeout'}


def main():
    uid, tok = load_creds()
    original_params = get_project_params(uid, tok)

    base = dict(original_params)
    # Seguridad live-only (no afecta BT por diseño)
    base.update({
        'live_safety_enabled': '1',
        'live_max_price_staleness_minutes': '5',
        'live_order_error_lock_enabled': '1',
        'live_max_order_errors_per_day': '3',
    })

    scenarios = [
        ('REG_FULL_2022_2026Q1', {'start_year': '2022', 'start_month': '1', 'start_day': '1', 'end_year': '2026', 'end_month': '3', 'end_day': '31'}),
        ('REG_OOS_2025_2026Q1', {'start_year': '2025', 'start_month': '1', 'start_day': '1', 'end_year': '2026', 'end_month': '3', 'end_day': '31'}),
        ('REG_STRESS_2020', {'start_year': '2020', 'start_month': '1', 'start_day': '1', 'end_year': '2020', 'end_month': '12', 'end_day': '31'}),
    ]

    results = {
        'generated_at_utc': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'project_id': PROJECT_ID,
        'results': []
    }

    try:
        upload_code(uid, tok)
        set_params(uid, tok, base)
        cid = compile_project(uid, tok)
        results['compile_id'] = cid

        for name, date_params in scenarios:
            p = dict(base)
            p.update(date_params)
            set_params(uid, tok, p)
            r = run_backtest(uid, tok, cid, f"{name}_{int(time.time())}")
            r['scenario'] = name
            r['date_params'] = date_params
            results['results'].append(r)

        # dejar listo para live con params base + safety
        set_params(uid, tok, base)

    finally:
        OUT_JSON.write_text(json.dumps(results, indent=2), encoding='utf-8')
        lines = [f"generated_at_utc={results.get('generated_at_utc')}", f"project_id={PROJECT_ID}", f"compile_id={results.get('compile_id','')}"]
        for r in results.get('results', []):
            lines.append(
                f"{r.get('scenario')} status={r.get('status')} np={r.get('np_pct')} dd={r.get('dd_pct')} sharpe={r.get('sharpe')} dbr={r.get('dbr')} tbr={r.get('tbr')} orders={r.get('orders')} id={r.get('backtest_id')}"
            )
        OUT_TXT.write_text('\n'.join(lines), encoding='utf-8')
        print(json.dumps({'ok': True, 'out_json': str(OUT_JSON), 'out_txt': str(OUT_TXT), 'results': results.get('results', [])}, indent=2))


if __name__ == '__main__':
    main()
