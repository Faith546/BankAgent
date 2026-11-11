# Contexto del Proyecto: Asistente Agéntico de Análisis de Portafolio (Banamex)

## 1. Visión General del Proyecto
Desarrollo de un sistema de Inteligencia Artificial Agéntica local para analizar un cubo de datos financieros de tarjetas de crédito. 
**Pivote crítico de negocio:** El sistema NO evalúa riesgo de fraude o morosidad de clientes individuales. Evalúa la rentabilidad, riesgo y deterioro de **cohortes agregadas** (segmentos completos de la cartera) a lo largo del tiempo.

## 2. Restricciones de Hardware y Entorno (CRÍTICO PARA LA IA DE CÓDIGO)
El sistema se ejecutará de forma local en una laptop con las siguientes especificaciones restrictivas:
* **GPU:** NVIDIA RTX 4070 (8 GB VRAM).
* **CPU:** Intel Core Ultra 9 185H (16 núcleos).
* **RAM:** 16 GB.
* **Modelo LLM Obligatorio:** `qwen2.5:7b-instruct-q4_K_M` (o similar en 7B cuantizado a Q4) corriendo en **Ollama**. NO sugerir modelos de 14B, 32B o 70B para evitar desbordamiento a la RAM (Out of Memory).
* **Gestión de Memoria:** Debido a los 16 GB de RAM, el procesamiento de datos debe ser In-Memory eficiente. PROHIBIDO cargar todo el dataset en memoria con `pandas.read_csv()` si no es estrictamente necesario; usar bases de datos analíticas.

## 3. Stack Tecnológico Definido
* **Inferencia LLM:** `ollama`, `langchain-ollama`.
* **Orquestación:** `langgraph` (StateGraph para flujos cíclicos y ToolCalling), `pydantic` (esquemas estrictos).
* **Procesamiento Numérico (El Cubo):** `duckdb` (Motor SQL in-memory para leer CSV/Parquet).
* **Memoria RAG (Políticas):** `chromadb` local con embeddings ligeros (`nomic-embed-text`).
* **Detección de Anomalías ML:** `scikit-learn` (K-Means, Isolation Forest).
* **Interfaz de Usuario:** `streamlit` (Dashboard de 3 columnas).
* **Visualización y Exportación:** `plotly`, `matplotlib`, `python-docx`, `python-pptx`.
* **Gestor de Paquetes:** `uv` o `poetry` (Python 3.11+).

## 4. Estructura de Datos (El Cubo)
El archivo principal es `base_cards_sintetica_mini.csv`. Cada fila es una instantánea mensual del desempeño de un segmento.
* **Agrupación Temporal:** `VINTAGE` (Mes de apertura, ej. 202401) y `MOB` (Months on Book, mes de maduración relativa 0, 1, 2...).
* **Dimensiones (Filtros):** `PRODUCT`, `CHANNEL`, `AGE_TAG`, `SCORE_TAG`, `STRATEGY`, `STRATEGY_SEGMENT`.
* **Métricas Clave:** 
  * `ACCOUNTS`, `ENRACCTS`, `ENRAMTS` (Volumen).
  * `OVER30AMTS` (Morosidad temprana).
  * `GCLAMTS` (Pérdida Bruta), `RECOVERYAMTS` (Recuperación), `NCLAMTS` (Pérdida Neta).
  * `REVENUE`, `EXPENSES_ACQ`, `EXPENSES_TOTAL` (Rentabilidad).

## 5. Diseño del Grafo y Skills (Herramientas)
El agente es un enrutador (Router Agent) con soporte para 4 niveles de peticiones (Análisis descriptivo, Diagnóstico de anomalías, Dictamen de originación, Generación de entregables). Las herramientas de Python (`@tool`) que se le expondrán deben tiparse estrictamente con **Pydantic**:

1. **`skill_consulta_cubo`:** Consultas SQL parametrizadas sobre DuckDB. Recibe métricas y dimensiones, devuelve tablas JSON agregadas.
2. **`skill_visualizacion`:** Genera gráficas estáticas (`.png`) con Matplotlib/Kaleido para exportar, e interactivas con Plotly para el dashboard.
3. **`skill_rag_memoria`:** Búsqueda por similitud en ChromaDB para contrastar los números de DuckDB contra las políticas de riesgo institucionales en Markdown.
4. **`skill_ml_pipeline`:** Ejecuta un modelo preentrenado (`.pkl`) para predecir si una cohorte terminará en números rojos.
5. **`skill_generador_reportes`:** Ensambla un Memorándum en `.docx` y un `.pptx` inyectando el texto y las gráficas generadas.

## 6. Reglas de Desarrollo y Gobernanza (DevSecOps)
Al generar código para este proyecto, la IA de asistencia debe acatar irrevocablemente las siguientes reglas:
* **Separación de Responsabilidades:** `DuckDB` es EXCLUSIVO para procesar números y tablas del CSV. `ChromaDB` es EXCLUSIVO para buscar texto en manuales. No usar RAG para matemáticas.
* **Cero Alucinaciones (JSON Strict):** Obligar al LLM a usar esquemas estructurados para llamar herramientas. Validar que las cifras del reporte provengan directamente del output de las herramientas.
* **Seguridad de Ejecución (No Bash):** El agente NUNCA debe ejecutar código arbitrario o `shell=True`. 
* **Audit-as-Code:** Toda salida generada (Dictámenes) debe guardarse en un directorio local (ej. `/outputs/caso_123/`) y versionarse automáticamente usando un subproceso de Git con Conventional Commits (`git commit -m "audit(...)"`).