# Instrucciones para GitHub Copilot — BankAgent

Sigue estrictamente las reglas definidas en `AGENTS.md` y `docs/guias/CONVENCIONES.md`:

- **PEP 8 (`ruff`):** Máximo 99 caracteres por línea, `snake_case` para archivos/funciones/variables (sin `camelCase` ni acentos), `PascalCase` para clases, `UPPER_SNAKE_CASE` para constantes, sin `print()` sueltos al importar.
- **Arquitectura en capas y SSOT:** No duplicar conexiones a DuckDB, gráficas Plotly ni plantillas. Reutilizar `src/skills/cubo_sql_tools.py`, `src/skills/viz_tools.py` y `templates/`. No importar `streamlit` dentro de `src/skills/`.
- **Seguridad y Sandbox Bancario:** Solo Ollama local (`OLLAMA_BASE_URL`), `DuckDB(read_only=True)`, sin `shell=True`/`eval`/`exec`, ChromaDB solo para documentos de texto (nunca `.csv`), y estricto dominio financiero/bancario.
- **Contratos Pydantic:** Toda tool debe validar entradas antes de ejecutar y devolver errores como JSON (`{"error": "...", "disponibles": [...]}`).
- **Pruebas y Docs:** Incluir pruebas unitarias en `tests/` y actualizar `docs/contexto/` y `docs/arquitectura/ARQUITECTURA_Y_LIBRERIAS.md` ante nuevos módulos o dependencias.
