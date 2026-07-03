# _probe_ui_v2.ps1 — read-only Phase 6 validation probes (v2)
$ErrorActionPreference = "Continue"
function Probe([string]$u, [scriptblock]$check) {
  try {
    $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 8
    $extra = if ($check) { & $check $r } else { "" }
    "{0,-3}  {1}  {2}" -f $r.StatusCode, $u, $extra
  } catch {
    $code = $null
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    "{0}  {1}  ({2})" -f $code, $u, $_.Exception.Message
  }
}
Probe "http://127.0.0.1:8092/" {
  param($r); if ($r.Content -match 'Brain Operator Console') { "TITLE OK len=" + $r.Content.Length } else { "TITLE MISSING" }
}
Probe "http://127.0.0.1:8092/static/app.js?v=4" {
  param($r)
  $hasMode = $r.Content -match 'mode-segment'
  $hasSetMode = $r.Content -match 'function setMode'
  $hasEsc = $r.Content -match 'msg-escalation'
  "mode-segment=" + $hasMode + " setMode=" + $hasSetMode + " escalation=" + $hasEsc + " len=" + $r.Content.Length
}
Probe "http://127.0.0.1:8092/static/styles.css?v=4" {
  param($r); $has = $r.Content -match 'mode-segment'; "mode-segment-css=" + $has + " len=" + $r.Content.Length
}
Probe "http://127.0.0.1:8092/health" {
  param($r); $b = $r.Content; if ($b.Length -gt 70) { $b = $b.Substring(0,70) }; "body=" + $b
}
Probe "http://127.0.0.1:8092/brain-dashboard/status" {
  param($r); $b = $r.Content; if ($b.Length -gt 50) { $b = $b.Substring(0,50) }; "body=" + $b
}
