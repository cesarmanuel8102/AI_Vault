$body = @'
{"versionId": "-1", "projectId": 29490680, "compileId": "91e9aa704f8c13a10e39acd5d5f62604-e27715652009231a5f8a4635045934c0", "nodeId": "LN-64d4787830461ee45574254f643f69b3", "brokerage": {"id": "InteractiveBrokersBrokerage", "ib-user-name": "cesarmanuel81", "ib-account": "DUM891854", "ib-password": "Casiopea8102*", "ib-weekly-restart-utc-time": "22:00:00"}, "dataProviders": {"InteractiveBrokersBrokerage": {"id": "InteractiveBrokersBrokerage"}}}
'@

$headers = @{
    "Authorization" = "Basic Mzg0OTQ1OjE5NDVjOTFjNjBiZGQ5YjA0Njc3NWI5NzQ0ZWM2ZDFjNGE2MzQxYmE2MzliYjQxNjUwMzEwZjNlOTA4NmQ1OGQ="
    "Timestamp" = "1775193055"
    "Content-Type" = "application/json"
}

$response = Invoke-WebRequest -Uri "https://www.quantconnect.com/api/v2/live/create" -Method Post -Body $body -Headers $headers -ContentType "application/json"
Write-Host $response.Content
