from __future__ import annotations

from pathlib import Path

CONTROL_ROOT = Path("tmp_agent/control")
STOP_FILE = CONTROL_ROOT / "STOP_AUTONOMY"
PAUSE_FILE = CONTROL_ROOT / "PAUSE_AUTONOMY"
SAFE_MODE_FILE = CONTROL_ROOT / "SAFE_MODE"
RUN_ONCE_FILE = CONTROL_ROOT / "RUN_ONCE"


def ensure_control_root() -> None:
    CONTROL_ROOT.mkdir(parents=True, exist_ok=True)


def is_stopped() -> bool:
    return STOP_FILE.exists()


def is_paused() -> bool:
    return PAUSE_FILE.exists()


def safe_mode_enabled() -> bool:
    return SAFE_MODE_FILE.exists()


def set_pause(paused: bool) -> None:
    ensure_control_root()
    if paused:
        PAUSE_FILE.write_text("paused\n", encoding="utf-8")
    elif PAUSE_FILE.exists():
        PAUSE_FILE.unlink()


def set_stop(stopped: bool) -> None:
    ensure_control_root()
    if stopped:
        STOP_FILE.write_text("stopped\n", encoding="utf-8")
    elif STOP_FILE.exists():
        STOP_FILE.unlink()


def request_run_once() -> None:
    ensure_control_root()
    RUN_ONCE_FILE.write_text("run_once\n", encoding="utf-8")
