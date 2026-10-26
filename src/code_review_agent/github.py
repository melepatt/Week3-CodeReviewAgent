"""Strict GitHub URL parsing, bounded reads, and isolated publication."""

from __future__ import annotations

import base64
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import httpx

from code_review_agent.config import GitHubConfig, Limits
from code_review_agent.models import (
    ChangedFile,
    PublishResult,
    PullRequestMetadata,
    PullRequestRef,
    PullRequestSnapshot,
)

_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9_.-])?"
_PULL_PATH = re.compile(rf"^/({_NAME})/({_NAME})/pull/([1-9][0-9]*)$")
_TRANSIENT = {429, 500, 502, 503, 504}


class PullRequestUrlError(ValueError):
    """Raised when a URL is not the canonical GitHub pull-request form."""


class GitHubReadError(RuntimeError):
    """Sanitized GitHub read failure."""


class SnapshotChangedError(GitHubReadError):
    """The pull-request head changed while a review snapshot was being assembled."""


class PublicationError(RuntimeError):
    """Sanitized refusal or failure at the write boundary."""


class HeadChangedError(PublicationError):
    """The pull-request head no longer matches the approved snapshot."""


def parse_pull_request_url(url: str) -> PullRequestRef:
    if not isinstance(url, str) or not url:
        raise PullRequestUrlError("A canonical GitHub pull-request URL is required")
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc != "github.com"
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or unquote(parts.path) != parts.path
    ):
        raise PullRequestUrlError("URL must use the canonical https://github.com form")
    match = _PULL_PATH.fullmatch(parts.path)
    if not match:
        raise PullRequestUrlError("URL must match https://github.com/{owner}/{repo}/pull/{number}")
    owner, repo, number_text = match.groups()
    return PullRequestRef(
        owner=owner,
        repo=repo,
        number=int(number_text),
        canonical_url=f"https://github.com/{owner}/{repo}/pull/{number_text}",
    )


def stable_marker(ref: PullRequestRef) -> str:
    return f"<!-- code-review-agent:{ref.owner}/{ref.repo}#{ref.number} -->"


def _safe_retry_after(response: httpx.Response, attempt: int) -> float:
    raw = response.headers.get("retry-after")
    if raw:
        try:
            return min(max(float(raw), 0.0), 10.0)
        except ValueError:
            pass
    return min(float(2**attempt), 10.0)


class GitHubReadClient:
    """GET-only GitHub client with bounded pagination and transient retries."""

    def __init__(
        self,
        read_token: str | None = None,
        *,
        api_url: str = "https://api.github.com",
        http_client: httpx.Client | None = None,
        max_pages: int = 10,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "week3-code-review-agent/0.1",
        }
        if read_token:
            headers["Authorization"] = f"Bearer {read_token}"
        self._client = http_client or httpx.Client(
            base_url=api_url.rstrip("/"), headers=headers, timeout=20.0
        )
        self._max_pages = max_pages
        self._max_retries = max_retries
        self._sleep = sleep

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        allow_404: bool = False,
    ) -> httpx.Response | None:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.get(path, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self._max_retries:
                    raise GitHubReadError(f"GitHub GET failed for {path}") from exc
                self._sleep(min(float(2**attempt), 10.0))
                continue
            if allow_404 and response.status_code == 404:
                return None
            if 200 <= response.status_code < 300:
                return response
            if response.status_code in _TRANSIENT and attempt < self._max_retries:
                self._sleep(_safe_retry_after(response, attempt))
                continue
            raise GitHubReadError(
                f"GitHub GET failed for {path} with status {response.status_code}"
            )
        raise GitHubReadError(f"GitHub GET failed for {path}")

    @staticmethod
    def _json(response: httpx.Response, *, expected: type) -> Any:
        try:
            value = response.json()
        except ValueError as exc:
            raise GitHubReadError("GitHub returned malformed JSON") from exc
        if not isinstance(value, expected):
            raise GitHubReadError("GitHub returned an unexpected data shape")
        return value

    def get_metadata(self, ref: PullRequestRef) -> PullRequestMetadata:
        path = f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}"
        response = self._get(path)
        assert response is not None
        payload = self._json(response, expected=dict)
        try:
            return PullRequestMetadata(
                owner=ref.owner,
                repo=ref.repo,
                number=int(payload["number"]),
                url=str(payload["html_url"]),
                title=str(payload["title"]),
                body=str(payload.get("body") or ""),
                author=str(payload["user"]["login"]),
                base_branch=str(payload["base"]["ref"]),
                head_branch=str(payload["head"]["ref"]),
                head_sha=str(payload["head"]["sha"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GitHubReadError("GitHub returned incomplete pull-request metadata") from exc

    def _list_files(self, ref: PullRequestRef, limits: Limits) -> tuple[list[dict[str, Any]], bool]:
        path = f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/files"
        items: list[dict[str, Any]] = []
        for page in range(1, min(self._max_pages, limits.max_pages) + 1):
            response = self._get(path, params={"per_page": 100, "page": page})
            assert response is not None
            payload = self._json(response, expected=list)
            if not all(isinstance(item, dict) for item in payload):
                raise GitHubReadError("GitHub returned an unexpected changed-file shape")
            remaining = max(limits.max_files - len(items), 0)
            items.extend(payload[:remaining])
            files_truncated = len(payload) > remaining
            has_next = 'rel="next"' in response.headers.get("link", "")
            if files_truncated:
                return items, True
            if not has_next:
                return items, False
            if page >= min(self._max_pages, limits.max_pages):
                raise GitHubReadError("GitHub file pagination limit reached")
        return items, False

    def get_file_content(
        self, ref: PullRequestRef, path: str, sha: str, max_chars: int
    ) -> tuple[str | None, bool]:
        encoded_path = quote(path, safe="/")
        api_path = f"/repos/{ref.owner}/{ref.repo}/contents/{encoded_path}"
        response = self._get(api_path, params={"ref": sha}, allow_404=True)
        if response is None:
            return None, False
        payload = self._json(response, expected=dict)
        if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
            return None, False
        try:
            decoded = base64.b64decode(payload["content"], validate=False).decode(
                "utf-8", errors="replace"
            )
        except (ValueError, TypeError):
            return None, False
        return decoded[:max_chars], len(decoded) > max_chars

    def fetch_snapshot(self, ref: PullRequestRef, limits: Limits) -> PullRequestSnapshot:
        metadata = self.get_metadata(ref)
        raw_files, files_truncated = self._list_files(ref, limits)
        files: list[ChangedFile] = []
        total_remaining = limits.max_total_context_chars
        for raw in raw_files:
            try:
                path = str(raw["filename"])
                status = str(raw["status"])
                raw_patch = raw.get("patch")
                patch = str(raw_patch) if raw_patch is not None else None
                patch_truncated = bool(patch and len(patch) > limits.max_patch_chars)
                if patch is not None:
                    patch = patch[: min(limits.max_patch_chars, total_remaining)]
                    total_remaining = max(total_remaining - len(patch), 0)
                content = None
                content_truncated = False
                if status != "removed" and total_remaining > 0:
                    content, content_truncated = self.get_file_content(
                        ref,
                        path,
                        metadata.head_sha,
                        min(limits.max_file_content_chars, total_remaining),
                    )
                    total_remaining = max(total_remaining - len(content or ""), 0)
                files.append(
                    ChangedFile(
                        path=path,
                        previous_path=(
                            str(raw["previous_filename"])
                            if raw.get("previous_filename") is not None
                            else None
                        ),
                        status=status,
                        additions=int(raw.get("additions", 0)),
                        deletions=int(raw.get("deletions", 0)),
                        changes=int(raw.get("changes", 0)),
                        patch=patch,
                        patch_truncated=patch_truncated,
                        content=content,
                        content_truncated=content_truncated,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise GitHubReadError("GitHub returned incomplete changed-file metadata") from exc
        current = self.get_metadata(ref)
        if current.head_sha.casefold() != metadata.head_sha.casefold():
            raise SnapshotChangedError(
                "Pull-request head SHA changed while retrieving the review snapshot"
            )
        return PullRequestSnapshot(
            metadata=metadata, files=tuple(files), files_truncated=files_truncated
        )


class GitHubPublisher:
    """Write-only boundary called after exact-body approval, never from the graph."""

    def __init__(
        self,
        config: GitHubConfig,
        *,
        http_client: httpx.Client | None = None,
        max_pages: int = 10,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "week3-code-review-agent/0.1",
        }
        if config.write_token:
            headers["Authorization"] = f"Bearer {config.write_token}"
        self._config = config
        self._client = http_client or httpx.Client(
            base_url=config.api_url.rstrip("/"), headers=headers, timeout=20.0
        )
        self._max_pages = max_pages

    @staticmethod
    def _payload(response: httpx.Response, expected: type) -> Any:
        if not 200 <= response.status_code < 300:
            raise PublicationError(f"GitHub publication failed with status {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise PublicationError("GitHub publication returned malformed JSON") from exc
        if not isinstance(payload, expected):
            raise PublicationError("GitHub publication returned an unexpected data shape")
        return payload

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise PublicationError(f"GitHub pre-publication read failed for {path}") from exc
        return self._payload(response, object)

    def _comments(self, ref: PullRequestRef) -> list[dict[str, Any]]:
        path = f"/repos/{ref.owner}/{ref.repo}/issues/{ref.number}/comments"
        comments: list[dict[str, Any]] = []
        for page in range(1, self._max_pages + 1):
            response = self._client.get(path, params={"per_page": 100, "page": page})
            payload = self._payload(response, list)
            if not all(isinstance(item, dict) for item in payload):
                raise PublicationError("GitHub comments had an unexpected shape")
            comments.extend(payload)
            if 'rel="next"' not in response.headers.get("link", ""):
                return comments
        raise PublicationError("GitHub comment pagination limit reached")

    def _matching_comments(
        self, ref: PullRequestRef, marker: str, login: str
    ) -> list[dict[str, Any]]:
        matches = []
        for comment in self._comments(ref):
            body = comment.get("body")
            author = comment.get("user")
            author_login = author.get("login") if isinstance(author, dict) else None
            if (
                isinstance(body, str)
                and marker in body
                and isinstance(author_login, str)
                and author_login.casefold() == login.casefold()
            ):
                matches.append(comment)
        return matches

    def _assert_head(self, ref: PullRequestRef, expected_head_sha: str) -> None:
        pull = self._get_json(f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}")
        try:
            current_sha = str(pull["head"]["sha"])
        except (KeyError, TypeError) as exc:
            raise PublicationError("GitHub head response was incomplete") from exc
        if current_sha != expected_head_sha:
            raise HeadChangedError(
                "Pull-request head SHA changed; regenerate and approve the review"
            )

    def publish(
        self, ref: PullRequestRef, expected_head_sha: str, approved_body: str
    ) -> PublishResult:
        if not self._config.publish_enabled:
            raise PublicationError("GitHub publishing is disabled")
        if not self._config.write_token:
            raise PublicationError("GitHub publishing requires a write token")
        marker = stable_marker(ref)
        if marker not in approved_body:
            raise PublicationError("The approved body does not contain the stable marker")

        user = self._get_json("/user")
        try:
            login = str(user["login"])
        except (KeyError, TypeError) as exc:
            raise PublicationError("GitHub identity response was incomplete") from exc
        self._assert_head(ref, expected_head_sha)

        matches = self._matching_comments(ref, marker, login)
        if len(matches) > 1:
            raise PublicationError("Found multiple matching comments from the publishing identity")
        if matches:
            try:
                comment_id = int(matches[0]["id"])
            except (KeyError, TypeError, ValueError) as exc:
                raise PublicationError("Matching comment metadata was incomplete") from exc
            self._assert_head(ref, expected_head_sha)
            response = self._client.patch(
                f"/repos/{ref.owner}/{ref.repo}/issues/comments/{comment_id}",
                json={"body": approved_body},
            )
            payload = self._payload(response, dict)
            return PublishResult(comment_id=int(payload["id"]), action="updated")

        path = f"/repos/{ref.owner}/{ref.repo}/issues/{ref.number}/comments"
        try:
            self._assert_head(ref, expected_head_sha)
            response = self._client.post(path, json={"body": approved_body})
        except httpx.TimeoutException as exc:
            recovered = self._matching_comments(ref, marker, login)
            if len(recovered) == 1:
                return PublishResult(comment_id=int(recovered[0]["id"]), action="recovered")
            if len(recovered) > 1:
                raise PublicationError(
                    "Ambiguous create timeout found multiple matching comments"
                ) from exc
            try:
                self._assert_head(ref, expected_head_sha)
                response = self._client.post(path, json={"body": approved_body})
            except httpx.HTTPError as exc:
                raise PublicationError(
                    "GitHub comment creation failed after timeout recovery"
                ) from exc
        except httpx.HTTPError as exc:
            raise PublicationError("GitHub comment creation failed") from exc
        payload = self._payload(response, dict)
        try:
            return PublishResult(comment_id=int(payload["id"]), action="created")
        except (KeyError, TypeError, ValueError) as exc:
            raise PublicationError("Created comment metadata was incomplete") from exc
