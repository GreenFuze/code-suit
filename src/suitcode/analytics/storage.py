from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from suitcode.analytics.errors import AnalyticsError
from suitcode.analytics.models import AnalyticsEvent
from suitcode.analytics.settings import AnalyticsSettings


class JsonlAnalyticsStore:
    def __init__(self, settings: AnalyticsSettings) -> None:
        self._settings = settings
        self._lock = RLock()

    @property
    def settings(self) -> AnalyticsSettings:
        return self._settings

    def append_event(self, event: AnalyticsEvent, repository_root: Path | None = None) -> None:
        line = json.dumps(event.model_dump(mode="json"), sort_keys=True, ensure_ascii=True)
        with self._lock:
            self._append_line(self._global_events_root(), line)
            if repository_root is not None:
                self._append_line(self._repository_events_root(repository_root), line)

    def load_events(self, repository_root: Path | None = None, include_global: bool = True) -> tuple[AnalyticsEvent, ...]:
        roots: list[Path] = []
        if include_global:
            roots.append(self._global_events_root())
        if repository_root is not None:
            roots.append(self._repository_events_root(repository_root))

        events_by_id: dict[str, AnalyticsEvent] = {}
        with self._lock:
            for root in roots:
                for line in self._iter_lines(root):
                    try:
                        payload = json.loads(line)
                        event = AnalyticsEvent.model_validate(payload)
                    except Exception as exc:  # noqa: BLE001
                        raise AnalyticsError(f"invalid analytics event JSONL line in `{root}`") from exc
                    events_by_id[event.event_id] = event

        events = tuple(events_by_id.values())
        return tuple(sorted(events, key=lambda item: item.timestamp_utc))

    def global_root(self) -> Path:
        return self._settings.global_root

    def repository_root(self, repository_root: Path) -> Path:
        return repository_root.expanduser().resolve() / self._settings.repo_subdir

    def _global_events_root(self) -> Path:
        return self.global_root() / "events"

    def _repository_events_root(self, repository_root: Path) -> Path:
        return self.repository_root(repository_root) / "events"

    def _append_line(self, stream_root: Path, line: str) -> None:
        stream_root.mkdir(parents=True, exist_ok=True)
        active_file = stream_root / "active.jsonl"
        encoded = (line + "\n").encode("utf-8")
        if active_file.exists() and active_file.stat().st_size + len(encoded) > self._settings.max_file_bytes:
            self._rollover(stream_root, active_file)
        with active_file.open("ab") as handle:
            handle.write(encoded)

    def _rollover(self, stream_root: Path, active_file: Path) -> None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        archive_file = stream_root / f"events-{timestamp}.jsonl"
        counter = 1
        while archive_file.exists():
            archive_file = stream_root / f"events-{timestamp}-{counter}.jsonl"
            counter += 1
        try:
            active_file.replace(archive_file)
        except OSError as exc:
            raise AnalyticsError(f"failed to rollover analytics log `{active_file}`") from exc

    @staticmethod
    def _iter_lines(stream_root: Path):
        if not stream_root.exists():
            return []
        archive_files = sorted(item for item in stream_root.glob("events-*.jsonl") if item.is_file())
        active_file = stream_root / "active.jsonl"
        ordered = [*archive_files, *( [active_file] if active_file.exists() else [] )]
        lines: list[str] = []
        for file_path in ordered:
            for raw_line in file_path.read_text(encoding="utf-8").splitlines():
                stripped = raw_line.strip()
                if stripped:
                    lines.append(stripped)
        return lines

