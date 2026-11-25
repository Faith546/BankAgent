# AI Coding Agent Context & Master Implementation Guide (MVP)
# Proyecto: Asistente Agéntico de Análisis de Portafolio - Banamex

> **INSTRUCCIÓN CRÍTICA PARA LA IA DE CÓDIGO (Codex / Gemini / Antigravity IDE / Cursor):**
> Este documento es tu fuente de verdad absoluta (Single Source of Truth). **NO generes todo el proyecto de golpe.** Trabajaremos de forma iterativa paso por paso.
> **Tu Paso 0 obligatorio:** Antes de escribir cualquier script de aplicación, debes generar el archivo `README.md` con los prerrequisitos de instalación, configuración de entorno (`uv`, `Ollama`, `DuckDB`) y comandos que el desarrollador humano debe ejecutar manualmente en su máquina. **No ejecutes instalaciones globales ni descargues modelos pesados por tu cuenta.**
> **Exclusión actual:** **NO implementes ningún modelo de Machine Learning (`scikit-learn`, `IsolationForest`, `K-Means`) en esta fase.** El módulo de ML se integrará al final del proyecto. La prioridad absoluta de este MVP es la **lectura impecable del cubo de datos en DuckDB, la conexión con Ollama local, las Skills deterministas/Text-to-SQL y la interfaz en Streamlit**.

---

## 1. Visión del Producto y Naturaleza de los Datos

El sistema es un **Asistente Agéntico Local de Análisis de Portafolio de Tarjetas de Crédito** para Banamex.
* **Qué hace:** Recibe consultas en lenguaje natural (o alertas predefinidas), consulta un cubo de datos financieros mediante SQL analítico en memoria (`DuckDB`), contrasta los números contra manuales de políticas internas (`ChromaDB`), genera visualizaciones ejecutivas (`Plotly` / `Kaleido`) y compila entregables corporativos (`.docx` y `.pptx`) bajo supervisión humana (*Human-in-the-Loop*) con trazabilidad en Git (`Audit-as-Code`).
* **Pivote de Datos Crítico:** El dataset **NO contiene clientes individuales ni transacciones unitarias**. Es un **cubo agregado por cohortes (`VINTAGE`) y segmentos de adquisición (`STRATEGY_SEGMENT`)** seguidos mensualmente a lo largo de su maduración (`MOB` - *Months on Book*). Por lo tanto, el agente evalúa la salud, morosidad y rentabilidad de **segmentos completos de la cartera**, nunca de personas físicas aisladas.

---

## 2. Entorno de Ejecución Local y Restricciones de Hardware

El desarrollo y ejecución de este MVP ocurrirá en una estación portátil local con recursos acotados. Todo el código debe respetar estrictamente estos límites:

* **Especificaciones de la Máquina Local (Dev Environment):**
  * **CPU:** Intel Core Ultra 9 185H (2.50 GHz, 16 núcleos).
  * **RAM:** 16.0 GB (15.4 GB utilizables).
  * **GPU:** NVIDIA GeForce RTX 4070 Laptop GPU (**8 GB VRAM dedicada**).
  * **OS:** Windows 11 64-bit (ejecución recomendada sobre WSL2 Ubuntu 22.04/24.04 o entorno nativo gestionado con `uv`).
* **Presupuesto de VRAM (Límite duro de 8 GB en Laptop / 20 GB en Workstation futura RTX A4500):**
  * **Modelo LLM Principal en Ollama:** `qwen3.5:9b` (cuantizado a 4 bits `q4_K_M`, consumo ~6.0 GB pesos + ~1.5 GB KV Cache = **~7.5 GB VRAM**) o `qwen2.5:7b-instruct-q4_K_M` (~5.0 GB VRAM).
  * **Modelo de Embeddings en Ollama:** `nomic-embed-text` (~0.5 GB VRAM).
  * **Parámetros obligatorios de inferencia:** `temperature = 0.1` (cero creatividad numérica), `num_ctx = 8192` o `16384` según disponibilidad de VRAM sin desbordar a la RAM compartida de Windows.
* **Regla de Oro de Memoria RAM (16 GB):**
  * Todo el procesamiento tabular debe ejecutarse dentro de **DuckDB**. Evita mantener múltiples copias de DataFrames en memoria con Pandas.

---

## 3. Restricciones Estrictas y Gobernanza (Lo que el Agente NO Puede Hacer)

1. **PROHIBIDO inventar o calcular cifras mentalmente:** El LLM tiene estrictamente prohibido realizar sumas, restas o promedios por cuenta propia en texto libre. Todo número reportado debe provenir de la salida JSON de una herramienta conectada a `DuckDB`.
2. **PROHIBIDO ejecutar SQL destructivo (`DDL` / `DML`):** La conexión del agente a DuckDB debe abrirse con `read_only=True`. Cualquier consulta generada por el LLM que contenga `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `CREATE` o `COPY` debe ser rechazada por un validador previo en Python.
3. **PROHIBIDO el acceso abierto a Terminal / Bash (`shell=True`):** El agente nunca puede ejecutar comandos arbitrarios de consola ni correr `pip install`. Solo puede invocar funciones en lista blanca dentro de `git_governance.py` usando `subprocess.run([...], shell=False, check=True)`.
4. **PROHIBIDO usar APIs externas de IA:** Cero llamadas a OpenAI, Anthropic o servicios cloud. Toda conexión apunta a `http://localhost:11434` (Ollama local).
5. **PROHIBIDO implementar Machine Learning en las Etapas 1 a 4:** No escribas código de `IsolationForest`, `KMeans` ni `DecisionTree` hasta que el usuario lo solicite explícitamente en la última fase posterior al MVP.
6. **PROHIBIDO mezclar motores de datos:** `DuckDB` es exclusivo para datos estructurados numéricos (el CSV). `ChromaDB` es exclusivo para documentos de texto normativo (`.md` / `.pdf`). Jamás vectorices el archivo CSV dentro de ChromaDB.

---

## 4. Radiografía Exacta de los Datos (Prioridad #1: Lectura del Cubo)

### 4.1. Archivos Fuente Disponibles
1. `data/raw/base_cards_sintetica_mini.csv` (499 filas, 22 columnas).
2. `data/raw/Base Cards para TEC - Diccionario de Variables.xlsx` (1 hoja: `Sheet1`, con definiciones y dominios válidos).

### 4.2. Esquema de las 22 Columnas y Reglas de Limpieza
Al cargar `base_cards_sintetica_mini.csv` en DuckDB, el script de ingesta (`src/data/init_db.py`) **DEBE aplicar `TRIM()` a todas las columnas de texto (`VARCHAR`)**, ya que en el CSV crudo existen valores con espacios al final (por ejemplo, `'Brands-NonPayroll-OffUs&LE '` tiene un espacio extra al final que rompe filtros exactos si no se limpia).

| # | Columna | Tipo DuckDB | Descripción y Dominio de Valores |
| :--- | :--- | :--- | :--- |
| 1 | `VINTAGE` | `INTEGER` | Mes y año de apertura (Booking) en formato `AAAAMM`. Dominio general: `202401` a `202609`. En el CSV mini actual: `202401`. |
| 2 | `STRATEGY` | `VARCHAR` | Estrategia de adquisición. Valores posibles en diccionario: `"14.Recalibration 1.0"`, `"15.Recalibration 2.0"`, `"r.Reca champ"`, `"DARIA 1.6"`, `"DARIA 2.0"`. En CSV mini: `"14.Recalibration 1.0"`. |
| 3 | `STRATEGY_SEGMENT` | `VARCHAR` | Segmento dentro de la estrategia. En CSV mini (tras `TRIM`): `"Brands-NonPayroll-OffUs&LE"`. |
| 4 | `PRODUCT` | `VARCHAR` | Producto de tarjeta (`"Clasica"`, `"Oro"`, `"Platinum"`, `"Costco"`, `"Home Depot"`, `"Joy"`, `"Affinity"`, `"Conquista"`, `"Descubre"`, `"Explora"`, `"Teleton"`, `"Beyond"`). En CSV mini: `"Clasica"`. |
| 5 | `CHANNEL` | `VARCHAR` | Canal de colocación. En CSV mini: `"Aeropuerto"` y `"Branch"`. |
| 6 | `AGE_TAG` | `VARCHAR` | Edad al momento del booking: `"01| Young < 25"`, `"02| Young 25-30"`, `"03| Mature >30"`. |
| 7 | `SCORE_TAG` | `VARCHAR` | Rango de Score de originación. En CSV mini: `"130-140"`, `"141-150"`, `"151-160"`, `"161-170"`, `"171-180"`, `"181-190"`. |
| 8 | `MOB` | `INTEGER` | *Months on Book* (Mes de desempeño relativo a `VINTAGE`, de `0` a `32`). `MOB = 0` es el mes de apertura. |
| 9 | `ACCOUNTS` | `BIGINT` | Cantidad de cuentas abiertas en esa cohorte en el mes `MOB`. |
| 10 | `CREDITLINESAMTS` | `BIGINT` | Suma de líneas de crédito asignadas a esas cuentas en el mes `MOB`. |
| 11 | `ENRACCTS` | `BIGINT` | Cantidad de cuentas activas con saldo deudor (Ending Receivable Accounts) en `MOB`. |
| 12 | `OVER30ACCTS` | `BIGINT` | Cantidad de cuentas con morosidad mayor a 30 días en `MOB`. |
| 13 | `OVER30AMTS` | `DOUBLE` | Suma de saldos vencidos a más de 30 días en `MOB`. |
| 14 | `GCLAMTS` | `DOUBLE` | *Gross Credit Loss*: Suma de saldos en pérdida bruta en `MOB`. |
| 15 | `NCLAMTS` | `DOUBLE` | *Net Credit Loss*: Suma de pérdida neta en `MOB`. Identidad contable: `NCLAMTS = GCLAMTS - RECOVERYAMTS`. |
| 16 | `RECOVERYAMTS` | `DOUBLE` | Monto recuperado por cobranza sobre la pérdida bruta en `MOB`. |
| 17 | `ENRAMTS` | `DOUBLE` | *Ending Receivables*: Suma total de saldos de las cuentas en `MOB`. |
| 18 | `REVENUE` | `DOUBLE` | Suma de ingresos financieros obtenidos en `MOB`. |
| 19 | `EXPENSES_ACQ` | `DOUBLE` | Gastos de adquisición. **Regla estricta:** Solo tiene valor positivo en `MOB = 0`; para `MOB > 0` siempre vale `0.0`. |
| 20 | `EXPENSES_ECM_VAR` | `DOUBLE` | Suma de gastos variables de administración de cartera en `MOB`. |
| 21 | `EXPENSES_ECM_FIX` | `DOUBLE` | Suma de gastos fijos de administración de cartera en `MOB`. |
| 22 | `EXPENSES_TOTAL` | `DOUBLE` | Gasto total en `MOB`. Identidad contable: `EXPENSES_TOTAL = EXPENSES_ACQ + EXPENSES_ECM_VAR + EXPENSES_ECM_FIX`. |

### 4.3. Trampas Matemáticas de Agregación SQL que debes Evitar
Cada combinación única de `(VINTAGE, STRATEGY, STRATEGY_SEGMENT, PRODUCT, CHANNEL, AGE_TAG, SCORE_TAG)` forma una **Cohorte (`COHORT_ID`)**. En el CSV mini existen **16 cohortes únicas** (15 cohortes completas con 33 filas de `MOB 0` a `MOB 32`, y 1 cohorte joven `Branch | 02| Young 25-30 | 141-150` con 4 filas de `MOB 0` a `MOB 3`).
* **Trampa 1 (No sumar `ACCOUNTS` ni `CREDITLINESAMTS` a lo largo de todos los `MOB`):** Si haces `SELECT SUM(ACCOUNTS) FROM cubo WHERE CHANNEL = 'Aeropuerto'`, estarás sumando las mismas cuentas 33 veces (una por cada mes `MOB`). Para conocer el volumen inicial de cuentas o líneas de una cohorte, debes filtrar `WHERE MOB = 0` (o usar `MAX(ACCOUNTS)` por `COHORT_ID`).
* **Trampa 2 (Tasas ponderadas vs. promedio de porcentajes):** Cuando calcules ratios agregados (ej. Tasa de Morosidad o Severidad de Pérdida Neta de un canal), **NUNCA hagas `AVG(OVER30AMTS / ENRAMTS)`**. Siempre calcula la razón de las sumas:
  * `OVER30_RATE_PCT = (SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100`
  * `NCL_RATE_PCT = (SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100`
  * `RECOVERY_RATE_PCT = (SUM(RECOVERYAMTS) / NULLIF(SUM(GCLAMTS), 0)) * 100`
  * `YIELD_RATE_PCT = (SUM(REVENUE) / NULLIF(SUM(ENRAMTS), 0)) * 100`
  * `NET_PROFIT = SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL)`
  * `NET_ROA_PCT = ((SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL)) / NULLIF(SUM(ENRAMTS), 0)) * 100`

---

## 5. Stack Tecnológico y Estructura de Carpetas del Proyecto

### 5.1. Librerías Oficiales (`pyproject.toml` gestionado con `uv` sobre Python 3.11)
* **Base de Datos y Datos:** `duckdb`, `pandas`, `pyarrow`, `openpyxl` (para leer el Excel del diccionario).
* **LLM y Orquestación:** `ollama`, `langchain-core`, `langchain-ollama`, `langgraph`, `langgraph-checkpoint-sqlite`, `pydantic`.
* **Memoria Vectorial (RAG):** `chromadb`, `langchain-community`.
* **Visualización (Inspirada en Control CAPEX):** `plotly`, `kaleido`, `matplotlib`, `seaborn`.
* **Generación de Reportes:** `python-docx`, `python-pptx`, `jinja2`.
* **Interfaz Web:** `streamlit`.
* **Calidad y Testing:** `pytest`, `ruff`.

### 5.2. Árbol de Directorios Objetivo
```text
banamex-portfolio-agent/
├── README.md                           # (PASO 0: Generado primero por la IA con instrucciones de instalación)
├── pyproject.toml                      # Dependencias gestionadas con uv
├── .gitignore                          # Excluye .venv, data/duckdb/*.duckdb, data/chromadb/, outputs/tmp/
├── data/
│   ├── raw/
│   │   ├── base_cards_sintetica_mini.csv
│   │   └── Base Cards para TEC - Diccionario de Variables.xlsx
│   ├── duckdb/
│   │   └── cubo_banamex.duckdb         # Base generada por init_db.py
│   ├── chromadb/                       # Persistencia vectorial local
│   ├── state/
│   │   └── checkpoints.db              # Estado de LangGraph (SqliteSaver)
│   └── politicas_internas/
│       └── manual_apetito_riesgo.md    # Reglas de negocio para RAG
├── templates/
│   ├── memo_template.docx              # Plantilla base Word (creada por script inicializador si no existe)
│   └── comite_template.pptx            # Plantilla base PowerPoint
├── src/
│   ├── __init__.py
│   ├── config.py                       # Rutas, nombre del modelo Ollama, constantes y umbrales
│   ├── data/
│   │   ├── init_db.py                  # Limpieza TRIM(), creación de tabla `cubo` y vista `v_cubo_metricas`
│   │   └── dictionary_loader.py        # Lee el .xlsx del diccionario y lo convierte en contexto Markdown
│   ├── skills/
│   │   ├── cubo_sql_tools.py           # Skills de consulta parametrizada + Text-to-SQL seguro en DuckDB
│   │   ├── viz_tools.py                # Generación de las 6 gráficas financieras (Plotly + PNG 300 DPI)
│   │   ├── rag_tools.py                # Ingesta y consulta semántica en ChromaDB
│   │   ├── report_tools.py             # Compilador de .docx y .pptx
│   │   └── git_governance.py           # Subprocesos en lista blanca (commits de auditoría y diffs)
│   └── agent/
│       ├── prompts.py                  # System Prompts con inyección de esquema SQL y reglas anti-alucinación
│       ├── guardrails.py               # Verificador Regex de cifras (Output LLM vs JSON DuckDB)
│       └── graph.py                    # StateGraph de LangGraph con pausa Human-in-the-Loop
├── app/
│   └── streamlit_app.py                # Consola Híbrida de 3 paneles
├── outputs/
│   └── cases/                          # Directorios por caso (CASO-YYYY-XXXX) versionados en Git
└── tests/
    ├── test_db_reading.py              # Verifica lectura exacta del CSV y cálculos base
    └── test_prompts_ollama.py          # Prueba de humo de conexión y Tool Calling con Ollama
```

---

## 6. Especificación Detallada de las Skills y Templates

### Skill 1: Lectura y Consulta del Cubo (`src/skills/cubo_sql_tools.py`)
Debe exponer **3 herramientas** decoradas con `@tool` y esquemas `Pydantic`:
1. `obtener_resumen_portafolio(channel: Optional[str], age_tag: Optional[str], score_tag: Optional[str])`:
   * Calcula cuentas iniciales (`MOB = 0`), líneas de crédito iniciales (`MOB = 0`), saldo promedio (`AVG(ENRAMTS)`), ingresos acumulados (`SUM(REVENUE)`), pérdida bruta (`SUM(GCLAMTS)`), recuperación (`SUM(RECOVERYAMTS)`), pérdida neta (`SUM(NCLAMTS)`), gastos totales (`SUM(EXPENSES_TOTAL)`), utilidad neta (`NET_PROFIT`) y severidad (`NCL_RATE_PCT`).
2. `obtener_curva_maduracion(channel: Optional[str], age_tag: Optional[str], score_tag: Optional[str])`:
   * Devuelve la serie temporal de `MOB 0` a `MOB 32` con `OVER30_RATE_PCT`, `NCL_RATE_PCT`, `YIELD_RATE_PCT` y `NET_ROA_PCT` para analizar en qué mes se dispara el deterioro.
3. `ejecutar_sql_select_seguro(query_sql: str, proposito: str)`:
   * **Text-to-SQL Controlado:** Permite al LLM escribir una consulta `SELECT` o `WITH` en dialecto DuckDB sobre la vista `v_cubo_metricas` para responder preguntas ad-hoc.
   * **Validación:** Verifica con expresión regular que sea exclusivamente de lectura, abre DuckDB con `read_only=True`, añade `LIMIT 100` si no tiene límite y, si DuckDB lanza un `CatalogException` o `ParserException`, devuelve el texto del error al LLM para que seautocorrija en el siguiente paso del grafo.

### Skill 2: Catálogo de Visualizaciones estilo CAPEX (`src/skills/viz_tools.py`)
Expone la herramienta `generar_grafica_portafolio(tipo_grafica: Literal[...], case_id: str, filtros: Optional[dict])` que genera tanto el objeto interactivo de `Plotly` como un archivo estático `.png` a 300 DPI en `outputs/cases/{case_id}/charts/`:
1. `"curva_maduracion_s"`: Curva S de evolución de `% Over30 / ENR` y `% NCL / ENR` del `MOB 0` al `MOB 32` con línea punteada de umbral de alerta.
2. `"curva_j_roa"`: Curva de Margen Neto / ROA Neto (`(REVENUE - NCLAMTS - EXPENSES_TOTAL) / ENRAMTS %`) por `MOB` desglosada por `SCORE_TAG`.
3. `"puente_pnl_waterfall"`: Gráfico Waterfall desde `+REVENUE`, `-GCLAMTS`, `+RECOVERYAMTS`, `-EXPENSES_ACQ`, `-EXPENSES_ECM_VAR`, `-EXPENSES_ECM_FIX` hasta el `Margen Neto`.
4. `"heatmap_severidad"`: Mapa de calor cruzando `CHANNEL | AGE_TAG` (filas) vs. `SCORE_TAG` (columnas) coloreado por `NCL_RATE_PCT`.
5. `"matriz_cuadrantes"`: Dispersión de burbujas en cohortes maduras (`MOB >= 12`) con `NCL_RATE_PCT` en eje X, `YIELD_RATE_PCT` en eje Y y `CREDITLINESAMTS` como tamaño de burbuja (dividido en cuadrantes: *Expandir*, *Restringir Línea*, *Suspender*).
6. `"embudo_cobranza"`: Comparativa de `ACCOUNTS` -> `ENRACCTS` -> `OVER30ACCTS` y eficiencia de recuperación (`GCLAMTS` vs `RECOVERYAMTS` vs `NCLAMTS`).

### Skill 3: Memoria Normativa RAG (`src/skills/rag_tools.py`)
* Ingesta el archivo `data/politicas_internas/manual_apetito_riesgo.md` (que incluye umbrales de negocio, ej.: *"Ningún segmento debe superar el 15% de pérdida neta sobre saldo (NCL/ENR) en madurez ni el 25% de morosidad Over30 a partir de MOB 6"*).
* Expone `consultar_politica_riesgo(consulta: str)` usando `ChromaDB` local y embeddings `nomic-embed-text` vía Ollama.

### Skill 4: Generación de Reportes y Templates (`src/skills/report_tools.py`)
* Incluye una función inicializadora `ensure_templates_exist()` que crea programáticamente las plantillas base en `templates/memo_template.docx` y `templates/comite_template.pptx` si no existen aún.
* Expone `compilar_entregables_ejecutivos(case_id: str, titulo: str, hallazgos: list[str], dictamen: str, rutas_graficas: list[str])` que genera el Memorándum en Word (`.docx`) y la Presentación Ejecutiva de 4 diapositivas en PowerPoint (`.pptx`) dentro de `outputs/cases/{case_id}/`.

### Skill 5: Gobernanza y Auditoría Git (`src/skills/git_governance.py`)
* Expone funciones seguras (`shell=False`) para:
  1. Crear el directorio del caso `outputs/cases/{case_id}/` y guardar `queries.sql`, `evidence.json` y `draft_dictamen.md`.
  2. Ejecutar un commit inicial cuando la IA genera su borrador: `git commit -m "feat(case-{case_id}): borrador inicial IA [model: {model_name}]"`.
  3. Ejecutar un segundo commit cuando el analista humano edita o aprueba en Streamlit: `git commit -m "audit(case-{case_id}): dictamen validado por analista [status: approved]"`, calculando `git diff` para mostrar qué cambió el humano respecto a la propuesta del agente.

---

## 7. Plan de Implementación Paso a Paso (Orden de Ejecución para la IA)

**REGLA DE INTERACCIÓN:** Completa **UN SOLO PASO A LA VEZ**. Al terminar cada paso, detente, muestra al usuario cómo probarlo en su terminal y espera su confirmación antes de pasar al siguiente.

### PASO 0: Generación exclusiva del `README.md` de Prerrequisitos (Hacer primero)
* **Objetivo:** Crear únicamente el archivo `README.md` explicando al desarrollador qué debe tener instalado antes de correr cualquier script:
  1. Instalación de `Ollama` y descarga de modelos (`ollama pull qwen3.5:9b` o `qwen2.5:7b-instruct-q4_K_M`, y `ollama pull nomic-embed-text`).
  2. Verificación de GPU con `nvidia-smi` (confirmando que el modelo usa los 8 GB de VRAM de la RTX 4070 sin desbordar a la RAM).
  3. Instalación de `uv` (Astral) y creación del entorno virtual con Python 3.11 (`uv venv --python 3.11`).
  4. Ubicación exacta donde el usuario debe colocar `base_cards_sintetica_mini.csv` y `Base Cards para TEC - Diccionario de Variables.xlsx` (`data/raw/`).
* **Criterio de parada:** Entregar el `README.md` y `pyproject.toml`, y esperar confirmación del usuario.

### ETAPA 1: Base de Datos en DuckDB, Lectura del Dato y Conexión con Ollama + Testing de Prompts
* **Objetivo:** Asegurar que el dato se lee sin errores, que las métricas cuadran al centavo y que el modelo local en Ollama responde y genera SQL válido.
* **Archivos a crear en esta etapa:**
  1. `src/config.py`: Configuración centralizada.
  2. `src/data/dictionary_loader.py`: Lee `Base Cards para TEC - Diccionario de Variables.xlsx` y extrae las descripciones de las 22 variables.
  3. `src/data/init_db.py`: Lee `base_cards_sintetica_mini.csv`, aplica `TRIM()` a las columnas de texto, crea la columna `COHORT_ID`, monta la tabla persistente `cubo` y la vista enriquecida `v_cubo_metricas` en `data/duckdb/cubo_banamex.duckdb`, e imprime en consola una tabla de auditoría verificando las 499 filas, las 16 cohortes y las sumas de control (`REVENUE = $5,184,889.61`, `GCLAMTS = $32,467,306.48`, `RECOVERYAMTS = $17,507,667.21`, `NCLAMTS = $14,959,639.27`, `EXPENSES_TOTAL = $626,989.91`).
  4. `tests/test_db_reading.py`: Pruebas unitarias validando las identidades contables (`NCL = GCL - RECOVERY`, `EXPENSES_ACQ = 0` cuando `MOB > 0`).
  5. `tests/test_prompts_ollama.py`: Script interactivo de prueba de prompts que conecta con `ChatOllama`, le inyecta el esquema de `DuckDB` y prueba 3 prompts reales (Nivel 1 descriptivo, Nivel 2 causa raíz en Aeropuerto vs Branch, Nivel 3 dictamen por Score) mostrando en consola el razonamiento del modelo y los tiempos de respuesta en la RTX 4070.

### ETAPA 2: Implementación de las Skills, Guardrail Anti-Alucinaciones y Grafo en LangGraph
* **Objetivo:** Dotar al LLM de las herramientas tipadas con `Pydantic` y orquestar el flujo cíclico.
* **Archivos a crear en esta etapa:**
  1. `data/politicas_internas/manual_apetito_riesgo.md`: Documento normativo base para pruebas de RAG.
  2. `src/skills/cubo_sql_tools.py`: Las 3 herramientas de consulta sobre DuckDB (incluyendo `ejecutar_sql_select_seguro` con autocorrección).
  3. `src/skills/viz_tools.py`: Generador de las 6 gráficas financieras (Plotly + PNG).
  4. `src/skills/rag_tools.py`: Conexión con ChromaDB local y `nomic-embed-text`.
  5. `src/skills/report_tools.py` y `src/skills/git_governance.py`: Generación de `.docx`/`.pptx` y commits de auditoría.
  6. `src/agent/prompts.py`, `src/agent/guardrails.py` y `src/agent/graph.py`: El `StateGraph` de LangGraph que une las Skills, verifica con Regex que ninguna cifra sea inventada y pausa la ejecución antes del cierre del dictamen.

### ETAPA 3: Implementación de la Consola Híbrida en Streamlit
* **Objetivo:** Construir `app/streamlit_app.py` con diseño de 3 paneles:
  * **Panel Izquierdo (Selector de Casos / Alertas Basadas en Reglas Paramétricas del Cubo):** Mientras no exista el modelo de ML, muestra las cohortes que violan umbrales paramétricos en DuckDB (ej. `Branch | 01| Young < 25 | 130-140` con 29.2% de pérdida neta, y `Aeropuerto | 02| Young 25-30 | 141-150` con 22.9%).
  * **Panel Central (Lienzo de Evidencia, Gráficas y Dictamen Editable):** Muestra los KPIs del segmento, las gráficas interactivas de Plotly, las consultas SQL exactas ejecutadas por el agente, el borrador del dictamen en un editor de texto y los botones **[Aprobar y Generar DOCX/PPTX + Git Commit]** y **[Ver Git Diff]**.
  * **Panel Derecho (Chat Copiloto Investigador):** Ventana de chat conectada al grafo en LangGraph para hacer preguntas ad-hoc en lenguaje natural sobre el cubo de datos.

### ETAPA 4 (Futura - Fuera de este MVP Inicial): Integración del Módulo de Machine Learning
* **Nota:** Solo cuando las Etapas 1, 2 y 3 estén funcionando y validadas, se agregará `src/ml/anomaly_detector.py` (`IsolationForest` normalizado por `MOB`, `K-Means` y `DecisionTreeClassifier`).
