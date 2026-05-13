"""
AI_VAULT Input Validation
Fase 6: Security Enhancements - Pydantic Input Validation
"""

from pydantic import BaseModel, Field, validator, ValidationError
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum
import re


class OrderSide(str, Enum):
    """Lados de orden validos"""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Tipos de orden validos"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TradingSymbol(str, Enum):
    """Simbolos de trading soportados"""
    BTC_USD = "BTC-USD"
    ETH_USD = "ETH-USD"
    SOL_USD = "SOL-USD"
    ADA_USD = "ADA-USD"
    XRP_USD = "XRP-USD"


class OrderRequest(BaseModel):
    """
    Modelo de validacion para ordenes de trading
    """
    symbol: TradingSymbol = Field(..., description="Par de trading")
    side: OrderSide = Field(..., description="Lado de la orden")
    order_type: OrderType = Field(default=OrderType.MARKET, description="Tipo de orden")
    quantity: float = Field(..., gt=0, description="Cantidad a operar")
    price: Optional[float] = Field(None, gt=0, description="Precio limite")
    stop_price: Optional[float] = Field(None, gt=0, description="Precio de stop")
    time_in_force: Literal["GTC", "IOC", "FOK"] = Field(default="GTC")
    client_order_id: Optional[str] = Field(None, max_length=50)
    
    @validator("price")
    def validate_price_for_limit(cls, v, values):
        """Valida que price este presente para ordenes limit"""
        if values.get("order_type") in [OrderType.LIMIT, OrderType.STOP_LIMIT] and v is None:
            raise ValueError("Price requerido para ordenes limit/stop_limit")
        return v
    
    @validator("stop_price")
    def validate_stop_price(cls, v, values):
        """Valida que stop_price este presente para ordenes stop"""
        if values.get("order_type") in [OrderType.STOP, OrderType.STOP_LIMIT] and v is None:
            raise ValueError("Stop price requerido para ordenes stop")
        return v
    
    @validator("client_order_id")
    def validate_client_order_id(cls, v):
        """Valida formato de client_order_id"""
        if v and not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("client_order_id solo puede contener letras, numeros, guiones y guiones bajos")
        return v


class MarketDataRequest(BaseModel):
    """
    Modelo de validacion para solicitudes de datos de mercado
    """
    symbol: TradingSymbol
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = Field(default="1h")
    limit: int = Field(default=100, ge=1, le=1000)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @validator("end_time")
    def validate_time_range(cls, v, values):
        """Valida que end_time sea posterior a start_time"""
        if v and values.get("start_time") and v <= values["start_time"]:
            raise ValueError("end_time debe ser posterior a start_time")
        return v


class ChatMessage(BaseModel):
    """
    Modelo de validacion para mensajes de chat
    """
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str = Field(..., min_length=8, max_length=64)
    user_id: Optional[str] = Field(None, max_length=64)
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    @validator("message")
    def sanitize_message(cls, v):
        """Sanitiza el mensaje removiendo caracteres peligrosos"""
        # Remover tags HTML
        v = re.sub(r"<[^>]+>", "", v)
        # Remover caracteres de control excepto newlines
        v = "".join(char for char in v if ord(char) >= 32 or char in "\n\r\t")
        return v.strip()
    
    @validator("session_id")
    def validate_session_id(cls, v):
        """Valida formato de session_id"""
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("session_id invalido")
        return v


class FinancialTransaction(BaseModel):
    """
    Modelo de validacion para transacciones financieras
    """
    transaction_id: str = Field(..., min_length=8, max_length=64)
    amount: float = Field(..., gt=0)
    currency: str = Field(..., regex=r"^[A-Z]{3}$")
    type: Literal["deposit", "withdrawal", "transfer", "fee"]
    description: Optional[str] = Field(None, max_length=500)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    
    @validator("amount")
    def validate_amount_precision(cls, v):
        """Valida precision decimal del monto"""
        # Maximo 8 decimales para cripto
        if round(v, 8) != v:
            raise ValueError("Monto excede precision maxima (8 decimales)")
        return v


class UserRegistration(BaseModel):
    """
    Modelo de validacion para registro de usuarios
    """
    username: str = Field(..., min_length=3, max_length=32)
    email: str = Field(..., regex=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    password: str = Field(..., min_length=12, max_length=128)
    
    @validator("username")
    def validate_username(cls, v):
        """Valida formato de username"""
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username solo puede contener letras, numeros y guiones bajos")
        if v[0].isdigit():
            raise ValueError("Username no puede comenzar con numero")
        return v
    
    @validator("password")
    def validate_password_strength(cls, v):
        """Valida fortaleza de password"""
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password debe contener al menos una mayuscula")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password debe contener al menos una minuscula")
        if not re.search(r"\d", v):
            raise ValueError("Password debe contener al menos un numero")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password debe contener al menos un caracter especial")
        return v


class APIKeyRequest(BaseModel):
    """
    Modelo de validacion para solicitudes de API keys
    """
    name: str = Field(..., min_length=1, max_length=100)
    permissions: List[str] = Field(default_factory=list)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)
    allowed_ips: Optional[List[str]] = Field(default_factory=list)
    
    @validator("allowed_ips")
    def validate_ip_addresses(cls, v):
        """Valida formato de direcciones IP"""
        ip_pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
        for ip in v:
            if not re.match(ip_pattern, ip):
                raise ValueError(f"Direccion IP invalida: {ip}")
            octets = ip.split(".")
            if not all(0 <= int(o) <= 255 for o in octets):
                raise ValueError(f"Direccion IP fuera de rango: {ip}")
        return v


class WebhookPayload(BaseModel):
    """
    Modelo de validacion para webhooks
    """
    event: str = Field(..., regex=r"^[a-z_]+\.[a-z_]+$")
    timestamp: datetime
    data: Dict[str, Any]
    signature: str = Field(..., min_length=64, max_length=128)
    
    @validator("event")
    def validate_event_format(cls, v):
        """Valida formato de evento (categoria.accion)"""
        parts = v.split(".")
        if len(parts) != 2:
            raise ValueError("Evento debe tener formato 'categoria.accion'")
        return v


class PaginationParams(BaseModel):
    """
    Modelo de validacion para parametros de paginacion
    """
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)
    sort_by: Optional[str] = Field(None, regex=r"^[a-z_]+$")
    sort_order: Literal["asc", "desc"] = Field(default="desc")
    
    def get_offset(self) -> int:
        """Calcula offset para queries"""
        return (self.page - 1) * self.per_page


class ValidationErrorResponse(BaseModel):
    """
    Modelo de respuesta para errores de validacion
    """
    error: str = "Validation Error"
    message: str
    details: List[Dict[str, Any]]
    timestamp: datetime = Field(default_factory=datetime.now)


# Funciones de utilidad
def validate_order(data: dict) -> OrderRequest:
    """Valida datos de orden"""
    return OrderRequest(**data)

def validate_chat_message(data: dict) -> ChatMessage:
    """Valida mensaje de chat"""
    return ChatMessage(**data)

def validate_transaction(data: dict) -> FinancialTransaction:
    """Valida transaccion financiera"""
    return FinancialTransaction(**data)


def sanitize_string(value: str, max_length: int = 255) -> str:
    """
    Sanitiza una cadena de texto
    
    Args:
        value: Cadena a sanitizar
        max_length: Longitud maxima permitida
        
    Returns:
        Cadena sanitizada
    """
    if not value:
        return ""
    
    # Remover tags HTML
    value = re.sub(r"<[^>]+>", "", value)
    
    # Remover caracteres de control
    value = "".join(char for char in value if ord(char) >= 32 or char in "\n\r\t")
    
    # Limitar longitud
    return value.strip()[:max_length]


def validate_email(email: str) -> bool:
    """Valida formato de email"""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_phone(phone: str) -> bool:
    """Valida formato de telefono internacional"""
    pattern = r"^\+[1-9]\d{1,14}$"
    return bool(re.match(pattern, phone))


if __name__ == "__main__":
    # Demo de validacion
    print("AI_VAULT Input Validation Demo")
    print("=" * 50)
    
    # Ejemplo valido
    try:
        order = OrderRequest(
            symbol="BTC-USD",
            side="buy",
            order_type="limit",
            quantity=0.5,
            price=65000.00
        )
        print(f"Orden valida: {order.json(indent=2)}")
    except ValidationError as e:
        print(f"Error de validacion: {e}")
    
    # Ejemplo invalido
    try:
        order = OrderRequest(
            symbol="BTC-USD",
            side="buy",
            order_type="limit",
            quantity=0.5
            # Falta price para orden limit
        )
    except ValidationError as e:
        print(f"\nError esperado: {e.json()}")
    
    # Validar registro de usuario (demo deshabilitado para evitar hardcoded passwords)
    # Para pruebas use variables de entorno o fixtures de testing.
    # try:
    #     user = UserRegistration(
    #         username="test_user",
    #         email="test@example.com",
    #         password=os.getenv("AI_VAULT_TEST_PASSWORD")
    #     )
    #     print(f"\nUsuario valido: {user.username}")
    # except ValidationError as e:
    #     print(f"Error: {e}")
