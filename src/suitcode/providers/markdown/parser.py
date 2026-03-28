from __future__ import annotations

import re
from pathlib import Path

from suitcode.core.provenance_builders import document_provenance
from suitcode.core.structured_artifact_models import (
    MarkdownChecklistItem,
    MarkdownCodeBlock,
    MarkdownDocumentStructure,
    MarkdownFrontmatter,
    MarkdownLink,
    MarkdownSection,
)

_ATX_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+\s*)?$")
_SETEXT_RE = re.compile(r"^\s{0,3}(=+|-+)\s*$")
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
_CHECKLIST_RE = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s+(.*)$")
_LINK_RE = re.compile(r"(?<!\!)\[(?P<text>[^\]]+)\]\((?P<destination>[^)\n]+)\)")
_FRONTMATTER_RE = re.compile(r"^(---|\+\+\+)\s*$")
_FRONTMATTER_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+\s*:")


def parse_markdown_document(path: Path, repository_rel_path: str) -> MarkdownDocumentStructure:
    lines = path.read_text(encoding="utf-8").splitlines()
    frontmatter, frontmatter_lines = _parse_frontmatter(lines)
    code_blocks, code_ranges = _parse_code_blocks(lines)
    masked_lines = set(frontmatter_lines)
    for start, end in code_ranges:
        masked_lines.update(range(start, end + 1))

    sections = _build_sections(_parse_headings(lines, masked_lines), total_line_count=len(lines))
    links: list[MarkdownLink] = []
    checklist_items: list[MarkdownChecklistItem] = []
    for line_number, line in enumerate(lines, start=1):
        if line_number in masked_lines:
            continue
        checklist_match = _CHECKLIST_RE.match(line)
        if checklist_match is not None:
            checklist_items.append(
                MarkdownChecklistItem(
                    text=checklist_match.group(2).strip(),
                    checked=checklist_match.group(1).lower() == "x",
                    line_start=line_number,
                    line_end=line_number,
                )
            )
        for match in _LINK_RE.finditer(line):
            links.append(
                MarkdownLink(
                    destination=match.group("destination").strip(),
                    text=match.group("text").strip(),
                    line_start=line_number,
                    line_end=line_number,
                )
            )

    provenance = (
        document_provenance(
            evidence_summary=f"markdown document structure parsed directly from `{repository_rel_path}`",
            evidence_paths=(repository_rel_path,),
        ),
    )
    return MarkdownDocumentStructure(
        section_count=len(sections),
        sections=tuple(sections),
        code_block_count=len(code_blocks),
        code_blocks=tuple(code_blocks),
        link_count=len(links),
        links=tuple(links),
        frontmatter=frontmatter,
        checklist_item_count=len(checklist_items),
        checklist_items=tuple(checklist_items),
        provenance=provenance,
    )


def _parse_frontmatter(lines: list[str]) -> tuple[MarkdownFrontmatter | None, set[int]]:
    if not lines or _FRONTMATTER_RE.match(lines[0]) is None:
        return None, set()
    delimiter = lines[0].strip()
    keys: list[str] = []
    for index in range(1, len(lines)):
        line = lines[index]
        if line.strip() == delimiter:
            return (
                MarkdownFrontmatter(
                    line_start=1,
                    line_end=index + 1,
                    keys=tuple(keys),
                ),
                set(range(1, index + 2)),
            )
        if _FRONTMATTER_KEY_RE.match(line):
            keys.append(line.split(":", 1)[0].strip())
    return None, set()


def _parse_code_blocks(lines: list[str]) -> tuple[list[MarkdownCodeBlock], list[tuple[int, int]]]:
    blocks: list[MarkdownCodeBlock] = []
    ranges: list[tuple[int, int]] = []
    line_index = 0
    while line_index < len(lines):
        match = _FENCE_RE.match(lines[line_index])
        if match is None:
            line_index += 1
            continue
        delimiter = match.group(1)
        marker = delimiter[0]
        minimum_width = len(delimiter)
        language = match.group(2).strip() or None
        start_line = line_index + 1
        end_index = len(lines) - 1
        for probe in range(line_index + 1, len(lines)):
            candidate = lines[probe].lstrip()
            if candidate.startswith(marker * minimum_width):
                end_index = probe
                break
        end_line = end_index + 1
        blocks.append(MarkdownCodeBlock(line_start=start_line, line_end=end_line, language=language))
        ranges.append((start_line, end_line))
        line_index = end_index + 1
    return blocks, ranges


def _parse_headings(lines: list[str], masked_lines: set[int]) -> list[tuple[str, int, int]]:
    headings: list[tuple[str, int, int]] = []
    for index, line in enumerate(lines, start=1):
        if index in masked_lines:
            continue
        atx_match = _ATX_HEADING_RE.match(line)
        if atx_match is not None:
            headings.append((_normalize_heading_text(atx_match.group(2)), len(atx_match.group(1)), index))
            continue
        if index >= len(lines) or (index + 1) in masked_lines or not line.strip():
            continue
        setext_match = _SETEXT_RE.match(lines[index])
        if setext_match is None:
            continue
        depth = 1 if setext_match.group(1).startswith("=") else 2
        headings.append((_normalize_heading_text(line), depth, index))
    return headings


def _build_sections(headings: list[tuple[str, int, int]], total_line_count: int) -> list[MarkdownSection]:
    sections: list[MarkdownSection] = []
    for index, (heading, depth, line_start) in enumerate(headings):
        line_end = total_line_count
        for _, next_depth, next_line_start in headings[index + 1 :]:
            if next_depth <= depth:
                line_end = next_line_start - 1
                break
        sections.append(
            MarkdownSection(
                heading=heading,
                depth=depth,
                line_start=line_start,
                line_end=max(line_start, line_end),
                anchor=_anchor_for_heading(heading, line_start),
            )
        )
    return sections


def _normalize_heading_text(value: str) -> str:
    return value.strip().strip("#").strip()


def _anchor_for_heading(heading: str, line_start: int) -> str:
    anchor = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
    return anchor or f"section-{line_start}"
