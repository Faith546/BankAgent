# BankAgent — Asistente Agéntico de Análisis de Portafolio (Banamex MVP)

Asistente agéntico **100% local** para el análisis de cohortes (`VINTAGE` / `MOB`) y segmentos de tarjetas de crédito. Combina consultas analíticas en **DuckDB**, razonamiento con **Ollama** local, búsqueda normativa en **ChromaDB (RAG)**, gráficas ejecutivas en **Plotly/Kaleido**, generación de reportes (`.docx` / `.pptx`), trazabilidad en **Git** (*Audit-as-Code*) e interfaz híbrida de 3 paneles en **Streamlit** con supervisión humana (*Human-in-the-Loop*).

---

## 1. Arquitectura rápida (¿Se necesita MCP?)

**No necesitas instalar ni configurar ningún servidor MCP para usar este proyecto.**

* **DuckDB (`data/duckdb/`):** Almacena el cubo numérico (`>1M` filas) en modo solo lectura para el agente. Nunca se vectoriza el CSV.
* **ChromaDB (`data/chromadb/`):** Almacena únicamente los documentos normativos de políticas internas (`manual_apetito_riesgo.md`) usando embeddings `nomic-embed-text`.
* **LangChain + LangGraph (`src/agent/graph.py`):** Orquestan al modelo en Ollama con herramientas tipadas (`@tool` + Pydantic), guardrail anti-alucinación de cifras y memoria persistente en `SqliteSaver` (`checkpoints.db`) con pausa *Human-in-the-Loop*.
* **MCP:** No hace falta porque Streamlit y las herramientas corren en el mismo proceso Python en memoria.

---

## 2. Prerrequisitos (Instalar una sola vez)

1. **Git** y **drivers NVIDIA** (recomendado GPU de al menos 8 GB VRAM; funciona también en CPU más lento):
   ```powershell
   git --version
   nvidia-smi
   ```
2. **Ollama** ([ollama.com/download](https://ollama.com/download)):
   Descarga el modelo LLM principal y el modelo de embeddings:
   ```powershell
   ollama pull qwen3.5:9b
   # Alternativa más ligera si tienes 8 GB VRAM y quieres más holgura:
   # ollama pull qwen2.5:7b-instruct-q4_K_M

   ollama pull nomic-embed-text
   ```
   *(Si usas un modelo distinto a `qwen3.5:9b`, define la variable de entorno `$env:OLLAMA_MODEL="qwen2.5:7b-instruct-q4_K_M"` antes de correr la app).*
3. **`uv` (Astral)** para gestionar Python 3.11 y dependencias:
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
   *(En macOS / Linux / WSL2: `curl -LsSf https://astral.sh/uv/install.sh | sh`)*

---

## 3. Guía de Arranque para el Equipo (Después de `git clone`)

> **Importante sobre los datos:** Por tamaño (>100 MB) y privacidad, `.gitignore` excluye `data/raw/*.csv`, `data/duckdb/*.duckdb`, `data/chromadb/` y `data/state/*.db`. Pide al equipo los archivos fuente y colócalos en `data/raw/`:
> * `data/raw/base_cards_sintetica.csv` *(o `base_cards_sintetica_mini.csv`)*
> * `data/raw/Base Cards para TEC - Diccionario de Variables.xlsx`

### Paso 1: Crear entorno virtual e instalar librerías
```powershell
uv venv --python 3.11
uv sync
```

### Paso 2: Construir la base de datos DuckDB
Ingesta el CSV con limpieza `TRIM()`, crea `COHORT_ID`, la tabla `cubo` y la vista `v_cubo_metricas`:
```powershell
uv run python -m src.data.init_db
```

### Paso 3: Indexar políticas internas en ChromaDB (requiere Ollama abierto)
```powershell
uv run python -c "from src.skills.rag_tools import ingest_policies; print('Secciones indexadas:', ingest_policies())"
```

### Paso 4: Verificar pruebas unitarias y Smoke Test / Benchmark
```powershell
uv run pytest tests/test_db_reading.py tests/test_skills_and_guardrails.py -v
```
*(Con Ollama abierto, corre las 4 pruebas de efecto de tool-calling o el benchmark completo de 10 casos del Golden Dataset):*
```powershell
uv run python -m tests.smoke_test_agent
uv run python -m tests.smoke_test_agent --benchmark
```

### Paso 5: Abrir la Consola Híbrida en Streamlit
Con **Ollama** corriendo en segundo plano:
```powershell
uv run streamlit run app/streamlit_app.py
```
Se abrirá en `http://localhost:8501` con 3 paneles:
1. **Izquierda (Alertas del Cubo):** Segmentos maduros (`MOB >= 6`) fuera de apetito (`NCL/ENR > 15%` u `Over30/ENR > 25%`).
2. **Centro (Evidencia y Dictamen):** KPIs desde DuckDB, 6 gráficas interactivas de Plotly, SQL ejecutado, editor de dictamen *Human-in-the-Loop*, descarga de `.docx`/`.pptx` y auditoría `git commit` / `git diff`.
3. **Derecha (Copiloto Investigador):** Chat conectado a LangGraph para consultas ad-hoc sobre el cubo o las políticas.

---

## 4. Estructura del Proyecto

```text
BankAgent/
├── app/
│   └── streamlit_app.py                # Consola Híbrida de 3 paneles
├── data/
│   ├── raw/                            # CSV del cubo y Excel diccionario (no versionado)
│   ├── duckdb/                         # Base generada cubo_banamex.duckdb (no versionado)
│   ├── chromadb/                       # Índice vectorial local (no versionado)
│   ├── state/                          # Checkpoints de LangGraph (no versionado)
│   └── politicas_internas/
│       └── manual_apetito_riesgo.md    # Reglas de negocio para RAG
├── docs/
│   ├── ARQUITECTURA_Y_LIBRERIAS.md     # Mapa de arquitectura, diagramas y librerías
│   ├── MVP_CONTEXT_AGENT_BANAMEX.md    # Guía maestra de arquitectura
│   └── TASKS.md                        # Tablero de tareas por etapas
├── src/
│   ├── config.py                       # Rutas, modelo Ollama y umbrales
│   ├── data/                           # Ingesta DuckDB y cargador de diccionario
│   ├── skills/                         # Tools: SQL, Plotly, RAG, DOCX/PPTX y Git
│   └── agent/                          # System prompt, guardrail numérico y LangGraph
└── tests/                              # Pruebas unitarias y smoke test de Ollama
```
