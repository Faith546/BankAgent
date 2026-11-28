# AGENTS.md — Instrucciones Obligatorias para Agentes de IA en BankAgent

Antes de escribir o modificar código en este repositorio, **debes leer y cumplir estrictamente**:
- `docs/guias/CONVENCIONES.md` (patrones de diseño, nombrado, fronteras por capa y Definition of Done)
- `docs/guias/COLABORACION_Y_CONTEXTO_IA.md` (dónde guardar contexto y actualizaciones)
- `docs/guias/BUENAS_PRACTICAS.md` (PEP 8, contratos Pydantic, seguridad sandbox y pruebas)

## Reglas No Negociables
1. **PEP 8 obligatorio (`line-length = 99`):** Antes de terminar cualquier tarea, ejecuta y garantiza 0 errores en:
   - `uv run ruff format --check src app tests`
   - `uv run ruff check src app tests`
2. **Nombrado:** Siempre `snake_case` para archivos, carpetas, funciones y variables (sin `camelCase`, sin espacios ni acentos en nombres de archivo). Clases en `PascalCase`, constantes en `UPPER_SNAKE_CASE`. Prohibido dejar `print(...)` al nivel de módulo.
3. **SSOT y Cero Duplicidad:**
   - Todas las consultas numéricas al cubo salen de `src/skills/cubo_sql_tools.py` (DuckDB `read_only=True`).
   - Todas las gráficas usan `src/skills/viz_tools.py` con la paleta oficial Banamex (`#003B71`, `#C8102E`, `#0F766E`, `#D97706`).
   - Todas las plantillas viven en `templates/`. No importes `streamlit` dentro de `src/skills/`.
4. **Sandbox y Dominio Exclusivo Bancario:**
   - Cero llamadas a APIs externas de IA (solo Ollama en `OLLAMA_BASE_URL`).
   - Prohibido `shell=True`, `eval`, `exec`, DDL/DML en DuckDB y vectorizar `.csv` en ChromaDB.
   - Rechazar cualquier tool, contrato o análisis ajeno al dominio financiero/bancario.
5. **Contratos y Pruebas:**
   - Toda tool nueva usa `Pydantic` (`args_schema`), `description` en inglés conciso y devuelve errores estructurados como datos (`{"error": "...", "disponibles": [...]}`).
   - Toda funcionalidad nueva incluye pruebas en `tests/` y valida `uv run pytest`.
6. **Trazabilidad de Contexto:**
   - Si agregas módulos, librerías en `pyproject.toml` o variables en `src/config.py`, actualiza `docs/arquitectura/ARQUITECTURA_Y_LIBRERIAS.md` y deja una nota breve en `docs/contexto/`.
