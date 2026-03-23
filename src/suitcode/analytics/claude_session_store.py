from __future__ import annotations

import json
from pathlib import Path


class ClaudeSessionStore:
    def __init__(self, projects_root: Path | None = None) -> None:
        self._projects_root = (projects_root or (Path.home() / '.claude' / 'projects')).expanduser().resolve()
        self._session_index_cache: dict[str, dict[str, object]] | None = None

    @property
    def projects_root(self) -> Path:
        return self._projects_root

    def candidate_sessions(self) -> tuple[Path, ...]:
        if not self._projects_root.exists():
            return ()
        return tuple(
            sorted(
                (
                    path for path in self._projects_root.rglob('*.jsonl')
                    if path.name != 'history.jsonl' and 'tool-results' not in {part.lower() for part in path.parts}
                ),
                key=lambda item: (item.stat().st_mtime_ns, item.as_posix()),
                reverse=True,
            )
        )

    def list_sessions(self, repository_root: Path | None = None, session_id: str | None = None) -> tuple[Path, ...]:
        normalized_root = repository_root.expanduser().resolve() if repository_root is not None else None
        normalized_session_id = session_id.strip() if session_id is not None else None
        if normalized_session_id == '':
            raise ValueError('session_id must not be empty when provided')
        matches: list[Path] = []
        for path in self.candidate_sessions():
            meta = self.session_meta(path)
            if normalized_session_id is not None and meta['session_id'] != normalized_session_id:
                continue
            if normalized_root is not None:
                cwd = meta['cwd']
                if cwd is None or cwd != normalized_root:
                    continue
            matches.append(path)
        return tuple(matches)

    def latest_session(self, repository_root: Path | None = None) -> Path | None:
        sessions = self.list_sessions(repository_root=repository_root)
        return sessions[0] if sessions else None

    def session_meta(self, path: Path) -> dict[str, object]:
        artifact_path = path.expanduser().resolve()
        session_id: str | None = None
        cwd: Path | None = None
        with artifact_path.open('r', encoding='utf-8') as handle:
            for raw_line in handle:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                if not isinstance(payload, dict):
                    continue
                raw_session_id = payload.get('sessionId')
                if isinstance(raw_session_id, str) and raw_session_id.strip():
                    session_id = raw_session_id.strip()
                raw_cwd = payload.get('cwd')
                if isinstance(raw_cwd, str) and raw_cwd.strip():
                    cwd = Path(raw_cwd).expanduser().resolve()
                if session_id is not None and cwd is not None:
                    break
        if session_id is None:
            session_id = artifact_path.stem
        if cwd is None:
            index_entry = self._session_index().get(session_id)
            if index_entry is not None:
                project_path = index_entry.get('projectPath')
                if isinstance(project_path, str) and project_path.strip():
                    cwd = Path(project_path).expanduser().resolve()
        return {'session_id': session_id, 'cwd': cwd}

    def _session_index(self) -> dict[str, dict[str, object]]:
        if self._session_index_cache is not None:
            return self._session_index_cache
        entries: dict[str, dict[str, object]] = {}
        for path in self._projects_root.rglob('sessions-index.json'):
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            raw_entries = payload.get('entries')
            if not isinstance(raw_entries, list):
                continue
            for item in raw_entries:
                if not isinstance(item, dict):
                    continue
                session_id = item.get('sessionId')
                if isinstance(session_id, str) and session_id.strip() and session_id not in entries:
                    entries[session_id] = item
        self._session_index_cache = entries
        return entries
