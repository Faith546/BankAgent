"""Pruebas unitarias de las Skills, Guardrails, contratos y Golden Dataset."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import duckdb
from langchain_core.messages import AIMessage

from src.agent.graph import _tools_node, build_agent_graph, make_initial_state
from src.agent.guardrails import verify_response_numbers
from src.config import CASES_DIR, DUCKDB_PATH
from src.skills.cubo_sql_tools import (
    ejecutar_sql_select_seguro,
    obtener_curva_maduracion,
    obtener_resumen_portafolio,
    validate_readonly_sql,
)
from src.skills.report_tools import compilar_entregables_ejecutivos
from src.skills.viz_tools import generar_grafica_portafolio

GOLDEN_PATH = Path(__file__).resolve().parent / "golden_dataset.json"


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


def test_filter_validation_returns_available_options_as_data() -> None:
    """Verifica que filtros inválidos devuelvan error estructurado con `disponibles`."""
    bad_prod = json.loads(obtener_resumen_portafolio.invoke({"product": "Clásica"}))
    assert "error" in bad_prod
    assert "Clasica" in bad_prod["disponibles"]

    bad_chan = json.loads(obtener_curva_maduracion.invoke({"channel": "Sucursal"}))
    assert "error" in bad_chan
    assert "Branch" in bad_chan["disponibles"]


def test_cubo_sql_tools_return_valid_json() -> None:
    """Verifica las 3 herramientas DuckDB contra la base real."""
    res_str = obtener_resumen_portafolio.invoke({"channel": "Aeropuerto", "product": "Clasica"})
    res = json.loads(res_str)
    assert res["cuentas_iniciales_mob0"] == 28152
    assert res["ncl_rate_pct"] == 8.56

    curva_str = obtener_curva_maduracion.invoke({"channel": "Branch"})
    curva = json.loads(curva_str)
    assert curva["puntos_mob"] > 0

    sql_str = ejecutar_sql_select_seguro.invoke(
        {
            "query_sql": (
                "SELECT CHANNEL, COUNT(DISTINCT COHORT_ID) AS n FROM v_cubo_metricas GROUP BY 1"
            ),
            "proposito": "Conteo de cohortes por canal",
        }
    )
    sql_res = json.loads(sql_str)
    assert sql_res["total_filas"] == 12


def test_tools_node_whitelist_and_antirepetition() -> None:
    """Verifica Guardrail 1 (lista blanca) y Guardrail 3 (antirrepetición) en _tools_node."""
    # 1) Tool inventada -> bloqueada por lista blanca
    state_fake = make_initial_state("test")
    state_fake["messages"] = [
        AIMessage(
            content="",
            tool_calls=[{"name": "borrar_base_datos", "args": {}, "id": "c1"}],
        )
    ]
    out_fake = _tools_node(state_fake)
    payload_fake = json.loads(out_fake["messages"][0].content)
    assert "error" in payload_fake
    assert "obtener_resumen_portafolio" in payload_fake["disponibles"]

    # 2) Llamada repetida exacta -> bloqueada por antirrepetición
    args = {"channel": "Aeropuerto", "product": "Clasica"}
    state_rep = make_initial_state("test")
    state_rep["messages"] = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "obtener_resumen_portafolio", "args": args, "id": "c2"},
                {"name": "obtener_resumen_portafolio", "args": args, "id": "c3"},
            ],
        )
    ]
    out_rep = _tools_node(state_rep)
    first_payload = json.loads(out_rep["messages"][0].content)
    second_payload = json.loads(out_rep["messages"][1].content)
    assert first_payload["cuentas_iniciales_mob0"] == 28152
    assert "already executed" in second_payload["error"]


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
                "hallazgos": [
                    "Cuentas iniciales (MOB 0): 28,152",
                    "Severidad NCL / ENR: 8.56%",
                ],
                "dictamen": "Mantener vigilancia preventiva.",
                "rutas_graficas": [viz["ruta_png"]],
                "estado_riesgo": "EN APETITO",
                "kpis": [
                    {
                        "label": "Cuentas MOB 0",
                        "value": "28,152",
                        "delta": "Base inicial",
                        "status": "blue",
                    },
                    {
                        "label": "NCL / ENR",
                        "value": "8.56%",
                        "delta": "-6.44 pp vs 15%",
                        "status": "green",
                    },
                    {
                        "label": "Over30 / ENR",
                        "value": "20.73%",
                        "delta": "-4.27 pp vs 25%",
                        "status": "green",
                    },
                    {
                        "label": "Utilidad Neta",
                        "value": "-$261.4M",
                        "delta": "Revisar margen",
                        "status": "orange",
                    },
                ],
                "tabla_metricas": [
                    ["NCL / ENR", "8.56%", "Límite 15.0%"],
                    ["Over30 / ENR", "20.73%", "Límite 25.0%"],
                ],
            }
        )
        rep = json.loads(rep_str)
        assert rep["ruta_docx"].endswith(".docx")
        assert rep["ruta_pptx"].endswith(".pptx")
        assert rep["slides_generadas"] == 5
        assert Path(rep["ruta_docx"]).exists()
        assert Path(rep["ruta_pptx"]).exists()
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


def test_golden_dataset_matches_duckdb() -> None:
    """Verifica que los 10 casos del Golden Dataset coincidan exactamente con DuckDB."""
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert len(cases) == 10

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        for case in cases:
            row = con.execute(case["sql_verificacion"]).fetchone()
            assert row is not None
            for expected, actual in zip(case["cifras_esperadas"], row):
                assert abs(float(expected) - float(actual)) < 1e-2, (
                    f"{case['id']}: esperado {expected}, DuckDB devolvió {actual}"
                )
    finally:
        con.close()


def test_langgraph_compiles() -> None:
    """Verifica que el grafo de LangGraph compile sin errores con SqliteSaver."""
    graph = build_agent_graph(with_interrupt=True)
    assert graph is not None
