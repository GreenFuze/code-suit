from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from suitcode.runtime.models import DiscoveryRecord

_DISCOVERY_IO_RETRIES = 12
_DISCOVERY_IO_RETRY_DELAY_SECONDS = 0.05


@dataclass(frozen=True)
class CoordinatorDiscoveryStore:
    path: Path
    retries: int = _DISCOVERY_IO_RETRIES
    retry_delay_seconds: float = _DISCOVERY_IO_RETRY_DELAY_SECONDS

    def read(self) -> DiscoveryRecord | None:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                return self._read_once()
            except (FileNotFoundError, PermissionError, ValidationError, json.JSONDecodeError) as exc:
                last_error = exc
                if isinstance(exc, FileNotFoundError):
                    return None
                if attempt == self.retries - 1:
                    raise
                time.sleep(self.retry_delay_seconds)
        if last_error is not None:
            raise last_error
        return None

    def write(self, record: DiscoveryRecord) -> None:
        payload = record.model_dump_json(indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(self.retries):
            try:
                self._write_once(payload)
                return
            except PermissionError:
                if attempt == self.retries - 1:
                    raise
                time.sleep(self.retry_delay_seconds)

    def remove_if_owned(self, instance_id: str) -> None:
        try:
            current = self.read()
        except (FileNotFoundError, PermissionError, ValidationError, json.JSONDecodeError):
            current = None
        if current is None or current.instance_id != instance_id:
            return
        for attempt in range(self.retries):
            try:
                self.path.unlink(missing_ok=True)
                return
            except PermissionError:
                if attempt == self.retries - 1:
                    return
                time.sleep(self.retry_delay_seconds)

    def _read_once(self) -> DiscoveryRecord | None:
        if not self.path.exists():
            return None
        raw = self.path.read_text(encoding="utf-8")
        if not raw.strip():
            raise json.JSONDecodeError("discovery file is empty", raw, 0)
        return DiscoveryRecord.model_validate_json(raw)

    def _write_once(self, payload: str) -> None:
        with self.path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())


def read_discovery(path: Path) -> DiscoveryRecord | None:
    return CoordinatorDiscoveryStore(path).read()


def write_discovery(path: Path, record: DiscoveryRecord) -> None:
    CoordinatorDiscoveryStore(path).write(record)


def remove_discovery_if_owned(path: Path, instance_id: str) -> None:
    CoordinatorDiscoveryStore(path).remove_if_owned(instance_id)
