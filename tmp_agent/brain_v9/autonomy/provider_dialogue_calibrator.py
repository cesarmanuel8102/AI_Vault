from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .dialogue_prompt_profiles import DialoguePromptProfile, iter_prompt_profiles, stable_micro_prompt_profile_ids

DEFAULT_CHAT_URL = "http://127.0.0.1:8091/v1/chat/completions"
NO_COT_PATTERNS = ("<think", "</think", "chain-of-thought", "chain of thought", "raw reasoning")


@dataclass(frozen=True)
class DialogueCalibrationResult:
    profile_id: str
    provider_selected: str | None
    model_selected: str | None
    provider_status: str | None
    fallback_used: bool | None
    content_non_empty: bool
    no_cot_leak: bool
    latency_ms: float
    error: str | None = None

    @property
    def stable(self) -> bool:
        return (
            self.provider_selected == "kimi_k2_6_cloud"
            and self.content_non_empty
            and self.no_cot_leak
            and not self.fallback_used
            and not self.error
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["stable"] = self.stable
        return data


@dataclass(frozen=True)
class DialogueCalibrationSummary:
    results: tuple[DialogueCalibrationResult, ...]
    stable_count: int
    total_count: int
    stability_ratio: float
    stable_profile_ids: tuple[str, ...]
    kimi_open_dialogue_stability: str
    recommended_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "stable_count": self.stable_count,
            "total_count": self.total_count,
            "stability_ratio": self.stability_ratio,
            "stable_profile_ids": list(self.stable_profile_ids),
            "kimi_open_dialogue_stability": self.kimi_open_dialogue_stability,
            "recommended_mode": self.recommended_mode,
        }


def _no_cot_leak(text: str) -> bool:
    lowered = (text or "").lower()
    return not any(pattern in lowered for pattern in NO_COT_PATTERNS)


def build_provider_probe_payload(profile: DialoguePromptProfile) -> dict[str, Any]:
    return {
        "model": "brain-v9",
        "messages": [{"role": "user", "content": profile.prompt}],
        "temperature": profile.temperature,
        "max_tokens": profile.max_tokens,
        "metadata": {"provider_probe": True, "read_only": True, "evaluation": True},
    }


def calibrate_profile(profile: DialoguePromptProfile, chat_url: str = DEFAULT_CHAT_URL, timeout_s: int = 35) -> DialogueCalibrationResult:
    started = time.perf_counter()
    try:
        payload = json.dumps(build_provider_probe_payload(profile)).encode("utf-8")
        request = urllib.request.Request(chat_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        brain = data.get("brain") or {}
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        return DialogueCalibrationResult(
            profile_id=profile.profile_id,
            provider_selected=brain.get("provider_selected"),
            model_selected=brain.get("model_selected"),
            provider_status=brain.get("provider_status"),
            fallback_used=brain.get("fallback_used"),
            content_non_empty=bool(content.strip()),
            no_cot_leak=_no_cot_leak(content),
            latency_ms=latency_ms,
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        return DialogueCalibrationResult(
            profile_id=profile.profile_id,
            provider_selected=None,
            model_selected=None,
            provider_status="ERROR",
            fallback_used=None,
            content_non_empty=False,
            no_cot_leak=True,
            latency_ms=latency_ms,
            error=str(exc)[:240],
        )


def summarize_calibration(results: Iterable[DialogueCalibrationResult]) -> DialogueCalibrationSummary:
    result_tuple = tuple(results)
    stable_ids = tuple(r.profile_id for r in result_tuple if r.stable)
    stable_count = len(stable_ids)
    total = len(result_tuple)
    ratio = round(stable_count / total, 3) if total else 0.0
    if stable_count >= 5:
        stability = "KIMI_OPEN_AUTONOMY_DIALOGUE_STABLE"
        mode = "use_kimi_for_constrained_open_dialogue"
    elif stable_micro_prompt_profile_ids().intersection(stable_ids):
        stability = "KIMI_OPEN_AUTONOMY_DIALOGUE_PARTIAL_MICRO_PROMPTS_ONLY"
        mode = "codex_mentor_with_kimi_micro_prompts"
    else:
        stability = "KIMI_OPEN_AUTONOMY_DIALOGUE_UNSTABLE"
        mode = "codex_mentor_only_until_provider_gap_closed"
    return DialogueCalibrationSummary(result_tuple, stable_count, total, ratio, stable_ids, stability, mode)


def run_calibration(output_json: Path, output_md: Path, chat_url: str = DEFAULT_CHAT_URL) -> DialogueCalibrationSummary:
    results = [calibrate_profile(profile, chat_url=chat_url) for profile in iter_prompt_profiles()]
    summary = summarize_calibration(results)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Kimi Open Autonomy Dialogue Calibration",
        "",
        f"- stable_count: `{summary.stable_count}/{summary.total_count}`",
        f"- stability_ratio: `{summary.stability_ratio}`",
        f"- status: `{summary.kimi_open_dialogue_stability}`",
        f"- recommended_mode: `{summary.recommended_mode}`",
        "",
        "| profile | provider | status | fallback | non_empty | no_cot | stable |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for result in summary.results:
        lines.append(
            f"| {result.profile_id} | {result.provider_selected} | {result.provider_status} | "
            f"{result.fallback_used} | {result.content_non_empty} | {result.no_cot_leak} | {result.stable} |"
        )
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    evidence = Path("tmp_agent/mega_front_brain_self_training_autonomy_maximization_200cycles_01")
    summary = run_calibration(evidence / "kimi_dialogue_calibration.json", evidence / "kimi_dialogue_calibration.md")
    print(json.dumps({"stable": summary.stable_count, "total": summary.total_count, "status": summary.kimi_open_dialogue_stability}, separators=(",", ":")))
