from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from suitcode.analytics.benchmark import BenchmarkHarness, SuitCodeBenchmarkAdapter


class _FakeService:
    def __init__(self, *, build_success: bool = True) -> None:
        self.build_success = build_success
        self.opened_paths: list[str] = []

    def open_workspace(self, repository_path: str):
        self.opened_paths.append(repository_path)
        return SimpleNamespace(
            workspace=SimpleNamespace(workspace_id="workspace:test"),
            initial_repository=SimpleNamespace(repository_id="repo:test"),
        )

    @staticmethod
    def repository_summary(workspace_id: str, repository_id: str, preview_limit: int = 10):
        return SimpleNamespace(
            component_ids_preview=("component:test",),
            component_count=1,
            test_count=1,
        )

    @staticmethod
    def describe_components(workspace_id: str, repository_id: str, component_ids: tuple[str, ...], **kwargs):
        return tuple()

    @staticmethod
    def analyze_change(workspace_id: str, repository_id: str, **kwargs):
        return SimpleNamespace(target_kind="file", related_tests=tuple())

    @staticmethod
    def list_tests(workspace_id: str, repository_id: str, limit: int = 200, offset: int = 0):
        return SimpleNamespace(items=(SimpleNamespace(id="test:test"),))

    @staticmethod
    def describe_test_target(workspace_id: str, repository_id: str, test_id: str):
        return SimpleNamespace(id=test_id)

    @staticmethod
    def run_test_targets(workspace_id: str, repository_id: str, test_ids: tuple[str, ...], timeout_seconds: int = 120):
        return SimpleNamespace(passed=1, failed=0, errors=0, timeouts=0)

    @staticmethod
    def list_build_targets(workspace_id: str, repository_id: str, limit: int = 200, offset: int = 0):
        return SimpleNamespace(items=(SimpleNamespace(action_id="action:test"),))

    @staticmethod
    def describe_build_target(workspace_id: str, repository_id: str, action_id: str):
        return SimpleNamespace(action_id=action_id)

    def build_target(self, workspace_id: str, repository_id: str, action_id: str, timeout_seconds: int = 300):
        status = "passed" if self.build_success else "failed"
        return SimpleNamespace(success=self.build_success, status=status, exit_code=(0 if self.build_success else 1))


def test_benchmark_harness_validates_required_task_fields(tmp_path: Path) -> None:
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text('[{"task_id": "a"}]', encoding="utf-8")

    harness = BenchmarkHarness(tmp_path)
    try:
        harness.load_tasks(tasks_file)
        assert False, "expected ValueError for missing repository_path/workflow"
    except ValueError as exc:
        assert "repository_path" in str(exc)


def test_benchmark_adapter_runs_orientation_workflow(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    service = _FakeService()
    adapter = SuitCodeBenchmarkAdapter(service_factory=lambda: service, working_directory=tmp_path)
    result = adapter.run_task(
        {
            "task_id": "orientation-1",
            "repository_path": ".",
            "workflow": "orientation",
        }
    )

    assert result.status == "passed"
    assert result.tool_calls >= 3
    assert service.opened_paths


def test_benchmark_adapter_reports_failed_build_workflow(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    service = _FakeService(build_success=False)
    adapter = SuitCodeBenchmarkAdapter(service_factory=lambda: service, working_directory=tmp_path)
    result = adapter.run_task(
        {
            "task_id": "build-1",
            "repository_path": ".",
            "workflow": "build_execute",
        }
    )

    assert result.status == "failed"
    assert "success=False" in (result.notes or "")


def test_benchmark_adapter_fails_change_workflow_with_ambiguous_selector(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    service = _FakeService()
    adapter = SuitCodeBenchmarkAdapter(service_factory=lambda: service, working_directory=tmp_path)
    result = adapter.run_task(
        {
            "task_id": "change-1",
            "repository_path": ".",
            "workflow": "change_impact",
            "repository_rel_path": "a.py",
            "owner_id": "component:x",
        }
    )

    assert result.status == "error"
    assert "exactly one selector" in (result.notes or "")


def test_benchmark_adapter_isolates_fixture_path_inside_parent_repo(tmp_path: Path) -> None:
    # Parent repository root
    (tmp_path / ".git").mkdir()
    fixture = tmp_path / "tests" / "test_repos" / "npm"
    fixture.mkdir(parents=True)
    (fixture / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")

    service = _FakeService()
    adapter = SuitCodeBenchmarkAdapter(service_factory=lambda: service, working_directory=tmp_path)
    result = adapter.run_task(
        {
            "task_id": "fixture-orientation",
            "repository_path": str(fixture),
            "workflow": "orientation",
        }
    )

    assert result.status == "passed"
    assert len(service.opened_paths) == 1
    assert Path(service.opened_paths[0]) != fixture.resolve()
