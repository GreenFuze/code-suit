from __future__ import annotations

import argparse
import signal
import uuid
from pathlib import Path

from suitcode.runtime.coordinator import CoordinatorServer


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="suitcode-coordinator")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--instance-id", default=uuid.uuid4().hex)
    parser.add_argument("--idle-ttl-seconds", type=float, default=60.0 * 60.0)
    parser.add_argument("--managed-session-ttl-seconds", type=float, default=60.0 * 60.0)
    parser.add_argument("--warmup-concurrency", type=int, default=2)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    server = CoordinatorServer(
        project_root=Path(args.project_root),
        instance_id=args.instance_id,
        idle_ttl_seconds=args.idle_ttl_seconds,
        managed_session_ttl_seconds=args.managed_session_ttl_seconds,
        warmup_concurrency=args.warmup_concurrency,
    )

    def _handle_signal(signum, frame):  # noqa: ANN001, ARG001
        server.shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _handle_signal)
    server.run()


if __name__ == "__main__":
    main()
