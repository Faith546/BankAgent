# Carpeta de Contexto Vivo (`docs/contexto/`)

Esta carpeta almacena el **contexto acumulativo del proyecto** para que tanto el equipo (`Jose`, `Fab`, `Diego`) como cualquier **agente de IA de código** puedan retomar el trabajo sin perder decisiones previas.

## Qué se guarda aquí
* **Bitácoras de cambios / handoffs por Issue:** Ej. `issue-10-generador-contratos.md` (qué se construyó, cómo se conecta, edge cases encontrados y cómo probarlo).
* **Decisiones de Arquitectura (ADR):** Ej. `adr-001-duckdb-vs-pandas.md`, `adr-002-sandbox-bancario.md`.
* **Resultados de Benchmarks:** Comparativas medidas de `tests/smoke_test_agent.py --benchmark` entre modelos (ej. `qwen3.5:9b` vs. `qwen2.5:7b-instruct-q4_K_M`) o cambios de prompt.

## Regla de mantenimiento
Al cerrar una issue relevante o tomar una decisión de diseño importante, agrega o actualiza un archivo `.md` aquí (en `snake_case`, sin espacios ni acentos) y enlázalo si aplica en [`docs/README.md`](../README.md).
