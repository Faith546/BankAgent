# Backlog de Issues del Equipo — BankAgent (Banamex)

Este documento concentra las **13 issues oficiales** del equipo (`Jose`, `Fab`, `Diego`) para evolucionar el MVP con rigor arquitectónico, seguridad tipo **sandbox** y estricto apego al **dominio financiero/bancario**.

---

## Regla Transversal de Seguridad y Sandbox (Aplica a TODAS las Issues)

* **Dominio exclusivo financiero/bancario:** Tanto el *System Prompt* (`src/agent/prompts.py`) como los validadores deterministas en Python deben rechazar solicitudes, gráficas o generación de nuevas tools que no correspondan a análisis financiero, riesgo de crédito o banca.
* **Entorno tipo Sandbox:**
  * Cero salida a internet ni llamadas a APIs externas (todo corre contra `http://localhost:11434`).
  * Prohibido `shell=True`, `eval`, `exec` arbitrario o DDL/DML en DuckDB (`read_only=True`).
  * Escritura permitida únicamente en directorios en lista blanca (`data/duckdb/`, `data/politicas_internas/`, `outputs/cases/`, `src/skills/generated/`).
  * Librerías permitidas acotadas al entorno controlado (`pyproject.toml`).
  * Todo código nuevo debe pasar `uv run ruff check src app tests` (PEP 8) y `uv run pytest`.

---

## Resumen y Orden Sugerido de Ejecución

| # | Título | Responsable | Prioridad | Labels |
| :-: | :--- | :---: | :---: | :--- |
| 1 | Endpoint / Pipeline de limpieza y preprocesamiento (Fase 1 FE) | **Jose** | `P1` | `feat`, `data`, `feature-engineering`, `sandbox` |
| 2 | Interpretación de gráficas adjuntas en el chat con filtro de dominio | **Jose** | `P1` | `feat`, `skills`, `vision`, `security` |
| 3 | Contexto separado y múltiples chats independientes (tipo LLM) | **Jose** | `P0` | `feat`, `agent`, `ui` |
| 4 | Gestión dinámica de documentos de políticas en ChromaDB (RAG) | **Jose** | `P1` | `feat`, `rag`, `ui` |
| 5 | Panel de configuración acotado de agentes, tools y parámetros | **Fab** | `P1` | `feat`, `ui`, `config`, `sandbox` |
| 6 | Dashboards dinámicos con componentes y gráficas preestablecidas | **Fab** | `P1` | `feat`, `ui`, `analytics` |
| 7 | Auditoría y estandarización de contratos (Tools & Prompts) | **Fab** | `P0` | `refactor`, `contracts`, `agent` |
| 8 | Documentación de arquitectura, flujos y guía del equipo | **Fab** | `P2` | `docs` |
| 9 | Catálogo de Skills analíticas básicas de datos bancarios | **Fab** | `P2` | `feat`, `skills`, `analytics` |
| 10 | Skill generadora de contratos (flexible y restringida a banca) | **Diego** | `P0` | `feat`, `skills`, `contracts`, `security`, `sandbox` |
| 11 | Mitigación estricta de alucinaciones y pruebas adversariales | **Por asignar** | `P0` | `feat`, `agent`, `guardrails`, `benchmark` |
| 12 | Dockerización del proyecto en entorno sandbox local | **Por asignar** | `P1` | `feat`, `infra`, `docker`, `sandbox` |
| 13 | Pruebas, configuración y benchmark contra servidor remoto (GPU) | **Por asignar** | `P0` | `infra`, `benchmark`, `server` |

---

## 👤 JOSE

### Issue 1 · `[Data/FE] Endpoint / Pipeline de limpieza y preprocesamiento (Fase 1 Feature Engineering)`
* **Labels:** `feat`, `data`, `feature-engineering`, `sandbox` · **Prioridad:** `P1`
* **Contexto:** Actualmente `src/data/init_db.py` solo aplica `TRIM()` y castea tipos. Se requiere un módulo/endpoint de limpieza reutilizable (preparado para cualquier tabla tabular, adaptado inicialmente a nuestro cubo Banamex) como primer paso de *Feature Engineering*.
* **Criterios de aceptación:**
  - [ ] Implementar funciones/endpoint parametrizables para diagnóstico de nulos, imputación controlada (mediana/moda/cero según tipo), detección y tratamiento de outliers (IQR / z-score / winsorizing) y normalización de texto (`TRIM`).
  - [ ] Adaptarlo y probarlo primero sobre el cubo de tarjetas en DuckDB, generando una tabla/vista limpia sin modificar `data/raw/`.
  - [ ] Devolver reporte JSON auditable (filas afectadas, nulos imputados, outliers marcados) y verificar identidades contables (`NCL = GCL - RECOVERY`).
  - [ ] Respetar las reglas del sandbox (solo lectura sobre `data/raw/`, sin dependencias externas de red).

### Issue 2 · `[Skills/Vision] Interpretación de gráficas adjuntas en el chat con filtro de dominio`
* **Labels:** `feat`, `skills`, `vision`, `security` · **Prioridad:** `P1`
* **Contexto:** Permitir al usuario adjuntar una imagen de gráfica directamente en el chat de Streamlit (`st.chat_input(accept_file=True, file_type=["png", "jpg", "jpeg", "webp"])`) para que el agente la interprete mediante tools dedicadas.
* **Criterios de aceptación:**
  - [ ] Habilitar carga de imágenes en `st.chat_input` dentro de `app/streamlit_app.py`.
  - [ ] Crear una Skill de visión local (Ollama multimodal, ej. `qwen2.5vl:7b` / `gemma3`) que extraiga tipo de gráfica, ejes, etiquetas y variables visibles.
  - [ ] Implementar un **validador de dominio**: cruzar lo extraído contra las 22 variables del cubo (`src/data/dictionary_loader.py`) y conceptos bancarios. Si la gráfica **no** corresponde al portafolio bancario, rechazarla explícitamente (*"No estoy preparado para analizar gráficas fuera del portafolio bancario"*).
  - [ ] Si sí corresponde, contrastar los hallazgos contra DuckDB / RAG y respetar el guardrail numérico (`src/agent/guardrails.py`).

### Issue 3 · `[Agent/UI] Contexto separado y múltiples chats independientes (tipo LLM)`
* **Labels:** `feat`, `agent`, `ui` · **Prioridad:** `P0`
* **Contexto:** Hoy el Copiloto en `app/streamlit_app.py` mantiene un solo `chat_history` por sesión. LangGraph ya soporta múltiples hilos mediante `thread_id` en `data/state/checkpoints.db` (`SqliteSaver`).
* **Criterios de aceptación:**
  - [ ] Permitir crear nuevos chats independientes (*Nuevo chat*), renombrarlos, alternar entre ellos y eliminarlos desde la UI.
  - [ ] Asociar cada chat a un `thread_id` único en `SqliteSaver` para aislar por completo el historial y la ventana de contexto (`num_ctx`).
  - [ ] Persistir la lista de chats entre recargas de Streamlit.
  - [ ] Mostrar por chat su consumo real de ventana de contexto (`prompt_eval_count / num_ctx`).

### Issue 4 · `[RAG] Gestión dinámica de documentos de políticas en ChromaDB`
* **Labels:** `feat`, `rag`, `ui` · **Prioridad:** `P1`
* **Contexto:** Actualmente `src/skills/rag_tools.py` solo indexa archivos `.md` estáticos mediante comando manual.
* **Criterios de aceptación:**
  - [ ] Soportar subida de documentos `.md` y `.pdf` desde Streamlit hacia `data/politicas_internas/`.
  - [ ] Re-indexar automáticamente en `ChromaDB` (`nomic-embed-text`) al subir, actualizar o eliminar un documento, sin duplicar chunks.
  - [ ] Mostrar en la UI el catálogo de documentos indexados (nombre, fecha, número de chunks).
  - [ ] Mantener la separación de motores: prohibido vectorizar `.csv` en `ChromaDB`.

---

## 👤 FAB

### Issue 5 · `[UI/Config] Panel de configuración acotado de agentes, tools y parámetros`
* **Labels:** `feat`, `ui`, `config`, `sandbox` · **Prioridad:** `P1`
* **Contexto:** Centralizar la configuración del sistema en la UI de forma realista para el MVP: permitir gestionar y ajustar piezas controladas sin abrir puertas inseguras.
* **Criterios de aceptación:**
  - [ ] Permitir desde la UI: (1) elegir modelo disponible en Ollama y parámetros (`temperature`, `reasoning`, `num_ctx`, `top_k`, `top_p`, `AGENT_MAX_TURNS`), (2) activar/desactivar tools registradas en `TOOL_MAP`, (3) ajustar umbrales de riesgo (`NCL`, `Over30`, `MOB`), y (4) personalizar el perfil del agente sin borrar las reglas duras de seguridad bancaria.
  - [ ] Persistir la configuración en un archivo JSON/YAML local con botón *Restaurar defaults*.
  - [ ] Impedir desactivar los guardrails obligatorios (DuckDB `read_only`, lista blanca y restricción de dominio financiero).

### Issue 6 · `[UI/Analytics] Dashboards dinámicos con componentes y gráficas preestablecidas`
* **Labels:** `feat`, `ui`, `analytics` · **Prioridad:** `P1`
* **Contexto:** Dar libertad al analista para configurar su dashboard del portafolio, pero **acotado al catálogo preestablecido** de KPIs y las 6 gráficas validadas (`src/skills/viz_tools.py`), sin generar código arbitrario desde cero.
* **Criterios de aceptación:**
  - [ ] Permitir elegir qué KPIs y qué combinación de las 6 gráficas preestablecidas mostrar en el lienzo (layout de 1 o 2 columnas).
  - [ ] Incluir filtros dinámicos globales (`VINTAGE`, `STRATEGY`, `PRODUCT`, `CHANNEL`, `AGE_TAG`, `SCORE_TAG`, `MOB`) conectados a DuckDB con `@st.cache_data`.
  - [ ] Permitir guardar/cargar *presets* de vista (ej. *"Vista Morosidad"*, *"Vista Rentabilidad"*).

### Issue 7 · `[Agent/Skills] Auditoría y estandarización de contratos (Tools & Prompts)`
* **Labels:** `refactor`, `contracts`, `agent` · **Prioridad:** `P0`
* **Contexto:** Los contratos entre el LLM y las herramientas (`Pydantic`, `description`, JSON de salida y errores) son la base para un *tool calling* confiable sin alucinaciones.
* **Criterios de aceptación:**
  - [ ] Auditar todas las tools en `src/skills/` para estandarizar su JSON de respuesta (`status`, `data`, `error`, `disponibles`).
  - [ ] Alinear todas las `description` y `src/agent/prompts.py` en inglés conciso (~1.8x menos tokens) con reglas explícitas de uso, no uso y dominio bancario.
  - [ ] Asegurar que todo error de entrada regrese como dato estructurado (nunca excepciones no controladas).
  - [ ] Documentar mejora medible con `uv run python -m tests.smoke_test_agent --benchmark`.

### Issue 8 · `[Docs] Documentación de arquitectura, flujos y guía del equipo`
* **Labels:** `docs` · **Prioridad:** `P2`
* **Contexto:** Todo el equipo debe comprender y defender la arquitectura, los contratos y las decisiones técnicas del sistema.
* **Criterios de aceptación:**
  - [ ] Mantener actualizados `README.md`, `docs/ARQUITECTURA_Y_LIBRERIAS.md` y `docs/ISSUES.md` conforme se integren nuevas issues.
  - [ ] Documentar flujos de prueba y calidad (`pytest`, `ruff`, `tests/smoke_test_agent.py`).
  - [ ] Agregar una sección de **Decisiones de Arquitectura (ADR)**: por qué DuckDB vs. Pandas, LangGraph vs. Chains, ChromaDB solo texto, sandbox bancario y criterio para una eventual migración de UI (Streamlit vs. React/`meta/astryx` + `GoogleChrome/modern-web-guidance`).

### Issue 9 · `[Skills] Catálogo de Skills analíticas básicas de datos bancarios`
* **Labels:** `feat`, `skills`, `analytics` · **Prioridad:** `P2`
* **Contexto:** Añadir herramientas deterministas para análisis recurrentes de datos del portafolio (set exacto por acordar con el equipo) y reducir la dependencia de Text-to-SQL abierto.
* **Criterios de aceptación:**
  - [ ] Acordar e implementar 3–4 skills prioritarias (ej. `perfil_estadistico_segmento`, `comparar_vs_benchmark`, `ranking_cohortes_por_metrica`, `calcular_payback_adquisicion`).
  - [ ] Registrarlas en `TOOLS` / `TOOL_MAP` (`src/agent/graph.py`) con contratos Pydantic y validación previa de filtros.
  - [ ] Agregar pruebas unitarias en `tests/test_skills_and_guardrails.py` y casos verificados en `tests/golden_dataset.json`.

---

## 👤 DIEGO

### Issue 10 · `[Skills/Contracts] Skill generadora de contratos (flexible y restringida a banca)`
* **Labels:** `feat`, `skills`, `contracts`, `security`, `sandbox` · **Prioridad:** `P0`
* **Contexto:** Construir una Skill capaz de generar nuevos contratos de herramientas/agentes (esquema Pydantic + especificación de entrada/salida + validaciones + reglas de error + prompt de uso) de forma flexible, pero **estrictamente restringida al dominio financiero/bancario** y dentro de nuestro sandbox.
* **Criterios de aceptación:**
  - [ ] Definir el estándar de contrato generado (JSON/YAML + esquema Pydantic + casos de borde + criterios de parada).
  - [ ] Implementar un **guardrail de dominio financiero/bancario** (tanto en el prompt como en validador determinista Python): rechazar cualquier solicitud de contrato/tool fuera de banca y finanzas.
  - [ ] Validar automáticamente cada contrato generado contra el diccionario de variables (`src/data/dictionary_loader.py`) y las reglas de sandbox (solo lectura DuckDB, sin `subprocess`/`shell=True`, sin acceso a red, solo librerías permitidas).
  - [ ] Guardar los contratos aprobados en un directorio controlado tras revisión *Human-in-the-Loop*, con pruebas unitarias cubriendo casos válidos (bancarios) y casos rechazados (fuera de dominio o inseguros).

---

## 👥 EQUIPO (POR ASIGNAR)

### Issue 11 · `[Agent/Guardrails] Mitigación estricta de alucinaciones y pruebas adversariales`
* **Labels:** `feat`, `agent`, `guardrails`, `benchmark` · **Prioridad:** `P0`
* **Contexto:** Aunque ya existe un verificador Regex en `src/agent/guardrails.py`, necesitamos endurecerlo para que el agente **no alucine cifras, políticas ni columnas**, sepa abstenerse cuando no hay datos y pueda medirse con rigor científico.
* **Criterios de aceptación:**
  - [ ] Mejorar `src/agent/guardrails.py` para validar correctamente cifras con escalas (`M`, `K`, porcentajes, signos negativos) evitando falsos positivos y atrapando cualquier cifra fabricada.
  - [ ] Exigir abstención explícita (*"No existen datos en el cubo para esta consulta"*) cuando DuckDB devuelva 0 filas, se pidan datos de clientes individuales (PII) o se hagan preguntas fuera del dominio bancario.
  - [ ] Agregar al menos **5 casos adversariales** en `tests/golden_dataset.json` (producto inexistente, solicitud de cliente físico, pregunta fuera de banca, trampa `MOB = 0`, política inexistente).
  - [ ] Correr `uv run python -m tests.smoke_test_agent --benchmark` y registrar el reporte de 0% alucinaciones en `docs/contexto/`.

### Issue 12 · `[Infra/Docker] Dockerización del proyecto en entorno sandbox local`
* **Labels:** `feat`, `infra`, `docker`, `sandbox` · **Prioridad:** `P1`
* **Contexto:** Empaquetar `BankAgent` en Docker permite reproducibilidad total entre las máquinas del equipo (Windows/macOS/Linux) y refuerza el aislamiento tipo **sandbox** (sin acceso al resto del sistema operativo ni a internet externo).
* **Criterios de aceptación:**
  - [ ] Crear `Dockerfile` (Python 3.11 + `uv`, usuario no-root) y `docker-compose.yml` para levantar Streamlit (`:8501`).
  - [ ] Configurar conexión automática al Ollama local del host vía `host.docker.internal:11434` (`extra_hosts: ["host.docker.internal:host-gateway"]`), igual que en `agents_intro`.
  - [ ] Montar `data/raw/` en modo **solo lectura (`:ro`)** y volúmenes persistentes para `data/duckdb/`, `data/chromadb/`, `data/state/` y `outputs/cases/`.
  - [ ] Documentar los comandos `docker compose up --build` y `docker compose down` en `docs/guias/` y `README.md`.

### Issue 13 · `[Infra/Eval] Pruebas, configuración y benchmark contra servidor remoto (GPU)`
* **Labels:** `infra`, `benchmark`, `server` · **Prioridad:** `P0`
* **Contexto:** Pasar las pruebas del entorno portátil local (`localhost:11434`, 8 GB VRAM) al **servidor remoto con GPU** (estación del Tec / servidor dedicado), validando conectividad, latencia, estabilidad de *tool calling* y capacidad de usar ventanas de contexto mayores (`num_ctx=16384`) o modelos más grandes.
* **Criterios de aceptación:**
  - [ ] Soportar cambio limpio entre `localhost` y servidor remoto vía `.env` / variables de entorno (`OLLAMA_BASE_URL=http://<ip-servidor>:11434`, `OLLAMA_MODEL`, `OLLAMA_NUM_CTX`), validando explícitamente esquema `http://` (sin TLS).
  - [ ] Verificar conectividad, modelos instalados (`/api/tags`), uso de VRAM (`nvidia-smi`) y que no haya bloqueos de firewall/VPN.
  - [ ] Ejecutar `uv run python -m tests.smoke_test_agent` y `uv run python -m tests.smoke_test_agent --benchmark` contra el servidor remoto.
  - [ ] Documentar en `docs/contexto/` la tabla comparativa de latencia, precisión sobre el Golden Dataset y consumo de tokens (local vs. servidor) y actualizar la guía en `docs/guias/`.
