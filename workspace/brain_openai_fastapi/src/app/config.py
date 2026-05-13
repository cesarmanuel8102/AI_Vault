from pydantic import BaseModel
import os

class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "brain_openai_fastapi")
    host: str = os.getenv("APP_HOST", "127.0.0.1")
    port: int = int(os.getenv("APP_PORT", "8040"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

settings = Settings()