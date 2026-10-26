# Video Demo Script

Target length: five minutes. Keep GitHub publishing disabled. Use the saved evaluation artifacts;
do not rerun the golden cases solely for recording.

## 0 00 to 0 35 Project goal

Show the Streamlit title and safety notices.

Say: “This is a multi-agent pull-request reviewer. It captures one exact GitHub head SHA, runs
correctness, security, and test-coverage specialists in parallel, and uses deterministic code to
decide which findings can be published. The graph cannot write to GitHub.”

## 0 35 to 1 10 Preview

Paste a canonical public pull-request URL and select **Preview pull request**. Point out repository,
number, title, author, branches, and head SHA.

Say: “Preview is a separate read-only action. The URL parser rejects alternate hosts, extra paths,
queries, and fragments. GitHub reads are paginated and bounded.”

## 1 10 to 1 35 Model approval

Point to the model-call disclosure and approval checkbox.

Say: “Before a potentially paid operation, the page states one capability probe plus the bounded
specialist attempts. Review stays disabled until I approve those calls.”

## 1 35 to 2 25 Review result

Show an already captured review result if one is available in the current session. Otherwise, point
out where specialist status, partial-result disclosure, static-analysis availability, and exact
Markdown appear without starting another paid call.

Say: “Repository text is redacted and fenced as untrusted. Each specialist can return at most three
findings. Pydantic validates the structure, then deterministic checks enforce changed-file and
changed-line grounding, subject relevance, actionable recommendations, direct-test contradiction,
and deduplication.”

## 2 25 to 3 00 Approval reset

If an already captured result is available, approve the exact body and edit one character. If not,
explain the fingerprint using the interface and documentation without invoking the model.

Say: “Approval binds the URL, captured SHA, generated draft, and edited body. Any change clears the
fingerprint and disables publication. The hidden idempotence marker is already inside the body I
approve.”

## 3 00 to 3 35 Publication boundary

Keep the publish button disabled, or use an already approved controlled target.

Say: “Publishing needs an explicit environment flag and a separate write token. Immediately before
each update, create, or retry, the publisher checks the head SHA again. It updates only its own
marker-tagged comment. After an ambiguous create timeout, it searches before retrying.”

If a controlled write was approved, show the created or updated comment ID. Otherwise say:
“Publication is intentionally not demonstrated because no external write was approved.”

## 3 35 to 4 35 Evaluation baseline

Show the clean-control, seeded, and recovery Markdown artifacts alongside the evaluation report.

Say: “Offline checks and fixture setup are reported separately from model accuracy. The catalog has
ten synthetic pull requests: seven seeded defects, two clean controls, and one controlled
malformed-recovery case. The sequence checks every pin, runs clean controls before seeded defects,
and reviews each case at most once. The official run stopped with
`clean-controls-produced-findings` because one clean case produced a false positive. The remaining
cases ran once in diagnostic modes, not as a passing combined sequence.”

Show the baseline table.

Say: “Across the ten unique diagnostic results, recall is 10 percent, precision is 14.29 percent,
specialist completion is 93.33 percent, the duplicate rate is 0 percent, clean behavior failed, and
malformed-response recovery failed. Severity and location agreement are 100 percent for one matched
finding only. These are baseline measurements, not production-accuracy claims.”

## 4 35 to 5 00 Week 4 handoff

Show the Week 4 evaluation handoff in the project report.

Say: “Week 3 establishes the safe agent and a reproducible baseline. Week 4 can now improve the
evaluation itself: audit labels, add source-free rejection diagnostics, expand and split the
dataset, compare prompts and models, and measure repeatability on a held-out set. GitHub review
publication was not run.”
