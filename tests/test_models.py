from __future__ import annotations

import pytest
from pydantic import ValidationError

from code_review_agent.models import (
    Category,
    Finding,
    ProviderFinding,
    ProviderSpecialistOutput,
    ReviewerIdentity,
    Severity,
)


def finding_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "identifier": "correctness.widget-null",
        "category": Category.CORRECTNESS,
        "severity": Severity.HIGH,
        "title": "Null widget crashes request handling",
        "path": "src/widgets.py",
        "start_line": 12,
        "end_line": 14,
        "subject": "build_widget",
        "evidence": "build_widget dereferences widget before validating it",
        "impact": "A normal missing widget request raises an exception",
        "recommendation": "Validate build_widget input before dereferencing widget",
        "reviewer": ReviewerIdentity.CORRECTNESS,
    }
    data.update(overrides)
    return data


def test_strict_finding_accepts_closed_taxonomy_and_coordinates() -> None:
    finding = Finding.model_validate(finding_data())

    assert finding.category is Category.CORRECTNESS
    assert finding.end_line == 14


@pytest.mark.parametrize(
    "overrides",
    [
        {"category": "style"},
        {"severity": "urgent"},
        {"reviewer": "general"},
        {"start_line": 0},
        {"start_line": 15, "end_line": 14},
        {"path": "/etc/passwd"},
        {"path": "src/../secret.py"},
        {"evidence": "too vague"},
        {"recommendation": "add test"},
    ],
)
def test_strict_finding_rejects_invalid_or_unbounded_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate(finding_data(**overrides))


def test_test_gap_cannot_be_high_solely_as_a_missing_test() -> None:
    with pytest.raises(ValidationError, match="test-gap"):
        Finding.model_validate(
            finding_data(
                identifier="test-gap.widget-null",
                category=Category.TEST_GAP,
                severity=Severity.HIGH,
                reviewer=ReviewerIdentity.TEST_COVERAGE,
            )
        )


def test_provider_schema_limits_findings_and_notes() -> None:
    provider_finding = ProviderFinding.model_validate(
        {
            key: value.value if hasattr(value, "value") else value
            for key, value in finding_data().items()
        }
    )

    valid = ProviderSpecialistOutput(
        findings=[provider_finding, provider_finding, provider_finding],
        validation_notes=["Grounded in the supplied hunk"] * 3,
    )

    assert len(valid.findings) == 3
    with pytest.raises(ValidationError):
        ProviderSpecialistOutput(findings=[provider_finding] * 4, validation_notes=[])
    with pytest.raises(ValidationError):
        ProviderSpecialistOutput(findings=[], validation_notes=["short"] * 4)


def test_provider_model_converts_to_strict_internal_model() -> None:
    provider = ProviderFinding.model_validate(
        {
            key: value.value if hasattr(value, "value") else value
            for key, value in finding_data().items()
        }
    )

    internal = provider.to_internal()

    assert isinstance(internal, Finding)
    assert internal.identifier == "correctness.widget-null"
