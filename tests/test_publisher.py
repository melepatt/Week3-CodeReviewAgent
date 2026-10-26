from __future__ import annotations

import httpx
import pytest

from code_review_agent.config import GitHubConfig
from code_review_agent.github import (
    GitHubPublisher,
    PublicationError,
    parse_pull_request_url,
    stable_marker,
)

REF = parse_pull_request_url("https://github.com/acme/widgets/pull/7")
SHA = "a" * 40
WRITE_TOKEN = "write-token"


def reply(request: httpx.Request, status: int, payload: object) -> httpx.Response:
    return httpx.Response(status, json=payload, request=request)


def config(*, enabled: bool = True, token: str | None = WRITE_TOKEN) -> GitHubConfig:
    return GitHubConfig(
        read_token=None,
        write_token=token,
        publish_enabled=enabled,
        api_url="https://api.github.test",
    )


def approved_body() -> str:
    return f"## Code review\n\nNo blocking findings.\n\n{stable_marker(REF)}"


def test_publication_is_default_off_before_any_request() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        raise AssertionError("network must not be reached")

    publisher = GitHubPublisher(
        config(enabled=False),
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
    )

    with pytest.raises(PublicationError, match="disabled"):
        publisher.publish(REF, SHA, approved_body())
    assert requests == 0


def test_head_sha_change_refuses_publication() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return reply(request, 200, {"login": "reviewer"})
        if request.url.path.endswith("/pulls/7"):
            return reply(request, 200, {"head": {"sha": "b" * 40}})
        raise AssertionError(str(request.url))

    publisher = GitHubPublisher(
        config(),
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
    )

    with pytest.raises(PublicationError, match="head SHA changed"):
        publisher.publish(REF, SHA, approved_body())


def test_existing_same_author_marker_comment_is_updated() -> None:
    methods: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append((request.method, request.url.path))
        if request.url.path == "/user":
            return reply(request, 200, {"login": "reviewer"})
        if request.url.path.endswith("/pulls/7"):
            return reply(request, 200, {"head": {"sha": SHA}})
        if request.url.path.endswith("/issues/7/comments"):
            return reply(
                request,
                200,
                [{"id": 91, "body": approved_body(), "user": {"login": "reviewer"}}],
            )
        if request.url.path.endswith("/issues/comments/91"):
            return reply(request, 200, {"id": 91})
        raise AssertionError(str(request.url))

    publisher = GitHubPublisher(
        config(),
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
    )

    result = publisher.publish(REF, SHA, approved_body())

    assert result.comment_id == 91
    assert result.action == "updated"
    assert ("PATCH", "/repos/acme/widgets/issues/comments/91") in methods


def test_foreign_marker_is_not_overwritten_and_new_comment_is_created() -> None:
    patched = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal patched
        if request.url.path == "/user":
            return reply(request, 200, {"login": "reviewer"})
        if request.url.path.endswith("/pulls/7"):
            return reply(request, 200, {"head": {"sha": SHA}})
        if request.method == "GET" and request.url.path.endswith("/issues/7/comments"):
            return reply(
                request,
                200,
                [{"id": 22, "body": approved_body(), "user": {"login": "someone-else"}}],
            )
        if request.method == "POST" and request.url.path.endswith("/issues/7/comments"):
            return reply(request, 201, {"id": 92})
        if request.method == "PATCH":
            patched = True
        raise AssertionError(str(request.url))

    publisher = GitHubPublisher(
        config(),
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
    )

    result = publisher.publish(REF, SHA, approved_body())

    assert result.comment_id == 92
    assert result.action == "created"
    assert patched is False


def test_multiple_same_author_marker_comments_abort_without_write() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return reply(request, 200, {"login": "reviewer"})
        if request.url.path.endswith("/pulls/7"):
            return reply(request, 200, {"head": {"sha": SHA}})
        if request.method == "GET" and request.url.path.endswith("/issues/7/comments"):
            item = {"body": approved_body(), "user": {"login": "reviewer"}}
            return reply(request, 200, [{"id": 1, **item}, {"id": 2, **item}])
        raise AssertionError("write must not happen")

    publisher = GitHubPublisher(
        config(),
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
    )

    with pytest.raises(PublicationError, match="multiple"):
        publisher.publish(REF, SHA, approved_body())


def test_ambiguous_create_timeout_searches_marker_before_retrying() -> None:
    comment_gets = 0
    posts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal comment_gets, posts
        if request.url.path == "/user":
            return reply(request, 200, {"login": "reviewer"})
        if request.url.path.endswith("/pulls/7"):
            return reply(request, 200, {"head": {"sha": SHA}})
        if request.method == "GET" and request.url.path.endswith("/issues/7/comments"):
            comment_gets += 1
            if comment_gets == 1:
                return reply(request, 200, [])
            return reply(
                request,
                200,
                [{"id": 93, "body": approved_body(), "user": {"login": "reviewer"}}],
            )
        if request.method == "POST" and request.url.path.endswith("/issues/7/comments"):
            posts += 1
            raise httpx.ReadTimeout("ambiguous", request=request)
        raise AssertionError(str(request.url))

    publisher = GitHubPublisher(
        config(),
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
    )

    result = publisher.publish(REF, SHA, approved_body())

    assert result.comment_id == 93
    assert result.action == "recovered"
    assert posts == 1
    assert comment_gets == 2


def test_body_must_already_contain_exact_marker() -> None:
    publisher = GitHubPublisher(config(), http_client=httpx.Client())

    with pytest.raises(PublicationError, match="marker"):
        publisher.publish(REF, SHA, "## Code review\n\nNo marker")


@pytest.mark.parametrize("existing_comment", [False, True])
def test_head_is_rechecked_immediately_before_create_or_update(existing_comment: bool) -> None:
    pull_reads = 0
    writes = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal pull_reads, writes
        if request.url.path == "/user":
            return reply(request, 200, {"login": "reviewer"})
        if request.url.path.endswith("/pulls/7"):
            pull_reads += 1
            sha = SHA if pull_reads == 1 else "b" * 40
            return reply(request, 200, {"head": {"sha": sha}})
        if request.method == "GET" and request.url.path.endswith("/issues/7/comments"):
            comments = (
                [{"id": 91, "body": approved_body(), "user": {"login": "reviewer"}}]
                if existing_comment
                else []
            )
            return reply(request, 200, comments)
        if request.method in {"PATCH", "POST"}:
            writes += 1
            return reply(request, 200, {"id": 91})
        raise AssertionError(str(request.url))

    publisher = GitHubPublisher(
        config(),
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
    )

    with pytest.raises(PublicationError) as caught:
        publisher.publish(REF, SHA, approved_body())

    assert type(caught.value).__name__ == "HeadChangedError"
    assert pull_reads == 2
    assert writes == 0


def test_head_is_rechecked_before_retry_after_ambiguous_timeout() -> None:
    pull_reads = 0
    comment_reads = 0
    posts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal pull_reads, comment_reads, posts
        if request.url.path == "/user":
            return reply(request, 200, {"login": "reviewer"})
        if request.url.path.endswith("/pulls/7"):
            pull_reads += 1
            sha = SHA if pull_reads < 3 else "b" * 40
            return reply(request, 200, {"head": {"sha": sha}})
        if request.method == "GET" and request.url.path.endswith("/issues/7/comments"):
            comment_reads += 1
            return reply(request, 200, [])
        if request.method == "POST" and request.url.path.endswith("/issues/7/comments"):
            posts += 1
            raise httpx.ReadTimeout("ambiguous", request=request)
        raise AssertionError(str(request.url))

    publisher = GitHubPublisher(
        config(),
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.github.test"
        ),
    )

    with pytest.raises(PublicationError) as caught:
        publisher.publish(REF, SHA, approved_body())

    assert type(caught.value).__name__ == "HeadChangedError"
    assert posts == 1
    assert comment_reads == 2
    assert pull_reads == 3
