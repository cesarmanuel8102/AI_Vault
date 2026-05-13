import re
from pathlib import Path

src = Path('C:/AI_VAULT/tmp_agent/state/qc_backups/v10_13b_champion_reconstructed.py')
out1 = Path('C:/AI_VAULT/tmp_agent/strategies/brain_v10/v10_15_qqq.py')
out2 = Path('C:/AI_VAULT/tmp_agent/state/qc_backups/v10_15_qqq.py')
text = src.read_text(encoding='utf-8')

# Version labels and default end date
text = text.replace('Brain V10.13b', 'Brain V10.15')
text = text.replace('V10.13b', 'V10.15')
text = text.replace('v10.13b', 'v10.15')
text = text.replace('BT_END   = (2026, 3, 23)', 'BT_END   = (2026, 4, 7)')

# Date parameterization: only start_year/end_year are free parameters
old_dates = '        self.SetStartDate(*self.BT_START)\n        self.SetEndDate(*self.BT_END)\n        self.SetCash(self.CASH)'
new_dates = '''        start_year = self._param_int("start_year", self.BT_START[0])\n        end_year = self._param_int("end_year", self.BT_END[0])\n\n        if start_year > self.BT_START[0]:\n            start_month, start_day = 1, 1\n        else:\n            start_month, start_day = self.BT_START[1], self.BT_START[2]\n\n        if end_year < self.BT_END[0]:\n            end_month, end_day = 12, 31\n        else:\n            end_month, end_day = self.BT_END[1], self.BT_END[2]\n\n        self.SetStartDate(start_year, start_month, start_day)\n        self.SetEndDate(end_year, end_month, end_day)\n        self.SetCash(self.CASH)'''
if old_dates not in text:
    raise RuntimeError('Initialize date block not found')
text = text.replace(old_dates, new_dates, 1)

# Core equity/ticker substitutions
text = re.sub(r'\bNVDA_', 'EQ_', text)
text = text.replace('BULL_EQUITY_WEIGHTS   = {"NVDA": 1.0}', 'BULL_EQUITY_WEIGHTS   = {"QQQ": 1.0}')
text = text.replace('"NVDA"', '"QQQ"')
text = re.sub(r'\bnvda_', 'eq_', text)
text = text.replace('self.nvda', 'self.eq_symbol')
text = text.replace('eq_eq', 'qqq_eq')

# Improve method name readability after automated renaming
text = text.replace('_liquidate_eq_equity', '_liquidate_equity_leg')

# Add param helper before _current_dd
anchor = '    def _current_dd(self):'
helper = '''    def _param_int(self, name, default):\n        raw = self.GetParameter(name)\n        if raw is None or raw == "":\n            return default\n        try:\n            return int(raw)\n        except Exception:\n            self.Log(f"PARAM_WARN: invalid {name}={raw}; using default {default}")\n            return default\n\n'''
if anchor not in text:
    raise RuntimeError('Helper anchor not found')
text = text.replace(anchor, helper + anchor, 1)

# Mandatory final liquidation
needle = '    def OnEndOfAlgorithm(self):\n'
insert = '    def OnEndOfAlgorithm(self):\n        self.Liquidate()\n\n'
if needle not in text:
    raise RuntimeError('OnEndOfAlgorithm not found')
text = text.replace(needle, insert, 1)

out1.write_text(text, encoding='utf-8')
out2.write_text(text, encoding='utf-8')

remaining = [line for line in text.splitlines() if ('NVDA' in line or 'self.nvda' in line or 'nvda_' in line)]
print(f'WROTE: {out1}')
print(f'WROTE: {out2}')
print(f'REMAINING_NVDA_REFERENCES: {len(remaining)}')
if remaining:
    for line in remaining[:20]:
        print(line)
