EXPECTED_FILE_SYMBOLS = {
    "src/acme/__init__.py": (),
    "src/acme/core/__init__.py": (),
    "src/acme/core/models/__init__.py": (),
    "src/acme/core/repository.py": (
        {"name": "RepositoryManager", "kind": "class", "line_start": 1, "line_end": 7, "column_start": 1, "column_end": 10, "signature": None},
        {"name": "__init__", "kind": "constructor", "line_start": 2, "line_end": 3, "column_start": 5, "column_end": 15, "signature": "__init__(prefix: str)"},
        {"name": "build", "kind": "method", "line_start": 5, "line_end": 6, "column_start": 5, "column_end": 10, "signature": "build(name: str) -> str"},
        {"name": "build_repository_id", "kind": "function", "line_start": 9, "line_end": 11, "column_start": 1, "column_end": 10, "signature": "build_repository_id(name: str) -> str"},
    ),
    "src/acme/mcp/__init__.py": (),
    "src/acme/mcp/server.py": (
        {"name": "main", "kind": "function", "line_start": 5, "line_end": 6, "column_start": 1, "column_end": 10, "signature": "main() -> str"},
        {"name": "run_server", "kind": "function", "line_start": 1, "line_end": 2, "column_start": 1, "column_end": 10, "signature": "run_server() -> str"},
    ),
    "src/acme/providers/__init__.py": (),
    "src/acme/providers/python/__init__.py": (
        {"name": "cli", "kind": "function", "line_start": 1, "line_end": 2, "column_start": 1, "column_end": 10, "signature": "cli() -> str"},
    ),
    "tests/test_basic.py": (
        {"name": "test_smoke", "kind": "function", "line_start": 1, "line_end": 2, "column_start": 1, "column_end": 10, "signature": "test_smoke() -> None"},
    ),
    "tests_unittest/test_unittest_sample.py": (
        {"name": "SampleTest", "kind": "class", "line_start": 4, "line_end": 6, "column_start": 1, "column_end": 10, "signature": None},
        {"name": "test_truth", "kind": "method", "line_start": 5, "line_end": 6, "column_start": 5, "column_end": 14, "signature": "test_truth() -> None"},
    ),
}
