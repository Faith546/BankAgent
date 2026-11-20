"""Skill 4: Motor de diseño ejecutivo para presentaciones 16:9 (.pptx) y memorándums (.docx).

Separa contenido (contrato Pydantic) de diseño (motor de layouts widescreen 16:9 con paleta
corporativa Banamex, KPI cards, tablas estilizadas, layout 60/40 de gráfica + callouts y
plan de acción numerado).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

from docx import Document as DocxDocument
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches as DocxInches
from docx.shared import Pt as DocxPt
from docx.shared import RGBColor as DocxRGBColor
from langchain_core.tools import tool
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt
from pydantic import BaseModel, Field

from src.config import CASES_DIR, MAX_NCL_RATE_PCT, MAX_OVER30_RATE_PCT, TEMPLATES_DIR

# ---------------------------------------------------------------------------
# Paleta Corporativa Banamex (coherente con .streamlit/config.toml)
# ---------------------------------------------------------------------------
NAVY = RGBColor(0x00, 0x3B, 0x71)
DARK_NAVY = RGBColor(0x00, 0x24, 0x47)
CRIMSON = RGBColor(0xC8, 0x10, 0x2E)
AMBER = RGBColor(0xD9, 0x77, 0x06)
TEAL = RGBColor(0x0F, 0x76, 0x6E)
SLATE = RGBColor(0x0F, 0x17, 0x2A)
MUTED = RGBColor(0x47, 0x55, 0x69)
BG_LIGHT = RGBColor(0xF8, 0xFA, 0xFC)
ROW_ALT = RGBColor(0xF1, 0xF5, 0xF9)
BORDER = RGBColor(0xCB, 0xD5, 0xE1)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SOFT_BLUE = RGBColor(0xE0, 0xEC, 0xF8)

STATUS_COLORS: dict[str, RGBColor] = {
    "red": CRIMSON,
    "orange": AMBER,
    "green": TEAL,
    "blue": NAVY,
    "FUERA DE APETITO": CRIMSON,
    "VIGILANCIA": AMBER,
    "EN APETITO": TEAL,
}

FONT_MAIN = "Calibri"
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


class KpiCard(BaseModel):
    """Tarjeta KPI estructurada para el resumen ejecutivo."""

    label: str = Field(description="Short KPI label (e.g. 'Severidad NCL / ENR').")
    value: str = Field(description="Formatted metric value (e.g. '43.00%').")
    delta: str = Field(default="", description="Comparison vs threshold or benchmark.")
    status: Literal["red", "orange", "green", "blue"] = Field(default="blue")


class ReportInput(BaseModel):
    """Structured contract to compile executive Word memorandum (.docx) and 16:9 deck (.pptx)."""

    case_id: str = Field(description="Case identifier (e.g. 'CASO-2026-0001').")
    titulo: str = Field(description="Executive action title for the portfolio verdict.")
    hallazgos: list[str] = Field(description="List of verified quantitative findings from DuckDB.")
    dictamen: str = Field(description="Final risk verdict and recommendation text.")
    rutas_graficas: list[str] = Field(
        default_factory=list,
        description="Paths to high-resolution .png charts generated for this case.",
    )
    subtitulo: str = Field(
        default="Comité de Riesgo de Portafolio · Tarjetas de Crédito Banamex",
        description="Cover subtitle.",
    )
    estado_riesgo: Literal["FUERA DE APETITO", "VIGILANCIA", "EN APETITO"] = Field(
        default="FUERA DE APETITO",
        description="Overall risk semaphore badge.",
    )
    kpis: list[KpiCard] = Field(
        default_factory=list,
        description="Up to 4 structured KPI cards for slide 2.",
    )
    tabla_metricas: list[list[str]] = Field(
        default_factory=list,
        description="Optional table rows [Metric, Verified Value, Policy Reference].",
    )
    politica_contrastada: str = Field(
        default="",
        description="Summary of the internal risk appetite policy rules contrasted via RAG.",
    )
    acciones: list[str] = Field(
        default_factory=list,
        description="Up to 3 concrete action items for the closing slide.",
    )


def _clip(text: str, max_chars: int) -> str:
    """Recorta texto limpiamente para evitar desbordamiento visual en cajas de PowerPoint."""
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "…"


def _set_slide_bg(slide, color: RGBColor) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_rect(
    slide,
    left,
    top,
    width,
    height,
    fill_color: RGBColor,
    line_color: RGBColor | None = None,
    rounded: bool = False,
):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if line_color is not None:
        shape.line.color.rgb = line_color
        shape.line.width = Pt(1.0)
    else:
        shape.line.fill.background()
    if rounded and shape.adjustments:
        shape.adjustments[0] = 0.08
    return shape


def _add_textbox(
    slide,
    left,
    top,
    width,
    height,
    text: str,
    font_size: int = 12,
    bold: bool = False,
    color: RGBColor = SLATE,
    align=PP_ALIGN.LEFT,
    valign=MSO_ANCHOR.TOP,
):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = valign
    tf.margin_left = Inches(0.05)
    tf.margin_right = Inches(0.05)
    tf.margin_top = Inches(0.03)
    tf.margin_bottom = Inches(0.03)
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = FONT_MAIN
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = color
    return tb


def _add_slide_chrome(
    slide,
    section_tag: str,
    title: str,
    case_id: str,
    page_num: int,
    total_pages: int = 5,
) -> None:
    """Agrega barra corporativa superior, encabezado de acción y pie institucional."""
    _set_slide_bg(slide, BG_LIGHT)

    # Barra superior Navy + acento Crimson
    _add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.10), NAVY)
    _add_rect(slide, Inches(0), Inches(0), Inches(2.4), Inches(0.10), CRIMSON)

    # Etiqueta de sección y título ejecutivo
    _add_textbox(
        slide,
        Inches(0.6),
        Inches(0.24),
        Inches(9.0),
        Inches(0.28),
        section_tag.upper(),
        font_size=10,
        bold=True,
        color=CRIMSON,
    )
    _add_textbox(
        slide,
        Inches(0.6),
        Inches(0.48),
        Inches(12.1),
        Inches(0.65),
        _clip(title, 95),
        font_size=22,
        bold=True,
        color=NAVY,
    )

    # Línea divisoria sutil bajo encabezado
    _add_rect(slide, Inches(0.6), Inches(1.16), Inches(12.13), Inches(0.02), BORDER)

    # Pie de página institucional
    _add_rect(slide, Inches(0.6), Inches(7.02), Inches(12.13), Inches(0.015), BORDER)
    _add_textbox(
        slide,
        Inches(0.6),
        Inches(7.06),
        Inches(8.5),
        Inches(0.30),
        (
            f"BANAMEX · Comité de Riesgo de Portafolio | {case_id} "
            "| Generado localmente (Audit-as-Code)"
        ),
        font_size=9,
        color=MUTED,
    )
    _add_textbox(
        slide,
        Inches(10.8),
        Inches(7.06),
        Inches(1.93),
        Inches(0.30),
        f"{page_num} / {total_pages}",
        font_size=9,
        bold=True,
        color=NAVY,
        align=PP_ALIGN.RIGHT,
    )


def _derive_default_kpis(hallazgos: list[str], estado_riesgo: str) -> list[KpiCard]:
    """Construye 4 tarjetas KPI a partir de hallazgos si el llamador no pasó `kpis` explícitos."""
    cards: list[KpiCard] = []
    badge_color: Literal["red", "orange", "green", "blue"] = (
        "red"
        if estado_riesgo == "FUERA DE APETITO"
        else ("orange" if estado_riesgo == "VIGILANCIA" else "green")
    )
    for idx, item in enumerate(hallazgos[:4]):
        if ":" in item:
            lbl, val = item.split(":", 1)
            cards.append(
                KpiCard(
                    label=_clip(lbl.strip(), 28),
                    value=_clip(val.strip(), 18),
                    delta="Dato verificado DuckDB",
                    status=badge_color if idx in (1, 2) else "blue",
                )
            )
        else:
            cards.append(
                KpiCard(
                    label=f"Hallazgo #{idx + 1}",
                    value=_clip(item, 22),
                    delta="Cubo Banamex",
                    status="blue",
                )
            )
    while len(cards) < 4:
        cards.append(
            KpiCard(
                label="Estado de Apetito",
                value=estado_riesgo,
                delta=f"Límite NCL {MAX_NCL_RATE_PCT}%",
                status=badge_color,
            )
        )
    return cards


def _derive_default_actions(estado_riesgo: str) -> list[str]:
    if estado_riesgo == "FUERA DE APETITO":
        return [
            "Suspender nuevas originaciones en el segmento y congelar incrementos de línea.",
            "Ajustar corte de score y migrar campañas del canal hacia segmentos en apetito.",
            "Escalar estrategia de cobranza temprana y revisar recuperación en 30 días.",
        ]
    if estado_riesgo == "VIGILANCIA":
        return [
            "Restringir línea de crédito promedio inicial en nuevas cuentas del segmento.",
            "Monitorear semanalmente la curva S de Over30 entre MOB 3 y MOB 9.",
            "Revisar eficiencia de recuperación y costos de adquisición en comité mensual.",
        ]
    return [
        "Mantener política actual de originación con monitoreo mensual por cohorte.",
        "Evaluar pruebas controladas de incremento de línea en scores superiores.",
        "Documentar desempeño como benchmark interno de referencia.",
    ]


def ensure_templates_exist() -> tuple[Path, Path]:
    """Crea plantillas base Word y PowerPoint 16:9 en `templates/` si no existen."""
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    memo_path = TEMPLATES_DIR / "memo_template.docx"
    pptx_path = TEMPLATES_DIR / "comite_template.pptx"

    if not memo_path.exists():
        doc = DocxDocument()
        h = doc.add_heading("Memorándum Ejecutivo — Comité de Riesgo de Portafolio", level=0)
        for run in h.runs:
            run.font.color.rgb = DocxRGBColor(0x00, 0x3B, 0x71)
        p = doc.add_paragraph(
            "Banamex | Análisis de Portafolio de Tarjetas de Crédito (Audit-as-Code)"
        )
        if p.runs:
            p.runs[0].font.color.rgb = DocxRGBColor(0x47, 0x55, 0x69)
        doc.save(str(memo_path))

    if not pptx_path.exists():
        prs = Presentation()
        prs.slide_width = SLIDE_W
        prs.slide_height = SLIDE_H
        prs.save(str(pptx_path))

    return memo_path, pptx_path


def _shade_docx_cell(cell, hex_color: str) -> None:
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def _set_docx_table_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "bottom", "insideH"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), "CBD5E1")
        borders.append(el)
    tbl_pr.append(borders)


def _build_docx(
    memo_template: Path,
    out_docx: Path,
    data: ReportInput,
) -> None:
    doc = DocxDocument(str(memo_template))
    h1 = doc.add_heading(f"[{data.case_id}] {data.titulo}", level=1)
    for r in h1.runs:
        r.font.color.rgb = DocxRGBColor(0x00, 0x3B, 0x71)

    meta_p = doc.add_paragraph()
    r_badge = meta_p.add_run(
        f"Estado de Apetito: {data.estado_riesgo}  |  Fecha: {date.today().isoformat()}"
    )
    r_badge.bold = True
    r_badge.font.size = DocxPt(10)
    r_badge.font.color.rgb = (
        DocxRGBColor(0xC8, 0x10, 0x2E)
        if data.estado_riesgo == "FUERA DE APETITO"
        else DocxRGBColor(0x0F, 0x76, 0x6E)
    )

    # Tabla resumen de KPIs / métricas si existe
    rows_to_table = data.tabla_metricas or [[k.label, k.value, k.delta] for k in data.kpis]
    if rows_to_table:
        doc.add_heading("1. Resumen Cuantitativo Verificado (DuckDB)", level=2)
        tbl = doc.add_table(rows=1 + len(rows_to_table), cols=3)
        _set_docx_table_borders(tbl)
        headers = ["Métrica", "Valor Verificado", "Referencia / Delta"]
        for c_idx, h_text in enumerate(headers):
            cell = tbl.rows[0].cells[c_idx]
            _shade_docx_cell(cell, "003B71")
            p = cell.paragraphs[0]
            run = p.add_run(h_text)
            run.bold = True
            run.font.size = DocxPt(10)
            run.font.color.rgb = DocxRGBColor(0xFF, 0xFF, 0xFF)
        for r_idx, row_vals in enumerate(rows_to_table, start=1):
            bg = "F1F5F9" if r_idx % 2 == 0 else "FFFFFF"
            for c_idx in range(3):
                val = row_vals[c_idx] if c_idx < len(row_vals) else ""
                cell = tbl.rows[r_idx].cells[c_idx]
                _shade_docx_cell(cell, bg)
                p = cell.paragraphs[0]
                run = p.add_run(str(val))
                run.font.size = DocxPt(10)

    doc.add_heading("2. Hallazgos Clave", level=2)
    for item in data.hallazgos:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("3. Dictamen y Recomendación", level=2)
    for para in data.dictamen.splitlines():
        if para.strip():
            doc.add_paragraph(para.strip())

    if data.politica_contrastada:
        doc.add_heading("4. Contraste con Manual de Apetito de Riesgo", level=2)
        doc.add_paragraph(data.politica_contrastada)

    existing_imgs = [Path(p) for p in data.rutas_graficas if Path(p).exists()]
    if existing_imgs:
        doc.add_heading("5. Evidencia Visual", level=2)
        for img_path in existing_imgs:
            doc.add_paragraph(img_path.stem.replace("_", " ").title())
            doc.add_picture(str(img_path), width=DocxInches(6.2))

    doc.save(str(out_docx))


def _build_pptx(out_pptx: Path, data: ReportInput) -> None:
    """Construye una presentación ejecutiva widescreen 16:9 de 5 diapositivas estilo Comité."""
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank_layout = prs.slide_layouts[6]

    kpis = data.kpis[:4] if data.kpis else _derive_default_kpis(data.hallazgos, data.estado_riesgo)
    acciones = data.acciones[:3] if data.acciones else _derive_default_actions(data.estado_riesgo)
    badge_color = STATUS_COLORS.get(data.estado_riesgo, CRIMSON)

    # ==================================================================
    # DIAPOSITIVA 1: PORTADA EJECUTIVA (DARK NAVY HERO)
    # ==================================================================
    s1 = prs.slides.add_slide(blank_layout)
    _set_slide_bg(s1, DARK_NAVY)
    _add_rect(s1, Inches(0), Inches(0), Inches(0.26), SLIDE_H, CRIMSON)
    _add_rect(s1, Inches(9.4), Inches(0), Inches(3.933), SLIDE_H, NAVY)

    # Píldora de estado de riesgo
    pill = _add_rect(
        s1, Inches(0.85), Inches(1.25), Inches(2.9), Inches(0.46), badge_color, rounded=True
    )
    tf_p = pill.text_frame
    tf_p.vertical_anchor = MSO_ANCHOR.MIDDLE
    p_pill = tf_p.paragraphs[0]
    p_pill.alignment = PP_ALIGN.CENTER
    r_pill = p_pill.add_run()
    r_pill.text = data.estado_riesgo
    r_pill.font.name = FONT_MAIN
    r_pill.font.size = Pt(12)
    r_pill.font.bold = True
    r_pill.font.color.rgb = WHITE

    _add_textbox(
        s1,
        Inches(0.85),
        Inches(1.95),
        Inches(8.1),
        Inches(2.1),
        _clip(data.titulo, 110),
        font_size=34,
        bold=True,
        color=WHITE,
    )
    _add_textbox(
        s1,
        Inches(0.85),
        Inches(4.15),
        Inches(8.0),
        Inches(0.8),
        data.subtitulo,
        font_size=16,
        color=SOFT_BLUE,
    )

    # Tarjeta de metadatos en panel derecho
    meta_card = _add_rect(
        s1,
        Inches(9.85),
        Inches(2.1),
        Inches(3.0),
        Inches(3.2),
        DARK_NAVY,
        line_color=RGBColor(0x2B, 0x5B, 0x8A),
        rounded=True,
    )
    _add_textbox(
        s1,
        Inches(10.05),
        Inches(2.3),
        Inches(2.6),
        Inches(2.8),
        (
            f"EXPEDIENTE\n{data.case_id}\n\n"
            f"FECHA\n{date.today().isoformat()}\n\n"
            "GOBERNANZA\nDuckDB Read-Only\nAudit-as-Code (Git)"
        ),
        font_size=12,
        color=WHITE,
    )
    _ = meta_card

    # ==================================================================
    # DIAPOSITIVA 2: RESUMEN EJECUTIVO (4 KPI CARDS + TABLA CONTABLE)
    # ==================================================================
    s2 = prs.slides.add_slide(blank_layout)
    _add_slide_chrome(
        s2,
        "Resumen Ejecutivo · Cifras Verificadas",
        f"Indicadores clave del segmento ({data.case_id})",
        data.case_id,
        page_num=2,
    )

    card_w = Inches(2.88)
    card_h = Inches(1.62)
    gap = Inches(0.20)
    start_x = Inches(0.6)
    top_y = Inches(1.42)

    for idx, kpi in enumerate(kpis[:4]):
        cx = start_x + idx * (card_w + gap)
        accent = STATUS_COLORS.get(kpi.status, NAVY)
        _add_rect(s2, cx, top_y, card_w, card_h, WHITE, line_color=BORDER, rounded=True)
        _add_rect(s2, cx, top_y, card_w, Inches(0.10), accent)
        _add_textbox(
            s2,
            cx + Inches(0.14),
            top_y + Inches(0.18),
            card_w - Inches(0.28),
            Inches(0.36),
            _clip(kpi.label, 30),
            font_size=11,
            bold=True,
            color=MUTED,
        )
        _add_textbox(
            s2,
            cx + Inches(0.14),
            top_y + Inches(0.56),
            card_w - Inches(0.28),
            Inches(0.56),
            _clip(kpi.value, 20),
            font_size=24,
            bold=True,
            color=SLATE,
        )
        _add_textbox(
            s2,
            cx + Inches(0.14),
            top_y + Inches(1.16),
            card_w - Inches(0.28),
            Inches(0.36),
            _clip(kpi.delta, 36),
            font_size=10,
            bold=True,
            color=accent,
        )

    # Tabla contable estilizada en mitad inferior
    rows_data = (
        data.tabla_metricas[:6]
        if data.tabla_metricas
        else [
            [
                _clip(h.split(":")[0], 40),
                _clip(h.split(":", 1)[1].strip() if ":" in h else h, 30),
                "Verificado en DuckDB",
            ]
            for h in data.hallazgos[:5]
        ]
    )
    if rows_data:
        n_rows = 1 + len(rows_data)
        tbl_shape = s2.shapes.add_table(
            n_rows, 3, Inches(0.6), Inches(3.32), Inches(12.13), Inches(3.4)
        )
        tbl = tbl_shape.table
        tbl.columns[0].width = Inches(5.13)
        tbl.columns[1].width = Inches(3.2)
        tbl.columns[2].width = Inches(3.8)

        headers = ["Métrica del Portafolio", "Valor Verificado", "Referencia / Política"]
        for c_idx, h_text in enumerate(headers):
            cell = tbl.cell(0, c_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.RIGHT if c_idx == 1 else PP_ALIGN.LEFT
            r = p.add_run()
            r.text = h_text
            r.font.name = FONT_MAIN
            r.font.size = Pt(11)
            r.font.bold = True
            r.font.color.rgb = WHITE

        for r_idx, r_vals in enumerate(rows_data, start=1):
            bg = ROW_ALT if r_idx % 2 == 0 else WHITE
            for c_idx in range(3):
                cell = tbl.cell(r_idx, c_idx)
                cell.fill.solid()
                cell.fill.fore_color.rgb = bg
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                p = cell.text_frame.paragraphs[0]
                p.alignment = PP_ALIGN.RIGHT if c_idx == 1 else PP_ALIGN.LEFT
                r = p.add_run()
                r.text = _clip(str(r_vals[c_idx]) if c_idx < len(r_vals) else "", 52)
                r.font.name = FONT_MAIN
                r.font.size = Pt(11)
                r.font.bold = c_idx == 1
                r.font.color.rgb = SLATE

    # ==================================================================
    # DIAPOSITIVA 3: EVIDENCIA VISUAL (LAYOUT 60/40 + CALLOUTS)
    # ==================================================================
    s3 = prs.slides.add_slide(blank_layout)
    _add_slide_chrome(
        s3,
        "Evidencia Visual · Comportamiento del Segmento",
        "Evolución de riesgo y hallazgos cuantitativos",
        data.case_id,
        page_num=3,
    )

    # Panel izquierdo: tarjeta contenedora para gráfica PNG
    _add_rect(
        s3,
        Inches(0.6),
        Inches(1.42),
        Inches(7.7),
        Inches(5.35),
        WHITE,
        line_color=BORDER,
        rounded=True,
    )
    existing_imgs = [Path(p) for p in data.rutas_graficas if Path(p).exists()]
    if existing_imgs:
        s3.shapes.add_picture(str(existing_imgs[0]), Inches(0.75), Inches(1.60), width=Inches(7.4))
    else:
        _add_textbox(
            s3,
            Inches(0.9),
            Inches(3.6),
            Inches(7.1),
            Inches(1.0),
            (
                "Gráfica exportada en formato interactivo Plotly (.json).\n"
                "Activa export_png=True en ejecución local para incrustar el PNG 300 DPI."
            ),
            font_size=13,
            color=MUTED,
            align=PP_ALIGN.CENTER,
        )

    # Panel derecho: 3 callout cards de insights
    _add_textbox(
        s3,
        Inches(8.55),
        Inches(1.42),
        Inches(4.15),
        Inches(0.35),
        "INSIGHTS CLAVE",
        font_size=11,
        bold=True,
        color=NAVY,
    )
    insights = data.hallazgos[:3] or ["Sin hallazgos adicionales registrados."]
    for idx, insight in enumerate(insights):
        cy = Inches(1.85) + idx * Inches(1.65)
        _add_rect(
            s3,
            Inches(8.55),
            cy,
            Inches(4.18),
            Inches(1.45),
            WHITE,
            line_color=BORDER,
            rounded=True,
        )
        _add_rect(s3, Inches(8.55), cy, Inches(0.12), Inches(1.45), CRIMSON if idx == 0 else NAVY)
        _add_textbox(
            s3,
            Inches(8.80),
            cy + Inches(0.14),
            Inches(3.80),
            Inches(1.18),
            _clip(insight, 150),
            font_size=12,
            color=SLATE,
            valign=MSO_ANCHOR.MIDDLE,
        )

    # ==================================================================
    # DIAPOSITIVA 4: CONTRASTE NORMATIVO (2 COLUMNAS)
    # ==================================================================
    s4 = prs.slides.add_slide(blank_layout)
    _add_slide_chrome(
        s4,
        "Gobernanza y Políticas Internas (RAG)",
        "Contraste del segmento frente al Manual de Apetito de Riesgo",
        data.case_id,
        page_num=4,
    )

    # Columna izquierda: Diagnóstico
    _add_rect(
        s4,
        Inches(0.6),
        Inches(1.45),
        Inches(5.9),
        Inches(5.25),
        WHITE,
        line_color=BORDER,
        rounded=True,
    )
    _add_rect(s4, Inches(0.6), Inches(1.45), Inches(5.9), Inches(0.48), NAVY)
    _add_textbox(
        s4,
        Inches(0.8),
        Inches(1.52),
        Inches(5.5),
        Inches(0.35),
        "EVIDENCIA DEL CUBO (DUCKDB)",
        font_size=12,
        bold=True,
        color=WHITE,
    )
    diag_text = "\n\n".join(f"• {_clip(h, 130)}" for h in data.hallazgos[:5])
    _add_textbox(
        s4,
        Inches(0.8),
        Inches(2.10),
        Inches(5.5),
        Inches(4.4),
        diag_text or "Sin hallazgos registrados.",
        font_size=13,
        color=SLATE,
    )

    # Columna derecha: Política Interna
    _add_rect(
        s4,
        Inches(6.83),
        Inches(1.45),
        Inches(5.9),
        Inches(5.25),
        SOFT_BLUE,
        line_color=BORDER,
        rounded=True,
    )
    _add_rect(s4, Inches(6.83), Inches(1.45), Inches(5.9), Inches(0.48), badge_color)
    _add_textbox(
        s4,
        Inches(7.03),
        Inches(1.52),
        Inches(5.5),
        Inches(0.35),
        f"POLÍTICA INTERNA · {data.estado_riesgo}",
        font_size=12,
        bold=True,
        color=WHITE,
    )
    policy_text = data.politica_contrastada or (
        f"• Límite de pérdida neta (NCL / ENR): máximo {MAX_NCL_RATE_PCT}% "
        "en cohortes maduras (MOB >= 6).\n\n"
        f"• Límite de morosidad temprana (Over30 / ENR): máximo {MAX_OVER30_RATE_PCT}% "
        "a partir de MOB 6.\n\n"
        "• Eficiencia mínima de cobranza (Recovery / GCL): 40.0%.\n\n"
        "• Regla de cuadrante: segmentos fuera de umbral requieren restricción "
        "de línea o suspensión de originación."
    )
    _add_textbox(
        s4,
        Inches(7.03),
        Inches(2.10),
        Inches(5.5),
        Inches(4.4),
        _clip(policy_text, 620),
        font_size=13,
        color=SLATE,
    )

    # ==================================================================
    # DIAPOSITIVA 5: DICTAMEN FINAL Y PLAN DE ACCIÓN
    # ==================================================================
    s5 = prs.slides.add_slide(blank_layout)
    _add_slide_chrome(
        s5,
        "Dictamen y Próximos Pasos · Validado Human-in-the-Loop",
        "Veredicto ejecutivo y plan de mitigación recomendado",
        data.case_id,
        page_num=5,
    )

    # Caja superior de Dictamen
    _add_rect(
        s5,
        Inches(0.6),
        Inches(1.42),
        Inches(12.13),
        Inches(2.45),
        WHITE,
        line_color=BORDER,
        rounded=True,
    )
    _add_rect(s5, Inches(0.6), Inches(1.42), Inches(0.16), Inches(2.45), badge_color)
    _add_textbox(
        s5,
        Inches(0.95),
        Inches(1.55),
        Inches(11.5),
        Inches(0.32),
        f"DICTAMEN DEL ANALISTA ({data.estado_riesgo})",
        font_size=11,
        bold=True,
        color=badge_color,
    )
    _add_textbox(
        s5,
        Inches(0.95),
        Inches(1.90),
        Inches(11.55),
        Inches(1.85),
        _clip(data.dictamen, 520),
        font_size=13,
        color=SLATE,
    )

    # 3 Tarjetas numeradas de Plan de Acción
    _add_textbox(
        s5,
        Inches(0.6),
        Inches(4.08),
        Inches(6.0),
        Inches(0.32),
        "PLAN DE ACCIÓN INMEDIATO",
        font_size=11,
        bold=True,
        color=NAVY,
    )
    act_w = Inches(3.88)
    act_gap = Inches(0.245)
    for idx, step_text in enumerate(acciones[:3]):
        ax = Inches(0.6) + idx * (act_w + act_gap)
        ay = Inches(4.48)
        _add_rect(s5, ax, ay, act_w, Inches(2.25), WHITE, line_color=BORDER, rounded=True)
        num_badge = _add_rect(
            s5,
            ax + Inches(0.18),
            ay + Inches(0.18),
            Inches(0.55),
            Inches(0.42),
            NAVY,
            rounded=True,
        )
        tf_n = num_badge.text_frame
        tf_n.vertical_anchor = MSO_ANCHOR.MIDDLE
        pn = tf_n.paragraphs[0]
        pn.alignment = PP_ALIGN.CENTER
        rn = pn.add_run()
        rn.text = f"0{idx + 1}"
        rn.font.name = FONT_MAIN
        rn.font.size = Pt(12)
        rn.font.bold = True
        rn.font.color.rgb = WHITE

        _add_textbox(
            s5,
            ax + Inches(0.18),
            ay + Inches(0.72),
            act_w - Inches(0.36),
            Inches(1.38),
            _clip(step_text, 140),
            font_size=12,
            color=SLATE,
        )

    prs.save(str(out_pptx))


@tool(args_schema=ReportInput)
def compilar_entregables_ejecutivos(
    case_id: str,
    titulo: str,
    hallazgos: list[str],
    dictamen: str,
    rutas_graficas: list[str] | None = None,
    subtitulo: str = "Comité de Riesgo de Portafolio · Tarjetas de Crédito Banamex",
    estado_riesgo: Literal["FUERA DE APETITO", "VIGILANCIA", "EN APETITO"] = "FUERA DE APETITO",
    kpis: list[KpiCard] | None = None,
    tabla_metricas: list[list[str]] | None = None,
    politica_contrastada: str = "",
    acciones: list[str] | None = None,
) -> str:
    """Compile styled executive Memorandum (.docx) and 5-slide 16:9 Committee Deck (.pptx)."""
    memo_tpl, _ = ensure_templates_exist()
    case_dir = CASES_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    payload = ReportInput(
        case_id=case_id,
        titulo=titulo,
        hallazgos=hallazgos,
        dictamen=dictamen,
        rutas_graficas=rutas_graficas or [],
        subtitulo=subtitulo,
        estado_riesgo=estado_riesgo,
        kpis=kpis or [],
        tabla_metricas=tabla_metricas or [],
        politica_contrastada=politica_contrastada,
        acciones=acciones or [],
    )

    out_docx = case_dir / f"{case_id}_memorandum.docx"
    out_pptx = case_dir / f"{case_id}_comite.pptx"

    _build_docx(memo_tpl, out_docx, payload)
    _build_pptx(out_pptx, payload)

    return json.dumps(
        {
            "case_id": case_id,
            "ruta_docx": str(out_docx),
            "ruta_pptx": str(out_pptx),
            "slides_generadas": 5,
            "formato": "16:9 Widescreen",
            "graficas_incluidas": [p for p in payload.rutas_graficas if Path(p).exists()],
        },
        ensure_ascii=False,
    )
