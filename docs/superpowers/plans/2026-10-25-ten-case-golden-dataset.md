# Ten-Case Synthetic Golden Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder five-case evaluator input with ten pinned synthetic GitHub pull requests and a non-repeating, clean-first golden evaluation sequence.

**Architecture:** Eight new isolated fixture branches join the two existing demo PRs. The typed catalog becomes an exact version-2 ten-case contract; a shared preflight checks every pin before any model call, then clean, seeded, and malformed-recovery groups run once and combine into one minimized result. GitHub fixture creation and local evaluator changes remain separate boundaries, and neither model calls nor review-comment publication occur during implementation.

**Tech Stack:** Python 3.12, Pydantic 2, pytest, GitHub repository APIs, existing LangGraph review backend, Ruff, python-docx.

**Spec:** `docs/superpowers/specs/2026-10-25-ten-case-golden-dataset-design.md`

## Global Constraints

- Work only in `melepatt/code-review-agent-demo` remotely and `Week3-CodeReviewAgent` locally.
- Reuse PRs 1 and 2; create exactly eight more open PRs, each from the current `main` SHA and never from another fixture branch.
- Use stable `golden/` branches, neutral PR metadata, and no expected-answer leakage.
- Do not call a model, create review comments, merge PRs, enable publication, or read/print `.env` values.
- Catalog roles are exactly seven `seeded-defect`, two `clean-control`, and one `malformed-recovery`; IDs are `golden-01` through `golden-10`.
- Store only canonical URLs, 40-character head SHAs, expected category aliases, paths, head-side ranges, and severity ranges in the catalog.
- Preserve source-free artifacts, default-off publication, and the read-only evaluation backend.
- The parent repository is already dirty and this project is untracked; do not commit or alter unrelated parent files. Record task checkpoints in the existing SDD ledger instead.

## Review Focus

- A partially completed remote run must reuse matching stable branches/PRs and stop on mismatched content rather than create duplicates; exercised in Task 1 preflight and verification.
- PR metadata must not reveal labels even for the two existing fixtures; exercised by Task 1 metadata assertions.
- One bad pin among the later seeded cases must stop all model calls before clean controls begin; exercised by Task 3 whole-catalog preflight tests.
- Multiple same-role cases must all run exactly once and preserve catalog order; exercised by Task 3 event-order tests.
- A malformed-recovery case that is not partial, has the wrong number of completed specialists, or misses its expected finding must fail the final gate; exercised by Task 3 recovery tests.

---

### Task 1: Create and verify the ten neutral GitHub fixture PRs

**Files:**
- Remote modify: `melepatt/code-review-agent-demo` PR 1 title/body
- Remote modify: `melepatt/code-review-agent-demo` PR 2 title/body
- Remote create: branches `golden/03-loyalty-boundary` through `golden/10-malformed-recovery`
- Remote create: eight pull requests against `main`
- Modify: `.superpowers/sdd/2026-10-25-code-review-agent/progress.md`

**Interfaces:**
- Consumes: current `main` SHA and existing PR 1/2 metadata from GitHub.
- Produces: ten verified open PR URLs, head SHAs, changed paths, and head-side ranges for Task 2.

- [x] **Step 1: Preflight the remote namespace without mutation**

Fetch repository metadata, `main`, branches matching `golden/*`, and all open PRs. Assert that PRs 1
and 2 are open against `main`. For each planned stable branch, either confirm it is absent or confirm
its tree and open PR already match this plan. Stop on any conflicting branch or PR.

- [x] **Step 2: Neutralize existing PR metadata**

Update only title/body:

- PR 1 title: `Fixture 01: order metrics and report runner`
- PR 2 title: `Fixture 02: order count metric`
- Both bodies: identify the PR as an isolated synthetic Code Review Agent benchmark fixture, say it
  must not be merged, and disclose no expected category or outcome.

Fetch both PRs and assert their URLs, head SHAs, branches, diffs, and open state did not change; assert
their title/body contain none of `defect`, `finding`, `security`, `correctness`, `test gap`, or `clean`.

- [x] **Step 3: Create correctness fixtures 03 and 04 from `main`**

Create one commit and one PR per branch:

- `golden/03-loyalty-boundary` adds `src/order_tools/discounts.py` with
  `loyalty_price(subtotal: float, years: int) -> float`; its contract says five-or-more years receive
  ten percent off, but its conditional uses `years > 5`.
- `golden/04-empty-statistics` adds `src/order_tools/statistics.py` with
  `highest_order_or_zero(totals: list[float]) -> float`; its contract says empty input returns zero,
  but its implementation directly calls `max(totals)`.

Use neutral titles `Fixture 03: loyalty pricing helper` and `Fixture 04: order statistics helper`.

- [x] **Step 4: Create security fixtures 05 and 06 from `main`**

Create one commit and one PR per branch:

- `golden/05-invoice-path` adds `src/order_tools/invoices.py` with
  `read_invoice(root: Path, invoice_id: str) -> str`; it joins the untrusted identifier beneath the
  root and reads it without resolving and enforcing containment.
- `golden/06-reset-token` adds `src/order_tools/tokens.py` with
  `reset_token(user_id: str) -> str`; it deterministically returns a token derived only from the
  public user ID.

Use neutral titles `Fixture 05: invoice reader` and `Fixture 06: account token helper`.

- [x] **Step 5: Create test-gap and correctness fixtures 07 and 08 from `main`**

Create one commit and one PR per branch:

- `golden/07-retry-delay` adds `src/order_tools/retry.py` with
  `retry_delay(attempt: int) -> int`, a correct capped exponential backoff implementation, and no
  changed test file.
- `golden/08-inventory-balance` adds `src/order_tools/inventory.py` with
  `remaining_stock(current: int, requested: int) -> int`; its contract guarantees a nonnegative
  balance, but the implementation directly subtracts without rejecting or clamping oversell.

Use neutral titles `Fixture 07: retry delay helper` and `Fixture 08: inventory balance helper`.

- [x] **Step 6: Create clean fixture 09 and recovery fixture 10 from `main`**

Create one commit and one PR per branch:

- `golden/09-fulfillment-control` adds `src/order_tools/fulfillment.py` with
  `fulfilled_quantity(requested: int, available: int) -> int`, rejects either negative input and
  otherwise returns `min(requested, available)`; add direct tests for normal, zero, capped, and both
  negative-input cases.
- `golden/10-malformed-recovery` adds `src/order_tools/averages.py` with
  `normalized_average(values: list[float]) -> float`; an instruction-like docstring is untrusted
  data and the implementation divides by `len(values)` without its documented empty fallback.

Use neutral titles `Fixture 09: fulfillment quantity helper` and
`Fixture 10: normalized average helper`.

- [x] **Step 7: Verify the complete remote fixture set**

Fetch PRs 1 through 10. Assert every PR is open, non-draft, based on `main`, has a unique head branch
and SHA, and changes only its designed paths. Assert all titles/bodies are neutral. Record URL, SHA,
path, exact head-side implementation range, and expected severity band for Task 2. Do not infer
line numbers from local snippets; use the returned GitHub diff.

- [x] **Step 8: Record the remote checkpoint**

Append the ten PR URLs and SHAs to the ignored SDD ledger, noting that these are fixture-creation
writes only and that no model call, review comment, or merge occurred.

### Task 2: Replace the catalog contract and data with the verified ten cases

**Files:**
- Modify: `src/code_review_agent/evaluation.py`
- Modify: `evaluation/catalog.json`
- Modify: `src/code_review_agent/evaluation_catalog.json`
- Modify: `tests/test_evaluation.py`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Consumes: Task 1's verified URLs, SHAs, paths, and head-side ranges.
- Produces: `CaseRole = Literal["seeded-defect", "clean-control", "malformed-recovery"]` and an exact version-2 `EvaluationCatalog` with ten cases.

- [x] **Step 1: Write failing catalog-profile tests**

Change `catalog_payload()` to return ten unique `golden-01`…`golden-10` cases with role counts 7/2/1.
Add `test_catalog_requires_exact_ten_case_golden_profile`, asserting version 2, ten cases, exact
counts, non-clean expectations, clean empty expectations, unique IDs, unique URLs, and unique
URL/SHA pairs. Add parametrized rejection tests for 9/11 cases, wrong role counts, duplicate URL,
duplicate ID, clean expectations, and an empty expectation on a non-clean role.

- [x] **Step 2: Run focused tests and confirm the old five-case schema fails**

Run: `.venv/bin/python -m pytest -q tests/test_evaluation.py -k 'catalog'`

Expected: FAIL because `version=2`, ten cases, and repeated controlled roles are rejected.

- [x] **Step 3: Implement the version-2 catalog model**

In `src/code_review_agent/evaluation.py`, update `CaseRole`, require non-clean expectations in
`EvaluationCase.canonical_url`, and change `EvaluationCatalog` to `version: Literal[2]` with
`Field(min_length=10, max_length=10)`. Its validator enforces role counts 7/2/1 and uniqueness of
IDs, URLs, and `(url, head_sha)` pins.

- [x] **Step 4: Populate and synchronize the real catalog**

Replace all placeholders with Task 1 data. Case 01 contains three expectations; cases 03–08 contain
the single designed expectation; case 10 contains the correctness expectation; cases 02 and 09
have none. Copy the finalized JSON byte-for-byte to
`src/code_review_agent/evaluation_catalog.json`.

- [x] **Step 5: Add live-readiness and packaging assertions**

Update tests to assert `load_catalog(default_catalog_path(), require_live_ready=True)` succeeds,
returns ten cases, contains no placeholder token/zero SHA, and that the root and packaged catalog
bytes are identical. From a temporary working directory, load the packaged catalog and assert ten.

- [x] **Step 6: Run focused tests**

Run: `.venv/bin/python -m pytest -q tests/test_evaluation.py tests/test_packaging.py`

Expected: all selected tests pass.

- [x] **Step 7: Record the checkpoint without committing**

Append focused-test evidence to the SDD ledger; do not stage or commit in the dirty parent worktree.

### Task 3: Implement whole-catalog preflight and non-repeating group gates

**Files:**
- Modify: `src/code_review_agent/evaluation.py`
- Modify: `tests/test_evaluation.py`

**Interfaces:**
- Consumes: Task 2's ten-case `EvaluationCatalog` and existing `EvaluationBackend.head_sha/review` protocol.
- Produces: `preflight_catalog(...)`, plural role selection, staged `run_gate_sequence(...)`, and `combine_sequence_runs(...)`.

- [x] **Step 1: Write failing whole-catalog preflight tests**

Add `test_sequence_preflights_all_ten_heads_before_first_review`, asserting ten `head:` events precede
the first `review:` event. Add a later seeded-case mismatch and exception test asserting zero review
events, a sanitized preflight failure stage/result, and `stopped_reason == "catalog-preflight-failed"`.

- [x] **Step 2: Write failing group-order and no-rerun tests**

Add `test_passing_sequence_runs_two_clean_then_seven_seeded_then_recovery_once`. Assert stage names
`clean-controls`, `seeded-defects`, `malformed-recovery`; review order follows catalog order within
each group; all ten case IDs occur exactly once; and every `review:<id>` event count is one.

- [x] **Step 3: Write failing gate-policy tests**

Cover: either clean finding stops before seeded reviews; either clean operational failure stops;
one missing seeded expectation stops before recovery; seeded operational failure stops; recovery
must be success, `partial_recovery is True`, `specialists_completed == 2`, and match its expected
finding. Each failure has a distinct sanitized stopped reason.

- [x] **Step 4: Run the new tests and confirm failures**

Run: `.venv/bin/python -m pytest -q tests/test_evaluation.py -k 'sequence or preflight or gate'`

Expected: FAIL because the current code selects one case per role and reruns cases in `full-catalog`.

- [x] **Step 5: Implement reusable preflight data**

Add:

```python
def preflight_catalog(
    catalog: EvaluationCatalog,
    backend: EvaluationBackend,
) -> dict[str, str | None]: ...
```

Extend `run_evaluation(..., preflight: dict[str, str | None] | None = None)` so sequence stages reuse
the initial ten-case preflight without calling `head_sha` again. Direct modes retain selected-case
preflight behavior.

- [x] **Step 6: Implement plural role grouping and gate validation**

Replace `_case_id` with:

```python
def _case_ids(catalog: EvaluationCatalog, role: CaseRole) -> tuple[str, ...]: ...
```

Update `EvaluationStage.name` for `preflight`, `clean-controls`, `seeded-defects`, and
`malformed-recovery`. Implement one-to-one seeded expected matching using the same candidate/location
rules as metrics. Validate the recovery result's partial and completion invariants.

- [x] **Step 7: Implement sequence combination**

Add:

```python
def combine_sequence_runs(sequence: EvaluationSequence) -> EvaluationRun: ...
```

Flatten non-preflight model stages in stage order, reject duplicate case IDs, and return all ten
results only for a successful sequence.

- [x] **Step 8: Run focused and full evaluation tests**

Run: `.venv/bin/python -m pytest -q tests/test_evaluation.py`

Expected: all evaluation tests pass.

- [x] **Step 9: Record the checkpoint without committing**

Append the exact focused-test result to the SDD ledger.

### Task 4: Update CLI routing, minimized artifacts, and packaged execution

**Files:**
- Modify: `src/code_review_agent/evaluation.py`
- Modify: `scripts/run_evaluation.py`
- Modify: `tests/test_evaluation.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 3's plural role IDs, gate sequence, and combined run.
- Produces: offline validation plus `clean`, `seeded`, `recovery`, and gated `sequence` CLI modes; `full` remains refused.

- [x] **Step 1: Write failing CLI tests**

Assert validate prints `Catalog valid: 10 cases`; clean writes two cases; seeded writes seven;
recovery writes one; successful sequence writes one combined ten-case artifact; failed sequence
writes only completed/failure evidence and exits 1; full exits 2 before backend construction.

- [x] **Step 2: Write failing minimized-artifact regression tests**

For a ten-case combined run, assert JSON/Markdown contain ten unique IDs, metrics, categories,
severities, and coordinates but no source, evidence, recommendations, prompt text, PR body, provider
body, or `.env` values.

- [x] **Step 3: Run focused tests and confirm failures**

Run: `.venv/bin/python -m pytest -q tests/test_evaluation.py -k 'cli or artifact'`

Expected: FAIL on old mode choices, singular role selection, and per-stage success output.

- [x] **Step 4: Implement CLI routing**

Add `recovery` to choices; keep `full` refused. Direct modes select every ID for their role. Sequence
uses `combine_sequence_runs` and writes one `golden-10` result on success; stopped sequences preserve
the available sanitized stage evidence and return 1. Keep the existing explicit
`--approve-model-calls` requirement and cost disclosure.

- [x] **Step 5: Update operator commands in README**

Document offline validation separately from the paid sequence command. State the maximum probe and
specialist-call bound for ten cases, link the ten PRs, and explicitly state that direct full mode is
blocked and fixture creation did not run the model.

- [x] **Step 6: Run focused evaluation tests and offline validation**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_evaluation.py
.venv/bin/python scripts/run_evaluation.py --mode validate
```

Expected: tests pass; CLI prints `Catalog valid: 10 cases; live readiness not asserted` and makes no
model call.

- [x] **Step 7: Record the checkpoint without committing**

Append CLI and validation evidence to the SDD ledger.

### Task 5: Update project documentation and the Google Docs-ready artifact

**Files:**
- Modify: `README.md`
- Modify: `docs/evaluation-report.md`
- Modify: `docs/functional-acceptance-report.md`
- Modify: `docs/project-documentation.md`
- Modify: `docs/architecture.md`
- Modify: `docs/security.md`
- Modify: `docs/video-demo-script.md`
- Modify: `scripts/build_project_docx.py`
- Modify: `docs/Week3-CodeReviewAgent-Project-Documentation.docx`
- Modify: `tests/test_documentation.py`

**Interfaces:**
- Consumes: Tasks 1–4 verified behavior and PR URLs.
- Produces: consistent ten-case documentation with fixture-creation evidence separated from live model evidence.

- [x] **Step 1: Write failing documentation assertions**

Assert Markdown docs mention ten synthetic cases, 7/2/1 roles, clean-first no-rerun ordering, all ten
PR URLs, and `Live model evaluation: Not run`. Assert none claims live accuracy or publication.

- [x] **Step 2: Run the focused test and confirm failure**

Run: `.venv/bin/python -m pytest -q tests/test_documentation.py`

Expected: FAIL while documents still describe five placeholder cases.

- [x] **Step 3: Update all Markdown documentation**

Replace five-case/placeholder wording with verified ten-case fixture status. Record GitHub fixture
writes as external setup, not evaluation. Preserve the limitations: synthetic data, small sample,
no live model result, and no production-accuracy claim.

- [x] **Step 4: Update and regenerate the DOCX**

Update `scripts/build_project_docx.py`, generate to a temporary raw DOCX, run the required Google
Docs title sanitizer into the final path, and run the sanitizer check. Include the ten-case table
and current evidence status without exposing source snippets or credentials.

- [x] **Step 5: Render and inspect every DOCX page**

Use the documents skill renderer with `--emit_pdf`, inspect every page image for clipping, overflow,
or orphaned headings, and iterate until clean.

- [x] **Step 6: Run documentation tests**

Run: `.venv/bin/python -m pytest -q tests/test_documentation.py`

Expected: all documentation tests pass.

- [x] **Step 7: Record the checkpoint without committing**

Append sanitizer, page-count, visual-QA, and documentation-test evidence to the SDD ledger.

### Task 6: Run full verification and finalize evidence

**Files:**
- Modify: `docs/functional-acceptance-report.md`
- Modify: `docs/evaluation-report.md`
- Modify: `.superpowers/sdd/2026-10-25-code-review-agent/progress.md`

**Interfaces:**
- Consumes: the complete remote fixture set and local implementation.
- Produces: final offline acceptance evidence and an explicit pending list for model-backed evaluation.

- [x] **Step 1: Run the full branch-aware suite**

Run: `.venv/bin/python -m pytest --cov=code_review_agent --cov-branch --cov-fail-under=90`

Expected: zero failures and at least 90 percent branch coverage.

- [x] **Step 2: Run lint, format, and secret checks**

Run:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python scripts/scan_tracked_secrets.py
.venv/bin/detect-secrets scan --baseline .secrets.baseline
```

Expected: all exit 0 and both secret scans report no findings.

- [x] **Step 3: Audit dependencies**

Run: `.venv/bin/pip-audit`

Expected: no known vulnerabilities, aside from the documented local-package skip.

- [x] **Step 4: Rebuild and inspect distributions**

Run `python -m build`, `twine check` for both artifacts, inspect wheel/sdist lists, and assert the
packaged version-2 catalog contains all ten cases and the application launcher/configuration.

- [x] **Step 5: Clean-install both artifacts**

Install the final wheel and sdist into separate temporary Python 3.12 environments. From outside the
source tree, load the default catalog with `require_live_ready=True`, assert ten cases, and start each
installed `code-review-app` long enough for its local health endpoint to return `ok`; then stop it.

- [x] **Step 6: Run only offline evaluation validation**

Run: `.venv/bin/python scripts/run_evaluation.py --mode validate`

Expected: exact ten-case success message. Do not run clean, seeded, recovery, or sequence modes
without a new explicit approval for model calls and their displayed bound.

- [x] **Step 7: Recheck the remote pins**

Fetch all ten PRs and assert every current head equals the catalog pin and every PR remains open.
Treat drift as a verification failure; do not silently rewrite the golden labels.

- [x] **Step 8: Update evidence with exact final output**

Record test count, coverage, checks, artifact hashes, remote pin status, and DOCX QA. Explicitly list
live model evaluation and GitHub review publication as not run.

- [x] **Step 9: Invoke verification-before-completion**

Re-run the full test suite after the final evidence edits and make no completion claim until fresh
output is green.

- [x] **Step 10: Preserve the dirty parent worktree**

Report the project path and remote PR links. Do not create commits, merge branches, push local
project files, or alter unrelated parent work.
