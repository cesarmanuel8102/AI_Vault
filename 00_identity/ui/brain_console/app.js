import { getJson, postJson } from "/ui/assets/api.js";

const state = {
  roomId: localStorage.getItem("brain_room_id") || "autobuild_brain_openai",
  bootstrap: null,
  blocked: null,
  refreshTimer: null
};

const $ = (id) => document.getElementById(id);

function esc(v) {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function fmt(v) {
  try { return JSON.stringify(v, null, 2); } catch { return String(v ?? ""); }
}

function setPill(el, mode, text) {
  el.className = "pill";
  if (mode === "good") el.classList.add("pill-good");
  else if (mode === "warn") el.classList.add("pill-warn");
  else if (mode === "bad") el.classList.add("pill-bad");
  else if (mode === "live") el.classList.add("pill-live");
  else el.classList.add("pill-muted");
  el.textContent = text;
}

function statusData() { return (state.bootstrap?.status?.data) || {}; }
function roadmapData() { return (state.bootstrap?.roadmap) || {}; }
function healthData() { return (state.bootstrap?.health) || {}; }
function runtimeData() { return (state.bootstrap?.conversation_runtime_v2) || {}; }
function contractData() { return (state.bootstrap?.contract) || {}; }
function processData() { return (state.bootstrap?.process_overview) || {}; }
function artifactsData() { return (state.bootstrap?.artifacts?.recent) || []; }
function evidenceData() { return (state.bootstrap?.evidence?.audit_tail) || []; }
function roadmapItems() { return (state.bootstrap?.roadmap?.work_items) || []; }

function extractSteps(status) {
  if (Array.isArray(status?.steps)) return status.steps;
  if (Array.isArray(status?.plan?.steps)) return status.plan.steps;
  if (Array.isArray(status?.plan_summary?.steps)) return status.plan_summary.steps;
  return [];
}

function extractBlocked(status) {
  return status?.blocked || null;
}

function statusClass(s) {
  const v = String(s || "pending");
  if (["done","in_progress","pending","blocked","error"].includes(v)) return v;
  return "pending";
}

function statusChip(s) {
  const v = statusClass(s);
  return `<span class="status-chip ${v}">${esc(v)}</span>`;
}

function refreshMeta() {
  const status = statusData();
  const roadmap = roadmapData();
  const health = healthData();

  $("roomMeta").innerHTML = `
    <div class="kv-item"><div class="kv-key">room_id</div><div class="kv-val">${esc(state.roomId)}</div></div>
    <div class="kv-item"><div class="kv-key">roadmap</div><div class="kv-val">${esc(roadmap.active_roadmap || "--")}</div></div>
    <div class="kv-item"><div class="kv-key">active item</div><div class="kv-val">${esc(roadmap.active_item?.id || "--")}</div></div>
    <div class="kv-item"><div class="kv-key">item status</div><div class="kv-val">${esc(roadmap.active_item?.status || roadmap.active_item?.status_norm || status.plan_summary?.status || "--")}</div></div>
    <div class="kv-item"><div class="kv-key">ui mode</div><div class="kv-val">${esc(health.ui_mode || "--")}</div></div>
  `;
}

function refreshSummaryStrip() {
  const status = statusData();
  const roadmap = roadmapData();
  const process = processData();
  const blocked = extractBlocked(status);
  const counts = roadmap.counts || {};

  const cards = [
    { label: "Contrato activo", value: contractData().bound ? "v2 present" : "v2 missing" },
    { label: "Plan status", value: status.plan_summary?.status || "--" },
    { label: "Etapa actual", value: process.current_stage || "--" },
    { label: "Paso actual", value: process.active_step_id || status.current_step_id || status.active_step_id || "--" },
    { label: "Roadmap item", value: roadmap.active_item?.id || "--" },
    { label: "Blocked", value: blocked ? (blocked.proposal_id || blocked.required_approve || "pending") : "none" },
    { label: "Roadmap done", value: String(counts.done || 0) },
    { label: "Roadmap in_progress", value: String(counts.in_progress || 0) }
  ];

  $("summaryStrip").innerHTML = cards.map(x => `
    <div class="summary-card">
      <div class="summary-label">${esc(x.label)}</div>
      <div class="summary-value">${esc(x.value)}</div>
    </div>
  `).join("");
}

function refreshTopPills() {
  const health = healthData();
  const brainOk = !!health?.summary?.brain_ok;
  const advisorOk = !!health?.summary?.advisor_ok;
  const snapshotOk = !!health?.summary?.runtime_bound;
  const live = !!state.bootstrap?.staleness?.is_live;

  setPill($("pillLive"), live ? "live" : "warn", live ? "LIVE" : "STALE");
  setPill($("pill8010"), brainOk ? "good" : "bad", brainOk ? "8010 OK" : "8010 FAIL");
  setPill($("pill8030"), advisorOk ? "good" : "warn", advisorOk ? "8030 OK" : "8030 DEGRADED");
  setPill($("pillSnapshot"), snapshotOk ? "good" : "warn", snapshotOk ? "SNAPSHOT OK" : "SNAPSHOT MISSING");
}

function refreshConsole() {
  const runtime = runtimeData();
  const process = processData();
  const summary = {
    room_id: state.roomId,
    runtime_bound: runtime.bound,
    current_stage: process.current_stage,
    human_action_required: process.human_action_required,
    reason: runtime.reason,
    latest_runtime_snapshot_keys: runtime.runtime_snapshot ? Object.keys(runtime.runtime_snapshot) : []
  };
  $("consoleSummary").textContent = fmt(summary);
  $("consoleState").textContent = runtime.bound ? "runtime visible" : "runtime pending";
}

function refreshProcess() {
  const process = processData();
  const summary = {
    current_stage: process.current_stage,
    current_stage_label: process.current_stage_label,
    active_step_id: process.active_step_id,
    human_action_required: process.human_action_required,
    active_roadmap_item: process.active_roadmap_item?.id || null,
    explanation: process.summary_text
  };
  $("processSummary").textContent = fmt(summary);
  $("processState").textContent = process.current_stage || "flow";

  const actors = process.actors || [];
  if (!actors.length) {
    $("actorsList").innerHTML = `<div class="actor-row"><div class="actor-title">Sin datos de actores</div></div>`;
    return;
  }

  $("actorsList").innerHTML = actors.map(a => `
    <div class="actor-row">
      <div class="actor-title">${esc(a.name)}</div>
      <div class="actor-meta"><strong>Rol:</strong> ${esc(a.role)}</div>
      <div class="actor-meta"><strong>Interviene:</strong> ${esc(a.when_intervenes)}</div>
      <div class="actor-meta"><strong>Estado actual:</strong> ${esc(a.current_state)}</div>
    </div>
  `).join("");
}

function refreshAutodev() {
  const process = processData();
  const roadmap = roadmapData();
  const stages = process.stages || [];
  const items = roadmapItems();

  $("autodevState").textContent = process.current_stage || "autodev";

  if (!stages.length) {
    $("stagesList").innerHTML = `<div class="stage-row"><div class="stage-title">Sin pipeline visible</div></div>`;
  } else {
    $("stagesList").innerHTML = stages.map(s => `
      <div class="stage-row">
        <div class="stage-title">${statusChip(s.status)}${esc(s.label)}</div>
        <div class="stage-meta"><strong>Owner:</strong> ${esc(s.owner)}</div>
        <div class="stage-meta">${esc(s.detail || "")}</div>
      </div>
    `).join("");
  }

  if (!items.length) {
    $("roadmapExecList").innerHTML = `<div class="stage-row"><div class="stage-title">Sin work items detectables</div></div>`;
  } else {
    $("roadmapExecList").innerHTML = items.slice(0, 30).map(it => `
      <div class="stage-row">
        <div class="stage-title">${statusChip(it.status_norm || it.status_raw)}${esc(it.id || "--")} — ${esc(it.title || "--")}</div>
        <div class="stage-meta"><strong>Stage:</strong> ${esc(it.stage || it.acceptance_stage || "--")}</div>
        <div class="stage-meta"><strong>Owner:</strong> ${esc(it.owner || "--")}</div>
        <div class="stage-meta">${esc(it.summary || "")}</div>
      </div>
    `).join("");
  }
}

function refreshContract() {
  const contract = contractData();
  const payload = {
    bound: contract.bound,
    version: contract.version,
    present_files: contract.present_files,
    contract_keys: contract.contract ? Object.keys(contract.contract) : [],
    clarification_policy_keys: contract.clarification_policy ? Object.keys(contract.clarification_policy) : [],
    response_policy_keys: contract.response_presentation_policy ? Object.keys(contract.response_presentation_policy) : [],
    examples_keys: contract.examples ? Object.keys(contract.examples) : []
  };
  $("contractSummary").textContent = fmt(payload);
  $("contractState").textContent = contract.bound ? "contract present" : "contract missing";
}

function refreshPlan() {
  const status = statusData();
  const steps = extractSteps(status);
  const planSummary = {
    plan_summary: status.plan_summary || {},
    active_step_id: status.active_step_id || status.current_step_id || null,
    blocked: status.blocked || null
  };
  $("planSummary").textContent = fmt(planSummary);
  $("planState").textContent = status.plan_summary?.status || "unknown";

  if (!steps.length) {
    $("stepsList").innerHTML = `<div class="step-row"><div class="step-title">Sin steps visibles</div><div class="step-meta">El backend no expuso una lista normalizada de steps para este room.</div></div>`;
    return;
  }

  $("stepsList").innerHTML = steps.map((s, idx) => `
    <div class="step-row">
      <div class="step-title">${statusChip(s.status || "pending")}${esc(s.id || `step_${idx+1}`)}</div>
      <div class="step-meta">${esc(s.tool_name || s.type || "--")}</div>
      <div class="step-meta">${esc(s.objective || s.summary || s.note || "")}</div>
    </div>
  `).join("");
}

function refreshEvidence() {
  const events = evidenceData();
  if (!events.length) {
    $("evidenceList").innerHTML = `<div class="timeline-row"><div class="step-title">Sin evidencia reciente</div><div class="timeline-meta">No se detectó audit.ndjson reciente para este room.</div></div>`;
    return;
  }
  $("evidenceList").innerHTML = events.slice().reverse().map((line) => `
    <div class="timeline-row"><div class="timeline-meta">${esc(line)}</div></div>
  `).join("");
}

function refreshArtifacts() {
  const items = artifactsData();
  $("artifactsState").textContent = `${items.length} recent`;

  if (!items.length) {
    $("artifactsTable").innerHTML = `<div class="raw-box">No hay artifacts recientes para este room.</div>`;
    $("latestArtifact").textContent = "Sin artifacts recientes.";
    return;
  }

  $("latestArtifact").textContent = fmt(items[0]);

  $("artifactsTable").innerHTML = `
    <table class="table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Kind</th>
          <th>Updated</th>
          <th>Size</th>
          <th>Preview</th>
        </tr>
      </thead>
      <tbody>
        ${items.map(it => `
          <tr>
            <td class="code-mini">${esc(it.rel_path)}</td>
            <td>${esc(it.kind)}</td>
            <td>${esc(it.updated_utc)}</td>
            <td>${esc(it.size)}</td>
            <td>${it.previewable ? `<button class="btn btn-accent artifact-preview-btn" data-rel="${esc(it.rel_path)}">Open</button>` : ""}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;

  document.querySelectorAll(".artifact-preview-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      try {
        const rel = btn.getAttribute("data-rel");
        const r = await fetch(`/ui/api/artifact/preview?room_id=${encodeURIComponent(state.roomId)}&rel_path=${encodeURIComponent(rel)}`);
        const body = await r.text();
        $("artifactPreview").textContent = body;
      } catch (e) {
        $("artifactPreview").textContent = String(e.message || e);
      }
    });
  });
}

function refreshRoadmap() {
  const roadmap = roadmapData();
  const payload = {
    source_path: roadmap.source_path,
    program_id: roadmap.program_id,
    active_roadmap: roadmap.active_roadmap,
    status: roadmap.status,
    objective: roadmap.objective,
    active_item: roadmap.active_item,
    counts: roadmap.counts
  };
  $("roadmapSummary").textContent = fmt(payload);
  $("roadmapState").textContent = roadmap.active_item?.id || "roadmap";
}

function refreshHealth() {
  const health = healthData();
  $("healthSummary").textContent = fmt(health);
  const degraded = !health?.summary?.brain_ok || !health?.summary?.advisor_ok || !health?.summary?.runtime_bound;
  $("healthState").textContent = degraded ? "degraded" : "healthy";

  const alerts = [];
  if (!health?.summary?.brain_ok) alerts.push("8010 no sano.");
  if (!health?.summary?.advisor_ok) alerts.push("8030 degradado/no responde.");
  if (!health?.summary?.runtime_bound) alerts.push("runtime snapshot no visible todavía.");
  if (!alerts.length) alerts.push("Sin alertas críticas.");
  $("alertsBox").textContent = alerts.join("\n");
}

function refreshBlocked() {
  const blocked = extractBlocked(statusData());
  state.blocked = blocked;

  if (!blocked) {
    $("blockedBody").textContent = "No hay bloqueos pendientes.";
    $("blockedState").textContent = "none";
    $("btnApply").disabled = true;
    $("btnReject").disabled = true;
    return;
  }

  $("blockedBody").textContent = fmt(blocked);
  $("blockedState").textContent = blocked.proposal_id || blocked.required_approve || "blocked";
  $("btnApply").disabled = !blocked.required_approve;
  $("btnReject").disabled = false;
}

function refreshStatusbar() {
  $("statusbarRight").textContent = `last refresh: ${new Date().toLocaleString()}`;
}

async function refreshAll() {
  const roomId = state.roomId.trim() || "default";
  localStorage.setItem("brain_room_id", roomId);
  state.bootstrap = await getJson(`/ui/api/bootstrap?room_id=${encodeURIComponent(roomId)}`);
  refreshMeta();
  refreshSummaryStrip();
  refreshTopPills();
  refreshConsole();
  refreshProcess();
  refreshAutodev();
  refreshContract();
  refreshPlan();
  refreshEvidence();
  refreshArtifacts();
  refreshRoadmap();
  refreshHealth();
  refreshBlocked();
  refreshStatusbar();
}

async function runOnce() {
  const out = await postJson("/ui/api/run_once", { room_id: state.roomId });
  $("advisorResult").textContent = fmt(out);
  await refreshAll();
}

async function advisorNext() {
  const objective = $("objectiveInput").value.trim();
  const out = await postJson("/ui/api/advisor/next", { room_id: state.roomId, objective, publish: true });
  $("advisorResult").textContent = fmt(out);
  await refreshAll();
}

async function applyBlocked() {
  if (!state.blocked?.required_approve) return;
  const body = {
    room_id: state.roomId,
    approve_token: state.blocked.required_approve,
    proposal_id: state.blocked.proposal_id || null
  };
  const out = await postJson("/ui/api/apply", body);
  $("advisorResult").textContent = fmt(out);
  await refreshAll();
}

async function rejectBlocked() {
  if (!state.blocked) return;
  const body = {
    room_id: state.roomId,
    proposal_id: state.blocked.proposal_id || null,
    approve_token: state.blocked.required_approve || null,
    reason: "ui_reject"
  };
  const out = await postJson("/ui/api/reject", body);
  $("advisorResult").textContent = fmt(out);
  await refreshAll();
}

function wire() {
  $("roomId").value = state.roomId;

  $("btnSetRoom").addEventListener("click", async () => {
    state.roomId = $("roomId").value.trim() || "default";
    await refreshAll();
  });

  $("btnRefresh").addEventListener("click", refreshAll);
  $("btnRunOnce").addEventListener("click", runOnce);
  $("btnAdvisorNext").addEventListener("click", advisorNext);
  $("btnApply").addEventListener("click", applyBlocked);
  $("btnReject").addEventListener("click", rejectBlocked);

  if (state.refreshTimer) clearInterval(state.refreshTimer);
  state.refreshTimer = setInterval(async () => {
    if (document.visibilityState === "visible") {
      try { await refreshAll(); } catch {}
    }
  }, 5000);
}

async function main() {
  wire();
  await refreshAll();
}

main().catch(err => {
  $("alertsBox").textContent = String(err.message || err);
});