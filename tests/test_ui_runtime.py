from __future__ import annotations

from types import SimpleNamespace

import pytest

from code_review_agent import ui_runtime
from code_review_agent.approval import ApprovalState
from code_review_agent.config import AppConfig, ConfigurationError
from code_review_agent.llm import ProbeResult
from code_review_agent.models import PullRequestMetadata

URL = "https://github.com/acme/widgets/pull/7"


def metadata() -> PullRequestMetadata:
    return PullRequestMetadata(
        owner="acme",
        repo="widgets",
        number=7,
        url=URL,
        title="Safe widgets",
        author="octocat",
        base_branch="main",
        head_branch="safe-widgets",
        head_sha="a" * 40,
    )


class FakeReader:
    def __init__(self, *args, **kwargs) -> None:
        self.seen = []

    def get_metadata(self, ref):
        self.seen.append(ref)
        return metadata()


class FakeModel:
    supported = True

    def __init__(self, config) -> None:
        self.config = config

    def probe(self) -> ProbeResult:
        return ProbeResult(self.supported, "probe detail")


class FakeService:
    def __init__(self, reader, reviewers, limits) -> None:
        self.reader = reader
        self.reviewers = reviewers
        self.limits = limits

    def run(self, url: str):
        return SimpleNamespace(url=url)


class FakePublication:
    def __init__(self, config, publisher) -> None:
        self.config = config
        self.publisher = publisher

    def publish(self, outcome, url, body, approval):
        return SimpleNamespace(outcome=outcome, url=url, body=body, approval=approval)


def patch_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui_runtime, "GitHubReadClient", FakeReader)
    monkeypatch.setattr(ui_runtime, "StructuredModelClient", FakeModel)
    monkeypatch.setattr(ui_runtime, "ReviewService", FakeService)
    monkeypatch.setattr(ui_runtime, "PublicationController", FakePublication)
    monkeypatch.setattr(ui_runtime, "GitHubPublisher", lambda config: object())


def test_runtime_keeps_preview_available_without_optional_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_runtime(monkeypatch)
    runtime = ui_runtime.ApplicationRuntime(AppConfig.from_env({}))

    assert runtime.model_available is False
    assert runtime.publish_enabled is False
    assert runtime.preview(URL) == metadata()
    with pytest.raises(ConfigurationError, match="Model review is unavailable"):
        runtime.review(URL)
    with pytest.raises(ConfigurationError, match="publishing is disabled"):
        runtime.publish(SimpleNamespace(), URL, "body", ApprovalState())


def test_runtime_composes_model_and_publication_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_runtime(monkeypatch)
    config = AppConfig.from_env(
        {
            "LLM_API_KEY": "placeholder-key",
            "LLM_BASE_URL": "https://models.example.test/v1",
            "LLM_MAX_RETRIES": "1",
            "ENABLE_GITHUB_PUBLISH": "true",
            "GITHUB_WRITE_TOKEN": "placeholder-token",
        }
    )
    runtime = ui_runtime.ApplicationRuntime(config)

    outcome = runtime.review(URL)
    published = runtime.publish(outcome, URL, "approved body", ApprovalState())

    assert outcome.url == URL
    assert published.body == "approved body"
    assert runtime.model_available is True
    assert runtime.publish_enabled is True
    assert "1 structured-output capability probe" in runtime.model_call_summary
    assert "up to 1 retry/retries" in runtime.model_call_summary


def test_runtime_stops_when_provider_probe_is_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_runtime(monkeypatch)
    FakeModel.supported = False
    config = AppConfig.from_env(
        {
            "LLM_API_KEY": "placeholder-key",
            "LLM_BASE_URL": "https://models.example.test/v1",
        }
    )
    try:
        runtime = ui_runtime.ApplicationRuntime(config)
        with pytest.raises(ConfigurationError, match="probe detail"):
            runtime.review(URL)
    finally:
        FakeModel.supported = True


def test_runtime_can_be_built_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_runtime(monkeypatch)
    calls: list[str] = []
    config = AppConfig.from_env({})
    monkeypatch.setattr(ui_runtime, "load_dotenv", lambda: calls.append("dotenv"))
    monkeypatch.setattr(
        ui_runtime.AppConfig,
        "from_env",
        classmethod(lambda cls, env: config),
    )

    runtime = ui_runtime.ApplicationRuntime.from_environment()

    assert calls == ["dotenv"]
    assert runtime.model_available is False
