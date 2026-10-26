from __future__ import annotations

import pytest

from code_review_agent.config import AppConfig, ConfigurationError


def test_app_can_start_without_credentials_and_uses_safe_defaults() -> None:
    config = AppConfig.from_env({})

    assert config.model.model == "Qwen/Qwen3-30B-A3B-Instruct-2507"
    assert config.model.timeout_seconds == 30.0
    assert config.model.max_retries == 2
    assert config.github.publish_enabled is False
    assert config.model_available is False
    assert config.publish_available is False


def test_model_capability_rejects_missing_required_values() -> None:
    config = AppConfig.from_env({"LLM_API_KEY": "placeholder-key"})

    with pytest.raises(ConfigurationError, match="LLM_BASE_URL"):
        config.require_model()


def test_model_capability_accepts_configurable_openai_endpoint() -> None:
    config = AppConfig.from_env(
        {
            "LLM_API_KEY": "placeholder-key",
            "LLM_BASE_URL": "https://models.example.test/v1",
            "LLM_MODEL": "example/model",
            "LLM_TIMEOUT_SECONDS": "12.5",
            "LLM_MAX_RETRIES": "1",
        }
    )

    model = config.require_model()

    assert model.model == "example/model"
    assert model.timeout_seconds == 12.5
    assert model.max_retries == 1


@pytest.mark.parametrize(
    ("name", "value"),
    [("LLM_TIMEOUT_SECONDS", "0"), ("LLM_MAX_RETRIES", "-1"), ("LLM_MAX_RETRIES", "6")],
)
def test_invalid_numeric_model_configuration_fails_closed(name: str, value: str) -> None:
    with pytest.raises(ConfigurationError):
        AppConfig.from_env({name: value})


def test_publish_capability_requires_both_explicit_flag_and_token() -> None:
    disabled = AppConfig.from_env({"GITHUB_WRITE_TOKEN": "placeholder-token"})
    enabled_without_token = AppConfig.from_env({"ENABLE_GITHUB_PUBLISH": "true"})

    with pytest.raises(ConfigurationError, match="disabled"):
        disabled.require_publish()
    with pytest.raises(ConfigurationError, match="GITHUB_WRITE_TOKEN"):
        enabled_without_token.require_publish()


def test_publish_capability_accepts_explicit_flag_and_token() -> None:
    config = AppConfig.from_env(
        {"ENABLE_GITHUB_PUBLISH": "true", "GITHUB_WRITE_TOKEN": "placeholder-token"}
    )

    assert config.require_publish().write_token == "placeholder-token"


def test_invalid_boolean_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="ENABLE_GITHUB_PUBLISH"):
        AppConfig.from_env({"ENABLE_GITHUB_PUBLISH": "sometimes"})
