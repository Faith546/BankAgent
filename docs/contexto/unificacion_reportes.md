# Unificación del Sistema de Reportes (SSOT + Renderer Pattern)

* **Fecha:** 2026-11-27
* **Contexto:** Tras el PR #14 coexistían dos generadores independientes (`src/skills/report_tools.py` y `src/skills/reporte/generar.py`) con paletas distintas (`#003B71`/`#C8102E` vs. `#0E3A47`/`#E4002B`), plantillas duplicadas y formatos partidos (`.docx`/`.pptx` en uno, `.docx`/`.html`/`.pdf` en el otro).

## Qué se unificó
1. **Paleta corporativa única (`BANAMEX_PALETTE` en `src/config.py`):** Fuente única de verdad compartida por `report_tools.py` y `reporte/generar.py` (`#003B71` Navy, `#C8102E` Crimson, `#0F766E` Teal, `#D97706` Amber).
2. **Plantillas centralizadas (`templates/`):** `reporte/generar.py` prioriza `templates/memo_template.docx` (con respaldo a `plantilla.docx`).
3. **Todos los formatos en ambos flujos (`.docx` + `.pptx` 16:9 + `.html` + `.pdf`):**
   * `compilar_entregables_ejecutivos` en `src/skills/report_tools.py` ahora también genera `.html` y `.pdf` corporativos vía `xhtml2pdf`.
   * `armar_archivos` en `src/skills/reporte/generar.py` ahora invoca `build_pptx_deck` de `report_tools.py` para generar también la presentación ejecutiva 16:9 de 5 diapositivas.
4. **Fachada única hacia la UI:** `app/streamlit_app.py` importa exclusivamente desde `src/skills/report_tools.py` (`compilar_entregables_ejecutivos`, `generar_reporte_chat`, `editar_reporte_chat`, `grafica_chat`) y ofrece descarga de **Word (`.docx`)**, **Presentación (`.pptx`)** y **PDF (`.pdf`)** tanto en *Dictamen* como en *Resultados*.

## Cómo probarlo
```powershell
uv run ruff format --check src app tests
uv run ruff check src app tests
uv run pytest tests/test_db_reading.py tests/test_skills_and_guardrails.py tests/test_pr14_modules.py -v
```
