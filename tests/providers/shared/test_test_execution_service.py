from __future__ import annotations

from pathlib import Path

from suitcode.core.models import TestDefinition as CoreTestDefinition, TestFramework as CoreTestFramework
from suitcode.core.provenance_builders import heuristic_provenance, test_tool_provenance as make_test_tool_provenance
from suitcode.core.tests.models import TestExecutionStatus as ExecutionStatus, TestTargetDescription as TargetDescription
from suitcode.providers.shared.test_execution.process import ProcessExecutionResult
from suitcode.providers.shared.test_execution.service import TestExecutionService as ExecutionService
from suitcode.providers.shared.test_execution.snippets import FailureSnippetExtractor


def _description(is_authoritative: bool = True) -> TargetDescription:
    provenance = (
        make_test_tool_provenance(
            source_tool="pytest",
            evidence_summary="discovered from pytest --collect-only -q",
            evidence_paths=("tests/test_sample.py",),
        ),
        heuristic_provenance(
            evidence_summary="derived from deterministic action mapping",
            evidence_paths=("pyproject.toml",),
        ),
    )
    warning = None if is_authoritative else "heuristic scope"
    return TargetDescription(
        test_definition=CoreTestDefinition(
            id="test:python:pytest:root",
            name="pytest",
            framework=CoreTestFramework.PYTEST,
            test_files=("tests/test_sample.py",),
            provenance=provenance,
        ),
        command_argv=("pytest", "tests/test_sample.py"),
        command_cwd=None,
        is_authoritative=is_authoritative,
        warning=warning,
        provenance=provenance,
    )


def test_failure_snippet_extractor_includes_plus_minus_two_lines(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir(parents=True)
    test_file = repository_root / "tests" / "test_sample.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "\n".join(
            [
                "def test_sample():",
                "    value = 1",
                "    expected = 2",
                "    assert value == expected",
                "    assert True",
                "    assert False",
            ]
        ),
        encoding="utf-8",
    )

    extractor = FailureSnippetExtractor()
    snippets = extractor.extract(
        output="tests/test_sample.py:4: AssertionError",
        repository_root=repository_root,
        source_tool="pytest",
    )

    assert len(snippets) == 1
    snippet = snippets[0]
    assert snippet.line_start == 2
    assert snippet.line_end == 6
    assert "4:     assert value == expected" in snippet.snippet
    assert snippet.provenance


def test_test_execution_service_writes_logs_and_marks_failed_status(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir(parents=True)
    suit_dir = repository_root / ".suit"
    suit_dir.mkdir(parents=True)
    failing_file = repository_root / "tests" / "test_sample.py"
    failing_file.parent.mkdir(parents=True)
    failing_file.write_text("assert False\n", encoding="utf-8")

    class _FakeProcessExecutor:
        def run(self, argv: tuple[str, ...], cwd: Path, timeout_seconds: int) -> ProcessExecutionResult:
            return ProcessExecutionResult(
                exit_code=1,
                output="tests/test_sample.py:1: AssertionError\nE assert False\n",
                timed_out=False,
                duration_ms=12,
            )

    service = ExecutionService(
        repository_root=repository_root,
        suit_dir=suit_dir,
        process_executor=_FakeProcessExecutor(),  # type: ignore[arg-type]
    )
    result = service.run_target(_description(is_authoritative=False), timeout_seconds=30)

    assert result.status == ExecutionStatus.FAILED
    assert result.success is False
    assert result.log_path.startswith(".suit/runs/tests/")
    assert (repository_root / result.log_path).exists()
    assert result.warning == "heuristic scope"
    assert result.failure_snippets
    assert result.provenance


def test_test_execution_service_timeout_sets_timeout_status(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir(parents=True)
    suit_dir = repository_root / ".suit"
    suit_dir.mkdir(parents=True)

    class _TimeoutProcessExecutor:
        def run(self, argv: tuple[str, ...], cwd: Path, timeout_seconds: int) -> ProcessExecutionResult:
            return ProcessExecutionResult(
                exit_code=None,
                output="",
                timed_out=True,
                duration_ms=1000,
            )

    service = ExecutionService(
        repository_root=repository_root,
        suit_dir=suit_dir,
        process_executor=_TimeoutProcessExecutor(),  # type: ignore[arg-type]
    )
    result = service.run_target(_description(), timeout_seconds=1)

    assert result.status == ExecutionStatus.TIMEOUT
    assert result.success is False
    assert result.exit_code is None
