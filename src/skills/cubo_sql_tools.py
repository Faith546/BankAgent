"""Skill 1: Herramientas parametrizadas y Text-to-SQL seguro sobre DuckDB (read_only=True)."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import duckdb
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.config import (
    DUCKDB_PATH,
    VALID_AGE_TAGS,
    VALID_CHANNELS,
    VALID_PRODUCTS,
    VALID_SCORE_TAGS,
    VINTAGE_MAX,
    VINTAGE_MIN,
)

_FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|COPY|ATTACH|DETACH|"
    r"PRAGMA|CALL|EXPORT|IMPORT|REPLACE|TRUNCATE|MERGE)\b",
    re.IGNORECASE,
)


class FiltroCuboInput(BaseModel):
    """Optional exact filters for querying Banamex credit card cohorts."""

    channel: Optional[str] = Field(
        default=None,
        description="Exact channel (e.g. 'Aeropuerto', 'Branch', 'F2F', 'Internet', 'TMK').",
    )
    age_tag: Optional[str] = Field(
        default=None,
        description="Exact age bracket ('01| Young < 25', '02| Young 25-30', '03| Mature >30').",
    )
    score_tag: Optional[str] = Field(
        default=None,
        description="Exact score bracket (e.g. '<130', '130-140', '141-150', 'a.<=154').",
    )
    product: Optional[str] = Field(
        default=None,
        description="Exact product without accents (e.g. 'Clasica', 'Oro', 'Platinum').",
    )
    vintage: Optional[int] = Field(
        default=None,
        description="Booking month in YYYYMM integer format (202401 to 202609).",
    )


class SqlSelectInput(BaseModel):
    """Schema for read-only DuckDB SELECT queries written by the agent."""

    query_sql: str = Field(
        description="Read-only DuckDB SELECT or WITH query targeting view `v_cubo_metricas`."
    )
    proposito: str = Field(
        description="Short explanation of what business metric or question this query answers."
    )


def validate_cube_filters(
    channel: Optional[str] = None,
    age_tag: Optional[str] = None,
    score_tag: Optional[str] = None,
    product: Optional[str] = None,
    vintage: Optional[int] = None,
) -> dict[str, Any] | None:
    """Validate filter values before querying DuckDB; return structured error with options."""
    checks = [
        ("channel", channel, VALID_CHANNELS),
        ("age_tag", age_tag, VALID_AGE_TAGS),
        ("score_tag", score_tag, VALID_SCORE_TAGS),
        ("product", product, VALID_PRODUCTS),
    ]
    for name, val, allowed in checks:
        if val is not None and str(val).strip() != "":
            clean = str(val).strip()
            if clean not in allowed:
                return {
                    "error": (
                        f"Invalid {name} value '{clean}'. Use an exact value from `disponibles`."
                    ),
                    "parametro": name,
                    "valor_recibido": clean,
                    "disponibles": list(allowed),
                }

    if vintage is not None:
        if not isinstance(vintage, int) or vintage < VINTAGE_MIN or vintage > VINTAGE_MAX:
            return {
                "error": (
                    f"Invalid vintage '{vintage}'. "
                    f"Must be an integer between {VINTAGE_MIN} and {VINTAGE_MAX}."
                ),
                "parametro": "vintage",
                "valor_recibido": vintage,
                "rango_valido": [VINTAGE_MIN, VINTAGE_MAX],
            }

    return None


def _build_where_clause(
    channel: Optional[str] = None,
    age_tag: Optional[str] = None,
    score_tag: Optional[str] = None,
    product: Optional[str] = None,
    vintage: Optional[int] = None,
) -> tuple[str, list[Any]]:
    """Builds parameterized WHERE clause and argument list."""
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
    """Rounds floats to 2 decimal places for JSON consistency."""
    return {k: round(v, 2) if isinstance(v, float) else v for k, v in row.items()}


def validate_readonly_sql(query_sql: str) -> str:
    """Validates that SQL is strictly read-only SELECT/WITH with no DDL/DML or multi-statements."""
    cleaned = query_sql.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()

    if not cleaned:
        raise ValueError("SQL query is empty.")
    if ";" in cleaned:
        raise ValueError("Multiple SQL statements separated by ';' are not allowed.")

    upper_start = cleaned.lstrip().upper()
    if not (upper_start.startswith("SELECT") or upper_start.startswith("WITH")):
        raise ValueError("Only read-only queries starting with SELECT or WITH are allowed.")

    forbidden = _FORBIDDEN_SQL_PATTERN.search(cleaned)
    if forbidden:
        raise ValueError(
            f"Forbidden SQL keyword detected: '{forbidden.group(1)}'. "
            "Only read-only SELECT queries are permitted."
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
    """Compute aggregated KPIs (MOB 0 accounts, NCL%, Over30%, net profit, ROA%) from DuckDB."""
    err = validate_cube_filters(channel, age_tag, score_tag, product, vintage)
    if err is not None:
        return json.dumps(err, ensure_ascii=False)

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
                (
                    (SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL))
                    / NULLIF(SUM(ENRAMTS), 0)
                ) * 100.0 AS net_roa_pct
            FROM v_cubo_metricas
            {where_sql}
            """,
            params,
        ).fetchone()
    finally:
        con.close()

    if agg_row[0] == 0:
        return json.dumps(
            {
                "aviso": "No rows matched the combined filters in the cube.",
                "filtros": {
                    "channel": channel,
                    "age_tag": age_tag,
                    "score_tag": score_tag,
                    "product": product,
                    "vintage": vintage,
                },
            },
            ensure_ascii=False,
        )

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
    """Return MOB (0..32) maturation series with weighted Over30%, NCL%, Yield%, and Net ROA%."""
    err = validate_cube_filters(channel, age_tag, score_tag, product, vintage)
    if err is not None:
        return json.dumps(err, ensure_ascii=False)

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
                (
                    (SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL))
                    / NULLIF(SUM(ENRAMTS), 0)
                ) * 100.0 AS net_roa_pct
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
    """Execute a read-only DuckDB SELECT/WITH query on `v_cubo_metricas` for ad-hoc analysis."""
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
                "instruccion": "Fix the column name or SQL syntax and retry once.",
            },
            ensure_ascii=False,
        )
    finally:
        con.close()
