# Manual de Usuario — BankAgent (Consola de Análisis de Portafolio Banamex)

Guía práctica pensada para el **analista de riesgo y usuario final** (sin necesidad de tocar código). Explica cómo navegar la consola web, interpretar alertas, usar el Copiloto Investigador, subir políticas y generar entregables ejecutivos auditables.

---

## 1. Qué es BankAgent (y qué NO hace)

* **Qué analiza:** El desempeño agregado de **cohortes (`VINTAGE`) y segmentos** de tarjetas de crédito a lo largo de su maduración (`MOB 0` a `MOB 32`): morosidad (`Over30`), pérdida neta (`NCL`), recuperación de cobranza, ingresos, gastos y rentabilidad (`ROA Neto`).
* **Qué NO analiza:** No contiene datos de clientes individuales (PII) ni transacciones unitarias, y **rechaza preguntas, documentos o gráficas ajenas al dominio financiero/bancario**.
* **Cero cifras inventadas:** Todos los números salen de la base local **DuckDB**; el asistente nunca calcula sumas ni promedios "de memoria".

---

## 2. Cómo Abrir la Aplicación

1. Verifica que **Ollama** esté activo en tu equipo (o apuntando al servidor configurado).
2. Abre PowerShell en la carpeta del proyecto y ejecuta:
   ```powershell
   uv run streamlit run app/streamlit_app.py
   ```
3. Se abrirá la consola en tu navegador en `http://localhost:8501`.

---

## 3. Recorrido por la Interfaz

### A. Barra Lateral Izquierda (Navegación, Alertas y Conversaciones)
1. **Filtro por Canal y Alertas Activas:** Muestra automáticamente los segmentos maduros (`MOB ≥ 6`) que superan los límites de apetito de riesgo (`NCL/ENR > 15%` u `Over30/ENR > 25%`). Haz clic en cualquier caso (`CASO-2026-XXXX`) para cargarlo en el panel principal.
2. **Selector de Modelo:** Permite alternar entre perfiles configurados (`Rápido`, `Normal`, `Potente`) según la profundidad deseada.
3. **Conversaciones:** Crea chats independientes (*Chat nuevo*), cambia entre conversaciones anteriores o borra hilos antiguos sin mezclar el contexto entre análisis.

---

### B. Panel Central (5 Pestañas de Trabajo)

En la parte superior verás el **semáforo de apetito** (`Fuera de Apetito` en rojo, `Vigilancia` en ámbar, `En Apetito` en verde) y **4 tarjetas KPI** (*Cuentas Iniciales MOB 0*, *Severidad NCL/ENR*, *Morosidad Over30/ENR* y *Utilidad Neta Acumulada* con sus diferencias contra el límite de política).

1. **Gráficas Financieras:**
   * Cambia con un clic entre las 6 vistas interactivas: **Curva S (Maduración)**, **Curva J (ROA Neto)**, **Puente P&L**, **Heatmap Severidad**, **Matriz Cuadrantes** y **Embudo Cobranza**.
   * Abre el desplegable *Resumen Contable del Segmento* para revisar los montos exactos verificados en DuckDB.
2. **Dictamen & Human-in-the-Loop:**
   * Haz clic en **Analizar con IA** para que el agente consulte DuckDB + manual de políticas y redacte un borrador.
   * **Revisión humana obligatoria:** Edita libremente el texto del dictamen en el cuadro de texto.
   * Haz clic en **Aprobar y Generar DOCX/PPTX + Git Commit** para compilar y descargar:
     * **Memorándum Ejecutivo (`.docx`)**
     * **Presentación de Comité 16:9 de 5 láminas (`.pptx`)**
   * Usa **Ver Git Diff de Auditoría** para comparar qué modificó el analista respecto al borrador original de la IA.
3. **Auditoría SQL & Telemetría:**
   * Consulta el porcentaje usado de la **ventana de contexto** (`tokens / num_ctx`), número de llamadas al modelo y latencia.
   * Revisa el código SQL exacto de solo lectura que ejecutó el agente para respaldar sus cifras.
4. **Resultados:**
   * Concentra las tablas, gráficas y reportes (Word / vista previa HTML editable / PDF) que le hayas pedido directamente al Copiloto dentro del chat activo.
5. **Políticas:**
   * Sube nuevos manuales o lineamientos internos en **`.md`, `.pdf` o `.docx`** (si pertenecen al dominio bancario se indexan automáticamente en ChromaDB).
   * Consulta el contenido indexado o elimina manuales obsoletos.

---

### C. Panel Derecho — Copiloto Investigador (Chat)
* Escribe preguntas en lenguaje natural sobre cualquier canal, producto, cohorte o política (o usa las **preguntas sugeridas** de un clic).
* **Adjuntar archivos en el chat:** Puedes subir `.pdf`, `.docx` o imágenes de gráficas (`.png`, `.jpg`, `.jpeg`) directamente en la barra del chat para pedir análisis relacionados con el portafolio.
* **Retroalimentación:** En la última respuesta puedes usar los botones de valoración para que el copiloto ajuste el estilo de respuesta (*corta*, *detallada* o *con tabla*).

---

## 4. Ejemplos de Preguntas Útiles

* *Descriptivas:* `"¿Cuántas cuentas iniciales (MOB = 0) tiene el canal Branch?"`
* *Comparativas:* `"Compara la pérdida neta (NCL/ENR %) entre Aeropuerto y Branch en cohortes maduras."`
* *Interpretación visual:* `"¿Qué muestra la gráfica que tengo en pantalla y en qué MOB cruza el límite?"`
* *Políticas y dictamen:* `"¿Qué dice el manual sobre la eficiencia mínima de recuperación de cobranza?"`
* *Reportes desde chat:* `"Genera un reporte comparando el producto Clasica y Oro en MOB >= 6."`

---

## 5. Solución Rápida de Problemas Comunes

| Síntoma | Causa probable | Cómo resolverlo |
| :--- | :--- | :--- |
| Error de conexión a `localhost:11434` | Ollama no está encendido o el servidor remoto no responde. | Abre Ollama (o verifica tu VPN / `OLLAMA_BASE_URL`). |
| "No se encontró la base DuckDB" | Falta construir `cubo_banamex.duckdb`. | Ejecuta `uv run python -m src.data.init_db`. |
| El asistente rechaza un archivo o pregunta | El contenido no pertenece al dominio financiero/bancario. | Sube únicamente documentos, gráficas o consultas del portafolio. |
| Aviso de *Guardrail* en una respuesta | Alguna cifra redactada no coincidió literalmente con DuckDB. | Revisa la pestaña *Auditoría SQL* o reformula la pregunta. |

---

> *Nota para el equipo:* Este manual debe actualizarse cada vez que cambien pestañas, botones o flujos visibles en `app/streamlit_app.py`.
