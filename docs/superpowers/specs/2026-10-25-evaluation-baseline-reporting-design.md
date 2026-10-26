# Evaluation Baseline Reporting Design

## Intent

Update the Week 3 project evidence so it accurately records the live golden-dataset evaluation and
uses that result as the baseline for the evaluation-focused Week 4 work. The report must distinguish
the quality of the implemented safety and control system from the accuracy of the configured review
model.

## Approaches considered

1. Update only the project report. This is narrow, but it leaves contradictory `Not run` statements
   in the README and acceptance evidence.
2. Update the complete status-bearing evidence set. This keeps the README, project report,
   evaluation report, acceptance report, demo script, and DOCX consistent. This is the selected
   approach.
3. Preserve the Week 3 report and create a separate Week 4 report. This keeps history intact, but it
   leaves the submitted Week 3 report factually stale after the authorized live run.

## Recorded evidence

The official gated sequence preflighted all ten pinned pull requests and ran both clean controls. It
stopped because `golden-02` produced one high-severity correctness finding, while `golden-09`
produced none. The stopped sequence is a failed clean-control result and is not a successful
ten-case sequence.

The seven seeded cases and one recovery case were subsequently run once in explicit diagnostic
modes. Together with the clean-control artifact, those source-free artifacts cover ten unique case
IDs. Their read-only diagnostic aggregate is:

- recall: 10 percent;
- precision: 14.29 percent;
- specialist completion: 93.33 percent;
- duplicate rate: 0 percent;
- clean-control behavior: failed;
- malformed-response recovery: failed;
- severity and location agreement: 100 percent, based on one matched finding only.

Only `golden-07` satisfied its expected finding match. The recovery case returned no accepted
finding, completed one of three specialists, and did not produce the required partial recovery.
GitHub review publication was not run.

## Reporting model

Every updated document will separate three evidence classes:

1. Offline implementation and safety verification, which remains green.
2. Official live evaluation, which stopped at the clean-control gate and failed.
3. Diagnostic execution, which exercised the remaining cases without overriding the official gate.

The Week 4 handoff will describe label auditing, source-free diagnostic telemetry, dataset
expansion, development and holdout splits, prompt and model comparisons, and repeatability
measurement. It will not claim that Week 4 changes have already been implemented.

## Deliverables

- `README.md`
- `docs/project-documentation.md`
- `docs/evaluation-report.md`
- `docs/functional-acceptance-report.md`
- `docs/video-demo-script.md`
- `scripts/build_project_docx.py`
- `docs/Week3-CodeReviewAgent-Project-Documentation.docx`
- `tests/test_documentation.py`
- refreshed wheel and source distribution because the README is package metadata

## Constraints

- Do not call the model again, rerun a golden case, or publish a GitHub comment.
- Do not describe the diagnostic aggregate as an official passing sequence.
- Do not present 100 percent severity or location agreement without the one-match denominator.
- Do not make a production-accuracy claim from ten synthetic cases.
- Preserve the existing report design and make local content changes rather than redesigning it.
- Rebuild package artifacts, update their hashes, sanitize the DOCX, render it, and inspect every
  page before delivery.
- Preserve unrelated work and do not commit or stage changes.

## Acceptance

All status-bearing documents contain the same baseline facts and no stale claim that live model
evaluation was not run. The demo script presents the failed gate as an evaluation result rather
than a demonstration failure. Documentation tests, the full offline suite, lint, formatting,
secret scans, package checks, DOCX sanitization, and final visual inspection pass. Publication
remains recorded as not run.
