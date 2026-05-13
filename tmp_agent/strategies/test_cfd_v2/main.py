# region imports
from AlgorithmImports import *
# endregion

class TestOandaCFDv2(QCAlgorithm):
    """Test which Oanda CFD tickers actually have data.
    Strategy: Add all tickers, track which ones receive data in OnData,
    report results via RuntimeStatistics (which persist in backtest JSON).
    Also attempt a tiny trade on each to confirm they're tradeable.
    """
    def Initialize(self):
        self.SetStartDate(2020, 1, 2)
        self.SetEndDate(2020, 1, 31)
        self.SetCash(100000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # Indices
        self.indices = ['SPX500USD', 'US30USD', 'NAS100USD', 'DE30EUR', 'JP225USD', 'UK100GBP',
                        'AU200AUD', 'EU50EUR', 'FR40EUR', 'HK33HKD', 'SG30SGD', 'TWIXUSD',
                        'IN50USD', 'CN50USD']
        # Commodities
        self.commodities = ['XAUUSD', 'XAGUSD', 'WTICOUSD', 'BCOUSD', 'NATGASUSD', 'XCUUSD',
                            'CORNUSD', 'SOYBNUSD', 'WHEATUSD', 'SUGARUSD', 'XPTUSD', 'XPDUSD']
        # Bonds
        self.bonds = ['USB02YUSD', 'USB05YUSD', 'USB10YUSD', 'USB30YUSD',
                      'UK10YBGBP', 'DE10YBEUR']

        all_tickers = self.indices + self.commodities + self.bonds
        self.assets = {}
        self.add_failed = []

        for ticker in all_tickers:
            try:
                cfd = self.AddCfd(ticker, Resolution.Daily, Market.Oanda)
                cfd.SetLeverage(10)
                self.assets[ticker] = cfd.Symbol
            except Exception as e:
                self.add_failed.append(ticker)

        self.data_received = {}   # ticker -> first date we got data
        self.traded = {}          # ticker -> True if order filled
        self.checked = set()
        self.day_count = 0

        self.SetRuntimeStatistic("AddOK", str(len(self.assets)))
        self.SetRuntimeStatistic("AddFail", ",".join(self.add_failed) if self.add_failed else "NONE")

    def OnData(self, data):
        self.day_count += 1

        for ticker, sym in self.assets.items():
            if ticker not in self.data_received and data.ContainsKey(sym) and data[sym] is not None:
                try:
                    price = float(data[sym].Close)
                    if price > 0:
                        self.data_received[ticker] = str(self.Time.date())
                except:
                    pass

            # Try to trade each one once (first 10 days)
            if self.day_count <= 10 and ticker not in self.checked and data.ContainsKey(sym):
                self.checked.add(ticker)
                try:
                    price = float(data[sym].Close)
                    if price > 0:
                        # Buy minimal quantity
                        qty = 1
                        self.MarketOrder(sym, qty)
                except:
                    pass

        # Update runtime stats every data event
        has_data = sorted(self.data_received.keys())
        no_data = sorted([t for t in self.assets if t not in self.data_received])

        # Split into categories for readability
        idx_ok = [t for t in has_data if t in self.indices]
        com_ok = [t for t in has_data if t in self.commodities]
        bnd_ok = [t for t in has_data if t in self.bonds]

        self.SetRuntimeStatistic("IDX_OK", ",".join(idx_ok) if idx_ok else "NONE")
        self.SetRuntimeStatistic("COM_OK", ",".join(com_ok) if com_ok else "NONE")
        self.SetRuntimeStatistic("BND_OK", ",".join(bnd_ok) if bnd_ok else "NONE")
        self.SetRuntimeStatistic("NO_DATA", ",".join(no_data) if no_data else "ALL_HAVE_DATA")
        self.SetRuntimeStatistic("DataCount", str(len(has_data)))
        self.SetRuntimeStatistic("TradeCount", str(len(self.traded)))
        self.SetRuntimeStatistic("DaysSeen", str(self.day_count))

    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status == OrderStatus.Filled:
            ticker = None
            for t, s in self.assets.items():
                if s == orderEvent.Symbol:
                    ticker = t
                    break
            if ticker:
                self.traded[ticker] = True
                self.SetRuntimeStatistic("TradeCount", str(len(self.traded)))
