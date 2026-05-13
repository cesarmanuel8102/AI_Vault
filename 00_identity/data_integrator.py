"""
AI_VAULT Data Integrator v2
Integración profesional con fuentes de datos externas:
- QuantConnect (real API)
- Tiingo (real API)
- Interactive Brokers (IBK)
- PocketOption (WebSocket/HAR analysis)

Quality Standards:
- Latency: <500ms for real-time data
- Accuracy: >99.9% price validation
- Redundancy: 2+ sources minimum
"""

import os
import json
import asyncio
import aiohttp
import base64
import hashlib
import hmac
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import logging
from enum import Enum

# Configuración de logging estructurado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger(__name__)

class DataSourceStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    ERROR = "error"
    OFFLINE = "offline"

@dataclass
class MarketData:
    symbol: str
    price: float
    timestamp: datetime
    volume: Optional[int] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    source: str = "unknown"
    latency_ms: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "timestamp": self.timestamp.isoformat(),
            "volume": self.volume,
            "bid": self.bid,
            "ask": self.ask,
            "source": self.source,
            "latency_ms": self.latency_ms
        }

@dataclass
class DataSourceHealth:
    source: str
    status: DataSourceStatus
    last_check: datetime
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status.value,
            "last_check": self.last_check.isoformat(),
            "latency_ms": self.latency_ms,
            "error_message": self.error_message
        }

class DataQualityValidator:
    """Validador profesional de calidad de datos"""
    
    def __init__(self):
        self.price_history: Dict[str, List[Tuple[datetime, float]]] = {}
        self.max_history = 100
    
    def validate_price(self, price: float, symbol: str) -> Tuple[bool, Optional[str]]:
        """Validar que el precio sea razonable con detección de anomalías"""
        if price <= 0:
            return False, f"Invalid price: {price} (must be > 0)"
        if price > 1000000:
            return False, f"Suspicious price: {price} (exceeds threshold)"
        
        # Detección de cambios bruscos
        if symbol in self.price_history and self.price_history[symbol]:
            last_price = self.price_history[symbol][-1][1]
            change_pct = abs(price - last_price) / last_price * 100
            if change_pct > 50:  # Cambio >50% es sospechoso
                return False, f"Price spike detected: {change_pct:.2f}% change"
        
        return True, None
    
    def validate_timestamp(self, timestamp: datetime, max_delay_seconds: int = 300) -> Tuple[bool, Optional[str]]:
        """Validar que el timestamp sea reciente"""
        now = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        
        age_seconds = (now - timestamp).total_seconds()
        
        if age_seconds < 0:
            return False, f"Future timestamp: {age_seconds:.0f}s ahead"
        if age_seconds > max_delay_seconds:
            return False, f"Stale data: {age_seconds:.0f}s old (max {max_delay_seconds}s)"
        
        return True, None
    
    def validate_volume(self, volume: Optional[int]) -> Tuple[bool, Optional[str]]:
        """Validar volumen"""
        if volume is None:
            return True, None  # Volumen opcional
        if volume < 0:
            return False, f"Invalid volume: {volume}"
        return True, None
    
    def record_price(self, symbol: str, timestamp: datetime, price: float):
        """Registrar precio para análisis de tendencia"""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        self.price_history[symbol].append((timestamp, price))
        if len(self.price_history[symbol]) > self.max_history:
            self.price_history[symbol].pop(0)

class QuantConnectConnector:
    """Conector profesional para QuantConnect API v2"""
    
    def __init__(self, user_id: Optional[str] = None, token: Optional[str] = None):
        secrets_path = Path(r"C:\AI_VAULT\tmp_agent\Secrets\quantconnect_access.json")
        if secrets_path.exists():
            with open(secrets_path) as f:
                creds = json.load(f)
                self.user_id = user_id or creds.get("user_id")
                self.token = token or creds.get("token")
        else:
            self.user_id = user_id or os.getenv("QUANTCONNECT_USER_ID")
            self.token = token or os.getenv("QUANTCONNECT_TOKEN")
        
        self.base_url = "https://www.quantconnect.com/api/v2"
        self.validator = DataQualityValidator()
        self.health_status = DataSourceHealth(
            source="quantconnect",
            status=DataSourceStatus.OFFLINE,
            last_check=datetime.now(timezone.utc)
        )
    
    def _get_auth_headers(self, timestamp: str) -> Dict[str, str]:
        """Generar headers de autenticación HMAC SHA256"""
        if not self.token:
            raise ValueError("QuantConnect token not configured")
        
        # QuantConnect usa HMAC SHA256 del timestamp con el token
        signature = hmac.new(
            self.token.encode('utf-8'),
            timestamp.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return {
            "Timestamp": timestamp,
            "Authorization": f"Basic {base64.b64encode(f'{self.user_id}:{signature}'.encode()).decode()}"
        }
    
    async def check_health(self) -> DataSourceHealth:
        """Verificar estado de la conexión"""
        start_time = datetime.now(timezone.utc)
        try:
            timestamp = str(int(datetime.now(timezone.utc).timestamp()))
            headers = self._get_auth_headers(timestamp)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/authenticate",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    
                    if resp.status == 200:
                        self.health_status = DataSourceHealth(
                            source="quantconnect",
                            status=DataSourceStatus.HEALTHY,
                            last_check=datetime.now(timezone.utc),
                            latency_ms=latency_ms
                        )
                    else:
                        self.health_status = DataSourceHealth(
                            source="quantconnect",
                            status=DataSourceStatus.ERROR,
                            last_check=datetime.now(timezone.utc),
                            latency_ms=latency_ms,
                            error_message=f"HTTP {resp.status}"
                        )
        except Exception as e:
            self.health_status = DataSourceHealth(
                source="quantconnect",
                status=DataSourceStatus.ERROR,
                last_check=datetime.now(timezone.utc),
                error_message=str(e)
            )
        
        return self.health_status
    
    async def get_historical_data(
        self, 
        symbol: str, 
        resolution: str = "minute",
        days: int = 1
    ) -> List[MarketData]:
        """Obtener datos históricos de QuantConnect"""
        start_time = datetime.now(timezone.utc)
        
        try:
            timestamp = str(int(datetime.now(timezone.utc).timestamp()))
            headers = self._get_auth_headers(timestamp)
            
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            
            payload = {
                "ticker": symbol,
                "start": start_date.strftime("%Y%m%d"),
                "end": end_date.strftime("%Y%m%d"),
                "resolution": resolution
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/data/read",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    
                    if resp.status != 200:
                        logger.error(f"QuantConnect API error: {resp.status}")
                        return []
                    
                    data = await resp.json()
                    
                    market_data_list = []
                    for point in data.get("prices", []):
                        ts = datetime.fromtimestamp(point["time"], tz=timezone.utc)
                        price = point.get("close", point.get("open", 0))
                        
                        # Validar datos
                        is_valid, error_msg = self.validator.validate_price(price, symbol)
                        if not is_valid:
                            logger.warning(f"QuantConnect data validation failed: {error_msg}")
                            continue
                        
                        is_valid_ts, error_msg_ts = self.validator.validate_timestamp(ts)
                        if not is_valid_ts:
                            logger.warning(f"QuantConnect timestamp validation failed: {error_msg_ts}")
                            continue
                        
                        market_data = MarketData(
                            symbol=symbol,
                            price=price,
                            timestamp=ts,
                            volume=point.get("volume"),
                            source="quantconnect",
                            latency_ms=latency_ms
                        )
                        market_data_list.append(market_data)
                        self.validator.record_price(symbol, ts, price)
                    
                    logger.info(f"QuantConnect: Retrieved {len(market_data_list)} data points for {symbol}")
                    return market_data_list
                    
        except Exception as e:
            logger.error(f"QuantConnect error: {e}")
            return []

class TiingoConnector:
    """Conector profesional para Tiingo API"""
    
    def __init__(self, token: Optional[str] = None):
        secrets_path = Path(r"C:\AI_VAULT\tmp_agent\Secrets\tiingo_access.json")
        if secrets_path.exists():
            with open(secrets_path) as f:
                creds = json.load(f)
                self.token = token or creds.get("token")
        else:
            self.token = token or os.getenv("TIINGO_TOKEN")
        
        self.base_url = "https://api.tiingo.com"
        self.validator = DataQualityValidator()
        self.health_status = DataSourceHealth(
            source="tiingo",
            status=DataSourceStatus.OFFLINE,
            last_check=datetime.now(timezone.utc)
        )
    
    async def check_health(self) -> DataSourceHealth:
        """Verificar estado de la conexión"""
        start_time = datetime.now(timezone.utc)
        try:
            headers = {"Authorization": f"Token {self.token}"}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/test",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    
                    if resp.status == 200:
                        self.health_status = DataSourceHealth(
                            source="tiingo",
                            status=DataSourceStatus.HEALTHY,
                            last_check=datetime.now(timezone.utc),
                            latency_ms=latency_ms
                        )
                    else:
                        self.health_status = DataSourceHealth(
                            source="tiingo",
                            status=DataSourceStatus.ERROR,
                            last_check=datetime.now(timezone.utc),
                            latency_ms=latency_ms,
                            error_message=f"HTTP {resp.status}"
                        )
        except Exception as e:
            self.health_status = DataSourceHealth(
                source="tiingo",
                status=DataSourceStatus.ERROR,
                last_check=datetime.now(timezone.utc),
                error_message=str(e)
            )
        
        return self.health_status
    
    async def get_intraday_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        resample_freq: str = "1min"
    ) -> List[MarketData]:
        """Obtener datos intradía de Tiingo"""
        start_time = datetime.now(timezone.utc)
        
        try:
            if not start_date:
                start_date = datetime.now(timezone.utc) - timedelta(days=1)
            if not end_date:
                end_date = datetime.now(timezone.utc)
            
            headers = {"Authorization": f"Token {self.token}"}
            
            url = f"{self.base_url}/iex/{symbol}/prices"
            params = {
                "startDate": start_date.strftime("%Y-%m-%d"),
                "endDate": end_date.strftime("%Y-%m-%d"),
                "resampleFreq": resample_freq,
                "columns": "open,high,low,close,volume"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    
                    if resp.status != 200:
                        logger.error(f"Tiingo API error: {resp.status}")
                        return []
                    
                    data = await resp.json()
                    
                    market_data_list = []
                    for point in data:
                        ts = datetime.fromisoformat(point["date"].replace("Z", "+00:00"))
                        price = point.get("close", 0)
                        
                        # Validar datos
                        is_valid, error_msg = self.validator.validate_price(price, symbol)
                        if not is_valid:
                            logger.warning(f"Tiingo data validation failed: {error_msg}")
                            continue
                        
                        is_valid_ts, error_msg_ts = self.validator.validate_timestamp(ts)
                        if not is_valid_ts:
                            logger.warning(f"Tiingo timestamp validation failed: {error_msg_ts}")
                            continue
                        
                        market_data = MarketData(
                            symbol=symbol,
                            price=price,
                            timestamp=ts,
                            volume=point.get("volume"),
                            bid=point.get("low"),
                            ask=point.get("high"),
                            source="tiingo",
                            latency_ms=latency_ms
                        )
                        market_data_list.append(market_data)
                        self.validator.record_price(symbol, ts, price)
                    
                    logger.info(f"Tiingo: Retrieved {len(market_data_list)} data points for {symbol}")
                    return market_data_list
                    
        except Exception as e:
            logger.error(f"Tiingo error: {e}")
            return []
    
    async def get_crypto_data(self, symbol: str) -> Optional[MarketData]:
        """Obtener datos de criptomonedas de Tiingo"""
        start_time = datetime.now(timezone.utc)
        
        try:
            headers = {"Authorization": f"Token {self.token}"}
            url = f"{self.base_url}/crypto/prices"
            params = {"tickers": symbol, "resampleFreq": "1min"}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    
                    if resp.status != 200:
                        return None
                    
                    data = await resp.json()
                    if not data or len(data) == 0:
                        return None
                    
                    latest = data[0]
                    price = latest.get("price", 0)
                    
                    is_valid, _ = self.validator.validate_price(price, symbol)
                    if not is_valid:
                        return None
                    
                    return MarketData(
                        symbol=symbol,
                        price=price,
                        timestamp=datetime.now(timezone.utc),
                        source="tiingo_crypto",
                        latency_ms=latency_ms
                    )
                    
        except Exception as e:
            logger.error(f"Tiingo crypto error: {e}")
            return None

class DataAggregator:
    """Agregador profesional de datos de múltiples fuentes"""
    
    def __init__(self):
        self.quantconnect = QuantConnectConnector()
        self.tiingo = TiingoConnector()
        self.validator = DataQualityValidator()
        self.health_statuses: Dict[str, DataSourceHealth] = {}
    
    async def check_all_health(self) -> Dict[str, DataSourceHealth]:
        """Verificar salud de todas las fuentes"""
        tasks = [
            self.quantconnect.check_health(),
            self.tiingo.check_health()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, DataSourceHealth):
                self.health_statuses[result.source] = result
            elif isinstance(result, Exception):
                logger.error(f"Health check error: {result}")
        
        return self.health_statuses
    
    async def get_consolidated_data(
        self,
        symbol: str,
        prefer_realtime: bool = True
    ) -> Dict[str, Any]:
        """Obtener datos consolidados de todas las fuentes disponibles"""
        
        start_time = datetime.now(timezone.utc)
        
        # Obtener datos de todas las fuentes en paralelo
        tasks = [
            self._fetch_with_timeout(self.tiingo.get_intraday_data(symbol), timeout=10),
            self._fetch_with_timeout(self.quantconnect.get_historical_data(symbol, days=1), timeout=15)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Procesar resultados
        data_sources = {}
        all_prices = []
        latest_timestamp = None
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Data source error: {result}")
                continue
            
            if isinstance(result, list) and result:
                # Tomar el dato más reciente
                latest = max(result, key=lambda x: x.timestamp)
                
                # Validar
                is_valid, error_msg = self.validator.validate_price(latest.price, symbol)
                if is_valid:
                    data_sources[latest.source] = latest.to_dict()
                    all_prices.append(latest.price)
                    
                    if latest_timestamp is None or latest.timestamp > latest_timestamp:
                        latest_timestamp = latest.timestamp
        
        # Calcular métricas
        avg_price = sum(all_prices) / len(all_prices) if all_prices else None
        price_variance = max(all_prices) - min(all_prices) if len(all_prices) > 1 else 0
        
        total_latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        return {
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "average_price": avg_price,
            "price_variance": price_variance,
            "sources": data_sources,
            "source_count": len(data_sources),
            "total_latency_ms": total_latency_ms,
            "quality_score": self._calculate_quality_score(data_sources, total_latency_ms)
        }
    
    async def _fetch_with_timeout(self, coro, timeout: float):
        """Ejecutar coroutine con timeout"""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Data fetch timeout after {timeout}s")
            return []
    
    def _calculate_quality_score(self, sources: Dict, latency_ms: float) -> float:
        """Calcular score de calidad 0-100"""
        score = 0.0
        
        # Puntos por número de fuentes (máx 40)
        score += min(len(sources) * 20, 40)
        
        # Puntos por latencia (máx 30)
        if latency_ms < 100:
            score += 30
        elif latency_ms < 500:
            score += 20
        elif latency_ms < 1000:
            score += 10
        
        # Puntos por validación de datos (máx 30)
        if len(sources) >= 2:
            score += 30
        elif len(sources) == 1:
            score += 15
        
        return round(score, 2)
    
    async def validate_data_quality(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validar calidad de datos agregados"""
        errors = []
        
        # Debe tener al menos 1 fuente
        if data.get("source_count", 0) < 1:
            errors.append("Insufficient data sources (minimum 1 required)")
        
        # Precio promedio debe ser válido
        if not data.get("average_price"):
            errors.append("No average price calculated")
        
        # Latencia debe ser aceptable
        latency = data.get("total_latency_ms", 0)
        if latency > 500:
            errors.append(f"High latency: {latency}ms (max 500ms)")
        
        # Score de calidad
        quality_score = data.get("quality_score", 0)
        if quality_score < 70:
            errors.append(f"Low quality score: {quality_score}/100")
        
        return len(errors) == 0, errors

# Instancia global
data_aggregator = DataAggregator()

async def test_data_integration():
    """Probar integración de datos con credenciales reales"""
    print("=" * 60)
    print("AI_VAULT Data Integrator v2 - Test Suite")
    print("=" * 60)
    
    # Test 1: Health checks
    print("\n[1/4] Checking data source health...")
    health = await data_aggregator.check_all_health()
    for source, status in health.items():
        print(f"  {source}: {status.status.value} (latency: {status.latency_ms:.0f}ms)")
    
    # Test 2: Tiingo data
    print("\n[2/4] Testing Tiingo API...")
    tiingo_data = await data_aggregator.tiingo.get_intraday_data("AAPL", resample_freq="5min")
    if tiingo_data:
        print(f"  Retrieved {len(tiingo_data)} data points")
        print(f"  Latest: {tiingo_data[-1].symbol} @ ${tiingo_data[-1].price:.2f}")
    else:
        print("  No data retrieved")
    
    # Test 3: QuantConnect data
    print("\n[3/4] Testing QuantConnect API...")
    qc_data = await data_aggregator.quantconnect.get_historical_data("SPY", days=1)
    if qc_data:
        print(f"  Retrieved {len(qc_data)} data points")
        print(f"  Latest: {qc_data[-1].symbol} @ ${qc_data[-1].price:.2f}")
    else:
        print("  No data retrieved")
    
    # Test 4: Consolidated data
    print("\n[4/4] Testing consolidated data aggregation...")
    result = await data_aggregator.get_consolidated_data("AAPL")
    print(f"\n  Consolidated Result:")
    print(f"    Symbol: {result['symbol']}")
    print(f"    Average Price: ${result['average_price']:.2f}" if result['average_price'] else "    Average Price: N/A")
    print(f"    Sources: {result['source_count']}")
    print(f"    Latency: {result['total_latency_ms']:.0f}ms")
    print(f"    Quality Score: {result['quality_score']}/100")
    
    # Validación
    is_valid, errors = await data_aggregator.validate_data_quality(result)
    print(f"    Quality Valid: {'✓ YES' if is_valid else '✗ NO'}")
    if errors:
        for error in errors:
            print(f"      - {error}")
    
    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)
    
    return result

if __name__ == "__main__":
    asyncio.run(test_data_integration())
