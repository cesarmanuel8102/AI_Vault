"""Analyze V1.8 trades in detail: winners vs losers, could losers have been saved?"""
import re

# Raw trade logs from V1.8 backtest (174 trades)
raw_logs = """
CLOSE YOEL_CALL_QQQ_230213_1: LIMIT_FILL_35% PnL=$+652(+35%) held=1d
CLOSE YOEL_CALL_AAPL_230301_2: SL_FILL=-32% PnL=$-290(-32%) held=1d
CLOSE YOEL_CALL_AAPL_230306_3: SL_FILL=-32% PnL=$-272(-32%) held=1d
CLOSE YOEL_CALL_QQQ_230406_4: LIMIT_FILL_35% PnL=$+534(+35%) held=0d
CLOSE YOEL_CALL_QQQ_230411_6: SL_FILL=-31% PnL=$-508(-31%) held=1d
CLOSE YOEL_CALL_AAPL_230411_5: LIMIT_FILL_35% PnL=$+360(+35%) held=3d
CLOSE YOEL_CALL_QQQ_230413_7: LIMIT_FILL_35% PnL=$+502(+35%) held=1d
CLOSE YOEL_CALL_NVDA_230417_9: LIMIT_FILL_35% PnL=$+914(+35%) held=0d
CLOSE YOEL_CALL_QQQ_230417_8: SL_FILL=-32% PnL=$-470(-32%) held=3d
CLOSE YOEL_CALL_AAPL_230418_10: TIME=5d PnL=$-200(-18%) held=5d
CLOSE YOEL_CALL_QQQ_230424_11: SL_FILL=-30% PnL=$-438(-30%) held=1d
CLOSE YOEL_CALL_AAPL_230426_13: LIMIT_FILL_35% PnL=$+386(+35%) held=1d
CLOSE YOEL_CALL_AAPL_230424_12: LIMIT_FILL_35% PnL=$+336(+35%) held=3d
CLOSE YOEL_CALL_QQQ_230501_15: SL_FILL=-32% PnL=$-460(-32%) held=2d
CLOSE YOEL_CALL_AAPL_230501_14: SL_FILL=-43% PnL=$-412(-43%) held=3d
CLOSE YOEL_CALL_NVDA_230504_16: LIMIT_FILL_35% PnL=$+1,022(+35%) held=1d
CLOSE YOEL_CALL_QQQ_230508_17: TIME=6d PnL=$+54(+4%) held=6d
CLOSE YOEL_CALL_QQQ_230509_18: TIME=5d PnL=$+133(+10%) held=5d
CLOSE YOEL_CALL_AAPL_230515_19: SL_FILL=-34% PnL=$-212(-34%) held=2d
CLOSE YOEL_CALL_QQQ_230515_20: LIMIT_FILL_35% PnL=$+488(+35%) held=2d
CLOSE YOEL_CALL_AAPL_230518_21: LIMIT_FILL_35% PnL=$+220(+35%) held=0d
CLOSE YOEL_CALL_AAPL_230522_22: SL_FILL=-32% PnL=$-224(-32%) held=1d
CLOSE YOEL_CALL_QQQ_230524_24: LIMIT_FILL_35% PnL=$+868(+61%) held=0d
CLOSE YOEL_CALL_AAPL_230523_23: LIMIT_FILL_35% PnL=$+294(+35%) held=3d
CLOSE YOEL_CALL_AAPL_230530_25: LIMIT_FILL_35% PnL=$+280(+35%) held=2d
CLOSE YOEL_CALL_AAPL_230531_26: LIMIT_FILL_35% PnL=$+280(+35%) held=1d
CLOSE YOEL_CALL_AAPL_230606_27: LIMIT_FILL_35% PnL=$+274(+35%) held=1d
CLOSE YOEL_CALL_AAPL_230607_28: SL_FILL=-32% PnL=$-256(-32%) held=0d
CLOSE YOEL_CALL_QQQ_230608_29: LIMIT_FILL_35% PnL=$+496(+35%) held=0d
CLOSE YOEL_CALL_AAPL_230612_30: LIMIT_FILL_35% PnL=$+354(+35%) held=3d
CLOSE YOEL_CALL_QQQ_230622_32: LIMIT_FILL_35% PnL=$+504(+35%) held=0d
CLOSE YOEL_CALL_MSFT_230621_31: SL_FILL=-27% PnL=$-490(-27%) held=5d
CLOSE YOEL_CALL_QQQ_230623_33: SL_FILL=-30% PnL=$-396(-30%) held=3d
CLOSE YOEL_CALL_QQQ_230627_35: LIMIT_FILL_35% PnL=$+474(+35%) held=0d
CLOSE YOEL_CALL_AAPL_230627_34: LIMIT_FILL_35% PnL=$+416(+35%) held=0d
CLOSE YOEL_CALL_AAPL_230628_36: LIMIT_FILL_35% PnL=$+276(+35%) held=1d
CLOSE YOEL_CALL_QQQ_230703_37: SL_FILL=-34% PnL=$-558(-34%) held=3d
CLOSE YOEL_CALL_QQQ_230705_38: SL_FILL=-27% PnL=$-392(-27%) held=5d
CLOSE YOEL_CALL_AAPL_230707_39: SL_FILL=-31% PnL=$-280(-31%) held=3d
CLOSE YOEL_CALL_QQQ_230711_40: LIMIT_FILL_35% PnL=$+554(+35%) held=0d
CLOSE YOEL_CALL_QQQ_230712_42: LIMIT_FILL_35% PnL=$+542(+35%) held=1d
CLOSE YOEL_CALL_AAPL_230711_41: TIME=5d PnL=$+130(+15%) held=5d
CLOSE YOEL_CALL_MSFT_230717_44: LIMIT_FILL_35% PnL=$+914(+35%) held=1d
CLOSE YOEL_CALL_AAPL_230717_43: LIMIT_FILL_35% PnL=$+280(+35%) held=2d
CLOSE YOEL_CALL_AAPL_230719_45: LIMIT_FILL_35% PnL=$+346(+35%) held=0d
CLOSE YOEL_CALL_AAPL_230725_47: LIMIT_FILL_35% PnL=$+392(+35%) held=2d
CLOSE YOEL_CALL_AAPL_230724_46: TIME=6d PnL=$+45(+5%) held=6d
CLOSE YOEL_CALL_AAPL_230728_48: LIMIT_FILL_35% PnL=$+60(+6%) held=2d
CLOSE YOEL_CALL_QQQ_230731_49: SL_FILL=-36% PnL=$-582(-36%) held=2d
CLOSE YOEL_CALL_AAPL_230731_50: SL_FILL=-31% PnL=$-350(-31%) held=2d
CLOSE YOEL_CALL_NVDA_230803_51: LIMIT_FILL_35% PnL=$+1,020(+17%) held=5d
CLOSE YOEL_CALL_QQQ_230807_52: SL_FILL=-30% PnL=$-512(-30%) held=2d
CLOSE YOEL_CALL_QQQ_230809_53: SL_FILL=-31% PnL=$-516(-31%) held=1d
CLOSE YOEL_CALL_QQQ_230810_54: SL_FILL=-36% PnL=$-566(-36%) held=1d
CLOSE YOEL_CALL_NVDA_230908_55: SL_FILL=-34% PnL=$-1,160(-34%) held=3d
CLOSE YOEL_CALL_NVDA_231127_56: SL_FILL=-29% PnL=$-1,070(-29%) held=3d
CLOSE YOEL_CALL_NVDA_231128_57: SL=-32% PnL=$-1,235(-32%) held=2d
CLOSE YOEL_CALL_AAPL_231201_58: SL_FILL=-33% PnL=$-214(-33%) held=3d
CLOSE YOEL_CALL_AAPL_231204_59: SL_FILL=-32% PnL=$-230(-32%) held=0d
CLOSE YOEL_CALL_MSFT_231205_60: LIMIT_FILL_35% PnL=$+676(+35%) held=0d
CLOSE YOEL_CALL_QQQ_231206_61: SL_FILL=-31% PnL=$-448(-31%) held=0d
CLOSE YOEL_CALL_MSFT_231211_63: LIMIT_FILL_35% PnL=$+522(+35%) held=1d
CLOSE YOEL_CALL_AAPL_231211_62: LIMIT_FILL_35% PnL=$+190(+35%) held=1d
CLOSE YOEL_CALL_AAPL_231213_64: LIMIT_FILL_35% PnL=$+262(+35%) held=0d
CLOSE YOEL_CALL_AAPL_231218_65: SL_FILL=-32% PnL=$-284(-32%) held=3d
CLOSE YOEL_CALL_MSFT_231218_66: TIME=7d PnL=$+205(+11%) held=7d
CLOSE YOEL_CALL_AAPL_231222_67: SL_FILL=-32% PnL=$-234(-32%) held=4d
CLOSE YOEL_CALL_AAPL_231226_68: SL_FILL=-31% PnL=$-280(-31%) held=1d
CLOSE YOEL_CALL_AAPL_231228_70: SL_FILL=-32% PnL=$-208(-32%) held=1d
CLOSE YOEL_CALL_AAPL_231227_69: TIME=5d PnL=$-95(-12%) held=5d
CLOSE YOEL_CALL_AAPL_240102_71: SL_FILL=-36% PnL=$-276(-36%) held=0d
CLOSE YOEL_CALL_QQQ_240102_72: SL_FILL=-31% PnL=$-392(-31%) held=0d
CLOSE YOEL_CALL_QQQ_240103_73: SL_FILL=-32% PnL=$-432(-32%) held=1d
CLOSE YOEL_CALL_QQQ_240108_74: LIMIT_FILL_35% PnL=$+590(+35%) held=0d
CLOSE YOEL_CALL_QQQ_240109_75: LIMIT_FILL_35% PnL=$+518(+35%) held=1d
CLOSE YOEL_CALL_QQQ_240110_76: LIMIT_FILL_35% PnL=$+494(+35%) held=1d
CLOSE YOEL_CALL_QQQ_240116_77: SL_FILL=-31% PnL=$-466(-31%) held=1d
CLOSE YOEL_CALL_QQQ_240117_78: LIMIT_FILL_35% PnL=$+462(+35%) held=0d
CLOSE YOEL_CALL_QQQ_240118_79: LIMIT_FILL_35% PnL=$+676(+35%) held=1d
CLOSE YOEL_CALL_MSFT_240202_81: LIMIT_FILL_35% PnL=$+442(+35%) held=0d
CLOSE YOEL_CALL_MSFT_240201_80: LIMIT_FILL_35% PnL=$+606(+35%) held=1d
CLOSE YOEL_CALL_MSFT_240206_83: SL_FILL=-32% PnL=$-480(-32%) held=0d
CLOSE YOEL_CALL_QQQ_240207_84: LIMIT_FILL_35% PnL=$+530(+35%) held=2d
CLOSE YOEL_CALL_QQQ_240206_82: LIMIT_FILL_35% PnL=$+578(+35%) held=3d
CLOSE YOEL_CALL_QQQ_240213_86: LIMIT_FILL_35% PnL=$+398(+35%) held=0d
CLOSE YOEL_CALL_MSFT_240213_85: TIME=6d PnL=$-190(-10%) held=6d
CLOSE YOEL_CALL_QQQ_240214_87: TIME=5d PnL=$-188(-11%) held=5d
CLOSE YOEL_CALL_QQQ_240220_88: SL_FILL=-30% PnL=$-520(-30%) held=0d
CLOSE YOEL_CALL_MSFT_240220_89: SL_FILL=-33% PnL=$-560(-33%) held=1d
CLOSE YOEL_CALL_QQQ_240221_90: LIMIT_FILL_35% PnL=$+1,044(+59%) held=0d
CLOSE YOEL_CALL_MSFT_240226_92: SL_FILL=-32% PnL=$-660(-32%) held=1d
CLOSE YOEL_CALL_QQQ_240228_93: LIMIT_FILL_35% PnL=$+544(+35%) held=1d
CLOSE YOEL_CALL_QQQ_240226_91: LIMIT_FILL_35% PnL=$+576(+35%) held=4d
CLOSE YOEL_CALL_QQQ_240304_95: SL_FILL=-32% PnL=$-508(-32%) held=1d
CLOSE YOEL_CALL_MSFT_240304_94: SL_FILL=-31% PnL=$-520(-31%) held=1d
CLOSE YOEL_CALL_MSFT_240306_96: LIMIT_FILL_35% PnL=$+780(+35%) held=1d
CLOSE YOEL_CALL_QQQ_240311_97: LIMIT_FILL_35% PnL=$+652(+35%) held=1d
CLOSE YOEL_CALL_QQQ_240313_99: SL_FILL=-32% PnL=$-522(-32%) held=1d
CLOSE YOEL_CALL_QQQ_240312_98: SL_FILL=-34% PnL=$-600(-34%) held=3d
CLOSE YOEL_CALL_QQQ_240318_101: SL_FILL=-32% PnL=$-700(-32%) held=1d
CLOSE YOEL_CALL_MSFT_240318_100: LIMIT_FILL_35% PnL=$+774(+35%) held=2d
CLOSE YOEL_CALL_QQQ_240320_102: LIMIT_FILL_35% PnL=$+642(+35%) held=0d
CLOSE YOEL_CALL_MSFT_240326_104: SL_FILL=-31% PnL=$-540(-31%) held=1d
CLOSE YOEL_CALL_QQQ_240325_103: TIME=6d PnL=$-238(-14%) held=6d
CLOSE YOEL_CALL_QQQ_240328_105: LIMIT_FILL_35% PnL=$-70(-5%) held=3d
CLOSE YOEL_CALL_QQQ_240401_106: SL_FILL=-35% PnL=$-594(-35%) held=1d
CLOSE YOEL_CALL_QQQ_240402_107: LIMIT_FILL_35% PnL=$+516(+35%) held=1d
CLOSE YOEL_CALL_QQQ_240403_108: LIMIT_FILL_35% PnL=$+580(+35%) held=0d
CLOSE YOEL_CALL_MSFT_240408_109: TIME=6d PnL=$-390(-14%) held=6d
CLOSE YOEL_CALL_MSFT_240409_110: TIME=5d PnL=$-410(-15%) held=5d
CLOSE YOEL_CALL_QQQ_240415_112: SL_FILL=-31% PnL=$-622(-31%) held=0d
CLOSE YOEL_CALL_MSFT_240415_111: SL_FILL=-31% PnL=$-880(-31%) held=0d
CLOSE YOEL_CALL_MSFT_240416_113: SL_FILL=-31% PnL=$-880(-31%) held=2d
CLOSE YOEL_CALL_AAPL_240524_114: LIMIT_FILL_35% PnL=$+242(+35%) held=3d
CLOSE YOEL_CALL_QQQ_240524_115: LIMIT_FILL_35% PnL=$+462(+35%) held=4d
CLOSE YOEL_CALL_QQQ_240530_117: SL_FILL=-34% PnL=$-580(-34%) held=1d
CLOSE YOEL_CALL_AAPL_240529_116: LIMIT_FILL_35% PnL=$+240(+25%) held=5d
CLOSE YOEL_CALL_QQQ_240604_119: LIMIT_FILL_35% PnL=$+590(+35%) held=0d
CLOSE YOEL_CALL_MSFT_240603_118: LIMIT_FILL_35% PnL=$+672(+35%) held=2d
CLOSE YOEL_CALL_QQQ_240605_120: LIMIT_FILL_35% PnL=$+572(+35%) held=0d
CLOSE YOEL_CALL_AAPL_240611_122: LIMIT_FILL_35% PnL=$+316(+35%) held=0d
CLOSE YOEL_CALL_QQQ_240610_121: LIMIT_FILL_35% PnL=$+570(+35%) held=1d
CLOSE YOEL_CALL_MSFT_240612_123: LIMIT_FILL_35% PnL=$+630(+35%) held=0d
CLOSE YOEL_CALL_QQQ_240701_124: LIMIT_FILL_35% PnL=$+646(+35%) held=1d
CLOSE YOEL_CALL_AAPL_240701_125: LIMIT_FILL_35% PnL=$+330(+35%) held=0d
CLOSE YOEL_CALL_QQQ_240702_126: LIMIT_FILL_35% PnL=$+614(+35%) held=0d
CLOSE YOEL_CALL_QQQ_240712_128: LIMIT_FILL_35% PnL=$+624(+35%) held=0d
CLOSE YOEL_CALL_MSFT_240710_127: SL_FILL=-23% PnL=$-620(-23%) held=5d
CLOSE YOEL_CALL_MSFT_240715_129: SL_FILL=-32% PnL=$-910(-32%) held=1d
CLOSE YOEL_CALL_MSFT_240716_130: SL_FILL=-44% PnL=$-1,210(-44%) held=1d
CLOSE YOEL_CALL_MSFT_240717_131: SL_FILL=-11% PnL=$-330(-11%) held=5d
CLOSE YOEL_CALL_QQQ_240722_132: SL_FILL=-43% PnL=$-862(-43%) held=2d
CLOSE YOEL_CALL_QQQ_240723_133: SL_FILL=-43% PnL=$-898(-43%) held=1d
CLOSE YOEL_CALL_AAPL_240905_134: SL_FILL=-37% PnL=$-410(-37%) held=4d
CLOSE YOEL_CALL_AAPL_240925_135: LIMIT_FILL_35% PnL=$+374(+35%) held=1d
CLOSE YOEL_CALL_AAPL_240926_136: LIMIT_FILL_35% PnL=$+340(+35%) held=3d
CLOSE YOEL_CALL_AAPL_240927_137: LIMIT_FILL_35% PnL=$+322(+35%) held=2d
CLOSE YOEL_CALL_QQQ_240930_138: SL_FILL=-31% PnL=$-654(-31%) held=1d
CLOSE YOEL_CALL_QQQ_241003_140: LIMIT_FILL_35% PnL=$+716(+35%) held=1d
CLOSE YOEL_CALL_MSFT_241002_139: SL_FILL=-28% PnL=$-660(-28%) held=5d
CLOSE YOEL_CALL_QQQ_241008_142: LIMIT_FILL_35% PnL=$+774(+35%) held=1d
CLOSE YOEL_CALL_MSFT_241007_141: TIME=6d PnL=$-170(-6%) held=6d
CLOSE YOEL_CALL_QQQ_241010_143: LIMIT_FILL_35% PnL=$+722(+35%) held=4d
CLOSE YOEL_CALL_QQQ_241014_144: SL_FILL=-30% PnL=$-718(-30%) held=1d
CLOSE YOEL_CALL_AAPL_241015_145: SL_FILL=-31% PnL=$-400(-31%) held=1d
CLOSE YOEL_CALL_AAPL_241016_146: LIMIT_FILL_35% PnL=$+230(+15%) held=5d
CLOSE YOEL_CALL_QQQ_241021_147: SL_FILL=-32% PnL=$-692(-32%) held=2d
CLOSE YOEL_CALL_QQQ_241022_148: SL_FILL=-31% PnL=$-720(-31%) held=1d
CLOSE YOEL_CALL_QQQ_241024_149: LIMIT_FILL_35% PnL=$+816(+35%) held=1d
CLOSE YOEL_CALL_AAPL_241028_151: SL_FILL=-33% PnL=$-440(-33%) held=3d
CLOSE YOEL_CALL_QQQ_241028_150: SL_FILL=-33% PnL=$-828(-33%) held=3d
CLOSE YOEL_CALL_QQQ_241101_152: LIMIT_FILL_35% PnL=$+832(+35%) held=4d
CLOSE YOEL_CALL_QQQ_241104_153: LIMIT_FILL_35% PnL=$+972(+35%) held=1d
CLOSE YOEL_CALL_QQQ_241106_154: LIMIT_FILL_35% PnL=$+1,012(+35%) held=1d
CLOSE YOEL_CALL_QQQ_241107_155: LIMIT_FILL_35% PnL=$+242(+13%) held=5d
CLOSE YOEL_CALL_QQQ_241114_156: SL_FILL=-54% PnL=$-972(-54%) held=1d
CLOSE YOEL_CALL_QQQ_241115_157: SL_FILL=-32% PnL=$-492(-32%) held=0d
CLOSE YOEL_CALL_QQQ_241118_158: LIMIT_FILL_35% PnL=$+758(+35%) held=2d
CLOSE YOEL_CALL_QQQ_241119_159: LIMIT_FILL_35% PnL=$+748(+35%) held=1d
CLOSE YOEL_CALL_QQQ_241121_160: SL_FILL=-34% PnL=$-708(-34%) held=0d
CLOSE YOEL_CALL_QQQ_241129_162: LIMIT_FILL_35% PnL=$+582(+35%) held=2d
CLOSE YOEL_CALL_QQQ_241127_161: LIMIT_FILL_35% PnL=$+532(+30%) held=5d
CLOSE YOEL_CALL_QQQ_241202_163: LIMIT_FILL_35% PnL=$+618(+35%) held=1d
CLOSE YOEL_CALL_QQQ_241203_164: LIMIT_FILL_35% PnL=$+592(+35%) held=0d
CLOSE YOEL_CALL_MSFT_241204_165: LIMIT_FILL_35% PnL=$+608(+35%) held=1d
CLOSE YOEL_CALL_QQQ_241210_166: LIMIT_FILL_35% PnL=$+604(+35%) held=1d
CLOSE YOEL_CALL_QQQ_241211_167: LIMIT_FILL_35% PnL=$+606(+35%) held=0d
CLOSE YOEL_CALL_QQQ_241213_168: LIMIT_FILL_35% PnL=$+580(+35%) held=3d
CLOSE YOEL_CALL_AAPL_241219_169: LIMIT_FILL_35% PnL=$+308(+35%) held=0d
CLOSE YOEL_CALL_QQQ_241220_170: SL_FILL=-45% PnL=$-1,072(-45%) held=1d
CLOSE YOEL_CALL_QQQ_241220_171: LIMIT_FILL_35% PnL=$+762(+35%) held=0d
CLOSE YOEL_CALL_QQQ_241223_172: LIMIT_FILL_35% PnL=$+846(+35%) held=3d
CLOSE YOEL_CALL_QQQ_241224_173: SL_FILL=-32% PnL=$-658(-32%) held=3d
CLOSE YOEL_CALL_QQQ_241227_174: SL_FILL=-31% PnL=$-592(-31%) held=0d
""".strip()

# Parse trades
trades = []
for line in raw_logs.split('\n'):
    line = line.strip()
    if not line or 'CLOSE' not in line:
        continue
    
    # Extract tag
    m_tag = re.search(r'CLOSE (YOEL_CALL_\w+):', line)
    if not m_tag:
        continue
    tag = m_tag.group(1)
    
    # Extract ticker
    parts = tag.split('_')
    ticker = parts[2]  # YOEL_CALL_QQQ_...
    
    # Extract reason
    m_reason = re.search(r': (\S+)', line[line.index(':'):])
    reason_full = m_reason.group(1) if m_reason else "UNKNOWN"
    reason_type = reason_full.split('=')[0].replace('%','')
    
    # Extract PnL dollar
    m_pnl = re.search(r'PnL=\$([+\-][\d,]+)', line)
    pnl_dollar = int(m_pnl.group(1).replace(',','').replace('+','')) if m_pnl else 0
    
    # Extract PnL pct
    m_pct = re.search(r'\(([+\-]\d+)%\)', line)
    pnl_pct = int(m_pct.group(1)) if m_pct else 0
    
    # Extract held days
    m_held = re.search(r'held=(\d+)d', line)
    held = int(m_held.group(1)) if m_held else 0
    
    trades.append({
        'tag': tag, 'ticker': ticker, 'reason': reason_type,
        'reason_full': reason_full, 'pnl_dollar': pnl_dollar,
        'pnl_pct': pnl_pct, 'held': held
    })

print(f"Total trades parsed: {len(trades)}")
print()

# ═══ 1. WINNERS vs LOSERS by exit reason ═══
print("=" * 70)
print("1. WINNERS VS LOSERS BY EXIT REASON")
print("=" * 70)

winners = [t for t in trades if t['pnl_dollar'] > 0]
losers = [t for t in trades if t['pnl_dollar'] <= 0]

print(f"\nGANADORES: {len(winners)} trades ({len(winners)/len(trades)*100:.1f}%)")
print(f"PERDEDORES: {len(losers)} trades ({len(losers)/len(trades)*100:.1f}%)")
print(f"PnL Total Ganadores: ${sum(t['pnl_dollar'] for t in winners):+,}")
print(f"PnL Total Perdedores: ${sum(t['pnl_dollar'] for t in losers):+,}")

# By exit type
print("\n--- Ganadores por causa de salida ---")
for reason in sorted(set(t['reason'] for t in winners)):
    rt = [t for t in winners if t['reason'] == reason]
    avg_pnl = sum(t['pnl_dollar'] for t in rt) / len(rt)
    avg_pct = sum(t['pnl_pct'] for t in rt) / len(rt)
    avg_held = sum(t['held'] for t in rt) / len(rt)
    print(f"  {reason:20s}: {len(rt):3d} trades | Avg PnL ${avg_pnl:+,.0f} ({avg_pct:+.0f}%) | Avg Held {avg_held:.1f}d | Total ${sum(t['pnl_dollar'] for t in rt):+,}")

print("\n--- Perdedores por causa de salida ---")
for reason in sorted(set(t['reason'] for t in losers)):
    rt = [t for t in losers if t['reason'] == reason]
    avg_pnl = sum(t['pnl_dollar'] for t in rt) / len(rt)
    avg_pct = sum(t['pnl_pct'] for t in rt) / len(rt)
    avg_held = sum(t['held'] for t in rt) / len(rt)
    print(f"  {reason:20s}: {len(rt):3d} trades | Avg PnL ${avg_pnl:+,.0f} ({avg_pct:+.0f}%) | Avg Held {avg_held:.1f}d | Total ${sum(t['pnl_dollar'] for t in rt):+,}")

# ═══ 2. SL LOSERS: Could they have been winners? ═══
print("\n" + "=" * 70)
print("2. PERDEDORES POR SL: ANALISIS DE VELOCIDAD DE CAIDA")
print("=" * 70)

sl_losers = [t for t in losers if t['reason'] in ('SL_FILL', 'SL')]
print(f"\nTotal SL losers: {len(sl_losers)}")
print(f"Total SL PnL: ${sum(t['pnl_dollar'] for t in sl_losers):+,}")

# How fast did they hit SL?
print("\n--- Velocidad de caida (dias hasta SL) ---")
by_held = {}
for t in sl_losers:
    h = t['held']
    if h not in by_held:
        by_held[h] = {'n': 0, 'pnl': 0}
    by_held[h]['n'] += 1
    by_held[h]['pnl'] += t['pnl_dollar']

for h in sorted(by_held.keys()):
    d = by_held[h]
    print(f"  Dia {h}: {d['n']:3d} trades, PnL ${d['pnl']:+,} (avg ${d['pnl']//d['n']:+,})")

# How many SL trades went past -30%? (indicates gap through SL)
print("\n--- SL que excedieron -30% (slippage / gap) ---")
severe_sl = [t for t in sl_losers if t['pnl_pct'] < -33]
mild_sl = [t for t in sl_losers if t['pnl_pct'] >= -33]
print(f"  SL normal (-30% a -33%): {len(mild_sl)} trades, PnL ${sum(t['pnl_dollar'] for t in mild_sl):+,}")
print(f"  SL severo (< -33%):      {len(severe_sl)} trades, PnL ${sum(t['pnl_dollar'] for t in severe_sl):+,}")
for t in severe_sl:
    print(f"    {t['tag']}: {t['pnl_pct']}% ${t['pnl_dollar']:+,} held={t['held']}d")

# ═══ 3. TIME LOSERS: were they ever positive? ═══
print("\n" + "=" * 70)
print("3. TRADES POR TIME EXIT (¿fueron alguna vez ganadores?)")
print("=" * 70)

time_trades = [t for t in trades if t['reason'] == 'TIME']
time_winners = [t for t in time_trades if t['pnl_dollar'] > 0]
time_losers = [t for t in time_trades if t['pnl_dollar'] <= 0]
print(f"\nTIME exits: {len(time_trades)} total")
print(f"  Positivos: {len(time_winners)} — PnL ${sum(t['pnl_dollar'] for t in time_winners):+,}")
print(f"  Negativos: {len(time_losers)} — PnL ${sum(t['pnl_dollar'] for t in time_losers):+,}")
for t in time_trades:
    status = "WIN" if t['pnl_dollar'] > 0 else "LOSS"
    print(f"    {t['tag']}: {t['pnl_pct']:+d}% ${t['pnl_dollar']:+,} held={t['held']}d [{status}]")

# ═══ 4. ANALYSIS: What if SL was tighter? ═══
print("\n" + "=" * 70)
print("4. SIMULACION: ¿QUE SI EL SL FUERA MAS APRETADO?")
print("=" * 70)

# We can't truly simulate without tick data, but we can estimate:
# If SL were -20% instead of -30%, the losses would be ~33% smaller on SL trades
# BUT some winning trades that dipped before recovering would have been stopped out

# Current: SL at -30%, avg SL loss is around -32%
# If SL -20%: avg loss would be ~-22% (saving ~$150-200 per trade)
# But unknown how many winners dipped below -20% before recovering

current_sl_pnl = sum(t['pnl_dollar'] for t in sl_losers)
# Estimate if losses were capped at -20% (proportional reduction)
estimated_20_pnl = sum(int(t['pnl_dollar'] * 20 / abs(t['pnl_pct'])) if t['pnl_pct'] != 0 else t['pnl_dollar'] for t in sl_losers)
saving = estimated_20_pnl - current_sl_pnl

print(f"\nActual SL -30%: {len(sl_losers)} trades, PnL ${current_sl_pnl:+,}")
print(f"Estimado SL -20%: mismos trades, PnL ~${estimated_20_pnl:+,}")
print(f"Ahorro estimado: ${saving:+,}")
print(f"NOTA: Esto NO cuenta trades ganadores que hubieran sido sacados por SL -20%")
print(f"      Si muchos winners caen -20% antes de subir +35%, el SL mas apretado PERDERIA mas")

# ═══ 5. TRAILING STOP ANALYSIS ═══
print("\n" + "=" * 70)
print("5. ¿SE HAN PROBADO TRAILING STOPS?")
print("=" * 70)
print("""
NO. Ninguna version ha probado trailing stops. El sistema actual usa:
  - LIMIT sell fijo a +35% (profit target)
  - SL fijo a -30% (hard stop loss)
  - TIME exit a 5 dias max hold

Un trailing stop podria:
  A) TRAILING TP: En vez de limit fijo +35%, mover el TP a medida que sube.
     Ej: Si la opcion sube +20%, mover SL a breakeven (+0%).
     Si sube +35%, mover SL a +20%. Dejar correr.
     RIESGO: El 99% WR del LIMIT_FILL muestra que +35% funciona muy bien.
             Un trailing podria dejar profit en la mesa si se reversa.

  B) TRAILING SL: En vez de SL fijo -30%, apretar el SL si no hay movimiento.
     Ej: Dia 0-1: SL -30%, Dia 2-3: SL -20%, Dia 4-5: SL -10%.
     BENEFICIO: Reduce perdidas en trades que languidecen.

  C) BREAKEVEN STOP: Si sube +10-15%, mover SL a breakeven.
     Esto protegeria los trades que ESTUVIERON en verde y luego cayeron.
""")

# ═══ 6. RAPID-FIRE LOSERS (same ticker, consecutive losses) ═══
print("=" * 70)
print("6. RACHAS DE PERDIDAS CONSECUTIVAS")
print("=" * 70)

streak = 0
max_streak = 0
max_streak_pnl = 0
current_streak_pnl = 0
streaks = []

for t in trades:
    if t['pnl_dollar'] <= 0:
        streak += 1
        current_streak_pnl += t['pnl_dollar']
    else:
        if streak >= 3:
            streaks.append((streak, current_streak_pnl))
        if streak > max_streak:
            max_streak = streak
            max_streak_pnl = current_streak_pnl
        streak = 0
        current_streak_pnl = 0

if streak >= 3:
    streaks.append((streak, current_streak_pnl))
if streak > max_streak:
    max_streak = streak
    max_streak_pnl = current_streak_pnl

print(f"\nMax racha perdedora: {max_streak} trades consecutivos, PnL ${max_streak_pnl:+,}")
print(f"Rachas >= 3 perdidas consecutivas: {len(streaks)}")
for i, (s, p) in enumerate(streaks):
    print(f"  Racha {i+1}: {s} trades, PnL ${p:+,}")

# ═══ 7. SUMMARY TABLE ═══
print("\n" + "=" * 70)
print("7. RESUMEN EJECUTIVO")
print("=" * 70)

total_win_pnl = sum(t['pnl_dollar'] for t in winners)
total_loss_pnl = sum(t['pnl_dollar'] for t in losers)

print(f"""
GANADORES: {len(winners)}/{len(trades)} ({len(winners)/len(trades)*100:.0f}%) | ${total_win_pnl:+,}
  - LIMIT_FILL_35%: El motor principal. 91 trades, 99% WR, +$49,024
  - TIME (positivos): 5 trades que no llegaron a +35% pero cerraron arriba
  - Avg win: ${total_win_pnl//len(winners):+,} | Avg hold: {sum(t['held'] for t in winners)/len(winners):.1f}d

PERDEDORES: {len(losers)}/{len(trades)} ({len(losers)/len(trades)*100:.0f}%) | ${total_loss_pnl:+,}
  - SL_FILL/SL: {len(sl_losers)} trades, la MAYORIA caen rapido (dia 0-1)
  - TIME (negativos): Trades que languidecieron sin llegar a +35% ni -30%
  - Avg loss: ${total_loss_pnl//len(losers):+,} | Avg hold: {sum(t['held'] for t in losers)/len(losers):.1f}d

EDGE NETO: ${total_win_pnl + total_loss_pnl:+,} sobre {len(trades)} trades
AVG PnL/TRADE: ${(total_win_pnl + total_loss_pnl)//len(trades):+,}
""")
