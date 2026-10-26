"""Deterministic consolidated Markdown rendering."""

from __future__ import annotations

from collections.abc import Iterable

from code_review_agent.github import stable_marker
from code_review_agent.models import (
    Finding,
    PullRequestMetadata,
    PullRequestRef,
    ReviewerIdentity,
    SpecialistResult,
    SpecialistStatus,
    StaticAnalysisResult,
)
from code_review_agent.validation import deduplicate_findings


def render_review(
    metadata: PullRequestMetadata,
    findings: Iterable[Finding],
    specialists: Iterable[SpecialistResult],
    static_analysis: StaticAnalysisResult,
) -> str:
    ordered_findings = deduplicate_findings(findings)
    status_by_identity = {result.identity: result for result in specialists}
    failures = [
        result for result in status_by_identity.values() if result.status is SpecialistStatus.FAILED
    ]

    lines = [
        "## Code review agent",
        "",
        (
            f"Reviewed `{metadata.owner}/{metadata.repo}#{metadata.number}` "
            f"at head `{metadata.head_sha}`."
        ),
        "",
    ]
    if failures:
        suffix = "specialist failed" if len(failures) == 1 else "specialists failed"
        lines.extend(
            [
                f"> Partial review: {len(failures)} {suffix}. See specialist status below.",
                "",
            ]
        )

    lines.extend(["### Findings", ""])
    if not ordered_findings:
        lines.extend(["No publishable findings were identified in the supplied change.", ""])
    else:
        for index, finding in enumerate(ordered_findings, start=1):
            location = (
                f"`{finding.path}:{finding.start_line}`"
                if finding.start_line == finding.end_line
                else f"`{finding.path}:{finding.start_line}-{finding.end_line}`"
            )
            lines.extend(
                [
                    f"#### {index}. [{finding.severity.value.upper()}] {finding.title}",
                    "",
                    f"- Category: `{finding.category.value}`",
                    f"- Location: {location}",
                    f"- Evidence: {finding.evidence}",
                    f"- Impact: {finding.impact}",
                    f"- Recommendation: {finding.recommendation}",
                    f"- Reviewer: `{finding.reviewer.value}`",
                    f"- Finding ID: `{finding.identifier}`",
                    "",
                ]
            )

    lines.extend(["### Specialist status", ""])
    for identity in ReviewerIdentity:
        result = status_by_identity.get(identity)
        if result is None:
            lines.append(f"- `{identity.value}`: not run")
        elif result.status is SpecialistStatus.SUCCESS:
            lines.append(
                f"- `{identity.value}`: completed ({len(result.findings)} candidate finding(s))"
            )
        else:
            lines.append(f"- `{identity.value}`: failed — {result.failure}")

    lines.extend(["", "### Analysis availability", ""])
    if static_analysis.available:
        lines.append(f"- Static analysis available: {static_analysis.summary}")
    else:
        lines.append(f"- Static analysis unavailable: {static_analysis.summary}")
    for tool in sorted(static_analysis.tools, key=lambda item: item.name):
        state = "available" if tool.available else "unavailable"
        lines.append(f"- `{tool.name}`: {state} — {tool.detail}")

    ref = PullRequestRef(
        owner=metadata.owner,
        repo=metadata.repo,
        number=metadata.number,
        canonical_url=metadata.url,
    )
    lines.extend(["", stable_marker(ref)])
    return "\n".join(lines)
