# _probe_ui.ps1 — read-only Phase 4 UI validation probes
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
  param($r); if ($r.Content -match 'Brain Operator Console') { "TITLE=new-shell OK len=" + $r.Content.Length } else { "TITLE=MISSING len=" + $r.Content.Length }
}
Probe "http://127.0.0.1:8092/health" {
  param($r); $b = $r.Content; if ($b.Length -gt 80) { $b = $b.Substring(0,80) }; "body=" + $b
}
Probe "http://127.0.0.1:8092/static/app.js?v=3" {
  param($r); if ($r.Content -match 'renderMarkdown') { "NEW-JS OK len=" + $r.Content.Length } else { "OLD-JS? len=" + $r.Content.Length }
}
Probe "http://127.0.0.1:8092/static/styles.css?v=3" {
  param($r); if ($r.Content -match 'topbar') { "NEW-CSS OK len=" + $r.Content.Length } else { "OLD-CSS? len=" + $r.Content.Length }
}
Probe "http://127.0.0.1:8092/brain-dashboard/status" {
  param($r); $b = $r.Content; if ($b.Length -gt 60) { $b = $b.Substring(0,60) }; "body=" + $b
}
