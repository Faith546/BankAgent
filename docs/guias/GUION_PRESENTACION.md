# Guion de Presentación (Ejecutiva + Técnica) — BankAgent

Estructura lista para armar una presentación de **12 diapositivas**: **6 ejecutivas** (para Comité de Riesgos / Socio Formador) y **6 técnicas** (para profesores / revisión de arquitectura). Para los diagramas técnicos de respaldo, consultar [`PIPELINE_AGENTES.md`](../arquitectura/PIPELINE_AGENTES.md).

---

## Bloque A · Slides Ejecutivas (Comité de Riesgos / Socio Formador)

### Slide 1 · Portada — BankAgent: Inteligencia Agéntica Local para Portafolio de Tarjetas
* **Mensaje clave:** Asistente de análisis de riesgo de portafolio 100% local, auditable y sin fugas de datos hacia la nube.
* **Visual sugerido:** Portada corporativa Navy/Crimson (`#003B71` / `#C8102E`) con subtítulo del equipo y stack clave (`DuckDB · Ollama · LangGraph · Streamlit`).
* **Guion (30s):** *"Presentamos BankAgent: un copiloto analítico diseñado para que un analista de riesgo pase de detectar una cohorte deteriorada a emitir un dictamen fundamentado en políticas y entregables ejecutivos en minutos, corriendo 100% en infraestructura local."*

### Slide 2 · El Problema de Negocio y Qué NO Hace el Sistema
* **Bullets:**
  * Analizar **1.08 millones de filas** y **64,245 cohortes** (`VINTAGE × MOB`) manualmente en Excel/BI es lento y propenso a errores de agregación (`MOB = 0` vs. tasas ponderadas).
  * Los LLMs genéricos en la nube **no son viables en banca** por privacidad y porque **inventan cifras** cuando no tienen acceso determinista a los datos.
  * **Frontera clara:** BankAgent analiza segmentos/cohortes agregadas (cero PII de clientes individuales) y **rechaza consultas o archivos ajenos a banca**.
* **Visual sugerido:** Comparativa de 2 columnas (*Riesgos de IA genérica en la nube* vs. *Control de BankAgent local*).

### Slide 3 · Flujo del Analista (De la Alerta al Dictamen en 4 Pasos)
* **Bullets:**
  1. **Detección automática:** La barra lateral lista segmentos maduros (`MOB ≥ 6`) fuera de apetito (`NCL/ENR > 15%` u `Over30/ENR > 25%`).
  2. **Exploración visual:** 6 gráficas interactivas (Curva S, Curva J ROA, Puente P&L, Heatmap, Cuadrantes, Cobranza).
  3. **Investigación con Copiloto:** Preguntas en lenguaje natural, análisis de gráficas/PDFs adjuntos y contraste automático contra el Manual de Apetito de Riesgo.
  4. **Aprobación Humana y Entregables:** El analista edita el borrador y genera con un clic **Memorándum (`.docx`)**, **Deck 16:9 (`.pptx`)** y **PDF (`.pdf`)** con respaldo en Git.
* **Visual sugerido:** Diagrama horizontal de 4 pasos + captura real de la consola en Streamlit.

### Slide 4 · Hallazgos Reales sobre el Portafolio (Demo de Valor)
* **Bullets:**
  * Volumen monitoreado: `1,249,981` cuentas iniciales (`MOB = 0`) en 33 vintages (`202401`–`202609`).
  * Identificación inmediata de focos rojos (ej. `TMK · Young 25-30 · <130` con `43.0%` NCL/ENR; `Branch · Young < 25 · <130` con `43.72%` en `MOB ≥ 6`).
  * Identidades contables verificadas al centavo (`NCL = GCL - Recovery`; `EXPENSES_ACQ = 0` en `MOB > 0`).
* **Visual sugerido:** 4 KPI cards reales + imagen exportada de la Curva S de maduración.

### Slide 5 · Gobernanza, Privacidad y *Human-in-the-Loop*
* **Bullets:**
  * **100% Local (Sandbox):** Cero llamadas a OpenAI/cloud; inferencia en Ollama local o servidor interno con GPU.
  * **Audit-as-Code:** Cada caso guarda `queries.sql`, `evidence.json`, `draft_dictamen.md` y dos commits de Git (borrador IA vs. dictamen aprobado por el analista) con `git diff` visible.
  * **Cero acciones destructivas autónomas:** El agente solo tiene acceso `read_only=True` a DuckDB; la aprobación final siempre es humana.
* **Visual sugerido:** Captura de la pestaña *Dictamen & Human-in-the-Loop* + ejemplo de `git diff`.

### Slide 6 · Hoja de Ruta y Escalabilidad
* **Bullets:**
  * **Hoy (MVP Consolidado):** Consola híbrida, 27 pruebas automatizadas, CI/CD con PEP 8, reportes unificados (`.docx`/`.pptx`/`.pdf`), RAG dinámico y múltiples chats.
  * **Corto plazo (Issues activas):** Pruebas en servidor remoto con GPU (`num_ctx=16384`), Dockerización en sandbox, skill generadora de contratos bancarios y pipeline de limpieza/FE.
  * **Siguiente fase:** Módulo de Machine Learning (`IsolationForest`, `K-Means`) y exposición opcional vía FastAPI/MCP sin reescribir las skills.

---

## Bloque B · Slides Técnicas (Profesores / Revisión de Arquitectura)

### Slide 7 · Arquitectura de 8 Capas y Separación Estricta de Motores
* **Bullets:**
  * **DuckDB (`read_only=True`):** Motor analítico columnar para >1M filas en milisegundos sin saturar RAM (vs. Pandas).
  * **ChromaDB (`nomic-embed-text`):** Exclusivo para texto normativo y documentos por chat (prohibido vectorizar CSVs).
  * **SQLite (`SqliteSaver`):** Persistencia de estado y pausas *Human-in-the-Loop* por `thread_id`.
  * **Configuración desacoplada:** `.env.example` + `load_dotenv()` en `src/config.py` permite cambiar entre laptop (8 GB VRAM, `ctx=8192`) y servidor GPU (`ctx=16384`) sin tocar código.
* **Visual sugerido:** Diagrama de 8 capas actualizado + Pipeline Macro de [`PIPELINE_AGENTES.md`](../arquitectura/PIPELINE_AGENTES.md).

### Slide 8 · Router del Copiloto y Memoria Adaptativa (`interpretacion/` + `recuerdame/`)
* **Bullets:**
  * `leer_intencion()` usa salida estructurada Pydantic para enrutar en 5 destinos (`conversacion`, `grafica_en_pantalla`, `grafica`, `reporte`, `agente`) evitando invocar el grafo pesado en saludos simples.
  * `interpretacion/` combina `pymupdf` (PDF), `python-docx` (Word), `qwen2.5vl:7b` (visión en imágenes/PDF escaneado) y `dominio.es_del_dominio()` (rechaza archivos ajenos a banca).
  * `recuerdame/` aísla chats con compresión automática de historial y aprende el estilo preferido (*corta*, *detallada*, *tabla*) con **TF-IDF + Naive Bayes + Gradient Bandit**.
* **Visual sugerido:** Flujo del Router + tabla de recompensas del Bandit.

### Slide 9 · Anatomía del Agente en LangGraph (`src/agent/graph.py`)
* **Bullets:**
  * ¿Por qué **LangGraph** y no cadenas lineales? Permite ciclos de autocorrección SQL, control explícito de vueltas y pausas persistentes (`interrupt_before=["human_review"]`).
  * **Optimización para `qwen3.5:9b`:** `temperature=0.0` (reproducibilidad) y `reasoning=False` (`think: False`) para evitar que el modelo agote tokens pensando y devuelva respuestas vacías.
  * **Prompt Contract en inglés (`src/agent/prompts.py`):** Ahorra ~1.8x tokens en ventana de contexto, incluye glosario de negocio y reglas SQL anti-trampas (`MOB = 0`, `SUM/NULLIF`), respondiendo siempre en español.
* **Visual sugerido:** Diagrama `StateGraph` de [`PIPELINE_AGENTES.md`](../arquitectura/PIPELINE_AGENTES.md).

### Slide 10 · Defensa en Profundidad: Los 5 Guardrails Deterministas
* **Bullets:**
  1. **Lista Blanca (`TOOL_MAP`):** Ninguna función fuera del diccionario registrado puede ejecutarse (cero `eval`/`getattr`).
  2. **Tope de Vueltas (`AGENT_MAX_TURNS = 8`):** Evita bucles infinitos y fuerza cierre limpio en `_final_node`.
  3. **Antirrepetición (`seen_calls`):** Bloquea llamadas idénticas `(tool, args)` consecutivas.
  4. **Validación Previa + Errores como Datos:** Valida filtros antes de tocar DuckDB devolviendo `{"error": "...", "disponibles": [...]}`; bloquea DDL/DML vía Regex.
  5. **Guardrail Numérico + HITL:** `verify_response_numbers()` contrasta las cifras del texto final contra los JSON de DuckDB y reintenta si detecta una cifra inventada.
* **Visual sugerido:** Diagrama de capas de seguridad (5 anillos).

### Slide 11 · Patrones de Diseño, Contratos y Motor Unificado de Reportes
* **Bullets:**
  * **SSOT + DRY:** Paleta única `BANAMEX_PALETTE` en `src/config.py`, plantillas centralizadas en `templates/` y fachada única en `src/skills/report_tools.py`.
  * **Renderer / Strategy Pattern:** Separación total entre contenido (`ReportInput`, `KpiCard`, `Reporte` con `max_length`) y renderizadores (`.docx`, `.pptx` 16:9 de 5 láminas, `.html` editable y `.pdf` vía `xhtml2pdf`).
  * **Desacoplamiento futuro:** Al vivir como funciones puras en `src/skills/`, cualquier capacidad puede exponerse después vía FastAPI o MCP sin reescribir lógica de negocio.
* **Visual sugerido:** Diagrama `ReportInput -> [DOCX | PPTX 16:9 | HTML/PDF]` + muestra de las 5 slides generadas.

### Slide 12 · Rigor de Ingeniería: Calidad, CI/CD y Benchmarks
* **Bullets:**
  * **Gobernanza de código (Humanos + IA):** `AGENTS.md`, `.github/copilot-instructions.md`, `CONVENCIONES.md` y plantilla de PR.
  * **GitHub Actions CI (`.github/workflows/ci.yml`):** Valida automáticamente `ruff format --check`, `ruff check` (PEP 8 `line-length=99`, `snake_case`) y pruebas unitarias offline en cada PR.
  * **Suite de verificación:** **27 pruebas unitarias** pasando + `tests/smoke_test_agent.py` (4 pruebas de efecto) + **Golden Dataset de 10 casos** verificados contra DuckDB para comparar modelos con rigor científico.
* **Visual sugerido:** Captura del check verde en GitHub Actions + tabla resumen del benchmark.
