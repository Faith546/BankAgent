# Guía de arranque (Adaptada a Ejecución 100% Local)

Esta es la adaptación de [`guia_arranque_original_ssh.md`](guia_arranque_original_ssh.md) para trabajar **en un solo equipo local** (Windows 11 + **NVIDIA RTX 4070 Laptop 8 GB VRAM** + **16 GB RAM**), sin depender de la estación universitaria por SSH ni de APIs externas.

---

## 1. Qué cambia respecto a la guía original (2 equipos vs. 1 equipo local)

| Aspecto | Guía Original (Laptop + Estación SSH) | Adaptación Local (Tu Máquina) |
| :--- | :--- | :--- |
| **Infraestructura** | Laptop + Estación RTX A4500 por SSH / `tmux` / Remote-SSH / túneles de puerto | **Todo corre en `localhost`** en la misma máquina (Ollama en `:11434`, Streamlit en `:8501`). |
| **Presupuesto VRAM** | 20 GB VRAM (RTX A4500), contexto `16,384`, opción de probar 27B | **8 GB VRAM dedicados (RTX 4070)**, contexto **`8,192`** tokens (para no desbordar a RAM compartida de Windows). |
| **Modelo LLM** | Qwen3.5 9B o 27B | **`qwen3.5:9b`** (~7.5 GB VRAM) o **`qwen2.5:7b-instruct-q4_K_M`** (~5.0 GB VRAM, más holgado en 8 GB). **No usar 27B** en local. |
| **Datos (`193 MB`)** | Copiar a estación por separado | Ya en `data/raw/base_cards_sintetica.csv` e ingerido en DuckDB (`1,089,833` filas). **Nota GitHub:** pesa >100 MB, así que no debe subirse a GitHub sin Git LFS o `.gitignore`. |

---

## 2. Estado Actual y Tareas Adaptadas

### Tarea 1 · Insumos del banco / socio formador
* **Ya resuelto:** Tienes el cubo sintético (`data/raw/base_cards_sintetica.csv`) y el diccionario (`data/raw/Base Cards para TEC - Diccionario de Variables.xlsx`).
* **Pendiente (si aplica):**
  * Pedir 2–3 documentos reales de apetito de riesgo (si no llegan, en Etapa 2 usamos `data/politicas_internas/manual_apetito_riesgo.md` como base).
  * Pedir plantillas `.docx` / `.pptx` del banco (si no llegan, `report_tools.py` genera plantillas base en `templates/`).
  * **Importante sobre GitHub:** `base_cards_sintetica.csv` pesa **~193 MB** y GitHub rechaza archivos >100 MB. Si vas a hacer `git push`, agrega `data/raw/*.csv` a `.gitignore`.

### Tarea 2 y 3 · Revisar hardware y entorno local *(Reemplaza revisión SSH)*
* **Ya resuelto:** Entorno `uv` con Python 3.11 (`.venv`), `pyproject.toml`, `src/config.py` y DuckDB (`cubo_banamex.duckdb`) ya funcionan en tu máquina.
* **Verificación rápida recomendada:**
  ```powershell
  nvidia-smi
  uv run pytest tests/test_db_reading.py -v
  ```

### Tarea 4 · Probar Ollama y Tool-Calling JSON en 8 GB VRAM *(Crítico antes de Etapa 2)*
En local, el riesgo principal no es el SSH sino **el límite de 8 GB VRAM** y el **modo de razonamiento (*thinking*) de Qwen3.5**, que a veces ensucia el JSON de herramientas.
* **Qué probar en PowerShell:**
  1. Correr la prueba de humo ya creada:
     ```powershell
     uv run python -m tests.test_prompts_ollama
     ```
  2. Monitorear `nvidia-smi -l 1` en otra ventana para confirmar que no desborda a RAM compartida y medir tokens/segundo.
  3. **Prueba de JSON de herramientas (10 repeticiones):** Verificar que el modelo devuelva JSON limpio cuando se le pida llamar una función. Si `qwen3.5:9b` mete bloques `<think>...</think>` que rompen el parseo o queda muy justo en VRAM, el plan alterno inmediato en local es cambiar `OLLAMA_MODEL` a `qwen2.5:7b-instruct-q4_K_M`.

### Tarea 5 · Entender el cubo de datos real (`1,089,833` filas)
* **Ya resuelto en parte:** `init_db.py` ya limpió espacios con `TRIM()`, creó `COHORT_ID` (`64,245` cohortes) y validó identidades contables.
* **Qué falta antes de escribir Pydantic en Etapa 2:** Sacar los valores únicos reales de `VINTAGE`, `STRATEGY`, `STRATEGY_SEGMENT`, `PRODUCT`, `CHANNEL`, `AGE_TAG`, `SCORE_TAG` desde `cubo_banamex.duckdb` para que los filtros de las herramientas coincidan exactamente con los datos reales.

### Tarea 6 · Golden Dataset inicial (10 casos verificados)
* **Para qué sirve:** Medir objetivamente si el agente acierta o inventa cifras, y comparar `qwen3.5:9b` vs `qwen2.5:7b-instruct-q4_K_M`.
* **Qué hacer:** Crear `tests/golden_dataset.json` (o `.csv`) con 10 preguntas reales (4 Nivel 1, 3 Nivel 2, 3 Nivel 3) cuyas cifras esperadas se calculen **directo en DuckDB**, nunca con el LLM.

### Tarea 7 y 8 · Contrato de herramientas y estructura de reportes
* **Ya definido en `docs/MVP_CONTEXT_AGENT_BANAMEX.md`:**
  * `cubo_sql_tools.py` (3 herramientas + validación `read_only=True`)
  * `viz_tools.py` (6 gráficas Plotly + PNG)
  * `rag_tools.py` (ChromaDB + `nomic-embed-text`)
  * `report_tools.py` (`.docx` + `.pptx`)
  * `git_governance.py` (commits de auditoría)

### Tarea 9 · Flujo de trabajo *(Simplificado a 1 equipo)*
* Todo vive en tu repo local y se respalda en GitHub con `git push` (sin `data/raw/*.csv`, `data/duckdb/*.duckdb`, ni `.venv`).
* Streamlit correrá directo en `http://localhost:8501` sin túneles SSH.

---

## 3. Checklist mínimo para arrancar Etapa 2 (Skills + LangGraph)
- [ ] `tests/test_prompts_ollama.py` ejecutado con éxito y VRAM estable bajo 8 GB en `nvidia-smi`.
- [ ] Confirmado si usamos `qwen3.5:9b` o `qwen2.5:7b-instruct-q4_K_M` para tool-calling JSON.
- [ ] Valores distintos de filtros verificados en `cubo_banamex.duckdb`.
- [ ] (Opcional recomendado) Golden Dataset de 10 casos listo en `tests/`.
