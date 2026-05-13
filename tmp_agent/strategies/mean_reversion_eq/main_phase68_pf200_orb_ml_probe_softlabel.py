
from AlgorithmImports import *
import json
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score, precision_score, recall_score


class PF200OrbMlProbe(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2026, 3, 31)
        self.SetCash(100000)
        self.SetTimeZone(TimeZones.NewYork)
        self.UniverseSettings.Resolution = Resolution.Minute

        self.or_minutes = 15
        self.slots = [("ORB1", 10, 15), ("ORB2", 11, 0)]
        self.fwd_minutes = 120
        self.opportunity_atr = 0.60
        self.features = [
            "gap_pct", "or_width_atr", "day_range_atr", "intraday_mom",
            "long_break", "short_break", "uptrend", "downtrend", "rv20", "prev_range_pct"
        ]
        self.threshold_grid = [0.50, 0.55, 0.60, 0.65]
        self.splits = {
            "IS": (datetime(2022, 1, 1).date(), datetime(2024, 12, 31).date()),
            "OOS": (datetime(2025, 1, 1).date(), datetime(2026, 3, 31).date()),
            "STRESS": (datetime(2020, 1, 1).date(), datetime(2020, 12, 31).date()),
        }

        self.instruments = {}
        self.state = {}
        self.rows = []
        self.failures = []

        self._add_instrument(Futures.Indices.MicroNASDAQ100EMini, "MNQ")
        self._add_instrument(Futures.Indices.MicroSP500EMini, "MES")

        self.SetWarmUp(70, Resolution.Daily)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(15, 58), self._finalize_day)

    def _add_instrument(self, future_type, name):
        fut = self.AddFuture(future_type, Resolution.Minute)
        fut.SetFilter(0, 182)
        sym = fut.Symbol
        atr = self.ATR(sym, 14, MovingAverageType.Simple, Resolution.Daily)
        trend = self.EMA(sym, 55, Resolution.Daily)
        ret_window = RollingWindow[float](25)
        range_window = RollingWindow[float](25)
        prev_close = {"v": None}
        rv20 = {"v": np.nan}
        prev_range_pct = {"v": np.nan}
        cons = TradeBarConsolidator(timedelta(days=1))

        def on_daily(_, bar):
            close = float(bar.Close)
            high = float(bar.High)
            low = float(bar.Low)
            pc = prev_close["v"]
            if pc is not None and pc > 0:
                ret_window.Add((close - pc) / pc)
                prev_range_pct["v"] = (high - low) / pc
                range_window.Add(prev_range_pct["v"])
                if ret_window.Count >= 20:
                    vals = [float(ret_window[i]) for i in range(ret_window.Count)]
                    rv20["v"] = float(np.std(vals[-20:], ddof=1) * np.sqrt(252)) if len(vals) >= 20 else np.nan
            prev_close["v"] = close

        cons.DataConsolidated += on_daily
        self.SubscriptionManager.AddConsolidator(sym, cons)
        self.instruments[name] = {
            "future": fut,
            "symbol": sym,
            "atr": atr,
            "trend": trend,
            "prev_close": prev_close,
            "rv20": rv20,
            "prev_range_pct": prev_range_pct,
        }

    def _new_state(self, day):
        return {
            "date": day,
            "session_open": None,
            "session_high": None,
            "session_low": None,
            "or_high": None,
            "or_low": None,
            "created_slots": set(),
            "pending": [],
        }

    def OnData(self, data):
        if self.IsWarmingUp:
            return
        now = self.Time
        day = now.date()
        hhmm = now.hour * 100 + now.minute

        for name, info in self.instruments.items():
            mapped = info["future"].Mapped
            if mapped is None:
                continue
            bar = data.Bars.get(mapped)
            if bar is None:
                continue

            st = self.state.get(name)
            if st is None or st["date"] != day:
                if st is not None:
                    self._flush_state(st)
                st = self._new_state(day)
                self.state[name] = st

            if hhmm < 930:
                continue

            price_open = float(bar.Open)
            price_high = float(bar.High)
            price_low = float(bar.Low)
            price_close = float(bar.Close)

            if st["session_open"] is None:
                st["session_open"] = price_open
                st["session_high"] = price_high
                st["session_low"] = price_low
            else:
                st["session_high"] = max(st["session_high"], price_high)
                st["session_low"] = min(st["session_low"], price_low)

            if hhmm <= 945:
                st["or_high"] = price_high if st["or_high"] is None else max(st["or_high"], price_high)
                st["or_low"] = price_low if st["or_low"] is None else min(st["or_low"], price_low)

            self._update_pending(st, now, price_high, price_low)

            for slot_name, sh, sm in self.slots:
                slot_hhmm = sh * 100 + sm
                if hhmm == slot_hhmm and slot_name not in st["created_slots"]:
                    self._create_candidate(name, info, st, slot_name, now, price_close)
                    st["created_slots"].add(slot_name)

    def _update_pending(self, st, now, high, low):
        remaining = []
        for row in st["pending"]:
            if now <= row["slot_time"]:
                remaining.append(row)
                continue
            if not row["long_done"] and high >= row["long_target"]:
                row["y_long"] = 1
                row["long_done"] = True
            if not row["short_done"] and low <= row["short_target"]:
                row["y_short"] = 1
                row["short_done"] = True
            if now >= row["expiry"]:
                row["long_done"] = True
                row["short_done"] = True
            if row["long_done"] and row["short_done"]:
                self.rows.append(self._finalize_row(row))
            else:
                remaining.append(row)
        st["pending"] = remaining

    def _create_candidate(self, name, info, st, slot_name, now, px):
        atr_ind = info["atr"]
        trend_ind = info["trend"]
        prev_close = info["prev_close"]["v"]
        rv20 = info["rv20"]["v"]
        prev_range_pct = info["prev_range_pct"]["v"]
        if st["session_open"] is None or st["or_high"] is None or st["or_low"] is None:
            return
        if prev_close is None or prev_close <= 0 or not atr_ind.IsReady or not trend_ind.IsReady:
            return
        atr = float(atr_ind.Current.Value)
        trend = float(trend_ind.Current.Value)
        if not np.isfinite(atr) or atr <= 0:
            return
        gap_pct = (st["session_open"] - prev_close) / prev_close if prev_close > 0 else 0.0
        or_width_atr = (st["or_high"] - st["or_low"]) / atr
        day_range_atr = (st["session_high"] - st["session_low"]) / atr
        intraday_mom = (px - st["session_open"]) / st["session_open"] if st["session_open"] > 0 else 0.0
        long_break = 1.0 if px > st["or_high"] else 0.0
        short_break = 1.0 if px < st["or_low"] else 0.0
        uptrend = 1.0 if px > trend else 0.0
        downtrend = 1.0 if px < trend else 0.0
        row = {
            "symbol": name,
            "date": st["date"],
            "slot": slot_name,
            "gap_pct": float(gap_pct),
            "or_width_atr": float(or_width_atr),
            "day_range_atr": float(day_range_atr),
            "intraday_mom": float(intraday_mom),
            "long_break": float(long_break),
            "short_break": float(short_break),
            "uptrend": float(uptrend),
            "downtrend": float(downtrend),
            "rv20": float(rv20) if rv20 is not None and np.isfinite(rv20) else np.nan,
            "prev_range_pct": float(prev_range_pct) if prev_range_pct is not None and np.isfinite(prev_range_pct) else np.nan,
            "entry": float(px),
            "slot_time": now,
            "expiry": now + timedelta(minutes=self.fwd_minutes),
            "long_target": float(px + self.opportunity_atr * atr),
            "short_target": float(px - self.opportunity_atr * atr),
            "y_long": 0,
            "y_short": 0,
            "long_done": False,
            "short_done": False,
        }
        st["pending"].append(row)

    def _finalize_row(self, row):
        out = {k: row[k] for k in ["symbol", "date", "slot"] + self.features}
        out["y_long"] = int(row["y_long"] or 0)
        out["y_short"] = int(row["y_short"] or 0)
        return out

    def _flush_state(self, st):
        for row in st["pending"]:
            self.rows.append(self._finalize_row(row))
        st["pending"] = []

    def _finalize_day(self):
        pass

    def _pick_model(self):
        model = RandomForestClassifier(n_estimators=400, max_depth=5, min_samples_leaf=20, random_state=42, n_jobs=-1)
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", model)])

    def _eval_threshold(self, y_true, probs):
        best = None
        for thr in self.threshold_grid:
            pred = (probs >= thr).astype(int)
            precision = precision_score(y_true, pred, zero_division=0)
            recall = recall_score(y_true, pred, zero_division=0)
            signal_rate = float(pred.mean())
            score = precision * max(signal_rate, 1e-6)
            row = {"threshold": float(thr), "precision": float(precision), "recall": float(recall), "signal_rate": signal_rate, "score": float(score)}
            if best is None or row["score"] > best["score"]:
                best = row
        return best

    def OnEndOfAlgorithm(self):
        for st in list(self.state.values()):
            self._flush_state(st)
        dataset = pd.DataFrame(self.rows)
        if dataset.empty:
            self.Log("PHASE68_ERROR no_rows")
            return
        dataset["date"] = pd.to_datetime(dataset["date"]).dt.date
        self.Log(f"PHASE68_DATASET n={len(dataset)} slots={dataset['slot'].value_counts().to_dict()} symbols={dataset['symbol'].value_counts().to_dict()}")
        results = []
        for slot in sorted(dataset["slot"].dropna().unique()):
            for side, target_col in [("LONG", "y_long"), ("SHORT", "y_short")]:
                sub = dataset[dataset["slot"] == slot].copy()
                a, b = self.splits["IS"]
                train = sub[(sub["date"] >= a) & (sub["date"] <= b)].copy()
                if train.empty or train[target_col].nunique() < 2:
                    results.append({"slot": slot, "side": side, "status": "insufficient_train", "train_n": int(len(train))})
                    continue
                pipe = self._pick_model()
                pipe.fit(train[self.features], train[target_col])
                train_probs = pipe.predict_proba(train[self.features])[:, 1]
                picked = self._eval_threshold(train[target_col].values, train_probs)
                metrics = {}
                for split_name, (sa, sb) in self.splits.items():
                    frame = sub[(sub["date"] >= sa) & (sub["date"] <= sb)].copy()
                    if frame.empty or frame[target_col].nunique() < 2:
                        metrics[split_name] = {"n": int(len(frame)), "auc": None, "precision": None, "signal_rate": None, "base_rate": float(frame[target_col].mean()) if len(frame) else None}
                        continue
                    probs = pipe.predict_proba(frame[self.features])[:, 1]
                    pred = (probs >= picked["threshold"]).astype(int)
                    auc = roc_auc_score(frame[target_col], probs) if frame[target_col].nunique() > 1 else np.nan
                    precision = precision_score(frame[target_col], pred, zero_division=0)
                    signal_rate = float(pred.mean())
                    base_rate = float(frame[target_col].mean())
                    metrics[split_name] = {"n": int(len(frame)), "auc": float(auc) if np.isfinite(auc) else None, "precision": float(precision), "signal_rate": signal_rate, "base_rate": base_rate}
                results.append({"slot": slot, "side": side, "status": "ok", "picked": picked, "metrics": metrics})
        summary = {
            "dataset_rows": int(len(dataset)),
            "slot_counts": {str(k): int(v) for k, v in dataset["slot"].value_counts().to_dict().items()},
            "symbol_counts": {str(k): int(v) for k, v in dataset["symbol"].value_counts().to_dict().items()},
            "failures": self.failures[:20],
            "results": results,
        }
        self.Log("PHASE68_SUMMARY " + json.dumps(summary, separators=(",", ":"), default=str))
        self.SetRuntimeStatistic("MLRows", str(len(dataset)))
        self.SetRuntimeStatistic("MLModels", str(sum(1 for r in results if r.get("status") == "ok")))
