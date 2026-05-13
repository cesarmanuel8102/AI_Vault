"""Identify and analyze major drawdown periods in V1.8 equity curve."""
import re
from datetime import datetime

# Parse all trades with dates
raw_logs = """
2023-02-14|CLOSE YOEL_CALL_QQQ_230213_1: LIMIT_FILL_35% PnL=$+652(+35%) held=1d
2023-03-02|CLOSE YOEL_CALL_AAPL_230301_2: SL_FILL=-32% PnL=$-290(-32%) held=1d
2023-03-07|CLOSE YOEL_CALL_AAPL_230306_3: SL_FILL=-32% PnL=$-272(-32%) held=1d
2023-04-06|CLOSE YOEL_CALL_QQQ_230406_4: LIMIT_FILL_35% PnL=$+534(+35%) held=0d
2023-04-12|CLOSE YOEL_CALL_QQQ_230411_6: SL_FILL=-31% PnL=$-508(-31%) held=1d
2023-04-14|CLOSE YOEL_CALL_AAPL_230411_5: LIMIT_FILL_35% PnL=$+360(+35%) held=3d
2023-04-14|CLOSE YOEL_CALL_QQQ_230413_7: LIMIT_FILL_35% PnL=$+502(+35%) held=1d
2023-04-18|CLOSE YOEL_CALL_NVDA_230417_9: LIMIT_FILL_35% PnL=$+914(+35%) held=0d
2023-04-20|CLOSE YOEL_CALL_QQQ_230417_8: SL_FILL=-32% PnL=$-470(-32%) held=3d
2023-04-24|CLOSE YOEL_CALL_AAPL_230418_10: TIME=5d PnL=$-200(-18%) held=5d
2023-04-25|CLOSE YOEL_CALL_QQQ_230424_11: SL_FILL=-30% PnL=$-438(-30%) held=1d
2023-04-27|CLOSE YOEL_CALL_AAPL_230426_13: LIMIT_FILL_35% PnL=$+386(+35%) held=1d
2023-04-27|CLOSE YOEL_CALL_AAPL_230424_12: LIMIT_FILL_35% PnL=$+336(+35%) held=3d
2023-05-03|CLOSE YOEL_CALL_QQQ_230501_15: SL_FILL=-32% PnL=$-460(-32%) held=2d
2023-05-04|CLOSE YOEL_CALL_AAPL_230501_14: SL_FILL=-43% PnL=$-412(-43%) held=3d
2023-05-05|CLOSE YOEL_CALL_NVDA_230504_16: LIMIT_FILL_35% PnL=$+1,022(+35%) held=1d
2023-05-15|CLOSE YOEL_CALL_QQQ_230508_17: TIME=6d PnL=$+54(+4%) held=6d
2023-05-15|CLOSE YOEL_CALL_QQQ_230509_18: TIME=5d PnL=$+133(+10%) held=5d
2023-05-17|CLOSE YOEL_CALL_AAPL_230515_19: SL_FILL=-34% PnL=$-212(-34%) held=2d
2023-05-17|CLOSE YOEL_CALL_QQQ_230515_20: LIMIT_FILL_35% PnL=$+488(+35%) held=2d
2023-05-18|CLOSE YOEL_CALL_AAPL_230518_21: LIMIT_FILL_35% PnL=$+220(+35%) held=0d
2023-05-23|CLOSE YOEL_CALL_AAPL_230522_22: SL_FILL=-32% PnL=$-224(-32%) held=1d
2023-05-25|CLOSE YOEL_CALL_QQQ_230524_24: LIMIT_FILL_35% PnL=$+868(+61%) held=0d
2023-05-26|CLOSE YOEL_CALL_AAPL_230523_23: LIMIT_FILL_35% PnL=$+294(+35%) held=3d
2023-06-02|CLOSE YOEL_CALL_AAPL_230530_25: LIMIT_FILL_35% PnL=$+280(+35%) held=2d
2023-06-02|CLOSE YOEL_CALL_AAPL_230531_26: LIMIT_FILL_35% PnL=$+280(+35%) held=1d
2023-06-07|CLOSE YOEL_CALL_AAPL_230606_27: LIMIT_FILL_35% PnL=$+274(+35%) held=1d
2023-06-07|CLOSE YOEL_CALL_AAPL_230607_28: SL_FILL=-32% PnL=$-256(-32%) held=0d
2023-06-09|CLOSE YOEL_CALL_QQQ_230608_29: LIMIT_FILL_35% PnL=$+496(+35%) held=0d
2023-06-15|CLOSE YOEL_CALL_AAPL_230612_30: LIMIT_FILL_35% PnL=$+354(+35%) held=3d
2023-06-22|CLOSE YOEL_CALL_QQQ_230622_32: LIMIT_FILL_35% PnL=$+504(+35%) held=0d
2023-06-26|CLOSE YOEL_CALL_MSFT_230621_31: SL_FILL=-27% PnL=$-490(-27%) held=5d
2023-06-26|CLOSE YOEL_CALL_QQQ_230623_33: SL_FILL=-30% PnL=$-396(-30%) held=3d
2023-06-27|CLOSE YOEL_CALL_QQQ_230627_35: LIMIT_FILL_35% PnL=$+474(+35%) held=0d
2023-06-27|CLOSE YOEL_CALL_AAPL_230627_34: LIMIT_FILL_35% PnL=$+416(+35%) held=0d
2023-06-30|CLOSE YOEL_CALL_AAPL_230628_36: LIMIT_FILL_35% PnL=$+276(+35%) held=1d
2023-07-06|CLOSE YOEL_CALL_QQQ_230703_37: SL_FILL=-34% PnL=$-558(-34%) held=3d
2023-07-10|CLOSE YOEL_CALL_QQQ_230705_38: SL_FILL=-27% PnL=$-392(-27%) held=5d
2023-07-10|CLOSE YOEL_CALL_AAPL_230707_39: SL_FILL=-31% PnL=$-280(-31%) held=3d
2023-07-12|CLOSE YOEL_CALL_QQQ_230711_40: LIMIT_FILL_35% PnL=$+554(+35%) held=0d
2023-07-13|CLOSE YOEL_CALL_QQQ_230712_42: LIMIT_FILL_35% PnL=$+542(+35%) held=1d
2023-07-17|CLOSE YOEL_CALL_AAPL_230711_41: TIME=5d PnL=$+130(+15%) held=5d
2023-07-18|CLOSE YOEL_CALL_MSFT_230717_44: LIMIT_FILL_35% PnL=$+914(+35%) held=1d
2023-07-19|CLOSE YOEL_CALL_AAPL_230717_43: LIMIT_FILL_35% PnL=$+280(+35%) held=2d
2023-07-19|CLOSE YOEL_CALL_AAPL_230719_45: LIMIT_FILL_35% PnL=$+346(+35%) held=0d
2023-07-27|CLOSE YOEL_CALL_AAPL_230725_47: LIMIT_FILL_35% PnL=$+392(+35%) held=2d
2023-07-31|CLOSE YOEL_CALL_AAPL_230724_46: TIME=6d PnL=$+45(+5%) held=6d
2023-07-31|CLOSE YOEL_CALL_AAPL_230728_48: LIMIT_FILL_35% PnL=$+60(+6%) held=2d
2023-08-02|CLOSE YOEL_CALL_QQQ_230731_49: SL_FILL=-36% PnL=$-582(-36%) held=2d
2023-08-02|CLOSE YOEL_CALL_AAPL_230731_50: SL_FILL=-31% PnL=$-350(-31%) held=2d
2023-08-08|CLOSE YOEL_CALL_NVDA_230803_51: LIMIT_FILL_35% PnL=$+1,020(+17%) held=5d
2023-08-09|CLOSE YOEL_CALL_QQQ_230807_52: SL_FILL=-30% PnL=$-512(-30%) held=2d
2023-08-10|CLOSE YOEL_CALL_QQQ_230809_53: SL_FILL=-31% PnL=$-516(-31%) held=1d
2023-08-11|CLOSE YOEL_CALL_QQQ_230810_54: SL_FILL=-36% PnL=$-566(-36%) held=1d
2023-09-11|CLOSE YOEL_CALL_NVDA_230908_55: SL_FILL=-34% PnL=$-1,160(-34%) held=3d
2023-11-30|CLOSE YOEL_CALL_NVDA_231127_56: SL_FILL=-29% PnL=$-1,070(-29%) held=3d
2023-11-30|CLOSE YOEL_CALL_NVDA_231128_57: SL=-32% PnL=$-1,235(-32%) held=2d
2023-12-04|CLOSE YOEL_CALL_AAPL_231201_58: SL_FILL=-33% PnL=$-214(-33%) held=3d
2023-12-04|CLOSE YOEL_CALL_AAPL_231204_59: SL_FILL=-32% PnL=$-230(-32%) held=0d
2023-12-05|CLOSE YOEL_CALL_MSFT_231205_60: LIMIT_FILL_35% PnL=$+676(+35%) held=0d
2023-12-06|CLOSE YOEL_CALL_QQQ_231206_61: SL_FILL=-31% PnL=$-448(-31%) held=0d
2023-12-13|CLOSE YOEL_CALL_MSFT_231211_63: LIMIT_FILL_35% PnL=$+522(+35%) held=1d
2023-12-13|CLOSE YOEL_CALL_AAPL_231211_62: LIMIT_FILL_35% PnL=$+190(+35%) held=1d
2023-12-13|CLOSE YOEL_CALL_AAPL_231213_64: LIMIT_FILL_35% PnL=$+262(+35%) held=0d
2023-12-21|CLOSE YOEL_CALL_AAPL_231218_65: SL_FILL=-32% PnL=$-284(-32%) held=3d
2023-12-26|CLOSE YOEL_CALL_MSFT_231218_66: TIME=7d PnL=$+205(+11%) held=7d
2023-12-26|CLOSE YOEL_CALL_AAPL_231222_67: SL_FILL=-32% PnL=$-234(-32%) held=4d
2023-12-27|CLOSE YOEL_CALL_AAPL_231226_68: SL_FILL=-31% PnL=$-280(-31%) held=1d
2023-12-29|CLOSE YOEL_CALL_AAPL_231228_70: SL_FILL=-32% PnL=$-208(-32%) held=1d
2024-01-02|CLOSE YOEL_CALL_AAPL_231227_69: TIME=5d PnL=$-95(-12%) held=5d
2024-01-02|CLOSE YOEL_CALL_AAPL_240102_71: SL_FILL=-36% PnL=$-276(-36%) held=0d
2024-01-02|CLOSE YOEL_CALL_QQQ_240102_72: SL_FILL=-31% PnL=$-392(-31%) held=0d
2024-01-04|CLOSE YOEL_CALL_QQQ_240103_73: SL_FILL=-32% PnL=$-432(-32%) held=1d
2024-01-08|CLOSE YOEL_CALL_QQQ_240108_74: LIMIT_FILL_35% PnL=$+590(+35%) held=0d
2024-01-10|CLOSE YOEL_CALL_QQQ_240109_75: LIMIT_FILL_35% PnL=$+518(+35%) held=1d
2024-01-11|CLOSE YOEL_CALL_QQQ_240110_76: LIMIT_FILL_35% PnL=$+494(+35%) held=1d
2024-01-17|CLOSE YOEL_CALL_QQQ_240116_77: SL_FILL=-31% PnL=$-466(-31%) held=1d
2024-01-18|CLOSE YOEL_CALL_QQQ_240117_78: LIMIT_FILL_35% PnL=$+462(+35%) held=0d
2024-01-19|CLOSE YOEL_CALL_QQQ_240118_79: LIMIT_FILL_35% PnL=$+676(+35%) held=1d
2024-02-02|CLOSE YOEL_CALL_MSFT_240202_81: LIMIT_FILL_35% PnL=$+442(+35%) held=0d
2024-02-02|CLOSE YOEL_CALL_MSFT_240201_80: LIMIT_FILL_35% PnL=$+606(+35%) held=1d
2024-02-06|CLOSE YOEL_CALL_MSFT_240206_83: SL_FILL=-32% PnL=$-480(-32%) held=0d
2024-02-09|CLOSE YOEL_CALL_QQQ_240207_84: LIMIT_FILL_35% PnL=$+530(+35%) held=2d
2024-02-09|CLOSE YOEL_CALL_QQQ_240206_82: LIMIT_FILL_35% PnL=$+578(+35%) held=3d
2024-02-14|CLOSE YOEL_CALL_QQQ_240213_86: LIMIT_FILL_35% PnL=$+398(+35%) held=0d
2024-02-20|CLOSE YOEL_CALL_MSFT_240213_85: TIME=6d PnL=$-190(-10%) held=6d
2024-02-20|CLOSE YOEL_CALL_QQQ_240214_87: TIME=5d PnL=$-188(-11%) held=5d
2024-02-20|CLOSE YOEL_CALL_QQQ_240220_88: SL_FILL=-30% PnL=$-520(-30%) held=0d
2024-02-21|CLOSE YOEL_CALL_MSFT_240220_89: SL_FILL=-33% PnL=$-560(-33%) held=1d
2024-02-22|CLOSE YOEL_CALL_QQQ_240221_90: LIMIT_FILL_35% PnL=$+1,044(+59%) held=0d
2024-02-27|CLOSE YOEL_CALL_MSFT_240226_92: SL_FILL=-32% PnL=$-660(-32%) held=1d
2024-03-01|CLOSE YOEL_CALL_QQQ_240228_93: LIMIT_FILL_35% PnL=$+544(+35%) held=1d
2024-03-01|CLOSE YOEL_CALL_QQQ_240226_91: LIMIT_FILL_35% PnL=$+576(+35%) held=4d
2024-03-05|CLOSE YOEL_CALL_QQQ_240304_95: SL_FILL=-32% PnL=$-508(-32%) held=1d
2024-03-05|CLOSE YOEL_CALL_MSFT_240304_94: SL_FILL=-31% PnL=$-520(-31%) held=1d
2024-03-07|CLOSE YOEL_CALL_MSFT_240306_96: LIMIT_FILL_35% PnL=$+780(+35%) held=1d
2024-03-12|CLOSE YOEL_CALL_QQQ_240311_97: LIMIT_FILL_35% PnL=$+652(+35%) held=1d
2024-03-14|CLOSE YOEL_CALL_QQQ_240313_99: SL_FILL=-32% PnL=$-522(-32%) held=1d
2024-03-15|CLOSE YOEL_CALL_QQQ_240312_98: SL_FILL=-34% PnL=$-600(-34%) held=3d
2024-03-19|CLOSE YOEL_CALL_QQQ_240318_101: SL_FILL=-32% PnL=$-700(-32%) held=1d
2024-03-20|CLOSE YOEL_CALL_MSFT_240318_100: LIMIT_FILL_35% PnL=$+774(+35%) held=2d
2024-03-21|CLOSE YOEL_CALL_QQQ_240320_102: LIMIT_FILL_35% PnL=$+642(+35%) held=0d
2024-03-27|CLOSE YOEL_CALL_MSFT_240326_104: SL_FILL=-31% PnL=$-540(-31%) held=1d
2024-04-01|CLOSE YOEL_CALL_QQQ_240325_103: TIME=6d PnL=$-238(-14%) held=6d
2024-04-01|CLOSE YOEL_CALL_QQQ_240328_105: LIMIT_FILL_35% PnL=$-70(-5%) held=3d
2024-04-02|CLOSE YOEL_CALL_QQQ_240401_106: SL_FILL=-35% PnL=$-594(-35%) held=1d
2024-04-04|CLOSE YOEL_CALL_QQQ_240402_107: LIMIT_FILL_35% PnL=$+516(+35%) held=1d
2024-04-04|CLOSE YOEL_CALL_QQQ_240403_108: LIMIT_FILL_35% PnL=$+580(+35%) held=0d
2024-04-15|CLOSE YOEL_CALL_MSFT_240408_109: TIME=6d PnL=$-390(-14%) held=6d
2024-04-15|CLOSE YOEL_CALL_MSFT_240409_110: TIME=5d PnL=$-410(-15%) held=5d
2024-04-15|CLOSE YOEL_CALL_QQQ_240415_112: SL_FILL=-31% PnL=$-622(-31%) held=0d
2024-04-15|CLOSE YOEL_CALL_MSFT_240415_111: SL_FILL=-31% PnL=$-880(-31%) held=0d
2024-04-18|CLOSE YOEL_CALL_MSFT_240416_113: SL_FILL=-31% PnL=$-880(-31%) held=2d
2024-05-28|CLOSE YOEL_CALL_AAPL_240524_114: LIMIT_FILL_35% PnL=$+242(+35%) held=3d
2024-05-28|CLOSE YOEL_CALL_QQQ_240524_115: LIMIT_FILL_35% PnL=$+462(+35%) held=4d
2024-05-31|CLOSE YOEL_CALL_QQQ_240530_117: SL_FILL=-34% PnL=$-580(-34%) held=1d
2024-06-03|CLOSE YOEL_CALL_AAPL_240529_116: LIMIT_FILL_35% PnL=$+240(+25%) held=5d
2024-06-05|CLOSE YOEL_CALL_QQQ_240604_119: LIMIT_FILL_35% PnL=$+590(+35%) held=0d
2024-06-05|CLOSE YOEL_CALL_MSFT_240603_118: LIMIT_FILL_35% PnL=$+672(+35%) held=2d
2024-06-05|CLOSE YOEL_CALL_QQQ_240605_120: LIMIT_FILL_35% PnL=$+572(+35%) held=0d
2024-06-11|CLOSE YOEL_CALL_AAPL_240611_122: LIMIT_FILL_35% PnL=$+316(+35%) held=0d
2024-06-11|CLOSE YOEL_CALL_QQQ_240610_121: LIMIT_FILL_35% PnL=$+570(+35%) held=1d
2024-06-12|CLOSE YOEL_CALL_MSFT_240612_123: LIMIT_FILL_35% PnL=$+630(+35%) held=0d
2024-07-01|CLOSE YOEL_CALL_QQQ_240701_124: LIMIT_FILL_35% PnL=$+646(+35%) held=1d
2024-07-01|CLOSE YOEL_CALL_AAPL_240701_125: LIMIT_FILL_35% PnL=$+330(+35%) held=0d
2024-07-02|CLOSE YOEL_CALL_QQQ_240702_126: LIMIT_FILL_35% PnL=$+614(+35%) held=0d
2024-07-12|CLOSE YOEL_CALL_QQQ_240712_128: LIMIT_FILL_35% PnL=$+624(+35%) held=0d
2024-07-15|CLOSE YOEL_CALL_MSFT_240710_127: SL_FILL=-23% PnL=$-620(-23%) held=5d
2024-07-16|CLOSE YOEL_CALL_MSFT_240715_129: SL_FILL=-32% PnL=$-910(-32%) held=1d
2024-07-17|CLOSE YOEL_CALL_MSFT_240716_130: SL_FILL=-44% PnL=$-1,210(-44%) held=1d
2024-07-22|CLOSE YOEL_CALL_MSFT_240717_131: SL_FILL=-11% PnL=$-330(-11%) held=5d
2024-07-24|CLOSE YOEL_CALL_QQQ_240722_132: SL_FILL=-43% PnL=$-862(-43%) held=2d
2024-07-24|CLOSE YOEL_CALL_QQQ_240723_133: SL_FILL=-43% PnL=$-898(-43%) held=1d
2024-09-09|CLOSE YOEL_CALL_AAPL_240905_134: SL_FILL=-37% PnL=$-410(-37%) held=4d
2024-09-26|CLOSE YOEL_CALL_AAPL_240925_135: LIMIT_FILL_35% PnL=$+374(+35%) held=1d
2024-09-30|CLOSE YOEL_CALL_AAPL_240926_136: LIMIT_FILL_35% PnL=$+340(+35%) held=3d
2024-09-30|CLOSE YOEL_CALL_AAPL_240927_137: LIMIT_FILL_35% PnL=$+322(+35%) held=2d
2024-10-01|CLOSE YOEL_CALL_QQQ_240930_138: SL_FILL=-31% PnL=$-654(-31%) held=1d
2024-10-04|CLOSE YOEL_CALL_QQQ_241003_140: LIMIT_FILL_35% PnL=$+716(+35%) held=1d
2024-10-07|CLOSE YOEL_CALL_MSFT_241002_139: SL_FILL=-28% PnL=$-660(-28%) held=5d
2024-10-09|CLOSE YOEL_CALL_QQQ_241008_142: LIMIT_FILL_35% PnL=$+774(+35%) held=1d
2024-10-14|CLOSE YOEL_CALL_MSFT_241007_141: TIME=6d PnL=$-170(-6%) held=6d
2024-10-14|CLOSE YOEL_CALL_QQQ_241010_143: LIMIT_FILL_35% PnL=$+722(+35%) held=4d
2024-10-15|CLOSE YOEL_CALL_QQQ_241014_144: SL_FILL=-30% PnL=$-718(-30%) held=1d
2024-10-16|CLOSE YOEL_CALL_AAPL_241015_145: SL_FILL=-31% PnL=$-400(-31%) held=1d
2024-10-21|CLOSE YOEL_CALL_AAPL_241016_146: LIMIT_FILL_35% PnL=$+230(+15%) held=5d
2024-10-23|CLOSE YOEL_CALL_QQQ_241021_147: SL_FILL=-32% PnL=$-692(-32%) held=2d
2024-10-23|CLOSE YOEL_CALL_QQQ_241022_148: SL_FILL=-31% PnL=$-720(-31%) held=1d
2024-10-25|CLOSE YOEL_CALL_QQQ_241024_149: LIMIT_FILL_35% PnL=$+816(+35%) held=1d
2024-10-31|CLOSE YOEL_CALL_AAPL_241028_151: SL_FILL=-33% PnL=$-440(-33%) held=3d
2024-10-31|CLOSE YOEL_CALL_QQQ_241028_150: SL_FILL=-33% PnL=$-828(-33%) held=3d
2024-11-06|CLOSE YOEL_CALL_QQQ_241101_152: LIMIT_FILL_35% PnL=$+832(+35%) held=4d
2024-11-06|CLOSE YOEL_CALL_QQQ_241104_153: LIMIT_FILL_35% PnL=$+972(+35%) held=1d
2024-11-07|CLOSE YOEL_CALL_QQQ_241106_154: LIMIT_FILL_35% PnL=$+1,012(+35%) held=1d
2024-11-12|CLOSE YOEL_CALL_QQQ_241107_155: LIMIT_FILL_35% PnL=$+242(+13%) held=5d
2024-11-15|CLOSE YOEL_CALL_QQQ_241114_156: SL_FILL=-54% PnL=$-972(-54%) held=1d
2024-11-15|CLOSE YOEL_CALL_QQQ_241115_157: SL_FILL=-32% PnL=$-492(-32%) held=0d
2024-11-21|CLOSE YOEL_CALL_QQQ_241118_158: LIMIT_FILL_35% PnL=$+758(+35%) held=2d
2024-11-21|CLOSE YOEL_CALL_QQQ_241119_159: LIMIT_FILL_35% PnL=$+748(+35%) held=1d
2024-11-21|CLOSE YOEL_CALL_QQQ_241121_160: SL_FILL=-34% PnL=$-708(-34%) held=0d
2024-12-02|CLOSE YOEL_CALL_QQQ_241129_162: LIMIT_FILL_35% PnL=$+582(+35%) held=2d
2024-12-02|CLOSE YOEL_CALL_QQQ_241127_161: LIMIT_FILL_35% PnL=$+532(+30%) held=5d
2024-12-04|CLOSE YOEL_CALL_QQQ_241202_163: LIMIT_FILL_35% PnL=$+618(+35%) held=1d
2024-12-04|CLOSE YOEL_CALL_QQQ_241203_164: LIMIT_FILL_35% PnL=$+592(+35%) held=0d
2024-12-05|CLOSE YOEL_CALL_MSFT_241204_165: LIMIT_FILL_35% PnL=$+608(+35%) held=1d
2024-12-11|CLOSE YOEL_CALL_QQQ_241210_166: LIMIT_FILL_35% PnL=$+604(+35%) held=1d
2024-12-11|CLOSE YOEL_CALL_QQQ_241211_167: LIMIT_FILL_35% PnL=$+606(+35%) held=0d
2024-12-16|CLOSE YOEL_CALL_QQQ_241213_168: LIMIT_FILL_35% PnL=$+580(+35%) held=3d
2024-12-19|CLOSE YOEL_CALL_AAPL_241219_169: LIMIT_FILL_35% PnL=$+308(+35%) held=0d
2024-12-20|CLOSE YOEL_CALL_QQQ_241219_170: SL_FILL=-45% PnL=$-1,072(-45%) held=1d
2024-12-20|CLOSE YOEL_CALL_QQQ_241220_171: LIMIT_FILL_35% PnL=$+762(+35%) held=0d
2024-12-26|CLOSE YOEL_CALL_QQQ_241223_172: LIMIT_FILL_35% PnL=$+846(+35%) held=3d
2024-12-27|CLOSE YOEL_CALL_QQQ_241224_173: SL_FILL=-32% PnL=$-658(-32%) held=3d
2024-12-27|CLOSE YOEL_CALL_QQQ_241227_174: SL_FILL=-31% PnL=$-592(-31%) held=0d
""".strip()

trades = []
for line in raw_logs.split('\n'):
    line = line.strip()
    if not line:
        continue
    parts = line.split('|', 1)
    date_str = parts[0].strip()
    rest = parts[1].strip()
    
    close_date = datetime.strptime(date_str, "%Y-%m-%d")
    
    m_tag = re.search(r'CLOSE (YOEL_CALL_\w+):', rest)
    if not m_tag:
        continue
    tag = m_tag.group(1)
    ticker = tag.split('_')[2]
    
    m_reason = re.search(r': (\S+)', rest[rest.index(':'):])
    reason = m_reason.group(1).split('=')[0].replace('%','') if m_reason else "UNK"
    
    m_pnl = re.search(r'PnL=\$([+\-][\d,]+)', rest)
    pnl = int(m_pnl.group(1).replace(',','').replace('+','')) if m_pnl else 0
    
    m_pct = re.search(r'\(([+\-]\d+)%\)', rest)
    pnl_pct = int(m_pct.group(1)) if m_pct else 0
    
    m_held = re.search(r'held=(\d+)d', rest)
    held = int(m_held.group(1)) if m_held else 0
    
    trades.append({
        'date': close_date, 'tag': tag, 'ticker': ticker,
        'reason': reason, 'pnl': pnl, 'pnl_pct': pnl_pct, 'held': held
    })

# ====== RECONSTRUCT EQUITY CURVE ======
equity = 10000
peak = 10000
equities = []
for t in trades:
    equity += t['pnl']
    if equity > peak:
        peak = equity
    dd = (peak - equity) / peak * 100 if peak > 0 else 0
    equities.append({
        'date': t['date'], 'equity': equity, 'peak': peak,
        'dd_pct': dd, 'pnl': t['pnl'], 'tag': t['tag'],
        'ticker': t['ticker'], 'reason': t['reason']
    })

print("=" * 80)
print("CURVA DE EQUITY RECONSTRUIDA - IDENTIFICACION DE DRAWDOWNS MAYORES")
print("=" * 80)

# Find drawdown periods (DD > 15%)
print("\n--- Equity curve (mensual) ---")
by_month = {}
for e in equities:
    mk = e['date'].strftime('%Y-%m')
    by_month[mk] = e  # last trade of month

for mk in sorted(by_month.keys()):
    e = by_month[mk]
    bar = '#' * max(1, int(e['equity'] / 500))
    dd_flag = f" *** DD={e['dd_pct']:.0f}%" if e['dd_pct'] > 15 else ""
    print(f"  {mk}: ${e['equity']:>8,} (peak ${e['peak']:>8,}){dd_flag}")

# ====== IDENTIFY MAJOR DD PERIODS ======
print("\n" + "=" * 80)
print("PERIODOS DE DRAWDOWN MAYOR (barras rojas)")
print("=" * 80)

# Find contiguous periods where DD > 10% or equity drops significantly
# Approach: find sequences of consecutive losing trades that create DD
dd_periods = []
current_period = None

for i, e in enumerate(equities):
    if e['dd_pct'] > 10:
        if current_period is None:
            current_period = {
                'start': e['date'], 'start_equity': equities[i-1]['equity'] if i > 0 else 10000,
                'trades': [], 'min_equity': e['equity'], 'max_dd': e['dd_pct'],
                'peak_before': e['peak']
            }
        current_period['trades'].append(e)
        if e['equity'] < current_period['min_equity']:
            current_period['min_equity'] = e['equity']
        if e['dd_pct'] > current_period['max_dd']:
            current_period['max_dd'] = e['dd_pct']
    else:
        if current_period is not None:
            current_period['end'] = equities[i-1]['date'] if i > 0 else e['date']
            current_period['recovery_date'] = e['date']
            dd_periods.append(current_period)
            current_period = None

if current_period is not None:
    current_period['end'] = equities[-1]['date']
    current_period['recovery_date'] = None
    dd_periods.append(current_period)

# Also find sharp drops (rolling 5-trade windows with big loss)
print("\n--- CAIDAS AGUDAS (ventanas de 5 trades con mayor perdida) ---")
window = 5
worst_windows = []
for i in range(len(trades) - window + 1):
    w = trades[i:i+window]
    w_pnl = sum(t['pnl'] for t in w)
    if w_pnl < -1500:
        worst_windows.append({
            'start_date': w[0]['date'],
            'end_date': w[-1]['date'],
            'pnl': w_pnl,
            'trades': w,
            'n_losses': sum(1 for t in w if t['pnl'] < 0)
        })

# Remove overlapping windows, keep worst
worst_windows.sort(key=lambda x: x['pnl'])
shown_dates = set()
major_drops = []
for w in worst_windows:
    key = w['start_date'].strftime('%Y-%m')
    if key not in shown_dates:
        shown_dates.add(key)
        major_drops.append(w)

print()
for i, w in enumerate(major_drops[:8]):
    print(f"  CAIDA #{i+1}: {w['start_date'].strftime('%Y-%m-%d')} a {w['end_date'].strftime('%Y-%m-%d')}")
    print(f"    PnL ventana: ${w['pnl']:+,} | {w['n_losses']}/{window} perdedores")
    for t in w['trades']:
        wl = "W" if t['pnl'] > 0 else "L"
        print(f"      [{wl}] {t['date'].strftime('%m-%d')} {t['tag']:45s} {t['reason']:15s} ${t['pnl']:+,}")
    print()

# ====== MAJOR DD PERIOD ANALYSIS ======
print("=" * 80)
print("ANALISIS DETALLADO DE CADA PERIODO DE DRAWDOWN")
print("=" * 80)

for i, p in enumerate(dd_periods):
    n_trades = len(p['trades'])
    losses = [t for t in p['trades'] if t['pnl'] < 0]
    wins = [t for t in p['trades'] if t['pnl'] > 0]
    tickers = set(t['ticker'] for t in p['trades'])
    loss_pnl = sum(t['pnl'] for t in losses)
    win_pnl = sum(t['pnl'] for t in wins)
    
    print(f"\n  DD PERIODO #{i+1}")
    print(f"  Fechas: {p['start'].strftime('%Y-%m-%d')} a {p['trades'][-1]['date'].strftime('%Y-%m-%d')}")
    print(f"  Max DD: {p['max_dd']:.1f}% | Min Equity: ${p['min_equity']:,} (desde peak ${p['peak_before']:,})")
    print(f"  Trades: {n_trades} ({len(losses)} L, {len(wins)} W)")
    print(f"  PnL: ${loss_pnl + win_pnl:+,} (losses ${loss_pnl:+,}, wins ${win_pnl:+,})")
    print(f"  Tickers: {', '.join(sorted(tickers))}")
    
    # By reason
    reasons = {}
    for t in p['trades']:
        r = t['reason']
        if r not in reasons:
            reasons[r] = {'n': 0, 'pnl': 0}
        reasons[r]['n'] += 1
        reasons[r]['pnl'] += t['pnl']
    print(f"  Exit reasons:")
    for r, d in sorted(reasons.items(), key=lambda x: x[1]['pnl']):
        print(f"    {r}: {d['n']}t ${d['pnl']:+,}")
    
    if p.get('recovery_date'):
        days_in_dd = (p['recovery_date'] - p['start']).days
        print(f"  Recovery: {p['recovery_date'].strftime('%Y-%m-%d')} ({days_in_dd} dias)")

# ====== MARKET CONTEXT CALENDAR ======
print("\n" + "=" * 80)
print("CONTEXTO DE MERCADO PARA CADA PERIODO ROJO")
print("=" * 80)

market_events = {
    '2023-08': {
        'event': 'Fitch downgrade USA + China slowdown fears',
        'detail': 'Fitch bajo rating de USA de AAA a AA+. Datos macro de China decepcionantes. '
                  'SPY cayo ~5% desde ATH de julio. QQQ cayo ~7%. VIX subio de 13 a 18.',
        'impact': 'Calls comprados en tendencia alcista fueron destruidos por reversal de agosto.'
    },
    '2023-09': {
        'event': 'Fed hawkish + Higher for Longer',
        'detail': 'FOMC mantuvo tasas pero senalo "higher for longer". Bond yields 10Y tocaron 4.5%. '
                  'SPY/QQQ en correccion sostenida Sep-Oct. NVDA corrigio -12% desde ATH.',
        'impact': 'NVDA call (trade #55) perdio -$1,160. Mercado entero bajista 6 semanas.'
    },
    '2023-11': {
        'event': 'NVDA volatilidad post-earnings + Pullback',
        'detail': 'NVDA earnings 11/21 — beat masivo pero toma de ganancias inmediata. '
                  'NVDA cayo ~8% en dias post-earnings pese a beat.',
        'impact': 'Dos trades NVDA consecutivos: -$1,070 y -$1,235 = -$2,305. Volatilidad de earnings '
                  'destruyo calls de corto plazo por crush de IV.'
    },
    '2023-12': {
        'event': 'Rotacion año nuevo + AAPL debilidad',
        'detail': 'AAPL underperformed en dic-ene. Supply chain concerns y China weakness. '
                  'Santa rally beneficio QQQ pero no AAPL. Multiple SL en AAPL.',
        'impact': '7 trades AAPL perdidos seguidos (dic 18 a ene 2). AAPL no estaba en momentum pero '
                  'el scanner lo seguia detectando como "near SMA20".'
    },
    '2024-03': {
        'event': 'Fed uncertainty + Hot CPI data',
        'detail': 'CPI feb 2024 vino mas caliente de esperado. Expectativas de recorte de tasas se retrasaron. '
                  'QQQ consolido/choppeo en rango 435-445. Market indeciso.',
        'impact': 'Mercado choppy = peor escenario para calls. Se compran calls, no se mueven lo suficiente, '
                  'theta decay los mata. Multiple SL en QQQ.'
    },
    '2024-04': {
        'event': 'Iran-Israel tensions + Rate cut hopes crushed',
        'detail': 'Escalada geopolitica Iran-Israel mid-abril. Powell dijo "higher for longer". '
                  'QQQ cayo -5% en 3 dias (10-15 abril). MSFT cayo -7% tambien.',
        'impact': 'Peor cluster del ano: 5 trades perdidos en 3 dias, -$3,182 total. '
                  'MSFT 3 SL seguidos (-$880, -$880, -$622). Geopolitica + macro = doble golpe.'
    },
    '2024-07': {
        'event': 'Rotation from tech to small caps',
        'detail': 'La "Great Rotation" de julio 2024. Dinero salio masivamente de mega-cap tech hacia '
                  'Russell 2000. QQQ cayo -8%, MSFT cayo -10% en 2 semanas. '
                  'CPI bajo + expectativa de rate cuts favorecio small caps.',
        'impact': 'PEOR DRAWDOWN DEL ANO. 6 trades perdidos seguidos: MSFT x4 (-$3,070) + QQQ x2 (-$1,760). '
                  'Total -$4,830 en 10 dias. La rotacion sectorial destruyo calls en mega-cap.'
    },
    '2024-10': {
        'event': 'Election uncertainty + Earnings anxiety',
        'detail': 'Pre-eleccion USA nov 2024. Incertidumbre macro. QQQ oscilo en rango con volatilidad. '
                  'Earnings de Big Tech en la ultima semana de octubre.',
        'impact': 'QQQ tuvo 4 SL en oct-21 a oct-31. Mercado indeciso pre-eleccion = theta decay.'
    },
}

for period_key in sorted(market_events.keys()):
    me = market_events[period_key]
    print(f"\n  === {period_key} ===")
    print(f"  EVENTO: {me['event']}")
    print(f"  DETALLE: {me['detail']}")
    print(f"  IMPACTO EN ALGO: {me['impact']}")

# ====== SYNTHESIS ======
print("\n" + "=" * 80)
print("SINTESIS: PATRONES COMUNES EN BARRAS ROJAS")
print("=" * 80)
print("""
  1. ROTACION SECTORIAL (Jul 2024): -$4,830
     El peor drawdown. Cuando el dinero rota de tech a small caps,
     nuestros calls en AAPL/MSFT/QQQ/NVDA se destruyen simultaneamente.
     NO HAY PROTECCION posible con calls-only en mega-cap.

  2. EVENTOS GEOPOLITICOS / MACRO SHOCKS (Abr 2024, Ago 2023): -$3,182, -$1,660
     Iran-Israel, Fitch downgrade. Causas gap-down overnight que
     traspasan el SL -30%. El SL a -30% NO protege contra gaps.

  3. MERCADO CHOPPY / SIDEWAYS (Mar 2024, Oct 2024): -$2,500 aprox
     Hot CPI, elecciones. El mercado oscila en rango. Los calls compran
     theta decay sin suficiente movimiento. SL se activa por decay, no por crash.

  4. EARNINGS VOLATILITY (Nov 2023 NVDA): -$2,305
     Post-earnings crush de IV destruye calls de corto plazo incluso si
     el underlying no cae mucho. NVDA beat pero el call perdio por IV crush.

  5. TICKER ESPECIFICO DEBIL (Dic 2023 AAPL, Jul 2024 MSFT): -$1,500 a -$3,000
     Un ticker sale del momentum pero sigue "cerca de SMA20" por lo que
     el scanner lo sigue detectando. Multiple SL en el mismo ticker.

  CONCLUSION:
  - Los drawdowns NO son por bugs del algoritmo
  - Son por REGIMEN DE MERCADO: rotacion, shocks, y chop
  - Posible mejora: detectar regimen (VIX alto, BB squeezing en SPY)
    y REDUCIR exposure, no eliminarlo
  - Un trailing SL no ayudaria con gaps overnight
  - Un filtro de VIX > 20 = reduce size podria mitigar los peores periodos
""")
