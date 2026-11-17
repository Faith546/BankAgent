# Plan de Tareas — MVP Asistente Agéntico de Portafolio (Banamex)

Este tablero sigue estrictamente el plan iterativo de [`docs/MVP_CONTEXT_AGENT_BANAMEX.md`](MVP_CONTEXT_AGENT_BANAMEX.md). Se completa **una etapa a la vez**, validando en terminal antes de avanzar.

---

## Paso 0: Prerrequisitos y Entorno (Completar antes de programar)
- [x] **T0.1** Generar [`README.md`](../README.md) con prerrequisitos (`Ollama`, `uv`, GPU `nvidia-smi`, rutas de datos y explicación de LangChain/LangGraph vs. MCP).
- [x] **T0.2** Crear [`pyproject.toml`](../pyproject.toml) con las dependencias oficiales del MVP.
- [x] **T0.3 (Manual - Usuario)** Instalar Ollama, descargar modelo LLM (`qwen3.5:9b` o `qwen2.5:7b-instruct-q4_K_M`) y embeddings (`nomic-embed-text`).
- [x] **T0.4 (Manual - Usuario)** Instalar `uv`, ejecutar `uv venv --python 3.11` y `uv sync`.
- [x] **T0.5 (Manual - Usuario)** Colocar el CSV y el diccionario `.xlsx` en `data/raw/` (y confirmar si se usará `base_cards_sintetica.csv` o `base_cards_sintetica_mini.csv`).

---

## Etapa 1: Base de Datos DuckDB, Lectura del Dato y Conexión Ollama
*Objetivo: Lectura impecable del cubo, métricas cuadradas al centavo y pruebas de humo con Ollama local.*
- [x] **T1.1** Crear `.gitignore` (excluir `.venv`, `data/duckdb/*.duckdb`, `data/chromadb/`, `outputs/tmp/`).
- [x] **T1.2** Crear `src/config.py` (rutas, modelo Ollama, `temperature=0.1`, `num_ctx`, umbrales de negocio).
- [x] **T1.3** Crear `src/data/dictionary_loader.py` para leer `Base Cards para TEC - Diccionario de Variables.xlsx` y generar contexto Markdown.
- [x] **T1.4** Crear `src/data/init_db.py`:
  - Aplicar `TRIM()` a columnas `VARCHAR`.
  - Crear `COHORT_ID`, tabla persistente `cubo` y vista `v_cubo_metricas` en `data/duckdb/cubo_banamex.duckdb`.
  - Imprimir tabla de auditoría con conteo de filas, cohortes y sumas de control.
- [x] **T1.5** Crear `tests/test_db_reading.py` (identidades contables `NCL = GCL - RECOVERY`, `EXPENSES_ACQ = 0` para `MOB > 0`, agregación `MOB = 0`).
- [x] **T1.6** Crear `tests/test_prompts_ollama.py` (prueba de humo con `ChatOllama` y 3 prompts reales sobre el esquema DuckDB — pendiente ejecución local por el usuario).

---

## Etapa 2: Skills, Guardrails y Grafo en LangGraph
*Objetivo: Dotar al LLM de herramientas tipadas con Pydantic, RAG normativo y flujo cíclico con pausa Human-in-the-Loop.*
- [x] **T2.1** Crear `data/politicas_internas/manual_apetito_riesgo.md` con umbrales de negocio (ej. `NCL/ENR <= 15%`, `Over30 <= 25%` desde `MOB 6`).
- [x] **T2.2** Crear `src/skills/cubo_sql_tools.py` (`obtener_resumen_portafolio`, `obtener_curva_maduracion`, `ejecutar_sql_select_seguro` con `read_only=True`, regex anti-DDL/DML y autocorrección).
- [x] **T2.3** Crear `src/skills/viz_tools.py` (6 gráficas Plotly + PNG 300 DPI con Kaleido en `outputs/cases/{case_id}/charts/`).
- [x] **T2.4** Crear `src/skills/rag_tools.py` (`consultar_politica_riesgo` sobre ChromaDB local + `nomic-embed-text`).
- [x] **T2.5** Crear `src/skills/report_tools.py` (`ensure_templates_exist()` + `compilar_entregables_ejecutivos` para `.docx` y `.pptx`).
- [x] **T2.6** Crear `src/skills/git_governance.py` (`subprocess.run(..., shell=False)` para commits de auditoría y `git diff`).
- [x] **T2.7** Crear `src/agent/prompts.py`, `src/agent/guardrails.py` (verificación Regex de cifras) y `src/agent/graph.py` (`StateGraph` con `SqliteSaver` e interrupción Human-in-the-Loop).

---

## Etapa 3: Consola Híbrida en Streamlit
*Objetivo: Interfaz de 3 paneles para analistas de riesgo.*
- [x] **T3.1** Crear `app/streamlit_app.py`:
  - **Panel Izquierdo:** Selector de casos / alertas paramétricas desde DuckDB.
  - **Panel Central:** KPIs, gráficas interactivas Plotly, SQL ejecutado, editor de dictamen y botones `[Aprobar y Generar DOCX/PPTX + Git Commit]` y `[Ver Git Diff]`.
  - **Panel Derecho:** Chat copiloto investigador conectado al grafo de LangGraph.

---

## Etapa 4 (Futura / Post-MVP): Módulo de Machine Learning
*Nota: Se implementará únicamente después de validar las Etapas 1, 2 y 3.*
- [ ] **T4.1** Crear `src/ml/anomaly_detector.py` (`IsolationForest` normalizado por `MOB`, `K-Means`, `DecisionTreeClassifier`).

