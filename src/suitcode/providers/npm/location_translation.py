from __future__ import annotations

from suitcode.core.code.models import CodeLocation
from suitcode.core.models import normalize_repository_relative_path
from suitcode.core.provenance_builders import lsp_location_provenance


class NpmLocationTranslator:
    def to_code_location(
        self,
        location: tuple[str, int, int, int, int],
        *,
        operation: str,
    ) -> CodeLocation:
        repository_rel_path, line_start, line_end, column_start, column_end = location
        repository_rel_path = normalize_repository_relative_path(repository_rel_path)
        return CodeLocation(
            repository_rel_path=repository_rel_path,
            line_start=line_start,
            line_end=line_end,
            column_start=column_start,
            column_end=column_end,
            provenance=(
                lsp_location_provenance(
                    source_tool="typescript-language-server",
                    repository_rel_path=repository_rel_path,
                    operation=operation,
                ),
            ),
        )
