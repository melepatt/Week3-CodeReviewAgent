from __future__ import annotations

from code_review_agent.approval import ApprovalState
from code_review_agent.models import PullRequestMetadata
from code_review_agent.ui_state import WorkflowState

URL = "https://github.com/acme/widgets/pull/7"


def preview(sha: str = "a" * 40) -> PullRequestMetadata:
    return PullRequestMetadata(
        owner="acme",
        repo="widgets",
        number=7,
        url=URL,
        title="Safe parse",
        author="octocat",
        base_branch="main",
        head_branch="safe",
        head_sha=sha,
    )


def approved_state() -> WorkflowState:
    state = WorkflowState().with_url(URL).with_preview(preview())
    state = state.with_markdown("generated", "edited")
    return state.with_approval(ApprovalState.approve(URL, "a" * 40, "generated", "edited"))


def test_url_change_clears_preview_review_approval_and_comment() -> None:
    changed = approved_state().with_comment(42, "created").with_url(URL.replace("7", "8"))

    assert changed.preview is None
    assert changed.outcome is None
    assert changed.generated_markdown == ""
    assert changed.edited_markdown == ""
    assert changed.approval == ApprovalState()
    assert changed.comment_id is None


def test_head_sha_change_clears_downstream_approval() -> None:
    state = approved_state()

    changed = state.with_preview(preview("b" * 40))

    assert changed.preview == preview("b" * 40)
    assert changed.approval == ApprovalState()
    assert changed.generated_markdown == ""


def test_edited_markdown_change_resets_approval() -> None:
    changed = approved_state().with_edited_markdown("different")

    assert changed.edited_markdown == "different"
    assert changed.approval == ApprovalState()


def test_unchanged_values_preserve_state() -> None:
    state = approved_state()

    assert state.with_url(URL) == state
    assert state.with_preview(preview()) == state
    assert state.with_edited_markdown("edited") == state
