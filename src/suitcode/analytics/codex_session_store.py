from __future__ import annotations

import json
from pathlib import Path


class CodexSessionStore:
    def __init__(self, sessions_root: Path | None = None) -> None:
        self._sessions_root = (sessions_root or (Path.home() / ".codex" / "sessions")).expanduser().resolve()

    @property
    def sessions_root(self) -> Path:
        return self._sessions_root

    def list_sessions(
        self,
        repository_root: Path | None = None,
        session_id: str | None = None,
    ) -> tuple[Path, ...]:
        normalized_root = repository_root.expanduser().resolve() if repository_root is not None else None
        normalized_session_id = session_id.strip() if session_id is not None else None
        if normalized_session_id == "":
            raise ValueError("session_id must not be empty when provided")
        if not self._sessions_root.exists():
            return ()

        matches: list[Path] = []
        for path in self.candidate_sessions():
            meta = self.session_meta(path)
            if normalized_session_id is not None and meta["session_id"] != normalized_session_id:
                continue
            if normalized_root is not None:
                cwd = meta["cwd"]
                if cwd is None or cwd != normalized_root:
                    continue
            matches.append(path)
        return tuple(matches)

    def latest_session(self, repository_root: Path | None = None) -> Path | None:
        sessions = self.list_sessions(repository_root=repository_root)
        return sessions[0] if sessions else None

    def candidate_sessions(self) -> tuple[Path, ...]:
        if not self._sessions_root.exists():
            return ()
        return tuple(
            sorted(
                self._sessions_root.rglob("*.jsonl"),
                key=lambda item: (item.stat().st_mtime_ns, item.as_posix()),
                reverse=True,
            )
        )

    def session_meta(self, path: Path) -> dict[str, object]:
        session_id: str | None = None
        cwd: Path | None = None
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                if payload.get("type") != "session_meta":
                    continue
                meta = payload.get("payload")
                if not isinstance(meta, dict):
                    raise ValueError(f"invalid Codex session_meta payload in `{path}`")
                raw_session_id = meta.get("id")
                if not isinstance(raw_session_id, str) or not raw_session_id.strip():
                    raise ValueError(f"invalid Codex session id in `{path}`")
                session_id = raw_session_id.strip()
                raw_cwd = meta.get("cwd")
                if raw_cwd is not None:
                    if not isinstance(raw_cwd, str) or not raw_cwd.strip():
                        raise ValueError(f"invalid Codex cwd in `{path}`")
                    cwd = Path(raw_cwd).expanduser().resolve()
                break
        if session_id is None:
            raise ValueError(f"missing Codex session_meta in `{path}`")
        return {"session_id": session_id, "cwd": cwd}
