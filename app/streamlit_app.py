"""Consola Híbrida de 3 Paneles en Streamlit — Asistente de Portafolio Banamex (MVP)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import streamlit as st
from langchain_core.messages import HumanMessage

# Asegurar que la raíz del proyecto esté en sys.path al ejecutar `streamlit run app/streamlit_app.py`
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.graph import build_agent_graph
from src.config import DUCKDB_PATH, MAX_NCL_RATE_PCT, MAX_OVER30_RATE_PCT, MIN_MATURE_MOB, OLLAMA_MODEL
from src.skills.cubo_sql_tools import obtener_resumen_portafolio
from src.skills.git_governance import (
    commit_ai_draft,
    commit_human_approval,
    get_case_diff,
    save_case_artifacts,
)
from src.skills.report_tools import compilar_entregables_ejecutivos
from src.skills.viz_tools import ChartType, build_plotly_figure, generar_grafica_portafolio

CHART_LABELS: dict[ChartType, str] = {
    "curva_maduracion_s": "Curva S de Maduración (Over30 y NCL)",
    "curva_j_roa": "Curva J de Rentabilidad (ROA Neto por Score)",
    "puente_pnl_waterfall": "Puente P&L (Waterfall)",
    "heatmap_severidad": "Mapa de Calor de Severidad (NCL/ENR %)",
    "matriz_cuadrantes": "Matriz de Cuadrantes (MOB >= 12)",
    "embudo_cobranza": "Embudo de Morosidad y Cobranza",
}


@st.cache_data(ttl=300)
def load_parametric_alerts(limit: int = 20) -> list[dict[str, Any]]:
    """Consulta segmentos maduros (MOB >= 6) que exceden umbrales de apetito de riesgo."""
    if not DUCKDB_PATH.exists():
        return []

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT
                CHANNEL,
                AGE_TAG,
                SCORE_TAG,
                COUNT(DISTINCT COHORT_ID) AS cohortes,
                ROUND((SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0, 2) AS ncl_rate_pct,
                ROUND((SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0, 2) AS over30_rate_pct,
                ROUND(SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL), 2) AS utilidad_neta,
                ROUND(SUM(ENRAMTS), 2) AS enr_total
            FROM v_cubo_metricas
            WHERE MOB >= {MIN_MATURE_MOB}
            GROUP BY CHANNEL, AGE_TAG, SCORE_TAG
            HAVING (SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 > {MAX_NCL_RATE_PCT}
                OR (SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 > {MAX_OVER30_RATE_PCT}
            ORDER BY ncl_rate_pct DESC, enr_total DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
    finally:
        con.close()

    alerts: list[dict[str, Any]] = []
    for idx, r in enumerate(rows, start=1):
        alerts.append(
            {
                "case_id": f"CASO-2026-{idx:04d}",
                "channel": r[0],
                "age_tag": r[1],
                "score_tag": r[2],
                "cohortes": r[3],
                "ncl_rate_pct": r[4],
                "over30_rate_pct": r[5],
                "utilidad_neta": r[6],
                "enr_total": r[7],
            }
        )
    return alerts


def _init_session_state() -> None:
    defaults: dict[str, Any] = {
        "selected_idx": 0,
        "draft_dictamen": "",
        "sql_queries": [],
        "evidence": [],
        "guardrail_issues": [],
        "chat_history": [],
        "last_outputs": {},
        "git_diff_text": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _run_agent_for_case(case: dict[str, Any]) -> None:
    prompt = (
        f"Analiza el segmento CHANNEL='{case['channel']}', AGE_TAG='{case['age_tag']}', "
        f"SCORE_TAG='{case['score_tag']}'. Obtén su resumen de portafolio, revisa su curva de "
        "maduración, consulta el manual de apetito de riesgo y redacta un dictamen ejecutivo "
        "con recomendación concreta (Expandir, Restringir Línea o Suspender Originación)."
    )
    graph = build_agent_graph(with_interrupt=True)
    config = {"configurable": {"thread_id": f"case-{case['case_id']}"}}
    initial_state = {
        "messages": [HumanMessage(content=prompt)],
        "case_id": case["case_id"],
        "sql_queries": [],
        "evidence": [],
        "draft_dictamen": "",
        "guardrail_passed": True,
        "guardrail_issues": [],
        "retry_count": 0,
    }
    result = graph.invoke(initial_state, config=config)

    draft = result.get("draft_dictamen", "")
    queries = result.get("sql_queries", [])
    evidence = result.get("evidence", [])
    issues = result.get("guardrail_issues", [])

    st.session_state["draft_dictamen"] = draft
    st.session_state["sql_queries"] = queries
    st.session_state["evidence"] = evidence
    st.session_state["guardrail_issues"] = issues

    parsed_ev = []
    for item in evidence:
        try:
            parsed_ev.append(json.loads(item) if isinstance(item, str) else item)
        except json.JSONDecodeError:
            parsed_ev.append({"raw": str(item)})

    save_case_artifacts(case["case_id"], queries, parsed_ev, draft)
    try:
        commit_ai_draft(case["case_id"], OLLAMA_MODEL)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Borrador guardado, pero no se pudo hacer commit Git automático: {exc}")


def main() -> None:
    st.set_page_config(
        page_title="Banamex Portfolio Agent — Consola Híbrida",
        page_icon="🏦",
        layout="wide",
    )
    _init_session_state()

    st.title("🏦 Asistente Agéntico de Portafolio — Banamex (MVP)")
    st.caption(
        f"Motor: DuckDB (solo lectura) + Ollama (`{OLLAMA_MODEL}`) + LangGraph + ChromaDB | "
        f"Umbrales: NCL > {MAX_NCL_RATE_PCT}% | Over30 > {MAX_OVER30_RATE_PCT}% (MOB >= {MIN_MATURE_MOB})"
    )

    if not DUCKDB_PATH.exists():
        st.error(
            f"No se encontró la base DuckDB en `{DUCKDB_PATH}`. "
            "Ejecuta primero `uv run python -m src.data.init_db`."
        )
        return

    alerts = load_parametric_alerts()
    if not alerts:
        st.warning("No se encontraron segmentos fuera de apetito en DuckDB.")
        return

    col_left, col_center, col_right = st.columns([1.05, 2.2, 1.35], gap="medium")

    # ------------------------------------------------------------------
    # PANEL IZQUIERDO: Selector de Casos / Alertas Paramétricas
    # ------------------------------------------------------------------
    with col_left:
        st.subheader("🚨 Alertas del Cubo")
        st.caption(f"{len(alerts)} segmentos fuera de umbral (MOB ≥ {MIN_MATURE_MOB})")

        options = [
            f"{a['case_id']} | {a['channel']} | {a['score_tag']} (NCL {a['ncl_rate_pct']}%)"
            for a in alerts
        ]
        selected_idx = st.radio(
            "Selecciona un caso para investigar:",
            options=range(len(options)),
            format_func=lambda i: options[i],
            index=min(st.session_state["selected_idx"], len(options) - 1),
        )
        if selected_idx != st.session_state["selected_idx"]:
            st.session_state["selected_idx"] = selected_idx
            st.session_state["draft_dictamen"] = ""
            st.session_state["sql_queries"] = []
            st.session_state["guardrail_issues"] = []
            st.session_state["git_diff_text"] = ""

        case = alerts[selected_idx]
        st.markdown("---")
        st.markdown(
            f"**Caso:** `{case['case_id']}`  \n"
            f"**Canal:** `{case['channel']}`  \n"
            f"**Edad:** `{case['age_tag']}`  \n"
            f"**Score:** `{case['score_tag']}`  \n"
            f"**Cohortes:** `{case['cohortes']}`"
        )

    # ------------------------------------------------------------------
    # PANEL CENTRAL: Evidencia, Gráficas, Dictamen Editable y Gobernanza
    # ------------------------------------------------------------------
    with col_center:
        st.subheader(f"📊 Evidencia del Caso — {case['case_id']}")

        resumen_json = obtener_resumen_portafolio.invoke(
            {
                "channel": case["channel"],
                "age_tag": case["age_tag"],
                "score_tag": case["score_tag"],
            }
        )
        resumen = json.loads(resumen_json)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Cuentas (MOB 0)", f"{resumen['cuentas_iniciales_mob0']:,}")
        m2.metric("NCL / ENR", f"{resumen['ncl_rate_pct']}%")
        m3.metric("Over30 / ENR", f"{resumen['over30_rate_pct']}%")
        m4.metric("Utilidad Neta", f"${resumen['utilidad_neta']:,.0f}")

        if st.button("🤖 Analizar Caso con Agente IA (LangGraph)", use_container_width=True):
            with st.spinner(f"Consultando DuckDB, políticas RAG y {OLLAMA_MODEL}..."):
                try:
                    _run_agent_for_case(case)
                    st.success("Borrador generado por el agente (pausado para revisión humana).")
                except Exception as exc:  # noqa: BLE001
                    st.error(
                        f"Error al ejecutar Ollama/LangGraph: {exc}. "
                        "Verifica que Ollama esté abierto en http://localhost:11434."
                    )

        # Visualización interactiva Plotly
        chart_type: ChartType = st.selectbox(
            "Gráfica financiera:",
            options=list(CHART_LABELS.keys()),
            format_func=lambda k: CHART_LABELS[k],
        )
        filtros = {
            "channel": case["channel"],
            "age_tag": case["age_tag"],
            "score_tag": case["score_tag"],
        }
        fig = build_plotly_figure(tipo_grafica=chart_type, filtros=filtros)
        st.plotly_chart(fig, use_container_width=True)

        if st.session_state["sql_queries"]:
            with st.expander("🔍 Consultas SQL ejecutadas por el agente"):
                for idx, q in enumerate(st.session_state["sql_queries"], start=1):
                    st.code(q, language="sql")

        if st.session_state["guardrail_issues"]:
            st.warning(
                "Guardrail detectó cifras no respaldadas en herramienta: "
                + ", ".join(st.session_state["guardrail_issues"])
            )

        default_draft = st.session_state["draft_dictamen"] or (
            f"Segmento {case['channel']} | {case['age_tag']} | {case['score_tag']}.\n"
            f"- Cuentas iniciales (MOB 0): {resumen['cuentas_iniciales_mob0']:,}\n"
            f"- Pérdida Neta (NCL/ENR): {resumen['ncl_rate_pct']}%\n"
            f"- Morosidad Over30 (Over30/ENR): {resumen['over30_rate_pct']}%\n"
            f"- Utilidad Neta acumulada: ${resumen['utilidad_neta']:,.2f}\n\n"
            "Dictamen preliminar: Presiona 'Analizar Caso con Agente IA' o edita este texto."
        )
        edited_draft = st.text_area(
            "📝 Dictamen Editable (Human-in-the-Loop):",
            value=default_draft,
            height=200,
        )
        st.session_state["draft_dictamen"] = edited_draft

        b1, b2 = st.columns(2)
        with b1:
            if st.button("✅ Aprobar y Generar DOCX/PPTX + Git Commit", use_container_width=True):
                with st.spinner("Exportando gráfica PNG, compilando DOCX/PPTX y registrando en Git..."):
                    viz_res = json.loads(
                        generar_grafica_portafolio.invoke(
                            {
                                "tipo_grafica": chart_type,
                                "case_id": case["case_id"],
                                "filtros": filtros,
                                "export_png": True,
                            }
                        )
                    )
                    hallazgos = [
                        f"Cuentas iniciales (MOB 0): {resumen['cuentas_iniciales_mob0']:,}",
                        f"Severidad NCL / ENR: {resumen['ncl_rate_pct']}%",
                        f"Morosidad Over30 / ENR: {resumen['over30_rate_pct']}%",
                        f"Utilidad Neta: ${resumen['utilidad_neta']:,.2f}",
                    ]
                    rep_res = json.loads(
                        compilar_entregables_ejecutivos.invoke(
                            {
                                "case_id": case["case_id"],
                                "titulo": f"Dictamen {case['channel']} | {case['age_tag']} | {case['score_tag']}",
                                "hallazgos": hallazgos,
                                "dictamen": edited_draft,
                                "rutas_graficas": [viz_res["ruta_png"]],
                            }
                        )
                    )
                    save_case_artifacts(
                        case["case_id"],
                        st.session_state["sql_queries"],
                        [{"resumen_cubo": resumen}],
                        edited_draft,
                    )
                    try:
                        git_msg = commit_human_approval(case["case_id"])
                    except Exception as exc:  # noqa: BLE001
                        git_msg = f"Aviso Git: {exc}"
                    st.session_state["last_outputs"] = rep_res
                    st.success(f"Entregables generados. {git_msg}")

        with b2:
            if st.button("🔀 Ver Git Diff", use_container_width=True):
                st.session_state["git_diff_text"] = get_case_diff(case["case_id"])

        if st.session_state["git_diff_text"]:
            st.code(st.session_state["git_diff_text"], language="diff")

        last_out = st.session_state.get("last_outputs", {})
        if last_out.get("ruta_docx") and Path(last_out["ruta_docx"]).exists():
            d1, d2 = st.columns(2)
            with d1:
                st.download_button(
                    "⬇️ Descargar Memorándum (.docx)",
                    data=Path(last_out["ruta_docx"]).read_bytes(),
                    file_name=Path(last_out["ruta_docx"]).name,
                    use_container_width=True,
                )
            with d2:
                st.download_button(
                    "⬇️ Descargar Presentación (.pptx)",
                    data=Path(last_out["ruta_pptx"]).read_bytes(),
                    file_name=Path(last_out["ruta_pptx"]).name,
                    use_container_width=True,
                )

    # ------------------------------------------------------------------
    # PANEL DERECHO: Chat Copiloto Investigador
    # ------------------------------------------------------------------
    with col_right:
        st.subheader("💬 Copiloto Investigador")
        st.caption("Pregunta libremente sobre el cubo DuckDB o políticas internas.")

        for role, msg in st.session_state["chat_history"]:
            with st.chat_message(role):
                st.markdown(msg)

        user_q = st.chat_input("Ej. ¿Qué canal tiene menor pérdida neta en MOB >= 12?")
        if user_q:
            st.session_state["chat_history"].append(("user", user_q))
            with st.chat_message("user"):
                st.markdown(user_q)

            with st.chat_message("assistant"):
                with st.spinner("Consultando agente..."):
                    try:
                        chat_graph = build_agent_graph(with_interrupt=False)
                        res = chat_graph.invoke(
                            {
                                "messages": [HumanMessage(content=user_q)],
                                "case_id": case["case_id"],
                                "sql_queries": [],
                                "evidence": [],
                                "draft_dictamen": "",
                                "guardrail_passed": True,
                                "guardrail_issues": [],
                                "retry_count": 0,
                            },
                            config={"configurable": {"thread_id": f"copilot-{case['case_id']}"}},
                        )
                        answer = res.get("draft_dictamen", "Sin respuesta del agente.")
                        if not res.get("guardrail_passed", True):
                            answer += (
                                "\n\n> ⚠️ *Aviso guardrail:* Algunas cifras no coincidieron "
                                f"exactamente con JSON: {', '.join(res.get('guardrail_issues', []))}"
                            )
                    except Exception as exc:  # noqa: BLE001
                        answer = (
                            f"Error al conectar con Ollama (`{OLLAMA_MODEL}`): `{exc}`. "
                            "Verifica que Ollama esté corriendo en `http://localhost:11434`."
                        )
                    st.markdown(answer)
                    st.session_state["chat_history"].append(("assistant", answer))


if __name__ == "__main__":
    main()
