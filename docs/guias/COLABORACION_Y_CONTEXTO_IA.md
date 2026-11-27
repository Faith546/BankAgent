# Guía de Colaboración y Protocolo de Contexto (Humanos + IA)

Este documento define las **reglas de trabajo colaborativo** del equipo (`Jose`, `Fab`, `Diego`) y las **instrucciones obligatorias para cualquier agente de IA de código** que colabore en `BankAgent`.

---

## 1. Flujo de Trabajo en Git (Ramas, Issues y Commits)

1. **Una rama por Issue:** Nunca trabajes cambios grandes directo en `main`. Crea una rama vinculada al número de issue:
   ```powershell
   git checkout main
   git pull origin main
   git checkout -b feat/issue-10-generador-contratos
   ```
   Prefijos permitidos: `feat/`, `fix/`, `refactor/`, `docs/`, `test/`, `chore/`.
2. **Commits atómicos y convencionales:**
   * `feat(skills): ...` — nueva funcionalidad o skill.
   * `fix(agent): ...` — corrección de error.
   * `refactor(contracts): ...` — mejora de contratos o código sin cambiar comportamiento.
   * `docs(guias): ...` — cambios en documentación o contexto.
   * `test(benchmark): ...` — nuevas pruebas o casos del Golden Dataset.
3. **Checklist obligatorio antes de hacer `git push` / Pull Request:**
   ```powershell
   uv run ruff format src app tests
   uv run ruff check src app tests
   uv run pytest tests/test_db_reading.py tests/test_skills_and_guardrails.py -v
   ```
   *(Si modificaste prompts, contratos o el grafo de LangGraph, corre también `uv run python -m tests.smoke_test_agent`).*
4. **Prohibido subir:** `.env`, `.env.*`, claves (`*.key`, `*.pem`), CSVs pesados (`data/*.csv`, `data/raw/*.csv`), `data/duckdb/*.duckdb`, `data/chromadb/` o `data/state/*.db`.

---

## 2. Dónde Guardar Cada Actualización (Mapa de Destino)

Tanto desarrolladores humanos como **agentes de IA** deben colocar cada tipo de cambio en su carpeta exacta:

| Tipo de cambio / actualización | Carpeta / Archivo exacto | Qué actualizar |
| :--- | :--- | :--- |
| **Configuración de entorno, setup o guías operativas** | [`docs/guias/`](.) | Actualizar `guia_arranque_local.md` o agregar nueva guía en `docs/guias/`. |
| **Contexto vivo, decisiones técnicas (ADR) y bitácoras de cambio** | [`docs/contexto/`](../contexto/README.md) | Dejar notas de handoff, decisiones de diseño y contexto relevante para futuras sesiones de IA. |
| **Cambios en arquitectura, librerías o diagramas** | [`docs/arquitectura/ARQUITECTURA_Y_LIBRERIAS.md`](../arquitectura/ARQUITECTURA_Y_LIBRERIAS.md) | Actualizar diagramas Mermaid, tabla de librerías y reglas de sandbox. |
| **Avance de Issues y tareas del equipo** | [`docs/planeacion/ISSUES.md`](../planeacion/ISSUES.md) y [`TASKS.md`](../planeacion/TASKS.md) | Marcar checkboxes `- [x]` y documentar bloqueos o cambios de alcance. |
| **Nuevas herramientas / Skills** | `src/skills/` + `src/agent/graph.py` | Registrar en `TOOLS` / `TOOL_MAP` con contrato Pydantic y pruebas en `tests/`. |
| **Nuevos parámetros globales** | `src/config.py` + `docs/guias/` | Declarar variable de entorno con default seguro y documentarla. |

---

## 3. Reglas Obligatorias para Agentes de IA que Trabajen en este Repo

Si estás usando una IA de código (Antigravity, Cursor, Copilot, Codex, Claude Code), **la IA debe seguir este protocolo**:

1. **Leer antes de editar:** Revisar primero [`README.md`](../../README.md), [`docs/contexto/`](../contexto/README.md), [`docs/arquitectura/ARQUITECTURA_Y_LIBRERIAS.md`](../arquitectura/ARQUITECTURA_Y_LIBRERIAS.md) y [`docs/guias/BUENAS_PRACTICAS.md`](BUENAS_PRACTICAS.md).
2. **Dejar trazabilidad del contexto:** Al terminar una feature o issue importante, crear o actualizar una nota breve en `docs/contexto/` explicando: *qué cambió, qué archivos se tocaron, qué decisiones se tomaron y cómo probarlo*.
3. **No romper el sandbox ni el dominio bancario:** Nunca introducir APIs cloud externas, `shell=True`, DDL/DML en DuckDB ni tools fuera del dominio financiero/bancario.
4. **Verificar siempre antes de cerrar:** Correr `ruff check` (PEP 8) y `pytest` tras el último cambio.
5. **No reescribir historial ni hacer `git push` sin autorización explícita del usuario.**
