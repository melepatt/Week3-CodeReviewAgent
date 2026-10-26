# Security Design

## Security objective

The application must let an engineer inspect a model-assisted pull-request review without giving
repository content, the graph, or stale human approval authority to write to GitHub. When evidence
is incomplete or ambiguous, the system suppresses publication rather than guessing.

## Trust boundaries

| Boundary | Untrusted input | Enforced control |
|---|---|---|
| Streamlit input | Pull-request URL and edited Markdown | Canonical parsing, exact-body fingerprint, server-side revalidation |
| GitHub read API | Metadata, descriptions, patches, file content | Typed validation, pagination and size bounds, sanitized errors |
| Model context | All repository and PR text | Credential redaction, explicit fencing, no tool authority |
| Model output | Structured findings and notes | Provider schema, strict Pydantic conversion, bounded retries |
| Publication | Approved body and remote PR state | Default-off flag, write token, same-author marker, per-mutation SHA check |

## URL and network controls

Only `https://github.com/{owner}/{repo}/pull/{positive-number}` is accepted. Alternate hosts,
credentials in URLs, HTTP, trailing paths, query strings, fragments, encoded separators, and zero or
nonnumeric pull-request numbers are rejected. GitHub reads use bounded pages and transient retries.
Errors contain method, path, and status only; response bodies and authorization values are excluded.

## Repository content handling

The application never clones or executes pull-request code. It does not run package managers,
imports, tests, hooks, build scripts, or repository-supplied commands. The optional Python check uses
`ast.parse` on supplied text. External scanners are reported as unavailable when they are not run.

Credential redaction covers common assignment forms, bearer headers, GitHub tokens, OpenAI-style
keys, AWS access keys, and private-key blocks. Redaction is a risk reduction measure, not a guarantee;
operators should avoid reviewing pull requests that contain active secrets.

## Prompt injection controls

Prompts state that repository content is untrusted data and cannot change role, instructions, tool
use, or output format. Context is enclosed by explicit delimiters; delimiter-like repository text
is escaped, and truncation cannot remove the closing fence. Specialists have no GitHub tool, shell,
filesystem, or publisher. Deterministic code rejects invented paths and coordinates because they do
not match the captured context.

## Output controls

Each specialist can return at most three findings and three notes. The internal schema rejects
unknown categories, severities, reviewer identities, invalid paths, reverse line ranges, and high or
critical test-gap severity. Deterministic gates verify hunk relevance, evidence, recommendation, and
direct-test contradiction before rendering.

## Write controls

Publishing requires all of the following:

1. `ENABLE_GITHUB_PUBLISH=true`.
2. A separate `GITHUB_WRITE_TOKEN`.
3. A nonaborted review body containing the stable marker.
4. Human approval of the URL, captured SHA, generated body, and edited body.
5. A current GitHub head SHA equal to the reviewed SHA immediately before every mutation attempt.

The LangGraph workflow cannot publish. The evaluator cannot publish. The publisher updates only a
same-author marker match, stops on ambiguous duplicates, and searches after an ambiguous create
timeout before it retries.

## Secret management

`.env`, Streamlit secrets, traces, evaluation runs, caches, and build outputs are ignored. The
tracked `.env.example` uses placeholders. `scripts/scan_tracked_secrets.py` scans project files and
prints only path, line, and finding type. Detect-secrets provides an independent scan.

## Residual risks

- Pattern redaction cannot recognize every credential format.
- Bounded PR context can omit repository-wide behavior needed to confirm a finding.
- Token permissions are an operator responsibility; the write token should have the narrowest
  repository issue permission that supports comments.
- Same-author marker lookup assumes GitHub preserves comment author identity.
- Model output can be wrong even when it is well formed and grounded. Human review remains required.
- The ten synthetic evaluation cases are too small to support a production-accuracy claim.
