"""Prueba de humo de conexión con Ollama local y generación de SQL sobre DuckDB."""

from __future__ import annotations

import re
import time

import duckdb
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from src.config import (
    DUCKDB_PATH,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_TEMPERATURE,
)

SCHEMA_SYSTEM_PROMPT = """Eres un analista cuantitativo de riesgo de portafolio de tarjetas de crédito en Banamex.
Tu única fuente de datos es una base DuckDB con la vista `v_cubo_metricas`.

Columnas clave de `v_cubo_metricas`:
- Dimensiones: `COHORT_ID`, `VINTAGE` (AAAAMM), `STRATEGY`, `STRATEGY_SEGMENT`, `PRODUCT`, `CHANNEL`, `AGE_TAG`, `SCORE_TAG`, `MOB` (0 a 32).
- Métricas aditivas: `ACCOUNTS`, `CREDITLINESAMTS`, `ENRACCTS`, `OVER30ACCTS`, `OVER30AMTS`, `GCLAMTS`, `NCLAMTS`, `RECOVERYAMTS`, `ENRAMTS`, `REVENUE`, `EXPENSES_ACQ`, `EXPENSES_ECM_VAR`, `EXPENSES_ECM_FIX`, `EXPENSES_TOTAL`.

REGLAS SQL OBLIGATORIAS (CERO EXCEPCIONES):
1. El cubo es agregado por cohorte y MOB. NUNCA sumes `ACCOUNTS` ni `CREDITLINESAMTS` a lo largo de todos los MOB; para volumen inicial filtra `WHERE MOB = 0`.
2. Para tasas agregadas NUNCA uses `AVG(ratio)`. Usa razón de sumas:
   - Tasa de pérdida neta (%): `(SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0`
   - Tasa Over30 (%): `(SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0`
   - Utilidad neta: `SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL)`
3. Responde únicamente con:
   - Una breve explicación (máximo 2 líneas).
   - Un bloque ```sql ... ``` con una consulta SELECT válida en dialecto DuckDB sobre `v_cubo_metricas` (con `LIMIT 20`).
"""

PROMPTS_DE_PRUEBA = [
    (
        "Nivel 1 (Descriptivo)",
        "¿Cuántas cuentas iniciales (MOB = 0) y qué monto de líneas de crédito iniciales hay por CHANNEL?",
    ),
    (
        "Nivel 2 (Causa Raíz)",
        "Compara la tasa de pérdida neta (NCL/ENR %) y la tasa de morosidad Over30 (OVER30/ENR %) "
        "entre los canales 'Aeropuerto' y 'Branch' para cohortes con MOB >= 6.",
    ),
    (
        "Nivel 3 (Dictamen por Score)",
        "Lista los 5 segmentos (CHANNEL, AGE_TAG, SCORE_TAG) con peor tasa de pérdida neta "
        "(NCL/ENR %) en MOB >= 6, mostrando su utilidad neta.",
    ),
]


def extract_sql_block(text: str) -> str | None:
    """Extrae el primer bloque SQL delimitado por ```sql ... ```."""
    match = re.search(r"```sql\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


def run_smoke_test() -> None:
    """Ejecuta los 3 prompts de prueba contra Ollama local y valida el SQL en DuckDB."""
    print(f"Conectando a Ollama en {OLLAMA_BASE_URL} con modelo '{OLLAMA_MODEL}'...")
    llm = ChatOllama(
        base_url=OLLAMA_BASE_URL,
        model=OLLAMA_MODEL,
        temperature=OLLAMA_TEMPERATURE,
        num_ctx=OLLAMA_NUM_CTX,
    )

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True) if DUCKDB_PATH.exists() else None
    try:
        for nombre, prompt in PROMPTS_DE_PRUEBA:
            print("\n" + "=" * 72)
            print(f"PRUEBA: {nombre}")
            print(f"PROMPT: {prompt}")
            print("-" * 72)

            t0 = time.perf_counter()
            response = llm.invoke(
                [
                    SystemMessage(content=SCHEMA_SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ]
            )
            elapsed = time.perf_counter() - t0
            content = str(response.content)

            print(f"Tiempo de respuesta: {elapsed:.2f} s")
            print("Respuesta del modelo:")
            print(content)

            sql = extract_sql_block(content)
            if sql and con is not None:
                print("-" * 72)
                print("Validando ejecución SQL en DuckDB (read_only=True)...")
                try:
                    rows = con.execute(sql).fetchall()
                    cols = [d[0] for d in con.description]
                    print(f"SQL OK | Columnas: {cols} | Filas devueltas: {len(rows)}")
                    for row in rows[:5]:
                        print("  ", row)
                except Exception as exc:  # noqa: BLE001
                    print(f"ERROR SQL en DuckDB: {exc}")
            elif not sql:
                print("AVISO: El modelo no devolvió un bloque ```sql ... ```.")
    finally:
        if con is not None:
            con.close()


if __name__ == "__main__":
    run_smoke_test()

