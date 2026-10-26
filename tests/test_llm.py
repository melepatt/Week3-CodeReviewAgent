from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep

from langchain_core.messages import BaseMessage

from code_review_agent.config import Limits, ModelConfig
from code_review_agent.context import build_review_context
from code_review_agent.llm import PROVIDER_SCHEMA, StructuredModelClient
from code_review_agent.models import (
    ChangedFile,
    PullRequestMetadata,
    PullRequestSnapshot,
    ReviewerIdentity,
    SpecialistStatus,
)


def context():
    metadata = PullRequestMetadata(
        owner="acme",
        repo="widgets",
        number=7,
        url="https://github.com/acme/widgets/pull/7",
        title="Validate widgets",
        author="octocat",
        base_branch="main",
        head_branch="validation",
        head_sha="a" * 40,
    )
    file = ChangedFile(
        path="src/widget.py",
        status="modified",
        additions=1,
        deletions=0,
        changes=1,
        patch="@@ -1 +1,2 @@\n def build_widget():\n+    validate_widget()",
        content="def build_widget():\n    validate_widget()\n",
    )
    return build_review_context(
        PullRequestSnapshot(metadata=metadata, files=(file,)),
        Limits(max_total_context_chars=10_000),
    )


def valid_payload(identity: str = "correctness") -> dict[str, object]:
    return {
        "findings": [
            {
                "identifier": "correctness.widget-check",
                "category": "correctness",
                "severity": "medium",
                "title": "Widget validation result is ignored",
                "path": "src/widget.py",
                "start_line": 2,
                "end_line": 2,
                "subject": "validate_widget",
                "evidence": "validate_widget is called without checking its result",
                "impact": "Invalid widgets may continue into request processing",
                "recommendation": "Check validate_widget result and return a clear error",
                "reviewer": identity,
            }
        ],
        "validation_notes": ["Coordinates refer to the supplied changed line"],
    }


def model_config(max_retries: int = 2) -> ModelConfig:
    return ModelConfig(
        api_key="placeholder",
        base_url="https://models.example.test/v1",
        model="example/model",
        timeout_seconds=10,
        max_retries=max_retries,
    )


def test_provider_schema_uses_only_compatibility_baseline_keywords() -> None:
    serialized = repr(PROVIDER_SCHEMA)

    assert PROVIDER_SCHEMA["type"] == "object"
    assert set(PROVIDER_SCHEMA["required"]) == {"findings", "validation_notes"}
    assert "enum" not in serialized
    assert "anyOf" not in serialized
    assert "maxItems" not in serialized
    assert "$ref" not in serialized


def test_real_langchain_adapter_accepts_provider_schema_without_network() -> None:
    client = StructuredModelClient(model_config())

    assert client is not None


def test_capability_probe_uses_exact_provider_schema_once() -> None:
    schemas: list[dict[str, object]] = []

    def invoke(messages: Sequence[BaseMessage], schema: dict[str, object]) -> object:
        schemas.append(schema)
        assert any("capability probe" in str(message.content).lower() for message in messages)
        return {"findings": [], "validation_notes": []}

    client = StructuredModelClient(model_config(), invoke=invoke)

    first = client.probe()
    second = client.probe()

    assert first.supported is True
    assert second == first
    assert schemas == [PROVIDER_SCHEMA]


def test_capability_probe_is_one_time_under_concurrent_calls() -> None:
    calls = 0
    calls_lock = Lock()

    def invoke(messages: Sequence[BaseMessage], schema: dict[str, object]) -> object:
        nonlocal calls
        with calls_lock:
            calls += 1
        sleep(0.03)
        return {"findings": [], "validation_notes": []}

    client = StructuredModelClient(model_config(), invoke=invoke)

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = tuple(pool.map(lambda _: client.probe(), range(5)))

    assert all(result.supported for result in results)
    assert calls == 1


def test_review_retries_malformed_output_with_hard_bound() -> None:
    calls = 0

    def invoke(messages: Sequence[BaseMessage], schema: dict[str, object]) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"findings": [], "validation_notes": []}  # probe
        if calls < 4:
            return {"findings": "not-a-list", "validation_notes": []}
        return valid_payload()

    client = StructuredModelClient(model_config(max_retries=2), invoke=invoke)

    result = client.review(ReviewerIdentity.CORRECTNESS, context())

    assert result.status is SpecialistStatus.SUCCESS
    assert result.attempts == 3
    assert len(result.findings) == 1
    assert calls == 4


def test_terminal_malformed_output_records_sanitized_failure() -> None:
    calls = 0

    def invoke(messages: Sequence[BaseMessage], schema: dict[str, object]) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"findings": [], "validation_notes": []}
        return {"provider_secret": "must-not-escape"}

    client = StructuredModelClient(model_config(max_retries=1), invoke=invoke)

    result = client.review(ReviewerIdentity.SECURITY, context())

    assert result.status is SpecialistStatus.FAILED
    assert result.attempts == 2
    assert result.failure == "Malformed structured response after 2 attempts"
    assert "must-not-escape" not in result.failure


def test_probe_failure_prevents_specialist_call() -> None:
    calls = 0

    def invoke(messages: Sequence[BaseMessage], schema: dict[str, object]) -> object:
        nonlocal calls
        calls += 1
        raise RuntimeError("provider body and secret")

    client = StructuredModelClient(model_config(), invoke=invoke)

    result = client.review(ReviewerIdentity.SECURITY, context())

    assert result.status is SpecialistStatus.FAILED
    assert result.failure == "Structured-output capability probe failed"
    assert calls == 1


def test_reviewer_identity_mismatch_is_retried_then_failed() -> None:
    def invoke(messages: Sequence[BaseMessage], schema: dict[str, object]) -> object:
        if "capability probe" in str(messages[-1].content).lower():
            return {"findings": [], "validation_notes": []}
        return valid_payload(identity="security")

    client = StructuredModelClient(model_config(max_retries=0), invoke=invoke)

    result = client.review(ReviewerIdentity.CORRECTNESS, context())

    assert result.status is SpecialistStatus.FAILED
    assert result.failure == "Malformed structured response after 1 attempts"
