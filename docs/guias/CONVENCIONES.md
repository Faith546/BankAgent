# Convenciones Oficiales del Proyecto — BankAgent

Este documento establece las **convenciones obligatorias** del repositorio y explica los **principios y patrones de diseño de ingeniería de software** que las respaldan, para que todo el equipo (`Jose`, `Fab`, `Diego`) y cualquier IA de código construyan bajo un mismo estándar.

---

## 1. Fundamento: Patrones y Principios que Usamos

Las reglas de este repo no son preferencias arbitrarias; aplican principios clásicos de arquitectura de software adaptados a agentes con LLMs:

| Principio / Patrón | Qué significa | Cómo se aplica en `BankAgent` |
| :--- | :--- | :--- |
| **SSOT** (*Single Source of Truth*) y **DRY** | Cada dato, fórmula, paleta o plantilla vive en **un solo lugar**. | Todas las consultas al cubo salen de `src/skills/cubo_sql_tools.py`, los umbrales y colores de `src/config.py` / `.streamlit/config.toml` y las plantillas de `templates/`. |
| **Arquitectura en Capas** (*Separation of Concerns*) | Cada carpeta tiene una única responsabilidad y dependencias claras. | `app/` (UI) $\rightarrow$ `src/agent/` (orquestación) $\rightarrow$ `src/skills/` (capacidades) $\rightarrow$ `src/data/` (ingesta/esquema). Un generador de reportes **no** abre DuckDB por su cuenta. |
| **Design by Contract** (Contratos) | Entradas, salidas y errores se declaran formalmente. | Toda tool usa `Pydantic` (`args_schema`), valida antes de ejecutar y devuelve errores estructurados como datos (`{"error": "...", "disponibles": [...]}`). |
| **Renderer / Strategy Pattern** | Separar **contenido** de **formato de salida**. | Un solo contrato de reporte (`ReportInput`) alimenta distintos renderizadores (`.docx`, `.pptx`, `.pdf`/HTML) sin duplicar lógica de negocio. |
| **Defense in Depth** (Seguridad por capas) | Nunca depender únicamente del prompt del LLM. | 5 guardrails deterministas en `src/agent/graph.py` + `DuckDB(read_only=True)` + restricción de dominio bancario + *Human-in-the-Loop*. |

---

## 2. Convenciones de Nombrado (PEP 8 Estricto)

* **Archivos y carpetas Python:** Siempre `snake_case`, sin espacios, sin acentos y sin mayúsculas.
  * ✅ `rag_dinamico.py`, `chats_pasados/`, `report_tools.py`
  * ❌ `ragDynamico.py`, `chatsPasados/`, `Guía de arranque.md`
* **Funciones, métodos y variables:** `snake_case` (`obtener_resumen_portafolio`, `ncl_rate_pct`).
* **Clases y esquemas Pydantic:** `PascalCase` (`FiltroCuboInput`, `KpiCard`, `ReportInput`).
* **Constantes globales:** `UPPER_SNAKE_CASE` (`OLLAMA_NUM_CTX`, `MAX_NCL_RATE_PCT`).
* **Sin efectos secundarios al importar:** Prohibido dejar `print(...)` sueltos a nivel de módulo (usar `logging` si se requiere traza).

---

## 3. Convenciones por Capa (Fronteras de Importación)

| Carpeta | Responsabilidad única | Regla estricta |
| :--- | :--- | :--- |
| `src/config.py` | Rutas, modelos Ollama, umbrales y catálogos válidos. | Toda constante compartida vive aquí (con override vía `os.getenv`). |
| `src/data/` | Ingesta del CSV a DuckDB y carga del diccionario `.xlsx`. | Solo lectura sobre `data/raw/`. |
| `src/skills/` | Herramientas atómicas (`@tool` o servicios puros) sin estado de UI. | No importar `streamlit` dentro de `src/skills/`. No duplicar consultas SQL ni gráficas entre skills. |
| `src/agent/` | Prompt contract, guardrails y grafo `LangGraph`. | Toda tool ejecutable por el LLM debe estar registrada en `TOOLS` / `TOOL_MAP`. |
| `app/` | Interfaz Streamlit (`streamlit_app.py`). | Solo presentación, estado de sesión y llamadas a `src/agent/` y `src/skills/`. |
| `templates/` | Plantillas corporativas (`.docx`, `.pptx`). | Prohibido guardar plantillas sueltas dentro de `src/skills/`. |
| `outputs/cases/` | Expedientes auditados por `case_id` (`CASO-YYYY-XXXX`). | Todo entregable final trazable se guarda aquí. |

---

## 4. Convenciones de Identidad Visual y Reportes

* **Paleta Corporativa Única (Banamex):**
  * Primario Navy: `#003B71` (Dark Navy `#002447`)
  * Acento / Riesgo Alto Crimson: `#C8102E`
  * Vigilancia Ámbar: `#D97706`
  * En Apetito Teal: `#0F766E`
  * Fondo claro `#F8FAFC` · Texto `#0F172A` · Bordes `#CBD5E1`
* **Un solo motor de entregables:** Todos los formatos (`.docx`, `.pptx`, `.pdf`/HTML) deben consumir el mismo contrato de datos, las mismas gráficas de `viz_tools.py` y las plantillas de `templates/`.

---

## 5. Convenciones de Contratos (Tools y Prompts)

* **Idioma:** `SYSTEM_PROMPT` y `description` de herramientas en **inglés conciso** (~1.8x menos tokens), con instrucción de responder siempre al usuario en **español**.
* **Formato JSON de salida:** Toda tool devuelve JSON serializado (`ensure_ascii=False`) con claves claras; ante error de entrada, devuelve `{"error": "...", "disponibles": [...]}` sin lanzar excepciones no controladas.
* **Límites en salida estructurada:** Cuando se use `with_structured_output(...)`, definir `max_length` / `max_items` en Pydantic para evitar bucles de generación en modelos locales.
* **Dominio y Sandbox:** Toda nueva tool debe pertenecer al dominio financiero/bancario, operar en local y respetar `read_only=True` en DuckDB.

---

## 6. Definition of Done (Checklist Obligatorio Antes de Mergear un PR)

Un Pull Request está listo para revisión y merge en `main` **solo si cumple los 5 puntos**:

- [ ] **PEP 8 limpio:** `uv run ruff format --check src app tests` y `uv run ruff check src app tests` pasan con **0 errores**.
- [ ] **Pruebas:** `uv run pytest` pasa completo y toda funcionalidad/skill nueva incluye al menos una prueba unitaria en `tests/`.
- [ ] **Sin duplicidad:** No reimplementa consultas DuckDB, paletas, plantillas ni módulos ya existentes.
- [ ] **Documentación y contexto al día:** Si se agregan librerías, módulos o variables en `src/config.py`, se actualiza `docs/arquitectura/ARQUITECTURA_Y_LIBRERIAS.md` y se deja una nota breve en `docs/contexto/`.
- [ ] **Sin archivos prohibidos:** Sin `.env`, claves, CSVs pesados ni temporales sin ignorar en `.gitignore`.
