from __future__ import annotations

from code_review_agent.markdown import render_review
from code_review_agent.models import (
    Category,
    Finding,
    PullRequestMetadata,
    ReviewerIdentity,
    Severity,
    SpecialistResult,
    SpecialistStatus,
    StaticAnalysisResult,
    StaticToolStatus,
)


def metadata() -> PullRequestMetadata:
    return PullRequestMetadata(
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


def finding(identifier: str, severity: Severity, line: int) -> Finding:
    return Finding(
        identifier=identifier,
        category=Category.CORRECTNESS,
        severity=severity,
        title="Widget parsing can raise unexpectedly",
        path="src/widget.py",
        start_line=line,
        end_line=line,
        subject="parse_widget",
        evidence="parse_widget sends an unchecked value directly into int",
        impact="A normal invalid widget request can raise unexpectedly",
        recommendation="Validate parse_widget input before converting the value",
        reviewer=ReviewerIdentity.CORRECTNESS,
    )


def statuses() -> tuple[SpecialistResult, ...]:
    return (
        SpecialistResult(
            identity=ReviewerIdentity.CORRECTNESS,
            status=SpecialistStatus.SUCCESS,
            attempts=1,
        ),
        SpecialistResult(
            identity=ReviewerIdentity.SECURITY,
            status=SpecialistStatus.FAILED,
            attempts=2,
            failure="Malformed structured response after 2 attempts",
        ),
        SpecialistResult(
            identity=ReviewerIdentity.TEST_COVERAGE,
            status=SpecialistStatus.SUCCESS,
            attempts=1,
        ),
    )


def static_absent() -> StaticAnalysisResult:
    return StaticAnalysisResult(
        available=False,
        tools=(
            StaticToolStatus(name="external-scanners", available=False, detail="Not configured"),
        ),
        signals=(),
        summary="No parseable Python file content was available for static inspection.",
    )


def test_markdown_is_deterministic_prioritized_and_contains_exact_marker() -> None:
    high = finding("correctness.high", Severity.HIGH, 12)
    low = finding("correctness.low", Severity.LOW, 11)

    first = render_review(metadata(), (low, high), statuses(), static_absent())
    second = render_review(metadata(), (high, low), tuple(reversed(statuses())), static_absent())

    assert first == second
    assert first.index("[HIGH]") < first.index("[LOW]")
    assert "Partial review: 1 specialist failed" in first
    assert "Static analysis unavailable" in first
    assert first.endswith("<!-- code-review-agent:acme/widgets#7 -->")


def test_clean_review_states_no_publishable_findings() -> None:
    successful = tuple(
        SpecialistResult(identity=identity, status=SpecialistStatus.SUCCESS, attempts=1)
        for identity in ReviewerIdentity
    )

    body = render_review(metadata(), (), successful, static_absent())

    assert "No publishable findings were identified" in body
    assert "Partial review" not in body
