from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
from typing import Literal
from uuid import uuid4

from pydantic import Field, field_validator

from suitcode.analytics.models import StrictModel


_TRACKED_REPOSITORIES_PATH = Path(__file__).resolve().parents[3] / "docs" / "dogfooding" / "tracked_repositories.v1.json"


class TrackedStudyRepository(StrictModel):
    label: str
    repository_root: str
    ecosystems: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    is_primary: bool = False

    @field_validator("label", "repository_root")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class TrackedStudyRepositoryCatalog(StrictModel):
    schema_version: str
    repositories: tuple[TrackedStudyRepository, ...]


class LiveStudyLaunchManifest(StrictModel):
    schema_version: str = "1.0"
    launch_id: str
    created_at: str
    tracked_repository_label: str | None = None
    repository_root: str
    analytics_run_id: str
    experiment_id: str | None = None
    experiment_label: str | None = None
    task_id: str
    task_kind: str
    study_kind: str
    model_name: str | None = None
    workspace_mode: str
    notes: str | None = None
    command: tuple[str, ...] = ()
    command_executed: bool = False


class TrackedStudyRepositoryResolver:
    def __init__(self, manifest_path: Path | None = None) -> None:
        self._manifest_path = (manifest_path or _TRACKED_REPOSITORIES_PATH).expanduser().resolve()

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    def load_catalog(self) -> TrackedStudyRepositoryCatalog:
        return TrackedStudyRepositoryCatalog.model_validate_json(self._manifest_path.read_text(encoding="utf-8"))

    def resolve(
        self,
        *,
        tracked_label: str | None,
        repository_root: str | None,
    ) -> TrackedStudyRepository:
        catalog = self.load_catalog()
        if tracked_label is not None:
            normalized = tracked_label.strip()
            for item in catalog.repositories:
                if item.label == normalized:
                    return item
            raise ValueError(f"unknown tracked repository label: `{tracked_label}`")
        if repository_root is None:
            primary = next((item for item in catalog.repositories if item.is_primary), None)
            if primary is None:
                raise ValueError("no primary tracked repository is configured")
            return primary
        root = str(Path(repository_root).expanduser().resolve())
        return TrackedStudyRepository(label=Path(root).name or "repository", repository_root=root)


class LiveStudyManifestStore:
    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._root = self._repository_root / ".suit" / "analytics" / "live-study"

    @property
    def root(self) -> Path:
        return self._root

    def write(self, manifest: LiveStudyLaunchManifest) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        timestamp = manifest.created_at.replace(":", "-").replace("+00:00", "Z")
        path = self._root / f"{timestamp}__{manifest.launch_id}.json"
        path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def load(self, path: Path) -> LiveStudyLaunchManifest:
        return LiveStudyLaunchManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def load_latest(self) -> LiveStudyLaunchManifest | None:
        if not self._root.exists():
            return None
        candidates = sorted(self._root.glob("*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True)
        if not candidates:
            return None
        return self.load(candidates[0])


class LiveStudyLauncher:
    def __init__(self, resolver: TrackedStudyRepositoryResolver | None = None) -> None:
        self._resolver = resolver or TrackedStudyRepositoryResolver()

    def prepare_launch(
        self,
        *,
        tracked_label: str | None,
        repository_root: str | None,
        task_id: str | None,
        task_kind: Literal["discovery", "planning", "implementation", "bugfix", "validation", "review"],
        study_kind: str,
        experiment_id: str | None,
        experiment_label: str | None,
        model_name: str | None,
        workspace_mode: str,
        notes: str | None,
        command: tuple[str, ...] = (),
        command_executed: bool = False,
        analytics_run_id: str | None = None,
    ) -> tuple[LiveStudyLaunchManifest, dict[str, str], Path]:
        repository = self._resolver.resolve(tracked_label=tracked_label, repository_root=repository_root)
        repo_root = Path(repository.repository_root).expanduser().resolve()
        created_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        launch_id = f"live-study-{uuid4().hex}"
        resolved_task_id = task_id or f"{task_kind}:{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        resolved_run_id = analytics_run_id or f"run:{uuid4().hex}"
        manifest = LiveStudyLaunchManifest(
            launch_id=launch_id,
            created_at=created_at,
            tracked_repository_label=repository.label,
            repository_root=str(repo_root),
            analytics_run_id=resolved_run_id,
            experiment_id=experiment_id,
            experiment_label=experiment_label,
            task_id=resolved_task_id,
            task_kind=task_kind,
            study_kind=study_kind,
            model_name=model_name,
            workspace_mode=workspace_mode,
            notes=notes,
            command=command,
            command_executed=command_executed,
        )
        env = {
            "SUITCODE_ANALYTICS_RUN_ID": resolved_run_id,
            "SUITCODE_TASK_ID": resolved_task_id,
            "SUITCODE_TASK_KIND": task_kind,
            "SUITCODE_STUDY_KIND": study_kind,
            "SUITCODE_WORKSPACE_MODE": workspace_mode,
        }
        if experiment_id:
            env["SUITCODE_ANALYTICS_EXPERIMENT_ID"] = experiment_id
        if experiment_label:
            env["SUITCODE_ANALYTICS_EXPERIMENT_LABEL"] = experiment_label
        if model_name:
            env["SUITCODE_MODEL_NAME"] = model_name
        if notes:
            env["SUITCODE_ANALYTICS_NOTES"] = notes
        store = LiveStudyManifestStore(repo_root)
        path = store.write(manifest)
        return manifest, env, path

    @staticmethod
    def launch_command(
        *,
        repository_root: Path,
        command: tuple[str, ...],
        env_overrides: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(command),
            cwd=repository_root,
            env={**os.environ, **env_overrides},
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
