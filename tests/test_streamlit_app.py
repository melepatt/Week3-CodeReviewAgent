from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from code_review_agent.config import Limits
from code_review_agent.context import build_review_context
from code_review_agent.github import HeadChangedError
from code_review_agent.models import (
    ChangedFile,
    PublishResult,
    PullRequestMetadata,
    PullRequestSnapshot,
    ReviewerIdentity,
    ReviewOutcome,
    SpecialistResult,
    SpecialistStatus,
    StaticAnalysisResult,
)

APP = Path(__file__).parents[1] / "streamlit_app.py"
URL = "https://github.com/acme/widgets/pull/7"
MARKDOWN = (
    "## Code review agent\n\nNo publishable findings.\n\n<!-- code-review-agent:acme/widgets#7 -->"
)


def metadata() -> PullRequestMetadata:
    return PullRequestMetadata(
        owner="acme",
        repo="widgets",
        number=7,
        url=URL,
        title="Safe parse",
        author="octocat",
        base_branch="main",
        head_branch="safe",
        head_sha="a" * 40,
    )


def review_outcome() -> ReviewOutcome:
    snapshot = PullRequestSnapshot(
        metadata=metadata(),
        files=(
            ChangedFile(
                path="src/widget.py",
                status="modified",
                additions=1,
                deletions=0,
                changes=1,
                patch="@@ -1 +1 @@\n+safe = True",
                content="safe = True\n",
            ),
        ),
    )
    context = build_review_context(snapshot, Limits(max_total_context_chars=10_000))
    specialists = (
        SpecialistResult(
            identity=ReviewerIdentity.CORRECTNESS,
            status=SpecialistStatus.SUCCESS,
            attempts=1,
        ),
        SpecialistResult(
            identity=ReviewerIdentity.SECURITY,
            status=SpecialistStatus.FAILED,
            attempts=1,
            failure="Malformed structured response after 1 attempts",
        ),
        SpecialistResult(
            identity=ReviewerIdentity.TEST_COVERAGE,
            status=SpecialistStatus.SUCCESS,
            attempts=1,
        ),
    )
    return ReviewOutcome(
        metadata=metadata(),
        context=context,
        specialists=specialists,
        static_analysis=StaticAnalysisResult(
            available=False,
            tools=(),
            signals=(),
            summary="External scanners were not run.",
        ),
        markdown=MARKDOWN,
        partial=True,
    )


class FakeRuntime:
    def __init__(
        self,
        *,
        model_available: bool = True,
        publish_enabled: bool = True,
        publish_error: Exception | None = None,
    ) -> None:
        self.model_available = model_available
        self.publish_enabled = publish_enabled
        self.preview_calls = 0
        self.review_calls = 0
        self.publish_calls = 0
        self.publish_error = publish_error
        self.model_call_summary = "1 capability probe and up to 9 specialist attempts"

    def preview(self, url: str) -> PullRequestMetadata:
        assert url == URL
        self.preview_calls += 1
        return metadata()

    def review(self, url: str) -> ReviewOutcome:
        assert url == URL
        self.review_calls += 1
        return review_outcome()

    def publish(self, outcome, url: str, body: str, approval) -> PublishResult:
        assert outcome.markdown == MARKDOWN
        assert url == URL
        assert body.endswith("<!-- code-review-agent:acme/widgets#7 -->")
        assert approval.fingerprint
        self.publish_calls += 1
        if self.publish_error is not None:
            raise self.publish_error
        return PublishResult(comment_id=321, action="created")


def app_with(runtime: FakeRuntime) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["_runtime_override"] = runtime
    return at.run()


def preview_pr(at: AppTest) -> AppTest:
    at.text_input(key="pr_url").set_value(URL)
    return at.form_submit_button(key="preview_submit").click().run()


def test_startup_without_credentials_keeps_preview_available_and_publish_off() -> None:
    at = app_with(FakeRuntime(model_available=False, publish_enabled=False))

    assert not at.exception
    assert at.title[0].value == "Pull request review"
    assert at.text_input(key="pr_url")
    assert any("Model review is unavailable" in warning.value for warning in at.warning)
    assert any("Publishing is disabled" in info.value for info in at.info)


def test_preview_and_review_are_separate_actions_with_required_metadata_and_status() -> None:
    runtime = FakeRuntime()
    at = preview_pr(app_with(runtime))

    assert not at.exception
    assert runtime.preview_calls == 1
    assert runtime.review_calls == 0
    page_text = "\n".join(item.value for item in at.markdown)
    for expected in ("acme/widgets", "#7", "Safe parse", "octocat", "main", "safe", "a" * 40):
        assert expected in page_text

    assert at.button(key="run_review").disabled is True
    at = at.checkbox(key="approve_model_calls").check().run()
    at = at.button(key="run_review").click().run()

    assert not at.exception
    assert runtime.review_calls == 1
    assert at.text_area(key="review_body").value == MARKDOWN
    page_text = "\n".join(item.value for item in at.markdown)
    assert "correctness" in page_text
    assert "security" in page_text
    assert any("Partial review" in warning.value for warning in at.warning)
    assert any("External scanners were not run" in warning.value for warning in at.warning)


def test_editing_markdown_resets_approval_and_disables_publish() -> None:
    at = preview_pr(app_with(FakeRuntime()))
    at = at.checkbox(key="approve_model_calls").check().run()
    at = at.button(key="run_review").click().run()
    at = at.checkbox(key="approve_exact").check().run()

    assert at.session_state["workflow"].approval.fingerprint
    assert at.button(key="publish_comment").disabled is False

    at = at.text_area(key="review_body").set_value(MARKDOWN + "\nchanged").run()

    assert at.session_state["workflow"].approval.fingerprint is None
    assert at.checkbox(key="approve_exact").value is False
    assert at.button(key="publish_comment").disabled is True


def test_approved_publication_displays_created_comment_id() -> None:
    runtime = FakeRuntime()
    at = preview_pr(app_with(runtime))
    at = at.checkbox(key="approve_model_calls").check().run()
    at = at.button(key="run_review").click().run()
    at = at.checkbox(key="approve_exact").check().run()
    at = at.button(key="publish_comment").click().run()

    assert not at.exception
    assert runtime.publish_calls == 1
    assert any("GitHub comment 321 created" in success.value for success in at.success)


def test_publish_control_stays_disabled_when_environment_flag_is_off() -> None:
    at = preview_pr(app_with(FakeRuntime(publish_enabled=False)))
    at = at.checkbox(key="approve_model_calls").check().run()
    at = at.button(key="run_review").click().run()
    at = at.checkbox(key="approve_exact").check().run()

    assert at.button(key="publish_comment").disabled is True


def test_head_change_during_publication_clears_exact_body_approval() -> None:
    runtime = FakeRuntime(
        publish_error=HeadChangedError(
            "Pull-request head SHA changed; regenerate and approve the review"
        )
    )
    at = preview_pr(app_with(runtime))
    at = at.checkbox(key="approve_model_calls").check().run()
    at = at.button(key="run_review").click().run()
    at = at.checkbox(key="approve_exact").check().run()
    at = at.button(key="publish_comment").click().run()

    assert runtime.publish_calls == 1
    assert at.session_state["workflow"].approval.fingerprint is None
    assert at.checkbox(key="approve_exact").value is False
    assert at.button(key="publish_comment").disabled is True
    assert any("head SHA changed" in error.value for error in at.error)
