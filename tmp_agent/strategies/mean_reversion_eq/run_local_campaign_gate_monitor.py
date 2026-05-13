import json
import logging
import math
import os
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf
from ib_insync import IB, Stock, util

warnings.filterwarnings("ignore")
logging.getLogger("ib_insync").setLevel(logging.CRITICAL)
logging.getLogger("ib_insync.client").setLevel(logging.CRITICAL)
logging.getLogger("ib_insync.wrapper").setLevel(logging.CRITICAL)

ROOT = Path(r"C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq")
OUT_JSON = ROOT / "campaign_gate_status_latest.json"
OUT_TXT = ROOT / "campaign_gate_status_latest.txt"
CACHE = ROOT / "campaign_gate_market_cache"
CACHE.mkdir(exist_ok=True)

TICKERS = ["SPY", "QQQ", "IWM", "VIXY"]
IBKR_PORTS = [7497, 4002, 7496, 4001]
IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "197"))
IBKR_TIMEOUT = float(os.getenv("IBKR_TIMEOUT_SEC", "8"))
IBKR_HISTORY_TIMEOUT = float(os.getenv("IBKR_HISTORY_TIMEOUT_SEC", "12"))

IWM_DD50_THR = -0.0511294
QQQ_RV20_THR = 0.174213
IWM_RNG10_THR = 0.0152915
EPISODE_GAP_DAYS = 21
ACTIVE_LOOKBACK_DAYS = 45
ACTIVATION_START_DAY = 21
ACTIVATION_END_DAY = 28
LATE_END_DAY = 35


def cache_file(ticker: str, provider: str) -> Path:
    return CACHE / f"{ticker}_{provider}.csv"


def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [c[0] for c in out.columns]
    if "date" in out.columns:
        out = out.rename(columns={"date": "Date"})
    required = ["Open", "High", "Low", "Close"]
    rename_map = {c: c.capitalize() for c in out.columns if c.lower() in {"open", "high", "low", "close", "volume"}}
    out = out.rename(columns=rename_map)
    if "Date" in out.columns:
        out["Date"] = pd.to_datetime(out["Date"])
        out = out.set_index("Date")
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    out = out.dropna(subset=[c for c in required if c in out.columns], how="any")
    return out


def try_connect_ibkr():
    attempts = []
    for port in IBKR_PORTS:
        ib = IB()
        try:
            ib.connect(IBKR_HOST, port, clientId=IBKR_CLIENT_ID, timeout=IBKR_TIMEOUT, readonly=True)
            if ib.isConnected():
                return ib, {"connected": True, "host": IBKR_HOST, "port": port, "client_id": IBKR_CLIENT_ID}
        except Exception as exc:
            attempts.append({"host": IBKR_HOST, "port": port, "error": str(exc)})
        finally:
            if not ib.isConnected():
                try:
                    ib.disconnect()
                except Exception:
                    pass
    return None, {"connected": False, "host": IBKR_HOST, "client_id": IBKR_CLIENT_ID, "attempts": attempts}


def download_ibkr(ticker: str, ib: IB) -> pd.DataFrame:
    contract = Stock(ticker, "SMART", "USD")
    ib.qualifyContracts(contract)
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr="300 D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
        timeout=IBKR_HISTORY_TIMEOUT,
    )
    if not bars:
        raise RuntimeError(f"No IBKR historical bars returned for {ticker}")
    df = util.df(bars)
    if df is None or df.empty:
        raise RuntimeError(f"Empty IBKR dataframe for {ticker}")
    df = normalize_history(df)
    df.to_csv(cache_file(ticker, "ibkr"), index_label="Date")
    return df


def download_yf(ticker: str) -> pd.DataFrame:
    end = (datetime.now().date() + timedelta(days=1)).isoformat()
    start = (datetime.now().date() - timedelta(days=300)).isoformat()
    fp = cache_file(ticker, "yfinance")
    try:
        df = yf.download(
            ticker,
            start=start,
            end=end,
            auto_adjust=False,
            progress=False,
            threads=False,
            timeout=30,
        )
        df = normalize_history(df)
        if not df.empty:
            df.to_csv(fp, index_label="Date")
            return df
    except Exception:
        pass
    if fp.exists():
        return normalize_history(pd.read_csv(fp))
    raise RuntimeError(f"No market data available for {ticker}")


def load_market_data():
    provider_by_ticker = {}
    provider_errors = {}
    ib, ibkr_status = try_connect_ibkr()
    data = {}
    try:
        for ticker in TICKERS:
            if ib and ib.isConnected():
                try:
                    data[ticker] = download_ibkr(ticker, ib)
                    provider_by_ticker[ticker] = "ibkr"
                    continue
                except Exception as exc:
                    provider_errors.setdefault(ticker, []).append(f"ibkr:{exc}")
            data[ticker] = download_yf(ticker)
            provider_by_ticker[ticker] = "yfinance"
    finally:
        if ib and ib.isConnected():
            ib.disconnect()
    return data, provider_by_ticker, provider_errors, ibkr_status


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ret1"] = out["Close"].pct_change()
    for n in [5, 10, 20, 50]:
        out[f"rv{n}"] = out["ret1"].rolling(n).std() * math.sqrt(252)
        out[f"rng{n}"] = ((out["High"] - out["Low"]) / out["Close"]).rolling(n).mean()
        out[f"dd{n}"] = out["Close"] / out["High"].rolling(n).max() - 1
    out["gap1"] = (out["Open"] - out["Close"].shift(1)) / out["Close"].shift(1)
    return out


def gate_at(ind, dt):
    q = ind["QQQ"].loc[:dt]
    i = ind["IWM"].loc[:dt]
    if len(q) < 51 or len(i) < 51:
        return None
    qlast = q.iloc[-1]
    ilast = i.iloc[-1]
    f = {
        "date": pd.Timestamp(dt).date().isoformat(),
        "qqq_rv20": float(qlast["rv20"]),
        "iwm_dd50": float(ilast["dd50"]),
        "iwm_rng10": float(ilast["rng10"]),
        "iwm_gap1": float(ilast["gap1"]),
    }
    f["base_gate"] = bool(
        f["iwm_dd50"] <= IWM_DD50_THR
        and f["qqq_rv20"] >= QQQ_RV20_THR
        and f["iwm_rng10"] <= IWM_RNG10_THR
    )
    return f


def weekly_signals(ind):
    common = sorted(set(ind["QQQ"].index).intersection(set(ind["IWM"].index)))
    signals = []
    details = []
    for dt in common:
        if pd.Timestamp(dt).weekday() != 4:
            continue
        f = gate_at(ind, dt)
        if not f:
            continue
        if f["base_gate"]:
            signal_date = pd.Timestamp(dt).date() + timedelta(days=2)
            signals.append(signal_date)
            detail = dict(f)
            detail["signal_date"] = signal_date.isoformat()
            details.append(detail)
    return signals, details


def active_campaign(signals, today):
    if not signals:
        return None, None
    episodes = []
    cur = []
    for sig in signals:
        if not cur or (sig - cur[-1]).days <= EPISODE_GAP_DAYS:
            cur.append(sig)
        else:
            episodes.append(cur)
            cur = [sig]
    if cur:
        episodes.append(cur)
    ep = episodes[-1]
    if (today - ep[-1]).days > ACTIVE_LOOKBACK_DAYS:
        return None, ep[-1]
    return ep[0], ep[-1]


def classify(campaign_start, today):
    if campaign_start is None:
        return -1, "NO_CAMPAIGN", "NO_BUY"
    age = (today - campaign_start).days
    if age < ACTIVATION_START_DAY:
        return age, "WAIT_MATURITY", "WATCH_ONLY"
    if ACTIVATION_START_DAY <= age <= ACTIVATION_END_DAY:
        return age, "ACTIVATION_WINDOW", "BUY_OR_ACTIVATE_ALLOWED"
    if ACTIVATION_END_DAY < age <= LATE_END_DAY:
        return age, "LATE_RISK_CONSISTENCY", "DO_NOT_BUY_LATE_UNLESS_MANUAL_OVERRIDE"
    return age, "EXPIRED", "NO_BUY_WAIT_NEXT_CAMPAIGN"


def main():
    data, providers, provider_errors, ibkr_status = load_market_data()
    ind = {ticker: indicators(df) for ticker, df in data.items()}
    today = datetime.now().date()
    signals, signal_details = weekly_signals(ind)
    start, last = active_campaign(signals, today)
    age, state, action = classify(start, today)
    latest_dt = min(ind["QQQ"].dropna().index[-1], ind["IWM"].dropna().index[-1])
    latest = gate_at(ind, latest_dt)
    days_to_window = -1 if start is None else max(0, ACTIVATION_START_DAY - age)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "today": today.isoformat(),
        "state": state,
        "action": action,
        "campaign_start": start.isoformat() if start else None,
        "last_signal": last.isoformat() if last else None,
        "campaign_age_days": age,
        "days_to_activation_window": days_to_window,
        "latest_features": latest,
        "signal_count": len(signals),
        "signals": [s.isoformat() for s in signals[-10:]],
        "signal_details_tail": signal_details[-5:],
        "providers": providers,
        "provider_errors": provider_errors,
        "ibkr_status": ibkr_status,
        "rules": {
            "iwm_dd50_lte": IWM_DD50_THR,
            "qqq_rv20_gte": QQQ_RV20_THR,
            "iwm_rng10_lte": IWM_RNG10_THR,
            "activation_days": [ACTIVATION_START_DAY, ACTIVATION_END_DAY],
            "late_end_day": LATE_END_DAY,
        },
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "PF CAMPAIGN GATE STATUS",
        f"generated_at_utc={payload['generated_at_utc']}",
        f"state={state}",
        f"action={action}",
        f"campaign_start={payload['campaign_start']}",
        f"last_signal={payload['last_signal']}",
        f"campaign_age_days={age}",
        f"days_to_activation_window={days_to_window}",
        f"signal_count={len(signals)}",
        "",
        f"ibkr_connected={ibkr_status.get('connected')}",
        f"ibkr_host={ibkr_status.get('host')}",
        f"ibkr_port={ibkr_status.get('port')}",
        f"providers={providers}",
        "",
        "Latest features:",
        f"  base_gate={latest.get('base_gate') if latest else None}",
        f"  iwm_dd50={latest.get('iwm_dd50') if latest else None:.6f}",
        f"  qqq_rv20={latest.get('qqq_rv20') if latest else None:.6f}",
        f"  iwm_rng10={latest.get('iwm_rng10') if latest else None:.6f}",
        "",
        "Recent signals:",
    ]
    lines += [f"  {s}" for s in payload["signals"]]
    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"JSON={OUT_JSON}")


if __name__ == "__main__":
    main()
