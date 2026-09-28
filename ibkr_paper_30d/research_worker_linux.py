"""Trusted Linux-side worker for the WSL research sandbox."""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import errno
import io
import json
import os
import resource
import runpy
import sys
import time
import traceback
from pathlib import Path


WORKER_SCHEMA = "RESEARCH_WORKER_RESULT_V1"
MAX_CAPTURE_CHARS = 512 * 1024
SCMP_ACT_ALLOW = 0x7FFF0000
SCMP_ACT_ERRNO = 0x00050000 | errno.EPERM
DENIED_SYSCALLS = (
    "socket",
    "socketpair",
    "connect",
    "bind",
    "listen",
    "accept",
    "accept4",
    "sendto",
    "sendmsg",
    "sendmmsg",
    "recvfrom",
    "recvmsg",
    "recvmmsg",
    "execve",
    "execveat",
    "fork",
    "vfork",
    "clone",
    "clone3",
    "ptrace",
    "mount",
    "umount2",
    "pivot_root",
    "setns",
    "unshare",
    "bpf",
    "keyctl",
    "add_key",
    "request_key",
    "open_by_handle_at",
    "name_to_handle_at",
    "process_vm_readv",
    "process_vm_writev",
)


class BoundedText(io.TextIOBase):
    def __init__(self, limit: int = MAX_CAPTURE_CHARS) -> None:
        self.limit = limit
        self.parts: list[str] = []
        self.length = 0
        self.truncated = False

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        text = str(value)
        available = max(0, self.limit - self.length)
        if available:
            self.parts.append(text[:available])
            self.length += min(len(text), available)
        if len(text) > available:
            self.truncated = True
        return len(text)

    def getvalue(self) -> str:
        return "".join(self.parts)


def _set_limits(timeout_seconds: int) -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (max(1, timeout_seconds), max(2, timeout_seconds + 1)))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    if hasattr(resource, "RLIMIT_NPROC"):
        resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))


def _install_seccomp() -> None:
    library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    library.seccomp_rule_add.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    context = library.seccomp_init(SCMP_ACT_ALLOW)
    if not context:
        raise RuntimeError("seccomp_init failed")
    try:
        for name in DENIED_SYSCALLS:
            syscall = library.seccomp_syscall_resolve_name(name.encode("ascii"))
            if syscall < 0:
                continue
            result = library.seccomp_rule_add(context, SCMP_ACT_ERRNO, syscall, 0)
            if result != 0:
                raise RuntimeError(f"seccomp_rule_add failed for {name}: {result}")
        result = library.seccomp_load(context)
        if result != 0:
            raise RuntimeError(f"seccomp_load failed: {result}")
    finally:
        library.seccomp_release(context)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True)
    parser.add_argument("--timeout", required=True, type=int)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    script = Path("/workspace") / Path(*args.script.split("/"))
    if not script.is_file() or script.is_symlink():
        raise SystemExit("invalid research script")

    os.environ.clear()
    os.environ.update(
        {
            "HOME": "/nonexistent",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TMPDIR": "/scratch",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    os.chdir("/workspace/experiments")
    _set_limits(args.timeout)
    _install_seccomp()

    stdout = BoundedText()
    stderr = BoundedText()
    status = "COMPLETED"
    returncode = 0
    failure_reason = None
    started = time.monotonic()
    try:
        sys.argv = [str(script), *args.arguments]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        returncode = int(code)
        if returncode != 0:
            status = "FAILED"
            failure_reason = "SCRIPT_EXIT_NONZERO"
    except BaseException as exc:
        status = "FAILED"
        returncode = 1
        failure_reason = type(exc).__name__
        stderr.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__, limit=12)))

    usage = resource.getrusage(resource.RUSAGE_SELF)
    result = {
        "schema": WORKER_SCHEMA,
        "status": status,
        "returncode": returncode,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "output_truncated": stdout.truncated or stderr.truncated,
        "resource_usage": {
            "cpu_seconds": round(usage.ru_utime + usage.ru_stime, 6),
            "max_rss_kib": int(usage.ru_maxrss),
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        },
        "failure_reason": failure_reason,
    }
    sys.__stdout__.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
    sys.__stdout__.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
