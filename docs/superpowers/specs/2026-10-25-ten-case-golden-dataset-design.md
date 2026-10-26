# Ten-Case Synthetic Golden Dataset Design

## Intent

Replace the current placeholder five-case evaluation catalog with a reproducible golden dataset of
ten open synthetic pull requests in `melepatt/code-review-agent-demo`. The dataset exists to measure
the Code Review Agent's finding recall, precision, severity agreement, location agreement,
specialist completion, malformed-response recovery, duplicate rate, and clean-control behavior.

The user selected replacement of the original five-case contract, not a second parallel catalog.
Existing pull requests 1 and 2 count as the first two cases; eight new independent pull requests
complete the dataset.

## Goals

- Maintain exactly ten independently pinned cases, each represented by one open pull request based
  directly on `main`.
- Cover correctness, security, and test-gap behavior with two clean controls and one controlled
  malformed-specialist recovery case.
- Keep expected answers out of the pull-request title, description, and changed source so the model
  cannot obtain the label from metadata.
- Store only canonical public URLs, exact head SHAs, category aliases, changed paths and head-side
  ranges, and acceptable severity ranges in the catalog.
- Run each case at most once in an approved live sequence: clean controls first, seeded defects
  second, malformed recovery last.
- Preserve the evaluator's read-only boundary and minimized, source-free result artifacts.

## Non-goals

- This work will not call the model, score live accuracy, post review comments, merge fixture pull
  requests, or enable the Code Review Agent publisher.
- Ten synthetic cases will not support a production-accuracy claim.
- The fixtures will not exercise repository code, CI workflows, package installation, or secrets.
- The dataset will not attempt to represent every Python bug or security weakness.

## Anti-goals

- Do not place phrases such as “command injection,” “clean control,” or “expected finding” in PR
  titles or descriptions.
- Do not build cases on top of another fixture branch; cross-case contamination would invalidate
  expected locations.
- Do not change expected labels after observing model output merely to improve a score.
- Do not create or update GitHub review comments as part of fixture creation.

## Constraints and safety boundaries

- GitHub changes are limited to the public `melepatt/code-review-agent-demo` repository authorized
  by the user.
- Pull requests remain open and explicitly say they are synthetic, non-mergeable benchmark
  fixtures, without disclosing their expected label.
- Branches use the stable prefix `golden/` and are based on the current `main` SHA.
- Before creating anything, inspect existing branches and PRs so a retry cannot create duplicates.
- After every PR is created, fetch its final metadata and diff; derive the catalog SHA and line range
  from GitHub rather than guessing.
- Existing PRs 1 and 2 will receive neutral titles and descriptions because their current metadata
  discloses the expected result. Their code, head branches, and URLs remain unchanged.
- The Code Review Agent's `.env` and credentials are never read, printed, or copied.

## Approaches considered

### 1. Preserve the five-case catalog and add a separate golden catalog

This minimizes regression risk and keeps the original assignment contract intact, but creates two
catalog profiles and two operational stories. The user declined this approach.

### 2. Replace the five-case catalog with the ten-case golden dataset — selected

This yields one authoritative dataset and one documented evaluation workflow. It requires deliberate
changes to catalog validation, gate sequencing, tests, packaged data, and documentation. The user
selected this approach.

### 3. Create PRs and a data-only manifest without evaluator integration

This is the smallest external change, but it leaves the dataset unvalidated and unscored. It does
not meet the goal of evaluating the existing agent end to end.

## Dataset composition

Every future fixture changes a unique source path so line-level expected results are unambiguous.
Exact coordinates and SHAs are filled only after GitHub returns the final diff.

| Case | Role | Fixture | Expected outcome |
|---|---|---|---|
| 01 | seeded-defect | Existing PR 1: average calculation and report runner | Correctness: empty input; security: shell command injection; test-gap: new behavior lacks direct tests |
| 02 | clean-control | Existing PR 2: tested order count helper | No publishable findings |
| 03 | seeded-defect | `discounts.py`: five-year loyalty boundary is excluded | One medium correctness finding |
| 04 | seeded-defect | `statistics.py`: documented empty-input fallback calls `max()` | One medium correctness finding |
| 05 | seeded-defect | `invoices.py`: invoice identifier is joined to a trusted root without containment validation | One high security finding |
| 06 | seeded-defect | `tokens.py`: password-reset token is deterministically derived from the user ID | One high security finding |
| 07 | seeded-defect | `retry.py`: correct retry-delay behavior is added without direct tests | One medium test-gap finding |
| 08 | seeded-defect | `inventory.py`: stock reservation can return a negative balance despite its contract | One high correctness finding |
| 09 | clean-control | `fulfillment.py` plus boundary tests: validated quantity clamping | No publishable findings |
| 10 | malformed-recovery | `averages.py`: untrusted instruction-like docstring plus empty-input division defect | One medium correctness finding; injected test-coverage specialist failure must yield a partial review |

The role cardinality is therefore seven `seeded-defect`, two `clean-control`, and one
`malformed-recovery` case. Case IDs are stable (`golden-01` through `golden-10`).

## Fixture construction

For each of cases 03 through 10:

1. Resolve the current `main` commit.
2. Create a stable branch such as `golden/03-loyalty-boundary` from that commit.
3. Add only the minimal source and, where required, test files for that fixture.
4. Create one commit with a neutral subject.
5. Open one PR with a neutral title and a standard body explaining only that it is an isolated
   synthetic benchmark fixture that must not be merged.
6. Fetch the PR and verify it is open, based on `main`, and contains only intended paths.
7. Record its exact head SHA and head-side changed range in the catalog draft.

If a stable branch or open PR already exists during a retry, inspect and reuse it only when its
content matches the design; otherwise stop instead of overwriting remote work.

## Catalog model

`evaluation/catalog.json` and packaged `src/code_review_agent/evaluation_catalog.json` become the
same version-2 ten-case document. Validation enforces:

- exactly ten unique IDs and canonical GitHub pull-request URLs;
- exactly seven seeded defects, two clean controls, and one malformed recovery case;
- no zero SHA or replacement placeholder;
- empty expectations only for clean controls;
- at least one expectation for every other role;
- unique URL and head-SHA pairs;
- closed expected category, coordinate, and severity fields.

The existing source-free result schema remains unchanged. The packaged catalog must byte-match the
root catalog so installed wheels behave like the source checkout.

## Evaluation sequence

The CLI retains offline `validate` mode and introduces role-group execution suitable for the new
cardinality. The only complete live workflow is `sequence`:

1. Preflight all ten pinned SHAs before any model call.
2. Run both clean controls once. Stop on an operational failure or any publishable finding.
3. Run all seven seeded-defect cases once. Stop if a case fails operationally or any expected
   finding has no one-to-one match.
4. Run the malformed-recovery case once. Require a successful partial review with the expected
   correctness match and exactly one failed specialist.
5. Combine the three non-overlapping stages into one ten-case minimized report and compute metrics.

No stage reruns a case. A direct full-catalog mode remains refused so users cannot bypass the clean
and seeded gates. Model calls still require the existing explicit `--approve-model-calls` flag.

## Error handling

- Remote creation failure stops before starting the next fixture and reports the stable branch/PR
  already created so work can resume idempotently.
- Catalog generation fails if GitHub metadata, changed paths, or head coordinates differ from the
  design.
- Snapshot drift, expected-SHA mismatch, provider errors, and malformed output continue to use the
  evaluator's sanitized per-case status behavior.
- Clean-control false positives stop the live sequence without relabeling the controls.
- Failed seeded expectations remain failed evidence; the sequence is not rerun to improve scores.

## Testing

Implementation follows test-first cycles. Regression coverage will prove:

- version-2 catalog cardinality, uniqueness, role counts, and live readiness;
- both clean controls run before any defect case;
- a false positive or clean operational failure stops later model calls;
- all seven seeded cases run once and use one-to-one expected matching;
- malformed recovery runs last and requires the partial outcome;
- a successful sequence contains ten distinct results and never reruns a case;
- minimized JSON and Markdown contain no source excerpts or provider bodies;
- root and packaged catalogs are identical and load outside the source checkout;
- existing publisher isolation, approval controls, and the full offline suite remain green.

## Documentation and evidence

Update the README, evaluation report, functional acceptance report, project documentation, and
Google Docs-ready DOCX to describe the ten synthetic cases and distinguish fixture creation from
live model evaluation. Documentation will link all ten public PRs and state that fixture creation is
verified while model accuracy remains not run until separately approved.

Final offline verification includes branch-aware tests, Ruff, both secret scans, dependency audit,
package builds and archive checks, clean-install packaged-catalog checks, Streamlit smoke, catalog
validation, DOCX sanitization, and visual inspection. Live model evaluation and GitHub comment
publication remain outside this work.

## Builder-owned details

- Exact neutral function and variable names, provided they preserve each fixture's stated behavior.
- Exact stable branch suffixes and commit subjects under the documented naming rules.
- Whether catalog synchronization uses a small checked-in script or an explicit test-enforced copy,
  provided the two shipped JSON files remain byte-identical.
- Presentation wording that does not leak expected labels.
