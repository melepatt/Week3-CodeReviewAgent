"""OpenAI-compatible structured-output adapter with an exact-schema probe."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from threading import Lock

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from code_review_agent.config import ModelConfig
from code_review_agent.models import (
    ProviderSpecialistOutput,
    ReviewContext,
    ReviewerIdentity,
    SpecialistResult,
    SpecialistStatus,
)
from code_review_agent.prompts import build_probe_messages, build_specialist_messages

_FINDING_PROPERTIES: dict[str, object] = {
    "identifier": {"type": "string"},
    "category": {"type": "string"},
    "severity": {"type": "string"},
    "title": {"type": "string"},
    "path": {"type": "string"},
    "start_line": {"type": "integer"},
    "end_line": {"type": "integer"},
    "subject": {"type": "string"},
    "evidence": {"type": "string"},
    "impact": {"type": "string"},
    "recommendation": {"type": "string"},
    "reviewer": {"type": "string"},
}
PROVIDER_SCHEMA: dict[str, object] = {
    "title": "specialist_review",
    "description": "Bounded pull-request specialist findings",
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": _FINDING_PROPERTIES,
                "required": list(_FINDING_PROPERTIES),
                "additionalProperties": False,
            },
        },
        "validation_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["findings", "validation_notes"],
    "additionalProperties": False,
}

InvokeStructured = Callable[[Sequence[BaseMessage], dict[str, object]], object]


@dataclass(frozen=True, slots=True)
class ProbeResult:
    supported: bool
    detail: str


class _LangChainInvoker:
    def __init__(self, config: ModelConfig) -> None:
        if not config.api_key or not config.base_url:
            raise ValueError("Model credentials and base URL are required")
        model = ChatOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            timeout=config.timeout_seconds,
            max_retries=0,
            temperature=0,
        )
        self._structured = model.with_structured_output(
            PROVIDER_SCHEMA, method="json_schema", strict=True
        )

    def __call__(self, messages: Sequence[BaseMessage], schema: dict[str, object]) -> object:
        if schema is not PROVIDER_SCHEMA:
            raise ValueError("Unexpected provider schema")
        return self._structured.invoke(list(messages))


class StructuredModelClient:
    """Runs one capability probe and bounded strict-conversion attempts."""

    def __init__(self, config: ModelConfig, *, invoke: InvokeStructured | None = None) -> None:
        self._config = config
        self._invoke = invoke or _LangChainInvoker(config)
        self._probe: ProbeResult | None = None
        self._probe_lock = Lock()

    def probe(self) -> ProbeResult:
        if self._probe is not None:
            return self._probe
        with self._probe_lock:
            if self._probe is None:
                try:
                    raw = self._invoke(build_probe_messages(), PROVIDER_SCHEMA)
                    ProviderSpecialistOutput.model_validate(raw)
                except Exception:  # provider errors and validation are deliberately sanitized
                    self._probe = ProbeResult(False, "Structured-output capability probe failed")
                else:
                    self._probe = ProbeResult(True, "Structured-output capability probe passed")
            return self._probe

    def review(self, identity: ReviewerIdentity, context: ReviewContext) -> SpecialistResult:
        probe = self.probe()
        if not probe.supported:
            return SpecialistResult(
                identity=identity,
                status=SpecialistStatus.FAILED,
                attempts=0,
                failure=probe.detail,
            )
        attempts = 0
        for attempts in range(1, self._config.max_retries + 2):
            try:
                raw = self._invoke(build_specialist_messages(identity, context), PROVIDER_SCHEMA)
                provider = ProviderSpecialistOutput.model_validate(raw)
                findings = tuple(item.to_internal() for item in provider.findings)
                if any(item.reviewer is not identity for item in findings):
                    raise ValidationError.from_exception_data("Reviewer identity mismatch", [])
                return SpecialistResult(
                    identity=identity,
                    status=SpecialistStatus.SUCCESS,
                    findings=findings,
                    validation_notes=tuple(provider.validation_notes),
                    attempts=attempts,
                )
            except Exception:  # noqa: S112 - never retain provider response or exception text
                continue
        return SpecialistResult(
            identity=identity,
            status=SpecialistStatus.FAILED,
            attempts=attempts,
            failure=f"Malformed structured response after {attempts} attempts",
        )
