import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run(cmd, cwd: Path) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def main() -> None:
    p = argparse.ArgumentParser(description="QC -> Phase0 paper daily pipeline")
    p.add_argument("--bridge-config", default="config/qc_signal_bridge.sample.json")
    p.add_argument("--profile", default="config/firm_profiles.mffu_flex50.paper.json")
    p.add_argument("--qc-secrets", default=None)
    p.add_argument("--outdir", default="artifacts")
    args = p.parse_args()

    base = Path(__file__).resolve().parent

    # 1) Build signals from QC live orders
    bridge_cmd = [sys.executable, "build_phase0_signals_from_qc.py", "--config", args.bridge_config]
    if args.qc_secrets:
        bridge_cmd += ["--qc-secrets", args.qc_secrets]
    bridge_out = run(bridge_cmd, base)
    bridge_json = json.loads(bridge_out)
    signals_path = Path(bridge_json["output"])

    # 2) Run phase0 paper day
    day_cmd = [
        sys.executable,
        "run_phase0_paper_day.py",
        "--profile",
        args.profile,
        "--signals",
        str(signals_path),
        "--outdir",
        args.outdir,
    ]
    day_out = run(day_cmd, base)

    report = {
        "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "bridge_summary": bridge_json,
        "paper_day_stdout": day_out,
    }
    out = (base / args.outdir / f"phase0_qc_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json").resolve()
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "pipeline_report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
