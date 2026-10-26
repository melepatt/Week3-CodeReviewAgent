from __future__ import annotations

from dataclasses import dataclass

import pytest

from code_review_agent.config import Limits
from code_review_agent.github import GitHubReadError
from code_review_agent.graph import ReviewerSet
from code_review_agent.models import (
    ChangedFile,
    PullRequestMetadata,
    PullRequestRef,
    PullRequestSnapshot,
    ReviewerIdentity,
    SpecialistResult,
    SpecialistStatus,
)
from code_review_agent.service import ReviewService


def metadata() -> PullRequestMetadata:
    return PullRequestMetadata(
        owner="acme",
        repo="widgets",
        number=7,
        url="https://github.com/acme/widgets/pull/7",
        title="Safe parse",
        author="octocat",
        base_branch="main",
        head_branch="safe",
        head_sha="a" * 40,
    )


def snapshot() -> PullRequestSnapshot:
    return PullRequestSnapshot(
        metadata=metadata(),
        files=(
            ChangedFile(
                path="src/widget.py",
                status="modified",
                additions=1,
                deletions=0,
                changes=1,
                patch="@@ -1 +1 @@\n+value = 1",
                content="value = 1\n",
            ),
        ),
    )


@dataclass
class FakeReader:
    metadata_calls: int = 0
    snapshot_calls: int = 0

    def get_metadata(self, ref: PullRequestRef) -> PullRequestMetadata:
        self.metadata_calls += 1
        assert ref.number == 7
        return metadata()

    def fetch_snapshot(self, ref: PullRequestRef, limits: Limits) -> PullRequestSnapshot:
        self.snapshot_calls += 1
        assert ref.number == 7
        assert limits.max_files == 5
        return snapshot()


def successful_reviewers() -> ReviewerSet:
    def run(identity: ReviewerIdentity):
        return lambda context: SpecialistResult(
            identity=identity, status=SpecialistStatus.SUCCESS, attempts=1
        )

    return ReviewerSet(
        correctness=run(ReviewerIdentity.CORRECTNESS),
        security=run(ReviewerIdentity.SECURITY),
        test_coverage=run(ReviewerIdentity.TEST_COVERAGE),
    )


def test_preview_fetches_only_metadata() -> None:
    reader = FakeReader()
    service = ReviewService(reader, successful_reviewers(), Limits(max_files=5))

    preview = service.preview("https://github.com/acme/widgets/pull/7")

    assert preview == metadata()
    assert reader.metadata_calls == 1
    assert reader.snapshot_calls == 0


def test_run_fetches_snapshot_builds_context_and_returns_outcome() -> None:
    reader = FakeReader()
    service = ReviewService(reader, successful_reviewers(), Limits(max_files=5))

    outcome = service.run("https://github.com/acme/widgets/pull/7")

    assert reader.snapshot_calls == 1
    assert outcome.metadata.head_sha == "a" * 40
    assert outcome.aborted is False
    assert outcome.markdown is not None


def test_run_rejects_snapshot_that_does_not_match_expected_head() -> None:
    reader = FakeReader()
    service = ReviewService(reader, successful_reviewers(), Limits(max_files=5))

    with pytest.raises(GitHubReadError) as caught:
        service.run("https://github.com/acme/widgets/pull/7", expected_head_sha="b" * 40)

    assert type(caught.value).__name__ == "SnapshotChangedError"
