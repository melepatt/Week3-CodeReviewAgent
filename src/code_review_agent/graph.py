"""Concurrent read-only LangGraph review orchestration."""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from code_review_agent.markdown import render_review
from code_review_agent.models import (
    ReviewContext,
    ReviewerIdentity,
    ReviewOutcome,
    SpecialistResult,
    SpecialistStatus,
    StaticAnalysisResult,
)
from code_review_agent.validation import validate_findings

Reviewer = Callable[[ReviewContext], SpecialistResult]


@dataclass(frozen=True, slots=True)
class ReviewerSet:
    correctness: Reviewer
    security: Reviewer
    test_coverage: Reviewer


class GraphState(TypedDict, total=False):
    context: ReviewContext
    static_analysis: StaticAnalysisResult
    specialist_results: Annotated[list[SpecialistResult], operator.add]
    outcome: ReviewOutcome


def build_review_graph(reviewers: ReviewerSet):
    """Compile a graph that has no access to any GitHub write component."""

    workflow = StateGraph(GraphState)

    def node(reviewer: Reviewer):
        def run(state: GraphState) -> GraphState:
            return {"specialist_results": [reviewer(state["context"])]}

        return run

    workflow.add_node("correctness", node(reviewers.correctness))
    workflow.add_node("security", node(reviewers.security))
    workflow.add_node("test_coverage", node(reviewers.test_coverage))

    def finalize(state: GraphState) -> GraphState:
        order = {identity: index for index, identity in enumerate(ReviewerIdentity)}
        specialists = tuple(
            sorted(state.get("specialist_results", []), key=lambda item: order[item.identity])
        )
        failed = [item for item in specialists if item.status is SpecialistStatus.FAILED]
        if len(failed) >= 2:
            outcome = ReviewOutcome(
                metadata=state["context"].metadata,
                context=state["context"],
                specialists=specialists,
                static_analysis=state["static_analysis"],
                aborted=True,
            )
            return {"outcome": outcome}

        candidates = tuple(
            finding
            for specialist in specialists
            if specialist.status is SpecialistStatus.SUCCESS
            for finding in specialist.findings
        )
        validation = validate_findings(candidates, state["context"])
        markdown = render_review(
            state["context"].metadata,
            validation.accepted,
            specialists,
            state["static_analysis"],
        )
        outcome = ReviewOutcome(
            metadata=state["context"].metadata,
            context=state["context"],
            specialists=specialists,
            static_analysis=state["static_analysis"],
            accepted=validation.accepted,
            rejected=validation.rejected,
            markdown=markdown,
            partial=len(failed) == 1,
        )
        return {"outcome": outcome}

    workflow.add_node("finalize", finalize)
    for name in ("correctness", "security", "test_coverage"):
        workflow.add_edge(START, name)
    workflow.add_edge(["correctness", "security", "test_coverage"], "finalize")
    workflow.add_edge("finalize", END)
    return workflow.compile()


def run_review_graph(
    graph,
    context: ReviewContext,
    static_analysis: StaticAnalysisResult,
) -> ReviewOutcome:
    state = graph.invoke({"context": context, "static_analysis": static_analysis})
    return state["outcome"]
