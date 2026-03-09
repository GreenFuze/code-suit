from __future__ import annotations

from pathlib import Path

from suitcode.analytics.codex_session_store import CodexSessionStore


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "codex_sessions"


def _write_session(target: Path, fixture_name: str, repository_root: Path) -> Path:
    template = (FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template.replace("__REPO_ROOT__", repository_root.as_posix()), encoding="utf-8")
    return target


def test_store_discovers_and_filters_sessions(tmp_path: Path) -> None:
    repo_a = (tmp_path / "repo-a").resolve()
    repo_b = (tmp_path / "repo-b").resolve()
    repo_a.mkdir()
    repo_b.mkdir()
    sessions_root = tmp_path / "sessions"
    _write_session(sessions_root / "2026" / "03" / "08" / "a.jsonl", "session_with_suitcode.jsonl", repo_a)
    _write_session(sessions_root / "2026" / "03" / "09" / "b.jsonl", "session_without_suitcode.jsonl", repo_b)

    store = CodexSessionStore(sessions_root)

    all_sessions = store.list_sessions()
    repo_a_sessions = store.list_sessions(repository_root=repo_a)
    session_b = store.list_sessions(session_id="codex-session-2")

    assert len(all_sessions) == 2
    assert len(repo_a_sessions) == 1
    assert repo_a_sessions[0].name == "a.jsonl"
    assert len(session_b) == 1
    assert session_b[0].name == "b.jsonl"


def test_store_returns_latest_session_for_repository(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    repo_root.mkdir()
    sessions_root = tmp_path / "sessions"
    first = _write_session(sessions_root / "2026" / "03" / "08" / "a.jsonl", "session_with_suitcode.jsonl", repo_root)
    second = _write_session(sessions_root / "2026" / "03" / "09" / "b.jsonl", "session_without_suitcode.jsonl", repo_root)

    first.touch()
    second.touch()

    latest = CodexSessionStore(sessions_root).latest_session(repository_root=repo_root)
    assert latest == second
