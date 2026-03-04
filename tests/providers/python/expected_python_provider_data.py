EXPECTED_COMPONENT_IDS = {
    "component:python:acme",
}

EXPECTED_RUNNER_IDS = (
    "runner:python:acme-admin",
    "runner:python:acme-server",
)

EXPECTED_PACKAGE_MANAGER_IDS = ("pkgmgr:python:root",)

EXPECTED_EXTERNAL_PACKAGE_IDS = {
    "external:python:fastapi",
    "external:python:mkdocs",
    "external:python:pydantic",
    "external:python:pytest",
    "external:python:ruff",
    "external:python:uvicorn",
}

EXPECTED_EXTERNAL_VERSION_SPECS = {
    "external:python:fastapi": "fastapi>=0.110",
    "external:python:mkdocs": "mkdocs>=1.6",
    "external:python:pydantic": "pydantic>=2.7",
    "external:python:pytest": "pytest>=8.2",
    "external:python:ruff": "ruff>=0.6",
    "external:python:uvicorn": "uvicorn[standard]>=0.30",
}

EXPECTED_TEST_IDS = (
    "test:python:pytest:root",
    "test:python:unittest:root",
)

EXPECTED_TEST_FILES = {
    "test:python:pytest:root": ("tests/test_basic.py",),
    "test:python:unittest:root": ("tests_unittest/test_unittest_sample.py",),
}

EXPECTED_REPRESENTATIVE_FILE_OWNERS = {
    "pyproject.toml": "pkgmgr:python:root",
    "src/acme/core/repository.py": "component:python:acme",
    "src/acme/mcp/server.py": "runner:python:acme-server",
    "src/acme/providers/python/__init__.py": "runner:python:acme-admin",
}
