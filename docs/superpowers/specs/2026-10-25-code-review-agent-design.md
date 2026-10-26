# Code Review Agent design

## Intent

Build a production-minded Week 3 project that helps an engineer review a GitHub pull request in a
Streamlit application. The system reads one canonical pull-request URL, gathers a bounded and
redacted snapshot at an exact head SHA, runs correctness, security, and test-coverage specialists,
and produces one deterministic review for a human to approve. Nothing is written to GitHub unless
publishing is enabled, the exact Markdown is approved, and the pull request still has the same head
SHA.

This implements the handout's code-heavy LangChain + LangGraph track and its central lesson: state,
tool-failure recovery, and human control at write boundaries matter more than a single prompt.

## One-liner and success measure

The agent helps software engineers review a GitHub pull request in a web app, replacing manual
diff-scanning with three bounded specialist reviews; it reads and analyzes autonomously, hands off
before a GitHub comment, and succeeds when an engineer can inspect a grounded, prioritized draft
and deliberately approve or reject the exact body without risking an accidental write.

## Goals

- Provide a typed, observable LangGraph fan-out/fan-in workflow for three specialists.
- Keep model output bounded and convert provider-compatible output into strict internal models.
- Make publishability a deterministic decision grounded in changed files and changed lines.
- Make every remote operation bounded, retryable where safe, and honest about partial failure.
- Make GitHub publication impossible from the graph and disabled by default everywhere else.
- Demonstrate behavior through branch-aware tests, source-free evaluation artifacts, packaging,
  security checks, and a Streamlit smoke test.

## Non-goals

- Executing pull-request code, installing its dependencies, or cloning it into an executable tree.
- Performing repository-wide semantic analysis beyond bounded PR patches and selected file content.
- Publishing inline review comments; one stable marker-tagged issue comment is the controlled write.
- Claiming production accuracy from five evaluation cases.
- Making paid model calls or GitHub writes during the offline build and verification phase.

## Anti-goals

- An agent or graph node that can write to GitHub.
- Prompt instructions from repository content influencing control flow or tool use.
- Fabricated static-analysis support, paths, line numbers, source excerpts, or evaluation evidence.
- Approval that survives a URL, head SHA, generated draft, or edited-body change.
- Logs or evaluation results containing credentials, prompts, provider bodies, or source excerpts.

## Approaches considered

### 1. Typed pipeline with deterministic safety boundaries — selected

Use focused Python modules, typed Pydantic models, a LangGraph `StateGraph`, injected GitHub/model
ports, and pure deterministic functions for grounding, filtering, deduplication, approval, and
Markdown. This is more code than a single agent, but it makes failure modes independently testable
and ensures the graph cannot publish.

### 2. One ReAct agent with GitHub tools — rejected

This would be shorter and more flexible, but it would blur read/write authority, make output and
retry behavior difficult to bound, and conflict with the required three-specialist orchestration.

### 3. Sequential specialist calls — rejected

This would simplify orchestration but would not demonstrate the handout's multi-agent fan-out and
would add avoidable latency. The reviewers have independent inputs and should run concurrently.

## Architecture

```text
Streamlit preview/run controls
        |
        v
GitHubReadClient -> bounded/redacted ReviewContext -> optional static checks
        |                                             |
        +-------------------- LangGraph ---------------+
                                | fan out
                   +------------+------------+
                   v            v            v
              correctness    security     test coverage
                   +------------+------------+
                                | fan in
                                v
                deterministic validate/filter/dedupe
                                |
                                v
                  deterministic Markdown + statuses
                                |
                                v
          session approval fingerprint (URL/SHA/draft/body)
                                |
                                v
                     GitHubPublisher (outside graph)
                  revalidate SHA -> update/create marker comment
```

### Boundaries

- `GitHubReadClient` has only GET operations and returns sanitized typed data.
- `ReviewGraph` consumes an already-built context and has no publisher or write credentials.
- `GitHubPublisher` owns comment lookup/create/update and always revalidates the head SHA first.
- The evaluation runner constructs read-only components and has no publisher dependency.
- Streamlit holds per-session approval state; pure approval helpers make resets testable.

### Package layout

- `src/code_review_agent/config.py`: strict environment settings and safe derived configuration.
- `src/code_review_agent/models.py`: provider and internal schemas, graph state, evaluation models.
- `src/code_review_agent/github.py`: canonical URL parser, read client, retries, pagination, publisher.
- `src/code_review_agent/context.py`: patch coordinates, size limits, redaction, injection fencing.
- `src/code_review_agent/static_analysis.py`: non-executing text checks with explicit availability.
- `src/code_review_agent/llm.py`: OpenAI-compatible chat model, exact-schema probe, bounded retries.
- `src/code_review_agent/reviewers.py`: three specialist prompts and conversion to internal findings.
- `src/code_review_agent/validation.py`: grounding, relevance, test contradiction, severity, dedupe.
- `src/code_review_agent/graph.py`: concurrent LangGraph orchestration and fail/partial policy.
- `src/code_review_agent/markdown.py`: deterministic consolidated review rendering.
- `src/code_review_agent/approval.py`: content fingerprint and approval reset rules.
- `src/code_review_agent/evaluation.py`: pinned catalog loading, gates, metrics, minimized outputs.
- `streamlit_app.py`: UI only; no business logic beyond state transitions and rendering.

## State and failure policy

The graph state stores the immutable review context, static-analysis status, per-specialist results,
accepted findings, failures, and final Markdown. Specialist completion is independent. One failed
specialist yields a disclosed partial review; two or three failures abort safely and produce no
publishable review. Model responses are retried only for malformed structured output, within the
configured bound.

Network reads retry bounded transient failures and rate-limit responses without logging bodies.
Publishing treats create timeouts as ambiguous: it searches by marker before any retry. A changed
head SHA stops publication and clears approval.

## Security design

- Parse only `https://github.com/{owner}/{repo}/pull/{positive integer}` with no query or fragment.
- Bound pages, files, per-patch bytes, fetched file bytes, and total context characters.
- Never execute repository code; optional static checks inspect text/AST only.
- Fence repository content as untrusted data and tell specialists to ignore embedded instructions.
- Redact common token, key, password, authorization, and private-key patterns before model calls.
- Keep logs metadata-only; exceptions exposed to users are sanitized.
- Require `ENABLE_GITHUB_PUBLISH=true`, a write token, an exact approval fingerprint, and head-SHA
  equality immediately before a comment write.
- Use one hidden marker derived from owner/repo/PR so repeated publication updates one comment.

## Deterministic publication rules

These rules intentionally prefer suppressing a questionable finding over publishing a weak one:

- Coordinates are inclusive, one-based line numbers on the head/right side. Renames use the new
  path. Deleted-only lines/files are not publishable. A missing or truncated patch is disclosed and
  cannot support a line-grounded finding.
- Correctness, security, test-gap, API-design, performance, and maintainability findings must overlap
  an added or modified head-side line. Documentation findings must refer to a changed file and valid
  head-side coordinate; they may anchor to unchanged context only when the documentation change is
  itself in that hunk.
- The provider finding includes a short `subject` identifier (function, class, endpoint, setting, or
  behavior). Relevance requires that normalized subject/evidence tokens intersect identifiers in the
  referenced hunk. Generic tokens and prose-only overlap do not count.
- Evidence is specific only when it names the concrete subject and describes an observable condition
  or mismatch in a bounded nonblank string. A recommendation is actionable only when it names the
  same subject and starts with a concrete change verb from a small documented allowlist. These are
  quality gates, not proof of correctness.
- A test-gap is contradicted only when an added/modified test hunk contains the same normalized
  subject plus a test/assert token and its test name or assertion tokens overlap the claimed behavior.
  Path proximity by itself is never enough. Ambiguous matches do not suppress the finding.
- The hidden marker is rendered into the exact Markdown shown to the user, fingerprinted, and
  approved. The publisher does not append or otherwise mutate the body after approval.
- The publisher updates only a marker-matching comment authored by the authenticated write identity.
  A foreign-authored marker is never overwritten. Multiple matching comments from the current
  identity are an ambiguous state and publication stops without writing.
- If at least two specialists fail, successful specialist outputs remain visible as nonpublishable
  diagnostics, but there is no consolidated review body and no state that can be approved.
- Configuration is validated per capability: the app and public-PR preview can start without tokens;
  missing read credentials may reduce GitHub rate limits, missing LLM settings disable review, and
  missing publish settings disable publishing. Each invoked capability rejects missing/invalid
  required values before making a request.

## Streamlit interaction design

The single page renders quickly, initializes session state once, and separates actions:

1. Enter a canonical PR URL and select **Preview pull request**.
2. Inspect repository, number, title, author, branches, and captured head SHA.
3. Select **Run review** to perform bounded reads and model calls.
4. Inspect specialist status, partial/unavailable disclosures, and exact Markdown.
5. Optionally edit the body; any input or body change clears approval.
6. Check an explicit approval control bound to the current fingerprint.
7. Publish only when environment configuration, approval, and unchanged SHA all pass.

The UI uses native Streamlit forms, containers, status messages, and code/Markdown elements without
custom CSS. API clients and model resources are cached with bounded lifetime; session results and
approval remain user-specific.

## Evaluation design

The tracked `evaluation/catalog.json` contains exactly five placeholder-safe cases with public URLs,
pinned SHAs, expected aliases/paths/ranges/severity ranges, ownership role, and recovery mode. The
runner validates the catalog, confirms all selected SHAs before any model call, cannot construct a
publisher, continues after operational failure, and writes timestamped JSON/Markdown containing no
source or evidence text.

The command sequence is enforced: offline verification, clean-control once, stop on any clean
finding, seeded-defect once, then all five once. Live runs are documented as pending until the user
supplies and approves exact cases and paid calls. Unavailable metrics are `N/A`; no production
accuracy claim is made.

## Acceptance criteria matrix

| Requirement | Acceptance criterion |
|---|---|
| Canonical URL | Valid owner/repo/positive PR parses; scheme/host/path/query/fragment variants fail. |
| GitHub retrieval | Metadata, paginated files, bounded patches, selected content, and exact head SHA are returned with bounded retries. |
| Bounded context | Limits truncate or omit deterministically and all model-bound text is redacted and fenced as untrusted. |
| Static analysis | Only non-executing inspection runs; each tool reports available/unavailable and never fabricates support. |
| Three reviewers | LangGraph fans out concurrently to correctness, security, and test-coverage nodes and joins their typed results. |
| Model configuration | Required model settings come from environment; Qwen default is configurable; invalid values fail closed. |
| Capability probe | One inexpensive call uses the exact provider schema before reviews and records pass/fail without assuming unsupported JSON Schema keywords. |
| Structured output | Provider schema allows at most three findings and notes; strict internal conversion rejects invalid categories, severities, coordinates, or identities. |
| Malformed output | Parsing retries are bounded; terminal specialist failure is explicit; two failures abort, one is disclosed. |
| Grounding | Publishable findings reference changed files, valid coordinates, required changed lines, and PR-relevant evidence. |
| Test contradiction | A direct added test covering the claimed behavior suppresses a contradicted test-gap finding. |
| Severity | Definitions are embedded; missing tests are medium/low and cannot be high solely for hypothetical impact. |
| Deduplication | A stable normalized key and deterministic precedence remove duplicates independent of response ordering. |
| Markdown | The same accepted findings and statuses always render byte-identical prioritized Markdown. |
| Graph write safety | No graph constructor, state, or node accepts a GitHub write client or calls write endpoints. |
| Approval | Approval binds URL, head SHA, generated draft, and edited body; changing any component resets it. |
| Default-off writes | Publishing is unavailable unless the explicit env flag and write token are present. |
| Head revalidation | Publisher fetches current head immediately before writing and refuses a mismatch. |
| Idempotence | Stable hidden marker updates one existing comment; absent marker creates one comment. |
| Ambiguous timeout | After create timeout, publisher searches for the marker before retrying and never blindly duplicates. |
| Secret handling | `.env.example`, `.gitignore`, detect-secrets baseline/config, and tracked-file scanner contain no real secrets. |
| Streamlit preview | URL preview displays repository, PR number, title, author, branches, and SHA before review. |
| Streamlit review | Review is a separate action; specialist statuses, partial failures, unavailable tools, exact body, approval, and comment ID are visible. |
| Regression tests | Tests cover every topic listed in the regeneration prompt, including Streamlit `AppTest` behavior. |
| Coverage | Test command enforces at least 90% branch coverage for the application package. |
| Evaluation catalog | Five pinned public cases are schema-validated and include seeded, clean-control, malformed-recovery roles. |
| Evaluation safety | Runner has no publishing capability, checks SHA before model calls, continues on operational failures, and emits source-free artifacts. |
| Evaluation metrics | Recall, precision, severity/location agreement, duplicate rate, completion, recovery, and clean behavior are reported or `N/A`. |
| Documentation | README, architecture, security, evaluation, functional acceptance, project documentation, video script, and rendered DOCX exist and distinguish evidence classes. |
| Verification | Tests/coverage, Ruff, secret scans, detect-secrets, pip-audit, distributions, archive checks, Streamlit smoke, and approved evaluation gates are run and reported honestly. |

## Decisions deferred without blocking implementation

- Exact five public evaluation URLs and pinned SHAs: placeholders cannot masquerade as evidence;
  the catalog will require explicit real values before a live run.
- OpenAI-compatible endpoint and credentials: no paid call will be made without a separate approval.
- GitHub write token and controlled target PR: no write will be made without a separate approval.
- Optional LangSmith tracing: implemented as environment-gated observability and disabled by default.

## Staged delivery

1. Foundations: packaging, configuration, schemas, URL parsing, context bounds, and security.
2. Review engine: model adapter/probe, specialists, static checks, validation, graph, Markdown.
3. Human boundary: approval state, publisher idempotence, and Streamlit workflow.
4. Evidence: regression tests, evaluation harness/catalog, scanners, packaging, and smoke checks.
5. Communication: architecture/security/evaluation/acceptance docs, project report, DOCX, demo script.
6. Optional controlled live work after explicit approval: clean gate, seeded gate, full evaluation,
   and one publication acceptance test.
