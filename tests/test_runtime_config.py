from __future__ import annotations

import pytest

import backend.runtime_config as runtime_config


def test_development_configuration_is_valid(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        runtime_config,
        "IS_PRODUCTION",
        False,
    )

    monkeypatch.setattr(
        runtime_config,
        "APP_ENV",
        "development",
    )

    monkeypatch.setattr(
        runtime_config,
        "CORS_ORIGINS",
        [
            "http://localhost:3000",
        ],
    )

    monkeypatch.setattr(
        runtime_config,
        "ALLOWED_HOSTS",
        [
            "localhost",
            "127.0.0.1",
        ],
    )

    result = (
        runtime_config
        .validate_runtime_config()
    )

    assert result[
        "environment"
    ] == "development"

    assert result[
        "production"
    ] is False


def test_wildcard_cors_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        runtime_config,
        "CORS_ORIGINS",
        ["*"],
    )

    with pytest.raises(
        RuntimeError,
        match="Wildcard CORS",
    ):
        runtime_config.validate_runtime_config()


def test_production_requires_real_host(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        runtime_config,
        "IS_PRODUCTION",
        True,
    )

    monkeypatch.setattr(
        runtime_config,
        "APP_ENV",
        "production",
    )

    monkeypatch.setattr(
        runtime_config,
        "ALLOWED_HOSTS",
        [
            "localhost",
            "127.0.0.1",
        ],
    )

    monkeypatch.setattr(
        runtime_config,
        "CORS_ORIGINS",
        [
            "https://frontend.example.com",
        ],
    )

    with pytest.raises(
        RuntimeError,
        match="deployed API host",
    ):
        runtime_config.validate_runtime_config()


def test_production_requires_real_frontend(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        runtime_config,
        "IS_PRODUCTION",
        True,
    )

    monkeypatch.setattr(
        runtime_config,
        "APP_ENV",
        "production",
    )

    monkeypatch.setattr(
        runtime_config,
        "ALLOWED_HOSTS",
        [
            "api.example.com",
        ],
    )

    monkeypatch.setattr(
        runtime_config,
        "CORS_ORIGINS",
        [
            "http://localhost:3000",
        ],
    )

    with pytest.raises(
        RuntimeError,
        match="deployed frontend origin",
    ):
        runtime_config.validate_runtime_config()


def test_production_configuration_can_be_valid(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        runtime_config,
        "IS_PRODUCTION",
        True,
    )

    monkeypatch.setattr(
        runtime_config,
        "APP_ENV",
        "production",
    )

    monkeypatch.setattr(
        runtime_config,
        "ALLOWED_HOSTS",
        [
            "api.example.com",
        ],
    )

    monkeypatch.setattr(
        runtime_config,
        "CORS_ORIGINS",
        [
            "https://app.example.com",
        ],
    )

    result = (
        runtime_config
        .validate_runtime_config()
    )

    assert result[
        "production"
    ] is True


def test_documentation_enabled_in_development(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        runtime_config,
        "IS_PRODUCTION",
        False,
    )

    settings = (
        runtime_config
        .api_documentation_settings()
    )

    assert settings[
        "docs_url"
    ] == "/docs"

    assert settings[
        "openapi_url"
    ] == "/openapi.json"


def test_documentation_disabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        runtime_config,
        "IS_PRODUCTION",
        True,
    )

    settings = (
        runtime_config
        .api_documentation_settings()
    )

    assert settings == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }