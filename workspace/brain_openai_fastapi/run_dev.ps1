$env:BRAIN_UPSTREAM = "http://127.0.0.1:8010"
param(
  [string]$HostAddr = "127.0.0.1",
  [int]$Port = 8040
)
$ErrorActionPreference="Stop"
$env:APP_HOST = $HostAddr
$env:APP_PORT = $Port
$env:APP_NAME = "brain_openai_fastapi"
$env:LOG_LEVEL = "INFO"

python -m uvicorn src.app.main:app --host $HostAddr --port $Port --reload
