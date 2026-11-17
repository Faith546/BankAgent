"""Ingesta del CSV crudo en DuckDB con limpieza TRIM(), tabla `cubo` y vista `v_cubo_metricas`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from src.config import DUCKDB_DIR, DUCKDB_PATH, RAW_CSV_PATH


def init_db(csv_path: Path | None = None, db_path: Path | None = None) -> dict[str, Any]:
    """Crea o reconstruye la base DuckDB a partir del CSV crudo y devuelve métricas de auditoría."""
    src_csv = csv_path or RAW_CSV_PATH
    target_db = db_path or DUCKDB_PATH

    if not src_csv.exists():
        raise FileNotFoundError(f"No se encontró el archivo CSV fuente en: {src_csv}")

    DUCKDB_DIR.mkdir(parents=True, exist_ok=True)
    target_db.parent.mkdir(parents=True, exist_ok=True)

    csv_posix = src_csv.resolve().as_posix()

    con = duckdb.connect(str(target_db))
    try:
        con.execute(
            f"""
            CREATE OR REPLACE TABLE cubo AS
            SELECT
                CONCAT_WS(
                    ' | ',
                    CAST(VINTAGE AS VARCHAR),
                    TRIM(CAST(STRATEGY AS VARCHAR)),
                    TRIM(CAST(STRATEGY_SEGMENT AS VARCHAR)),
                    TRIM(CAST(PRODUCT AS VARCHAR)),
                    TRIM(CAST(CHANNEL AS VARCHAR)),
                    TRIM(CAST(AGE_TAG AS VARCHAR)),
                    TRIM(CAST(SCORE_TAG AS VARCHAR))
                ) AS COHORT_ID,
                CAST(VINTAGE AS INTEGER) AS VINTAGE,
                TRIM(CAST(STRATEGY AS VARCHAR)) AS STRATEGY,
                TRIM(CAST(STRATEGY_SEGMENT AS VARCHAR)) AS STRATEGY_SEGMENT,
                TRIM(CAST(PRODUCT AS VARCHAR)) AS PRODUCT,
                TRIM(CAST(CHANNEL AS VARCHAR)) AS CHANNEL,
                TRIM(CAST(AGE_TAG AS VARCHAR)) AS AGE_TAG,
                TRIM(CAST(SCORE_TAG AS VARCHAR)) AS SCORE_TAG,
                CAST(MOB AS INTEGER) AS MOB,
                CAST(ACCOUNTS AS BIGINT) AS ACCOUNTS,
                CAST(CREDITLINESAMTS AS BIGINT) AS CREDITLINESAMTS,
                CAST(ENRACCTS AS BIGINT) AS ENRACCTS,
                CAST(OVER30ACCTS AS BIGINT) AS OVER30ACCTS,
                CAST(OVER30AMTS AS DOUBLE) AS OVER30AMTS,
                CAST(GCLAMTS AS DOUBLE) AS GCLAMTS,
                CAST(NCLAMTS AS DOUBLE) AS NCLAMTS,
                CAST(RECOVERYAMTS AS DOUBLE) AS RECOVERYAMTS,
                CAST(ENRAMTS AS DOUBLE) AS ENRAMTS,
                CAST(REVENUE AS DOUBLE) AS REVENUE,
                CAST(EXPENSES_ACQ AS DOUBLE) AS EXPENSES_ACQ,
                CAST(EXPENSES_ECM_VAR AS DOUBLE) AS EXPENSES_ECM_VAR,
                CAST(EXPENSES_ECM_FIX AS DOUBLE) AS EXPENSES_ECM_FIX,
                CAST(EXPENSES_TOTAL AS DOUBLE) AS EXPENSES_TOTAL
            FROM read_csv_auto('{csv_posix}', header=True)
            """
        )

        con.execute(
            """
            CREATE OR REPLACE VIEW v_cubo_metricas AS
            SELECT
                *,
                (OVER30AMTS / NULLIF(ENRAMTS, 0)) * 100.0 AS OVER30_RATE_PCT,
                (NCLAMTS / NULLIF(ENRAMTS, 0)) * 100.0 AS NCL_RATE_PCT,
                (RECOVERYAMTS / NULLIF(GCLAMTS, 0)) * 100.0 AS RECOVERY_RATE_PCT,
                (REVENUE / NULLIF(ENRAMTS, 0)) * 100.0 AS YIELD_RATE_PCT,
                (REVENUE - NCLAMTS - EXPENSES_TOTAL) AS NET_PROFIT,
                ((REVENUE - NCLAMTS - EXPENSES_TOTAL) / NULLIF(ENRAMTS, 0)) * 100.0 AS NET_ROA_PCT
            FROM cubo
            """
        )

        row = con.execute(
            """
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT COHORT_ID) AS unique_cohorts,
                MIN(VINTAGE) AS min_vintage,
                MAX(VINTAGE) AS max_vintage,
                MIN(MOB) AS min_mob,
                MAX(MOB) AS max_mob,
                SUM(REVENUE) AS sum_revenue,
                SUM(GCLAMTS) AS sum_gcl,
                SUM(RECOVERYAMTS) AS sum_recovery,
                SUM(NCLAMTS) AS sum_ncl,
                SUM(EXPENSES_TOTAL) AS sum_expenses_total,
                SUM(ENRAMTS) AS sum_enramts
            FROM cubo
            """
        ).fetchone()
    finally:
        con.close()

    return {
        "csv_path": str(src_csv),
        "db_path": str(target_db),
        "total_rows": row[0],
        "unique_cohorts": row[1],
        "min_vintage": row[2],
        "max_vintage": row[3],
        "min_mob": row[4],
        "max_mob": row[5],
        "sum_revenue": row[6],
        "sum_gcl": row[7],
        "sum_recovery": row[8],
        "sum_ncl": row[9],
        "sum_expenses_total": row[10],
        "sum_enramts": row[11],
    }


def print_audit_table(audit: dict[str, Any]) -> None:
    """Imprime en consola la tabla de auditoría de la ingesta en DuckDB."""
    print("=" * 68)
    print("AUDITORÍA DE INGESTA DUCKDB — CUBO BANAMEX")
    print("=" * 68)
    print(f"Archivo CSV fuente : {audit['csv_path']}")
    print(f"Base DuckDB        : {audit['db_path']}")
    print(f"Total de filas     : {audit['total_rows']:,}")
    print(f"Cohortes únicas    : {audit['unique_cohorts']:,}")
    print(f"Rango VINTAGE      : {audit['min_vintage']} .. {audit['max_vintage']}")
    print(f"Rango MOB          : {audit['min_mob']} .. {audit['max_mob']}")
    print("-" * 68)
    print(f"SUM(REVENUE)       : ${audit['sum_revenue']:,.2f}")
    print(f"SUM(GCLAMTS)       : ${audit['sum_gcl']:,.2f}")
    print(f"SUM(RECOVERYAMTS)  : ${audit['sum_recovery']:,.2f}")
    print(f"SUM(NCLAMTS)       : ${audit['sum_ncl']:,.2f}")
    print(f"SUM(EXPENSES_TOTAL): ${audit['sum_expenses_total']:,.2f}")
    print(f"SUM(ENRAMTS)       : ${audit['sum_enramts']:,.2f}")
    print("=" * 68)


if __name__ == "__main__":
    summary = init_db()
    print_audit_table(summary)

