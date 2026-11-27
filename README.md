# BankAgent — Asistente Agéntico de Análisis de Portafolio (Banamex)

> **Punto de entrada central del repositorio.** Aquí encuentras cómo ejecutar el proyecto, cómo está organizado, qué consideraciones técnicas debes respetar y dónde consultar/dejar contexto si trabajas en equipo o con IA.

Asistente agéntico **100% local** para analizar cohortes (`VINTAGE` / `MOB`) y segmentos de tarjetas de crédito. Combina **DuckDB** (datos numéricos), **Ollama** (LLM local), **LangGraph** (orquestación con 5 guardrails y *Human-in-the-Loop*), **ChromaDB** (RAG normativo), **Plotly/Kaleido** (visualización), **python-pptx/docx** (reportes ejecutivos 16:9), **Git** (*Audit-as-Code*) y **Streamlit** (consola híbrida).

---

## 1. Para el Equipo (Leer Primero)

Antes de hacer cambios o pedirle código a una IA, revisa estas 4 referencias clave:

* **Reglas de colaboración y dónde dejar actualizaciones/contexto (IA + Humanos):** [`docs/guias/COLABORACION_Y_CONTEXTO_IA.md`](docs/guias/COLABORACION_Y_CONTEXTO_IA.md)
* **Buenas prácticas (PEP 8, contratos, seguridad sandbox y pruebas):** [`docs/guias/BUENAS_PRACTICAS.md`](docs/guias/BUENAS_PRACTICAS.md)
* **Carpeta de contexto vivo (ADRs, handoffs y benchmarks):** [`docs/contexto/`](docs/contexto/README.md)
* **Índice completo de documentación y backlog de 13 issues:** [`docs/README.md`](docs/README.md) · [`docs/planeacion/ISSUES.md`](docs/planeacion/ISSUES.md)

---

## 2. Cómo Ejecutar el Proyecto (Paso a Paso)

### Prerrequisitos (instalar una sola vez)
1. **Git** y **drivers NVIDIA** (`nvidia-smi` — recomendado ≥ 8 GB VRAM; también corre en CPU).
2. **Ollama** ([ollama.com/download](https://ollama.com/download)) con los modelos locales:
   ```powershell
   ollama pull qwen3.5:9b
   # Alternativa más ligera (~5 GB VRAM): ollama pull qwen2.5:7b-instruct-q4_K_M
   ollama pull nomic-embed-text
   ```
3. **`uv`** (gestor de Python 3.11 y dependencias):
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
4. **Datos fuente:** Coloca en `data/raw/` los archivos proporcionados al equipo (no versionados en Git por tamaño >100 MB):
   * `data/raw/base_cards_sintetica.csv` *(o `base_cards_sintetica_mini.csv`)*
   * `data/raw/Base Cards para TEC - Diccionario de Variables.xlsx`

### Arranque después de `git clone`
```powershell
# 1. Crear entorno Python 3.11 e instalar dependencias
uv venv --python 3.11
uv sync

# 2. Construir base de datos analítica DuckDB (tabla `cubo` + vista `v_cubo_metricas`)
uv run python -m src.data.init_db

# 3. Indexar políticas internas en ChromaDB (requiere Ollama abierto)
uv run python -c "from src.skills.rag_tools import ingest_policies; print('Chunks:', ingest_policies())"

# 4. Verificar PEP 8 y pruebas unitarias
uv run ruff check src app tests
uv run pytest tests/test_db_reading.py tests/test_skills_and_guardrails.py -v

# 5. (Opcional) Smoke test de 4 efectos y benchmark del Golden Dataset con Ollama
uv run python -m tests.smoke_test_agent
uv run python -m tests.smoke_test_agent --benchmark

# 6. Levantar la consola ejecutiva en http://localhost:8501
uv run streamlit run app/streamlit_app.py
```

---

## 3. Estructura de Carpetas

```text
BankAgent/
├── .streamlit/                 # Tema corporativo nativo Banamex (config.toml)
├── app/
│   └── streamlit_app.py        # Consola ejecutiva híbrida (alertas, gráficas, dictamen, chat)
├── src/
│   ├── config.py               # Rutas, parámetros Ollama, umbrales y valores válidos del cubo
│   ├── data/                   # Ingesta DuckDB (init_db.py) y diccionario Excel
│   ├── skills/                 # Herramientas tipadas: SQL, Plotly, RAG, PPTX/DOCX y Git
│   └── agent/                  # Prompt contract (EN), guardrail numérico y grafo LangGraph
├── data/
│   ├── raw/                    # CSV fuente (ignorado en Git) y Excel diccionario
│   ├── politicas_internas/     # Manuales normativos (.md/.pdf) para RAG en ChromaDB
│   ├── duckdb/                 # Base cubo_banamex.duckdb generada localmente (ignorada)
│   ├── chromadb/               # Índice vectorial local (ignorado)
│   └── state/                  # Checkpoints SqliteSaver de LangGraph (ignorado)
├── templates/                  # Plantillas base Word y PowerPoint 16:9
├── outputs/cases/              # Expedientes auditados por caso (DOCX, PPTX, PNG, SQL, JSON)
├── tests/                      # Pruebas unitarias, Golden Dataset (10 casos) y smoke test
└── docs/
    ├── README.md               # Índice maestro de documentación
    ├── arquitectura/           # Diagramas, librerías, guardrails y contexto maestro MVP
    ├── contexto/               # Contexto vivo, ADRs, handoffs y resultados de benchmarks
    ├── guias/                  # Configuración, buenas prácticas y guía de colaboración/IA
    └── planeacion/             # Backlog oficial de 13 issues (ISSUES.md) y TASKS.md
```

---

## 4. Consideraciones Críticas del Proyecto

* **100% Local y Sandbox Bancario:** Cero APIs cloud externas; todo apunta a `http://localhost:11434`. El sistema está restringido al **dominio financiero/bancario**, sin `shell=True`, sin DDL/DML en DuckDB (`read_only=True`) y con escritura limitada a carpetas en lista blanca.
* **Separación de Motores:** `DuckDB` es exclusivo para cifras tabulares; `ChromaDB` es exclusivo para texto normativo (jamás vectorizar CSVs); `SQLite` es exclusivo para estado de conversación (`thread_id`).
* **Presupuesto de Hardware Local (8 GB VRAM / 16 GB RAM):** Se usa `num_ctx=8192`, `reasoning=False` (`think: False`) y `temperature=0.0` para evitar desbordes a RAM compartida y respuestas vacías en `qwen3.5:9b`. Todo cálculo pesado corre en DuckDB, no en Pandas.
* **Sin MCP obligatorio en el MVP:** Las tools viven desacopladas en `src/skills/` y corren en memoria; si después se requiere exponerlas a clientes externos, pueden envolverse en FastAPI o MCP sin reescribir la lógica.
* **No subir secretos ni CSVs pesados:** `.gitignore` bloquea `.env*`, `*.key`, `*.pem`, `data/*.csv`, `data/raw/*.csv`, `data/duckdb/*.duckdb`, `data/chromadb/` y `data/state/*.db`.
