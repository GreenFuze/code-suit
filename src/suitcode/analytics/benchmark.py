from __future__ import annotations

import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Callable, Protocol
from uuid import uuid4

from suitcode.analytics.models import BenchmarkReport, BenchmarkTaskResult


class BenchmarkAdapter(Protocol):
    @property
    def name(self) -> str:
        ...

    def run_task(self, task: dict[str, object]) -> BenchmarkTaskResult:
        ...


class BenchmarkHarness:
    def __init__(self, benchmark_root: Path) -> None:
        self._benchmark_root = benchmark_root

    def load_tasks(self, tasks_file: Path) -> tuple[dict[str, object], ...]:
        payload = json.loads(tasks_file.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("benchmark tasks file must contain a JSON list")
        tasks: list[dict[str, object]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("each benchmark task must be an object")
            task_id = item.get("task_id")
            repository_path = item.get("repository_path")
            workflow = item.get("workflow")
            if not isinstance(task_id, str) or not task_id.strip():
                raise ValueError("benchmark task missing non-empty `task_id`")
            if not isinstance(repository_path, str) or not repository_path.strip():
                raise ValueError(f"benchmark task `{task_id}` missing non-empty `repository_path`")
            if not isinstance(workflow, str) or not workflow.strip():
                raise ValueError(f"benchmark task `{task_id}` missing non-empty `workflow`")
            tasks.append(item)
        return tuple(tasks)

    def run(self, adapter: BenchmarkAdapter, tasks: tuple[dict[str, object], ...]) -> BenchmarkReport:
        results = tuple(adapter.run_task(task) for task in tasks)
        passed = sum(1 for item in results if item.status == "passed")
        failed = sum(1 for item in results if item.status == "failed")
        errored = sum(1 for item in results if item.status == "error")
        avg_tool_calls = (sum(item.tool_calls for item in results) / len(results)) if results else 0.0
        avg_duration = (sum(item.duration_ms for item in results) / len(results)) if results else 0.0
        report = BenchmarkReport(
            report_id=f"benchmark:{uuid4().hex}",
            generated_at_utc=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            adapter_name=adapter.name,
            task_total=len(results),
            task_passed=passed,
            task_failed=failed,
            task_error=errored,
            avg_tool_calls=avg_tool_calls,
            avg_duration_ms=avg_duration,
            tasks=results,
        )
        self.write_report(report)
        return report

    def write_report(self, report: BenchmarkReport) -> Path:
        benchmark_dir = self._benchmark_root / "benchmarks"
        benchmark_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        output_file = benchmark_dir / f"report-{timestamp}.json"
        output_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return output_file


class SuitCodeBenchmarkAdapter:
    name = "suitcode-mcp-deterministic"

    def __init__(
        self,
        service_factory: Callable[[], object] | None = None,
        *,
        working_directory: Path | None = None,
    ) -> None:
        self._service_factory = service_factory or self._default_service_factory
        self._working_directory = (working_directory or Path.cwd()).expanduser().resolve()

    def run_task(self, task: dict[str, object]) -> BenchmarkTaskResult:
        task_id = _required_string(task, "task_id")
        temp_roots: list[Path] = []
        start = perf_counter()
        tool_calls = 0
        try:
            repository_path = self._prepare_repository_path(task, temp_roots=temp_roots)
            workflow = _required_string(task, "workflow")
            timeout_seconds = _optional_positive_int(task.get("timeout_seconds"), default=120)
            service = self._service_factory()

            def _call(method_name: str, *args, **kwargs):
                nonlocal tool_calls
                tool_calls += 1
                method = getattr(service, method_name, None)
                if method is None or not callable(method):
                    raise ValueError(f"benchmark service does not expose `{method_name}`")
                return method(*args, **kwargs)

            opened = _call("open_workspace", str(repository_path))
            workspace_id = opened.workspace.workspace_id
            repository_id = opened.initial_repository.repository_id

            if workflow == "orientation":
                note = self._run_orientation_workflow(
                    _call,
                    workspace_id=workspace_id,
                    repository_id=repository_id,
                    preview_limit=_optional_positive_int(task.get("preview_limit"), default=10),
                )
                status = "passed"
            elif workflow == "change_impact":
                note = self._run_change_impact_workflow(
                    _call,
                    task=task,
                    workspace_id=workspace_id,
                    repository_id=repository_id,
                )
                status = "passed"
            elif workflow == "test_execute":
                status, note = self._run_test_execute_workflow(
                    _call,
                    task=task,
                    workspace_id=workspace_id,
                    repository_id=repository_id,
                    timeout_seconds=timeout_seconds,
                )
            elif workflow == "build_execute":
                status, note = self._run_build_execute_workflow(
                    _call,
                    task=task,
                    workspace_id=workspace_id,
                    repository_id=repository_id,
                    timeout_seconds=timeout_seconds,
                )
            else:
                raise ValueError(
                    f"unsupported benchmark workflow `{workflow}`; expected one of "
                    "`orientation`, `change_impact`, `test_execute`, `build_execute`"
                )
        except Exception as exc:  # noqa: BLE001
            status = "error"
            note = f"{exc.__class__.__name__}: {exc}"
        finally:
            for temp_root in temp_roots:
                shutil.rmtree(temp_root, ignore_errors=True)

        duration_ms = int((perf_counter() - start) * 1000)
        return BenchmarkTaskResult(
            task_id=task_id,
            status=status,
            tool_calls=tool_calls,
            duration_ms=duration_ms,
            notes=note,
        )

    @staticmethod
    def _default_service_factory() -> object:
        from suitcode.mcp.service import SuitMcpService
        from suitcode.mcp.state import WorkspaceRegistry

        return SuitMcpService(registry=WorkspaceRegistry())

    def _run_orientation_workflow(
        self,
        call: Callable[..., object],
        *,
        workspace_id: str,
        repository_id: str,
        preview_limit: int,
    ) -> str:
        summary = call(
            "repository_summary",
            workspace_id,
            repository_id,
            preview_limit=preview_limit,
        )
        component_ids = tuple(summary.component_ids_preview)  # type: ignore[attr-defined]
        if not component_ids:
            listed = call(
                "list_components",
                workspace_id,
                repository_id,
                limit=1,
                offset=0,
            )
            component_ids = tuple(item.id for item in listed.items)  # type: ignore[attr-defined]
        if component_ids:
            call(
                "describe_components",
                workspace_id,
                repository_id,
                component_ids=(component_ids[0],),
                file_preview_limit=10,
                dependency_preview_limit=10,
                dependent_preview_limit=10,
                test_preview_limit=5,
            )
        return (
            f"orientation complete; components={summary.component_count}, tests={summary.test_count}"  # type: ignore[attr-defined]
        )

    @staticmethod
    def _run_change_impact_workflow(
        call: Callable[..., object],
        *,
        task: dict[str, object],
        workspace_id: str,
        repository_id: str,
    ) -> str:
        symbol_id = _optional_string(task.get("symbol_id"))
        repository_rel_path = _optional_string(task.get("repository_rel_path"))
        owner_id = _optional_string(task.get("owner_id"))
        selector_count = sum(1 for item in (symbol_id, repository_rel_path, owner_id) if item is not None)
        if selector_count != 1:
            raise ValueError(
                "change_impact workflow requires exactly one selector: `symbol_id`, `repository_rel_path`, or `owner_id`"
            )
        impact = call(
            "analyze_change",
            workspace_id,
            repository_id,
            symbol_id=symbol_id,
            repository_rel_path=repository_rel_path,
            owner_id=owner_id,
        )
        return (
            f"change impact complete; target_kind={impact.target_kind}, related_tests={len(impact.related_tests)}"  # type: ignore[attr-defined]
        )

    @staticmethod
    def _run_test_execute_workflow(
        call: Callable[..., object],
        *,
        task: dict[str, object],
        workspace_id: str,
        repository_id: str,
        timeout_seconds: int,
    ) -> tuple[str, str]:
        tests = call(
            "list_tests",
            workspace_id,
            repository_id,
            limit=200,
            offset=0,
        )
        explicit_test_id = _optional_string(task.get("test_id"))
        if explicit_test_id is not None:
            test_id = explicit_test_id
        elif tests.items:  # type: ignore[attr-defined]
            test_id = tests.items[0].id  # type: ignore[attr-defined]
        else:
            raise ValueError("test_execute workflow could not find any discovered tests")
        call("describe_test_target", workspace_id, repository_id, test_id=test_id)
        run = call(
            "run_test_targets",
            workspace_id,
            repository_id,
            test_ids=(test_id,),
            timeout_seconds=timeout_seconds,
        )
        status = "passed" if (run.failed == 0 and run.errors == 0 and run.timeouts == 0) else "failed"  # type: ignore[attr-defined]
        note = (
            f"test_id={test_id}, passed={run.passed}, failed={run.failed}, "  # type: ignore[attr-defined]
            f"errors={run.errors}, timeouts={run.timeouts}"  # type: ignore[attr-defined]
        )
        return status, note

    @staticmethod
    def _run_build_execute_workflow(
        call: Callable[..., object],
        *,
        task: dict[str, object],
        workspace_id: str,
        repository_id: str,
        timeout_seconds: int,
    ) -> tuple[str, str]:
        build_targets = call(
            "list_build_targets",
            workspace_id,
            repository_id,
            limit=200,
            offset=0,
        )
        explicit_action_id = _optional_string(task.get("action_id"))
        if explicit_action_id is not None:
            action_id = explicit_action_id
        elif build_targets.items:  # type: ignore[attr-defined]
            action_id = build_targets.items[0].action_id  # type: ignore[attr-defined]
        else:
            raise ValueError("build_execute workflow could not find any build targets")
        call("describe_build_target", workspace_id, repository_id, action_id=action_id)
        result = call(
            "build_target",
            workspace_id,
            repository_id,
            action_id=action_id,
            timeout_seconds=timeout_seconds,
        )
        status = "passed" if result.success else "failed"  # type: ignore[attr-defined]
        note = (
            f"action_id={action_id}, success={result.success}, status={result.status}, "  # type: ignore[attr-defined]
            f"exit_code={result.exit_code}"  # type: ignore[attr-defined]
        )
        return status, note

    def _prepare_repository_path(self, task: dict[str, object], *, temp_roots: list[Path]) -> Path:
        from suitcode.core.repository import Repository

        repository_path_raw = _required_string(task, "repository_path")
        repository_path = Path(repository_path_raw).expanduser()
        if not repository_path.is_absolute():
            repository_path = self._working_directory / repository_path
        repository_path = repository_path.resolve()
        if not repository_path.exists() or not repository_path.is_dir():
            raise ValueError(f"benchmark repository path does not exist or is not a directory: `{repository_path}`")
        root_candidate = Repository.root_candidate(repository_path)
        if root_candidate == repository_path:
            return repository_path
        if self._is_fixture_candidate(repository_path, root_candidate):
            temp_root = Path(tempfile.mkdtemp(prefix="suitcode-bench-"))
            temp_repo = temp_root / "repo"
            shutil.copytree(repository_path, temp_repo)
            (temp_repo / ".git").mkdir(exist_ok=True)
            temp_roots.append(temp_root)
            return temp_repo
        raise ValueError(
            f"repository_path `{repository_path}` resolves to root `{root_candidate}`; "
            "provide a repository root path or a fixture path that can be isolated"
        )

    @staticmethod
    def _is_fixture_candidate(repository_path: Path, root_candidate: Path) -> bool:
        if repository_path == root_candidate:
            return False
        if not (repository_path / "package.json").exists():
            return False
        if (repository_path / ".git").exists():
            return False
        return repository_path.is_relative_to(root_candidate)


def _required_string(task: dict[str, object], key: str) -> str:
    value = task.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"benchmark task missing non-empty `{key}`")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("optional selector values must be non-empty strings when provided")
    return value.strip()


def _optional_positive_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("numeric benchmark options must be positive integers")
    return value
