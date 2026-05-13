import json
import os
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path


ROOT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq")
STATUS_JSON = ROOT / "campaign_gate_status_latest.json"
OUT_JSON = ROOT / "campaign_gate_email_last_send.json"
OUT_TXT = ROOT / "campaign_gate_email_last_send.txt"
ENV_CANDIDATES = [
    Path(r"C:/AI_VAULT/Secrets/email_alerts.env"),
    Path(r"C:/AI_VAULT/.env"),
    Path(
        r"C:/Users/cesar/OneDrive/Escritorio/Memoria 32/Personal/TradingBot/Proyecto 2. GitHub-Render-Alapaca-Tastytrade/.env"
    ),
]


def load_env_files():
    loaded = []
    for path in ENV_CANDIDATES:
        if not path.exists():
            continue
        loaded.append(str(path))
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    return loaded


def get_config():
    loaded = load_env_files()
    return {
        "loaded_env_files": loaded,
        "email_user": os.getenv("EMAIL_USER", "").strip(),
        "email_pass": os.getenv("EMAIL_PASS", "").strip(),
        "email_to": (os.getenv("EMAIL_TO") or os.getenv("EMAIL_USER") or "").strip(),
        "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        "smtp_port": int(os.getenv("SMTP_PORT", "465").strip()),
    }


def load_status():
    if not STATUS_JSON.exists():
        raise FileNotFoundError(f"No existe {STATUS_JSON}")
    return json.loads(STATUS_JSON.read_text(encoding="utf-8"))


def compose_subject(status):
    state = status.get("state", "UNKNOWN")
    if state == "ACTIVATION_WINDOW":
        return f"ALERTA PF Campaign Gate: {state}"
    if state == "LATE_RISK_CONSISTENCY":
        return f"ADVERTENCIA PF Campaign Gate: {state}"
    return f"PF Campaign Gate Diario: {state}"


def compose_body(status):
    latest = status.get("latest_features") or {}
    ibkr_status = status.get("ibkr_status") or {}
    providers = status.get("providers") or {}
    provider_errors = status.get("provider_errors") or {}
    provider_lines = "\n".join(f"- {k}: {v}" for k, v in providers.items()) or "- NONE"
    provider_error_lines = "\n".join(
        f"- {ticker}: {' | '.join(errors)}" for ticker, errors in provider_errors.items()
    ) or "- NONE"
    return (
        "PF Campaign Gate Diario\n\n"
        f"Estado: {status.get('state')}\n"
        f"Accion: {status.get('action')}\n"
        f"Campana inicio: {status.get('campaign_start') or 'NONE'}\n"
        f"Ultima senal: {status.get('last_signal') or 'NONE'}\n"
        f"Edad campana: {status.get('campaign_age_days')}\n"
        f"Dias a ventana: {status.get('days_to_activation_window')}\n"
        f"Signal count: {status.get('signal_count')}\n"
        "\nLatest features:\n"
        f"Base gate: {latest.get('base_gate')}\n"
        f"IWM_DD50: {latest.get('iwm_dd50')}\n"
        f"QQQ_RV20: {latest.get('qqq_rv20')}\n"
        f"IWM_RNG10: {latest.get('iwm_rng10')}\n"
        f"IWM_GAP1: {latest.get('iwm_gap1')}\n"
        "\nFuente de datos:\n"
        f"IBKR conectado: {ibkr_status.get('connected')}\n"
        f"IBKR host: {ibkr_status.get('host')}\n"
        f"IBKR port: {ibkr_status.get('port')}\n"
        "Providers por ticker:\n"
        f"{provider_lines}\n"
        "Errores de provider:\n"
        f"{provider_error_lines}\n"
        "\nSignals:\n"
        + "\n".join(f"- {sig}" for sig in status.get("signals", []))
        + "\n\n"
        f"Timestamp UTC: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
    )


def send_email(cfg, subject, body):
    missing = [k for k in ("email_user", "email_pass", "email_to") if not cfg.get(k)]
    if missing:
        return {
            "ok": False,
            "mode": "not_sent_missing_config",
            "missing": missing,
            "hint": "Configura EMAIL_USER, EMAIL_PASS y opcionalmente EMAIL_TO.",
        }
    if cfg["email_user"].startswith("your_") or cfg["email_pass"].startswith("your_"):
        return {
            "ok": False,
            "mode": "not_sent_placeholder_config",
            "to": cfg["email_to"],
            "hint": "EMAIL_USER/EMAIL_PASS actuales son placeholders. Usa un correo real y una app password valida.",
        }
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = cfg["email_user"]
    msg["To"] = cfg["email_to"]
    try:
        with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=45) as server:
            server.login(cfg["email_user"], cfg["email_pass"])
            server.sendmail(cfg["email_user"], [cfg["email_to"]], msg.as_string())
        return {
            "ok": True,
            "mode": "smtp_ssl",
            "smtp_host": cfg["smtp_host"],
            "smtp_port": cfg["smtp_port"],
            "to": cfg["email_to"],
        }
    except Exception as exc:
        return {
            "ok": False,
            "mode": "smtp_ssl_exception",
            "smtp_host": cfg["smtp_host"],
            "smtp_port": cfg["smtp_port"],
            "to": cfg["email_to"],
            "error": str(exc),
        }


def main():
    cfg = get_config()
    status = load_status()
    subject = compose_subject(status)
    body = compose_body(status)
    result = send_email(cfg, subject, body)
    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status_state": status.get("state"),
        "status_action": status.get("action"),
        "subject": subject,
        "send_result": result,
        "loaded_env_files": cfg.get("loaded_env_files"),
    }
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    lines = [
        f"generated_at_utc={out['generated_at_utc']}",
        f"state={out['status_state']}",
        f"action={out['status_action']}",
        f"send_ok={result.get('ok')}",
        f"mode={result.get('mode')}",
        f"smtp_host={result.get('smtp_host')}",
        f"smtp_port={result.get('smtp_port')}",
        f"to={result.get('to')}",
        f"error={result.get('error') or result.get('hint')}",
        "",
        f"SUBJECT: {subject}",
    ]
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
