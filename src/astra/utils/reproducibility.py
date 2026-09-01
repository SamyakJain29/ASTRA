"""Small reproducibility helpers shared by research runners."""

from __future__ import annotations

import ctypes
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(payload: Any) -> str:
    """Hash a JSON-compatible value with stable key and separator choices."""
    serialized = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def git_state(project_root: Path) -> dict[str, str | bool | None]:
    """Return the current commit and dirty state without requiring a repository."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        return {"commit": commit, "dirty": bool(status.strip()), "note": None}
    except (OSError, subprocess.CalledProcessError):
        return {
            "commit": None,
            "dirty": None,
            "note": "Repository has no resolvable commit.",
        }


def peak_working_set_bytes() -> int | None:
    """Return peak process working-set bytes on Windows when available."""
    if sys.platform != "win32":
        return None
    try:
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.argtypes = []
        get_current_process.restype = wintypes.HANDLE
        get_process_memory_info = psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_process_memory_info.restype = wintypes.BOOL
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        result = get_process_memory_info(
            get_current_process(), ctypes.byref(counters), counters.cb
        )
        return int(counters.PeakWorkingSetSize) if result else None
    except (AttributeError, OSError):
        return None


def build_experiment_identity(
    scientific_config: Any,
    *,
    dataset_manifest_sha256: str,
    split_manifest_sha256: str,
    code_sha256: dict[str, str],
) -> dict[str, Any]:
    """Build deterministic scientific metadata independent of runtime measurements."""
    identity_payload = {
        "scientific_config": scientific_config,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "split_manifest_sha256": split_manifest_sha256,
        "code_sha256": dict(sorted(code_sha256.items())),
    }
    return {
        **identity_payload,
        "experiment_id": canonical_sha256(identity_payload),
    }


def create_unique_run_directory(
    output_root: Path,
    experiment_id: str,
    *,
    now: datetime | None = None,
) -> tuple[str, Path]:
    """Create an exclusive run directory; an existing ID is never overwritten."""
    timestamp = now or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    timestamp = timestamp.astimezone(UTC)
    run_id = f"{timestamp.strftime('%Y%m%dT%H%M%S.%fZ')}-{experiment_id[:12]}"
    run_directory = Path(output_root) / run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    return run_id, run_directory
