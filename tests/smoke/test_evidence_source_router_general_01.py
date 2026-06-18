#!/usr/bin/env python3
"""
Evidence source router general test matrix.
Ensures deterministic routing selects correct source(s) for each domain.
"""
import sys, json
sys.path.insert(0, r"C:\AI_VAULT_CANONICAL\tmp_agent")

import brain_v9.config as cfg
cfg.BRAIN_USE_LLM_INTENT_CLASSIFIER = False

from brain_v9.core.agent_kernel_v2.intent_adapter import AgentV2IntentAdapter

adapter = AgentV2IntentAdapter()

CASES = [
    {
        "label": "A1: curated ingestion spanish",
        "query": "CUALES Y CUANTAS FUENTES DE INGESTA CURADA TIENE BRAIN EN ESTE MOMENTO?",
        "route": "brain_evidence",
        "expected_sources": {"learning_external"},
        "must_have_paths": ["source_registry.py", "external_intel_ingestor.py"],
        "must_have_tool": "file_read",
    },
    {
        "label": "A2: donde aprende Brain",
        "query": "de dónde aprende Brain sus fuentes externas?",
        "route": "brain_evidence",
        "expected_sources": {"learning_external"},
        "must_have_paths": ["external_intel_ingestor.py"],
        "must_have_tool": "file_read",
    },
    {
        "label": "A3: github repos spanish",
        "query": "qué repositorios de GitHub usa Brain para aprender?",
        "route": "brain_evidence",
        "expected_sources": {"learning_external"},
        "must_have_paths": ["github"],
        "must_have_tool": "file_read",
    },
    {
        "label": "A4: curated ingestion english",
        "query": "what curated external ingestion sources does Brain have?",
        "route": "brain_evidence",
        "expected_sources": {"learning_external"},
        "must_have_paths": ["source_registry.py"],
        "must_have_tool": "file_read",
    },
    {
        "label": "A5: show source_registry",
        "query": "show source_registry.py sources",
        "route": "brain_evidence",
        "expected_sources": {"learning_external"},
        "must_have_paths": ["source_registry.py"],
        "must_have_tool": "file_read",
    },
    {
        "label": "B1: restart server spanish",
        "query": "reinicia el servidor 8091",
        "route": "brain_evidence",
        "expected_sources": {"runtime_operations"},
        "must_have_tool": "file_read",
    },
    {
        "label": "B2: process on port spanish",
        "query": "qué proceso está corriendo Brain en el puerto 8091?",
        "route": "brain_evidence",
        "expected_sources": {"runtime_operations"},
        "must_have_tool": "file_read",
    },
    {
        "label": "C1: available tools spanish",
        "query": "qué herramientas tiene disponibles el agente?",
        "route": "brain_evidence",
        "expected_sources": {"tools_capabilities"},
        "must_have_tool": "file_read",
    },
    {
        "label": "C2: file_read failed spanish",
        "query": "por qué file_read falló?",
        "route": "brain_evidence",
        "expected_sources": {"tools_capabilities"},
        "must_have_tool": "file_read",
    },
    {
        "label": "D1: execution trace spanish",
        "query": "muéstrame el execution trace del run_id agv2_x",
        "route": "brain_evidence",
        "expected_sources": {"traces"},
        "must_have_tool": "file_read",
    },
    {
        "label": "D2: executed tools spanish",
        "query": "qué tools se ejecutaron realmente?",
        "route": "brain_evidence",
        "expected_sources": {"traces"},
        "must_have_tool": "file_read",
    },
    {
        "label": "E1: production readiness spanish",
        "query": "está Agent V2 listo para producción?",
        "route": "brain_evidence",
        "expected_sources": {"production_operations"},
        "must_have_tool": "file_read",
    },
    {
        "label": "E2: operator ready english",
        "query": "operator ready status production operations",
        "route": "brain_evidence",
        "expected_sources": {"production_operations"},
        "must_have_tool": "file_read",
    },
    {
        "label": "F1: microfix autonomous spanish",
        "query": "qué microfix evitó que autonomous disparara AUTO?",
        "route": "brain_evidence",
        "expected_sources": {"autonomous_microfix"},
        "must_have_tool": "file_read",
    },
    {
        "label": "F2: auto mode activated spanish",
        "query": "por qué el modo auto se activó?",
        "route": "brain_evidence",
        "expected_sources": {"autonomous_microfix"},
        "must_have_tool": "file_read",
    },
    {
        "label": "G1: general brain structure spanish",
        "query": "explícame cómo está estructurado Brain",
        "route": "brain_evidence",
        "expected_sources": {"front_brain"},
        "forbidden_sources": {"learning_external"},
    },
    {
        "label": "H1: chicken recipe spanish",
        "query": "dame una receta de arroz con pollo",
        "route": "direct_assistant",
        "expected_sources": set(),
    },
]


def run_matrix():
    passed = 0
    failed = 0
    failed_cases = []

    for case in CASES:
        label = case["label"]
        query = case["query"]
        route_info = adapter.select_route(query)
        route = route_info["route"]
        sources = adapter.get_evidence_sources(route, query) if route == "brain_evidence" else []
        source_types = {s["type"] for s in sources}

        ok = True
        msgs = []

        # Check route
        if route != case["route"]:
            ok = False
            msgs.append(f"route={route} expected={case['route']}")

        # Check expected sources
        for exp in case.get("expected_sources", set()):
            if exp not in source_types:
                ok = False
                msgs.append(f"missing_source={exp}")

        # Check forbidden sources
        for forbid in case.get("forbidden_sources", set()):
            if forbid in source_types:
                ok = False
                msgs.append(f"forbidden_source_present={forbid}")

        # Check must-have paths on the *specific* source(s) they belong to
        for mh in case.get("must_have_paths", []):
            found = False
            for src in sources:
                if any(mh in p for p in src.get("paths", [])):
                    found = True
                    break
            if not found:
                ok = False
                msgs.append(f"missing_path_keyword={mh}")

        # Check must-have tool
        if case.get("must_have_tool"):
            has_tool = any(case["must_have_tool"] in s.get("tools", []) for s in sources)
            if not has_tool:
                ok = False
                msgs.append(f"missing_tool={case['must_have_tool']}")

        if ok:
            passed += 1
            print(f"PASS {label}")
        else:
            failed += 1
            failed_cases.append(label)
            print(f"FAIL {label}: {'; '.join(msgs)}")
            print(f"  sources={source_types}")

    print(f"\nTOTAL={len(CASES)} PASSED={passed} FAILED={failed}")
    if failed_cases:
        print(f"FAILED_CASES={failed_cases}")
    assert failed == 0, f"Matrix had {failed} failures"
    print("MATRIX_PASS")


if __name__ == "__main__":
    run_matrix()
