from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from code_review_agent import evaluation
from code_review_agent.config import AppConfig
from code_review_agent.evaluation import (
    ApprovalRequired,
    CatalogError,
    EvalFinding,
    EvaluationBackend,
    EvaluationCaseResult,
    EvaluationCatalog,
    ReadOnlyLiveBackend,
    combine_sequence_runs,
    compute_metrics,
    load_catalog,
    main,
    run_evaluation,
    run_gate_sequence,
    write_minimized_results,
)
from code_review_agent.llm import ProbeResult
from code_review_agent.models import (
    Category,
    ChangedFile,
    Finding,
    PullRequestMetadata,
    PullRequestSnapshot,
    ReviewerIdentity,
    SpecialistResult,
    SpecialistStatus,
)

SHA = "a" * 40


def catalog_payload() -> dict[str, object]:
    roles = [
        "seeded-defect",
        "clean-control",
        "seeded-defect",
        "seeded-defect",
        "seeded-defect",
        "seeded-defect",
        "seeded-defect",
        "seeded-defect",
        "clean-control",
        "malformed-recovery",
    ]
    cases = []
    for index, role in enumerate(roles, start=1):
        expected = []
        if role != "clean-control":
            expected = [
                {
                    "category_aliases": ["correctness"],
                    "path": "src/widget.py",
                    "start_line": 10,
                    "end_line": 12,
                    "min_severity": "low",
                    "max_severity": "high",
                }
            ]
        cases.append(
            {
                "id": f"golden-{index:02d}",
                "role": role,
                "url": f"https://github.com/acme/golden/pull/{index}",
                "head_sha": f"{index:040x}",
                "expected": expected,
            }
        )
    return {"version": 2, "cases": cases}


def write_catalog(path: Path) -> Path:
    path.write_text(json.dumps(catalog_payload()), encoding="utf-8")
    return path


def test_catalog_requires_exact_ten_case_golden_profile(tmp_path: Path) -> None:
    catalog = load_catalog(write_catalog(tmp_path / "catalog.json"))

    assert catalog.version == 2
    assert len(catalog.cases) == 10
    assert Counter(case.role for case in catalog.cases) == Counter(
        {"seeded-defect": 7, "clean-control": 2, "malformed-recovery": 1}
    )
    assert [case.id for case in catalog.cases] == [f"golden-{index:02d}" for index in range(1, 11)]
    assert all(not case.expected for case in catalog.cases if case.role == "clean-control")
    assert all(case.expected for case in catalog.cases if case.role != "clean-control")
    assert len({case.url for case in catalog.cases}) == 10
    assert len({(case.url, case.head_sha) for case in catalog.cases}) == 10

    payload = catalog_payload()
    payload["cases"][0]["head_sha"] = "0" * 40  # type: ignore[index]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogError, match="placeholder"):
        load_catalog(bad, require_live_ready=True)


@pytest.mark.parametrize("case_count", [9, 11])
def test_catalog_rejects_wrong_case_count(case_count: int) -> None:
    payload = catalog_payload()
    cases = payload["cases"]  # type: ignore[assignment]
    if case_count == 9:
        del cases[-1]  # type: ignore[index]
    else:
        extra = deepcopy(cases[0])  # type: ignore[index]
        extra.update(
            {
                "id": "golden-11",
                "url": "https://github.com/acme/golden/pull/11",
                "head_sha": f"{11:040x}",
            }
        )
        cases.append(extra)  # type: ignore[union-attr]

    with pytest.raises(ValueError):
        EvaluationCatalog.model_validate(payload)


@pytest.mark.parametrize(
    "mutation",
    ["wrong-role-counts", "duplicate-url", "duplicate-id", "clean-expected", "defect-empty"],
)
def test_catalog_rejects_invalid_golden_profile(mutation: str) -> None:
    payload = catalog_payload()
    cases = payload["cases"]  # type: ignore[assignment]
    if mutation == "wrong-role-counts":
        cases[1]["role"] = "seeded-defect"  # type: ignore[index]
        cases[1]["expected"] = deepcopy(cases[0]["expected"])  # type: ignore[index]
    elif mutation == "duplicate-url":
        cases[1]["url"] = cases[0]["url"]  # type: ignore[index]
    elif mutation == "duplicate-id":
        cases[1]["id"] = cases[0]["id"]  # type: ignore[index]
    elif mutation == "clean-expected":
        cases[1]["expected"] = deepcopy(cases[0]["expected"])  # type: ignore[index]
    else:
        cases[0]["expected"] = []  # type: ignore[index]

    with pytest.raises(ValueError):
        EvaluationCatalog.model_validate(payload)


@pytest.mark.parametrize(
    "mutation",
    ["unknown-category", "unsafe-path", "duplicate-alias", "reversed-severity"],
)
def test_expected_findings_reject_invalid_closed_fields(mutation: str) -> None:
    payload = catalog_payload()
    expected = payload["cases"][0]["expected"][0]  # type: ignore[index]
    if mutation == "unknown-category":
        expected["category_aliases"] = ["typo-category"]
    elif mutation == "unsafe-path":
        expected["path"] = "../../outside.py"
    elif mutation == "duplicate-alias":
        expected["category_aliases"] = ["correctness", "correctness"]
    else:
        expected["min_severity"] = "high"
        expected["max_severity"] = "low"

    with pytest.raises(ValueError):
        EvaluationCatalog.model_validate(payload)


class FakeBackend(EvaluationBackend):
    def __init__(
        self,
        *,
        mismatch: str | None = None,
        head_failure: str | None = None,
        failure: str | None = None,
        clean_finding: bool = False,
        missing_finding: str | None = None,
        recovery_partial: bool = True,
        recovery_completed: int = 2,
    ) -> None:
        self.events: list[str] = []
        self.mismatch = mismatch
        self.head_failure = head_failure
        self.failure = failure
        self.clean_finding = clean_finding
        self.missing_finding = missing_finding
        self.recovery_partial = recovery_partial
        self.recovery_completed = recovery_completed

    def head_sha(self, case) -> str:
        self.events.append(f"head:{case.id}")
        if case.id == self.head_failure:
            raise RuntimeError("provider secret body")
        return "b" * 40 if case.id == self.mismatch else case.head_sha

    def review(self, case) -> EvaluationCaseResult:
        self.events.append(f"review:{case.id}")
        if case.id == self.failure:
            raise RuntimeError("provider secret body")
        findings = ()
        if (case.expected and case.id != self.missing_finding) or (
            case.role == "clean-control" and self.clean_finding
        ):
            findings = (
                EvalFinding(
                    identifier=f"{case.id}.finding",
                    category="correctness",
                    severity="medium",
                    path="src/widget.py",
                    start_line=10,
                    end_line=12,
                ),
            )
        return EvaluationCaseResult(
            case_id=case.id,
            role=case.role,
            status="success",
            findings=findings,
            specialists_completed=(
                self.recovery_completed if case.role == "malformed-recovery" else 3
            ),
            partial_recovery=(
                self.recovery_partial if case.role == "malformed-recovery" else False
            ),
        )


def catalog() -> EvaluationCatalog:
    return EvaluationCatalog.model_validate(catalog_payload())


def test_model_calls_require_explicit_approval() -> None:
    backend = FakeBackend()

    with pytest.raises(ApprovalRequired):
        run_evaluation(catalog(), backend, allow_model_calls=False)

    assert backend.events == []


def test_all_selected_heads_are_preflighted_before_first_model_call() -> None:
    backend = FakeBackend()

    result = run_evaluation(catalog(), backend, allow_model_calls=True)

    assert len(result.cases) == 10
    first_review = next(i for i, event in enumerate(backend.events) if event.startswith("review:"))
    assert all(event.startswith("head:") for event in backend.events[:first_review])
    assert first_review == 10


def test_head_mismatch_skips_that_model_call_but_later_cases_continue() -> None:
    backend = FakeBackend(mismatch="golden-03")

    result = run_evaluation(catalog(), backend, allow_model_calls=True)

    by_id = {case.case_id: case for case in result.cases}
    assert by_id["golden-03"].status == "head-mismatch"
    assert "review:golden-03" not in backend.events
    assert "review:golden-04" in backend.events


def test_operational_failure_is_sanitized_and_later_cases_continue() -> None:
    backend = FakeBackend(failure="golden-03")

    result = run_evaluation(catalog(), backend, allow_model_calls=True)

    by_id = {case.case_id: case for case in result.cases}
    assert by_id["golden-03"].status == "operational-failure"
    assert by_id["golden-03"].error == "Evaluation case failed operationally"
    assert "secret" not in (by_id["golden-03"].error or "")
    assert "review:golden-04" in backend.events


def test_sequence_preflights_all_ten_heads_before_first_review() -> None:
    backend = FakeBackend()

    run_gate_sequence(catalog(), backend, allow_model_calls=True)

    first_review = next(i for i, event in enumerate(backend.events) if event.startswith("review:"))
    assert backend.events[:first_review] == [f"head:golden-{index:02d}" for index in range(1, 11)]


@pytest.mark.parametrize("failure_kind", ["mismatch", "exception"])
def test_sequence_preflight_failure_stops_before_all_model_calls(failure_kind: str) -> None:
    kwargs = {failure_kind if failure_kind == "mismatch" else "head_failure": "golden-08"}
    backend = FakeBackend(**kwargs)

    sequence = run_gate_sequence(catalog(), backend, allow_model_calls=True)

    assert [stage.name for stage in sequence.stages] == ["preflight"]
    assert sequence.stopped_reason == "catalog-preflight-failed"
    assert not any(event.startswith("review:") for event in backend.events)
    failed = sequence.stages[0].run.cases[0]
    assert failed.case_id == "golden-08"
    assert failed.status == (
        "head-mismatch" if failure_kind == "mismatch" else "operational-failure"
    )
    assert "secret" not in (failed.error or "")


def test_clean_gate_stops_sequence_on_any_publishable_finding() -> None:
    backend = FakeBackend(clean_finding=True)

    sequence = run_gate_sequence(catalog(), backend, allow_model_calls=True)

    assert [stage.name for stage in sequence.stages] == ["clean-controls"]
    assert sequence.stopped_reason == "clean-controls-produced-findings"
    assert not any(event.startswith("review:golden-01") for event in backend.events)


def test_passing_sequence_runs_two_clean_then_seven_seeded_then_recovery_once() -> None:
    backend = FakeBackend()

    sequence = run_gate_sequence(catalog(), backend, allow_model_calls=True)

    assert [stage.name for stage in sequence.stages] == [
        "clean-controls",
        "seeded-defects",
        "malformed-recovery",
    ]
    assert sequence.stopped_reason is None
    expected_review_order = [
        "review:golden-02",
        "review:golden-09",
        "review:golden-01",
        "review:golden-03",
        "review:golden-04",
        "review:golden-05",
        "review:golden-06",
        "review:golden-07",
        "review:golden-08",
        "review:golden-10",
    ]
    review_events = [event for event in backend.events if event.startswith("review:")]
    assert review_events == expected_review_order
    assert all(backend.events.count(event) == 1 for event in expected_review_order)

    combined = combine_sequence_runs(sequence)
    assert [case.case_id for case in combined.cases] == [
        event.removeprefix("review:") for event in expected_review_order
    ]
    assert len({case.case_id for case in combined.cases}) == 10


def test_overlapping_expectations_use_complete_one_to_one_assignment() -> None:
    payload = catalog_payload()
    payload["cases"][0]["expected"] = [  # type: ignore[index]
        {
            "category_aliases": ["correctness", "security"],
            "path": "src/widget.py",
            "start_line": 10,
            "end_line": 12,
            "min_severity": "low",
            "max_severity": "high",
        },
        {
            "category_aliases": ["correctness"],
            "path": "src/widget.py",
            "start_line": 10,
            "end_line": 10,
            "min_severity": "low",
            "max_severity": "high",
        },
    ]
    overlapping_catalog = EvaluationCatalog.model_validate(payload)

    class OverlappingBackend(FakeBackend):
        def review(self, case) -> EvaluationCaseResult:
            if case.id != "golden-01":
                return super().review(case)
            self.events.append(f"review:{case.id}")
            return EvaluationCaseResult(
                case_id=case.id,
                role=case.role,
                status="success",
                findings=(
                    EvalFinding(
                        identifier="golden-01.correctness",
                        category="correctness",
                        severity="medium",
                        path="src/widget.py",
                        start_line=10,
                        end_line=10,
                    ),
                    EvalFinding(
                        identifier="golden-01.security",
                        category="security",
                        severity="medium",
                        path="src/widget.py",
                        start_line=12,
                        end_line=12,
                    ),
                ),
                specialists_completed=3,
            )

    sequence = run_gate_sequence(overlapping_catalog, OverlappingBackend(), allow_model_calls=True)

    assert sequence.stopped_reason is None
    metrics = compute_metrics(overlapping_catalog, combine_sequence_runs(sequence))
    assert metrics["recall"] == 1.0
    assert metrics["precision"] == 1.0


def test_clean_operational_failure_stops_before_seeded_reviews() -> None:
    backend = FakeBackend(failure="golden-09")

    sequence = run_gate_sequence(catalog(), backend, allow_model_calls=True)

    assert sequence.stopped_reason == "clean-controls-operational-failure"
    assert not any(event == "review:golden-01" for event in backend.events)


@pytest.mark.parametrize(
    ("backend", "reason"),
    [
        (FakeBackend(missing_finding="golden-06"), "seeded-defects-gate-failed"),
        (FakeBackend(failure="golden-03"), "seeded-defects-gate-failed"),
        (FakeBackend(recovery_partial=False), "malformed-recovery-gate-failed"),
        (FakeBackend(recovery_completed=3), "malformed-recovery-gate-failed"),
        (FakeBackend(missing_finding="golden-10"), "malformed-recovery-gate-failed"),
    ],
)
def test_seeded_and_recovery_gate_policies(backend: FakeBackend, reason: str) -> None:
    sequence = run_gate_sequence(catalog(), backend, allow_model_calls=True)

    assert sequence.stopped_reason == reason
    if reason == "seeded-defects-gate-failed":
        assert "review:golden-10" not in backend.events


def test_metrics_report_values_or_na_without_division_errors() -> None:
    result = run_evaluation(catalog(), FakeBackend(), allow_model_calls=True)

    metrics = compute_metrics(catalog(), result)

    assert metrics["recall"] == 1.0
    assert metrics["precision"] == 1.0
    assert metrics["severity_agreement"] == 1.0
    assert metrics["location_agreement"] == 1.0
    assert metrics["duplicate_rate"] == 0.0
    assert metrics["partial_recovery"] is True
    assert metrics["clean_control"] is True

    clean_only = run_evaluation(
        catalog(), FakeBackend(), case_ids=("golden-02",), allow_model_calls=True
    )
    clean_metrics = compute_metrics(catalog(), clean_only)
    assert clean_metrics["recall"] == "N/A"
    assert clean_metrics["precision"] == "N/A"


def test_result_artifacts_are_timestamped_minimized_and_source_free(tmp_path: Path) -> None:
    result = run_evaluation(catalog(), FakeBackend(), allow_model_calls=True)

    json_path, markdown_path = write_minimized_results(
        catalog(), result, tmp_path, timestamp="20261025T120000Z"
    )

    assert json_path.name == "evaluation-20261025T120000Z.json"
    assert markdown_path.name == "evaluation-20261025T120000Z.md"
    text = json_path.read_text(encoding="utf-8")
    assert '"identifier"' in text
    assert '"category"' in text
    assert '"start_line"' in text
    assert "evidence" not in text.casefold()
    assert "recommendation" not in text.casefold()
    assert "provider secret" not in text.casefold()


def test_combined_ten_case_artifact_is_unique_and_contains_only_minimized_results(
    tmp_path: Path,
) -> None:
    sequence = run_gate_sequence(catalog(), FakeBackend(), allow_model_calls=True)
    combined = combine_sequence_runs(sequence)

    json_path, markdown_path = write_minimized_results(
        catalog(), combined, tmp_path, timestamp="20261025T120000Z", label="golden-10"
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(payload["cases"]) == 10
    assert len({case["case_id"] for case in payload["cases"]}) == 10
    assert payload["metrics"]
    rendered = (
        json_path.read_text(encoding="utf-8") + markdown_path.read_text(encoding="utf-8")
    ).casefold()
    for required in ("category", "severity", "start_line", "end_line"):
        assert required in rendered
    for forbidden in (
        "source",
        "evidence",
        "recommendation",
        "system prompt",
        "pull request body",
        "provider secret body",
        "llm_api_key",
    ):
        assert forbidden not in rendered


def test_result_artifact_labels_prevent_same_timestamp_stage_collisions(tmp_path: Path) -> None:
    result = run_evaluation(catalog(), FakeBackend(), allow_model_calls=True)

    clean_paths = write_minimized_results(
        catalog(), result, tmp_path, timestamp="20261025T120000Z", label="clean-control"
    )
    seeded_paths = write_minimized_results(
        catalog(), result, tmp_path, timestamp="20261025T120000Z", label="seeded-defect"
    )

    assert clean_paths[0] != seeded_paths[0]
    assert clean_paths[0].name.endswith("-clean-control.json")
    assert seeded_paths[0].name.endswith("-seeded-defect.json")


def test_backend_protocol_has_no_publication_capability() -> None:
    backend = FakeBackend()

    assert not hasattr(backend, "publish")


def test_preflight_failure_is_recorded_without_reviewing_that_case() -> None:
    class FailingHeadBackend(FakeBackend):
        def head_sha(self, case) -> str:
            self.events.append(f"head:{case.id}")
            if case.id == "golden-03":
                raise RuntimeError("network details")
            return case.head_sha

    backend = FailingHeadBackend()

    result = run_evaluation(catalog(), backend, allow_model_calls=True)

    failed = next(item for item in result.cases if item.case_id == "golden-03")
    assert failed.status == "operational-failure"
    assert failed.error == "Pinned-head preflight failed operationally"
    assert "review:golden-03" not in backend.events


def test_metrics_count_duplicates_and_unmatched_predictions() -> None:
    duplicate = EvalFinding(
        identifier="duplicate",
        category="security",
        severity="info",
        path="other.py",
        start_line=1,
        end_line=1,
    )
    run = evaluation.EvaluationRun(
        cases=(
            EvaluationCaseResult(
                case_id="golden-01",
                role="seeded-defect",
                status="success",
                findings=(duplicate, duplicate),
                specialists_completed=1,
            ),
        )
    )

    metrics = compute_metrics(catalog(), run)

    assert metrics["recall"] == 0.0
    assert metrics["precision"] == 0.0
    assert metrics["severity_agreement"] == "N/A"
    assert metrics["duplicate_rate"] == 0.5
    assert metrics["specialist_completion"] == pytest.approx(1 / 3)


def test_metrics_use_one_to_one_matching_and_independent_location_agreement() -> None:
    payload = catalog_payload()
    payload["cases"][0]["expected"].append(  # type: ignore[index,union-attr]
        dict(payload["cases"][0]["expected"][0])  # type: ignore[index,call-overload]
    )
    duplicated_catalog = EvaluationCatalog.model_validate(payload)
    finding = EvalFinding(
        identifier="one-prediction",
        category="correctness",
        severity="medium",
        path="src/widget.py",
        start_line=10,
        end_line=12,
    )
    duplicated_run = evaluation.EvaluationRun(
        cases=(
            EvaluationCaseResult(
                case_id="golden-01",
                role="seeded-defect",
                status="success",
                findings=(finding,),
                specialists_completed=3,
            ),
        )
    )

    duplicated_metrics = compute_metrics(duplicated_catalog, duplicated_run)
    assert duplicated_metrics["recall"] == 0.5
    assert duplicated_metrics["precision"] == 1.0

    far_finding = finding.model_copy(
        update={"identifier": "far-location", "start_line": 50, "end_line": 50}
    )
    far_run = evaluation.EvaluationRun(
        cases=(
            EvaluationCaseResult(
                case_id="golden-01",
                role="seeded-defect",
                status="success",
                findings=(far_finding,),
                specialists_completed=3,
            ),
        )
    )

    far_metrics = compute_metrics(catalog(), far_run)
    assert far_metrics["recall"] == 1.0
    assert far_metrics["precision"] == 1.0
    assert far_metrics["location_agreement"] == 0.0


def accepted_finding() -> Finding:
    return Finding(
        identifier="correctness.widget-check",
        category=Category.CORRECTNESS,
        severity="medium",
        title="Widget validation result is ignored",
        path="src/widget.py",
        start_line=10,
        end_line=10,
        subject="validate_widget",
        evidence="validate_widget is called without checking its result",
        impact="Invalid widgets may continue into request processing",
        recommendation="Check validate_widget result and return a clear error",
        reviewer=ReviewerIdentity.CORRECTNESS,
    )


def test_read_only_live_backend_maps_snapshot_and_source_free_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_metadata(self, ref):
            return SimpleNamespace(head_sha=SHA)

    class Service:
        def __init__(self, reader, reviewers, limits) -> None:
            self.reviewers = reviewers
            self.expected_head_sha = None

        def run(self, url: str, *, expected_head_sha: str | None = None):
            self.expected_head_sha = expected_head_sha
            metadata = PullRequestMetadata(
                owner="acme",
                repo="project-5",
                number=5,
                url=url,
                title="Recover malformed output",
                author="octocat",
                base_branch="main",
                head_branch="recovery",
                head_sha=SHA,
            )
            specialists = (
                SpecialistResult(
                    identity=ReviewerIdentity.CORRECTNESS,
                    status=SpecialistStatus.SUCCESS,
                    attempts=1,
                ),
                SpecialistResult(
                    identity=ReviewerIdentity.SECURITY,
                    status=SpecialistStatus.SUCCESS,
                    attempts=1,
                ),
                SpecialistResult(
                    identity=ReviewerIdentity.TEST_COVERAGE,
                    status=SpecialistStatus.FAILED,
                    attempts=2,
                    failure="sanitized failure",
                ),
            )
            return SimpleNamespace(
                metadata=metadata,
                accepted=(accepted_finding(),),
                specialists=specialists,
                partial=True,
            )

    class Model:
        def probe(self) -> ProbeResult:
            return ProbeResult(True, "supported")

    monkeypatch.setattr(evaluation, "ReviewService", Service)
    config = AppConfig.from_env(
        {
            "LLM_API_KEY": "placeholder-key",
            "LLM_BASE_URL": "https://models.example.test/v1",
        }
    )
    backend = ReadOnlyLiveBackend(config, reader=Reader(), model_client=Model())
    case = catalog().cases[-1]

    assert backend.head_sha(case) == SHA
    result = backend.review(case)
    assert result.status == "success"
    assert result.specialists_completed == 2
    assert result.partial_recovery is True
    assert result.findings[0].category == "correctness"
    assert backend._malformed_service.expected_head_sha == case.head_sha
    assert not hasattr(backend, "publish")


def test_malformed_recovery_injects_one_specialist_failure_end_to_end() -> None:
    case = catalog().cases[-1]

    class Reader:
        def get_metadata(self, ref):
            return PullRequestMetadata(
                owner=ref.owner,
                repo=ref.repo,
                number=ref.number,
                url=ref.canonical_url,
                title="Malformed recovery",
                author="octocat",
                base_branch="main",
                head_branch="recovery",
                head_sha=case.head_sha,
            )

        def fetch_snapshot(self, ref, limits):
            return PullRequestSnapshot(
                metadata=self.get_metadata(ref),
                files=(
                    ChangedFile(
                        path="src/widget.py",
                        status="modified",
                        additions=1,
                        deletions=0,
                        changes=1,
                        patch="@@ -9,0 +10 @@\n+validate_widget()",
                        content="\n" * 9 + "validate_widget()\n",
                    ),
                ),
            )

    class Model:
        def __init__(self) -> None:
            self.probe_calls = 0
            self.review_calls: list[ReviewerIdentity] = []

        def probe(self) -> ProbeResult:
            self.probe_calls += 1
            return ProbeResult(True, "supported")

        def review(self, identity, context):
            self.review_calls.append(identity)
            return SpecialistResult(
                identity=identity,
                status=SpecialistStatus.SUCCESS,
                attempts=1,
            )

    model = Model()
    config = AppConfig.from_env(
        {
            "LLM_API_KEY": "placeholder-key",
            "LLM_BASE_URL": "https://models.example.test/v1",
            "LLM_MAX_RETRIES": "1",
        }
    )
    backend = ReadOnlyLiveBackend(config, reader=Reader(), model_client=model)

    result = backend.review(case)

    assert result.status == "success"
    assert result.specialists_completed == 2
    assert result.partial_recovery is True
    assert model.probe_calls == 1
    assert set(model.review_calls) == {
        ReviewerIdentity.CORRECTNESS,
        ReviewerIdentity.SECURITY,
    }


def test_cli_validate_mode_is_offline_and_reports_catalog(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_catalog(tmp_path / "catalog.json")

    assert main(["--catalog", str(path), "--mode", "validate"]) == 0
    assert "Catalog valid: 10 cases" in capsys.readouterr().out


def test_default_catalog_is_available_outside_source_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root_catalog = Path(__file__).parents[1] / "evaluation" / "catalog.json"
    root_bytes = root_catalog.read_bytes()
    monkeypatch.chdir(tmp_path)

    path = evaluation.default_catalog_path()
    packaged_catalog = load_catalog(path, require_live_ready=True)

    assert path.is_file()
    assert len(packaged_catalog.cases) == 10
    assert path.read_bytes() == root_bytes


def test_cli_rejects_live_mode_without_explicit_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(evaluation, "load_catalog", lambda *args, **kwargs: catalog())

    with pytest.raises(SystemExit) as caught:
        main(["--mode", "full"])

    assert caught.value.code == 2


@pytest.mark.parametrize(
    ("mode", "expected_writes"),
    [("clean", [2]), ("seeded", [7]), ("recovery", [1]), ("sequence", [10])],
)
def test_cli_live_modes_route_to_read_only_backend_and_write_minimized_results(
    mode: str,
    expected_writes: list[int],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    writes: list[int] = []
    monkeypatch.setattr(evaluation, "load_catalog", lambda *args, **kwargs: catalog())
    monkeypatch.setattr(evaluation, "ReadOnlyLiveBackend", lambda config: backend)
    monkeypatch.setattr(
        evaluation,
        "write_minimized_results",
        lambda selected_catalog, run, output, **kwargs: writes.append(len(run.cases)),
    )

    result = main(
        [
            "--mode",
            mode,
            "--approve-model-calls",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert writes == expected_writes


def test_cli_failed_sequence_writes_only_available_sanitized_stage_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend(missing_finding="golden-06")
    writes: list[tuple[str | None, tuple[str, ...]]] = []
    monkeypatch.setattr(evaluation, "load_catalog", lambda *args, **kwargs: catalog())
    monkeypatch.setattr(evaluation, "ReadOnlyLiveBackend", lambda config: backend)
    monkeypatch.setattr(
        evaluation,
        "write_minimized_results",
        lambda selected_catalog, run, output, **kwargs: writes.append(
            (kwargs.get("label"), tuple(case.case_id for case in run.cases))
        ),
    )

    result = main(
        [
            "--mode",
            "sequence",
            "--approve-model-calls",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert result == 1
    assert writes == [
        ("clean-controls", ("golden-02", "golden-09")),
        (
            "seeded-defects",
            (
                "golden-01",
                "golden-03",
                "golden-04",
                "golden-05",
                "golden-06",
                "golden-07",
                "golden-08",
            ),
        ),
    ]


def test_cli_full_mode_cannot_bypass_required_gate_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    monkeypatch.setattr(evaluation, "load_catalog", lambda *args, **kwargs: catalog())
    monkeypatch.setattr(
        evaluation,
        "ReadOnlyLiveBackend",
        lambda config: pytest.fail("full mode constructed a live backend"),
    )

    with pytest.raises(SystemExit) as caught:
        main(["--mode", "full", "--approve-model-calls"])

    assert caught.value.code == 2
    assert backend.events == []
