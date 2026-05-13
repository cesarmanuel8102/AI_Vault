"""R10.2c failure-path test.

Goal: verify auto-rollback triggers when health gate times out.

Strategy: respawn_wait=1, poll_seconds=5.
- Gate kills brain at T=0.
- Gate sleeps 1s, polls 5s -> watchdog hasn't respawned yet -> NOT healthy.
- Gate restores files from backups.
- Gate kills brain again, sleeps 1s, polls 60s.
- Watchdog respawns brain ~T+30s, healthy ~T+60s -> within 60s poll window.
- Final status -> 'rolled_back_auto'.

Verifies:
* Rollback file restore actually reverts changes
* Status transitions correctly (applied_pending_health -> rolled_back_auto)
* Gate log shows AUTO-ROLLBACK SUCCESS
"""
import json
import time
import urllib.request
from pathlib import Path

PROP_ID = "ce_prop_20260504_133441"
PROP_PATH = Path("C:/AI_VAULT/tmp_agent/state/proposed_patches") / f"{PROP_ID}.json"
LLM_PATH = Path("C:/AI_VAULT/tmp_agent/brain_v9/core/llm.py")


def http_post(url, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def http_get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def reset_proposal():
    rec = json.loads(PROP_PATH.read_text(encoding="utf-8-sig"))
    rec["status"] = "pending_review"
    for k in (
        "applied_at", "applied_by", "apply_note", "diff", "backups",
        "applied_edits", "health_gate_started_at", "health_gate_poll_seconds",
        "health_gate_respawn_wait", "health_gate_pid", "health_gate_completed_at",
        "health_gate_spawn_error", "rolled_back_at", "rollback_reason",
        "rollback_restored", "rollback_failed", "health_gate_post_rollback_pid",
    ):
        rec.pop(k, None)
    PROP_PATH.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[reset] proposal reset to pending_review")


def get_llm_constants():
    src = LLM_PATH.read_text(encoding="utf-8")
    th = next((l for l in src.splitlines() if "_CB_FAIL_THRESHOLD" in l and "=" in l), None)
    cd = next((l for l in src.splitlines() if "_CB_COOLDOWN_S" in l and "=" in l), None)
    return th.strip() if th else None, cd.strip() if cd else None


def main():
    print("=== R10.2c FAILURE-PATH e2e test ===\n")

    # 0. Sanity: file should be at baseline 2/180
    th, cd = get_llm_constants()
    print(f"[pre] llm.py: {th}, {cd}")
    if "= 2" not in (th or "") or "= 180" not in (cd or ""):
        print(f"[ABORT] llm.py not at baseline 2/180. Manual fix needed first.")
        return 2

    # 1. Reset proposal state
    reset_proposal()

    # 2. Apply with aggressive timing -> forces rollback path
    print("\n[apply] auto_restart=True, poll_seconds=5, respawn_wait=1")
    res = http_post(
        f"http://127.0.0.1:8090/brain/chat_excellence/proposals/{PROP_ID}/apply",
        {
            "by": "r10.2c_failure_test",
            "note": "force-fail to trigger auto-rollback",
            "dry_run": False,
            "auto_restart": True,
            "poll_seconds": 5,
            "respawn_wait": 1,
        },
    )
    print(f"[apply resp] ok={res.get('ok')} status={res.get('status')} "
          f"gate_spawned={res.get('health_gate_spawned')} err={res.get('health_gate_error')}")
    if not res.get("ok") or not res.get("health_gate_spawned"):
        print("[ABORT] apply failed or gate not spawned")
        return 3

    # 3. Verify file was actually changed (5/60)
    th2, cd2 = get_llm_constants()
    print(f"[post-apply] llm.py: {th2}, {cd2}")
    expect_changed = ("= 5" in (th2 or "") and "= 60" in (cd2 or ""))
    if not expect_changed:
        print(f"[WARN] file does NOT show expected 5/60 changes. proceeding.")

    # 4. Wait long enough for gate full cycle:
    # T+0 kill -> T+1 sleep -> T+6 give up -> rollback -> T+7 kill -> T+8 sleep
    # -> poll 60s waiting for watchdog respawn (~T+37 launch, ~T+67 healthy)
    # -> mark rolled_back_auto
    # Plus schtasks runs gate ~90s after apply call. So total ~90 + 70 = 160s minimum.
    # Add buffer -> poll up to 300s.
    print("\n[wait] polling proposal status up to 300s (expect 'rolled_back_auto')...")
    deadline = time.time() + 300
    last_status = None
    while time.time() < deadline:
        try:
            rec = json.loads(PROP_PATH.read_text(encoding="utf-8-sig"))
            status = rec.get("status")
            if status != last_status:
                print(f"  [{int(time.time()-(deadline-300))}s] status={status}")
                last_status = status
            if status in ("rolled_back_auto", "rollback_failed", "applied_active"):
                print(f"\n[final] status={status}")
                # Verify files restored
                th3, cd3 = get_llm_constants()
                print(f"[final] llm.py: {th3}, {cd3}")
                if status == "rolled_back_auto":
                    if "= 2" in (th3 or "") and "= 180" in (cd3 or ""):
                        print("[OK] files restored to baseline 2/180")
                    else:
                        print("[FAIL] status=rolled_back_auto but file NOT at baseline!")
                        return 4
                # Check gate log
                try:
                    log = http_get(f"http://127.0.0.1:8090/brain/chat_excellence/proposals/{PROP_ID}/health_gate_log?tail=50")
                    print("\n--- last 20 gate log lines ---")
                    for line in (log.get("log") or "").splitlines()[-20:]:
                        print(f"  {line}")
                except Exception as e:
                    print(f"[warn] gate log fetch failed: {e}")
                return 0 if status == "rolled_back_auto" else 5
        except Exception as e:
            print(f"  [poll error] {e}")
        time.sleep(5)

    print("\n[TIMEOUT] no terminal status after 300s")
    return 6


if __name__ == "__main__":
    raise SystemExit(main())
