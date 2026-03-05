from __future__ import annotations

import re
from pathlib import Path

from suitcode.core.provenance import SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance
from suitcode.core.tests.models import TestFailureSnippet


class FailureSnippetExtractor:
    _PATH_LINE_PATTERNS = (
        re.compile(r"\((?P<path>[^()\s]+?\.(?:py|ts|tsx|js|jsx)):(?P<line>\d+)(?::\d+)?\)"),
        re.compile(r"(?P<path>[A-Za-z0-9_./\\-]+?\.(?:py|ts|tsx|js|jsx)):(?P<line>\d+)(?::\d+)?"),
    )

    def __init__(self, context_lines: int = 2, max_snippets: int = 10) -> None:
        if context_lines < 0:
            raise ValueError("context_lines must be >= 0")
        if max_snippets < 1:
            raise ValueError("max_snippets must be >= 1")
        self._context_lines = context_lines
        self._max_snippets = max_snippets

    def extract(
        self,
        output: str,
        repository_root: Path,
        source_tool: str | None,
    ) -> tuple[TestFailureSnippet, ...]:
        root = repository_root.expanduser().resolve()
        snippets: list[TestFailureSnippet] = []
        seen: set[tuple[str, int]] = set()
        for raw_path, line in self._locations(output):
            normalized = self._resolve_repository_path(raw_path, root)
            if normalized is None:
                continue
            key = (normalized, line)
            if key in seen:
                continue
            seen.add(key)
            snippet = self._build_snippet(normalized, line, root, source_tool)
            if snippet is not None:
                snippets.append(snippet)
            if len(snippets) >= self._max_snippets:
                break
        return tuple(snippets)

    def _locations(self, output: str) -> tuple[tuple[str, int], ...]:
        found: list[tuple[str, int]] = []
        for pattern in self._PATH_LINE_PATTERNS:
            for match in pattern.finditer(output):
                raw_path = match.group("path")
                line = int(match.group("line"))
                if line < 1:
                    continue
                found.append((raw_path, line))
        return tuple(found)

    def _resolve_repository_path(self, raw_path: str, repository_root: Path) -> str | None:
        candidate_path = Path(raw_path)
        if not candidate_path.is_absolute():
            candidate_path = repository_root / candidate_path
        candidate = candidate_path.expanduser().resolve()
        if not candidate.exists() or not candidate.is_file():
            return None
        try:
            rel = candidate.relative_to(repository_root).as_posix()
        except ValueError:
            return None
        return rel

    def _build_snippet(
        self,
        repository_rel_path: str,
        line: int,
        repository_root: Path,
        source_tool: str | None,
    ) -> TestFailureSnippet | None:
        file_path = (repository_root / repository_rel_path).resolve()
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            return None
        if not lines:
            return None
        clamped_line = min(max(line, 1), len(lines))
        line_start = max(1, clamped_line - self._context_lines)
        line_end = min(len(lines), clamped_line + self._context_lines)
        snippet_text = "\n".join(
            f"{line_no}: {lines[line_no - 1]}"
            for line_no in range(line_start, line_end + 1)
        )
        return TestFailureSnippet(
            repository_rel_path=repository_rel_path,
            line_start=line_start,
            line_end=line_end,
            snippet=snippet_text,
            provenance=(
                derived_summary_provenance(
                    source_kind=SourceKind.TEST_TOOL,
                    source_tool=source_tool,
                    evidence_summary="derived from test output file/line references",
                    evidence_paths=(repository_rel_path,),
                ),
            ),
        )
