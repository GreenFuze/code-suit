from __future__ import annotations

from pathlib import Path

from suitcode.providers.npm.runner_parser import NpmRunnerScriptInspector
from suitcode.providers.shared.package_json.workspace import PackageJsonWorkspaceLoader


FIXTURE_ROOT = Path("tests/test_repos/npm")


def test_runner_parser_detects_only_external_executable_scripts() -> None:
    workspace = PackageJsonWorkspaceLoader().load(FIXTURE_ROOT)
    codegen = workspace.package_by_name("@monorepo/codegen")
    build_all = workspace.package_by_name("@monorepo/build-all")
    inspector = NpmRunnerScriptInspector()

    codegen_runners = inspector.inspect(codegen)
    build_all_runners = inspector.inspect(build_all)

    assert [(runner.package_name, runner.script_name) for runner in codegen_runners] == [
        ("@monorepo/codegen", "build"),
        ("@monorepo/codegen", "test"),
    ]
    assert build_all_runners == tuple()
