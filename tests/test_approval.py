from __future__ import annotations

from dataclasses import replace

from code_review_agent.approval import (
    ApprovalState,
    PublicationController,
    approval_fingerprint,
    can_publish,
    reconcile_approval,
)
from code_review_agent.config import GitHubConfig, Limits
from code_review_agent.context import build_review_context
from code_review_agent.models import (
    ChangedFile,
    PublishResult,
    PullRequestMetadata,
    PullRequestSnapshot,
    ReviewerIdentity,
    ReviewOutcome,
    SpecialistResult,
    SpecialistStatus,
    StaticAnalysisResult,
)

URL = "https://github.com/acme/widgets/pull/7"
SHA = "a" * 40
GENERATED = "## Review\n\nGenerated body\n<!-- code-review-agent:acme/widgets#7 -->"
EDITED = "## Review\n\nApproved body\n<!-- code-review-agent:acme/widgets#7 -->"


def outcome(*, aborted: bool = False, partial: bool = False) -> ReviewOutcome:
    metadata = PullRequestMetadata(
        owner="acme",
        repo="widgets",
        number=7,
        url=URL,
        title="Safe parse",
        author="octocat",
        base_branch="main",
        head_branch="safe",
        head_sha=SHA,
    )
    context = build_review_context(
        PullRequestSnapshot(
            metadata=metadata,
            files=(
                ChangedFile(
                    path="src/widget.py",
                    status="modified",
                    additions=1,
                    deletions=0,
                    changes=1,
                    patch="@@ -1 +1 @@\n+safe = True",
                    content="safe = True\n",
                ),
            ),
        ),
        Limits(max_total_context_chars=10_000),
    )
    specialists = tuple(
        SpecialistResult(identity=identity, status=SpecialistStatus.SUCCESS, attempts=1)
        for identity in ReviewerIdentity
    )
    return ReviewOutcome(
        metadata=metadata,
        context=context,
        specialists=specialists,
        static_analysis=StaticAnalysisResult(
            available=False, tools=(), signals=(), summary="Unavailable"
        ),
        markdown=None if aborted else GENERATED,
        aborted=aborted,
        partial=partial,
    )


def enabled_config() -> GitHubConfig:
    return GitHubConfig(
        read_token=None,
        write_token="placeholder-token",
        publish_enabled=True,
        api_url="https://api.github.test",
    )


def test_fingerprint_changes_for_every_approval_input() -> None:
    baseline = approval_fingerprint(URL, SHA, GENERATED, EDITED)

    variants = {
        approval_fingerprint(URL + "x", SHA, GENERATED, EDITED),
        approval_fingerprint(URL, "b" * 40, GENERATED, EDITED),
        approval_fingerprint(URL, SHA, GENERATED + "x", EDITED),
        approval_fingerprint(URL, SHA, GENERATED, EDITED + "x"),
    }

    assert baseline not in variants
    assert len(variants) == 4


def test_approval_is_valid_only_for_exact_components() -> None:
    state = ApprovalState.approve(URL, SHA, GENERATED, EDITED)

    assert state.matches(URL, SHA, GENERATED, EDITED)
    assert not state.matches(URL, SHA, GENERATED, EDITED + "changed")


def test_reconcile_resets_approval_after_any_change() -> None:
    state = ApprovalState.approve(URL, SHA, GENERATED, EDITED)

    reset = reconcile_approval(state, URL, "b" * 40, GENERATED, EDITED)

    assert reset == ApprovalState()


def test_can_publish_requires_enabled_token_exact_approval_and_nonaborted_body() -> None:
    review = outcome()
    approved = ApprovalState.approve(URL, SHA, GENERATED, EDITED)

    assert can_publish(enabled_config(), review, URL, EDITED, approved) is True
    assert (
        can_publish(replace(enabled_config(), publish_enabled=False), review, URL, EDITED, approved)
        is False
    )
    assert (
        can_publish(replace(enabled_config(), write_token=None), review, URL, EDITED, approved)
        is False
    )
    assert can_publish(enabled_config(), outcome(aborted=True), URL, EDITED, approved) is False
    assert can_publish(enabled_config(), review, URL, EDITED + "changed", approved) is False


def test_disclosed_partial_review_can_be_approved() -> None:
    review = outcome(partial=True)
    approved = ApprovalState.approve(URL, SHA, GENERATED, EDITED)

    assert can_publish(enabled_config(), review, URL, EDITED, approved) is True


class FakePublisher:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str, str]] = []

    def publish(self, ref, head_sha: str, body: str) -> PublishResult:
        self.calls.append((ref, head_sha, body))
        return PublishResult(comment_id=123, action="created")


def test_controller_passes_exact_approved_body_and_returns_comment_id() -> None:
    publisher = FakePublisher()
    controller = PublicationController(enabled_config(), publisher)
    review = outcome()
    approved = ApprovalState.approve(URL, SHA, GENERATED, EDITED)

    result = controller.publish(review, URL, EDITED, approved)

    assert result.comment_id == 123
    assert result.action == "created"
    assert publisher.calls[0][1:] == (SHA, EDITED)


def test_controller_refuses_unapproved_request_before_publisher() -> None:
    publisher = FakePublisher()
    controller = PublicationController(enabled_config(), publisher)

    try:
        controller.publish(outcome(), URL, EDITED, ApprovalState())
    except PermissionError as exc:
        assert "not approved" in str(exc)
    else:
        raise AssertionError("expected publication refusal")

    assert publisher.calls == []
