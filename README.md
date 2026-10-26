# Code Review Agent

A Streamlit application that reviews one exact GitHub pull-request snapshot with correctness,
security, and test-coverage specialists. LangGraph runs the specialists concurrently. Deterministic
code then validates, grounds, filters, deduplicates, and renders their findings. A separate publisher
can create or update one marker-tagged GitHub comment only after a human approves the exact body and
the pull request still has the reviewed head SHA.

## Current evidence status

- Offline regression tests and safety controls are implemented.
- Final offline verification passed 175 tests with 92.60 percent branch coverage. Lint, formatting,
  secret scans, dependency audit, package checks, clean installs, and Streamlit health checks pass.
- GitHub publication is disabled by default.
- Fixture setup created or updated ten synthetic pull requests. It did not call the model, publish a
  review comment, or merge a fixture.
- The version-2 golden catalog contains ten live-ready pinned fixtures: seven seeded defects, two
  clean controls, and one controlled malformed-output recovery case.
- The official live sequence stopped with `clean-controls-produced-findings`: `golden-02` produced
  one false positive and `golden-09` remained clean. The remaining cases were then executed once in
  diagnostic modes without overriding the failed gate.
- Across the three source-free artifacts, the diagnostic baseline is 10 percent recall, 14.29
  percent precision, 93.33 percent specialist completion, 0 percent duplicates, failed clean
  behavior, and failed malformed-response recovery. Severity and location agreement are 100
  percent for one matched finding only.
- GitHub review publication: Not run.
- Final command evidence is recorded in `docs/functional-acceptance-report.md`.

## Workflow

```text
canonical PR URL
      |
      v
bounded GitHub reads -> redaction and untrusted-data fencing -> optional static checks
      |                                                        |
      +---------------------- LangGraph ------------------------+
                                | fan out
                   correctness  security  test coverage
                                | fan in
                                v
              deterministic grounding filtering deduplication
                                |
                                v
                  deterministic marker-tagged Markdown
                                |
                                v
          exact-body approval and per-mutation head-SHA check
                                |
                                v
                   create or update one GitHub comment
```

The LangGraph graph has no GitHub write dependency. `GitHubPublisher` and
`PublicationController` live outside the graph.

## Requirements

- Python 3.12
- A public GitHub pull request for anonymous preview, or `GITHUB_READ_TOKEN` for higher read limits
- An OpenAI-compatible model endpoint for reviews
- Optional GitHub write token only for a controlled publication test

## Install

```bash
uv venv --python 3.12
uv pip install --python .venv/bin/python -e '.[dev]'
cp .env.example .env
```

Put real values only in the untracked `.env` file. The tracked `.env.example` contains placeholders.

## Run the app

```bash
.venv/bin/streamlit run streamlit_app.py
```

The page separates preview, model review, exact-body approval, and publication. Before model calls,
the user must approve the displayed call bound. Publishing remains disabled unless both
`ENABLE_GITHUB_PUBLISH=true` and `GITHUB_WRITE_TOKEN` are present.

## Model settings

| Variable | Purpose | Default |
|---|---|---|
| `LLM_API_KEY` | OpenAI-compatible endpoint credential | none |
| `LLM_BASE_URL` | OpenAI-compatible API root | none |
| `LLM_MODEL` | Provider model identifier | `Qwen/Qwen3-30B-A3B-Instruct-2507` |
| `LLM_TIMEOUT_SECONDS` | Request timeout | `30` |
| `LLM_MAX_RETRIES` | Malformed structured-response retry count | `2` |

The client sends one inexpensive capability probe using the exact schema used by specialists. The
provider-facing schema uses a conservative JSON Schema subset; Pydantic performs stricter internal
validation afterward.

## GitHub settings

| Variable | Purpose | Default |
|---|---|---|
| `GITHUB_READ_TOKEN` | Optional authenticated reads | empty |
| `GITHUB_WRITE_TOKEN` | Comment creation and update | empty |
| `ENABLE_GITHUB_PUBLISH` | Enables the publication capability | `false` |

The publisher updates only a marker-matching comment authored by the authenticated write identity.
It stops on multiple same-author matches. After an ambiguous create timeout, it searches for the
marker before retrying and rechecks the head SHA immediately before every update, create, or retry.

## Verification

```bash
.venv/bin/python -m pytest --cov=code_review_agent --cov-branch --cov-fail-under=90
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python scripts/scan_tracked_secrets.py
.venv/bin/detect-secrets scan --baseline .secrets.baseline
.venv/bin/pip-audit
.venv/bin/python -m build
.venv/bin/twine check dist/*
```

See `docs/functional-acceptance-report.md` for actual results rather than inferred status.

## Evaluation

Validate the catalog without model calls:

```bash
.venv/bin/python scripts/run_evaluation.py --mode validate
```

The complete paid workflow is explicit and gated:

```bash
.venv/bin/python scripts/run_evaluation.py --mode sequence --approve-model-calls
```

All ten head SHAs are preflighted before the first model call. The sequence then runs both clean
controls, all seven seeded defects, and the malformed-recovery case. Each case runs at most once.
Direct `clean`, `seeded`, and `recovery` modes are available for diagnosis; direct `full` mode is
blocked so it cannot bypass the gates. A complete sequence can make at most two capability probes
and `30 * (LLM_MAX_RETRIES + 1)` specialist attempts—92 provider calls with the default retry value
of two. An earlier failed gate reduces that bound.

The fixtures are [01](https://github.com/melepatt/code-review-agent-demo/pull/1),
[02](https://github.com/melepatt/code-review-agent-demo/pull/2),
[03](https://github.com/melepatt/code-review-agent-demo/pull/3),
[04](https://github.com/melepatt/code-review-agent-demo/pull/6),
[05](https://github.com/melepatt/code-review-agent-demo/pull/4),
[06](https://github.com/melepatt/code-review-agent-demo/pull/5),
[07](https://github.com/melepatt/code-review-agent-demo/pull/7),
[08](https://github.com/melepatt/code-review-agent-demo/pull/9),
[09](https://github.com/melepatt/code-review-agent-demo/pull/8), and
[10](https://github.com/melepatt/code-review-agent-demo/pull/10). Fixture creation did not run the
model. Generated JSON and Markdown contain only case status, finding IDs, categories, severities,
coordinates, completion, and metrics; they contain no source excerpts or provider responses.

The authorized live sequence preflighted all ten pins but stopped after the clean controls because
`golden-02` produced a high-severity correctness false positive. Direct diagnostic modes then ran
the seven seeded cases and the recovery case once. This covered ten unique case IDs, but it is not
an official complete sequence and does not erase the clean-gate failure. The saved artifacts are:

- Clean controls: [JSON](evaluation/runs/evaluation-20261026T002439043692Z-clean-controls.json) and
  [Markdown](evaluation/runs/evaluation-20261026T002439043692Z-clean-controls.md)
- Seeded cases: [JSON](evaluation/runs/evaluation-20261026T004421625474Z-seeded.json) and
  [Markdown](evaluation/runs/evaluation-20261026T004421625474Z-seeded.md)
- Recovery case: [JSON](evaluation/runs/evaluation-20261026T004440793716Z-recovery.json) and
  [Markdown](evaluation/runs/evaluation-20261026T004440793716Z-recovery.md)

The live baseline becomes the starting point for Week 4 evaluation work: audit labels, add
source-free rejection and retry diagnostics, expand and split the dataset, compare prompts and
models, and measure repeatability on a held-out set.

## Documentation

- `docs/architecture.md`
- `docs/security.md`
- `docs/evaluation-report.md`
- `docs/functional-acceptance-report.md`
- `docs/project-documentation.md`
- `docs/Week3-CodeReviewAgent-Project-Documentation.docx`
- `docs/video-demo-script.md`
