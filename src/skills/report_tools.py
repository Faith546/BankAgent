"""Skill 4: Generador de plantillas y compilador de entregables ejecutivos (.docx y .pptx)."""

from __future__ import annotations

import json
from pathlib import Path

from docx import Document as DocxDocument
from docx.shared import Inches
from langchain_core.tools import tool
from pptx import Presentation
from pptx.util import Inches as PptxInches
from pydantic import BaseModel, Field

from src.config import CASES_DIR, TEMPLATES_DIR


class ReportInput(BaseModel):
    """Parámetros para compilar el memorándum Word y la presentación PowerPoint."""

    case_id: str = Field(description="Identificador del caso (ej. 'CASO-2026-0001').")
    titulo: str = Field(description="Título ejecutivo del dictamen de portafolio.")
    hallazgos: list[str] = Field(description="Lista de hallazgos cuantitativos verificados.")
    dictamen: str = Field(description="Texto completo del dictamen y recomendación final.")
    rutas_graficas: list[str] = Field(
        default_factory=list,
        description="Lista de rutas a archivos .png de gráficas generadas para el caso.",
    )


def ensure_templates_exist() -> tuple[Path, Path]:
    """Crea plantillas base Word y PowerPoint en `templates/` si no existen."""
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    memo_path = TEMPLATES_DIR / "memo_template.docx"
    pptx_path = TEMPLATES_DIR / "comite_template.pptx"

    if not memo_path.exists():
        doc = DocxDocument()
        doc.add_heading("Memorándum Ejecutivo — Comité de Riesgo de Portafolio", level=0)
        doc.add_paragraph("Banamex | Análisis de Portafolio de Tarjetas de Crédito")
        doc.save(str(memo_path))

    if not pptx_path.exists():
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "Comité de Riesgo de Portafolio — Banamex"
        if len(slide.placeholders) > 1:
            slide.placeholders[1].text = "Plantilla Base Ejecutiva"
        prs.save(str(pptx_path))

    return memo_path, pptx_path


def _build_docx(
    memo_template: Path,
    out_docx: Path,
    case_id: str,
    titulo: str,
    hallazgos: list[str],
    dictamen: str,
    rutas_graficas: list[str],
) -> None:
    doc = DocxDocument(str(memo_template))
    doc.add_heading(f"[{case_id}] {titulo}", level=1)

    doc.add_heading("1. Hallazgos Cuantitativos", level=2)
    for item in hallazgos:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("2. Dictamen y Recomendación", level=2)
    for para in dictamen.splitlines():
        if para.strip():
            doc.add_paragraph(para.strip())

    existing_imgs = [Path(p) for p in rutas_graficas if Path(p).exists()]
    if existing_imgs:
        doc.add_heading("3. Evidencia Visual", level=2)
        for img_path in existing_imgs:
            doc.add_paragraph(img_path.stem.replace("_", " ").title())
            doc.add_picture(str(img_path), width=Inches(6.0))

    doc.save(str(out_docx))


def _build_pptx(
    pptx_template: Path,
    out_pptx: Path,
    case_id: str,
    titulo: str,
    hallazgos: list[str],
    dictamen: str,
    rutas_graficas: list[str],
) -> None:
    prs = Presentation(str(pptx_template))

    # Diapositiva 1: Portada (reutiliza la primera diapositiva de la plantilla)
    cover = prs.slides[0]
    cover.shapes.title.text = titulo
    if len(cover.placeholders) > 1:
        cover.placeholders[1].text = f"Caso: {case_id} | Comité de Riesgo Banamex"

    # Diapositiva 2: Hallazgos Cuantitativos
    s2 = prs.slides.add_slide(prs.slide_layouts[1])
    s2.shapes.title.text = "Hallazgos Cuantitativos"
    tf2 = s2.placeholders[1].text_frame
    tf2.clear()
    for idx, item in enumerate(hallazgos[:6]):
        p = tf2.paragraphs[0] if idx == 0 else tf2.add_paragraph()
        p.text = item

    # Diapositiva 3: Evidencia Visual
    s3 = prs.slides.add_slide(prs.slide_layouts[5])
    s3.shapes.title.text = "Evidencia Visual del Portafolio"
    existing_imgs = [Path(p) for p in rutas_graficas if Path(p).exists()]
    if existing_imgs:
        s3.shapes.add_picture(str(existing_imgs[0]), PptxInches(0.8), PptxInches(1.5), width=PptxInches(8.4))

    # Diapositiva 4: Dictamen y Plan de Acción
    s4 = prs.slides.add_slide(prs.slide_layouts[1])
    s4.shapes.title.text = "Dictamen y Recomendación"
    tf4 = s4.placeholders[1].text_frame
    tf4.clear()
    lines = [ln.strip() for ln in dictamen.splitlines() if ln.strip()][:8]
    for idx, ln in enumerate(lines):
        p = tf4.paragraphs[0] if idx == 0 else tf4.add_paragraph()
        p.text = ln

    prs.save(str(out_pptx))


@tool(args_schema=ReportInput)
def compilar_entregables_ejecutivos(
    case_id: str,
    titulo: str,
    hallazgos: list[str],
    dictamen: str,
    rutas_graficas: list[str] | None = None,
) -> str:
    """Genera el Memorándum (.docx) y la Presentación de 4 diapositivas (.pptx) del caso."""
    memo_tpl, pptx_tpl = ensure_templates_exist()
    case_dir = CASES_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    out_docx = case_dir / f"{case_id}_memorandum.docx"
    out_pptx = case_dir / f"{case_id}_comite.pptx"
    imgs = rutas_graficas or []

    _build_docx(memo_tpl, out_docx, case_id, titulo, hallazgos, dictamen, imgs)
    _build_pptx(pptx_tpl, out_pptx, case_id, titulo, hallazgos, dictamen, imgs)

    return json.dumps(
        {
            "case_id": case_id,
            "ruta_docx": str(out_docx),
            "ruta_pptx": str(out_pptx),
            "graficas_incluidas": [p for p in imgs if Path(p).exists()],
        },
        ensure_ascii=False,
    )
