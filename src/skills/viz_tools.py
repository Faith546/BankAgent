"""Skill 2: Catálogo de 6 visualizaciones financieras estilo CAPEX (Plotly + PNG)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Optional

import duckdb
import plotly.graph_objects as go
from langchain_core.tools import tool
from plotly.subplots import make_subplots
from pydantic import BaseModel, Field

from src.config import CASES_DIR, DUCKDB_PATH, MAX_NCL_RATE_PCT, MAX_OVER30_RATE_PCT
from src.skills.cubo_sql_tools import _build_where_clause

ChartType = Literal[
    "curva_maduracion_s",
    "curva_j_roa",
    "puente_pnl_waterfall",
    "heatmap_severidad",
    "matriz_cuadrantes",
    "embudo_cobranza",
]


class VizInput(BaseModel):
    """Parámetros para generar una gráfica ejecutiva del portafolio."""

    tipo_grafica: ChartType = Field(description="Tipo de gráfica financiera a generar.")
    case_id: str = Field(
        default="CASO-2026-0001",
        description="Identificador del caso para guardar archivos en outputs/cases/{case_id}/.",
    )
    filtros: Optional[dict[str, Any]] = Field(
        default=None,
        description="Filtros opcionales: channel, age_tag, score_tag, product, vintage.",
    )
    export_png: bool = Field(
        default=True,
        description="Si es True, exporta también el archivo estático .png mediante Kaleido.",
    )


def _extract_filters(filtros: Optional[dict[str, Any]]) -> tuple[str, list[Any]]:
    f = filtros or {}
    return _build_where_clause(
        channel=f.get("channel"),
        age_tag=f.get("age_tag"),
        score_tag=f.get("score_tag"),
        product=f.get("product"),
        vintage=f.get("vintage"),
    )


def build_plotly_figure(
    tipo_grafica: ChartType,
    filtros: Optional[dict[str, Any]] = None,
) -> go.Figure:
    """Construye una figura interactiva de Plotly consultando DuckDB en modo solo lectura."""
    where_sql, params = _extract_filters(filtros)
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        if tipo_grafica == "curva_maduracion_s":
            rows = con.execute(
                f"""
                SELECT
                    MOB,
                    (SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS over30_pct,
                    (SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS ncl_pct
                FROM v_cubo_metricas
                {where_sql}
                GROUP BY MOB
                ORDER BY MOB
                """,
                params,
            ).fetchall()
            mobs = [r[0] for r in rows]
            over30 = [r[1] for r in rows]
            ncl = [r[2] for r in rows]

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=mobs,
                    y=over30,
                    mode="lines+markers",
                    name="% Over30 / ENR",
                    line={"color": "#D97706", "width": 3},
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=mobs,
                    y=ncl,
                    mode="lines+markers",
                    name="% NCL / ENR",
                    line={"color": "#C8102E", "width": 3},
                )
            )
            fig.add_hline(
                y=MAX_NCL_RATE_PCT,
                line_dash="dash",
                line_color="#C8102E",
                annotation_text=f"Límite NCL ({MAX_NCL_RATE_PCT}%)",
            )
            fig.add_hline(
                y=MAX_OVER30_RATE_PCT,
                line_dash="dot",
                line_color="#D97706",
                annotation_text=f"Límite Over30 ({MAX_OVER30_RATE_PCT}%)",
            )
            fig.update_layout(
                title="Curva S de Maduración: Morosidad Over30 y Pérdida Neta (NCL)",
                xaxis_title="MOB (Months on Book)",
                yaxis_title="Tasa sobre Saldo (%)",
                hovermode="x unified",
                margin={"l": 40, "r": 20, "t": 55, "b": 40},
                legend={
                    "orientation": "h",
                    "yanchor": "bottom",
                    "y": 1.02,
                    "xanchor": "right",
                    "x": 1,
                },
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            return fig

        if tipo_grafica == "curva_j_roa":
            rows = con.execute(
                f"""
                SELECT
                    SCORE_TAG,
                    MOB,
                    (
                        (SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL))
                        / NULLIF(SUM(ENRAMTS), 0)
                    ) * 100.0 AS net_roa_pct
                FROM v_cubo_metricas
                {where_sql}
                GROUP BY SCORE_TAG, MOB
                ORDER BY SCORE_TAG, MOB
                """,
                params,
            ).fetchall()
            by_score: dict[str, tuple[list[int], list[float]]] = {}
            for score, mob, roa in rows:
                by_score.setdefault(score, ([], []))
                by_score[score][0].append(mob)
                by_score[score][1].append(roa)

            fig = go.Figure()
            for score, (mobs, roas) in by_score.items():
                fig.add_trace(go.Scatter(x=mobs, y=roas, mode="lines", name=score))
            fig.add_hline(
                y=0.0,
                line_dash="dash",
                line_color="#374151",
                annotation_text="Punto de Equilibrio (0%)",
            )
            fig.update_layout(
                title="Curva J de Rentabilidad: ROA Neto por MOB y Score",
                xaxis_title="MOB (Months on Book)",
                yaxis_title="ROA Neto (%)",
                template="plotly_white",
            )
            return fig

        if tipo_grafica == "puente_pnl_waterfall":
            row = con.execute(
                f"""
                SELECT
                    COALESCE(SUM(REVENUE), 0.0) AS rev,
                    COALESCE(SUM(GCLAMTS), 0.0) AS gcl,
                    COALESCE(SUM(RECOVERYAMTS), 0.0) AS rec,
                    COALESCE(SUM(EXPENSES_ACQ), 0.0) AS acq,
                    COALESCE(SUM(EXPENSES_ECM_VAR), 0.0) AS ecm_var,
                    COALESCE(SUM(EXPENSES_ECM_FIX), 0.0) AS ecm_fix,
                    COALESCE(SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL), 0.0) AS net_margin
                FROM v_cubo_metricas
                {where_sql}
                """,
                params,
            ).fetchone()
            rev, gcl, rec, acq, ecm_var, ecm_fix, net_margin = row
            fig = go.Figure(
                go.Waterfall(
                    orientation="v",
                    measure=[
                        "relative",
                        "relative",
                        "relative",
                        "relative",
                        "relative",
                        "relative",
                        "total",
                    ],
                    x=[
                        "+Revenue",
                        "-GCL (Bruta)",
                        "+Recovery",
                        "-Exp. Acq",
                        "-Exp. Var",
                        "-Exp. Fix",
                        "Margen Neto",
                    ],
                    y=[rev, -gcl, rec, -acq, -ecm_var, -ecm_fix, net_margin],
                    connector={"line": {"color": "rgb(63, 63, 63)"}},
                )
            )
            fig.update_layout(
                title="Puente P&L del Segmento (Waterfall)",
                yaxis_title="Monto ($ MXN)",
                template="plotly_white",
            )
            return fig

        if tipo_grafica == "heatmap_severidad":
            mature_where = f"{where_sql} AND MOB >= 6" if where_sql else "WHERE MOB >= 6"
            rows = con.execute(
                f"""
                SELECT
                    CHANNEL || ' | ' || AGE_TAG AS row_label,
                    SCORE_TAG,
                    (SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS ncl_pct
                FROM v_cubo_metricas
                {mature_where}
                GROUP BY 1, 2
                ORDER BY 1, 2
                """,
                params,
            ).fetchall()
            y_labels = sorted({r[0] for r in rows})
            x_labels = sorted({r[1] for r in rows})
            grid_map = {(r[0], r[1]): round(r[2], 2) if r[2] is not None else None for r in rows}
            z_matrix = [[grid_map.get((y, x)) for x in x_labels] for y in y_labels]

            fig = go.Figure(
                data=go.Heatmap(
                    z=z_matrix,
                    x=x_labels,
                    y=y_labels,
                    colorscale="RdYlGn_r",
                    colorbar={"title": "NCL / ENR (%)"},
                )
            )
            fig.update_layout(
                title="Mapa de Calor de Severidad (NCL / ENR % en MOB >= 6)",
                xaxis_title="SCORE_TAG",
                yaxis_title="CHANNEL | AGE_TAG",
                template="plotly_white",
            )
            return fig

        if tipo_grafica == "matriz_cuadrantes":
            mature_where = f"{where_sql} AND MOB >= 12" if where_sql else "WHERE MOB >= 12"
            rows = con.execute(
                f"""
                SELECT
                    CHANNEL || ' | ' || PRODUCT || ' | ' || SCORE_TAG AS seg_label,
                    (SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS ncl_pct,
                    (SUM(REVENUE) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 AS yield_pct,
                    SUM(ENRAMTS) AS enr_vol
                FROM v_cubo_metricas
                {mature_where}
                GROUP BY 1
                HAVING SUM(ENRAMTS) > 0
                ORDER BY enr_vol DESC
                LIMIT 60
                """,
                params,
            ).fetchall()
            labels = [r[0] for r in rows]
            ncl_vals = [r[1] for r in rows]
            yield_vals = [r[2] for r in rows]
            vols = [r[3] for r in rows]
            max_vol = max(vols) if vols else 1.0
            sizes = [max(10.0, (v / max_vol) * 45.0) for v in vols]

            fig = go.Figure(
                go.Scatter(
                    x=ncl_vals,
                    y=yield_vals,
                    mode="markers",
                    text=labels,
                    marker={
                        "size": sizes,
                        "color": ncl_vals,
                        "colorscale": "RdYlGn_r",
                        "showscale": True,
                    },
                )
            )
            fig.add_vline(
                x=MAX_NCL_RATE_PCT,
                line_dash="dash",
                line_color="#dc2626",
                annotation_text="Límite NCL 15%",
            )
            fig.update_layout(
                title="Matriz de Cuadrantes (Cohortes Maduras MOB >= 12)",
                xaxis_title="Severidad NCL / ENR (%)",
                yaxis_title="Yield Revenue / ENR (%)",
                template="plotly_white",
            )
            return fig

        # embudo_cobranza
        row = con.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN MOB = 0 THEN ACCOUNTS ELSE 0 END), 0) AS accts_mob0,
                COALESCE(AVG(ENRACCTS), 0) AS avg_enraccts,
                COALESCE(AVG(OVER30ACCTS), 0) AS avg_over30accts,
                COALESCE(SUM(GCLAMTS), 0.0) AS gcl,
                COALESCE(SUM(RECOVERYAMTS), 0.0) AS rec,
                COALESCE(SUM(NCLAMTS), 0.0) AS ncl
            FROM v_cubo_metricas
            {where_sql}
            """,
            params,
        ).fetchone()
        accts0, enr_accts, over30_accts, gcl, rec, ncl = row

        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=("Embudo de Cuentas (Promedio/Inicio)", "Eficiencia de Cobranza ($)"),
        )
        fig.add_trace(
            go.Bar(
                x=["ACCOUNTS (MOB 0)", "ENRACCTS (Prom)", "OVER30ACCTS (Prom)"],
                y=[accts0, enr_accts, over30_accts],
                marker_color=["#2563eb", "#0ea5e9", "#f59e0b"],
                name="Cuentas",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Bar(
                x=["GCL (Bruta)", "Recovery", "NCL (Neta)"],
                y=[gcl, rec, ncl],
                marker_color=["#ef4444", "#10b981", "#b91c1c"],
                name="Montos",
            ),
            row=1,
            col=2,
        )
        fig.update_layout(
            title="Embudo de Morosidad y Eficiencia de Recuperación",
            showlegend=False,
            template="plotly_white",
        )
        return fig
    finally:
        con.close()


@tool(args_schema=VizInput)
def generar_grafica_portafolio(
    tipo_grafica: ChartType,
    case_id: str = "CASO-2026-0001",
    filtros: Optional[dict[str, Any]] = None,
    export_png: bool = True,
) -> str:
    """Genera una gráfica financiera de Plotly y la exporta en PNG y JSON dentro del caso."""
    charts_dir: Path = CASES_DIR / case_id / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    fig = build_plotly_figure(tipo_grafica=tipo_grafica, filtros=filtros)
    png_path = charts_dir / f"{tipo_grafica}.png"
    json_path = charts_dir / f"{tipo_grafica}.json"

    json_path.write_text(fig.to_json(), encoding="utf-8")
    png_status = "skipped"
    if export_png:
        png_status = "ok"
        try:
            fig.write_image(str(png_path), width=1200, height=700, scale=2)
        except Exception as exc:  # noqa: BLE001
            png_status = f"error_kaleido: {exc}"

    return json.dumps(
        {
            "tipo_grafica": tipo_grafica,
            "case_id": case_id,
            "ruta_png": str(png_path),
            "ruta_plotly_json": str(json_path),
            "png_status": png_status,
        },
        ensure_ascii=False,
    )
