from __future__ import annotations

import json

import httpx
import pytest

from code_review_agent.config import Limits
from code_review_agent.github import GitHubReadClient, GitHubReadError, parse_pull_request_url


def response(
    request: httpx.Request, status: int, payload: object, **headers: str
) -> httpx.Response:
    return httpx.Response(status, json=payload, headers=headers, request=request)


def pr_payload(sha: str = "a" * 40) -> dict[str, object]:
    return {
        "number": 7,
        "html_url": "https://github.com/acme/widgets/pull/7",
        "title": "Guard widget parsing",
        "body": "Adds input validation",
        "user": {"login": "octocat"},
        "base": {"ref": "main"},
        "head": {"ref": "safe-parse", "sha": sha},
    }


def test_fetch_snapshot_paginates_files_and_retrieves_bounded_content() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/pulls/7"):
            return response(request, 200, pr_payload())
        if request.url.path.endswith("/pulls/7/files") and request.url.params["page"] == "1":
            return response(
                request,
                200,
                [
                    {
                        "filename": "src/widget.py",
                        "status": "modified",
                        "additions": 2,
                        "deletions": 1,
                        "changes": 3,
                        "patch": "@@ -1 +1,2 @@\n-old\n+new\n+safe",
                    }
                ],
                link=(
                    '<https://api.github.test/repos/acme/widgets/pulls/7/files?page=2>; rel="next"'
                ),
            )
        if request.url.path.endswith("/pulls/7/files"):
            return response(
                request,
                200,
                [
                    {
                        "filename": "tests/test_widget.py",
                        "status": "added",
                        "additions": 1,
                        "deletions": 0,
                        "changes": 1,
                        "patch": "@@ -0,0 +1 @@\n+def test_safe(): pass",
                    }
                ],
            )
        if request.url.path.endswith("/contents/src/widget.py"):
            return response(request, 200, {"content": "cHJpbnQoJ3NhZmUnKQo=", "encoding": "base64"})
        if request.url.path.endswith("/contents/tests/test_widget.py"):
            return response(request, 200, {"content": "YXNzZXJ0IFRydWUK", "encoding": "base64"})
        raise AssertionError(f"unexpected request {request.url}")

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.github.test"
    )
    reader = GitHubReadClient(http_client=client, max_retries=0)

    snapshot = reader.fetch_snapshot(
        parse_pull_request_url("https://github.com/acme/widgets/pull/7"),
        Limits(max_files=5, max_file_content_chars=12, max_total_context_chars=100),
    )

    assert snapshot.metadata.head_sha == "a" * 40
    assert snapshot.metadata.author == "octocat"
    assert [file.path for file in snapshot.files] == ["src/widget.py", "tests/test_widget.py"]
    assert snapshot.files[0].content == "print('safe'"
    assert snapshot.files[0].content_truncated is True
    assert any("page=2" in call for call in calls)


def test_file_pagination_stops_at_configured_page_bound() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pulls/7"):
            return response(request, 200, pr_payload())
        if request.url.path.endswith("/files"):
            return response(
                request,
                200,
                [{"filename": "a.py", "status": "modified", "additions": 1, "deletions": 0}],
                link='<https://api.github.test/next>; rel="next"',
            )
        if request.url.path.endswith("/contents/a.py"):
            return response(request, 404, {"message": "Not Found"})
        raise AssertionError(str(request.url))

    reader = GitHubReadClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
        max_pages=1,
        max_retries=0,
    )

    with pytest.raises(GitHubReadError, match="pagination limit"):
        reader.fetch_snapshot(
            parse_pull_request_url("https://github.com/acme/widgets/pull/7"), Limits()
        )


def test_transient_response_retries_with_bounded_delay() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return response(request, 503, {"secret": "must not escape"}, **{"retry-after": "2"})
        return response(request, 200, pr_payload())

    reader = GitHubReadClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
        max_retries=1,
        sleep=sleeps.append,
    )

    metadata = reader.get_metadata(parse_pull_request_url("https://github.com/acme/widgets/pull/7"))

    assert metadata.number == 7
    assert attempts == 2
    assert sleeps == [2.0]


def test_terminal_github_error_is_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(request, 401, {"token": "very-secret", "message": "Bad credentials"})

    reader = GitHubReadClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
        max_retries=0,
    )

    with pytest.raises(GitHubReadError) as caught:
        reader.get_metadata(parse_pull_request_url("https://github.com/acme/widgets/pull/7"))

    assert "very-secret" not in str(caught.value)
    assert "response" not in str(caught.value).lower()


def test_malformed_github_shape_fails_without_exposing_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"private": "source"}), request=request)

    reader = GitHubReadClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
        max_retries=0,
    )

    with pytest.raises(GitHubReadError) as caught:
        reader.get_metadata(parse_pull_request_url("https://github.com/acme/widgets/pull/7"))

    assert "source" not in str(caught.value)


def test_snapshot_fails_when_head_changes_during_retrieval() -> None:
    metadata_reads = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal metadata_reads
        if request.url.path.endswith("/pulls/7"):
            metadata_reads += 1
            sha = "a" * 40 if metadata_reads == 1 else "b" * 40
            return response(request, 200, pr_payload(sha))
        if request.url.path.endswith("/pulls/7/files"):
            return response(request, 200, [])
        raise AssertionError(str(request.url))

    reader = GitHubReadClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
        max_retries=0,
    )

    with pytest.raises(GitHubReadError) as caught:
        reader.fetch_snapshot(
            parse_pull_request_url("https://github.com/acme/widgets/pull/7"), Limits()
        )

    assert type(caught.value).__name__ == "SnapshotChangedError"
    assert metadata_reads == 2


def test_file_content_percent_encodes_special_path_characters() -> None:
    raw_paths: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        raw_paths.append(request.url.raw_path)
        return response(request, 404, {"message": "Not Found"})

    reader = GitHubReadClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
        max_retries=0,
    )

    content = reader.get_file_content(
        parse_pull_request_url("https://github.com/acme/widgets/pull/7"),
        "dir/name?#%.py",
        "a" * 40,
        100,
    )

    assert content == (None, False)
    assert raw_paths == [b"/repos/acme/widgets/contents/dir/name%3F%23%25.py?ref=" + b"a" * 40]
