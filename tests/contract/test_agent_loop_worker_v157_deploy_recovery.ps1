$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") "..")

function Test-WorkerContainsV157PromptDelivery {
  $source = Join-Path $Root "scripts\agent_loop\local_worker\agent_worker.py"
  $text = Get-Content -LiteralPath $source -Raw
  @("prompt_task_sentinel", "validate_executor_delivery", "_CONVERSATIONAL_REJECTION_PATTERNS",
    "_opencode_node_entrypoint", "STATE_SCHEMA_VERSION", "EVENT_REQUIRED_FIELDS") | ForEach-Object {
    if ($text -notmatch $_) { throw "v157 function/symbol missing in worker: $_" }
  }
}

function Test-WorkerContractContainsV157Flags {
  $path = Join-Path $Root "scripts\agent_loop\local_worker\worker_contract.json"
  $json = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
  $hardening = $json.hardening
  @("v157_prompt_delivery_sentinel", "v157_executor_jsonl_ack_required",
    "v157_conversational_refusal_rejected", "v157_no_output_change_rejected",
    "v157_state_schema_version", "v157_event_required_fields",
    "v157_codex_supervisor_prompt", "v157_worker_contract_workflow_updated") | ForEach-Object {
    if (-not $hardening.$_) { throw "v157 contract flag missing: $_" }
  }
}

function Test-WorkerContractWorkflowIncludesV157Tests {
  $path = Join-Path $Root ".github\workflows\agent-loop-worker-contract.yml"
  $text = Get-Content -LiteralPath $path -Raw
  @("test_agent_loop_worker_v157_runtime_resolution.py",
    "test_agent_loop_worker_v157_real_cmd_quoting.py",
    "test_agent_loop_worker_v157_lossless_transport.py",
    "test_agent_loop_worker_v157_prompt_delivery.py",
    "test_agent_loop_worker_v157_state_event_contract.py",
    "test_agent_loop_worker_v157_codex_supervisor_contract.py") | ForEach-Object {
    if ($text -notmatch $_) { throw "v157 test not referenced in worker-contract workflow: $_" }
  }
}

function Test-InstalledWorkerCanBeValidated {
  $install = Join-Path ([IO.Path]::GetTempPath()) ("v157-install-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path (Join-Path $install "worker") | Out-Null
  $source = Join-Path $Root "scripts\agent_loop\local_worker\agent_worker.py"
  $dest = Join-Path $install "worker\agent_worker.py"
  Copy-Item -LiteralPath $source -Destination $dest -Force
  $installed = Get-Content -LiteralPath $dest -Raw
  if ($installed -notmatch "prompt_task_sentinel") { throw "installed worker missing v157 prompt delivery" }
  if ($installed -notmatch "validate_executor_delivery") { throw "installed worker missing v157 delivery validation" }
}

Test-WorkerContainsV157PromptDelivery
Test-WorkerContractContainsV157Flags
Test-WorkerContractWorkflowIncludesV157Tests
Test-InstalledWorkerCanBeValidated
Write-Host '{"status":"PASS","tests":["worker_symbols","contract_flags","workflow_references","installed_worker_validation"],"atomic_command":true}'
