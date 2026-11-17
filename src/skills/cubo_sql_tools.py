"""Skill 1: Herramientas parametrizadas y Text-to-SQL seguro sobre DuckDB (read_only=True)."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import duckdb
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.config import DUCKDB_PATH

_FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|COPY|ATTACH|DETACH|PRAGMA|CALL|EXPORT|IMPORT|REPLACE|TRUNCATE|MERGE)\b",
    re.IGNORECASE,
)


class FiltroCuboInput(BaseModel):
    """Filtros opcionales para consultar cohortes del cubo Banamex."""

    channel: Optional[str] = Field(
        default=None,
        description="Canal de colocación exacto (ej. 'Aeropuerto', 'Branch', 'F2F', 'Internet').",
    )
    age_tag: Optional[str] = Field(
        default=None,
        description="Rango de edad exacto (ej. '01| Young < 25', '02| Young 25-30', '03| Mature >30').",
    )
    score_tag: Optional[str] = Field(
        default=None,
        description="Rango de score exacto (ej. '130-140', '141-150', 'a.<=154').",
    )
    product: Optional[str] = Field(
        default=None,
        description="Producto exacto sin acentos (ej. 'Clasica', 'Oro', 'Platinum', 'Teleton').",
    )
    vintage: Optional[int] = Field(
        default=None,
        description="Mes de apertura en formato AAAAMM (ej. 202401).",
    )


class SqlSelectInput(BaseModel):
    """Esquema para consultas SQL de solo lectura generadas por el agente."""

    query_sql: str = Field(
        description="Consulta SELECT o WITH en dialecto DuckDB sobre la vista `v_cubo_metricas`."
    )
    proposito: str = Field(
        description="Breve explicación de qué métrica o pregunta responde esta consulta."
    )


def _build_where_clause(
    channel: Optional[str] = None,
    age_tag: Optional[str] = None,
    score_tag: Optional[str] = None,
    product: Optional[str] = None,
    vintage: Optional[int] = None,
) -> tuple[str, list[Any]]:
    """Construye cláusula WHERE parametrizada y lista de argumentos."""
    clauses: list[str] = []
    params: list[Any] = []
    filters = [
        ("CHANNEL", channel),
        ("AGE_TAG", age_tag),
        ("SCORE_TAG", score_tag),
        ("PRODUCT", product),
        ("VINTAGE", vintage),
    ]
    for col, val in filters:
        if val is not None and str(val).strip() != "":
            clauses.append(f"{col} = ?")
            params.append(val.strip() if isinstance(val, str) else val)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def _round_row(row: dict[str, Any]) -> dict[str, Any]:
    """Redondea floats a 2 decimales para legibilidad y consistencia JSON."""
    return {
        k: round(v, 2) if isinstance(v, float) else v
        for k, v in row.items()
    }


def validate_readonly_sql(query_sql: str) -> str:
    """Valida que el SQL sea exclusivamente SELECT/WITH sin DDL/DML ni múltiples sentencias."""
    cleaned = query_sql.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()

    if not cleaned:
        raise ValueError("La consulta SQL está vacía.")
    if ";" in cleaned:
        raise ValueError("No se permiten múltiples sentencias SQL separadas por ';'.")

    upper_start = cleaned.lstrip().upper()
    if not (upper_start.startswith("SELECT") or upper_start.startswith("WITH")):
        raise ValueError("Solo se permiten consultas de lectura que inicien con SELECT o WITH.")

    forbidden = _FORBIDDEN_SQL_PATTERN.search(cleaned)
    if forbidden:
        raise ValueError(
            f"Palabra clave prohibida detectada en SQL: '{forbidden.group(1)}'. "
            "Solo se permiten consultas SELECT de lectura."
        )

    if not re.search(r"\bLIMIT\b", cleaned, re.IGNORECASE):
        cleaned = f"{cleaned}\nLIMIT 100"

    return cleaned


@tool(args_schema=FiltroCuboInput)
def obtener_resumen_portafolio(
    channel: Optional[str] = None,
    age_tag: Optional[str] = None,
    score_tag: Optional[str] = None,
    product: Optional[str] = None,
    vintage: Optional[int] = None,
) -> str:
    """Calcula el resumen financiero y de riesgo agregado para el segmento filtrado en DuckDB."""
    where_sql, params = _build_where_clause(channel, age_tag, score_tag, product, vintage)
    mob0_where = f"{where_sql} AND MOB = 0" if where_sql else "WHERE MOB = 0"

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        init_row = con.execute(
            f"""
            SELECT
                COUNT(DISTINCT COHORT_ID) AS cohortes_unicas,
                COALESCE(SUM(ACCOUNTS), 0) AS cuentas_iniciales_mob0,
                COALESCE(SUM(CREDITLINESAMTS), 0) AS lineas_credito_iniciales_mob0
            FROM v_cubo_metricas
            {mob0_where}
            """,
            params,
        ).fetchone()

        agg_row = con.execute(
            f"""
            SELECT
                COUNT(*) AS filas_cubo,
                MIN(MOB) AS min_mob,
                MAX(MOB) AS max_mob,
                COALESCE(AVG(ENRAMTS), 0.0) AS saldo_promedio_enr,
                COALESCE(SUM(ENRAMTS), 0.0) AS saldo_acumulado_enr,
                COALESCE(SUM(REVENUE), 0.0) AS ingresos_acumulados,
                COALESCE(SUM(GCLAMTS), 0.0) AS perdida_bruta_gcl,
                COALESCE(SUM(RECOVERYAMTS), 0.0) AS recuperacion_cobranza,
                COALESCE(SUM(NCLAMTS), 0.0) AS perdida_neta_ncl,
                COALESCE(SUM(EXPENSES_TOTAL), 0.0) AS gastos_totales,
                COALESCE(SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL), 0.0) AS utilidad_neta,
                (SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS over30_rate_pct,
                (SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS ncl_rate_pct,
                (SUM(RECOVERYAMTS) / NULLIF(SUM(GCLAMTS), 0)) * 100.0 AS recovery_rate_pct,
                (SUM(REVENUE) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS yield_rate_pct,
                ((SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL)) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS net_roa_pct
            FROM v_cubo_metricas
            {where_sql}
            """,
            params,
        ).fetchone()
    finally:
        con.close()

    result = _round_row(
        {
            "filtros": {
                "channel": channel,
                "age_tag": age_tag,
                "score_tag": score_tag,
                "product": product,
                "vintage": vintage,
            },
            "cohortes_unicas": init_row[0],
            "cuentas_iniciales_mob0": init_row[1],
            "lineas_credito_iniciales_mob0": init_row[2],
            "filas_cubo": agg_row[0],
            "min_mob": agg_row[1],
            "max_mob": agg_row[2],
            "saldo_promedio_enr": agg_row[3],
            "saldo_acumulado_enr": agg_row[4],
            "ingresos_acumulados": agg_row[5],
            "perdida_bruta_gcl": agg_row[6],
            "recuperacion_cobranza": agg_row[7],
            "perdida_neta_ncl": agg_row[8],
            "gastos_totales": agg_row[9],
            "utilidad_neta": agg_row[10],
            "over30_rate_pct": agg_row[11],
            "ncl_rate_pct": agg_row[12],
            "recovery_rate_pct": agg_row[13],
            "yield_rate_pct": agg_row[14],
            "net_roa_pct": agg_row[15],
        }
    )
    return json.dumps(result, ensure_ascii=False)


@tool(args_schema=FiltroCuboInput)
def obtener_curva_maduracion(
    channel: Optional[str] = None,
    age_tag: Optional[str] = None,
    score_tag: Optional[str] = None,
    product: Optional[str] = None,
    vintage: Optional[int] = None,
) -> str:
    """Devuelve la serie temporal por MOB (0 a 32) con tasas ponderadas de morosidad, pérdida y ROA."""
    where_sql, params = _build_where_clause(channel, age_tag, score_tag, product, vintage)

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        cursor = con.execute(
            f"""
            SELECT
                MOB,
                SUM(ACCOUNTS) AS accounts,
                SUM(ENRAMTS) AS enramts,
                (SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS over30_rate_pct,
                (SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS ncl_rate_pct,
                (SUM(REVENUE) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS yield_rate_pct,
                ((SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL)) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS net_roa_pct
            FROM v_cubo_metricas
            {where_sql}
            GROUP BY MOB
            ORDER BY MOB ASC
            """,
            params,
        )
        cols = [d[0].lower() for d in cursor.description]
        rows = [_round_row(dict(zip(cols, r))) for r in cursor.fetchall()]
    finally:
        con.close()

    return json.dumps(
        {
            "filtros": {
                "channel": channel,
                "age_tag": age_tag,
                "score_tag": score_tag,
                "product": product,
                "vintage": vintage,
            },
            "puntos_mob": len(rows),
            "curva": rows,
        },
        ensure_ascii=False,
    )


@tool(args_schema=SqlSelectInput)
def ejecutar_sql_select_seguro(query_sql: str, proposito: str) -> str:
    """Ejecuta una consulta SQL SELECT de solo lectura sobre `v_cubo_metricas` en DuckDB."""
    try:
        safe_sql = validate_readonly_sql(query_sql)
    except ValueError as exc:
        return json.dumps({"error": str(exc), "sql_rechazado": query_sql}, ensure_ascii=False)

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        cursor = con.execute(safe_sql)
        cols = [d[0] for d in cursor.description]
        rows = [_round_row(dict(zip(cols, r))) for r in cursor.fetchall()]
        return json.dumps(
            {
                "proposito": proposito,
                "sql_ejecutado": safe_sql,
                "total_filas": len(rows),
                "datos": rows,
            },
            ensure_ascii=False,
        )
    except duckdb.Error as exc:
        return json.dumps(
            {
                "error_duckdb": str(exc),
                "sql_intentado": safe_sql,
                "instruccion": "Corrige el nombre de columna o sintaxis SQL e inténtalo de nuevo.",
            },
            ensure_ascii=False,
        )
    finally:
        con.close()
