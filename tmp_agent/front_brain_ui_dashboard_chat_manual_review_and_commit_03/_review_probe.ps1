# _review_probe.ps1
$r = Invoke-WebRequest -Uri 'http://127.0.0.1:8092/' -UseBasicParsing -TimeoutSec 8
"root=$($r.StatusCode) title=$(if ($r.Content -match 'Brain Operator Console') {'OK'} else {'MISSING'})"
$j = Invoke-WebRequest -Uri 'http://127.0.0.1:8092/static/app.js?v=4' -UseBasicParsing -TimeoutSec 8
"app.js=$($j.StatusCode) mode-segment=$(if ($j.Content -match 'mode-segment') {'Y'} else {'N'}) setMode=$(if ($j.Content -match 'function setMode') {'Y'} else {'N'})"
$h = Invoke-WebRequest -Uri 'http://127.0.0.1:8092/health' -UseBasicParsing -TimeoutSec 8
"health=$($h.StatusCode) $($h.Content)"
