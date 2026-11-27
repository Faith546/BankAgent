"""Configuración centralizada del proyecto BankAgent (Banamex Portfolio MVP)."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

# Rutas principales del proyecto
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
def _load_dotenv_file(path: Path) -> int:
    """Carga pares CLAVE=VALOR de un `.env` simple sin pisar variables ya definidas en el entorno."""
    if not path.is_file():
        return 0
    loaded = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded

# Las variables reales del entorno siempre ganan sobre el `.env`
_load_dotenv_file(PROJECT_ROOT / ".env")


def validate_ollama_base_url(url: str) -> str:
    """Valida y normaliza `OLLAMA_BASE_URL` (solo `http://host[:puerto]`, sin TLS ni rutas)."""
    cleaned = (url or "").strip().rstrip("/")
    if cleaned.lower().startswith("https://"):
        raise ValueError(
            f"OLLAMA_BASE_URL={url!r} usa https://, pero Ollama sirve HTTP sin TLS. "
            f"Usa 'http://{cleaned[8:]}'."
        )
    if not cleaned.lower().startswith("http://"):
        raise ValueError(
            f"OLLAMA_BASE_URL={url!r} debe empezar con 'http://' "
            "(ejemplo: http://192.168.1.50:11434 o http://localhost:11434)."
        )
    parsed = urlparse(cleaned)
    if not parsed.hostname:
        raise ValueError(f"OLLAMA_BASE_URL={url!r} no incluye host.")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"OLLAMA_BASE_URL={url!r} tiene un puerto inválido.") from exc
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError(
            f"OLLAMA_BASE_URL={url!r} no debe incluir ruta ni parámetros; "
            "usa solo http://host:puerto."
        )
    return cleaned

DATA_DIR: Path = PROJECT_ROOT / "data"
DATA_RAW_DIR: Path = DATA_DIR / "raw"
DUCKDB_DIR: Path = DATA_DIR / "duckdb"
CHROMADB_DIR: Path = DATA_DIR / "chromadb"
STATE_DIR: Path = DATA_DIR / "state"
POLICIES_DIR: Path = DATA_DIR / "politicas_internas"
TEMPLATES_DIR: Path = PROJECT_ROOT / "templates"
OUTPUTS_DIR: Path = PROJECT_ROOT / "outputs"
CASES_DIR: Path = OUTPUTS_DIR / "cases"
MEMORIA_UTIL_DIR: Path = DATA_DIR / "memoria_util"


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


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "si", "on")


def _parse_optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    return int(raw) if raw is not None and raw.strip() != "" else None


def _parse_optional_float(name: str) -> float | None:
    raw = os.getenv(name)
    return float(raw) if raw is not None and raw.strip() != "" else None


RAW_CSV_PATH: Path = resolve_raw_csv_path()
DICTIONARY_XLSX_PATH: Path = DATA_RAW_DIR / "Base Cards para TEC - Diccionario de Variables.xlsx"
DUCKDB_PATH: Path = DUCKDB_DIR / "cubo_banamex.duckdb"
CHECKPOINTS_DB_PATH: Path = STATE_DIR / "checkpoints.db"

# Configuración de Ollama local (cero APIs externas)
OLLAMA_BASE_URL: str = validate_ollama_base_url(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
# temperature=0.0 mejora reproducibilidad en tool-calling y análisis numérico
OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.0"))
# reasoning=False (think: False en Ollama) evita que qwen3.5:9b gaste miles de tokens pensando
OLLAMA_REASONING: bool = _parse_bool_env("OLLAMA_REASONING", False)
OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
OLLAMA_TOP_K: int | None = _parse_optional_int("OLLAMA_TOP_K")
OLLAMA_TOP_P: float | None = _parse_optional_float("OLLAMA_TOP_P")

# Límites de ejecución del bucle agéntico (Guardrail de tope de vueltas)
AGENT_MAX_TURNS: int = int(os.getenv("AGENT_MAX_TURNS", "8"))

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

# Catálogo exacto de valores válidos del cubo (contratos de validación para tools)
VALID_PRODUCTS: tuple[str, ...] = (
    "Affinity",
    "Beyond",
    "Clasica",
    "Conquista",
    "Costco",
    "Descubre",
    "Explora",
    "Home Depot",
    "Joy",
    "Oro",
    "Platinum",
    "Teleton",
)

VALID_CHANNELS: tuple[str, ...] = (
    "Aeropuerto",
    "Affinity",
    "Beyond/Prestige",
    "Branch",
    "Costco",
    "F2F",
    "Home Depot",
    "Internet",
    "One Click",
    "Others",
    "TMK",
    "Turismo",
)

VALID_AGE_TAGS: tuple[str, ...] = (
    "01| Young < 25",
    "02| Young 25-30",
    "03| Mature >30",
)

VALID_STRATEGIES: tuple[str, ...] = (
    "14.Recalibration 1.0",
    "15.Recalibration 2.0",
    "DARIA 1.6",
    "DARIA 2.0",
    "r.Reca champ",
)

VALID_SCORE_TAGS: tuple[str, ...] = (
    "<130",
    "130-140",
    "141-150",
    "151-160",
    "161-170",
    "171-180",
    "181-190",
    "190+",
    "a.<=154",
    "b.155-159",
    "c.160-164",
    "d.165-169",
    "e.170-174",
    "f.175-189",
    "g.190-199",
    "h.200-204",
    "i.205+",
)

VINTAGE_MIN: int = 202401
VINTAGE_MAX: int = 202609

OLLAMA_VISION_MODEL = "qwen2.5vl:7b"

# modelos que el usuario puede escoger en la app, el normal es el de siempre
OLLAMA_MODELOS: dict[str, str] = {
    "Rápido": "qwen3.5:4b",
    "Normal": "qwen3.5:9b",
    "Potente": "gpt-oss:20b",
}

# caracteres del historial del chat que le mandamos al modelo en cada pregunta
HISTORIAL_CHARS: int = 4000
