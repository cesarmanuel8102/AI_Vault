"""
Brain V9 — Unified State I/O
Canonical JSON read/write with:
  - File locking (Windows-compatible via msvcrt)
  - Atomic writes (write to .tmp then rename)
  - Structured error logging (never silent swallow)
  - Optional schema validation
  - Bounded collection helpers (ledger rotation, list cap)

Usage:
    from brain_v9.core.state_io import read_json, write_json

    data = read_json(path, default={})
    write_json(path, data)
"""
import json
import logging
import os
import shutil
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

log = logging.getLogger("state_io")

_IO_MAX_RETRIES = 4
_IO_RETRY_BASE_SLEEP = 0.05
_RETRYABLE_ERRNOS = {13, 11}
_RETRYABLE_WINERRORS = {5, 32, 33}

# ── File Locking (Windows-compatible) ─────────────────────────────────────────
# On Windows we use msvcrt; on POSIX we use fcntl.
# Both provide advisory locking sufficient for single-machine concurrency.

try:
    import msvcrt

    def _lock_file(f, exclusive: bool = True):
        """Lock the file handle (Windows)."""
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK if exclusive else msvcrt.LK_NBRLCK, 1)

    def _unlock_file(f):
        """Unlock the file handle (Windows)."""
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception as exc:
            log.debug("msvcrt unlock failed: %s", exc)

except ImportError:
    import fcntl  # type: ignore[import-not-found]

    def _lock_file(f, exclusive: bool = True):
        """Lock the file handle (POSIX)."""
        fcntl.flock(f.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)

    def _unlock_file(f):
        """Unlock the file handle (POSIX)."""
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception as exc:
            log.debug("fcntl unlock failed: %s", exc)


def _is_retryable_os_error(exc: OSError) -> bool:
    """Return True when the OS error is likely a transient file lock/contention."""
    errno = getattr(exc, "errno", None)
    winerror = getattr(exc, "winerror", None)
    return errno in _RETRYABLE_ERRNOS or winerror in _RETRYABLE_WINERRORS


# ── Core Read ─────────────────────────────────────────────────────────────────

def read_json(
    path: Union[str, Path],
    default: Any = None,
    *,
    validator: Optional[Callable[[Any], bool]] = None,
    log_missing: bool = False,
) -> Any:
    """
    Read and parse a JSON file with proper error handling.

    Args:
        path:        File path (str or Path).
        default:     Value returned if file is missing or unreadable.
                     A deepcopy is returned to prevent mutation of the default.
        validator:   Optional callable; if it returns False the data is treated
                     as invalid and the default is returned.
        log_missing: If True, log a warning when the file doesn't exist.
                     Default False because many callers expect absent files.

    Returns:
        Parsed JSON data, or deepcopy(default) on any failure.
    """
    p = Path(path)

    if not p.exists():
        if log_missing:
            log.warning("state_io.read: file not found: %s", p)
        return deepcopy(default)

    for attempt in range(1, _IO_MAX_RETRIES + 1):
        try:
            with open(p, "r", encoding="utf-8") as f:
                _lock_file(f, exclusive=False)
                try:
                    raw = f.read()
                    if not raw.strip():
                        log.warning("state_io.read: empty file: %s", p)
                        return deepcopy(default)
                    data = json.loads(raw)
                finally:
                    _unlock_file(f)

            # Optional validation
            if validator is not None:
                if not validator(data):
                    log.warning(
                        "state_io.read: validation failed for %s, returning default", p
                    )
                    return deepcopy(default)

            return data

        except json.JSONDecodeError as e:
            log.error("state_io.read: corrupt JSON in %s: %s", p, e)
            # Back up corrupt file for debugging
            _backup_corrupt(p)
            return deepcopy(default)

        except OSError as e:
            if _is_retryable_os_error(e) and attempt < _IO_MAX_RETRIES:
                sleep_s = _IO_RETRY_BASE_SLEEP * attempt
                log.debug(
                    "state_io.read: transient OS error reading %s (attempt %d/%d): %s",
                    p, attempt, _IO_MAX_RETRIES, e,
                )
                time.sleep(sleep_s)
                continue
            log.error("state_io.read: OS error reading %s: %s", p, e)
            return deepcopy(default)

        except Exception as e:
            log.error("state_io.read: unexpected error reading %s: %s", p, e)
            return deepcopy(default)


# ── Core Write ────────────────────────────────────────────────────────────────

def write_json(
    path: Union[str, Path],
    payload: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
    backup_on_overwrite: bool = False,
) -> bool:
    """
    Write data to a JSON file atomically.

    Writes to a temporary file first, then renames to the target path.
    This prevents partial/corrupt files from interrupted writes.

    Args:
        path:               Target file path.
        payload:            Data to serialize (must be JSON-serializable).
        indent:             JSON indentation (default 2).
        ensure_ascii:       If False (default), allow UTF-8 characters.
        backup_on_overwrite: If True, copy existing file to .bak before writing.

    Returns:
        True on success, False on failure.
    """
    p = Path(path)

    for attempt in range(1, _IO_MAX_RETRIES + 1):
        try:
            # Ensure parent directory exists
            p.parent.mkdir(parents=True, exist_ok=True)

            # Optional backup
            if backup_on_overwrite and p.exists():
                bak = p.with_suffix(p.suffix + ".bak")
                try:
                    shutil.copy2(str(p), str(bak))
                except Exception as e:
                    log.warning("state_io.write: backup failed for %s: %s", p, e)

            # Atomic write: write to .tmp, then rename
            tmp_path = p.with_suffix(p.suffix + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                _lock_file(f, exclusive=True)
                try:
                    json.dump(payload, f, indent=indent, ensure_ascii=ensure_ascii, default=str)
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    _unlock_file(f)

            # Atomic rename (on Windows, need to remove target first)
            if os.name == "nt" and p.exists():
                os.replace(str(tmp_path), str(p))
            else:
                os.rename(str(tmp_path), str(p))

            return True

        except (TypeError, ValueError) as e:
            log.error("state_io.write: serialization error for %s: %s", p, e)
            _cleanup_tmp(p)
            return False

        except OSError as e:
            _cleanup_tmp(p)
            if _is_retryable_os_error(e) and attempt < _IO_MAX_RETRIES:
                sleep_s = _IO_RETRY_BASE_SLEEP * attempt
                log.debug(
                    "state_io.write: transient OS error writing %s (attempt %d/%d): %s",
                    p, attempt, _IO_MAX_RETRIES, e,
                )
                time.sleep(sleep_s)
                continue
            log.error("state_io.write: OS error writing %s: %s", p, e)
            return False

        except Exception as e:
            log.error("state_io.write: unexpected error writing %s: %s", p, e)
            _cleanup_tmp(p)
            return False

    return False


# ── Bounded Collection Helpers ────────────────────────────────────────────────

def append_to_json_list(
    path: Union[str, Path],
    entry: Any,
    *,
    max_entries: int = 1000,
    prune_to: Optional[int] = None,
) -> bool:
    """
    Append an entry to a JSON file containing a list.
    If the list exceeds max_entries, prune oldest entries.

    Args:
        path:        File path.
        entry:       Item to append.
        max_entries:  Maximum list length before pruning.
        prune_to:    After pruning, keep this many entries.
                     Defaults to max_entries // 2.

    Returns:
        True on success, False on failure.
    """
    if prune_to is None:
        prune_to = max_entries // 2

    data = read_json(path, default=[])
    if not isinstance(data, list):
        log.warning("state_io.append: %s is not a list, resetting", path)
        data = []

    data.append(entry)

    if len(data) > max_entries:
        log.info(
            "state_io.append: pruning %s from %d to %d entries",
            path, len(data), prune_to,
        )
        data = data[-prune_to:]

    return write_json(path, data)


def append_to_json_dict_list(
    path: Union[str, Path],
    key: str,
    entry: Any,
    *,
    max_entries: int = 1000,
) -> bool:
    """
    Append an entry to a list stored under a key in a JSON dict file.
    Example: {"actions": [...], "errors": [...]}

    Args:
        path:        File path.
        key:         Dict key that holds the list.
        entry:       Item to append.
        max_entries:  Max length for the list under this key.

    Returns:
        True on success, False on failure.
    """
    data = read_json(path, default={})
    if not isinstance(data, dict):
        log.warning("state_io.append_dict: %s is not a dict, resetting", path)
        data = {}

    lst = data.get(key, [])
    if not isinstance(lst, list):
        lst = []
    lst.append(entry)

    if len(lst) > max_entries:
        lst = lst[-max_entries:]

    data[key] = lst
    return write_json(path, data)


# ── Validators ────────────────────────────────────────────────────────────────
# Reusable validator functions for common state file schemas.

def is_dict(data: Any) -> bool:
    """Validate that data is a dict."""
    return isinstance(data, dict)


def is_list(data: Any) -> bool:
    """Validate that data is a list."""
    return isinstance(data, list)


def has_keys(*keys: str) -> Callable[[Any], bool]:
    """Return a validator that checks a dict has all specified keys."""
    def _check(data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        return all(k in data for k in keys)
    return _check


# ── Internal Helpers ──────────────────────────────────────────────────────────

def append_ndjson(
    path: Union[str, Path],
    entry: Any,
    *,
    ensure_ascii: bool = True,
) -> bool:
    """
    Append a single JSON object as a line to an NDJSON file.

    Creates the file if it doesn't exist.  Uses file locking to prevent
    interleaved writes from concurrent processes.

    Args:
        path:          Target .ndjson file.
        entry:         Data to serialize as one JSON line.
        ensure_ascii:  Passed to json.dumps (default True for NDJSON compat).

    Returns:
        True on success, False on failure.
    """
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            _lock_file(f, exclusive=True)
            try:
                f.write(json.dumps(entry, ensure_ascii=ensure_ascii, default=str))
                f.write("\n")
                f.flush()
            finally:
                _unlock_file(f)
        return True
    except Exception as e:
        log.error("state_io.append_ndjson: error writing %s: %s", p, e)
        return False


def read_text(
    path: Union[str, Path],
    default: str = "",
    *,
    encoding: str = "utf-8",
    errors: str = "replace",
) -> str:
    """
    Read a text file with proper error handling and file locking.

    Args:
        path:     File path.
        default:  Value returned if file is missing or unreadable.
        encoding: File encoding (default utf-8).
        errors:   Error handling for decode (default 'replace').

    Returns:
        File contents as string, or default on failure.
    """
    p = Path(path)
    if not p.exists():
        return default
    try:
        with open(p, "r", encoding=encoding, errors=errors) as f:
            _lock_file(f, exclusive=False)
            try:
                return f.read()
            finally:
                _unlock_file(f)
    except Exception as e:
        log.error("state_io.read_text: error reading %s: %s", p, e)
        return default


def _backup_corrupt(path: Path):
    """Move a corrupt JSON file to .corrupt.TIMESTAMP for debugging."""
    try:
        ts = time.strftime("%Y%m%d_%H%M%S")
        corrupt_path = path.with_suffix(f".corrupt.{ts}")
        shutil.copy2(str(path), str(corrupt_path))
        log.info("state_io: backed up corrupt file to %s", corrupt_path)
    except Exception as e:
        log.warning("state_io: failed to backup corrupt file %s: %s", path, e)


def _cleanup_tmp(path: Path):
    """Remove leftover .tmp file from failed atomic write."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        if tmp.exists():
            tmp.unlink()
    except Exception as exc:
        log.debug("Could not remove tmp file %s: %s", tmp, exc)
