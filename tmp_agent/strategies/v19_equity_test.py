# v19 Equity Test v3 - Aggressive Tuning
# Changes vs v2: threshold 0.55->0.50, position 0.50->0.90, horizon 10->15,
# SMA200 regime filter (long only above SMA200), wider TP (1.5x sigma).
# v2 diagnosis: model has mild edge (WR 53%, P/L 1.34, +$1309 in 4y)
# but trades too rarely (45 trades) with too-small position (50%) = cash drag.
# v3 aims to capture more of the edge with higher conviction sizing.

import numpy as np
import pandas as pd
import math
from datetime import datetime, timedelta
from collections import deque

# QuantConnect imports (only exist at QC runtime)
from AlgorithmImports import *

class V19EquityTest(QCAlgorithm):

    def Initialize(self):
        # --- Period from parameters ---
        sy = int(self.GetParameter("start_year") or "2022")
        sm = int(self.GetParameter("start_month") or "1")
        ey = int(self.GetParameter("end_year") or "2026")
        em = int(self.GetParameter("end_month") or "4")
        self.SetStartDate(sy, sm, 1)
        self.SetEndDate(ey, em, 1)

        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # SPY + auxiliaries for features
        self.spy = self.AddEquity("SPY", Resolution.Daily).Symbol
        self.vix = self.AddIndex("VIX", Resolution.Daily).Symbol
        self.tlt = self.AddEquity("TLT", Resolution.Daily).Symbol
        self.hyg = self.AddEquity("HYG", Resolution.Daily).Symbol

        self.SetBenchmark("SPY")

        # --- ML config ---
        self.RETRAIN_EVERY = 63       # trading days between retrains
        self.MIN_TRAIN = 500          # minimum training samples
        self.HORIZON = 15             # triple-barrier horizon (was 10)
        self.PT_K = 1.5               # profit target multiplier (was 1.25)
        self.SL_K = 1.0               # stop loss multiplier (x sigma)
        self.COST_BPS = 15            # round-trip cost in bps
        self.TOTAL_COST = self.COST_BPS / 10000.0
        self.ENTRY_THRESHOLD = 0.50   # probability threshold (was 0.55)
        self.EXIT_THRESHOLD = 0.45    # exit threshold (was 0.48)
        self.POSITION_SIZE = 0.90     # fraction of portfolio (was 0.50)
        self.SMA_PERIOD = 200         # regime filter: long only above SMA200

        # --- State ---
        self.model = None
        self.scaler = None
        self.days_since_train = 999   # force initial train
        self.trade_day = 0
        self.entry_price = 0.0
        self.entry_sigma = 0.0
        self.bars_in_trade = 0
        self.initialized_history = False

        # --- Data buffers (store raw OHLCV) ---
        self.MAX_HISTORY = 4000
        self.spy_close = deque(maxlen=self.MAX_HISTORY)
        self.spy_high = deque(maxlen=self.MAX_HISTORY)
        self.spy_low = deque(maxlen=self.MAX_HISTORY)
        self.spy_open = deque(maxlen=self.MAX_HISTORY)
        self.spy_volume = deque(maxlen=self.MAX_HISTORY)
        self.vix_close = deque(maxlen=self.MAX_HISTORY)
        self.tlt_close = deque(maxlen=self.MAX_HISTORY)
        self.hyg_close = deque(maxlen=self.MAX_HISTORY)
        self.dates = deque(maxlen=self.MAX_HISTORY)

        # --- Pre-load historical data (1500 trading days ~ 6 years) ---
        self._preload_history(1500)

        # Schedule: run at 10:00 AM to avoid opening noise
        self.Schedule.On(
            self.DateRules.EveryDay(self.spy),
            self.TimeRules.At(10, 0),
            self.DailyLogic
        )

    def _preload_history(self, days):
        """Load historical data BEFORE start date to train model immediately."""
        try:
            # Get SPY history
            spy_hist = self.History(self.spy, days, Resolution.Daily)
            if spy_hist.empty:
                self.Debug("PRELOAD: No SPY history returned")
                return

            # Reset index for easier access
            if isinstance(spy_hist.index, pd.MultiIndex):
                spy_hist = spy_hist.reset_index(level=0, drop=True)

            # Get auxiliary histories
            vix_hist = self.History(self.vix, days, Resolution.Daily)
            if isinstance(vix_hist.index, pd.MultiIndex) and not vix_hist.empty:
                vix_hist = vix_hist.reset_index(level=0, drop=True)

            tlt_hist = self.History(self.tlt, days, Resolution.Daily)
            if isinstance(tlt_hist.index, pd.MultiIndex) and not tlt_hist.empty:
                tlt_hist = tlt_hist.reset_index(level=0, drop=True)

            hyg_hist = self.History(self.hyg, days, Resolution.Daily)
            if isinstance(hyg_hist.index, pd.MultiIndex) and not hyg_hist.empty:
                hyg_hist = hyg_hist.reset_index(level=0, drop=True)

            # Fill buffers
            last_vix = 20.0
            last_tlt = 100.0
            last_hyg = 80.0

            for dt in spy_hist.index:
                row = spy_hist.loc[dt]
                # Handle case where row might be a DataFrame (multiple rows for same date)
                if hasattr(row, 'iloc') and len(row.shape) > 1:
                    row = row.iloc[0]

                self.spy_close.append(float(row['close']))
                self.spy_high.append(float(row['high']))
                self.spy_low.append(float(row['low']))
                self.spy_open.append(float(row['open']))
                self.spy_volume.append(float(row['volume']))
                self.dates.append(dt)

                # VIX
                if not vix_hist.empty and dt in vix_hist.index:
                    vr = vix_hist.loc[dt]
                    if hasattr(vr, 'iloc') and len(vr.shape) > 1:
                        vr = vr.iloc[0]
                    last_vix = float(vr['close'])
                self.vix_close.append(last_vix)

                # TLT
                if not tlt_hist.empty and dt in tlt_hist.index:
                    tr = tlt_hist.loc[dt]
                    if hasattr(tr, 'iloc') and len(tr.shape) > 1:
                        tr = tr.iloc[0]
                    last_tlt = float(tr['close'])
                self.tlt_close.append(last_tlt)

                # HYG
                if not hyg_hist.empty and dt in hyg_hist.index:
                    hr = hyg_hist.loc[dt]
                    if hasattr(hr, 'iloc') and len(hr.shape) > 1:
                        hr = hr.iloc[0]
                    last_hyg = float(hr['close'])
                self.hyg_close.append(last_hyg)

            self.initialized_history = True
            self.Debug(f"PRELOAD: {len(self.spy_close)} bars loaded. Training initial model...")

            # Train initial model immediately
            if len(self.spy_close) >= self.MIN_TRAIN:
                self._train_model()
                self.days_since_train = 0
                if self.model is not None:
                    self.Debug("PRELOAD: Initial model trained successfully")
                else:
                    self.Debug("PRELOAD: Model training returned None")
            else:
                self.Debug(f"PRELOAD: Only {len(self.spy_close)} bars, need {self.MIN_TRAIN}")

        except Exception as e:
            self.Debug(f"PRELOAD ERROR: {str(e)[:200]}")

    def OnData(self, data):
        self._collect_bar(data)

    def _collect_bar(self, data):
        if not data.Bars.ContainsKey(self.spy):
            return
        bar = data.Bars[self.spy]
        self.spy_close.append(float(bar.Close))
        self.spy_high.append(float(bar.High))
        self.spy_low.append(float(bar.Low))
        self.spy_open.append(float(bar.Open))
        self.spy_volume.append(float(bar.Volume))
        self.dates.append(self.Time)

        # Auxiliaries - use close price, ffill if missing
        if data.Bars.ContainsKey(self.vix):
            self.vix_close.append(float(data.Bars[self.vix].Close))
        elif len(self.vix_close) > 0:
            self.vix_close.append(self.vix_close[-1])
        else:
            self.vix_close.append(20.0)

        if data.Bars.ContainsKey(self.tlt):
            self.tlt_close.append(float(data.Bars[self.tlt].Close))
        elif len(self.tlt_close) > 0:
            self.tlt_close.append(self.tlt_close[-1])
        else:
            self.tlt_close.append(100.0)

        if data.Bars.ContainsKey(self.hyg):
            self.hyg_close.append(float(data.Bars[self.hyg].Close))
        elif len(self.hyg_close) > 0:
            self.hyg_close.append(self.hyg_close[-1])
        else:
            self.hyg_close.append(80.0)

    def DailyLogic(self):
        n = len(self.spy_close)
        if n < 200:
            return

        self.days_since_train += 1
        self.trade_day += 1

        # --- Retrain check ---
        if self.model is None or self.days_since_train >= self.RETRAIN_EVERY:
            if n >= self.MIN_TRAIN:
                self._train_model()
                self.days_since_train = 0

        if self.model is None:
            return

        # --- Compute features for today (latest bar) ---
        features = self._compute_features_latest()
        if features is None:
            return

        # --- Predict ---
        try:
            feat_scaled = self.scaler.transform(features.reshape(1, -1))
            prob = self.model.predict_proba(feat_scaled)[0][1]
        except Exception as e:
            self.Debug(f"Predict error: {str(e)[:100]}")
            return

        # --- Position management ---
        invested = self.Portfolio[self.spy].Invested
        current_price = self.spy_close[-1]

        # SMA200 regime filter
        closes_arr = np.array(self.spy_close)
        sma200 = float(np.mean(closes_arr[-self.SMA_PERIOD:])) if n >= self.SMA_PERIOD else current_price
        above_sma = current_price > sma200

        if invested:
            self.bars_in_trade += 1
            pnl_pct = (current_price / self.entry_price) - 1.0 if self.entry_price > 0 else 0.0

            tp_hit = pnl_pct >= self.PT_K * self.entry_sigma
            sl_hit = pnl_pct <= -self.SL_K * self.entry_sigma
            time_exit = self.bars_in_trade >= self.HORIZON
            signal_exit = prob < self.EXIT_THRESHOLD

            if tp_hit or sl_hit or time_exit or signal_exit:
                reason = "TP" if tp_hit else "SL" if sl_hit else "TIME" if time_exit else "SIG"
                self.Liquidate(self.spy, f"EXIT-{reason} pnl={pnl_pct:.4f} p={prob:.3f}")
                self.bars_in_trade = 0
                self.entry_price = 0.0
        else:
            if prob >= self.ENTRY_THRESHOLD and above_sma:
                self.SetHoldings(self.spy, self.POSITION_SIZE, tag=f"LONG p={prob:.3f} sma={sma200:.1f}")
                self.entry_price = current_price
                closes = np.array(self.spy_close)
                rets = np.diff(closes[-21:]) / closes[-21:-1]
                self.entry_sigma = float(np.std(rets)) * np.sqrt(self.HORIZON) if len(rets) >= 10 else 0.02
                self.bars_in_trade = 0

    def _train_model(self):
        """Train LightGBM on all available data."""
        try:
            from lightgbm import LGBMClassifier
            from sklearn.preprocessing import StandardScaler as SkScaler
        except ImportError:
            self.Debug("LightGBM or sklearn not available")
            return

        n = len(self.spy_close)
        if n < self.MIN_TRAIN + 100:
            return

        features, valid_start = self._compute_features_matrix()
        if features is None or len(features) < self.MIN_TRAIN:
            return

        closes = np.array(self.spy_close)
        labels = self._compute_labels(closes, valid_start)
        if labels is None:
            return

        min_len = min(len(features), len(labels))
        features = features[:min_len]
        labels = labels[:min_len]

        valid = ~np.isnan(labels)
        features = features[valid]
        labels = labels[valid].astype(np.int8)

        if len(labels) < self.MIN_TRAIN:
            self.Debug(f"Train: insufficient samples ({len(labels)})")
            return

        pos_rate = float(labels.mean())
        if pos_rate < 0.05 or pos_rate > 0.95:
            self.Debug(f"Train: class imbalance ({pos_rate:.3f})")
            return

        # Time decay weights
        n_samples = len(labels)
        half_life = min(n_samples * 0.6, 252 * 1.5)
        idx = np.arange(n_samples, dtype=np.float64)
        weights = np.exp(-np.log(2) * (n_samples - 1 - idx) / half_life)
        weights = weights / weights.sum() * n_samples

        scaler = SkScaler()
        feat_scaled = scaler.fit_transform(features)

        model = LGBMClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_lambda=1.0,
            min_child_samples=30,
            random_state=42,
            n_jobs=1,
            verbosity=-1,
            class_weight='balanced'
        )

        # Split with horizon purge for early stopping
        split = int(len(labels) * 0.8)
        gap = self.HORIZON
        train_end = split - gap
        val_start = split

        if train_end < int(self.MIN_TRAIN * 0.5) or val_start >= len(labels) - 20:
            model.fit(feat_scaled, labels, sample_weight=weights)
        else:
            X_tr = feat_scaled[:train_end]
            y_tr = labels[:train_end]
            w_tr = weights[:train_end]
            X_va = feat_scaled[val_start:]
            y_va = labels[val_start:]

            import lightgbm as lgb
            model.fit(
                X_tr, y_tr,
                sample_weight=w_tr,
                eval_set=[(X_va, y_va)],
                callbacks=[
                    lgb.early_stopping(50, verbose=False),
                    lgb.log_evaluation(period=0)
                ]
            )

        self.model = model
        self.scaler = scaler

        train_prob = model.predict_proba(feat_scaled)[:, 1]
        above_thr = int((train_prob >= self.ENTRY_THRESHOLD).sum())
        self.Debug(f"TRAIN: {len(labels)} samp, pos={pos_rate:.3f}, "
                   f"signals>={self.ENTRY_THRESHOLD}: {above_thr} ({above_thr*100//len(labels)}%)")

    def _compute_features_matrix(self):
        """Build feature matrix for ALL bars. Returns (features_2d, valid_start_index)."""
        closes = np.array(self.spy_close, dtype=np.float64)
        highs = np.array(self.spy_high, dtype=np.float64)
        lows = np.array(self.spy_low, dtype=np.float64)
        opens = np.array(self.spy_open, dtype=np.float64)
        volumes = np.array(self.spy_volume, dtype=np.float64)
        vix = np.array(self.vix_close, dtype=np.float64)
        tlt = np.array(self.tlt_close, dtype=np.float64)
        hyg = np.array(self.hyg_close, dtype=np.float64)
        n = len(closes)

        if n < 200:
            return None, 0

        # Pre-compute returns
        ret1 = np.zeros(n)
        ret1[1:] = closes[1:] / closes[:-1] - 1.0

        feature_arrays = []

        # --- Returns at various horizons (shifted by 1 = causal) ---
        for p in [1, 2, 3, 5, 10, 20, 60]:
            r = np.zeros(n)
            for i in range(p+1, n):
                if closes[i-1-p] > 0:
                    r[i] = closes[i-1] / closes[i-1-p] - 1.0
            feature_arrays.append(r)

        # --- Volatility windows ---
        for w in [5, 10, 20, 60]:
            vol = np.zeros(n)
            for i in range(w+1, n):
                vol[i] = np.std(ret1[i-w:i]) * np.sqrt(252)
            feature_arrays.append(vol)

        # Index of vol_20d for later use
        vol_20d_idx = 7 + 2  # 7 returns + vol_5d, vol_10d, then vol_20d

        # --- RSI 14 (shifted) ---
        rsi = np.full(n, 50.0)
        for i in range(15, n):
            gains = 0.0; losses = 0.0
            for j in range(i-14, i):
                d = closes[j] - closes[j-1]
                if d > 0: gains += d
                else: losses -= d
            if losses > 1e-10:
                rsi[i] = 100.0 - 100.0 / (1.0 + gains / losses)
            else:
                rsi[i] = 100.0
        rsi_s = np.zeros(n); rsi_s[1:] = rsi[:-1]
        feature_arrays.append(rsi_s)

        # --- Bollinger Band position 20 ---
        bb_pos = np.zeros(n)
        for i in range(21, n):
            w = closes[i-20:i]; sma = np.mean(w); std = np.std(w)
            if std > 1e-10: bb_pos[i] = (closes[i-1] - sma) / (2.0 * std)
        feature_arrays.append(bb_pos)

        # --- BB width 20 ---
        bb_w = np.zeros(n)
        for i in range(21, n):
            w = closes[i-20:i]; sma = np.mean(w); std = np.std(w)
            if sma > 1e-10: bb_w[i] = std / sma
        feature_arrays.append(bb_w)

        # --- MACD histogram ---
        ema12 = np.zeros(n); ema26 = np.zeros(n)
        ema12[0] = closes[0]; ema26[0] = closes[0]
        m12 = 2.0/13.0; m26 = 2.0/27.0
        for i in range(1, n):
            ema12[i] = closes[i-1]*m12 + ema12[i-1]*(1-m12)
            ema26[i] = closes[i-1]*m26 + ema26[i-1]*(1-m26)
        macd = ema12 - ema26
        sig = np.zeros(n); sig[0] = macd[0]; m9 = 2.0/10.0
        for i in range(1, n):
            sig[i] = macd[i]*m9 + sig[i-1]*(1-m9)
        macd_h = np.zeros(n)
        for i in range(1, n):
            if closes[i-1] > 1e-10: macd_h[i] = (macd[i]-sig[i])/closes[i-1]
        feature_arrays.append(macd_h)

        # --- ATR 14 normalized ---
        atr = np.zeros(n)
        for i in range(2, n):
            tr = max(highs[i-1]-lows[i-1], abs(highs[i-1]-closes[i-2]), abs(lows[i-1]-closes[i-2]))
            if closes[i-1] > 1e-10: atr[i] = tr/closes[i-1]
        atr_s = np.zeros(n); a_a = 2.0/15.0
        for i in range(1, n): atr_s[i] = atr[i]*a_a + atr_s[i-1]*(1-a_a)
        feature_arrays.append(atr_s)

        # --- VIX level (shifted) ---
        vix_s = np.zeros(n); vix_s[1:] = vix[:-1]
        feature_arrays.append(vix_s)

        # --- VIX 20-day MA ---
        vix_ma = np.zeros(n)
        for i in range(21, n): vix_ma[i] = np.mean(vix[i-20:i])
        feature_arrays.append(vix_ma)

        # --- VIX term structure ---
        vix_t = np.zeros(n)
        for i in range(61, n):
            w = vix[i-60:i]; mu = np.mean(w); sd = np.std(w)
            if sd > 1e-10: vix_t[i] = (vix[i-1]-mu)/sd
        feature_arrays.append(vix_t)

        # --- Credit spread proxy ---
        cs = np.zeros(n)
        for i in range(22, n):
            tr_ = (tlt[i-1]/tlt[i-21]-1.0) if tlt[i-21] > 0 else 0.0
            hr_ = (hyg[i-1]/hyg[i-21]-1.0) if hyg[i-21] > 0 else 0.0
            cs[i] = tr_ - hr_
        feature_arrays.append(cs)

        # --- Order flow imbalance ---
        tick = np.zeros(n)
        for i in range(1, n):
            d = closes[i]-closes[i-1]
            if d > 0: tick[i] = 1.0
            elif d < 0: tick[i] = -1.0
            else: tick[i] = 1.0 if closes[i] > opens[i] else -1.0
        ofi = np.zeros(n)
        for i in range(21, n):
            ss = 0.0; vs = 0.0
            for j in range(i-20, i):
                ss += volumes[j]*tick[j]; vs += volumes[j]
            if vs > 0: ofi[i] = ss/vs
        ofi_s = np.zeros(n); ofi_s[1:] = ofi[:-1]
        feature_arrays.append(ofi_s)

        # --- Volume clock ---
        vc = np.zeros(n)
        for i in range(61, n):
            med = np.median(volumes[i-60:i])
            if med > 0: vc[i] = volumes[i-1]/med
        feature_arrays.append(vc)

        # --- Volatility skew ---
        vsk = np.zeros(n)
        for i in range(21, n):
            wr = ret1[i-20:i]; m = np.mean(wr); s = np.std(wr)
            if s > 1e-10: vsk[i] = np.mean(((wr-m)/s)**3)
        vsk_s = np.zeros(n); vsk_s[1:] = vsk[:-1]
        feature_arrays.append(vsk_s)

        # --- Vol regime z-score ---
        vol_20 = feature_arrays[vol_20d_idx]
        vrz = np.zeros(n)
        for i in range(120, n):
            w = vol_20[max(1,i-252):i]
            if len(w) >= 60:
                mu = np.mean(w); sd = np.std(w)
                if sd > 1e-10: vrz[i] = (vol_20[i-1]-mu)/sd
        feature_arrays.append(vrz)

        # --- Day of week ---
        dow = np.zeros(n)
        dl = list(self.dates)
        for i in range(min(len(dl), n)): dow[i] = dl[i].weekday() if hasattr(dl[i], 'weekday') else 0
        feature_arrays.append(dow)

        # --- Month ---
        moy = np.zeros(n)
        for i in range(min(len(dl), n)): moy[i] = dl[i].month if hasattr(dl[i], 'month') else 1
        feature_arrays.append(moy)

        all_feats = np.column_stack(feature_arrays)
        valid_start = 120
        all_feats = np.nan_to_num(all_feats, nan=0.0, posinf=0.0, neginf=0.0)
        return all_feats[valid_start:], valid_start

    def _compute_features_latest(self):
        """Compute features for the most recent bar only."""
        n = len(self.spy_close)
        if n < 200:
            return None
        features, _ = self._compute_features_matrix()
        if features is None or len(features) == 0:
            return None
        return features[-1]

    def _compute_labels(self, closes, valid_start):
        """Triple-barrier labels with costs."""
        n = len(closes)
        total = n - valid_start
        labels = np.full(total, np.nan)

        for i in range(total):
            idx = i + valid_start
            if idx < 20: continue
            rets = np.diff(closes[idx-20:idx]) / closes[idx-20:idx-1]
            sigma = np.std(rets)
            if sigma < 1e-8: continue

            thr_up = self.PT_K * sigma
            thr_dn = self.SL_K * sigma
            base = closes[idx] * (1.0 + self.TOTAL_COST)

            for j in range(1, min(self.HORIZON+1, n-idx)):
                exit_px = closes[idx+j] * (1.0 - self.TOTAL_COST)
                ret = (exit_px / base) - 1.0
                if ret >= thr_up:
                    labels[i] = 1.0; break
                if ret <= -thr_dn:
                    labels[i] = 0.0; break

        return labels

    def OnEndOfAlgorithm(self):
        self.Liquidate()

    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status == OrderStatus.Filled:
            self.Debug(f"ORDER: {orderEvent.Symbol} {orderEvent.Direction} "
                       f"qty={orderEvent.FillQuantity} px={orderEvent.FillPrice:.2f}")
