"""Configuración centralizada del proyecto BankAgent (Banamex Portfolio MVP)."""

from __future__ import annotations

import os
from pathlib import Path

# Rutas principales del proyecto
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"
DATA_RAW_DIR: Path = DATA_DIR / "raw"
DUCKDB_DIR: Path = DATA_DIR / "duckdb"
CHROMADB_DIR: Path = DATA_DIR / "chromadb"
STATE_DIR: Path = DATA_DIR / "state"
POLICIES_DIR: Path = DATA_DIR / "politicas_internas"
TEMPLATES_DIR: Path = PROJECT_ROOT / "templates"
OUTPUTS_DIR: Path = PROJECT_ROOT / "outputs"
CASES_DIR: Path = OUTPUTS_DIR / "cases"


def resolve_raw_csv_path() -> Path:
    """Resuelve la ruta del CSV fuente priorizando variable de entorno o archivo existente."""
    env_path = os.getenv("BANKAGENT_CSV_PATH")
    if env_path:
        return Path(env_path)

    full_csv = DATA_RAW_DIR / "base_cards_sintetica.csv"
    mini_csv = DATA_RAW_DIR / "base_cards_sintetica_mini.csv"
    if full_csv.exists():
        return full_csv
    if mini_csv.exists():
        return mini_csv
    return full_csv


RAW_CSV_PATH: Path = resolve_raw_csv_path()
DICTIONARY_XLSX_PATH: Path = DATA_RAW_DIR / "Base Cards para TEC - Diccionario de Variables.xlsx"
DUCKDB_PATH: Path = DUCKDB_DIR / "cubo_banamex.duckdb"
CHECKPOINTS_DB_PATH: Path = STATE_DIR / "checkpoints.db"

# Configuración de Ollama local (cero APIs externas)
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_TEMPERATURE: float = 0.1
OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

# Umbrales de apetito de riesgo (reglas de negocio base)
MAX_NCL_RATE_PCT: float = 15.0
MAX_OVER30_RATE_PCT: float = 25.0
MIN_MATURE_MOB: int = 6

# Columnas de texto que requieren TRIM() al ingerirse en DuckDB
TEXT_COLUMNS: tuple[str, ...] = (
    "STRATEGY",
    "STRATEGY_SEGMENT",
    "PRODUCT",
    "CHANNEL",
    "AGE_TAG",
    "SCORE_TAG",
)

