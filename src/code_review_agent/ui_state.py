"""Pure Streamlit workflow transitions, independent of rerun mechanics."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from code_review_agent.approval import ApprovalState
from code_review_agent.models import PullRequestMetadata, ReviewOutcome


@dataclass(frozen=True, slots=True)
class WorkflowState:
    url: str = ""
    preview: PullRequestMetadata | None = None
    outcome: ReviewOutcome | None = None
    generated_markdown: str = ""
    edited_markdown: str = ""
    approval: ApprovalState = field(default_factory=ApprovalState)
    comment_id: int | None = None
    comment_action: str | None = None

    def with_url(self, url: str) -> WorkflowState:
        if url == self.url:
            return self
        return WorkflowState(url=url)

    def with_preview(self, preview: PullRequestMetadata) -> WorkflowState:
        if preview == self.preview:
            return self
        return WorkflowState(url=self.url, preview=preview)

    def with_outcome(self, outcome: ReviewOutcome) -> WorkflowState:
        body = outcome.markdown or ""
        return WorkflowState(
            url=self.url,
            preview=outcome.metadata,
            outcome=outcome,
            generated_markdown=body,
            edited_markdown=body,
        )

    def with_markdown(self, generated: str, edited: str) -> WorkflowState:
        return replace(
            self,
            generated_markdown=generated,
            edited_markdown=edited,
            approval=ApprovalState(),
            comment_id=None,
            comment_action=None,
        )

    def with_edited_markdown(self, edited: str) -> WorkflowState:
        if edited == self.edited_markdown:
            return self
        return replace(
            self,
            edited_markdown=edited,
            approval=ApprovalState(),
            comment_id=None,
            comment_action=None,
        )

    def with_approval(self, approval: ApprovalState) -> WorkflowState:
        return replace(self, approval=approval)

    def with_comment(self, comment_id: int, action: str) -> WorkflowState:
        return replace(self, comment_id=comment_id, comment_action=action)
