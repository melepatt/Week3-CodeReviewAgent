"""Conservative deterministic gates between model output and publication."""

from __future__ import annotations

import re
from collections.abc import Iterable

from code_review_agent.models import (
    Category,
    Finding,
    RejectedFinding,
    ReviewContext,
    ReviewFile,
    Severity,
    ValidationResult,
)

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TEST_CONSTRUCT = re.compile(
    r"\b(?:test_[A-Za-z0-9_]*|assert[A-Za-z0-9_]*|pytest\s*\.\s*raises|expect\s*\()",
    re.IGNORECASE,
)
_ACTION_VERBS = {
    "add",
    "await",
    "check",
    "close",
    "escape",
    "guard",
    "handle",
    "limit",
    "move",
    "preserve",
    "propagate",
    "reject",
    "remove",
    "replace",
    "return",
    "sanitize",
    "test",
    "update",
    "use",
    "validate",
}
_GENERIC_BEHAVIOR = {
    "add",
    "assert",
    "assertion",
    "behavior",
    "change",
    "changed",
    "direct",
    "gap",
    "handling",
    "input",
    "lacks",
    "missing",
    "regression",
    "subject",
    "test",
    "tests",
    "value",
}
_SEVERITY_RANK = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


def _tokens(text: str) -> set[str]:
    return {match.group(0).casefold() for match in _TOKEN.finditer(text)}


def _head_line_text(file: ReviewFile) -> dict[int, str]:
    if not file.patch:
        return {}
    header = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    line_number: int | None = None
    lines: dict[int, str] = {}
    for raw in file.patch.splitlines():
        match = header.match(raw)
        if match:
            line_number = int(match.group(1))
            continue
        if line_number is None or raw.startswith("\\"):
            continue
        if raw.startswith("-") and not raw.startswith("---"):
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            lines[line_number] = raw[1:]
            line_number += 1
        else:
            lines[line_number] = raw[1:] if raw.startswith(" ") else raw
            line_number += 1
    return lines


def _valid_coordinate(finding: Finding, file: ReviewFile) -> bool:
    max_line = (
        len(file.content.splitlines()) if file.content else max(file.changed_lines, default=0)
    )
    return finding.start_line <= finding.end_line <= max_line


def _overlaps_changed_line(finding: Finding, file: ReviewFile) -> bool:
    return any(
        line in file.changed_lines for line in range(finding.start_line, finding.end_line + 1)
    )


def _relevant_subject(finding: Finding, file: ReviewFile) -> bool:
    if not file.patch:
        return False
    header = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@(.*)$")
    hunks: list[tuple[int, int, list[str]]] = []
    current: tuple[int, int, list[str]] | None = None
    for raw in file.patch.splitlines():
        match = header.match(raw)
        if match:
            start = int(match.group(1))
            count = int(match.group(2) or "1")
            current = (start, start + max(count - 1, 0), [match.group(3)])
            hunks.append(current)
        elif current is not None:
            current[2].append(raw[1:] if raw[:1] in {"+", "-", " "} else raw)
    referenced = "\n".join(
        "\n".join(lines)
        for start, end, lines in hunks
        if finding.start_line <= end and start <= finding.end_line
    )
    return bool(_tokens(finding.subject) & _tokens(referenced))


def _specific_evidence(finding: Finding) -> bool:
    return bool(_tokens(finding.subject) & _tokens(finding.evidence))


def _actionable_recommendation(finding: Finding) -> bool:
    words = list(_TOKEN.finditer(finding.recommendation))
    if not words or words[0].group(0).casefold() not in _ACTION_VERBS:
        return False
    return bool(_tokens(finding.subject) & _tokens(finding.recommendation))


def _contradicted_by_direct_test(finding: Finding, context: ReviewContext) -> bool:
    if finding.category is not Category.TEST_GAP:
        return False
    subject = _tokens(finding.subject)
    behavior = (
        _tokens(f"{finding.title} {finding.evidence} {finding.recommendation}")
        - subject
        - _GENERIC_BEHAVIOR
    )
    for file in context.files:
        if not file.is_test or not file.changed_lines:
            continue
        line_map = _head_line_text(file)
        changed_text = "\n".join(line_map.get(line, "") for line in sorted(file.changed_lines))
        test_tokens = _tokens(changed_text)
        if not subject.issubset(test_tokens):
            continue
        if _TEST_CONSTRUCT.search(changed_text) is None:
            continue
        if behavior & test_tokens:
            return True
    return False


def validate_findings(findings: Iterable[Finding], context: ReviewContext) -> ValidationResult:
    files = {file.path: file for file in context.files}
    accepted: list[Finding] = []
    rejected: list[RejectedFinding] = []
    for finding in findings:
        file = files.get(finding.path)
        reason: str | None = None
        if file is None:
            reason = "unknown-file"
        elif not _valid_coordinate(finding, file):
            reason = "invalid-coordinate"
        elif not _overlaps_changed_line(finding, file):
            reason = "unchanged-line"
        elif not _relevant_subject(finding, file):
            reason = "irrelevant-subject"
        elif not _specific_evidence(finding):
            reason = "insufficient-evidence"
        elif not _actionable_recommendation(finding):
            reason = "nonactionable-recommendation"
        elif _contradicted_by_direct_test(finding, context):
            reason = "contradicted-by-direct-test"
        if reason:
            rejected.append(RejectedFinding(identifier=finding.identifier, reason=reason))
        else:
            accepted.append(finding)
    deduplicated = deduplicate_findings(accepted)
    return ValidationResult(accepted=deduplicated, rejected=tuple(rejected))


def _duplicates(left: Finding, right: Finding) -> bool:
    if (
        left.category is not right.category
        or left.path != right.path
        or _tokens(left.subject) != _tokens(right.subject)
    ):
        return False
    return left.start_line <= right.end_line and right.start_line <= left.end_line


def _sort_key(finding: Finding) -> tuple[object, ...]:
    return (
        _SEVERITY_RANK[finding.severity],
        finding.path,
        finding.start_line,
        finding.end_line,
        finding.identifier,
    )


def deduplicate_findings(findings: Iterable[Finding]) -> tuple[Finding, ...]:
    selected: list[Finding] = []
    for candidate in sorted(findings, key=_sort_key):
        if not any(_duplicates(candidate, existing) for existing in selected):
            selected.append(candidate)
    return tuple(sorted(selected, key=_sort_key))
