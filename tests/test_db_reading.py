"""Pruebas unitarias de lectura del cubo en DuckDB e identidades contables."""

from __future__ import annotations

import duckdb
import pytest

from src.config import DUCKDB_PATH, TEXT_COLUMNS
from src.data.dictionary_loader import load_dictionary
from src.data.init_db import init_db


@pytest.fixture(scope="module")
def db_con():
    """Asegura que la base DuckDB exista y la abre en modo solo lectura."""
    if not DUCKDB_PATH.exists():
        init_db()
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield con
    con.close()


def test_cubo_and_view_exist_with_rows(db_con: duckdb.DuckDBPyConnection) -> None:
    """Verifica que la tabla `cubo` y la vista `v_cubo_metricas` tengan registros."""
    cubo_count = db_con.execute("SELECT COUNT(*) FROM cubo").fetchone()[0]
    view_count = db_con.execute("SELECT COUNT(*) FROM v_cubo_metricas").fetchone()[0]
    assert cubo_count > 0
    assert view_count == cubo_count


def test_text_columns_are_trimmed(db_con: duckdb.DuckDBPyConnection) -> None:
    """Verifica que ninguna columna de texto tenga espacios al inicio o al final."""
    for col in TEXT_COLUMNS:
        dirty_rows = db_con.execute(
            f"SELECT COUNT(*) FROM cubo WHERE {col} <> TRIM({col})"
        ).fetchone()[0]
        assert dirty_rows == 0, f"La columna {col} tiene {dirty_rows} filas sin TRIM()"


def test_accounting_identity_ncl(db_con: duckdb.DuckDBPyConnection) -> None:
    """Verifica la identidad contable: NCLAMTS = GCLAMTS - RECOVERYAMTS."""
    max_diff = db_con.execute(
        "SELECT MAX(ABS(NCLAMTS - (GCLAMTS - RECOVERYAMTS))) FROM cubo"
    ).fetchone()[0]
    assert max_diff < 1e-4, f"Diferencia máxima en NCLAMTS: {max_diff}"


def test_accounting_identity_expenses(db_con: duckdb.DuckDBPyConnection) -> None:
    """Verifica la identidad contable: EXPENSES_TOTAL = ACQ + ECM_VAR + ECM_FIX."""
    max_diff = db_con.execute(
        """
        SELECT MAX(
            ABS(EXPENSES_TOTAL - (EXPENSES_ACQ + EXPENSES_ECM_VAR + EXPENSES_ECM_FIX))
        )
        FROM cubo
        """
    ).fetchone()[0]
    assert max_diff < 1e-4, f"Diferencia máxima en EXPENSES_TOTAL: {max_diff}"


def test_expenses_acq_zero_after_mob_zero(db_con: duckdb.DuckDBPyConnection) -> None:
    """Verifica la regla estricta: EXPENSES_ACQ debe ser 0.0 cuando MOB > 0."""
    violations = db_con.execute(
        "SELECT COUNT(*) FROM cubo WHERE MOB > 0 AND ABS(EXPENSES_ACQ) > 1e-6"
    ).fetchone()[0]
    assert violations == 0, f"Se encontraron {violations} filas con EXPENSES_ACQ > 0 en MOB > 0"


def test_dictionary_loader_has_22_variables() -> None:
    """Verifica que el diccionario Excel cargue las 22 variables esperadas."""
    variables = load_dictionary()
    assert len(variables) == 22
    names = {v["variable"] for v in variables}
    assert {"VINTAGE", "MOB", "COHORT_ID"} - {"COHORT_ID"} <= names
    assert {"NCLAMTS", "GCLAMTS", "RECOVERYAMTS", "ENRAMTS", "REVENUE"} <= names
