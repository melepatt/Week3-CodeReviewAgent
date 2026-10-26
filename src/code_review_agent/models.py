"""Strict internal and provider-compatible review models."""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class Category(StrEnum):
    CORRECTNESS = "correctness"
    SECURITY = "security"
    TEST_GAP = "test-gap"
    API_DESIGN = "api-design"
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    DOCUMENTATION = "documentation"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ReviewerIdentity(StrEnum):
    CORRECTNESS = "correctness"
    SECURITY = "security"
    TEST_COVERAGE = "test-coverage"


Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9._-]+$",
    ),
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=160)]
EvidenceText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=20, max_length=500)
]
ImpactText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=15, max_length=500)]
RecommendationText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=20, max_length=500)
]
SubjectText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]


class Finding(BaseModel):
    """A validated internal finding eligible for deterministic checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    identifier: Identifier
    category: Category
    severity: Severity
    title: ShortText
    path: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    subject: SubjectText
    evidence: EvidenceText
    impact: ImpactText
    recommendation: RecommendationText
    reviewer: ReviewerIdentity

    @model_validator(mode="after")
    def validate_semantics(self) -> Finding:
        path = PurePosixPath(self.path)
        if path.is_absolute() or ".." in path.parts or "\\" in self.path:
            raise ValueError("path must be a repository-relative POSIX path")
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        if self.category is Category.TEST_GAP and self.severity in {
            Severity.CRITICAL,
            Severity.HIGH,
        }:
            raise ValueError("test-gap findings must use medium, low, or info severity")
        return self


class ProviderFinding(BaseModel):
    """Simple provider-facing schema converted into the stricter internal model."""

    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=3, max_length=64)
    category: str = Field(min_length=3, max_length=32)
    severity: str = Field(min_length=3, max_length=16)
    title: str = Field(min_length=5, max_length=160)
    path: str = Field(min_length=1, max_length=300)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    subject: str = Field(min_length=2, max_length=80)
    evidence: str = Field(min_length=20, max_length=500)
    impact: str = Field(min_length=15, max_length=500)
    recommendation: str = Field(min_length=20, max_length=500)
    reviewer: str = Field(min_length=3, max_length=32)

    def to_internal(self) -> Finding:
        return Finding.model_validate(self.model_dump())


class ProviderSpecialistOutput(BaseModel):
    """Bounded structured output shared by all model specialists."""

    model_config = ConfigDict(extra="forbid")

    findings: list[ProviderFinding] = Field(default_factory=list, max_length=3)
    validation_notes: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=160)]
    ] = Field(default_factory=list, max_length=3)


class PullRequestRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    owner: str
    repo: str
    number: int = Field(gt=0)
    canonical_url: str


class PullRequestMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    owner: str
    repo: str
    number: int = Field(gt=0)
    url: str
    title: str
    body: str = ""
    author: str
    base_branch: str
    head_branch: str
    head_sha: str = Field(pattern=r"^[0-9a-fA-F]{40}$")


class ChangedFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    status: str
    additions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    changes: int = Field(ge=0)
    previous_path: str | None = None
    patch: str | None = None
    patch_truncated: bool = False
    content: str | None = None
    content_truncated: bool = False


class PullRequestSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: PullRequestMetadata
    files: tuple[ChangedFile, ...]
    files_truncated: bool = False


class PublishResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    comment_id: int = Field(gt=0)
    action: Literal["created", "updated", "recovered"]


class ReviewFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    previous_path: str | None = None
    status: str
    patch: str | None = None
    content: str | None = None
    changed_lines: frozenset[int] = frozenset()
    patch_available: bool = False
    patch_truncated: bool = False
    content_truncated: bool = False
    is_test: bool = False


class ReviewContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: PullRequestMetadata
    files: tuple[ReviewFile, ...]
    model_text: str
    omissions: tuple[str, ...] = ()
    redaction_count: int = Field(ge=0)


class StaticToolStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    available: bool
    detail: str


class StaticSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: str
    path: str
    line: int = Field(ge=1)
    message: str


class StaticAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    tools: tuple[StaticToolStatus, ...]
    signals: tuple[StaticSignal, ...]
    summary: str


class SpecialistStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class SpecialistResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identity: ReviewerIdentity
    status: SpecialistStatus
    findings: tuple[Finding, ...] = ()
    validation_notes: tuple[str, ...] = ()
    attempts: int = Field(ge=0)
    failure: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> SpecialistResult:
        if self.status is SpecialistStatus.SUCCESS and self.failure is not None:
            raise ValueError("successful specialist cannot have a failure")
        if self.status is SpecialistStatus.FAILED and not self.failure:
            raise ValueError("failed specialist requires a failure")
        return self


class RejectedFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identifier: str
    reason: str


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: tuple[Finding, ...]
    rejected: tuple[RejectedFinding, ...]


class ReviewOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: PullRequestMetadata
    context: ReviewContext
    specialists: tuple[SpecialistResult, ...]
    static_analysis: StaticAnalysisResult
    accepted: tuple[Finding, ...] = ()
    rejected: tuple[RejectedFinding, ...] = ()
    markdown: str | None = None
    partial: bool = False
    aborted: bool = False
