from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from suitcode.providers.go.symbol_service import GoFileSymbolService


@dataclass(frozen=True)
class GoImplementationAnchor:
    repository_rel_path: str
    line: int
    column: int
    kind: str


class GoImplementationService:
    def __init__(
        self,
        *,
        repository_root: Path,
        attachment_root: Path,
        attachment_root_rel_path: str,
        symbol_service: GoFileSymbolService,
    ) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._attachment_root = attachment_root.expanduser().resolve()
        self._attachment_root_rel_path = attachment_root_rel_path.strip().strip("/").replace("\\", "/")
        self._symbol_service = symbol_service
        self._anchors_cache: dict[str, tuple[GoImplementationAnchor, ...]] = {}
        self._definition_symbol_cache: dict[str, tuple[object, ...]] = {}
        self._locations_cache: dict[str, tuple[tuple[str, int, int, int, int], ...]] = {}
        self._lock = Lock()

    def get_file_implementation_locations(self, repository_rel_path: str) -> tuple[tuple[str, int, int, int, int], ...]:
        with self._lock:
            cached = self._locations_cache.get(repository_rel_path)
            if cached is not None:
                return cached
        anchors = self._anchors_for_file(repository_rel_path)
        locations: dict[tuple[str, int, int, int, int], tuple[str, int, int, int, int]] = {}
        with self._symbol_service.open_session() as session:
            for anchor in anchors:
                if anchor.kind != "interface_declaration" and not self._anchor_targets_interface(anchor, session=session):
                    continue
                for location in session.find_implementations(
                    anchor.repository_rel_path,
                    anchor.line,
                    anchor.column,
                ):
                    locations.setdefault(location, location)
        result = tuple(sorted(locations.values(), key=lambda item: (item[0], item[1], item[3], item[2], item[4])))
        with self._lock:
            self._locations_cache[repository_rel_path] = result
        return result

    def _anchor_targets_interface(self, anchor: GoImplementationAnchor, *, session) -> bool:
        definitions = session.find_definition(anchor.repository_rel_path, anchor.line, anchor.column)
        if not definitions:
            return False
        for definition in definitions:
            if self._definition_kind(definition[0], definition[1], definition[3], session=session) == "interface":
                return True
        return False

    def _definition_kind(self, repository_rel_path: str, line: int, column: int, *, session) -> str | None:
        symbols = self._symbols_for_definition_file(repository_rel_path, session=session)
        candidates = [
            symbol
            for symbol in symbols
            if symbol.line_start is not None
            and symbol.line_end is not None
            and symbol.column_start is not None
            and symbol.column_end is not None
            and self._contains_position(symbol, line, column)
        ]
        if not candidates:
            return None
        best = min(
            candidates,
            key=lambda item: (
                (item.line_end - item.line_start if item.line_end is not None and item.line_start is not None else 0),
                (item.column_end - item.column_start if item.column_end is not None and item.column_start is not None else 0),
            ),
        )
        return best.kind

    @staticmethod
    def _contains_position(symbol, line: int, column: int) -> bool:
        line_start = symbol.line_start or line
        line_end = symbol.line_end or line
        column_start = symbol.column_start or column
        column_end = symbol.column_end or column
        if line < line_start or line > line_end:
            return False
        if line == line_start and column < column_start:
            return False
        if line == line_end and column > column_end:
            return False
        return True

    def _symbols_for_definition_file(self, repository_rel_path: str, *, session) -> tuple[object, ...]:
        with self._lock:
            cached = self._definition_symbol_cache.get(repository_rel_path)
            if cached is not None:
                return cached
        symbols = session.list_file_symbols(repository_rel_path)
        with self._lock:
            self._definition_symbol_cache[repository_rel_path] = symbols
        return symbols

    def _anchors_for_file(self, repository_rel_path: str) -> tuple[GoImplementationAnchor, ...]:
        with self._lock:
            cached = self._anchors_cache.get(repository_rel_path)
            if cached is not None:
                return cached
        source_file = self._repository_root / repository_rel_path
        helper = Path(__file__).with_name("interface_anchors.go")
        result = subprocess.run(
            ("go", "run", str(helper), "--", str(source_file)),
            cwd=self._attachment_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        raw_items = json.loads(result.stdout)
        anchors = tuple(
            GoImplementationAnchor(
                repository_rel_path=repository_rel_path,
                line=int(item["line"]),
                column=int(item["column"]),
                kind=str(item.get("kind") or "type_usage"),
            )
            for item in raw_items
            if self._is_valid_anchor_payload(item)
        )
        with self._lock:
            self._anchors_cache[repository_rel_path] = anchors
        return anchors

    @staticmethod
    def _is_valid_anchor_payload(item: object) -> bool:
        return (
            isinstance(item, dict)
            and isinstance(item.get("line"), int)
            and isinstance(item.get("column"), int)
            and isinstance(item.get("kind"), str)
        )
