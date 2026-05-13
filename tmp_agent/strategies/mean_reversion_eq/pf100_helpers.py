def _parse_hhmm_list(self, raw):
    out = []
    if raw is None:
        return out
    for chunk in str(raw).split(","):
        token = chunk.strip()
        if not token:
            continue
        parts = token.split(":")
        if len(parts) != 2:
            continue
        try:
            h = int(parts[0])
            m = int(parts[1])
        except Exception:
            continue
        if 0 <= h <= 23 and 0 <= m <= 59:
            out.append((h, m))
    return out


def _is_mff_news_window(self):
    if not (self.mff_compliance_enabled and self.mff_news_guard_enabled):
        return False
    if self.mff_news_block_minutes < 0 or not self.mff_news_times:
        return False
    now_m = int(self.Time.hour) * 60 + int(self.Time.minute)
    pad = max(0, int(self.mff_news_block_minutes))
    for h, m in self.mff_news_times:
        event_m = int(h) * 60 + int(m)
        if abs(now_m - event_m) <= pad:
            return True
    return False


def _is_mff_price_limit_blocked(self, current_price, ref_price):
    if not (self.mff_compliance_enabled and self.mff_price_limit_guard_enabled):
        return False
    if ref_price is None or current_price is None:
        return False
    if ref_price <= 0 or current_price <= 0:
        return False
    threshold = max(0.01, float(self.mff_price_limit_pct))
    chg = abs((float(current_price) - float(ref_price)) / float(ref_price))
    return chg >= threshold


def _current_best_day_profit_usd(self):
    return max(float(self.best_day_profit_usd), float(self.day_best_pnl_usd))


def _current_consistency_pct(self, equity):
    total_profit = float(equity) - float(self.initial_cash)
    if total_profit <= 0:
        return 999.0
    best_day = self._current_best_day_profit_usd()
    if best_day <= 0:
        return 0.0
    return 100.0 * best_day / total_profit


def _check_pf100_signal(self, sym, info, atr_points):
    if self.stress_trades_today >= self.pf100_stress_max_trades_per_day:
        return None
    if info["daily_bars"].Count < 1 or info["daily_closes"].Count < 1:
        return None
    prev_bar = info["daily_bars"][0]
    prev_close = float(info["daily_closes"][0])
    prev_high = float(prev_bar.High)
    prev_low = float(prev_bar.Low)
    if prev_close <= 0 or prev_high <= 0 or prev_low <= 0 or prev_high <= prev_low:
        return None
    range_pct = (prev_high - prev_low) / prev_close
    if range_pct < self.pf100_stress_min_range_pct:
        return None
    sec = self.Securities[sym]
    current_price = float(sec.Price)
    if current_price <= 0:
        return None
    open_price = float(sec.Open) if sec.Open is not None else 0.0
    if open_price <= 0:
        return None
    intraday_mom = (current_price - open_price) / open_price

    long_break = current_price > prev_high * (1.0 + self.pf100_stress_breakout_buffer)
    short_break = current_price < prev_low * (1.0 - self.pf100_stress_breakout_buffer)
    if self.pf100_stress_gap_fallback and not (long_break or short_break):
        gap_pct = (current_price - prev_close) / prev_close
        long_break = gap_pct >= self.pf100_stress_min_gap_pct
        short_break = gap_pct <= -self.pf100_stress_min_gap_pct
    if self.pf100_stress_disable_shorts:
        short_break = False
    if self.pf100_stress_intraday_confirm:
        if long_break and intraday_mom < self.pf100_stress_intraday_mom_pct:
            long_break = False
        if short_break and intraday_mom > -self.pf100_stress_intraday_mom_pct:
            short_break = False
    if not (long_break or short_break):
        return None
    stop_dist = atr_points * self.pf100_stress_atr_stop
    if stop_dist <= 0:
        return None
    target_dist = atr_points * self.pf100_stress_atr_target
    if long_break:
        return {
            "direction": 1,
            "entry": current_price,
            "stop_dist": stop_dist,
            "stop": current_price - stop_dist,
            "target": current_price + target_dist,
            "hold_hours_limit": self.pf100_stress_max_hold_hours,
        }
    return {
        "direction": -1,
        "entry": current_price,
        "stop_dist": stop_dist,
        "stop": current_price + stop_dist,
        "target": current_price - target_dist,
        "hold_hours_limit": self.pf100_stress_max_hold_hours,
    }


def _pf100_try_partial(self, mapped, info, qty, cont_price):
    if not self.pf100_partial_enabled:
        return
    if info.get("partial_done", False):
        return
    if info.get("entry_qty", 0) < 2 or abs(qty) < 2:
        return
    direction = int(info.get("direction", 0))
    if direction == 0:
        return
    entry = float(info.get("entry_price", 0.0) or 0.0)
    r = float(info.get("initial_stop_dist", 0.0) or 0.0)
    if entry <= 0 or r <= 0:
        return

    tp_r = max(0.1, float(self.pf100_partial_tp_r))
    tp_price = entry + direction * tp_r * r
    reached = (direction == 1 and cont_price >= tp_price) or (direction == -1 and cont_price <= tp_price)
    if not reached:
        return

    frac = min(0.9, max(0.1, float(self.pf100_partial_fraction)))
    close_qty = int(round(info["entry_qty"] * frac))
    close_qty = max(1, close_qty)
    close_qty = min(close_qty, abs(qty) - 1)
    if close_qty < 1:
        return
    if not self._security_has_fresh_price(mapped):
        self.price_guard_skips += 1
        return

    if direction == 1:
        self.MarketOrder(mapped, -close_qty, tag="PF100_PARTIAL")
        info["stop_price"] = max(float(info["stop_price"]), entry)
    else:
        self.MarketOrder(mapped, close_qty, tag="PF100_PARTIAL")
        info["stop_price"] = min(float(info["stop_price"]), entry)

    info["partial_done"] = True
    self.pf100_partial_fills += 1

    if self.pf100_disable_target_after_partial:
        info["target_price"] = 1e30 if direction == 1 else -1e30


def _pf100_update_runner_trail(self, info, cont_price):
    if not self.pf100_runner_trail_enabled:
        return
    direction = int(info.get("direction", 0))
    if direction == 0:
        return
    entry = float(info.get("entry_price", 0.0) or 0.0)
    r = float(info.get("initial_stop_dist", 0.0) or 0.0)
    if entry <= 0 or r <= 0:
        return

    open_r = (cont_price - entry) / r if direction == 1 else (entry - cont_price) / r
    if open_r < max(0.1, float(self.pf100_runner_trail_start_r)):
        return

    atr = info.get("atr")
    atr_points = atr.Current.Value if atr is not None and atr.IsReady else 0.0
    if atr_points <= 0:
        return
    trail_dist = atr_points * max(0.1, float(self.pf100_runner_trail_atr_mult))

    if direction == 1:
        new_stop = cont_price - trail_dist
        if new_stop > float(info["stop_price"]):
            info["stop_price"] = new_stop
            self.pf100_runner_trail_updates += 1
    else:
        new_stop = cont_price + trail_dist
        if new_stop < float(info["stop_price"]):
            info["stop_price"] = new_stop
            self.pf100_runner_trail_updates += 1


def _pf100_pass_quality(self, info):
    if not self.pf100_quality_filter_enabled:
        return True
    if info["daily_bars"].Count < 2 or info["daily_closes"].Count < 2:
        return False

    prev_bar = info["daily_bars"][0]
    prev2_bar = info["daily_bars"][1]
    prev_close = float(info["daily_closes"][0]) if info["daily_closes"][0] is not None else 0.0
    prev2_close = float(info["daily_closes"][1]) if info["daily_closes"][1] is not None else 0.0
    if prev_close <= 0 or prev2_close <= 0:
        return False

    prev_range_pct = (float(prev_bar.High) - float(prev_bar.Low)) / prev_close
    prev2_range_pct = (float(prev2_bar.High) - float(prev2_bar.Low)) / prev2_close
    if prev_range_pct <= 0 or prev2_range_pct <= 0:
        return False
    if prev_range_pct < max(0.0005, float(self.pf100_quality_min_prev_range_pct)):
        return False
    return prev_range_pct >= prev2_range_pct * max(1.0, float(self.pf100_quality_range_exp_mult))


def bind_pf100_helpers(target_cls):
    target_cls._parse_hhmm_list = _parse_hhmm_list
    target_cls._is_mff_news_window = _is_mff_news_window
    target_cls._is_mff_price_limit_blocked = _is_mff_price_limit_blocked
    target_cls._current_best_day_profit_usd = _current_best_day_profit_usd
    target_cls._current_consistency_pct = _current_consistency_pct
    target_cls._check_pf100_signal = _check_pf100_signal
    target_cls._pf100_try_partial = _pf100_try_partial
    target_cls._pf100_update_runner_trail = _pf100_update_runner_trail
    target_cls._pf100_pass_quality = _pf100_pass_quality

