from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from suitcode.analytics.benchmark import BenchmarkHarness, SuitCodeBenchmarkAdapter
from suitcode.analytics.recorder import ToolCallRecorder
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore


class _FakeService:
    def __init__(self, analytics_root: Path, *, build_success: bool = True) -> None:
        self.build_success = build_success
        self.opened_paths: list[str] = []
        self._current_repository_root: Path | None = None
        settings = AnalyticsSettings(global_root=analytics_root, repo_subdir=".suit/analytics", max_file_bytes=10 * 1024)
        self.analytics_recorder = ToolCallRecorder(JsonlAnalyticsStore(settings), session_id="session:test")

    def resolve_analytics_repository_root(self, arguments: dict[str, object]) -> Path | None:
        workspace_id = arguments.get("workspace_id")
        repository_id = arguments.get("repository_id")
        if isinstance(workspace_id, str) and isinstance(repository_id, str):
            return self._current_repository_root
        return None

    def open_workspace(self, repository_path: str):
        self.opened_paths.append(repository_path)
        self._current_repository_root = Path(repository_path).resolve()
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
            provenance=(
                {
                    "confidence_mode": "authoritative",
                    "source_kind": "manifest",
                },
            ),
        )

    @staticmethod
    def describe_components(workspace_id: str, repository_id: str, component_ids: tuple[str, ...], **kwargs):
        return (
            SimpleNamespace(
                id=component_ids[0],
                provenance=(
                    {
                        "confidence_mode": "derived",
                        "source_kind": "ownership",
                    },
                ),
            ),
        )

    @staticmethod
    def analyze_change(workspace_id: str, repository_id: str, **kwargs):
        return SimpleNamespace(
            target_kind="file",
            related_tests=tuple(),
            provenance=(
                {
                    "confidence_mode": "heuristic",
                    "source_kind": "heuristic",
                },
            ),
        )

    @staticmethod
    def list_tests(workspace_id: str, repository_id: str, limit: int = 200, offset: int = 0):
        return SimpleNamespace(items=(SimpleNamespace(id="test:test"),))

    @staticmethod
    def describe_test_target(workspace_id: str, repository_id: str, test_id: str):
        return SimpleNamespace(
            id=test_id,
            provenance=(
                {
                    "confidence_mode": "authoritative",
                    "source_kind": "test_tool",
                },
            ),
        )

    @staticmethod
    def run_test_targets(workspace_id: str, repository_id: str, test_ids: tuple[str, ...], timeout_seconds: int = 120):
        return SimpleNamespace(
            passed=1,
            failed=0,
            errors=0,
            timeouts=0,
            results=(
                SimpleNamespace(
                    test_id=test_ids[0],
                    provenance=(
                        {
                            "confidence_mode": "authoritative",
                            "source_kind": "test_tool",
                        },
                    ),
                ),
            ),
        )

    @staticmethod
    def list_build_targets(workspace_id: str, repository_id: str, limit: int = 200, offset: int = 0):
        return SimpleNamespace(items=(SimpleNamespace(action_id="action:test"),))

    @staticmethod
    def describe_build_target(workspace_id: str, repository_id: str, action_id: str):
        return SimpleNamespace(
            action_id=action_id,
            provenance=(
                {
                    "confidence_mode": "authoritative",
                    "source_kind": "manifest",
                },
            ),
        )

    def build_target(self, workspace_id: str, repository_id: str, action_id: str, timeout_seconds: int = 300):
        status = "passed" if self.build_success else "failed"
        return SimpleNamespace(
            success=self.build_success,
            status=status,
            exit_code=(0 if self.build_success else 1),
            provenance=(
                {
                    "confidence_mode": "derived",
                    "source_kind": "quality_tool",
                },
            ),
        )

    @staticmethod
    def get_truth_coverage(workspace_id: str, repository_id: str):
        return SimpleNamespace(
            scope_kind="repository",
            scope_id=repository_id,
            domains=(
                SimpleNamespace(
                    domain="architecture",
                    total_entities=1,
                    authoritative_count=1,
                    derived_count=0,
                    heuristic_count=0,
                    unavailable_count=0,
                    availability="available",
                    degraded_reason=None,
                    source_kind_mix={"manifest": 1},
                    source_tool_mix={},
                    execution_available=None,
                    action_capabilities={},
                ),
                SimpleNamespace(
                    domain="code",
                    total_entities=1,
                    authoritative_count=1,
                    derived_count=0,
                    heuristic_count=0,
                    unavailable_count=0,
                    availability="available",
                    degraded_reason=None,
                    source_kind_mix={"lsp": 1},
                    source_tool_mix={"basedpyright": 1},
                    execution_available=None,
                    action_capabilities={},
                ),
                SimpleNamespace(
                    domain="tests",
                    total_entities=1,
                    authoritative_count=1,
                    derived_count=0,
                    heuristic_count=0,
                    unavailable_count=0,
                    availability="available",
                    degraded_reason=None,
                    source_kind_mix={"test_tool": 1},
                    source_tool_mix={},
                    execution_available=None,
                    action_capabilities={},
                ),
                SimpleNamespace(
                    domain="quality",
                    total_entities=1,
                    authoritative_count=1,
                    derived_count=0,
                    heuristic_count=0,
                    unavailable_count=0,
                    availability="available",
                    degraded_reason=None,
                    source_kind_mix={"quality_tool": 1},
                    source_tool_mix={},
                    execution_available=True,
                    action_capabilities={},
                ),
                SimpleNamespace(
                    domain="actions",
                    total_entities=1,
                    authoritative_count=1,
                    derived_count=0,
                    heuristic_count=0,
                    unavailable_count=0,
                    availability="available",
                    degraded_reason=None,
                    source_kind_mix={"manifest": 1},
                    source_tool_mix={},
                    execution_available=True,
                    action_capabilities={"tests": True, "builds": True, "runners": True},
                ),
            ),
            overall_authoritative_count=5,
            overall_derived_count=0,
            overall_heuristic_count=0,
            overall_unavailable_count=0,
            overall_availability="available",
            provenance=(
                {
                    "confidence_mode": "derived",
                    "source_kind": "manifest",
                    "evidence_summary": "truth coverage summary",
                    "evidence_paths": [],
                },
            ),
        )


def test_benchmark_harness_validates_required_task_fields(tmp_path: Path) -> None:
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text('[{"task_id": "a"}]', encoding="utf-8")

    harness = BenchmarkHarness(tmp_path)
    try:
        harness.load_tasks(tasks_file)
        assert False, "expected ValueError for missing repository_path/workflow"
    except ValueError as exc:
        assert "repository_path" in str(exc)


def test_benchmark_adapter_runs_orientation_workflow_with_telemetry(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    service = _FakeService(tmp_path / "analytics")
    adapter = SuitCodeBenchmarkAdapter(service_factory=lambda: service, working_directory=tmp_path)
    task_run = adapter.run_task(
        {
            "task_id": "orientation-1",
            "repository_path": ".",
            "workflow": "orientation",
        },
        run_id="benchmark-test",
        task_artifact_path=tmp_path / "benchmarks" / "benchmark-test" / "tasks" / "orientation-1.json",
    )
    result = task_run.result

    assert result.status == "passed"
    assert result.tool_calls >= 3
    assert result.turn_count == result.tool_calls
    assert result.session_id == "session:test"
    assert result.first_high_value_tool == "get_truth_coverage"
    assert result.first_high_value_tool_call_index == 2
    assert result.used_high_value_tool_early is True
    assert result.provenance_confidence_mix["authoritative"] >= 1
    assert result.provenance_confidence_mix["derived"] >= 1
    assert result.artifact_references[0].kind == "benchmark_task_metadata"
    assert service.opened_paths
    assert task_run.metadata["event_ids"]


def test_benchmark_adapter_reports_failed_build_workflow(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    service = _FakeService(tmp_path / "analytics", build_success=False)
    adapter = SuitCodeBenchmarkAdapter(service_factory=lambda: service, working_directory=tmp_path)
    result = adapter.run_task(
        {
            "task_id": "build-1",
            "repository_path": ".",
            "workflow": "build_execute",
        },
        run_id="benchmark-test",
        task_artifact_path=tmp_path / "benchmarks" / "benchmark-test" / "tasks" / "build-1.json",
    ).result

    assert result.status == "failed"
    assert result.deterministic_action_kind == "build"
    assert result.deterministic_action_target_id == "action:test"
    assert result.deterministic_action_status == "failed"
    assert "success=False" in (result.notes or "")


def test_benchmark_adapter_fails_change_workflow_with_ambiguous_selector(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    service = _FakeService(tmp_path / "analytics")
    adapter = SuitCodeBenchmarkAdapter(service_factory=lambda: service, working_directory=tmp_path)
    result = adapter.run_task(
        {
            "task_id": "change-1",
            "repository_path": ".",
            "workflow": "change_impact",
            "repository_rel_path": "a.py",
            "owner_id": "component:x",
        },
        run_id="benchmark-test",
        task_artifact_path=tmp_path / "benchmarks" / "benchmark-test" / "tasks" / "change-1.json",
    ).result

    assert result.status == "error"
    assert "exactly one selector" in (result.notes or "")
    assert result.first_high_value_tool == "get_truth_coverage"


def test_benchmark_adapter_keeps_supported_nested_fixture_path(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    fixture = tmp_path / "tests" / "test_repos" / "npm"
    fixture.mkdir(parents=True)
    (fixture / "package.json").write_text(
        '{"name":"fixture","private":true,"workspaces":["packages/*"]}',
        encoding="utf-8",
    )
    package_dir = fixture / "packages" / "app"
    package_dir.mkdir(parents=True)
    (package_dir / "package.json").write_text(
        '{"name":"@fixture/app","version":"1.0.0","scripts":{"test":"jest"}}',
        encoding="utf-8",
    )

    service = _FakeService(tmp_path / "analytics")
    adapter = SuitCodeBenchmarkAdapter(service_factory=lambda: service, working_directory=tmp_path)
    result = adapter.run_task(
        {
            "task_id": "fixture-orientation",
            "repository_path": str(fixture),
            "workflow": "orientation",
        },
        run_id="benchmark-test",
        task_artifact_path=tmp_path / "benchmarks" / "benchmark-test" / "tasks" / "fixture-orientation.json",
    ).result

    assert result.status == "passed"
    assert len(service.opened_paths) == 1
    assert Path(service.opened_paths[0]) == fixture.resolve()


def test_benchmark_harness_writes_report_directory_and_task_metadata(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    tasks = (
        {
            "task_id": "orientation-1",
            "repository_path": ".",
            "workflow": "orientation",
        },
    )
    harness = BenchmarkHarness(tmp_path / "analytics")
    adapter = SuitCodeBenchmarkAdapter(
        service_factory=lambda: _FakeService(tmp_path / "analytics"),
        working_directory=tmp_path,
    )

    report = harness.run(adapter, tasks)

    report_path = tmp_path / "analytics" / "benchmarks" / report.report_id / "report.json"
    task_path = tmp_path / "analytics" / "benchmarks" / report.report_id / "tasks" / "orientation-1.json"
    assert report_path.exists()
    assert task_path.exists()
    assert report.high_value_tool_usage_rate == 1.0
    assert report.high_value_tool_early_rate == 1.0
    assert report.authoritative_provenance_rate > 0.0
    assert report.truth_coverage is not None
