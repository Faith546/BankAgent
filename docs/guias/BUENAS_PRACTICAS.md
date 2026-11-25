# Buenas Prácticas de Ingeniería — BankAgent

Estándares técnicos obligatorios para mantener código limpio, seguro, reproducible y defendible ante revisión académica o corporativa.

---

## 1. Estándar de Código Python (PEP 8 Estricto)

* **Formato y Lint:** Todo el código en `src/`, `app/` y `tests/` debe pasar con **0 errores**:
  ```powershell
  uv run ruff format src app tests
  uv run ruff check src app tests
  ```
* **Reglas activas en `pyproject.toml`:** `line-length = 99`, reglas `E`/`W` (PEP 8), `F` (Pyflakes), `I` (orden de imports) y `N` (convenciones de nombres PEP 8: `snake_case` para funciones/variables, `PascalCase` para clases, `UPPER_SNAKE_CASE` para constantes).
* **Tipado y Docstrings:** Usar *type hints* (`from __future__ import annotations`) en todas las funciones públicas y docstrings claros de una línea (recuerda: en `@tool`, el docstring es parte del prompt que lee el LLM).

---

## 2. Diseño de Contratos, Prompts y Tools

* **Prompt Engineering = Contratos:** Un prompt y un esquema de herramienta no son texto casual; definen **rol, entradas válidas, salidas esperadas, manejo de errores y criterio de parada**.
* **Prompt y `description` en inglés, respuesta al usuario en español:** Ahorra ~1.8x tokens en la ventana de contexto (`8,192`) y mejora precisión de *tool calling*.
* **Errores como datos, nunca crashes silenciosos:** Si el LLM pasa un filtro inválido (ej. `"Clásica"` con acento o un canal inexistente), la tool valida antes de consultar DuckDB y devuelve `{"error": "...", "disponibles": [...]}` para que el modelo se autocorrija.
* **Parámetros deterministas en Ollama:** Usar `temperature = 0.0` y `reasoning = False` (`think: False` en `qwen3.5:9b`) para evitar respuestas vacías y maximizar reproducibilidad.
* **Separar contenido de diseño:** En reportes (`.docx`/`.pptx`), el LLM entrega datos estructurados (`ReportInput` / `KpiCard`) y Python controla el layout visual.

---

## 3. Seguridad, Sandbox y Dominio Bancario

* **Solo dominio financiero/bancario:** Toda nueva skill, validación de gráficas o generador de contratos debe rechazar solicitudes ajenas a banca, finanzas o riesgo de crédito (en el prompt y en validadores Python).
* **Separación estricta de motores de datos:**
  * `DuckDB` (`read_only=True`): exclusivo para datos numéricos tabulares. Prohibido DDL/DML (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `COPY`).
  * `ChromaDB`: exclusivo para documentos normativos de texto (`.md` / `.pdf`). **Jamás vectorizar archivos `.csv`.**
  * `SQLite` (`checkpoints.db`): exclusivo para estado de conversación de LangGraph (`thread_id`).
* **Entorno Sandbox:**
  * Cero APIs externas de IA (solo `http://localhost:11434`).
  * Cero `shell=True`, `eval()` o `exec()` sobre entradas del modelo.
  * Subprocesos permitidos únicamente en lista blanca dentro de `src/skills/git_governance.py` (`shell=False`).
* **Los 5 Guardrails del bucle agéntico (`src/agent/graph.py`):** Lista blanca (`TOOL_MAP`), tope de vueltas (`AGENT_MAX_TURNS`), antirrepetición (`seen_calls`), validación previa + guardrail numérico Regex (`guardrails.py`), y pausa *Human-in-the-Loop*.

---

## 4. Reglas Matemáticas y de Datos del Cubo

* **Trampa 1 (Volumen inicial):** Nunca sumar `ACCOUNTS` ni `CREDITLINESAMTS` a lo largo de todos los `MOB`. Filtrar siempre `WHERE MOB = 0`.
* **Trampa 2 (Tasas ponderadas):** Nunca usar `AVG(ratio)`. Calcular siempre razón de sumas: `(SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0`.
* **No saturar RAM (16 GB):** Ejecutar agregaciones y filtros dentro de DuckDB; evitar cargar el CSV completo de >1M filas en DataFrames de Pandas.

---

## 5. Pruebas y Benchmarks (Rigor Científico)

* **Pruebas deterministas (offline, <5 s):** `uv run pytest tests/test_db_reading.py tests/test_skills_and_guardrails.py -v` valida identidades contables, bloqueos SQL, filtros, guardrails y cuadre del Golden Dataset.
* **Pruebas de agentes por efecto (no por comparación literal de texto):** Usar `uv run python -m tests.smoke_test_agent` (4 efectos clave) y `--benchmark` sobre `tests/golden_dataset.json` para respaldar con métricas cada cambio de modelo, prompt o contrato.

---

## 6. Interfaz en Streamlit

* **Theming nativo primero:** Centralizar colores, tipografía, bordes y sidebar en `.streamlit/config.toml` en lugar de inyectar CSS frágil.
* **Rendimiento:** Cachear consultas de lectura de DuckDB con `@st.cache_data(ttl=300)` y mantener `st.session_state` limpio por caso/hilo.
