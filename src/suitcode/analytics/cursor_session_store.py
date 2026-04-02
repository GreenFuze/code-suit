from __future__ import annotations

import re
from pathlib import Path

from suitcode.analytics.repository_scope import repository_roots_overlap


class CursorSessionStore:
    _WORKSPACE_PATTERN = re.compile(r'workspacePath=(.+)$')

    def __init__(self, projects_root: Path | None = None) -> None:
        self._projects_root = (projects_root or (Path.home() / '.cursor' / 'projects')).expanduser().resolve()
        self._candidate_sessions_cache: tuple[Path, ...] | None = None
        self._session_meta_cache: dict[Path, dict[str, object]] = {}
        self._worker_log_cache: dict[Path, Path | None] = {}

    @property
    def projects_root(self) -> Path:
        return self._projects_root

    def candidate_sessions(self) -> tuple[Path, ...]:
        if not self._projects_root.exists():
            return ()
        if self._candidate_sessions_cache is None:
            self._candidate_sessions_cache = tuple(
                sorted(
                    self._projects_root.glob('*/agent-transcripts/**/*.jsonl'),
                    key=lambda item: (item.stat().st_mtime_ns, item.as_posix()),
                    reverse=True,
                )
            )
        return self._candidate_sessions_cache

    def list_sessions(self, repository_root: Path | None = None, session_id: str | None = None) -> tuple[Path, ...]:
        normalized_root = repository_root.expanduser().resolve() if repository_root is not None else None
        normalized_session_id = session_id.strip() if session_id is not None else None
        if normalized_session_id == '':
            raise ValueError('session_id must not be empty when provided')
        matches: list[Path] = []
        for path in self.candidate_sessions():
            if 'agent-transcripts' not in {part.lower() for part in path.parts}:
                continue
            meta = self.session_meta(path)
            if normalized_session_id is not None and meta['session_id'] != normalized_session_id:
                continue
            if normalized_root is not None:
                cwd = meta['cwd']
                if not repository_roots_overlap(normalized_root, cwd):
                    continue
            matches.append(path)
        return tuple(matches)

    def latest_session(self, repository_root: Path | None = None) -> Path | None:
        sessions = self.list_sessions(repository_root=repository_root)
        return sessions[0] if sessions else None

    def session_meta(self, path: Path) -> dict[str, object]:
        artifact_path = path.expanduser().resolve()
        cached = self._session_meta_cache.get(artifact_path)
        if cached is not None:
            return cached
        agent_transcripts_index = self._agent_transcripts_index(artifact_path)
        if agent_transcripts_index is None:
            raise ValueError(f'unsupported Cursor transcript path: `{artifact_path}`')
        session_id = artifact_path.stem
        project_root = Path(*artifact_path.parts[:agent_transcripts_index])
        cwd = self._workspace_path_from_worker_log(project_root / 'worker.log')
        meta = {'session_id': session_id, 'cwd': cwd}
        self._session_meta_cache[artifact_path] = meta
        return meta

    @staticmethod
    def _agent_transcripts_index(path: Path) -> int | None:
        for index, part in enumerate(path.parts):
            if part.lower() == 'agent-transcripts':
                return index
        return None

    def _workspace_path_from_worker_log(self, worker_log: Path) -> Path | None:
        cached = self._worker_log_cache.get(worker_log)
        if cached is not None or worker_log in self._worker_log_cache:
            return cached
        if not worker_log.exists():
            self._worker_log_cache[worker_log] = None
            return None
        for raw_line in worker_log.read_text(encoding='utf-8', errors='replace').splitlines():
            match = self._WORKSPACE_PATTERN.search(raw_line)
            if match is None:
                continue
            candidate = match.group(1).strip()
            if candidate:
                resolved = Path(candidate).expanduser().resolve()
                self._worker_log_cache[worker_log] = resolved
                return resolved
        self._worker_log_cache[worker_log] = None
        return None
