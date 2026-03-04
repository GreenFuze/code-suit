from __future__ import annotations

from suitcode.providers.shared.lsp.protocol import LspProtocolParser


def test_protocol_parser_parses_document_symbols() -> None:
    parser = LspProtocolParser()

    symbols = parser.parse_document_symbols(
        [
            {
                "name": "Core",
                "kind": 5,
                "detail": "class",
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 10, "character": 1},
                },
                "selectionRange": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 4},
                },
                "children": [
                    {
                        "name": "getValue",
                        "kind": 6,
                        "range": {
                            "start": {"line": 4, "character": 2},
                            "end": {"line": 6, "character": 3},
                        },
                        "selectionRange": {
                            "start": {"line": 4, "character": 2},
                            "end": {"line": 4, "character": 10},
                        },
                    }
                ],
            }
        ]
    )

    assert len(symbols) == 1
    assert symbols[0].name == "Core"
    assert symbols[0].children[0].name == "getValue"


def test_protocol_parser_parses_symbol_information_document_symbols() -> None:
    parser = LspProtocolParser()

    symbols = parser.parse_document_symbols(
        [
            {
                "name": "Workspace",
                "kind": 5,
                "location": {
                    "uri": "file:///repo/workspace.py",
                    "range": {
                        "start": {"line": 10, "character": 0},
                        "end": {"line": 30, "character": 1},
                    },
                },
                "containerName": "module",
            }
        ]
    )

    assert len(symbols) == 1
    assert symbols[0].name == "Workspace"
    assert symbols[0].container_name == "module"
    assert symbols[0].selection_range == symbols[0].range


def test_protocol_parser_parses_location_and_location_link_payloads() -> None:
    parser = LspProtocolParser()

    direct = parser.parse_locations(
        {
            "uri": "file:///repo/core.py",
            "range": {
                "start": {"line": 4, "character": 2},
                "end": {"line": 4, "character": 9},
            },
        }
    )
    linked = parser.parse_locations(
        [
            {
                "targetUri": "file:///repo/models.py",
                "targetRange": {
                    "start": {"line": 10, "character": 0},
                    "end": {"line": 10, "character": 12},
                },
                "targetSelectionRange": {
                    "start": {"line": 10, "character": 4},
                    "end": {"line": 10, "character": 12},
                },
            }
        ]
    )

    assert direct[0].uri == "file:///repo/core.py"
    assert direct[0].range.start.line == 4
    assert linked[0].uri == "file:///repo/models.py"
    assert linked[0].range.start.character == 4
