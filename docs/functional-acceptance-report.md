# Functional Acceptance Report

## Status summary

The application includes a live-ready catalog of ten synthetic fixtures: seven seeded defects, two
clean controls, and one controlled malformed-recovery case. Final offline application, safety,
packaging, clean-install, startup, documentation, and remote-pin checks passed on 25 October 2026 in
the America/New_York timezone.

The authorized live sequence stopped with `clean-controls-produced-findings` after one clean-control
false positive. The remaining groups were executed once in diagnostic modes, covering ten unique
case IDs without converting the stopped sequence into a pass. The diagnostic aggregate is 10
percent recall, 14.29 percent precision, 93.33 percent specialist completion, 0 percent duplicates,
failed clean behavior, and failed recovery. Severity and location agreement are 100 percent for one
matched finding only. GitHub review publication: Not run.

## Requirement status

| Capability | Status | Evidence |
|---|---|---|
| Canonical pull-request URL parsing | Implemented offline | Parser regression tests |
| Bounded GitHub reads and pagination | Implemented offline | MockTransport retry, pagination, and content tests |
| Exact head SHA capture | Implemented offline | Snapshot drift and per-mutation publication tests |
| Redaction and prompt-injection fencing | Implemented offline | Context tests |
| Nonexecuting static inspection | Implemented offline | AST tests and unavailable-tool disclosure tests |
| Three concurrent LangGraph specialists | Implemented offline | Concurrency and graph topology tests |
| Provider capability probe | Implemented offline | Exact-schema probe tests |
| Structured-output retry and failure policy | Implemented offline | Malformed, partial, and abort tests |
| Grounding and deduplication | Implemented offline | Validation and deterministic Markdown tests |
| Exact-body approval reset | Implemented offline | Approval and Streamlit rerun tests |
| Default-off idempotent publication | Implemented offline | Publisher and timeout recovery tests |
| Source-free evaluation harness | Implemented offline | Catalog, gate, metrics, and artifact tests |
| Ten-case golden dataset | Implemented and live-ready | Ten open pinned pull requests; exact 7/2/1 role profile |
| Whole-catalog preflight and grouped gates | Implemented offline | Ten heads before reviews; clean, seeded, then recovery; no reruns |
| Live ten-case model evaluation | Baseline recorded; official gate failed | Sequence stopped at clean controls; remaining cases ran diagnostically once |
| Controlled GitHub write | Not run | Requires explicit target and action-time approval |

## Final command evidence

The commands below ran from the project directory with Python 3.12.14. Clean artifact environments
used CPython 3.12.15. The dependency audit queried current PyPI data and found no known
vulnerabilities; the local project package was skipped because it is not published on PyPI.

| Check | Result | Notes |
|---|---|---|
| Pytest with branch coverage | Pass | 175 passed; 92.60 percent branch coverage; 90 percent gate met; Streamlit entrypoint is black-box tested and omitted from in-process coverage |
| Ruff lint | Pass | `All checks passed!` |
| Ruff formatting | Pass | 56 files already formatted |
| Project secret scanner | Pass | 0 findings |
| Detect-secrets | Pass | 27 active detector plugins; empty result set |
| Pip-audit | Pass after remediation | No known vulnerabilities; local project package is not on PyPI |
| Wheel and source distribution | Pass | Built version 0.1.0 wheel and source archive without warnings |
| Twine archive check | Pass | Both artifacts passed |
| Package file-list inspection | Pass | Wheel and sdist contain the launcher, Streamlit page/configuration, evaluator, and version-2 ten-case catalog; the sdist omits checkout-only tests |
| Clean artifact installation | Pass | Wheel and sdist installed independently under `/private/tmp`; each loaded its packaged ten-case catalog with live readiness required |
| Streamlit startup smoke test | Pass | Source checkout, clean wheel install, and clean sdist install returned `ok` from local health endpoints and stopped cleanly |
| Evaluation catalog offline validation | Pass | Ten version-2 cases valid; packaged and root catalogs byte-match; no model calls |
| Golden fixture setup | Pass | Ten open, non-draft PRs with pinned unique heads; no review comment or merge |
| Clean-control live gate | Fail | `golden-02` produced one false positive; `golden-09` remained clean; stop reason `clean-controls-produced-findings` |
| Seeded-defect diagnostic | Completed | Seven cases ran once; only `golden-07` satisfied its expected match |
| Malformed-recovery diagnostic | Fail | `golden-10` completed 1/3 specialists, returned no finding, and did not recover partially |
| Complete live catalog | Diagnostic coverage only | Three artifacts contain ten unique case IDs; no successful combined sequence was created |
| Controlled publication | Not run | No approved target or GitHub write approval |

## Distribution evidence

| Artifact | SHA-256 |
|---|---|
| `week3_code_review_agent-0.1.0-py3-none-any.whl` | `ea03ea3549ddb50160eea1c0e83b40aa752fc20f611fd08d6ceaa7315c649789` |
| `week3_code_review_agent-0.1.0.tar.gz` | `da57176176eb724341ad9bdb7bb1cf36d8434c2c5e9787bdfbb8e450ce7fd336` |

## Remote pin evidence

GitHub metadata was fetched after local and package verification. Pull requests 1 through 10 are
open, unmerged, non-draft, and based on `main`. Every current head SHA equals its catalog pin:

- `golden-01` — PR 1 — `9aaac85382cbc3c2cfd01fa80e584916adb3b892`
- `golden-02` — PR 2 — `99c1bd161c345f8bc63c6ab5ca1f19c7df34b41a`
- `golden-03` — PR 3 — `fa744571344980e536911bc51c0be26591a667f6`
- `golden-04` — PR 6 — `20edb9b3c56499f0cc050ea02c175902019a61e5`
- `golden-05` — PR 4 — `365edc372e5aa98ef437cc8b284470846727b05c`
- `golden-06` — PR 5 — `f68b49804adc15dcb72932671259527cce51f1dd`
- `golden-07` — PR 7 — `0e685df6235e43e65fe33b5f56a353453b1462be`
- `golden-08` — PR 9 — `1c69bc8456b9f2ba9c1554404746ea7ac3b67af8`
- `golden-09` — PR 8 — `b8d3c3b3cf98164eb968cc8a7182662c0f0d9e43`
- `golden-10` — PR 10 — `f41beb3085a8fcbe4d5b9e3291814567faa20d3c`

## Acceptance limits

Passing offline tests does not establish model accuracy. A successful package build does not prove
GitHub credentials, provider compatibility, or remote availability. A live model run does not
authorize publication. These evidence classes remain separate throughout the report.

## Week 4 handoff

The live result is the frozen evaluation baseline for Week 4. Follow-on work should audit label
completeness, record sanitized generation and rejection diagnostics, expand and balance the golden
dataset, create separate development and holdout splits, compare prompt and model variants, and
measure repeatability with predetermined runs. No Week 4 improvement is claimed in this report.
