from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable

from suitcode.analytics.benchmark_harness import BenchmarkTaskRun
from suitcode.analytics.benchmark_service_caller import BenchmarkServiceCaller
from suitcode.analytics.benchmark_telemetry import BenchmarkTelemetryCollector


@dataclass(frozen=True)
class _WorkflowExecution:
    status: str
    note: str | None
    outputs: tuple[object, ...]
    deterministic_action_kind: str | None = None
    deterministic_action_target_id: str | None = None
    deterministic_action_status: str = "not_applicable"


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
        self._telemetry_collector = BenchmarkTelemetryCollector()

    def run_task(self, task: dict[str, object], *, run_id: str, task_artifact_path: Path) -> BenchmarkTaskRun:
        task_id = _required_string(task, "task_id")
        repository_hint = self._repository_hint(task)
        temp_roots: list[Path] = []
        start = perf_counter()
        service = self._service_factory()
        workspace_id: str | None = None
        repository_id: str | None = None
        repository_root = repository_hint
        execution = _WorkflowExecution(
            status="error",
            note=None,
            outputs=tuple(),
            deterministic_action_status="not_applicable",
        )
        caller = BenchmarkServiceCaller(service, repository_root=repository_root)
        with caller.benchmark_context(run_id=run_id, task_id=task_id):
            try:
                repository_root = self._prepare_repository_path(task, temp_roots=temp_roots)
                caller = BenchmarkServiceCaller(service, repository_root=repository_root)
                workflow = _required_string(task, "workflow")
                timeout_seconds = _optional_positive_int(task.get("timeout_seconds"), default=120)
                opened = caller.call("open_workspace", str(repository_root))
                workspace_id = opened.workspace.workspace_id
                repository_id = opened.initial_repository.repository_id
                truth_coverage = caller.call(
                    "get_truth_coverage",
                    workspace_id,
                    repository_id,
                )

                if workflow == "orientation":
                    execution = self._run_orientation_workflow(
                        caller,
                        workspace_id=workspace_id,
                        repository_id=repository_id,
                        preview_limit=_optional_positive_int(task.get("preview_limit"), default=10),
                    )
                elif workflow == "change_impact":
                    execution = self._run_change_impact_workflow(
                        caller,
                        task=task,
                        workspace_id=workspace_id,
                        repository_id=repository_id,
                    )
                elif workflow == "test_execute":
                    execution = self._run_test_execute_workflow(
                        caller,
                        task=task,
                        workspace_id=workspace_id,
                        repository_id=repository_id,
                        timeout_seconds=timeout_seconds,
                    )
                elif workflow == "build_execute":
                    execution = self._run_build_execute_workflow(
                        caller,
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
                execution = _WorkflowExecution(
                    status="error",
                    note=f"{exc.__class__.__name__}: {exc}",
                    outputs=tuple(),
                    deterministic_action_status=(
                        "error" if execution.deterministic_action_kind is not None else "not_applicable"
                    ),
                    deterministic_action_kind=execution.deterministic_action_kind,
                    deterministic_action_target_id=execution.deterministic_action_target_id,
                )
            finally:
                for temp_root in temp_roots:
                    shutil.rmtree(temp_root, ignore_errors=True)

        duration_ms = int((perf_counter() - start) * 1000)
        return self._telemetry_collector.collect_task_run(
            run_id=run_id,
            task=task,
            task_artifact_path=task_artifact_path,
            repository_root=repository_root,
            session_id=caller.session_id,
            workspace_id=workspace_id,
            repository_id=repository_id,
            tool_calls=caller.tool_calls,
            duration_ms=duration_ms,
            execution=execution,
            store=caller.store,
            truth_coverage=locals().get("truth_coverage"),
        )

    @staticmethod
    def _default_service_factory() -> object:
        from suitcode.mcp.service import SuitMcpService
        from suitcode.mcp.state import WorkspaceRegistry

        return SuitMcpService(registry=WorkspaceRegistry())

    def _run_orientation_workflow(
        self,
        caller: BenchmarkServiceCaller,
        *,
        workspace_id: str,
        repository_id: str,
        preview_limit: int,
    ) -> _WorkflowExecution:
        summary = caller.call(
            "repository_summary",
            workspace_id,
            repository_id,
            preview_limit=preview_limit,
        )
        outputs: list[object] = [summary]
        component_ids = tuple(summary.component_ids_preview)  # type: ignore[attr-defined]
        if not component_ids:
            listed = caller.call(
                "list_components",
                workspace_id,
                repository_id,
                limit=1,
                offset=0,
            )
            component_ids = tuple(item.id for item in listed.items)  # type: ignore[attr-defined]
            outputs.append(listed)
        if component_ids:
            described = caller.call(
                "describe_components",
                workspace_id,
                repository_id,
                component_ids=(component_ids[0],),
                file_preview_limit=10,
                dependency_preview_limit=10,
                dependent_preview_limit=10,
                test_preview_limit=5,
            )
            outputs.append(described)
        return _WorkflowExecution(
            status="passed",
            note=f"orientation complete; components={summary.component_count}, tests={summary.test_count}",  # type: ignore[attr-defined]
            outputs=tuple(outputs),
        )

    def _run_change_impact_workflow(
        self,
        caller: BenchmarkServiceCaller,
        *,
        task: dict[str, object],
        workspace_id: str,
        repository_id: str,
    ) -> _WorkflowExecution:
        symbol_id = _optional_string(task.get("symbol_id"))
        repository_rel_path = _optional_string(task.get("repository_rel_path"))
        owner_id = _optional_string(task.get("owner_id"))
        selector_count = sum(1 for item in (symbol_id, repository_rel_path, owner_id) if item is not None)
        if selector_count != 1:
            raise ValueError(
                "change_impact workflow requires exactly one selector: `symbol_id`, `repository_rel_path`, or `owner_id`"
            )
        impact = caller.call(
            "analyze_change",
            workspace_id,
            repository_id,
            symbol_id=symbol_id,
            repository_rel_path=repository_rel_path,
            owner_id=owner_id,
        )
        return _WorkflowExecution(
            status="passed",
            note=f"change impact complete; target_kind={impact.target_kind}, related_tests={len(impact.related_tests)}",  # type: ignore[attr-defined]
            outputs=(impact,),
        )

    def _run_test_execute_workflow(
        self,
        caller: BenchmarkServiceCaller,
        *,
        task: dict[str, object],
        workspace_id: str,
        repository_id: str,
        timeout_seconds: int,
    ) -> _WorkflowExecution:
        tests = caller.call(
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
        description = caller.call("describe_test_target", workspace_id, repository_id, test_id=test_id)
        run = caller.call(
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
        return _WorkflowExecution(
            status=status,
            note=note,
            outputs=(tests, description, run),
            deterministic_action_kind="test",
            deterministic_action_target_id=test_id,
            deterministic_action_status=status,
        )

    def _run_build_execute_workflow(
        self,
        caller: BenchmarkServiceCaller,
        *,
        task: dict[str, object],
        workspace_id: str,
        repository_id: str,
        timeout_seconds: int,
    ) -> _WorkflowExecution:
        build_targets = caller.call(
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
        description = caller.call("describe_build_target", workspace_id, repository_id, action_id=action_id)
        result = caller.call(
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
        return _WorkflowExecution(
            status=status,
            note=note,
            outputs=(build_targets, description, result),
            deterministic_action_kind="build",
            deterministic_action_target_id=action_id,
            deterministic_action_status=status,
        )

    def _prepare_repository_path(self, task: dict[str, object], *, temp_roots: list[Path]) -> Path:
        from suitcode.core.repository import Repository

        repository_path = self._repository_hint(task)
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

    def _repository_hint(self, task: dict[str, object]) -> Path:
        repository_path_raw = _required_string(task, "repository_path")
        repository_path = Path(repository_path_raw).expanduser()
        if not repository_path.is_absolute():
            repository_path = self._working_directory / repository_path
        return repository_path.resolve()

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
