from __future__ import annotations

import sys
import tomllib
from importlib.resources import as_file, files

from streamlit.web import cli


def main() -> int:
    """Launch the packaged Streamlit page while preserving user CLI options."""
    options = sys.argv[1:]
    packaged_config = tomllib.loads(
        files("code_review_agent").joinpath("streamlit_config.toml").read_text(encoding="utf-8")
    )
    gather_usage = packaged_config["browser"]["gatherUsageStats"]
    if not any(option.startswith("--browser.gatherUsageStats") for option in options):
        options = [f"--browser.gatherUsageStats={str(gather_usage).lower()}", *options]
    with as_file(files("code_review_agent").joinpath("streamlit_app.py")) as page:
        sys.argv = ["streamlit", "run", str(page), *options]
        return cli.main()
