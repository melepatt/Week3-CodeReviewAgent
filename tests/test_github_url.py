from __future__ import annotations

import pytest

from code_review_agent.github import PullRequestUrlError, parse_pull_request_url, stable_marker


def test_parse_canonical_pull_request_url() -> None:
    ref = parse_pull_request_url("https://github.com/OpenAI/example.py/pull/42")

    assert ref.owner == "OpenAI"
    assert ref.repo == "example.py"
    assert ref.number == 42
    assert ref.canonical_url == "https://github.com/OpenAI/example.py/pull/42"
    assert stable_marker(ref) == "<!-- code-review-agent:OpenAI/example.py#42 -->"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/acme/widgets/pull/1",
        "https://www.github.com/acme/widgets/pull/1",
        "https://github.com/acme/widgets/pull/1/",
        "https://github.com/acme/widgets/pull/0",
        "https://github.com/acme/widgets/pulls/1",
        "https://github.com/acme/widgets/pull/1/files",
        "https://github.com/acme/widgets/pull/1?diff=split",
        "https://github.com/acme/widgets/pull/1#discussion",
        "https://user@github.com/acme/widgets/pull/1",
        "https://github.com/acme/widgets/pull/not-a-number",
        "https://github.com/acme%2Fother/widgets/pull/1",
    ],
)
def test_reject_noncanonical_pull_request_url(url: str) -> None:
    with pytest.raises(PullRequestUrlError):
        parse_pull_request_url(url)
