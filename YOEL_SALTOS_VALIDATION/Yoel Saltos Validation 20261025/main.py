from AlgorithmImports import *
from collections import defaultdict, deque
import json

from analysis_core import summarize_binary_outcomes


class YoelSaltosValidation20261025(QCAlgorithm):
    """Phase A: test the course's first-jump/second-jump claim without trading."""

    def initialize(self):
        self.set_start_date(int(self.get_parameter("start_year") or 2008), 1, 1)
        self.set_end_date(int(self.get_parameter("end_year") or 2025), 12, 31)
        self.set_cash(100000)
        self.set_time_zone("America/New_York")

        self.u1 = {
            "TSLA", "AAPL", "AMZN", "NFLX", "META", "COIN", "NIO", "XPEV",
            "LI", "SPY", "IWM", "QQQ", "DIA", "GLD", "USO",
        }
        broad = {
            "MSFT", "GOOG", "NVDA", "AMD", "AVGO", "JPM", "BAC", "WMT",
            "COST", "HD", "UNH", "JNJ", "XOM", "CVX", "CAT", "BA", "DIS",
            "TLT", "XLF", "XLE", "XBI", "XLK", "XLV", "EEM", "SMH",
        }
        self.u2 = self.u1 | broad
        self.symbol_to_ticker = {}
        self.history_by_ticker = {}
        self.pending_by_ticker = defaultdict(list)
        self.aggregates = defaultdict(lambda: {
            "signal_successes": 0,
            "signal_total": 0,
            "control_successes": 0,
            "control_total": 0,
            "signal_returns": [],
        })

        for ticker in sorted(self.u2):
            security = self.add_equity(
                ticker,
                Resolution.DAILY,
                data_normalization_mode=DataNormalizationMode.ADJUSTED,
            )
            self.symbol_to_ticker[security.symbol] = ticker
            self.history_by_ticker[ticker] = deque(maxlen=205)

        self.gaps = (0.005, 0.01, 0.015, 0.02)
        self.lookbacks = (5, 10)
        self.strict_modes = (False, True)
        self.high_volume_modes = (False, True)

    def on_data(self, data: Slice):
        for symbol, ticker in self.symbol_to_ticker.items():
            if not data.bars.contains_key(symbol):
                continue
            bar = data.bars[symbol]
            history = self.history_by_ticker[ticker]
            if len(history) >= 100:
                self._process_bar(ticker, bar, history)
            history.append({
                "time": bar.end_time,
                "open": float(bar.open),
                "close": float(bar.close),
                "volume": float(bar.volume),
            })

    def _process_bar(self, ticker, bar, history):
        prior_close = history[-1]["close"]
        if prior_close <= 0 or bar.open <= 0:
            return
        gap = float(bar.open) / prior_close - 1.0
        intraday_return = float(bar.close) / float(bar.open) - 1.0

        pending = self.pending_by_ticker[ticker]
        for item in pending:
            success = gap * item["direction"] >= item["gap_threshold"]
            aggregate = self.aggregates[item["key"]]
            if item["kind"] == "signal":
                aggregate["signal_total"] += 1
                aggregate["signal_successes"] += int(success)
                aggregate["signal_returns"].append(intraday_return * item["direction"])
            else:
                aggregate["control_total"] += 1
                aggregate["control_successes"] += int(success)
        pending.clear()

        closes = [item["close"] for item in history]
        volumes = [item["volume"] for item in history]
        sma20 = sum(closes[-20:]) / 20
        sma40 = sum(closes[-40:]) / 40
        sma100 = sum(closes[-100:]) / 100
        avg_volume20 = sum(volumes[-20:]) / 20
        high_volume = avg_volume20 > 0 and float(bar.volume) > 2.5 * avg_volume20
        prior_price = closes[-1]
        period = "OOS" if bar.end_time.year >= 2022 else "IS"
        universes = ["U2"] + (["U1"] if ticker in self.u1 else [])

        for threshold in self.gaps:
            prior_gaps = []
            for index in range(1, 11):
                current = history[-index]
                previous = history[-index - 1]
                if previous["close"] > 0:
                    prior_gaps.append(abs(current["open"] / previous["close"] - 1.0))

            for lookback in self.lookbacks:
                no_recent_gap = all(value < threshold for value in prior_gaps[:lookback])
                for strict in self.strict_modes:
                    for exclude_high_volume in self.high_volume_modes:
                        if exclude_high_volume and high_volume:
                            continue
                        for direction in (1, -1):
                            if direction == 1:
                                trend_ok = sma20 > sma40 and prior_price > sma40
                                if strict:
                                    trend_ok = trend_ok and prior_price > sma100
                            else:
                                trend_ok = sma20 < sma40 and prior_price < sma40
                                if strict:
                                    trend_ok = trend_ok and prior_price < sma100
                            if not trend_ok:
                                continue

                            is_first_gap = gap * direction >= threshold and no_recent_gap
                            kind = "signal" if is_first_gap else "control"
                            for universe in universes:
                                for segment in ("ALL", period):
                                    pending.append({
                                        "kind": kind,
                                        "direction": direction,
                                        "gap_threshold": threshold,
                                        "key": (
                                            universe, segment, threshold, lookback,
                                            strict, exclude_high_volume, ticker,
                                        ),
                                    })

    def on_end_of_algorithm(self):
        grouped = defaultdict(lambda: {
            "signal_successes": 0,
            "signal_total": 0,
            "control_successes": 0,
            "control_total": 0,
            "signal_returns": [],
            "ticker_lifts": [],
        })
        for key, values in self.aggregates.items():
            universe, segment, threshold, lookback, strict, exclude_high_volume, ticker = key
            group_key = (universe, segment, threshold, lookback, strict, exclude_high_volume)
            group = grouped[group_key]
            for field in (
                "signal_successes", "signal_total", "control_successes", "control_total"
            ):
                group[field] += values[field]
            group["signal_returns"].extend(values["signal_returns"])
            if values["signal_total"] >= 5 and values["control_total"] > 0:
                signal_rate = values["signal_successes"] / values["signal_total"]
                control_rate = values["control_successes"] / values["control_total"]
                group["ticker_lifts"].append(signal_rate - control_rate)

        results = []
        for key, values in sorted(grouped.items(), key=lambda item: str(item[0])):
            universe, segment, threshold, lookback, strict, exclude_high_volume = key
            summary = summarize_binary_outcomes(
                values["signal_successes"],
                values["signal_total"],
                values["control_successes"],
                values["control_total"],
            )
            returns = values["signal_returns"]
            positive_ticker_fraction = None
            if values["ticker_lifts"]:
                positive_ticker_fraction = sum(x > 0 for x in values["ticker_lifts"]) / len(values["ticker_lifts"])
            result = {
                "universe": universe,
                "segment": segment,
                "gap_threshold": threshold,
                "lookback": lookback,
                "strict_sma100": strict,
                "exclude_volume_spikes": exclude_high_volume,
                "signal_successes": values["signal_successes"],
                "signal_total": values["signal_total"],
                "control_successes": values["control_successes"],
                "control_total": values["control_total"],
                **summary,
                "next_day_directional_intraday_mean": sum(returns) / len(returns) if returns else None,
                "tickers_with_sample": len(values["ticker_lifts"]),
                "positive_ticker_fraction": positive_ticker_fraction,
            }
            results.append(result)
            self.debug("YOEL_PHASE_A|" + json.dumps(result, separators=(",", ":")))

        principal = next((
            item for item in results
            if item["universe"] == "U2"
            and item["segment"] == "OOS"
            and item["gap_threshold"] == 0.01
            and item["lookback"] == 5
            and item["strict_sma100"] is False
            and item["exclude_volume_spikes"] is True
        ), None)
        verdict = {
            "claim_tested": "P(second same-direction >=1% gap next session | first valid >=1% gap)",
            "course_claim": 0.90,
            "principal_oos_u2": principal,
            "phase_a_go": bool(
                principal
                and principal["passes_primary_gate"]
                and (principal["positive_ticker_fraction"] or 0) >= 0.70
            ),
        }
        if principal:
            self.set_runtime_statistic("YOEL Signal N", str(principal["signal_total"]))
            self.set_runtime_statistic("YOEL Signal Rate", f"{principal['signal_rate']:.6f}")
            self.set_runtime_statistic("YOEL Control Rate", f"{principal['control_rate']:.6f}")
            self.set_runtime_statistic("YOEL Lift PP", f"{principal['lift_pp']:.6f}")
            self.set_runtime_statistic(
                "YOEL Wilson 95",
                f"{principal['signal_wilson_95'][0]:.6f},{principal['signal_wilson_95'][1]:.6f}",
            )
            self.set_runtime_statistic(
                "YOEL Positive Tickers",
                f"{principal['positive_ticker_fraction']:.6f}",
            )
            self.set_runtime_statistic(
                "YOEL Next Intraday",
                f"{principal['next_day_directional_intraday_mean']:.8f}",
            )
        self.set_runtime_statistic("YOEL Phase A", "GO" if verdict["phase_a_go"] else "NO_GO")
        self.debug("YOEL_VERDICT|" + json.dumps(verdict, separators=(",", ":")))
