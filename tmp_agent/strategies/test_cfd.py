# region imports
from AlgorithmImports import *
# endregion

class TestOandaCFD(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2024, 1, 1)
        self.SetEndDate(2024, 1, 10)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # Test indices CFDs
        indices = ['SPX500USD', 'US30USD', 'NAS100USD', 'DE30EUR', 'JP225USD', 'UK100GBP']
        # Test commodity CFDs
        commodities = ['XAUUSD', 'XAGUSD', 'WTICOUSD', 'BCOUSD', 'NATGASUSD', 'XCUUSD']
        # Test bond CFDs
        bonds = ['USB02YUSD', 'USB05YUSD', 'USB10YUSD', 'USB30YUSD']

        self.assets = {}
        for ticker in indices + commodities + bonds:
            try:
                cfd = self.AddCfd(ticker, Resolution.Daily, Market.Oanda)
                cfd.SetLeverage(10)
                self.assets[ticker] = cfd.Symbol
                self.Log(f"[OK] {ticker}")
            except Exception as e:
                self.Log(f"[FAIL] {ticker}: {str(e)[:100]}")

        self.Log(f"[TOTAL] {len(self.assets)} assets added successfully")

    def OnData(self, data):
        for ticker, sym in self.assets.items():
            if data.ContainsKey(sym):
                price = float(data[sym].Close)
                if not self.Portfolio[sym].Invested:
                    self.Log(f"[PRICE] {ticker} = {price}")
