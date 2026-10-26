"""Specialist entry points used by graph nodes."""

from __future__ import annotations

from code_review_agent.llm import StructuredModelClient
from code_review_agent.models import (
    ReviewContext,
    ReviewerIdentity,
    SpecialistResult,
)


def run_specialist(
    identity: ReviewerIdentity,
    context: ReviewContext,
    client: StructuredModelClient,
) -> SpecialistResult:
    return client.review(identity, context)
