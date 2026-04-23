from __future__ import annotations

import json
from pathlib import Path


def test_tracked_repositories_manifest_exists_and_includes_expected_entries() -> None:
    manifest_path = Path("docs/dogfooding/tracked_repositories.v1.json")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0"
    labels = {item["label"] for item in payload["repositories"]}
    assert {"suitcode", "mygamesanywhere", "mygames-server"} <= labels


def test_phase3_runbook_links_manifest_and_summary_script() -> None:
    content = Path("docs/dogfooding/phase3_runbook.md").read_text(encoding="utf-8")

    assert "tracked_repositories.v1.json" in content
    assert "python scripts/analyze_dogfooding.py --tracked-label suitcode" in content
    assert "python scripts/analyze_dogfooding.py --tracked-label mygames-server" in content
