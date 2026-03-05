from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re

from suitcode.core.provenance import SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance
from suitcode.core.tests.models import (
    TestExecutionResult,
    TestExecutionStatus,
    TestTargetDescription,
)
from suitcode.providers.shared.test_execution.process import ProcessExecutor
from suitcode.providers.shared.test_execution.snippets import FailureSnippetExtractor


class TestExecutionService:
    def __init__(
        self,
        repository_root: Path,
        suit_dir: Path,
        process_executor: ProcessExecutor | None = None,
        snippet_extractor: FailureSnippetExtractor | None = None,
    ) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._suit_dir = suit_dir.expanduser().resolve()
        self._process_executor = process_executor or ProcessExecutor()
        self._snippet_extractor = snippet_extractor or FailureSnippetExtractor()

    def run_target(self, description: TestTargetDescription, timeout_seconds: int) -> TestExecutionResult:
        if timeout_seconds < 1 or timeout_seconds > 3600:
            raise ValueError("timeout_seconds must be between 1 and 3600")
        working_directory = self._resolve_working_directory(description.command_cwd)
        try:
            execution = self._process_executor.run(
                argv=description.command_argv,
                cwd=working_directory,
                timeout_seconds=timeout_seconds,
            )
        except OSError as exc:
            argv_display = " ".join(description.command_argv)
            raise ValueError(f"failed to execute test command `{argv_display}`: {exc}") from exc
        log_path = self._write_run_log(description.test_definition.id, execution.output)
        source_tool = self._source_tool(description)
        failure_snippets = (
            tuple()
            if execution.exit_code == 0 and not execution.timed_out
            else self._snippet_extractor.extract(execution.output, self._repository_root, source_tool=source_tool)
        )
        status = self._resolve_status(execution.exit_code, execution.timed_out)
        summary_kind = SourceKind.TEST_TOOL if description.is_authoritative else SourceKind.HEURISTIC
        provenance = (
            *description.provenance,
            derived_summary_provenance(
                source_kind=summary_kind,
                source_tool=source_tool,
                evidence_summary="test target execution result derived from deterministic provider command",
                evidence_paths=(log_path, *description.test_definition.test_files),
            ),
        )
        return TestExecutionResult(
            test_id=description.test_definition.id,
            status=status,
            success=status == TestExecutionStatus.PASSED,
            command_argv=description.command_argv,
            command_cwd=description.command_cwd,
            exit_code=execution.exit_code,
            duration_ms=execution.duration_ms,
            log_path=log_path,
            warning=description.warning,
            output_excerpt=self._excerpt(execution.output),
            failure_snippets=failure_snippets,
            provenance=provenance,
        )

    def _resolve_working_directory(self, command_cwd: str | None) -> Path:
        if command_cwd is None:
            return self._repository_root
        working_directory = (self._repository_root / command_cwd).resolve()
        try:
            working_directory.relative_to(self._repository_root)
        except ValueError as exc:
            raise ValueError(f"command cwd escapes repository root: `{command_cwd}`") from exc
        if not working_directory.exists() or not working_directory.is_dir():
            raise ValueError(f"command cwd does not exist: `{command_cwd}`")
        return working_directory

    def _write_run_log(self, test_id: str, output: str) -> str:
        runs_dir = (self._suit_dir / "runs" / "tests").resolve()
        runs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_test_id = re.sub(r"[^a-zA-Z0-9._-]+", "_", test_id).strip("._-")
        if not safe_test_id:
            safe_test_id = "test"
        filename = f"{timestamp}-{safe_test_id}.log"
        log_file = runs_dir / filename
        log_file.write_text(output, encoding="utf-8")
        return log_file.relative_to(self._repository_root).as_posix()

    @staticmethod
    def _resolve_status(exit_code: int | None, timed_out: bool) -> TestExecutionStatus:
        if timed_out:
            return TestExecutionStatus.TIMEOUT
        if exit_code == 0:
            return TestExecutionStatus.PASSED
        if exit_code is None:
            return TestExecutionStatus.ERROR
        return TestExecutionStatus.FAILED

    @staticmethod
    def _source_tool(description: TestTargetDescription) -> str | None:
        for entry in description.provenance:
            if entry.source_kind == SourceKind.TEST_TOOL and entry.source_tool is not None:
                return entry.source_tool
        return None

    @staticmethod
    def _excerpt(output: str, max_lines: int = 40, max_chars: int = 4000) -> str | None:
        stripped = output.strip()
        if not stripped:
            return None
        lines = stripped.splitlines()
        excerpt = "\n".join(lines[-max_lines:])
        if len(excerpt) > max_chars:
            return excerpt[-max_chars:]
        return excerpt
