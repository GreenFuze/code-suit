from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

from suitcode.runtime.errors import CoordinatorElectionError
from suitcode.runtime.paths import bootstrap_lock_path_for_project, project_hash

if os.name == "nt":
    import ctypes
    from ctypes import wintypes
else:
    import fcntl


_LOCK_POLL_INTERVAL_SECONDS = 0.1

if os.name == "nt":
    _WAIT_OBJECT_0 = 0x00000000
    _WAIT_ABANDONED = 0x00000080
    _WAIT_TIMEOUT = 0x00000102
    _WAIT_FAILED = 0xFFFFFFFF
    _INFINITE = 0xFFFFFFFF

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _create_mutex = _kernel32.CreateMutexW
    _create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _create_mutex.restype = wintypes.HANDLE

    _wait_for_single_object = _kernel32.WaitForSingleObject
    _wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _wait_for_single_object.restype = wintypes.DWORD

    _release_mutex = _kernel32.ReleaseMutex
    _release_mutex.argtypes = [wintypes.HANDLE]
    _release_mutex.restype = wintypes.BOOL

    _close_handle = _kernel32.CloseHandle
    _close_handle.argtypes = [wintypes.HANDLE]
    _close_handle.restype = wintypes.BOOL


def _mutex_name_for_project(project_root: Path) -> str:
    return f"Local\\SuitCode-{project_hash(project_root)}"


@contextmanager
def project_lock(project_root: Path, instance_id: str, timeout_seconds: float = 15.0):  # noqa: ARG001
    normalized_root = project_root.expanduser().resolve()
    if os.name == "nt":
        with _windows_project_lock(normalized_root, timeout_seconds):
            yield
        return
    with _posix_project_lock(normalized_root, timeout_seconds):
        yield


@contextmanager
def _windows_project_lock(project_root: Path, timeout_seconds: float):
    mutex_name = _mutex_name_for_project(project_root)
    handle = _create_mutex(None, False, mutex_name)
    if not handle:
        raise CoordinatorElectionError(f"failed to create project mutex `{mutex_name}`")

    acquired = False
    wait_ms = _INFINITE if timeout_seconds <= 0 else max(1, int(timeout_seconds * 1000))
    try:
        result = _wait_for_single_object(handle, wait_ms)
        if result in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
            acquired = True
            yield
            return
        if result == _WAIT_TIMEOUT:
            raise CoordinatorElectionError(f"timed out acquiring project mutex `{mutex_name}`")
        if result == _WAIT_FAILED:
            raise CoordinatorElectionError(f"failed while waiting for project mutex `{mutex_name}`")
        raise CoordinatorElectionError(f"unexpected result acquiring project mutex `{mutex_name}`: {result}")
    finally:
        if acquired:
            _release_mutex(handle)
        _close_handle(handle)


@contextmanager
def _posix_project_lock(project_root: Path, timeout_seconds: float):
    lock_path = bootstrap_lock_path_for_project(project_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    deadline = None if timeout_seconds <= 0 else time.time() + timeout_seconds
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if deadline is not None and time.time() >= deadline:
                    raise CoordinatorElectionError(f"timed out acquiring project lock `{lock_path}`")
                time.sleep(_LOCK_POLL_INTERVAL_SECONDS)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
