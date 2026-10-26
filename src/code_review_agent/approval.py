"""Exact-body approval state and the controlled publication composition boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from code_review_agent.config import GitHubConfig
from code_review_agent.github import parse_pull_request_url
from code_review_agent.models import PublishResult, PullRequestRef, ReviewOutcome


def approval_fingerprint(
    url: str,
    head_sha: str,
    generated_markdown: str,
    edited_markdown: str,
) -> str:
    payload = json.dumps(
        [url, head_sha, generated_markdown, edited_markdown],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovalState:
    fingerprint: str | None = None

    @classmethod
    def approve(
        cls,
        url: str,
        head_sha: str,
        generated_markdown: str,
        edited_markdown: str,
    ) -> ApprovalState:
        return cls(approval_fingerprint(url, head_sha, generated_markdown, edited_markdown))

    def matches(
        self,
        url: str,
        head_sha: str,
        generated_markdown: str,
        edited_markdown: str,
    ) -> bool:
        return bool(
            self.fingerprint
            and self.fingerprint
            == approval_fingerprint(url, head_sha, generated_markdown, edited_markdown)
        )


def reconcile_approval(
    state: ApprovalState,
    url: str,
    head_sha: str,
    generated_markdown: str,
    edited_markdown: str,
) -> ApprovalState:
    if state.matches(url, head_sha, generated_markdown, edited_markdown):
        return state
    return ApprovalState()


def can_publish(
    config: GitHubConfig,
    outcome: ReviewOutcome,
    url: str,
    edited_markdown: str,
    approval: ApprovalState,
) -> bool:
    if not config.publish_enabled or not config.write_token:
        return False
    if outcome.aborted or outcome.markdown is None:
        return False
    return approval.matches(
        url,
        outcome.metadata.head_sha,
        outcome.markdown,
        edited_markdown,
    )


class Publisher(Protocol):
    def publish(
        self, ref: PullRequestRef, expected_head_sha: str, approved_body: str
    ) -> PublishResult: ...


class PublicationController:
    """Only this component composes approval state with the write-only publisher."""

    def __init__(self, config: GitHubConfig, publisher: Publisher) -> None:
        self._config = config
        self._publisher = publisher

    def publish(
        self,
        outcome: ReviewOutcome,
        url: str,
        edited_markdown: str,
        approval: ApprovalState,
    ) -> PublishResult:
        if not can_publish(self._config, outcome, url, edited_markdown, approval):
            raise PermissionError("Review is not approved for exact-body publication")
        ref = parse_pull_request_url(url)
        if (
            ref.owner != outcome.metadata.owner
            or ref.repo != outcome.metadata.repo
            or ref.number != outcome.metadata.number
        ):
            raise PermissionError("Approved URL does not match the reviewed pull request")
        return self._publisher.publish(ref, outcome.metadata.head_sha, edited_markdown)
