"""Application service composing read-only retrieval and review orchestration."""

from __future__ import annotations

from typing import Protocol

from code_review_agent.config import Limits
from code_review_agent.context import build_review_context
from code_review_agent.github import SnapshotChangedError, parse_pull_request_url
from code_review_agent.graph import ReviewerSet, build_review_graph, run_review_graph
from code_review_agent.models import (
    PullRequestMetadata,
    PullRequestRef,
    PullRequestSnapshot,
    ReviewOutcome,
)
from code_review_agent.static_analysis import run_static_checks


class PullRequestReader(Protocol):
    def get_metadata(self, ref: PullRequestRef) -> PullRequestMetadata: ...

    def fetch_snapshot(self, ref: PullRequestRef, limits: Limits) -> PullRequestSnapshot: ...


class ReviewService:
    def __init__(
        self,
        reader: PullRequestReader,
        reviewers: ReviewerSet,
        limits: Limits,
    ) -> None:
        self._reader = reader
        self._limits = limits
        self._graph = build_review_graph(reviewers)

    def preview(self, url: str) -> PullRequestMetadata:
        return self._reader.get_metadata(parse_pull_request_url(url))

    def run(self, url: str, *, expected_head_sha: str | None = None) -> ReviewOutcome:
        ref = parse_pull_request_url(url)
        snapshot = self._reader.fetch_snapshot(ref, self._limits)
        if (
            expected_head_sha is not None
            and snapshot.metadata.head_sha.casefold() != expected_head_sha.casefold()
        ):
            raise SnapshotChangedError(
                "Pull-request head SHA does not match the pinned evaluation snapshot"
            )
        context = build_review_context(snapshot, self._limits)
        static_analysis = run_static_checks(context)
        return run_review_graph(self._graph, context, static_analysis)
