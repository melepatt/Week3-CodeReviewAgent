# Evaluation Report

## Report status

The offline evaluation harness and ten synthetic GitHub fixtures are implemented and tested. The
version 2 catalog contains seven seeded defects, two clean controls, and one controlled
malformed-recovery case. All URLs and 40-character head SHAs are pinned and live-ready.

Live model evaluation ran with the configured Qwen model. The official gated sequence preflighted
all ten heads and stopped with `clean-controls-produced-findings` after `golden-02` produced one
high-severity correctness false positive. `golden-09` produced no finding. The remaining seeded and
recovery cases were run once in explicit diagnostic modes; those runs do not override the failed
official gate. GitHub review publication: Not run.

## Golden dataset

| Case | Role | Pull request | Expected result |
|---|---|---|---|
| golden-01 | Seeded defect | [PR 1](https://github.com/melepatt/code-review-agent-demo/pull/1) | Correctness, security, and test-gap findings |
| golden-02 | Clean control | [PR 2](https://github.com/melepatt/code-review-agent-demo/pull/2) | No publishable finding |
| golden-03 | Seeded defect | [PR 3](https://github.com/melepatt/code-review-agent-demo/pull/3) | Correctness finding |
| golden-04 | Seeded defect | [PR 6](https://github.com/melepatt/code-review-agent-demo/pull/6) | Correctness finding |
| golden-05 | Seeded defect | [PR 4](https://github.com/melepatt/code-review-agent-demo/pull/4) | Security finding |
| golden-06 | Seeded defect | [PR 5](https://github.com/melepatt/code-review-agent-demo/pull/5) | Security finding |
| golden-07 | Seeded defect | [PR 7](https://github.com/melepatt/code-review-agent-demo/pull/7) | Test-gap finding |
| golden-08 | Seeded defect | [PR 9](https://github.com/melepatt/code-review-agent-demo/pull/9) | Correctness finding |
| golden-09 | Clean control | [PR 8](https://github.com/melepatt/code-review-agent-demo/pull/8) | No publishable finding |
| golden-10 | Malformed recovery | [PR 10](https://github.com/melepatt/code-review-agent-demo/pull/10) | Correctness finding with one controlled specialist failure |

The labels above live only in this evaluator documentation and catalog. Pull-request titles and
bodies remain neutral so they do not disclose the expected answer to the model.

## Evidence classes

### Offline regression evidence

The automated suite exercises catalog cardinality and uniqueness, whole-catalog head preflight,
clean-first gates, one-to-one expected matching, malformed-response recovery, no-rerun sequencing,
minimized artifacts, URL rejection, bounded GitHub reads, prompt-injection fencing, deterministic
validation, approval reset, and default-off publication.

Final verification produced 175 passing tests and 92.60 percent branch coverage. Ruff lint and
formatting, two secret scans, dependency audit, wheel and source-distribution builds, Twine checks,
archive inspection, clean installs, and source/wheel/sdist Streamlit health checks passed. Both
installed artifacts loaded the packaged ten-case catalog as live-ready. The functional acceptance
report records the exact hashes and command evidence.

### Live model evaluation

Status: **Failed at the clean-control gate**. The official sequence stopped with
`clean-controls-produced-findings`. The diagnostic seeded and recovery runs subsequently exercised
the remaining eight cases once, producing coverage of ten unique case IDs across three artifacts.
This is diagnostic coverage, not a successful complete sequence.

## Live baseline results

| Measure | Result | Interpretation |
|---|---:|---|
| Recall | 10 percent | One of ten expected findings matched |
| Precision | 14.29 percent | One of seven accepted findings matched |
| Specialist completion | 93.33 percent | 28 of 30 specialist slots completed |
| Duplicate rate | 0 percent | No duplicate accepted coordinates |
| Clean-control behavior | Failed | `golden-02` produced one false positive |
| Partial recovery | Failed | `golden-10` completed 1/3 specialists and returned no finding |
| Severity agreement | 100 percent | Based on one matched finding only |
| Location agreement | 100 percent | Based on one matched finding only |

Only `golden-07` satisfied its expected finding match. The saved source-free artifacts are
`evaluation-20261026T002439043692Z-clean-controls`,
`evaluation-20261026T004421625474Z-seeded`, and
`evaluation-20261026T004440793716Z-recovery`, each with JSON and Markdown forms under
`evaluation/runs/`.

### Controlled GitHub publication acceptance

Status: **Not run**. Offline tests cover disabled publication, changed SHA, same-author update,
foreign marker handling, duplicate marker refusal, creation, and timeout recovery. The fixture
setup used repository APIs to create benchmark branches and pull requests; it did not exercise the
agent's review-comment publisher.

## Evaluation sequence

1. Preflight all ten pinned head SHAs before any model call.
2. Run both clean controls. Stop on an operational failure or any publishable finding.
3. Run all seven seeded defects. Stop if a case fails or an expected finding lacks a one-to-one
   category, path, and location match.
4. Run the malformed-recovery case. Require a successful partial review, exactly two completed
   specialists, and the expected correctness match.
5. Combine the three groups into one ten-case minimized result.

The clean controls, seeded defects, and malformed-recovery case each run at most once. Standalone
`full` mode is refused. A complete run is available only through the ordered `sequence` mode.
Stopped runs keep the sanitized stages they reached and are not combined.

The recorded official run stopped after step 2. Direct seeded and recovery modes were then used for
diagnosis, not to construct a passing combined result or rerun a case for a better score.

## Metrics and artifacts

The report includes recall, precision, severity agreement, location agreement, duplicate rate,
specialist completion, malformed-response partial recovery, and clean-control behavior. Expected
findings are matched one-to-one. A metric without a valid denominator is `N/A`.

Timestamped JSON and Markdown contain status, IDs, categories, severities, coordinates, completion,
partial recovery, and metrics. They omit source excerpts, evidence prose, prompts, pull-request
bodies, provider responses, and credentials.

## Limitations

Ten synthetic cases can reveal regressions and obvious precision failures, but they cannot estimate
production accuracy. Expected labels encode evaluator judgment. Results also depend on the pinned
diffs, model endpoint, configuration, and run conditions recorded with the artifacts.

## Week 4 evaluation handoff

Week 4 should freeze this run as the baseline, audit labels for acceptable secondary findings, add
source-free counts for generated and rejected findings, expand the dataset, and separate prompt
development cases from a held-out test set. Prompt and model comparisons should use predetermined
runs and report variation rather than selecting the best retry. These steps improve the evaluation
system before attempting to optimize the agent against a small benchmark.
