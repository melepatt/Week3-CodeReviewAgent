"""Production dependencies used by the Streamlit page."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from code_review_agent.approval import ApprovalState, PublicationController
from code_review_agent.config import AppConfig, ConfigurationError
from code_review_agent.github import GitHubPublisher, GitHubReadClient, parse_pull_request_url
from code_review_agent.graph import ReviewerSet
from code_review_agent.llm import StructuredModelClient
from code_review_agent.models import (
    PublishResult,
    PullRequestMetadata,
    ReviewerIdentity,
    ReviewOutcome,
)
from code_review_agent.reviewers import run_specialist
from code_review_agent.service import ReviewService


class ApplicationRuntime:
    """Composes capabilities while preserving the graph's read-only boundary."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self.model_available = config.model_available
        self.publish_enabled = config.publish_available
        self.model_call_summary = (
            "1 structured-output capability probe, then 3 specialist calls with up to "
            f"{config.model.max_retries} retry/retries each"
        )
        reader = GitHubReadClient(
            config.github.read_token,
            api_url=config.github.api_url,
            max_pages=config.limits.max_pages,
        )
        self._reader = reader
        self._service: ReviewService | None = None
        self._model_client: StructuredModelClient | None = None
        if self.model_available:
            model_client = StructuredModelClient(config.require_model())
            self._model_client = model_client
            reviewers = ReviewerSet(
                correctness=lambda context: run_specialist(
                    ReviewerIdentity.CORRECTNESS, context, model_client
                ),
                security=lambda context: run_specialist(
                    ReviewerIdentity.SECURITY, context, model_client
                ),
                test_coverage=lambda context: run_specialist(
                    ReviewerIdentity.TEST_COVERAGE, context, model_client
                ),
            )
            self._service = ReviewService(reader, reviewers, config.limits)
        self._publication: PublicationController | None = None
        if self.publish_enabled:
            github = config.require_publish()
            self._publication = PublicationController(github, GitHubPublisher(github))

    @classmethod
    def from_environment(cls) -> ApplicationRuntime:
        load_dotenv()
        return cls(AppConfig.from_env(os.environ))

    def preview(self, url: str) -> PullRequestMetadata:
        # Preview is deliberately available without model credentials.
        return self._reader.get_metadata(parse_pull_request_url(url))

    def review(self, url: str) -> ReviewOutcome:
        if self._service is None or self._model_client is None:
            raise ConfigurationError(
                "Model review is unavailable until LLM settings are configured"
            )
        # The probe runs once, synchronously, before fan-out to avoid duplicate capability calls.
        probe = self._model_client.probe()
        if not probe.supported:
            raise ConfigurationError(probe.detail)
        return self._service.run(url)

    def publish(
        self,
        outcome: ReviewOutcome,
        url: str,
        body: str,
        approval: ApprovalState,
    ) -> PublishResult:
        if self._publication is None:
            raise ConfigurationError("GitHub publishing is disabled")
        return self._publication.publish(outcome, url, body, approval)
