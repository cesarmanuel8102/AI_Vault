import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq')
STATUS_JSON = ROOT / 'campaign_gate_status_latest.json'
OUT_JSON = ROOT / 'campaign_gate_whatsapp_last_send.json'
OUT_TXT = ROOT / 'campaign_gate_whatsapp_last_send.txt'
ENV_CANDIDATES = [
    Path(r'C:/AI_VAULT/Secrets/whatsapp_twilio.env'),
    Path(r'C:/AI_VAULT/.env'),
    Path(r'C:/Users/cesar/OneDrive/Escritorio/Memoria 32/Personal/TradingBot/Proyecto 2. GitHub-Render-Alapaca-Tastytrade/.env'),
]


def load_env_files():
    loaded = []
    for path in ENV_CANDIDATES:
        if not path.exists():
            continue
        loaded.append(str(path))
        for raw in path.read_text(encoding='utf-8', errors='ignore').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, val = line.split('=', 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    return loaded


def normalize_whatsapp(value):
    if not value:
        return ''
    value = str(value).strip()
    if value.startswith('whatsapp:'):
        return value
    return 'whatsapp:' + value


def get_config():
    loaded = load_env_files()
    sid = os.getenv('TWILIO_ACCOUNT_SID') or os.getenv('TWILIO_SID')
    token = os.getenv('TWILIO_AUTH_TOKEN') or os.getenv('TWILIO_AUTH')
    from_ = os.getenv('TWILIO_WHATSAPP_FROM') or os.getenv('TWILIO_PHONE')
    to = os.getenv('WHATSAPP_TO') or os.getenv('USER_PHONE')
    return {
        'loaded_env_files': loaded,
        'sid': sid,
        'token': token,
        'from': normalize_whatsapp(from_),
        'to': normalize_whatsapp(to),
    }


def load_status():
    if not STATUS_JSON.exists():
        raise FileNotFoundError(f'No existe {STATUS_JSON}')
    return json.loads(STATUS_JSON.read_text(encoding='utf-8'))


def compose_message(status):
    state = status.get('state', 'UNKNOWN')
    action = status.get('action', 'UNKNOWN')
    age = status.get('campaign_age_days', 'NA')
    start = status.get('campaign_start') or 'NONE'
    last = status.get('last_signal') or 'NONE'
    days_to = status.get('days_to_activation_window', 'NA')
    latest = status.get('latest_features') or {}
    base = latest.get('base_gate')
    iwm_dd50 = latest.get('iwm_dd50')
    qqq_rv20 = latest.get('qqq_rv20')
    iwm_rng10 = latest.get('iwm_rng10')

    title = 'PF Campaign Gate Diario'
    if state == 'ACTIVATION_WINDOW':
        title = 'ALERTA PF: ACTIVATION_WINDOW'
    elif state == 'LATE_RISK_CONSISTENCY':
        title = 'ADVERTENCIA PF: LATE_RISK_CONSISTENCY'

    return (
        f'{title}\n'
        f'Estado: {state}\n'
        f'Accion: {action}\n'
        f'Campana inicio: {start}\n'
        f'Ultima senal: {last}\n'
        f'Edad campana: {age} dias\n'
        f'Dias a ventana: {days_to}\n'
        f'Base gate hoy: {base}\n'
        f'IWM_DD50: {iwm_dd50}\n'
        f'QQQ_RV20: {qqq_rv20}\n'
        f'IWM_RNG10: {iwm_rng10}\n'
        f'Timestamp UTC: {datetime.now(timezone.utc).isoformat(timespec="seconds")}\n'
    )


def _post_twilio(cfg, body):
    url = f'https://api.twilio.com/2010-04-01/Accounts/{quote(cfg["sid"])}/Messages.json'
    data = {'From': cfg['from'], 'To': cfg['to'], 'Body': body}
    r = requests.post(url, data=data, auth=(cfg['sid'], cfg['token']), timeout=45)
    try:
        payload = r.json()
    except Exception:
        payload = {'text': r.text[:1000]}
    return {
        'ok': 200 <= r.status_code < 300,
        'mode': 'twilio_whatsapp',
        'status_code': r.status_code,
        'sid': payload.get('sid'),
        'status': payload.get('status'),
        'error_code': payload.get('code') or payload.get('error_code'),
        'error_message': payload.get('message') or payload.get('error_message'),
        'from': cfg['from'],
        'to': cfg['to'],
    }


def send_twilio_whatsapp(cfg, body):
    missing = [k for k in ('sid', 'token', 'from', 'to') if not cfg.get(k)]
    if missing:
        return {
            'ok': False,
            'mode': 'not_sent_missing_config',
            'missing': missing,
            'hint': 'Configura TWILIO_SID, TWILIO_AUTH, TWILIO_WHATSAPP_FROM/TWILIO_PHONE y WHATSAPP_TO/USER_PHONE.',
        }
    try:
        result = _post_twilio(cfg, body)
        # Error 63007 usually means the configured From number is SMS-only.
        # Retry with Twilio's WhatsApp sandbox number if no explicit WhatsApp
        # sender was configured. The recipient must have joined the sandbox.
        if (
            not result.get('ok')
            and str(result.get('error_code')) == '63007'
            and not os.getenv('TWILIO_WHATSAPP_FROM')
        ):
            retry_cfg = dict(cfg)
            retry_cfg['from'] = 'whatsapp:+14155238886'
            retry = _post_twilio(retry_cfg, body)
            retry['fallback_from_sms_number'] = cfg.get('from')
            retry['fallback_reason'] = 'configured sender is not a WhatsApp channel'
            return retry
        return result
    except Exception as exc:
        return {'ok': False, 'mode': 'twilio_whatsapp_exception', 'error': str(exc), 'from': cfg.get('from'), 'to': cfg.get('to')}


def main():
    cfg = get_config()
    status = load_status()
    body = compose_message(status)
    result = send_twilio_whatsapp(cfg, body)
    out = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'status_state': status.get('state'),
        'status_action': status.get('action'),
        'message_preview': body,
        'send_result': result,
        'loaded_env_files': cfg.get('loaded_env_files'),
    }
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding='utf-8')
    lines = [
        f"generated_at_utc={out['generated_at_utc']}",
        f"state={out['status_state']}",
        f"action={out['status_action']}",
        f"send_ok={result.get('ok')}",
        f"mode={result.get('mode')}",
        f"status_code={result.get('status_code')}",
        f"twilio_status={result.get('status')}",
        f"error_code={result.get('error_code')}",
        f"error_message={result.get('error_message') or result.get('error') or result.get('hint')}",
        '',
        'MESSAGE:',
        body,
    ]
    OUT_TXT.write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))
    return 0 if result.get('ok') else 2


if __name__ == '__main__':
    raise SystemExit(main())
