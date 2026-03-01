from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    os.chdir(repo_root)
    return pytest.main(sys.argv[1:] or ["tests"])


if __name__ == "__main__":
    raise SystemExit(main())
