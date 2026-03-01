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
