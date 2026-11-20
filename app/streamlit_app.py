"""Consola Híbrida Ejecutiva en Streamlit — Asistente de Portafolio Banamex (MVP).

Sigue las mejores prácticas de diseño y tematización de Streamlit:
- Tema corporativo nativo en `.streamlit/config.toml` (light/dark + sidebar navy).
- Jerarquía visual con `st.sidebar`, tarjetas `st.container(border=True)`,
  `st.metric(..., border=True)`, `st.badge`, `st.tabs`, `st.pills` e íconos Material.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.graph import build_agent_graph, make_initial_state  # noqa: E402
from src.config import (  # noqa: E402
    DUCKDB_PATH,
    MAX_NCL_RATE_PCT,
    MAX_OVER30_RATE_PCT,
    MIN_MATURE_MOB,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_REASONING,
    VALID_CHANNELS,
)
from src.skills.cubo_sql_tools import obtener_resumen_portafolio  # noqa: E402
from src.skills.git_governance import (  # noqa: E402
    commit_ai_draft,
    commit_human_approval,
    get_case_diff,
    save_case_artifacts,
)
from src.skills.report_tools import compilar_entregables_ejecutivos  # noqa: E402
from src.skills.viz_tools import (  # noqa: E402
    ChartType,
    build_plotly_figure,
    generar_grafica_portafolio,
)

CHART_LABELS: dict[ChartType, str] = {
    "curva_maduracion_s": "Curva S (Maduración)",
    "curva_j_roa": "Curva J (ROA Neto)",
    "puente_pnl_waterfall": "Puente P&L",
    "heatmap_severidad": "Heatmap Severidad",
    "matriz_cuadrantes": "Matriz Cuadrantes",
    "embudo_cobranza": "Embudo Cobranza",
}

QUICK_PROMPTS: list[str] = [
    "¿Qué canal tiene peor pérdida neta en MOB >= 6?",
    "Compara Aeropuerto vs Branch en MOB >= 6",
    "¿Cuál es la política de recuperación de cobranza?",
]


@st.cache_data(ttl=300)
def load_parametric_alerts(
    channel_filter: str | None = None, limit: int = 25
) -> list[dict[str, Any]]:
    """Consulta segmentos maduros (MOB >= 6) que exceden umbrales de apetito de riesgo."""
    if not DUCKDB_PATH.exists():
        return []

    where_extra = "AND CHANNEL = ?" if channel_filter and channel_filter != "Todos" else ""
    params: list[Any] = [channel_filter, limit] if where_extra else [limit]

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
            WHERE MOB >= {MIN_MATURE_MOB} {where_extra}
            GROUP BY CHANNEL, AGE_TAG, SCORE_TAG
            HAVING (SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 > {MAX_NCL_RATE_PCT}
                OR (SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 > {MAX_OVER30_RATE_PCT}
            ORDER BY ncl_rate_pct DESC, enr_total DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    finally:
        con.close()

    return [
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
        for idx, r in enumerate(rows, start=1)
    ]


def _init_session_state() -> None:
    defaults: dict[str, Any] = {
        "selected_case_key": "",
        "draft_dictamen": "",
        "sql_queries": [],
        "evidence": [],
        "guardrail_issues": [],
        "chat_history": [],
        "last_outputs": {},
        "git_diff_text": "",
        "token_usage": {},
        "last_quick_prompt": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _reset_case_state(case_key: str) -> None:
    st.session_state["selected_case_key"] = case_key
    st.session_state["draft_dictamen"] = ""
    st.session_state["sql_queries"] = []
    st.session_state["evidence"] = []
    st.session_state["guardrail_issues"] = []
    st.session_state["git_diff_text"] = ""
    st.session_state["last_outputs"] = {}


def _run_agent_for_case(case: dict[str, Any]) -> None:
    prompt = (
        f"Analiza el segmento CHANNEL='{case['channel']}', AGE_TAG='{case['age_tag']}', "
        f"SCORE_TAG='{case['score_tag']}'. Obtén su resumen de portafolio, revisa su curva de "
        "maduración, consulta el manual de apetito de riesgo y redacta un dictamen ejecutivo "
        "con recomendación concreta (Expandir, Restringir Línea o Suspender Originación)."
    )
    graph = build_agent_graph(with_interrupt=True)
    config = {"configurable": {"thread_id": f"case-{case['case_id']}"}}
    result = graph.invoke(
        make_initial_state(prompt=prompt, case_id=case["case_id"]), config=config
    )

    draft = result.get("draft_dictamen", "")
    queries = result.get("sql_queries", [])
    evidence = result.get("evidence", [])
    issues = result.get("guardrail_issues", [])

    st.session_state["draft_dictamen"] = draft
    st.session_state["sql_queries"] = queries
    st.session_state["evidence"] = evidence
    st.session_state["guardrail_issues"] = issues
    st.session_state["token_usage"] = result.get("token_usage", {})

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
        st.toast(f"Borrador guardado (sin commit Git automático): {exc}", icon=":material/info:")


def _send_copilot_message(user_q: str, case_id: str) -> None:
    st.session_state["chat_history"].append(("user", user_q))
    try:
        chat_graph = build_agent_graph(with_interrupt=False)
        res = chat_graph.invoke(
            make_initial_state(prompt=user_q, case_id=case_id),
            config={"configurable": {"thread_id": f"copilot-{case_id}"}},
        )
        st.session_state["token_usage"] = res.get("token_usage", {})
        answer = res.get("draft_dictamen", "Sin respuesta del agente.")
        if not res.get("guardrail_passed", True):
            answer += (
                "\n\n> :material/warning: *Aviso guardrail:* Algunas cifras no coincidieron "
                f"exactamente con JSON: {', '.join(res.get('guardrail_issues', []))}"
            )
    except Exception as exc:  # noqa: BLE001
        answer = (
            f"Error al conectar con Ollama (`{OLLAMA_MODEL}`): `{exc}`. "
            "Verifica que Ollama esté corriendo en `http://localhost:11434`."
        )
    st.session_state["chat_history"].append(("assistant", answer))


def _render_sidebar() -> dict[str, Any] | None:
    with st.sidebar:
        st.markdown("### :material/account_balance: Banamex Risk Agent")
        st.caption("Consola Local de Portafolio de Tarjetas")
        st.divider()

        channel_filter = st.selectbox(
            "Filtrar alertas por canal",
            options=["Todos", *VALID_CHANNELS],
            index=0,
        )
        alerts = load_parametric_alerts(channel_filter=channel_filter)

        st.markdown(f"#### :material/warning: Alertas Activas ({len(alerts)})")
        st.caption(
            f"Cohortes MOB ≥ {MIN_MATURE_MOB} | "
            f"NCL > {MAX_NCL_RATE_PCT}% u Over30 > {MAX_OVER30_RATE_PCT}%"
        )

        if not alerts:
            st.info("Sin segmentos fuera de umbral para este canal.")
            return None

        labels = [
            f"{a['case_id']} · {a['channel']} · {a['score_tag']} ({a['ncl_rate_pct']}%)"
            for a in alerts
        ]
        selected_idx = st.radio(
            "Cola de investigación",
            options=range(len(alerts)),
            format_func=lambda i: labels[i],
            label_visibility="collapsed",
        )
        case = alerts[selected_idx]
        case_key = f"{case['channel']}|{case['age_tag']}|{case['score_tag']}"
        if st.session_state["selected_case_key"] != case_key:
            _reset_case_state(case_key)

        st.divider()
        with st.container(border=True):
            st.markdown(f"**{case['case_id']}**")
            st.caption(
                f"Canal: **{case['channel']}**  \n"
                f"Edad: **{case['age_tag']}**  \n"
                f"Score: **{case['score_tag']}**  \n"
                f"Cohortes: **{case['cohortes']}**"
            )

        st.divider()
        think_tag = "ON" if OLLAMA_REASONING else "OFF"
        st.caption(
            f":material/memory: `{OLLAMA_MODEL}` · think `{think_tag}` · ctx `{OLLAMA_NUM_CTX:,}`"
        )
        return case


def main() -> None:
    st.set_page_config(
        page_title="Banamex Risk Agent — Consola Ejecutiva",
        page_icon=":material/account_balance:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_session_state()

    if not DUCKDB_PATH.exists():
        st.error(
            f"No se encontró la base DuckDB en `{DUCKDB_PATH}`. "
            "Ejecuta primero `uv run python -m src.data.init_db`."
        )
        return

    case = _render_sidebar()
    if case is None:
        return

    # ------------------------------------------------------------------
    # ENCABEZADO EJECUTIVO CON BADGES DE ESTADO
    # ------------------------------------------------------------------
    header_l, header_r = st.columns([3, 1.4], vertical_alignment="bottom")
    with header_l:
        st.markdown(
            f"## :material/analytics: {case['case_id']} — {case['channel']} · {case['score_tag']}"
        )
        st.caption(
            f"Segmento de edad `{case['age_tag']}` · "
            f"{case['cohortes']} cohortes monitoreadas en DuckDB"
        )
    with header_r:
        with st.container(horizontal=True, horizontal_alignment="right"):
            if case["ncl_rate_pct"] > MAX_NCL_RATE_PCT:
                st.badge("Fuera de Apetito", icon=":material/gpp_bad:", color="red")
            elif case["ncl_rate_pct"] >= 12.0:
                st.badge("Vigilancia", icon=":material/visibility:", color="orange")
            else:
                st.badge("En Apetito", icon=":material/verified_user:", color="green")
            st.badge(f"MOB ≥ {MIN_MATURE_MOB}", color="blue")

    # ------------------------------------------------------------------
    # TARJETAS KPI (BORDERED METRICS CON DELTAS VS. POLÍTICA)
    # ------------------------------------------------------------------
    resumen = json.loads(
        obtener_resumen_portafolio.invoke(
            {
                "channel": case["channel"],
                "age_tag": case["age_tag"],
                "score_tag": case["score_tag"],
            }
        )
    )
    ncl_val = float(resumen["ncl_rate_pct"] or 0.0)
    over30_val = float(resumen["over30_rate_pct"] or 0.0)
    roa_val = float(resumen["net_roa_pct"] or 0.0)

    k1, k2, k3, k4 = st.columns(4, gap="small")
    k1.metric(
        "Cuentas Iniciales (MOB 0)",
        f"{resumen['cuentas_iniciales_mob0']:,}",
        delta=f"Líneas: ${resumen['lineas_credito_iniciales_mob0'] / 1e6:,.1f}M",
        delta_color="off",
        border=True,
    )
    k2.metric(
        "Severidad NCL / ENR",
        f"{ncl_val:.2f}%",
        delta=f"{ncl_val - MAX_NCL_RATE_PCT:+.2f} pp vs límite {MAX_NCL_RATE_PCT}%",
        delta_color="inverse",
        border=True,
    )
    k3.metric(
        "Morosidad Over30 / ENR",
        f"{over30_val:.2f}%",
        delta=f"{over30_val - MAX_OVER30_RATE_PCT:+.2f} pp vs límite {MAX_OVER30_RATE_PCT}%",
        delta_color="inverse",
        border=True,
    )
    k4.metric(
        "Utilidad Neta Acumulada",
        f"${resumen['utilidad_neta'] / 1e6:,.2f}M",
        delta=f"ROA Neto: {roa_val:.2f}%",
        delta_color="normal" if roa_val >= 0 else "inverse",
        border=True,
    )

    st.divider()

    # ------------------------------------------------------------------
    # LIENZO PRINCIPAL (IZQ: EVIDENCIA Y DICTAMEN | DER: COPILOTO)
    # ------------------------------------------------------------------
    col_main, col_chat = st.columns([1.75, 1.0], gap="medium")

    with col_main:
        tab_viz, tab_dictamen, tab_audit = st.tabs(
            [
                ":material/monitoring: Gráficas Financieras",
                ":material/edit_document: Dictamen & Human-in-the-Loop",
                ":material/database: Auditoría SQL & Telemetría",
            ]
        )

        filtros = {
            "channel": case["channel"],
            "age_tag": case["age_tag"],
            "score_tag": case["score_tag"],
        }

        with tab_viz:
            with st.container(border=True):
                chart_type: ChartType = (
                    st.pills(
                        "Selecciona visualización",
                        options=list(CHART_LABELS.keys()),
                        format_func=lambda k: CHART_LABELS[k],
                        default="curva_maduracion_s",
                        selection_mode="single",
                        label_visibility="collapsed",
                    )
                    or "curva_maduracion_s"
                )

                fig = build_plotly_figure(tipo_grafica=chart_type, filtros=filtros)
                st.plotly_chart(fig, use_container_width=True)

            with st.expander(
                ":material/table_view: Resumen Contable del Segmento (DuckDB)", expanded=False
            ):
                summary_df = pd.DataFrame(
                    [
                        (
                            "Ingresos acumulados (REVENUE)",
                            f"${resumen['ingresos_acumulados']:,.2f}",
                        ),
                        ("Pérdida bruta (GCLAMTS)", f"${resumen['perdida_bruta_gcl']:,.2f}"),
                        (
                            "Recuperación cobranza (RECOVERYAMTS)",
                            f"${resumen['recuperacion_cobranza']:,.2f}",
                        ),
                        ("Eficiencia recuperación (%)", f"{resumen['recovery_rate_pct']}%"),
                        ("Pérdida neta (NCLAMTS)", f"${resumen['perdida_neta_ncl']:,.2f}"),
                        ("Gastos totales (EXPENSES_TOTAL)", f"${resumen['gastos_totales']:,.2f}"),
                        ("Utilidad neta (NET_PROFIT)", f"${resumen['utilidad_neta']:,.2f}"),
                    ],
                    columns=["Métrica", "Valor Verificado"],
                )
                st.dataframe(summary_df, use_container_width=True, hide_index=True)

        with tab_dictamen:
            with st.container(border=True):
                act_l, act_r = st.columns([2, 1], vertical_alignment="center")
                with act_l:
                    st.markdown("#### Borrador de Dictamen Ejecutivo")
                    st.caption(
                        "Pausa Human-in-the-Loop: revisa y edita antes de compilar DOCX/PPTX."
                    )
                with act_r:
                    if st.button(
                        "Analizar con IA",
                        icon=":material/smart_toy:",
                        type="primary",
                        use_container_width=True,
                    ):
                        with st.spinner(f"Consultando DuckDB, RAG y `{OLLAMA_MODEL}`..."):
                            try:
                                _run_agent_for_case(case)
                                st.toast(
                                    "Borrador IA listo para revisión.",
                                    icon=":material/check_circle:",
                                )
                            except Exception as exc:  # noqa: BLE001
                                st.error(
                                    f"Error al ejecutar Ollama/LangGraph: {exc}. "
                                    "Verifica que Ollama esté abierto en `http://localhost:11434`."
                                )

                if st.session_state["guardrail_issues"]:
                    st.warning(
                        "Guardrail detectó cifras no respaldadas en herramienta: "
                        + ", ".join(st.session_state["guardrail_issues"]),
                        icon=":material/warning:",
                    )

                default_draft = st.session_state["draft_dictamen"] or (
                    f"Segmento {case['channel']} | {case['age_tag']} | {case['score_tag']}.\n"
                    f"- Cuentas iniciales (MOB 0): {resumen['cuentas_iniciales_mob0']:,}\n"
                    f"- Pérdida Neta (NCL/ENR): {resumen['ncl_rate_pct']}%\n"
                    f"- Morosidad Over30 (Over30/ENR): {resumen['over30_rate_pct']}%\n"
                    f"- Utilidad Neta acumulada: ${resumen['utilidad_neta']:,.2f}\n\n"
                    "Dictamen preliminar: presiona 'Analizar con IA' o edita este texto."
                )
                edited_draft = st.text_area(
                    "Texto del dictamen",
                    value=default_draft,
                    height=220,
                    label_visibility="collapsed",
                )
                st.session_state["draft_dictamen"] = edited_draft

                b1, b2 = st.columns(2)
                with b1:
                    if st.button(
                        "Aprobar y Generar DOCX/PPTX + Git Commit",
                        icon=":material/verified:",
                        type="primary",
                        use_container_width=True,
                    ):
                        with st.spinner(
                            "Exportando PNG, compilando DOCX/PPTX y commiteando en Git..."
                        ):
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
                            estado_riesgo = (
                                "FUERA DE APETITO"
                                if ncl_val > MAX_NCL_RATE_PCT or over30_val > MAX_OVER30_RATE_PCT
                                else ("VIGILANCIA" if ncl_val >= 12.0 else "EN APETITO")
                            )
                            lineas_m = resumen["lineas_credito_iniciales_mob0"] / 1e6
                            util_m = resumen["utilidad_neta"] / 1e6
                            ncl_delta = ncl_val - MAX_NCL_RATE_PCT
                            over30_delta = over30_val - MAX_OVER30_RATE_PCT
                            kpis_payload = [
                                {
                                    "label": "Cuentas Iniciales (MOB 0)",
                                    "value": f"{resumen['cuentas_iniciales_mob0']:,}",
                                    "delta": f"Líneas: ${lineas_m:,.1f}M",
                                    "status": "blue",
                                },
                                {
                                    "label": "Severidad NCL / ENR",
                                    "value": f"{ncl_val:.2f}%",
                                    "delta": f"{ncl_delta:+.2f} pp vs límite {MAX_NCL_RATE_PCT}%",
                                    "status": "red" if ncl_val > MAX_NCL_RATE_PCT else "green",
                                },
                                {
                                    "label": "Morosidad Over30 / ENR",
                                    "value": f"{over30_val:.2f}%",
                                    "delta": (
                                        f"{over30_delta:+.2f} pp vs límite {MAX_OVER30_RATE_PCT}%"
                                    ),
                                    "status": (
                                        "red" if over30_val > MAX_OVER30_RATE_PCT else "green"
                                    ),
                                },
                                {
                                    "label": "Utilidad Neta Acumulada",
                                    "value": f"${util_m:,.2f}M",
                                    "delta": f"ROA Neto: {roa_val:.2f}%",
                                    "status": "green" if roa_val >= 0 else "orange",
                                },
                            ]
                            tabla_payload = [
                                [
                                    "Ingresos acumulados (REVENUE)",
                                    f"${resumen['ingresos_acumulados']:,.2f}",
                                    "Cubo DuckDB",
                                ],
                                [
                                    "Pérdida bruta (GCLAMTS)",
                                    f"${resumen['perdida_bruta_gcl']:,.2f}",
                                    "Antes de cobranza",
                                ],
                                [
                                    "Recuperación cobranza",
                                    f"${resumen['recuperacion_cobranza']:,.2f}",
                                    f"Eficiencia: {resumen['recovery_rate_pct']}% (mín 40%)",
                                ],
                                [
                                    "Pérdida neta (NCLAMTS)",
                                    f"${resumen['perdida_neta_ncl']:,.2f}",
                                    f"NCL/ENR: {ncl_val:.2f}% (máx {MAX_NCL_RATE_PCT}%)",
                                ],
                                [
                                    "Gastos totales (EXPENSES_TOTAL)",
                                    f"${resumen['gastos_totales']:,.2f}",
                                    "ACQ + ECM Var/Fix",
                                ],
                                [
                                    "Utilidad neta (NET_PROFIT)",
                                    f"${resumen['utilidad_neta']:,.2f}",
                                    f"ROA Neto: {roa_val:.2f}%",
                                ],
                            ]
                            hallazgos = [
                                (
                                    f"Cuentas iniciales (MOB 0): "
                                    f"{resumen['cuentas_iniciales_mob0']:,} "
                                    f"con líneas por ${lineas_m:,.1f}M."
                                ),
                                (
                                    f"Severidad NCL / ENR de {ncl_val:.2f}% "
                                    f"({ncl_delta:+.2f} pp vs límite {MAX_NCL_RATE_PCT}%)."
                                ),
                                (
                                    f"Morosidad Over30 / ENR de {over30_val:.2f}% "
                                    f"(recuperación de cobranza: {resumen['recovery_rate_pct']}%)."
                                ),
                                (
                                    f"Utilidad Neta acumulada de ${util_m:,.2f}M "
                                    f"(ROA Neto {roa_val:.2f}%)."
                                ),
                            ]
                            deck_title = (
                                f"{case['channel']} · {case['age_tag']} · "
                                f"{case['score_tag']} ({estado_riesgo})"
                            )
                            rep_res = json.loads(
                                compilar_entregables_ejecutivos.invoke(
                                    {
                                        "case_id": case["case_id"],
                                        "titulo": deck_title,
                                        "hallazgos": hallazgos,
                                        "dictamen": edited_draft,
                                        "rutas_graficas": [viz_res["ruta_png"]],
                                        "estado_riesgo": estado_riesgo,
                                        "kpis": kpis_payload,
                                        "tabla_metricas": tabla_payload,
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
                            st.success(
                                f"Entregables compilados. {git_msg}",
                                icon=":material/check_circle:",
                            )

                with b2:
                    if st.button(
                        "Ver Git Diff de Auditoría",
                        icon=":material/difference:",
                        use_container_width=True,
                    ):
                        st.session_state["git_diff_text"] = get_case_diff(case["case_id"])

                if st.session_state["git_diff_text"]:
                    st.code(st.session_state["git_diff_text"], language="diff")

                last_out = st.session_state.get("last_outputs", {})
                if last_out.get("ruta_docx") and Path(last_out["ruta_docx"]).exists():
                    d1, d2 = st.columns(2)
                    with d1:
                        st.download_button(
                            "Descargar Memorándum (.docx)",
                            data=Path(last_out["ruta_docx"]).read_bytes(),
                            file_name=Path(last_out["ruta_docx"]).name,
                            icon=":material/download:",
                            use_container_width=True,
                        )
                    with d2:
                        st.download_button(
                            "Descargar Presentación (.pptx)",
                            data=Path(last_out["ruta_pptx"]).read_bytes(),
                            file_name=Path(last_out["ruta_pptx"]).name,
                            icon=":material/download:",
                            use_container_width=True,
                        )

        with tab_audit:
            with st.container(border=True):
                st.markdown("#### :material/speed: Telemetría de Ventana de Contexto")
                tu = st.session_state.get("token_usage") or {}
                used_ctx = int(tu.get("prompt_eval_count", 0))
                max_ctx = max(int(tu.get("num_ctx", OLLAMA_NUM_CTX)), 1)
                ratio = min(used_ctx / max_ctx, 1.0)
                st.progress(
                    ratio,
                    text=f"Contexto usado: {used_ctx:,} / {max_ctx:,} tokens ({ratio * 100:.1f}%)",
                )

                t1, t2, t3 = st.columns(3)
                t1.metric("Tokens Generados", f"{tu.get('eval_count', 0):,}", border=True)
                t2.metric("Llamadas al LLM", f"{tu.get('total_calls', 0)}", border=True)
                t3.metric("Última Latencia", f"{tu.get('last_latency_s', 0)} s", border=True)

            with st.container(border=True):
                st.markdown("#### :material/code: Consultas SQL Ejecutadas por el Agente")
                if st.session_state["sql_queries"]:
                    for q in st.session_state["sql_queries"]:
                        st.code(q, language="sql")
                else:
                    st.caption("Aún no se han ejecutado consultas Text-to-SQL en este caso.")

    # ------------------------------------------------------------------
    # PANEL DERECHO: CHAT COPILOTO INVESTIGADOR
    # ------------------------------------------------------------------
    with col_chat:
        with st.container(border=True):
            ch_l, ch_r = st.columns([3, 1], vertical_alignment="center")
            with ch_l:
                st.markdown("#### :material/forum: Copiloto Investigador")
            with ch_r:
                if st.button("Limpiar", icon=":material/delete_sweep:", use_container_width=True):
                    st.session_state["chat_history"] = []
                    st.rerun()

            st.caption("Consulta ad-hoc el cubo DuckDB y las políticas internas.")

            quick_choice = st.pills(
                "Preguntas sugeridas",
                options=QUICK_PROMPTS,
                selection_mode="single",
                label_visibility="collapsed",
                key="quick_prompt_pills",
            )

            chat_box = st.container(height=420, border=False)
            with chat_box:
                if not st.session_state["chat_history"]:
                    st.info(
                        "Haz una pregunta sobre cohortes, canales, scores o políticas de riesgo. "
                        "El agente verificará todas las cifras en DuckDB.",
                        icon=":material/lightbulb:",
                    )
                for role, msg in st.session_state["chat_history"]:
                    with st.chat_message(role):
                        st.markdown(msg)

            user_q = st.chat_input("Pregunta sobre el portafolio...")
            active_q = None
            if user_q:
                active_q = user_q
            elif quick_choice and quick_choice != st.session_state.get("last_quick_prompt"):
                st.session_state["last_quick_prompt"] = quick_choice
                active_q = quick_choice

            if active_q:
                with st.spinner("Consultando agente..."):
                    _send_copilot_message(active_q, case["case_id"])
                st.rerun()


if __name__ == "__main__":
    main()
