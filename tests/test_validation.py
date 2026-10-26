from __future__ import annotations

import pytest

from code_review_agent.config import Limits
from code_review_agent.context import build_review_context
from code_review_agent.models import (
    Category,
    ChangedFile,
    Finding,
    PullRequestMetadata,
    PullRequestSnapshot,
    ReviewerIdentity,
    Severity,
)
from code_review_agent.validation import deduplicate_findings, validate_findings


def make_context(*, include_direct_test: bool = False, test_patch: str | None = None):
    source_lines = ["# filler"] * 9 + [
        "def parse_widget(raw):",
        "    value = raw.strip()",
        "    return int(value)",
        "",
        "def caller(raw):",
        "    return parse_widget(raw)",
    ]
    files = [
        ChangedFile(
            path="src/widget.py",
            status="modified",
            additions=3,
            deletions=1,
            changes=4,
            patch=(
                "@@ -10,3 +10,3 @@ def parse_widget(raw):\n"
                "+def parse_widget(raw):\n"
                "+    value = raw.strip()\n"
                "+    return int(value)"
            ),
            content="\n".join(source_lines),
        )
    ]
    if include_direct_test:
        patch = test_patch or (
            "@@ -0,0 +1,2 @@\n"
            "+def test_parse_widget_rejects_empty():\n"
            "+    assert parse_widget('') raises ValueError"
        )
        files.append(
            ChangedFile(
                path="tests/test_widget.py",
                status="modified",
                additions=2,
                deletions=0,
                changes=2,
                patch=patch,
                content=(
                    "def test_parse_widget_rejects_empty():\n"
                    "    assert parse_widget('') raises ValueError\n"
                ),
            )
        )
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
    return build_review_context(
        PullRequestSnapshot(metadata=metadata, files=tuple(files)),
        Limits(max_total_context_chars=20_000),
    )


def finding(**overrides: object) -> Finding:
    values: dict[str, object] = {
        "identifier": "correctness.parse-empty",
        "category": Category.CORRECTNESS,
        "severity": Severity.HIGH,
        "title": "Empty widget input raises an uncaught error",
        "path": "src/widget.py",
        "start_line": 11,
        "end_line": 12,
        "subject": "parse_widget",
        "evidence": "parse_widget passes an empty stripped value directly to int",
        "impact": "An empty widget value raises during normal request handling",
        "recommendation": "Validate parse_widget input and return a clear validation error",
        "reviewer": ReviewerIdentity.CORRECTNESS,
    }
    values.update(overrides)
    return Finding.model_validate(values)


def test_grounded_specific_actionable_finding_is_accepted() -> None:
    result = validate_findings((finding(),), make_context())

    assert result.accepted == (finding(),)
    assert result.rejected == ()


def test_unknown_file_is_rejected() -> None:
    result = validate_findings((finding(path="src/invented.py"),), make_context())

    assert result.rejected[0].reason == "unknown-file"


def test_invalid_coordinate_is_rejected() -> None:
    result = validate_findings(
        (finding(start_line=99, end_line=99),),
        make_context(),
    )

    assert result.rejected[0].reason == "invalid-coordinate"


def test_unchanged_line_is_rejected() -> None:
    result = validate_findings(
        (finding(start_line=15, end_line=15),),
        make_context(),
    )

    assert result.rejected[0].reason == "unchanged-line"


def test_subject_must_be_relevant_to_referenced_changed_hunk() -> None:
    result = validate_findings(
        (
            finding(
                subject="database_pool",
                evidence="database_pool may be used after it has been closed",
                recommendation="Guard database_pool before accepting a new request",
            ),
        ),
        make_context(),
    )

    assert result.rejected[0].reason == "irrelevant-subject"


def test_evidence_must_name_concrete_subject() -> None:
    result = validate_findings(
        (finding(evidence="This changed code can fail for a concrete normal input"),),
        make_context(),
    )

    assert result.rejected[0].reason == "insufficient-evidence"


def test_recommendation_must_start_with_change_verb_and_name_subject() -> None:
    result = validate_findings(
        (finding(recommendation="The implementation of parse_widget needs improvement"),),
        make_context(),
    )

    assert result.rejected[0].reason == "nonactionable-recommendation"


def test_direct_added_test_suppresses_matching_test_gap() -> None:
    gap = finding(
        identifier="test-gap.parse-empty",
        category=Category.TEST_GAP,
        severity=Severity.MEDIUM,
        title="Empty widget parsing lacks a direct regression test",
        evidence="parse_widget empty input behavior has no direct assertion",
        impact="A regression in empty widget handling could ship unnoticed",
        recommendation="Add parse_widget empty input assertion for ValueError",
        reviewer=ReviewerIdentity.TEST_COVERAGE,
    )

    result = validate_findings((gap,), make_context(include_direct_test=True))

    assert result.rejected[0].reason == "contradicted-by-direct-test"


@pytest.mark.parametrize(
    "test_patch",
    [
        (
            "@@ -0,0 +1,3 @@\n"
            "+def test_parse_widget_rejects_empty():\n"
            "+    with pytest.raises(ValueError):\n"
            "+        parse_widget('')"
        ),
        (
            "@@ -0,0 +1,2 @@\n"
            "+def check_empty_widget(self):\n"
            "+    self.assertRaises(ValueError, parse_widget, '')"
        ),
        ("@@ -0,0 +1 @@\n+expect(lambda: parse_widget('')).to_raise(ValueError)"),
    ],
)
def test_common_python_test_constructs_suppress_matching_gap(test_patch: str) -> None:
    gap = finding(
        identifier="test-gap.parse-empty",
        category=Category.TEST_GAP,
        severity=Severity.MEDIUM,
        title="Empty widget parsing lacks a direct regression test",
        evidence="parse_widget empty input behavior has no direct assertion",
        impact="A regression in empty widget handling could ship unnoticed",
        recommendation="Add parse_widget empty input assertion for ValueError",
        reviewer=ReviewerIdentity.TEST_COVERAGE,
    )

    result = validate_findings(
        (gap,), make_context(include_direct_test=True, test_patch=test_patch)
    )

    assert result.rejected[0].reason == "contradicted-by-direct-test"


def test_unrelated_test_does_not_suppress_test_gap() -> None:
    gap = finding(
        identifier="test-gap.parse-overflow",
        category=Category.TEST_GAP,
        severity=Severity.MEDIUM,
        title="Large widget parsing lacks a direct regression test",
        evidence="parse_widget large integer behavior has no direct assertion",
        impact="A regression in large widget handling could ship unnoticed",
        recommendation="Add parse_widget large integer assertion for bounded handling",
        reviewer=ReviewerIdentity.TEST_COVERAGE,
    )

    result = validate_findings((gap,), make_context(include_direct_test=True))

    assert result.accepted == (gap,)


def test_deduplication_is_deterministic_and_keeps_highest_severity() -> None:
    medium = finding(identifier="correctness.parse-a", severity=Severity.MEDIUM)
    high = finding(identifier="correctness.parse-b", severity=Severity.HIGH)

    forward = deduplicate_findings((medium, high))
    reverse = deduplicate_findings((high, medium))

    assert forward == reverse == (high,)


def test_distinct_categories_are_not_deduplicated() -> None:
    security = finding(
        identifier="security.parse-empty",
        category=Category.SECURITY,
        reviewer=ReviewerIdentity.SECURITY,
    )

    result = deduplicate_findings((finding(), security))

    assert {item.identifier for item in result} == {
        "correctness.parse-empty",
        "security.parse-empty",
    }
