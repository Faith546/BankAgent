"""Pruebas de la validación de `OLLAMA_BASE_URL`, la carga de `.env` y el chequeo de modelos."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.config import _load_dotenv_file, validate_ollama_base_url
from tests.check_ollama_connection import model_installed


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:11434", "http://localhost:11434"),
        ("http://192.168.1.50:11434/", "http://192.168.1.50:11434"),
        ("  http://gpu-tec.local:11434  ", "http://gpu-tec.local:11434"),
        ("HTTP://10.0.0.5", "HTTP://10.0.0.5"),
    ],
)
def test_validate_ollama_base_url_accepts_http(raw: str, expected: str) -> None:
    assert validate_ollama_base_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "192.168.1.50:11434",  # sin esquema
        "ftp://host:11434",
        "http://",  # sin host
        "http://host:abc",  # puerto inválido
        "http://host:99999",  # puerto fuera de rango
        "http://host:11434/api/tags",  # no debe llevar ruta
    ],
)
def test_validate_ollama_base_url_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        validate_ollama_base_url(raw)


def test_validate_ollama_base_url_rejects_https_with_hint() -> None:
    with pytest.raises(ValueError, match="http://192.168.1.50:11434"):
        validate_ollama_base_url("https://192.168.1.50:11434")


def test_load_dotenv_file_does_not_override_existing_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comentario\n"
        "BA_TEST_URL=http://10.0.0.9:11434\n"
        'BA_TEST_QUOTED="valor con comillas"\n'
        "export BA_TEST_EXPORT=1\n"
        "BA_TEST_EXISTING=desde_archivo\n"
        "línea sin igual\n",
        encoding="utf-8",
    )
    for key in ("BA_TEST_URL", "BA_TEST_QUOTED", "BA_TEST_EXPORT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BA_TEST_EXISTING", "desde_terminal")

    loaded = _load_dotenv_file(env_file)
    try:
        assert loaded == 3
        assert os.environ["BA_TEST_URL"] == "http://10.0.0.9:11434"
        assert os.environ["BA_TEST_QUOTED"] == "valor con comillas"
        assert os.environ["BA_TEST_EXPORT"] == "1"
        assert os.environ["BA_TEST_EXISTING"] == "desde_terminal"
    finally:
        for key in ("BA_TEST_URL", "BA_TEST_QUOTED", "BA_TEST_EXPORT"):
            os.environ.pop(key, None)


def test_load_dotenv_file_missing_returns_zero(tmp_path: Path) -> None:
    assert _load_dotenv_file(tmp_path / "no_existe.env") == 0


def test_model_installed_handles_latest_tag() -> None:
    installed = ["qwen3.5:9b", "nomic-embed-text:latest"]
    assert model_installed("qwen3.5:9b", installed)
    assert model_installed("nomic-embed-text", installed)
    assert not model_installed("qwen3.8", installed)
    assert not model_installed("qwen3.5:4b", installed)
