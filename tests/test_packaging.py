from __future__ import annotations

import sys
from pathlib import Path


def test_installed_launcher_targets_packaged_streamlit_page(monkeypatch) -> None:
    from code_review_agent import launcher

    calls: list[list[str]] = []
    monkeypatch.setattr(launcher.cli, "main", lambda: calls.append(list(sys.argv)) or 0)

    assert launcher.main() == 0
    assert calls[0][1] == "run"
    assert "--browser.gatherUsageStats=false" in calls[0]
    page = Path(calls[0][2])
    assert page.name == "streamlit_app.py"
    assert page.is_file()


def test_sdist_manifest_omits_source_checkout_only_tests() -> None:
    manifest = (Path(__file__).parents[1] / "MANIFEST.in").read_text(encoding="utf-8")

    assert "prune tests" in manifest
