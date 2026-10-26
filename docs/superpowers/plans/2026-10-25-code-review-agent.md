# Code Review Agent implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a safe Streamlit application that reviews an exact GitHub pull-request snapshot with three concurrent AI specialists and publishes one human-approved marker-tagged comment only through a separate default-off component.

**Architecture:** Focused typed modules isolate GitHub reads, bounded context construction, model calls, deterministic validation, LangGraph orchestration, approval state, and GitHub publication. The Streamlit entry point composes those modules but owns no review or publication rules; the evaluation runner uses read-only ports and cannot obtain a publisher.

**Tech Stack:** Python 3.12, Pydantic 2, HTTPX, LangChain, LangGraph, OpenAI-compatible chat API, Streamlit, pytest/pytest-cov, Ruff, build, twine, detect-secrets, pip-audit, python-docx.

**Spec:** `docs/superpowers/specs/2026-10-25-code-review-agent-design.md`

## Global constraints

- Build only in `/Users/sunil/GenAcademyCoursePlayground/Week3/Week3-CodeReviewAgent`; do not inspect or copy the sibling reference implementation.
- The graph must never accept or call a GitHub write client.
- Never execute pull-request code or install pull-request dependencies.
- Never make paid model calls, live black-box evaluation calls, or GitHub writes without explicit user approval at action time.
- Publishing defaults off and requires `ENABLE_GITHUB_PUBLISH=true` plus write credentials.
- Each specialist emits at most three findings and three short validation notes.
- Two specialist failures abort publication; one failure produces a disclosed partial result.
- Application package coverage must be at least 90% with branch measurement.
- Generated evaluation runs contain no source excerpts, prompts, provider responses, or secrets.

## Review focus

- GitHub returns a renamed, deleted-only, binary, or patchless file: context remains bounded and no invalid head-side coordinate becomes publishable (Task 2 tests).
- Repository text contains prompt injection or credential-shaped text: it is fenced, redacted, and never changes tool/control behavior (Task 3 tests).
- A provider accepts basic JSON but rejects richer schema features or returns malformed data: probe/retry/failure policy remains bounded (Task 4 tests).
- A comment create times out after GitHub accepted it: marker search recovers the comment without a duplicate write (Task 7 tests).
- Streamlit reruns after URL, SHA, draft, or edited-body mutation: prior approval is cleared and publish is disabled (Task 8 tests).

---

### Task 1: Project foundation, configuration, and domain schemas

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.env.example`, `.gitignore`, `.secrets.baseline`
- Create: `src/code_review_agent/__init__.py`, `src/code_review_agent/config.py`, `src/code_review_agent/models.py`
- Test: `tests/test_config.py`, `tests/test_models.py`

**Interfaces:**
- Produces: `AppConfig.from_env(env: Mapping[str, str]) -> AppConfig`, `ModelConfig`, `GitHubConfig`, `Limits`, `Finding`, `ProviderFinding`, `SpecialistResult`, `ReviewContext`, `ReviewOutcome`.

- [x] Write tests for safe defaults, per-capability missing/invalid settings, Qwen default, schema list/string limits, closed taxonomies, coordinate validation, and test-gap severity.
- [x] Run `pytest tests/test_config.py tests/test_models.py -q` and confirm failures because the package does not exist.
- [x] Add packaging/configuration and the minimum strict/provider Pydantic models needed by the tests.
- [x] Re-run the focused tests and then `pytest -q`; confirm green.
- [x] Commit the task if repository policy and permissions permit (skipped by recorded dirty-parent ruling).

### Task 2: Canonical URLs and bounded GitHub read/write boundaries

**Files:**
- Create: `src/code_review_agent/github.py`
- Test: `tests/test_github_url.py`, `tests/test_github_read.py`, `tests/test_publisher.py`

**Interfaces:**
- Consumes: `AppConfig`, `PullRequestRef`, `PullRequestSnapshot`, `ChangedFile`.
- Produces: `parse_pull_request_url(url: str) -> PullRequestRef`, `GitHubReadClient`, `GitHubPublisher`, `PublishResult`, injected `httpx.Client` transport.

- [x] Write failing tests for canonical parsing/rejection, pagination, retry-after/transient retry bounds, metadata/files/content retrieval, sanitized errors, stable marker lookup, same-author update, foreign/multiple marker behavior, head mismatch, default-off writes, create, update, and ambiguous-timeout recovery.
- [x] Run focused tests and confirm expected missing-interface failures.
- [x] Implement a GET-only read client and a separately constructed publisher with exact-SHA revalidation and idempotent comment logic.
- [x] Re-run focused tests and full suite; confirm green.
- [x] Commit the task if permitted (skipped by recorded dirty-parent ruling).

### Task 3: Context bounds, redaction, changed-line indexing, and static checks

**Files:**
- Create: `src/code_review_agent/context.py`, `src/code_review_agent/static_analysis.py`
- Test: `tests/test_context.py`, `tests/test_static_analysis.py`

**Interfaces:**
- Consumes: `PullRequestSnapshot`, `ChangedFile`, `Limits`.
- Produces: `build_review_context(...) -> ReviewContext`, `parse_changed_lines(patch: str) -> frozenset[int]`, `redact_secrets(text: str) -> str`, `run_static_checks(context: ReviewContext) -> StaticAnalysisResult`.

- [x] Write failing tests for file/patch/content/total bounds, deterministic truncation, common credential redaction, prompt-injection fencing, head-side patch coordinates, renamed/deleted/binary/patchless files, and explicit static-tool absence.
- [x] Run focused tests and confirm failures for missing behavior.
- [x] Implement pure bounded context and non-executing text/AST checks with availability metadata.
- [x] Re-run focused tests and full suite; confirm green.
- [x] Commit the task if permitted (skipped by recorded dirty-parent ruling).

### Task 4: Provider adapter, capability probe, and specialists

**Files:**
- Create: `src/code_review_agent/llm.py`, `src/code_review_agent/reviewers.py`, `src/code_review_agent/prompts.py`
- Test: `tests/test_llm.py`, `tests/test_reviewers.py`

**Interfaces:**
- Consumes: `ModelConfig`, `ReviewContext`, exact `ProviderSpecialistOutput` schema.
- Produces: `StructuredModelClient.probe() -> ProbeResult`, `StructuredModelClient.review(...) -> SpecialistResult`, `run_specialist(identity, context, client) -> SpecialistResult`.

- [x] Write failing tests for the exact simple provider schema, one capability probe, prompt bounds, untrusted-data instructions, malformed-response retries, strict conversion, identity enforcement, per-specialist limits, and sanitized failures.
- [x] Run focused tests and confirm expected failures.
- [x] Implement the OpenAI-compatible LangChain adapter and three specialist prompt builders; use injected model responses in all offline tests.
- [x] Re-run focused tests and full suite; confirm green without network calls.
- [x] Commit the task if permitted (skipped by recorded dirty-parent ruling).

### Task 5: Deterministic validation, filtering, deduplication, and Markdown

**Files:**
- Create: `src/code_review_agent/validation.py`, `src/code_review_agent/markdown.py`
- Test: `tests/test_validation.py`, `tests/test_markdown.py`

**Interfaces:**
- Consumes: `Finding`, `ReviewContext`, `SpecialistResult`, static status.
- Produces: `validate_findings(...) -> ValidationResult`, `deduplicate_findings(...) -> tuple[Finding, ...]`, `render_review(...) -> str`.

- [x] Write failing tests for changed-file/coordinate/changed-line grounding, subject relevance, specific evidence, actionable recommendations, direct-test contradiction, test-gap severity, stable IDs, deterministic precedence/deduplication, ordering, partial disclosure, marker inclusion, and byte-identical Markdown.
- [x] Run focused tests and confirm failures.
- [x] Implement conservative pure validators and renderer from the design's deterministic rules.
- [x] Re-run focused tests and full suite; confirm green.
- [x] Commit the task if permitted (skipped by recorded dirty-parent ruling).

### Task 6: Concurrent LangGraph workflow and failure policy

**Files:**
- Create: `src/code_review_agent/graph.py`, `src/code_review_agent/service.py`
- Test: `tests/test_graph.py`, `tests/test_service.py`

**Interfaces:**
- Consumes: `ReviewContext`, specialist callables, validators, renderer.
- Produces: `build_review_graph(reviewers: ReviewerSet) -> CompiledStateGraph`, `ReviewService.preview(...)`, `ReviewService.run(...) -> ReviewOutcome`.

- [x] Write failing tests proving all three nodes fan out, results join, one failure is partial/disclosed, two failures abort with diagnostics and no review body, zero findings is safe, and the graph contains no publisher/write dependency.
- [x] Run focused tests and confirm failures.
- [x] Implement typed state, conditional fan-in finalization, and orchestration service.
- [x] Re-run focused tests and full suite; confirm green.
- [x] Commit the task if permitted (skipped by recorded dirty-parent ruling).

### Task 7: Approval fingerprints and controlled publication

**Files:**
- Create: `src/code_review_agent/approval.py`
- Modify: `src/code_review_agent/github.py`
- Test: `tests/test_approval.py`, `tests/test_publisher.py`

**Interfaces:**
- Produces: `approval_fingerprint(url, head_sha, generated_markdown, edited_markdown) -> str`, `ApprovalState`, `can_publish(...) -> bool`.

- [x] Write failing tests for exact-body approval, every reset input, aborted/partial states, disabled configuration, missing token, SHA revalidation, unchanged approved body, and returned created/updated comment IDs.
- [x] Run focused tests and confirm failures.
- [x] Implement immutable approval state and compose it with the publisher preconditions.
- [x] Re-run focused tests and full suite; confirm green.
- [x] Commit the task if permitted (skipped by recorded dirty-parent ruling).

### Task 8: Streamlit workflow and headless UI tests

**Files:**
- Create: `streamlit_app.py`, `src/code_review_agent/ui_state.py`, `.streamlit/config.toml`
- Test: `tests/test_ui_state.py`, `tests/test_streamlit_app.py`

**Interfaces:**
- Consumes: `ReviewService`, `ApprovalState`, `GitHubPublisher` only after UI gates.
- Produces: one-page preview/review/approve/publish workflow and pure UI-state transition helpers.

- [x] Write failing pure and `st.testing.v1.AppTest` tests for startup without credentials, canonical input, separate preview/review actions, metadata fields, specialist statuses, unavailable/partial/abort disclosure, exact Markdown editing, approval reset, default-off publish, and comment ID display.
- [x] Run focused tests and confirm failures.
- [x] Implement the native Streamlit UI using forms/containers/session state with no custom HTML/CSS.
- [x] Re-run focused tests and full suite; confirm green.
- [x] Commit the task if permitted (skipped by recorded dirty-parent ruling).

### Task 9: Source-free evaluation harness and security tooling

**Files:**
- Create: `evaluation/catalog.json`, `src/code_review_agent/evaluation.py`, `scripts/run_evaluation.py`, `scripts/scan_tracked_secrets.py`
- Test: `tests/test_evaluation.py`, `tests/test_secret_scanner.py`

**Interfaces:**
- Produces: `load_catalog(...)`, `run_evaluation(...)`, `compute_metrics(...)`, minimized JSON/Markdown serializers, CLI exit codes.

- [x] Write failing tests for exactly five case roles, pinned-SHA preflight before model calls, clean/seeded/full gates, continue-on-operational-failure, malformed recovery, N/A metrics, minimized artifacts, no publisher construction, and tracked-file secret detection.
- [x] Run focused tests and confirm failures.
- [x] Implement a placeholder-safe catalog schema, read-only evaluator, metrics, artifacts, scanner, and documented approval guard for live calls.
- [x] Re-run focused tests and full suite; confirm green.
- [x] Commit the task if permitted (skipped by recorded dirty-parent ruling).

### Task 10: Documentation and Google Docs-ready DOCX

**Files:**
- Create: `README.md`, `docs/architecture.md`, `docs/security.md`, `docs/evaluation-report.md`, `docs/functional-acceptance-report.md`, `docs/project-documentation.md`, `docs/video-demo-script.md`, `docs/Week3-CodeReviewAgent-Project-Documentation.docx`
- Test: `tests/test_documentation.py`

**Interfaces:**
- Produces: reproducible operator/developer docs, evidence-class labels, demo script under five minutes, rendered DOCX.

- [x] Write a failing documentation-presence/content test for required files, commands, evidence distinctions, limitations, one-liner/framework, and no false live-evaluation claim.
- [x] Run the focused test and confirm failures.
- [x] Write Markdown documentation from verified behavior and generate the DOCX with headings, tables, and code-safe styling.
- [x] Render the DOCX to page images/PDF, inspect every page, correct layout defects, and re-run the documentation test.
- [x] Commit the task if permitted (skipped by recorded dirty-parent ruling).

### Task 11: Full verification and honest acceptance report

**Files:**
- Modify: `docs/functional-acceptance-report.md`, `docs/evaluation-report.md`, `README.md`

**Interfaces:**
- Consumes: all build/test/security/package commands.
- Produces: timestamped command evidence and an explicit pending list for work requiring credentials/approval.

- [x] Run `pytest --cov=code_review_agent --cov-branch --cov-fail-under=90`.
- [x] Run `ruff check .` and `ruff format --check .`.
- [x] Run the tracked-file scanner and `detect-secrets scan --baseline .secrets.baseline` verification.
- [x] Run `pip-audit`, `python -m build`, `twine check dist/*`, and inspect wheel/sdist file lists.
- [x] Start Streamlit on a temporary local port, wait for health, fetch it, then terminate it.
- [x] Run only offline evaluation validation; do not run live clean/seeded/full gates without explicit approval.
- [x] Update reports with exact pass/fail/N/A evidence and re-run the relevant tests.
- [x] Invoke `superpowers:verification-before-completion` before making any completion claim.
