from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.evaluation.live_study import LiveStudyLauncher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_live_study")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--tracked-label", default="mygamesanywhere")
    scope.add_argument("--repository-root", default=None)
    parser.add_argument("--task-id", default=None)
    parser.add_argument(
        "--task-kind",
        choices=("discovery", "planning", "implementation", "bugfix", "validation", "review"),
        required=True,
    )
    parser.add_argument("--study-kind", default="live_session")
    parser.add_argument("--experiment-id", default="mga-hybrid")
    parser.add_argument("--experiment-label", default="MyGamesAnywhere hybrid study")
    parser.add_argument("--model-name", default=None)
    parser.add_argument("--workspace-mode", default="read_only")
    parser.add_argument("--notes", default=None)
    parser.add_argument("--analytics-run-id", default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    command = tuple(_normalize_command(args.command))
    launcher = LiveStudyLauncher()
    manifest, env, manifest_path = launcher.prepare_launch(
        tracked_label=args.tracked_label,
        repository_root=args.repository_root,
        task_id=args.task_id,
        task_kind=args.task_kind,
        study_kind=args.study_kind,
        experiment_id=args.experiment_id,
        experiment_label=args.experiment_label,
        model_name=args.model_name,
        workspace_mode=args.workspace_mode,
        notes=args.notes,
        command=command,
        command_executed=bool(command),
        analytics_run_id=args.analytics_run_id,
    )
    repository_root = Path(manifest.repository_root)
    if command:
        completed = launcher.launch_command(repository_root=repository_root, command=command, env_overrides=env)
        if args.as_json:
            print(
                json.dumps(
                    {
                        "manifest": manifest.model_dump(mode="json"),
                        "manifest_path": str(manifest_path),
                        "env": env,
                        "command_exit_code": completed.returncode,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            if completed.stdout:
                print(completed.stdout, end="")
            if completed.stderr:
                print(completed.stderr, file=sys.stderr, end="")
        else:
            print(f"Prepared live-study launch: {manifest.launch_id}")
            print(f"Manifest: {manifest_path}")
            print(f"Repository: {manifest.repository_root}")
            print(f"Analytics run: {manifest.analytics_run_id}")
            print(f"Task: {manifest.task_id} ({manifest.task_kind})")
            print(f"Study kind: {manifest.study_kind}")
            print("Environment:")
            for key in sorted(env):
                print(f"  {key}={env[key]}")
            print(f"Command exit code: {completed.returncode}")
        raise SystemExit(completed.returncode)
    if args.as_json:
        print(json.dumps({"manifest": manifest.model_dump(mode="json"), "manifest_path": str(manifest_path), "env": env}, indent=2, sort_keys=True))
        return
    print(f"Prepared live-study launch: {manifest.launch_id}")
    print(f"Manifest: {manifest_path}")
    print(f"Repository: {manifest.repository_root}")
    print(f"Analytics run: {manifest.analytics_run_id}")
    print(f"Task: {manifest.task_id} ({manifest.task_kind})")
    print(f"Study kind: {manifest.study_kind}")
    print("PowerShell environment:")
    for key in sorted(env):
        print(f"$env:{key}='{env[key]}'")


def _normalize_command(items: list[str]) -> list[str]:
    if items and items[0] == "--":
        return items[1:]
    return items


if __name__ == "__main__":
    main()
