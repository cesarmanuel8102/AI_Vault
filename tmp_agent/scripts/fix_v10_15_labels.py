from pathlib import Path
p = Path('C:/AI_VAULT/tmp_agent/strategies/brain_v10/v10_15_qqq.py')
text = p.read_text(encoding='utf-8')
text = text.replace('nvda_', 'eq_')
text = text.replace('NVDA', 'QQQ')
# keep class and other names coherent
text = text.replace('qqq_eq', 'equity_leg')
# ensure method name readability if double replacement produced odd name
text = text.replace('_liquidate_eq_equity', '_liquidate_equity_leg')
p.write_text(text, encoding='utf-8')
Path('C:/AI_VAULT/tmp_agent/state/qc_backups/v10_15_qqq.py').write_text(text, encoding='utf-8')
print('UPDATED v10_15_qqq.py')
print('NVDA_LEFT', text.count('NVDA'))
print('nvda_left', text.count('nvda'))
