from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.providers.go.symbol_models import GoWorkspaceSymbol
from suitcode.providers.shared.structural_symbols import filter_structural_symbols


@dataclass(frozen=True)
class GoStructuralSymbolService:
    repository_root: Path
    attachment_root: Path
    attachment_root_rel_path: str

    _SUPPORTED_EXTENSIONS = frozenset({".go"})

    def list_file_symbols(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[GoWorkspaceSymbol, ...]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        absolute_path = (self.repository_root / normalized_path).resolve()
        try:
            absolute_path.relative_to(self.attachment_root)
        except ValueError:
            return tuple()
        if absolute_path.suffix.lower() not in self._SUPPORTED_EXTENSIONS:
            return tuple()
        if not absolute_path.exists() or not absolute_path.is_file():
            raise ValueError(f"file does not exist: `{normalized_path}`")

        helper = Path(__file__).with_name("structural_symbols.go")
        result = subprocess.run(
            ("go", "run", str(helper), "--", str(absolute_path)),
            cwd=self.attachment_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("Go structural symbol probe returned invalid JSON") from exc
        symbols = self._coerce_symbols(normalized_path, payload)
        return filter_structural_symbols(symbols, query=query, is_case_sensitive=is_case_sensitive)

    @staticmethod
    def _coerce_symbols(repository_rel_path: str, payload: object) -> tuple[GoWorkspaceSymbol, ...]:
        if not isinstance(payload, dict):
            raise ValueError("Go structural symbol probe returned an invalid payload shape")
        raw_symbols = payload.get("symbols")
        if not isinstance(raw_symbols, list):
            raise ValueError("Go structural symbol probe field `symbols` must be a list")
        items: list[GoWorkspaceSymbol] = []
        seen: set[tuple[object, ...]] = set()
        for item in raw_symbols:
            if not isinstance(item, dict):
                raise ValueError("Go structural symbol items must be objects")
            name = item.get("name")
            kind = item.get("kind")
            line_start = item.get("line_start")
            line_end = item.get("line_end")
            column_start = item.get("column_start")
            column_end = item.get("column_end")
            signature = item.get("signature")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Go structural symbol `name` must be a non-empty string")
            if not isinstance(kind, str) or not kind.strip():
                raise ValueError("Go structural symbol `kind` must be a non-empty string")
            if not isinstance(line_start, int) or line_start < 1:
                raise ValueError("Go structural symbol `line_start` must be a positive integer")
            if not isinstance(line_end, int) or line_end < line_start:
                raise ValueError("Go structural symbol `line_end` must be a valid integer")
            if not isinstance(column_start, int) or column_start < 1:
                raise ValueError("Go structural symbol `column_start` must be a positive integer")
            if not isinstance(column_end, int) or column_end < 1:
                raise ValueError("Go structural symbol `column_end` must be a positive integer")
            if signature is not None and not isinstance(signature, str):
                raise ValueError("Go structural symbol `signature` must be a string when present")
            key = (name, kind, line_start, line_end, column_start, column_end)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                GoWorkspaceSymbol(
                    name=name.strip(),
                    kind=kind.strip(),
                    repository_rel_path=repository_rel_path,
                    line_start=line_start,
                    line_end=line_end,
                    column_start=column_start,
                    column_end=column_end,
                    container_name=None,
                    signature=signature,
                )
            )
        return tuple(
            sorted(
                items,
                key=lambda item: (item.name, item.kind, item.line_start or 0, item.column_start or 0),
            )
        )
