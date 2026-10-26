"""Environment-backed configuration with capability-specific validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"


class ConfigurationError(ValueError):
    """Raised when an invoked capability is not safely configured."""


def _parse_bool(name: str, raw: str | None, *, default: bool = False) -> bool:
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be true or false")


def _parse_float(name: str, raw: str | None, *, default: float) -> float:
    try:
        value = default if raw in {None, ""} else float(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{name} must be a number") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


def _parse_int(name: str, raw: str | None, *, default: int, low: int, high: int) -> int:
    try:
        value = default if raw in {None, ""} else int(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not low <= value <= high:
        raise ConfigurationError(f"{name} must be between {low} and {high}")
    return value


def _validate_http_url(name: str, raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.rstrip("/")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username:
        raise ConfigurationError(f"{name} must be an HTTP(S) endpoint without user information")
    return value


@dataclass(frozen=True, slots=True)
class ModelConfig:
    api_key: str | None
    base_url: str | None
    model: str
    timeout_seconds: float
    max_retries: int


@dataclass(frozen=True, slots=True)
class GitHubConfig:
    read_token: str | None
    write_token: str | None
    publish_enabled: bool
    api_url: str = "https://api.github.com"


@dataclass(frozen=True, slots=True)
class Limits:
    max_files: int = 50
    max_patch_chars: int = 20_000
    max_file_content_chars: int = 30_000
    max_total_context_chars: int = 120_000
    max_pages: int = 10


@dataclass(frozen=True, slots=True)
class TracingConfig:
    enabled: bool
    api_key: str | None
    workspace_id: str | None


@dataclass(frozen=True, slots=True)
class AppConfig:
    model: ModelConfig
    github: GitHubConfig
    limits: Limits
    tracing: TracingConfig

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> AppConfig:
        model = ModelConfig(
            api_key=env.get("LLM_API_KEY") or None,
            base_url=_validate_http_url("LLM_BASE_URL", env.get("LLM_BASE_URL")),
            model=env.get("LLM_MODEL") or DEFAULT_MODEL,
            timeout_seconds=_parse_float(
                "LLM_TIMEOUT_SECONDS", env.get("LLM_TIMEOUT_SECONDS"), default=30.0
            ),
            max_retries=_parse_int(
                "LLM_MAX_RETRIES", env.get("LLM_MAX_RETRIES"), default=2, low=0, high=5
            ),
        )
        github = GitHubConfig(
            read_token=env.get("GITHUB_READ_TOKEN") or None,
            write_token=env.get("GITHUB_WRITE_TOKEN") or None,
            publish_enabled=_parse_bool("ENABLE_GITHUB_PUBLISH", env.get("ENABLE_GITHUB_PUBLISH")),
        )
        tracing = TracingConfig(
            enabled=_parse_bool("LANGSMITH_TRACING", env.get("LANGSMITH_TRACING")),
            api_key=env.get("LANGSMITH_API_KEY") or None,
            workspace_id=env.get("LANGSMITH_WORKSPACE_ID") or None,
        )
        return cls(model=model, github=github, limits=Limits(), tracing=tracing)

    @property
    def model_available(self) -> bool:
        return bool(self.model.api_key and self.model.base_url)

    @property
    def publish_available(self) -> bool:
        return bool(self.github.publish_enabled and self.github.write_token)

    def require_model(self) -> ModelConfig:
        missing = []
        if not self.model.api_key:
            missing.append("LLM_API_KEY")
        if not self.model.base_url:
            missing.append("LLM_BASE_URL")
        if missing:
            raise ConfigurationError(f"Model review requires {', '.join(missing)}")
        return self.model

    def require_publish(self) -> GitHubConfig:
        if not self.github.publish_enabled:
            raise ConfigurationError("GitHub publishing is disabled")
        if not self.github.write_token:
            raise ConfigurationError("GitHub publishing requires GITHUB_WRITE_TOKEN")
        return self.github
