# Evaluation Baseline Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every status-bearing project report accurately describe the failed official live gate, the ten-case diagnostic baseline, and the Week 4 evaluation handoff.

**Architecture:** Treat the three source-free evaluation artifacts as immutable evidence. Update the Markdown evidence set first, regenerate the existing DOCX through its checked-in builder, then rebuild package metadata and refresh distribution hashes. No application behavior or external state changes.

**Tech Stack:** Markdown, Python 3.12, pytest, python-docx, packaged document renderer, build, Twine, Ruff.

**Spec:** `docs/superpowers/specs/2026-10-25-evaluation-baseline-reporting-design.md`

## Global Constraints

- Do not call the model, rerun a golden case, or publish a GitHub comment.
- Official status is `clean-controls-produced-findings`; diagnostics do not override that gate.
- Diagnostic aggregate is recall 10 percent, precision 14.29 percent, specialist completion 93.33 percent, duplicate rate 0 percent, clean behavior false, and partial recovery false.
- Severity and location agreement are 100 percent for one matched finding only.
- Controlled GitHub publication remains not run.
- Ten synthetic cases do not support a production-accuracy claim.
- Preserve the existing DOCX style and modify content locally.
- Preserve unrelated work; do not commit or stage changes.

## Review Focus

- Stale `Live model evaluation: Not run` text must be rejected by documentation tests.
- Diagnostic coverage must never be described as an official complete or passing sequence.
- Agreement metrics must state their one-match denominator.
- Distribution hashes must match artifacts rebuilt after the README update.
- The regenerated DOCX must remain readable with no table overflow, orphaned heading, or clipped text.

---

### Task 1: Pin the new reporting contract

**Files:**
- Modify: `tests/test_documentation.py`

**Interfaces:**
- Consumes: exact baseline facts and evidence distinctions from the approved design.
- Produces: documentation assertions used by Tasks 2 and 4.

- [x] **Step 1: Replace pending-evaluation assertions with baseline assertions**

Require the Markdown evidence set and DOCX to contain the official stopped-gate status, diagnostic
coverage of ten unique cases, 10 percent recall, 14.29 percent precision, failed clean behavior,
failed recovery, the one-match agreement qualification, Week 4 handoff, and publication not run.
Reject stale `live model evaluation: not run` text and any claim that the ten-case sequence passed.

- [x] **Step 2: Run the focused test and confirm RED**

Run: `.venv/bin/python -m pytest -q tests/test_documentation.py`

Expected: failures identify the old pending-evaluation language.

### Task 2: Update the Markdown evidence set and demo script

**Files:**
- Modify: `README.md`
- Modify: `docs/project-documentation.md`
- Modify: `docs/evaluation-report.md`
- Modify: `docs/functional-acceptance-report.md`
- Modify: `docs/video-demo-script.md`

**Interfaces:**
- Consumes: clean, seeded, and recovery artifacts already written under `evaluation/runs/`.
- Produces: one consistent written baseline and Week 4 handoff for the DOCX builder.

- [x] **Step 1: Update the README evidence summary**

State the failed clean-control gate, diagnostic ten-case coverage, aggregate metrics, and unchanged
publication status. Link the three source-free artifacts.

- [x] **Step 2: Update the evaluation and acceptance reports**

Record official and diagnostic results separately, include the case-level outcome summary, qualify
the agreement denominator, and mark the three live stages with their actual outcomes. Preserve all
offline verification evidence.

- [x] **Step 3: Update the project narrative and Week 4 handoff**

Replace pending live-evaluation language with the baseline result and add a Week 4 evaluation plan
covering label quality, observability, larger split datasets, model/prompt experiments, and repeated
runs.

- [x] **Step 4: Update the demo script**

Use saved artifacts rather than another model run. Explain that the official gate failed, show the
diagnostic baseline, distinguish accuracy from safety verification, and keep publication disabled.

- [x] **Step 5: Run the focused test**

Run: `.venv/bin/python -m pytest -q tests/test_documentation.py`

Expected: Markdown assertions pass; DOCX assertions remain RED until Task 4.

### Task 3: Rebuild package metadata and refresh hashes

**Files:**
- Modify: `docs/functional-acceptance-report.md`
- Rebuild: `dist/week3_code_review_agent-0.1.0-py3-none-any.whl`
- Rebuild: `dist/week3_code_review_agent-0.1.0.tar.gz`

**Interfaces:**
- Consumes: the updated README from Task 2.
- Produces: final artifact hashes recorded by the acceptance report.

- [x] **Step 1: Rebuild both distributions from a clean `dist` directory**

Run: `.venv/bin/python -m build`

Expected: one wheel and one source archive build successfully.

- [x] **Step 2: Check package metadata**

Run: `.venv/bin/twine check dist/week3_code_review_agent-0.1.0-py3-none-any.whl dist/week3_code_review_agent-0.1.0.tar.gz`

Expected: both artifacts pass.

- [x] **Step 3: Record exact SHA-256 hashes**

Run: `shasum -a 256 dist/week3_code_review_agent-0.1.0-py3-none-any.whl dist/week3_code_review_agent-0.1.0.tar.gz`

Update only the two hash cells in the acceptance report.

### Task 4: Regenerate and visually verify the project DOCX

**Files:**
- Modify: `scripts/build_project_docx.py`
- Modify: `docs/Week3-CodeReviewAgent-Project-Documentation.docx`

**Interfaces:**
- Consumes: the final narrative and exact baseline values from Task 2.
- Produces: a sanitized, visually verified Word report matching the Markdown evidence.

- [x] **Step 1: Mark the DOCX edit operation exactly once**

Run the document skill's `mark_artifact_operation_started.mjs` with operation `edit`, expected output
count 1, and output format `docx` using the authoritative runtime.

- [x] **Step 2: Update the builder content**

Revise the document purpose, dataset status, testing and evaluation, evidence table, results and
limitations, and demonstration plan. Add an evaluation-baseline table and Week 4 handoff while
preserving the existing visual system.

- [x] **Step 3: Generate and sanitize the DOCX**

Run the checked-in builder to a temporary path, apply the Google Docs title sanitizer into the final
path, and run the sanitizer check.

- [x] **Step 4: Render the latest DOCX**

Use the packaged `render_docx.py` with `--emit_pdf` and a fresh temporary output directory.

- [x] **Step 5: Inspect every rendered page at original detail**

Confirm no clipping, overflow, broken tables, orphaned headings, missing glyphs, or footer problems.
Iterate and rerender if any issue is found.

- [x] **Step 6: Run the focused documentation test**

Run: `.venv/bin/python -m pytest -q tests/test_documentation.py`

Expected: all documentation tests pass.

### Task 5: Run final verification

**Files:**
- Verify only; do not modify application behavior.

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: fresh completion evidence.

- [x] **Step 1: Run the full offline suite with branch coverage**

Run: `.venv/bin/python -m pytest --cov=code_review_agent --cov-branch --cov-fail-under=90`

Expected: all tests pass and branch coverage remains at least 90 percent.

- [x] **Step 2: Run lint and formatting checks**

Run: `.venv/bin/ruff check .`

Run: `.venv/bin/ruff format --check .`

Expected: both pass.

- [x] **Step 3: Run both secret scans**

Run: `.venv/bin/python scripts/scan_tracked_secrets.py`

Run: `.venv/bin/detect-secrets scan --baseline .secrets.baseline`

Expected: zero findings and an empty detect-secrets result.

- [x] **Step 4: Recheck reporting and artifact invariants**

Assert ten unique case IDs across the three evaluation artifacts, no source/evidence/prompt/provider
payload keys, no stale pending-evaluation claim in status-bearing deliverables, matching distribution
hashes, and a clean DOCX sanitizer check.

- [x] **Step 5: Preserve the dirty parent worktree**

Report modified deliverables and verification evidence. Do not commit, stage, publish, or rerun the
model.
