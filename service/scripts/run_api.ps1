$ErrorActionPreference = "Stop"

$hostValue = if ($env:APP_HOST) { $env:APP_HOST } else { "0.0.0.0" }
$portValue = if ($env:APP_PORT) { $env:APP_PORT } else { "8081" }

python -m uvicorn app.main:app --host $hostValue --port $portValue
