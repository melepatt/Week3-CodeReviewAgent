from __future__ import annotations

import threading
import time

from code_review_agent.config import Limits
from code_review_agent.context import build_review_context
from code_review_agent.graph import ReviewerSet, build_review_graph, run_review_graph
from code_review_agent.models import (
    Category,
    ChangedFile,
    Finding,
    PullRequestMetadata,
    PullRequestSnapshot,
    ReviewerIdentity,
    Severity,
    SpecialistResult,
    SpecialistStatus,
    StaticAnalysisResult,
    StaticToolStatus,
)


def context():
    metadata = PullRequestMetadata(
        owner="acme",
        repo="widgets",
        number=7,
        url="https://github.com/acme/widgets/pull/7",
        title="Parse widget input",
        author="octocat",
        base_branch="main",
        head_branch="parse",
        head_sha="a" * 40,
    )
    file = ChangedFile(
        path="src/widget.py",
        status="modified",
        additions=2,
        deletions=0,
        changes=2,
        patch=(
            "@@ -10,2 +10,2 @@ def parse_widget(raw):\n"
            "+def parse_widget(raw):\n"
            "+    return int(raw)"
        ),
        content="\n".join(["# filler"] * 9 + ["def parse_widget(raw):", "    return int(raw)"]),
    )
    return build_review_context(
        PullRequestSnapshot(metadata=metadata, files=(file,)),
        Limits(max_total_context_chars=10_000),
    )


def static_result() -> StaticAnalysisResult:
    return StaticAnalysisResult(
        available=True,
        tools=(StaticToolStatus(name="python-ast", available=True, detail="parsed"),),
        signals=(),
        summary="No static signals.",
    )


def valid_finding() -> Finding:
    return Finding(
        identifier="correctness.parse-empty",
        category=Category.CORRECTNESS,
        severity=Severity.HIGH,
        title="Empty widget input raises unexpectedly",
        path="src/widget.py",
        start_line=10,
        end_line=11,
        subject="parse_widget",
        evidence="parse_widget converts unchecked empty input directly with int",
        impact="A normal invalid widget request can raise unexpectedly",
        recommendation="Validate parse_widget input before converting it with int",
        reviewer=ReviewerIdentity.CORRECTNESS,
    )


def success(identity: ReviewerIdentity, findings: tuple[Finding, ...] = ()) -> SpecialistResult:
    return SpecialistResult(
        identity=identity,
        status=SpecialistStatus.SUCCESS,
        findings=findings,
        attempts=1,
    )


def failure(identity: ReviewerIdentity) -> SpecialistResult:
    return SpecialistResult(
        identity=identity,
        status=SpecialistStatus.FAILED,
        attempts=1,
        failure="Malformed structured response after 1 attempts",
    )


def test_graph_fans_out_reviewers_concurrently_and_joins_results() -> None:
    active = 0
    maximum = 0
    lock = threading.Lock()

    def reviewer(identity: ReviewerIdentity):
        def run(review_context):
            nonlocal active, maximum
            assert review_context == context()
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            findings = (valid_finding(),) if identity is ReviewerIdentity.CORRECTNESS else ()
            return success(identity, findings)

        return run

    reviewers = ReviewerSet(
        correctness=reviewer(ReviewerIdentity.CORRECTNESS),
        security=reviewer(ReviewerIdentity.SECURITY),
        test_coverage=reviewer(ReviewerIdentity.TEST_COVERAGE),
    )

    outcome = run_review_graph(build_review_graph(reviewers), context(), static_result())

    assert maximum >= 2
    assert outcome.aborted is False
    assert outcome.partial is False
    assert outcome.accepted == (valid_finding(),)
    assert outcome.markdown is not None


def test_one_specialist_failure_produces_disclosed_partial_review() -> None:
    reviewers = ReviewerSet(
        correctness=lambda ctx: success(ReviewerIdentity.CORRECTNESS, (valid_finding(),)),
        security=lambda ctx: failure(ReviewerIdentity.SECURITY),
        test_coverage=lambda ctx: success(ReviewerIdentity.TEST_COVERAGE),
    )

    outcome = run_review_graph(build_review_graph(reviewers), context(), static_result())

    assert outcome.aborted is False
    assert outcome.partial is True
    assert outcome.markdown is not None
    assert "Partial review: 1 specialist failed" in outcome.markdown


def test_two_specialist_failures_abort_with_diagnostics_and_no_body() -> None:
    reviewers = ReviewerSet(
        correctness=lambda ctx: success(ReviewerIdentity.CORRECTNESS, (valid_finding(),)),
        security=lambda ctx: failure(ReviewerIdentity.SECURITY),
        test_coverage=lambda ctx: failure(ReviewerIdentity.TEST_COVERAGE),
    )

    outcome = run_review_graph(build_review_graph(reviewers), context(), static_result())

    assert outcome.aborted is True
    assert outcome.partial is False
    assert outcome.markdown is None
    assert outcome.accepted == ()
    assert len(outcome.specialists) == 3
    assert outcome.specialists[0].findings == (valid_finding(),)


def test_graph_has_no_publication_node_or_write_dependency() -> None:
    reviewers = ReviewerSet(
        correctness=lambda ctx: success(ReviewerIdentity.CORRECTNESS),
        security=lambda ctx: success(ReviewerIdentity.SECURITY),
        test_coverage=lambda ctx: success(ReviewerIdentity.TEST_COVERAGE),
    )

    graph = build_review_graph(reviewers).get_graph()

    assert set(graph.nodes) == {
        "__start__",
        "correctness",
        "security",
        "test_coverage",
        "finalize",
        "__end__",
    }
    assert not any("publish" in name or "github" in name for name in graph.nodes)
