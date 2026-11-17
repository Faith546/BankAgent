"""Pruebas unitarias de las Skills, Guardrails y compilación de LangGraph (Etapa 2)."""

from __future__ import annotations

import json
import shutil

from src.agent.guardrails import verify_response_numbers
from src.agent.graph import build_agent_graph
from src.config import CASES_DIR
from src.skills.cubo_sql_tools import (
    ejecutar_sql_select_seguro,
    obtener_curva_maduracion,
    obtener_resumen_portafolio,
    validate_readonly_sql,
)
from src.skills.report_tools import compilar_entregables_ejecutivos
from src.skills.viz_tools import generar_grafica_portafolio


def test_validate_readonly_sql_blocks_ddl_dml() -> None:
    """Verifica que el validador rechace DDL/DML y múltiples sentencias."""
    for bad_sql in [
        "DROP TABLE cubo",
        "DELETE FROM cubo WHERE MOB = 0",
        "SELECT * FROM cubo; DROP TABLE cubo;",
        "UPDATE cubo SET ACCOUNTS = 0",
    ]:
        try:
            validate_readonly_sql(bad_sql)
            assert False, f"Debió rechazar: {bad_sql}"
        except ValueError:
            pass

    safe = validate_readonly_sql("SELECT CHANNEL, COUNT(*) FROM v_cubo_metricas GROUP BY 1")
    assert "LIMIT 100" in safe


def test_cubo_sql_tools_return_valid_json() -> None:
    """Verifica las 3 herramientas DuckDB contra la base real."""
    res_str = obtener_resumen_portafolio.invoke({"channel": "Aeropuerto", "product": "Clasica"})
    res = json.loads(res_str)
    assert res["cuentas_iniciales_mob0"] > 0
    assert res["ncl_rate_pct"] is not None

    curva_str = obtener_curva_maduracion.invoke({"channel": "Branch"})
    curva = json.loads(curva_str)
    assert curva["puntos_mob"] > 0

    sql_str = ejecutar_sql_select_seguro.invoke(
        {
            "query_sql": "SELECT CHANNEL, COUNT(DISTINCT COHORT_ID) AS n FROM v_cubo_metricas GROUP BY 1",
            "proposito": "Conteo de cohortes por canal",
        }
    )
    sql_res = json.loads(sql_str)
    assert sql_res["total_filas"] == 12


def test_viz_and_report_tools_generate_outputs() -> None:
    """Verifica generación de gráfica Plotly/PNG y compilación DOCX/PPTX."""
    test_case = "CASO-TEST-0001"
    try:
        viz_str = generar_grafica_portafolio.invoke(
            {
                "tipo_grafica": "curva_maduracion_s",
                "case_id": test_case,
                "filtros": {"channel": "Aeropuerto"},
                "export_png": False,
            }
        )
        viz = json.loads(viz_str)
        assert viz["ruta_plotly_json"].endswith(".json")

        rep_str = compilar_entregables_ejecutivos.invoke(
            {
                "case_id": test_case,
                "titulo": "Análisis Prueba Aeropuerto",
                "hallazgos": ["Pérdida neta controlada en segmento Clasica."],
                "dictamen": "Mantener vigilancia preventiva.",
                "rutas_graficas": [viz["ruta_png"]],
            }
        )
        rep = json.loads(rep_str)
        assert rep["ruta_docx"].endswith(".docx")
        assert rep["ruta_pptx"].endswith(".pptx")
    finally:
        case_dir = CASES_DIR / test_case
        if case_dir.exists():
            shutil.rmtree(case_dir, ignore_errors=True)


def test_guardrail_verifies_numbers() -> None:
    """Verifica que el guardrail detecte cifras inventadas y acepte cifras reales."""
    evidence = ['{"ncl_rate_pct": 18.42, "cuentas_iniciales_mob0": 1250}']
    ok, issues = verify_response_numbers(
        "El segmento tiene 1,250 cuentas iniciales y una pérdida neta de 18.42%.",
        evidence,
    )
    assert ok is True
    assert issues == []

    ok_bad, issues_bad = verify_response_numbers(
        "El segmento tiene 99.99% de pérdida neta y 5,432 cuentas.",
        evidence,
    )
    assert ok_bad is False
    assert "99.99" in issues_bad


def test_langgraph_compiles() -> None:
    """Verifica que el grafo de LangGraph compile sin errores con SqliteSaver."""
    graph = build_agent_graph(with_interrupt=True)
    assert graph is not None
