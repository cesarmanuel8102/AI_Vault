# region imports
from AlgorithmImports import *
from datetime import timedelta, date
import math
# endregion


class CampaignMaturityGateMonitor(QCAlgorithm):
    """
    PF Campaign Maturity Gate Monitor

    This is NOT a trading model. It monitors the market regime that historically
    made the G1_ORB_R0150 fast-pass profile viable. Its job is to tell us when
    buying/activating a prop-firm challenge has a favorable tactical window.

    Core validated gate from Phase49/Phase51:
      IWM dd50 <= -5.11294%
      QQQ rv20 >= 17.4213% annualized
      IWM rng10 <= 1.52915%

    Phase52 conclusion:
      Best tactical activation was not first signal. It was campaign maturity:
      roughly D21-D28 after the first signal in the active campaign.
    """

    def Initialize(self):
        self.SetStartDate(int(self.GetParameter("start_year") or 2024), int(self.GetParameter("start_month") or 10), int(self.GetParameter("start_day") or 1))
        if not self.LiveMode:
            self.SetEndDate(int(self.GetParameter("end_year") or 2025), int(self.GetParameter("end_month") or 3), int(self.GetParameter("end_day") or 31))
        self.SetCash(float(self.GetParameter("initial_cash") or 100000))
        self.SetTimeZone(TimeZones.NewYork)

        self.iwm_dd50_thr = float(self.GetParameter("iwm_dd50_thr") or -0.0511294)
        self.qqq_rv20_thr = float(self.GetParameter("qqq_rv20_thr") or 0.174213)
        self.iwm_rng10_thr = float(self.GetParameter("iwm_rng10_thr") or 0.0152915)
        self.episode_gap_days = int(self.GetParameter("episode_gap_days") or 21)
        self.active_lookback_days = int(self.GetParameter("active_lookback_days") or 45)
        self.activation_start_day = int(self.GetParameter("activation_start_day") or 21)
        self.activation_end_day = int(self.GetParameter("activation_end_day") or 28)
        self.late_end_day = int(self.GetParameter("late_end_day") or 35)

        self.symbols = {}
        self.windows = {}
        for ticker in ["SPY", "QQQ", "IWM", "VIXY"]:
            sym = self.AddEquity(ticker, Resolution.Daily).Symbol
            self.symbols[ticker] = sym
            self.windows[ticker] = RollingWindow[TradeBar](120)

        self.current_state = "INIT"
        self.current_action = "WAIT_DATA"
        self.last_logged_state = None
        self.latest_snapshot = {}
        self.first_activation_window_date = None
        self.activation_window_days_seen = 0
        self.late_window_days_seen = 0
        self.max_campaign_age_seen = -1

        self.SetWarmUp(90, Resolution.Daily)
        self.Schedule.On(self.DateRules.EveryDay(self.symbols["SPY"]), self.TimeRules.AfterMarketClose(self.symbols["SPY"], 5), self.EvaluateGate)

    def OnData(self, data):
        for ticker, sym in self.symbols.items():
            if data.Bars.ContainsKey(sym):
                self.windows[ticker].Add(data.Bars[sym])

        if self.IsWarmingUp:
            return

    def OnWarmupFinished(self):
        self.EvaluateGate()

    def EvaluateGate(self):
        if not self._ready():
            self.current_state = "WAIT_DATA"
            self.current_action = "WAIT_DATA"
            self._publish({}, [], None, None)
            return

        signals = self._scan_base_signals()
        campaign_start, last_signal = self._active_campaign(signals)
        features = self._features_at_latest()
        base_now = self._base_gate(features)

        today = self.Time.date()
        age = -1
        if campaign_start is not None:
            age = (today - campaign_start).days

        if campaign_start is None:
            state = "NO_CAMPAIGN"
            action = "NO_BUY"
        elif age < self.activation_start_day:
            state = "WAIT_MATURITY"
            action = "WATCH_ONLY"
        elif self.activation_start_day <= age <= self.activation_end_day:
            state = "ACTIVATION_WINDOW"
            action = "BUY_OR_ACTIVATE_ALLOWED"
            self.activation_window_days_seen += 1
            if self.first_activation_window_date is None:
                self.first_activation_window_date = today
        elif self.activation_end_day < age <= self.late_end_day:
            state = "LATE_RISK_CONSISTENCY"
            action = "DO_NOT_BUY_LATE_UNLESS_MANUAL_OVERRIDE"
            self.late_window_days_seen += 1
        else:
            state = "EXPIRED"
            action = "NO_BUY_WAIT_NEXT_CAMPAIGN"

        if age > self.max_campaign_age_seen:
            self.max_campaign_age_seen = age

        self.current_state = state
        self.current_action = action
        self.latest_snapshot = features
        self._publish(features, signals, campaign_start, last_signal)

        if state != self.last_logged_state:
            self.Log(
                "CAMPAIGN_GATE "
                f"state={state} action={action} age={age} start={campaign_start} last_signal={last_signal} "
                f"base_now={base_now} iwm_dd50={features.get('iwm_dd50', 0):.4f} "
                f"qqq_rv20={features.get('qqq_rv20', 0):.4f} iwm_rng10={features.get('iwm_rng10', 0):.4f} "
                f"signals={len(signals)}"
            )
            self.last_logged_state = state

    def _ready(self):
        return all(w.Count >= 60 for w in self.windows.values())

    def _bars(self, ticker):
        # RollingWindow index 0 is newest; reverse into chronological order.
        return list(reversed([self.windows[ticker][i] for i in range(self.windows[ticker].Count)]))

    def _common_dates(self):
        maps = {}
        for ticker in ["QQQ", "IWM"]:
            maps[ticker] = {b.EndTime.date(): b for b in self._bars(ticker)}
        return sorted(set(maps["QQQ"].keys()).intersection(set(maps["IWM"].keys())))

    def _feature_at_date(self, ticker, dt):
        bars = [b for b in self._bars(ticker) if b.EndTime.date() <= dt]
        if len(bars) < 51:
            return None
        closes = [float(b.Close) for b in bars]
        highs = [float(b.High) for b in bars]
        lows = [float(b.Low) for b in bars]
        opens = [float(b.Open) for b in bars]
        rets = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                rets.append(closes[i] / closes[i - 1] - 1.0)
        ret20 = closes[-1] / closes[-21] - 1.0 if len(closes) >= 21 and closes[-21] > 0 else 0.0
        rv20 = self._std(rets[-20:]) * math.sqrt(252.0) if len(rets) >= 20 else 0.0
        rng10 = sum((highs[i] - lows[i]) / closes[i] for i in range(len(closes) - 10, len(closes)) if closes[i] > 0) / 10.0
        dd50 = closes[-1] / max(highs[-50:]) - 1.0 if max(highs[-50:]) > 0 else 0.0
        gap1 = (opens[-1] - closes[-2]) / closes[-2] if len(closes) >= 2 and closes[-2] > 0 else 0.0
        return {"ret20": ret20, "rv20": rv20, "rng10": rng10, "dd50": dd50, "gap1": gap1}

    def _features_at_latest(self):
        dt = min(self._bars("QQQ")[-1].EndTime.date(), self._bars("IWM")[-1].EndTime.date())
        qqq = self._feature_at_date("QQQ", dt) or {}
        iwm = self._feature_at_date("IWM", dt) or {}
        vixy = self._feature_at_date("VIXY", dt) or {}
        return {
            "date": dt.isoformat(),
            "qqq_rv20": qqq.get("rv20", 0.0),
            "iwm_dd50": iwm.get("dd50", 0.0),
            "iwm_rng10": iwm.get("rng10", 0.0),
            "iwm_gap1": iwm.get("gap1", 0.0),
            "vixy_rv20": vixy.get("rv20", 0.0),
            "vixy_rng10": vixy.get("rng10", 0.0),
        }

    def _base_gate(self, features):
        return (
            features.get("iwm_dd50", 0.0) <= self.iwm_dd50_thr
            and features.get("qqq_rv20", 0.0) >= self.qqq_rv20_thr
            and features.get("iwm_rng10", 99.0) <= self.iwm_rng10_thr
        )

    def _scan_base_signals(self):
        signals = []
        for dt in self._common_dates():
            # Phase49/52 validation used weekly Sunday start dates with
            # features known before that start. Friday close maps to Sunday.
            if dt.weekday() != 4:
                continue
            qqq = self._feature_at_date("QQQ", dt)
            iwm = self._feature_at_date("IWM", dt)
            if qqq is None or iwm is None:
                continue
            features = {"qqq_rv20": qqq["rv20"], "iwm_dd50": iwm["dd50"], "iwm_rng10": iwm["rng10"]}
            if self._base_gate(features):
                signals.append(dt + timedelta(days=2))
        return signals

    def _active_campaign(self, signals):
        if not signals:
            return None, None
        episodes = []
        cur = []
        for sig in signals:
            if not cur or (sig - cur[-1]).days <= self.episode_gap_days:
                cur.append(sig)
            else:
                episodes.append(cur)
                cur = [sig]
        if cur:
            episodes.append(cur)

        today = self.Time.date()
        last_ep = episodes[-1]
        last_signal = last_ep[-1]
        if (today - last_signal).days > self.active_lookback_days:
            return None, last_signal
        return last_ep[0], last_signal

    def _std(self, values):
        n = len(values)
        if n < 2:
            return 0.0
        mean = sum(values) / n
        var = sum((x - mean) ** 2 for x in values) / (n - 1)
        return math.sqrt(max(0.0, var))

    def _publish(self, features, signals, campaign_start, last_signal):
        today = self.Time.date()
        age = -1 if campaign_start is None else (today - campaign_start).days
        days_to_window = -1 if campaign_start is None else max(0, self.activation_start_day - age)
        base_now = self._base_gate(features) if features else False

        self.SetRuntimeStatistic("GateState", self.current_state)
        self.SetRuntimeStatistic("Action", self.current_action)
        self.SetRuntimeStatistic("CampaignStart", str(campaign_start) if campaign_start else "NONE")
        self.SetRuntimeStatistic("LastSignal", str(last_signal) if last_signal else "NONE")
        self.SetRuntimeStatistic("CampaignAgeDays", str(age))
        self.SetRuntimeStatistic("DaysToActivationWindow", str(days_to_window))
        self.SetRuntimeStatistic("BaseGateNow", "1" if base_now else "0")
        self.SetRuntimeStatistic("SignalCount", str(len(signals)))
        self.SetRuntimeStatistic("FirstActivationWindow", str(self.first_activation_window_date) if self.first_activation_window_date else "NONE")
        self.SetRuntimeStatistic("ActivationWindowDaysSeen", str(self.activation_window_days_seen))
        self.SetRuntimeStatistic("LateWindowDaysSeen", str(self.late_window_days_seen))
        self.SetRuntimeStatistic("MaxCampaignAgeSeen", str(self.max_campaign_age_seen))
        self.SetRuntimeStatistic("IWM_DD50", f"{features.get('iwm_dd50', 0.0):.4f}" if features else "NA")
        self.SetRuntimeStatistic("QQQ_RV20", f"{features.get('qqq_rv20', 0.0):.4f}" if features else "NA")
        self.SetRuntimeStatistic("IWM_RNG10", f"{features.get('iwm_rng10', 0.0):.4f}" if features else "NA")

    def OnEndOfAlgorithm(self):
        self.EvaluateGate()
        self.Log(
            "FINAL_CAMPAIGN_GATE "
            f"state={self.current_state} action={self.current_action} snapshot={self.latest_snapshot}"
        )



