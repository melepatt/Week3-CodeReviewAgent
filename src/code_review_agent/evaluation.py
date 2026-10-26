"""Read-only, source-free black-box evaluation with explicit paid-call gates."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from code_review_agent.config import AppConfig, ConfigurationError
from code_review_agent.github import GitHubReadClient, parse_pull_request_url
from code_review_agent.graph import ReviewerSet
from code_review_agent.llm import StructuredModelClient
from code_review_agent.models import Category, ReviewerIdentity, Severity, SpecialistStatus
from code_review_agent.reviewers import run_specialist
from code_review_agent.service import ReviewService


class CatalogError(ValueError):
    pass


class ApprovalRequired(PermissionError):
    pass


_SEVERITY_RANK = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


class ExpectedFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category_aliases: tuple[Category, ...] = Field(min_length=1)
    path: str = Field(min_length=1, max_length=300)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    min_severity: Severity
    max_severity: Severity

    @model_validator(mode="after")
    def lines_are_ordered(self) -> ExpectedFinding:
        if self.end_line < self.start_line:
            raise ValueError("expected line range is reversed")
        if len(self.category_aliases) != len(set(self.category_aliases)):
            raise ValueError("expected category aliases must be unique")
        path = PurePosixPath(self.path)
        if path.is_absolute() or ".." in path.parts or "\\" in self.path:
            raise ValueError("expected path must be a repository-relative POSIX path")
        if _SEVERITY_RANK[self.min_severity] < _SEVERITY_RANK[self.max_severity]:
            raise ValueError("expected severity range is reversed")
        return self


CaseRole = Literal["seeded-defect", "clean-control", "malformed-recovery"]


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]+$")
    role: CaseRole
    url: str
    head_sha: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    expected: tuple[ExpectedFinding, ...] = ()

    @model_validator(mode="after")
    def canonical_url(self) -> EvaluationCase:
        parse_pull_request_url(self.url)
        if self.role == "clean-control" and self.expected:
            raise ValueError("clean-control cannot contain expected findings")
        if self.role != "clean-control" and not self.expected:
            raise ValueError("non-clean evaluation cases require expected findings")
        return self


class EvaluationCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[2]
    cases: tuple[EvaluationCase, ...] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def required_roles(self) -> EvaluationCatalog:
        roles = Counter(case.role for case in self.cases)
        if roles != Counter({"seeded-defect": 7, "clean-control": 2, "malformed-recovery": 1}):
            raise ValueError("catalog must have seven seeded, two clean, and one recovery case")
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("catalog case IDs must be unique")
        urls = [case.url for case in self.cases]
        if len(urls) != len(set(urls)):
            raise ValueError("catalog pull-request URLs must be unique")
        pins = [(case.url, case.head_sha.casefold()) for case in self.cases]
        if len(pins) != len(set(pins)):
            raise ValueError("catalog URL and head-SHA pins must be unique")
        return self


class EvalFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identifier: str
    category: str
    severity: Severity
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class EvaluationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    role: CaseRole
    status: Literal["success", "head-mismatch", "operational-failure"]
    findings: tuple[EvalFinding, ...] = ()
    specialists_completed: int = Field(default=0, ge=0, le=3)
    partial_recovery: bool = False
    error: str | None = None


class EvaluationRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cases: tuple[EvaluationCaseResult, ...]


class EvaluationStage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["preflight", "clean-controls", "seeded-defects", "malformed-recovery"]
    run: EvaluationRun


class EvaluationSequence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stages: tuple[EvaluationStage, ...]
    stopped_reason: str | None = None


class EvaluationBackend(Protocol):
    def head_sha(self, case: EvaluationCase) -> str: ...

    def review(self, case: EvaluationCase) -> EvaluationCaseResult: ...


def _is_placeholder(case: EvaluationCase) -> bool:
    ref = parse_pull_request_url(case.url)
    tokens = f"{ref.owner}/{ref.repo}".casefold()
    return (
        len(set(case.head_sha.casefold())) == 1
        or "replace" in tokens
        or "placeholder" in tokens
        or "your-" in tokens
    )


def load_catalog(path: Path, *, require_live_ready: bool = False) -> EvaluationCatalog:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        catalog = EvaluationCatalog.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise CatalogError("Evaluation catalog is invalid") from exc
    if require_live_ready and any(_is_placeholder(case) for case in catalog.cases):
        raise CatalogError("Evaluation catalog contains placeholder URLs or head SHAs")
    return catalog


def default_catalog_path() -> Path:
    checkout_path = Path("evaluation/catalog.json")
    if checkout_path.is_file():
        return checkout_path
    return Path(str(files("code_review_agent").joinpath("evaluation_catalog.json")))


def run_evaluation(
    catalog: EvaluationCatalog,
    backend: EvaluationBackend,
    *,
    case_ids: tuple[str, ...] | None = None,
    allow_model_calls: bool = False,
    preflight: dict[str, str | None] | None = None,
) -> EvaluationRun:
    if not allow_model_calls:
        raise ApprovalRequired("Model-backed evaluation requires explicit approval")
    wanted = set(case_ids) if case_ids is not None else None
    selected = [case for case in catalog.cases if wanted is None or case.id in wanted]

    resolved_heads = preflight
    if resolved_heads is None:
        resolved_heads = {}
        for case in selected:
            try:
                resolved_heads[case.id] = backend.head_sha(case)
            except Exception:
                resolved_heads[case.id] = None

    results: list[EvaluationCaseResult] = []
    for case in selected:
        actual_sha = resolved_heads.get(case.id)
        if actual_sha is None:
            results.append(
                EvaluationCaseResult(
                    case_id=case.id,
                    role=case.role,
                    status="operational-failure",
                    error="Pinned-head preflight failed operationally",
                )
            )
            continue
        if actual_sha.casefold() != case.head_sha.casefold():
            results.append(
                EvaluationCaseResult(
                    case_id=case.id,
                    role=case.role,
                    status="head-mismatch",
                    error="Pinned head SHA does not match current pull-request head",
                )
            )
            continue
        try:
            result = backend.review(case)
        except Exception:
            result = EvaluationCaseResult(
                case_id=case.id,
                role=case.role,
                status="operational-failure",
                error="Evaluation case failed operationally",
            )
        results.append(result)
    return EvaluationRun(cases=tuple(results))


def preflight_catalog(
    catalog: EvaluationCatalog,
    backend: EvaluationBackend,
) -> dict[str, str | None]:
    resolved: dict[str, str | None] = {}
    for case in catalog.cases:
        try:
            resolved[case.id] = backend.head_sha(case)
        except Exception:
            resolved[case.id] = None
    return resolved


def _case_ids(catalog: EvaluationCatalog, role: CaseRole) -> tuple[str, ...]:
    return tuple(case.id for case in catalog.cases if case.role == role)


def _expected_match(expected: ExpectedFinding, finding: EvalFinding) -> bool:
    return (
        finding.category in expected.category_aliases
        and finding.path == expected.path
        and finding.start_line <= expected.end_line
        and expected.start_line <= finding.end_line
    )


def _metric_candidate(expected: ExpectedFinding, finding: EvalFinding) -> bool:
    return finding.category in expected.category_aliases and finding.path == expected.path


def _maximum_matching(
    expected_items: tuple[ExpectedFinding, ...],
    findings: tuple[EvalFinding, ...],
    matches: Callable[[ExpectedFinding, EvalFinding], bool],
) -> dict[int, int]:
    finding_to_expected: dict[int, int] = {}

    def assign(expected_index: int, visited: set[int]) -> bool:
        for finding_index, finding in enumerate(findings):
            if finding_index in visited or not matches(expected_items[expected_index], finding):
                continue
            visited.add(finding_index)
            previous = finding_to_expected.get(finding_index)
            if previous is None or assign(previous, visited):
                finding_to_expected[finding_index] = expected_index
                return True
        return False

    for expected_index in range(len(expected_items)):
        assign(expected_index, set())
    return {
        expected_index: finding_index
        for finding_index, expected_index in finding_to_expected.items()
    }


def _expected_findings_match(case: EvaluationCase, result: EvaluationCaseResult) -> bool:
    matches = _maximum_matching(case.expected, result.findings, _expected_match)
    return len(matches) == len(case.expected)


def _preflight_failures(
    catalog: EvaluationCatalog,
    resolved_heads: dict[str, str | None],
) -> tuple[EvaluationCaseResult, ...]:
    failures: list[EvaluationCaseResult] = []
    for case in catalog.cases:
        actual_sha = resolved_heads.get(case.id)
        if actual_sha is None:
            failures.append(
                EvaluationCaseResult(
                    case_id=case.id,
                    role=case.role,
                    status="operational-failure",
                    error="Pinned-head preflight failed operationally",
                )
            )
        elif actual_sha.casefold() != case.head_sha.casefold():
            failures.append(
                EvaluationCaseResult(
                    case_id=case.id,
                    role=case.role,
                    status="head-mismatch",
                    error="Pinned head SHA does not match current pull-request head",
                )
            )
    return tuple(failures)


def run_gate_sequence(
    catalog: EvaluationCatalog,
    backend: EvaluationBackend,
    *,
    allow_model_calls: bool = False,
) -> EvaluationSequence:
    if not allow_model_calls:
        raise ApprovalRequired("Model-backed evaluation requires explicit approval")

    resolved_heads = preflight_catalog(catalog, backend)
    failures = _preflight_failures(catalog, resolved_heads)
    if failures:
        return EvaluationSequence(
            stages=(EvaluationStage(name="preflight", run=EvaluationRun(cases=failures)),),
            stopped_reason="catalog-preflight-failed",
        )

    clean_ids = _case_ids(catalog, "clean-control")
    clean = run_evaluation(
        catalog,
        backend,
        case_ids=clean_ids,
        allow_model_calls=True,
        preflight=resolved_heads,
    )
    stages = [EvaluationStage(name="clean-controls", run=clean)]
    if any(result.status != "success" for result in clean.cases):
        return EvaluationSequence(
            stages=tuple(stages), stopped_reason="clean-controls-operational-failure"
        )
    if any(result.findings for result in clean.cases):
        return EvaluationSequence(
            stages=tuple(stages), stopped_reason="clean-controls-produced-findings"
        )

    seeded_ids = _case_ids(catalog, "seeded-defect")
    seeded = run_evaluation(
        catalog,
        backend,
        case_ids=seeded_ids,
        allow_model_calls=True,
        preflight=resolved_heads,
    )
    stages.append(EvaluationStage(name="seeded-defects", run=seeded))
    cases_by_id = {case.id: case for case in catalog.cases}
    if any(
        result.status != "success"
        or not _expected_findings_match(cases_by_id[result.case_id], result)
        for result in seeded.cases
    ):
        return EvaluationSequence(stages=tuple(stages), stopped_reason="seeded-defects-gate-failed")

    recovery_ids = _case_ids(catalog, "malformed-recovery")
    recovery = run_evaluation(
        catalog,
        backend,
        case_ids=recovery_ids,
        allow_model_calls=True,
        preflight=resolved_heads,
    )
    stages.append(EvaluationStage(name="malformed-recovery", run=recovery))
    recovery_result = recovery.cases[0]
    recovery_case = cases_by_id[recovery_result.case_id]
    if (
        recovery_result.status != "success"
        or not recovery_result.partial_recovery
        or recovery_result.specialists_completed != 2
        or not _expected_findings_match(recovery_case, recovery_result)
    ):
        return EvaluationSequence(
            stages=tuple(stages), stopped_reason="malformed-recovery-gate-failed"
        )
    return EvaluationSequence(stages=tuple(stages))


def combine_sequence_runs(sequence: EvaluationSequence) -> EvaluationRun:
    if sequence.stopped_reason is not None:
        raise ValueError("Cannot combine an incomplete evaluation sequence")
    combined: list[EvaluationCaseResult] = []
    seen: set[str] = set()
    for stage in sequence.stages:
        if stage.name == "preflight":
            continue
        for result in stage.run.cases:
            if result.case_id in seen:
                raise ValueError("Evaluation sequence contains a duplicate case")
            seen.add(result.case_id)
            combined.append(result)
    if len(combined) != 10:
        raise ValueError("Successful evaluation sequence must contain all ten cases")
    return EvaluationRun(cases=tuple(combined))


def compute_metrics(catalog: EvaluationCatalog, run: EvaluationRun) -> dict[str, object]:
    by_id = {case.id: case for case in catalog.cases}
    expected_total = 0
    predicted_total = 0
    matched_expected = 0
    matched_predictions = 0
    severity_matches = 0
    location_matches = 0
    all_findings: list[EvalFinding] = []
    finding_keys: list[tuple[str, str, str, int, int]] = []
    for result in run.cases:
        case = by_id[result.case_id]
        if result.status != "success":
            continue
        expected_total += len(case.expected)
        predicted_total += len(result.findings)
        all_findings.extend(result.findings)
        finding_keys.extend(
            (result.case_id, item.category, item.path, item.start_line, item.end_line)
            for item in result.findings
        )
        matches = _maximum_matching(case.expected, result.findings, _metric_candidate)
        for expected_index, finding_index in matches.items():
            expected = case.expected[expected_index]
            match = result.findings[finding_index]
            matched_expected += 1
            matched_predictions += 1
            if match.start_line <= expected.end_line and expected.start_line <= match.end_line:
                location_matches += 1
            low, high = sorted(
                (_SEVERITY_RANK[expected.min_severity], _SEVERITY_RANK[expected.max_severity])
            )
            if low <= _SEVERITY_RANK[match.severity] <= high:
                severity_matches += 1

    duplicate_count = len(finding_keys) - len(set(finding_keys))
    successful = [case for case in run.cases if case.status == "success"]
    malformed = [case for case in successful if case.role == "malformed-recovery"]
    clean = [case for case in successful if case.role == "clean-control"]
    return {
        "recall": matched_expected / expected_total if expected_total else "N/A",
        "precision": matched_predictions / predicted_total if predicted_total else "N/A",
        "severity_agreement": (severity_matches / matched_expected if matched_expected else "N/A"),
        "location_agreement": (location_matches / matched_expected if matched_expected else "N/A"),
        "duplicate_rate": duplicate_count / len(all_findings) if all_findings else 0.0,
        "specialist_completion": (
            sum(case.specialists_completed for case in successful) / (3 * len(successful))
            if successful
            else "N/A"
        ),
        "partial_recovery": (
            all(case.partial_recovery for case in malformed) if malformed else "N/A"
        ),
        "clean_control": (all(not case.findings for case in clean) if clean else "N/A"),
    }


def write_minimized_results(
    catalog: EvaluationCatalog,
    run: EvaluationRun,
    output_dir: Path,
    *,
    timestamp: str | None = None,
    label: str | None = None,
) -> tuple[Path, Path]:
    stamp = timestamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    if label is not None and re.fullmatch(r"[a-z0-9-]+", label) is None:
        raise ValueError("Evaluation artifact label must use lowercase letters, digits, or hyphens")
    artifact_id = f"{stamp}-{label}" if label else stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = compute_metrics(catalog, run)
    payload = {
        "timestamp": stamp,
        "cases": run.model_dump(mode="json")["cases"],
        "metrics": metrics,
    }
    json_path = output_dir / f"evaluation-{artifact_id}.json"
    markdown_path = output_dir / f"evaluation-{artifact_id}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Evaluation result", "", f"Timestamp: `{stamp}`", "", "## Cases", ""]
    for case in run.cases:
        lines.append(
            f"- `{case.case_id}` ({case.role}): {case.status}; "
            f"{len(case.findings)} finding(s); {case.specialists_completed}/3 specialists"
        )
        for finding in case.findings:
            lines.append(
                f"  - `{finding.identifier}` — {finding.category}/{finding.severity.value} "
                f"at `{finding.path}:{finding.start_line}-{finding.end_line}`"
            )
    lines.extend(["", "## Metrics", ""])
    for name, value in metrics.items():
        lines.append(f"- {name}: {value}")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


class ReadOnlyLiveBackend:
    """Live backend intentionally has no publisher or write-token dependency."""

    def __init__(
        self,
        config: AppConfig,
        *,
        reader: GitHubReadClient | None = None,
        model_client: StructuredModelClient | None = None,
    ) -> None:
        model_config = config.require_model()
        model = model_client or StructuredModelClient(model_config)
        reader = reader or GitHubReadClient(
            config.github.read_token,
            api_url=config.github.api_url,
            max_pages=config.limits.max_pages,
        )
        standard_reviewers = ReviewerSet(
            correctness=lambda context: run_specialist(
                ReviewerIdentity.CORRECTNESS, context, model
            ),
            security=lambda context: run_specialist(ReviewerIdentity.SECURITY, context, model),
            test_coverage=lambda context: run_specialist(
                ReviewerIdentity.TEST_COVERAGE, context, model
            ),
        )

        def malformed_response(messages, schema):
            if any("capability probe" in str(message.content).casefold() for message in messages):
                return {"findings": [], "validation_notes": []}
            return {"findings": "malformed", "validation_notes": []}

        malformed_model = StructuredModelClient(model_config, invoke=malformed_response)
        malformed_reviewers = ReviewerSet(
            correctness=standard_reviewers.correctness,
            security=standard_reviewers.security,
            test_coverage=lambda context: run_specialist(
                ReviewerIdentity.TEST_COVERAGE, context, malformed_model
            ),
        )
        self._reader = reader
        self._model = model
        self._malformed_model = malformed_model
        self._service = ReviewService(reader, standard_reviewers, config.limits)
        self._malformed_service = ReviewService(reader, malformed_reviewers, config.limits)

    def head_sha(self, case: EvaluationCase) -> str:
        return self._reader.get_metadata(parse_pull_request_url(case.url)).head_sha

    def review(self, case: EvaluationCase) -> EvaluationCaseResult:
        probe = self._model.probe()
        if not probe.supported:
            raise ConfigurationError(probe.detail)
        service = self._service
        if case.role == "malformed-recovery":
            malformed_probe = self._malformed_model.probe()
            if not malformed_probe.supported:
                raise ConfigurationError(malformed_probe.detail)
            service = self._malformed_service
        outcome = service.run(case.url, expected_head_sha=case.head_sha)
        findings = tuple(
            EvalFinding(
                identifier=item.identifier,
                category=item.category.value,
                severity=item.severity,
                path=item.path,
                start_line=item.start_line,
                end_line=item.end_line,
            )
            for item in outcome.accepted
        )
        completed = sum(result.status is SpecialistStatus.SUCCESS for result in outcome.specialists)
        return EvaluationCaseResult(
            case_id=case.id,
            role=case.role,
            status="success",
            findings=findings,
            specialists_completed=completed,
            partial_recovery=(case.role == "malformed-recovery" and outcome.partial),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument(
        "--mode",
        choices=("validate", "clean", "seeded", "recovery", "full", "sequence"),
        default="validate",
    )
    parser.add_argument("--approve-model-calls", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/runs"))
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(
            args.catalog or default_catalog_path(),
            require_live_ready=args.mode != "validate",
        )
    except CatalogError as exc:
        parser.error(str(exc))
    if args.mode == "validate":
        print(f"Catalog valid: {len(catalog.cases)} cases; live readiness not asserted")
        return 0
    if not args.approve_model_calls:
        parser.error(
            "A complete ten-case sequence can make up to two capability probes plus "
            "30 * (LLM_MAX_RETRIES + 1) specialist attempts; pass --approve-model-calls "
            "only after approving that cost"
        )
    if args.mode == "full":
        parser.error("Full-catalog evaluation must run through --mode sequence and its gates")
    try:
        backend = ReadOnlyLiveBackend(AppConfig.from_env(dict(__import__("os").environ)))
    except (ConfigurationError, ValueError) as exc:
        parser.error(str(exc))
    if args.mode == "sequence":
        sequence = run_gate_sequence(catalog, backend, allow_model_calls=True)
        if sequence.stopped_reason is not None:
            for stage in sequence.stages:
                write_minimized_results(catalog, stage.run, args.output_dir, label=stage.name)
            print(f"Evaluation sequence stopped: {sequence.stopped_reason}")
            return 1
        combined = combine_sequence_runs(sequence)
        write_minimized_results(catalog, combined, args.output_dir, label="golden-10")
        return 0
    role_for_mode = {
        "clean": "clean-control",
        "seeded": "seeded-defect",
        "recovery": "malformed-recovery",
    }
    ids = None
    if args.mode in role_for_mode:
        ids = _case_ids(catalog, role_for_mode[args.mode])
    run = run_evaluation(catalog, backend, case_ids=ids, allow_model_calls=True)
    write_minimized_results(catalog, run, args.output_dir, label=args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
