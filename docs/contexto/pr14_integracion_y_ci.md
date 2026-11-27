# Integración PR #14, Candados CI/PEP 8 y Configuración `.env`

* **Fecha:** 2026-11-27
* **Alcance:** Consolidación tras el merge de PR #14 (`mejorasBankagent`) para garantizar cumplimiento de PEP 8, pruebas automáticas y configuración multi-entorno sin editar código.

## Cambios Clave
1. **Candados automáticos de calidad:**
   * Creados `AGENTS.md`, `.github/copilot-instructions.md`, `.github/pull_request_template.md` y `.github/workflows/ci.yml` (`ruff format --check`, `ruff check` y `pytest` offline).
   * Agregado `[tool.pytest.ini_options] pythonpath = ["."]` en `pyproject.toml` para que `uv run pytest` funcione igual en local y en Linux/GitHub Actions.
2. **Limpieza PEP 8 y `snake_case`:**
   * Resueltos 222 errores de PEP 8 en 32 archivos Python.
   * Renombrados `ragDynamico.py` $\rightarrow$ `src/skills/interpretacion/rag_dinamico.py` y `chatsPasados/` $\rightarrow$ `src/skills/recuerdame/chats_pasados/`.
3. **Pruebas unitarias para PR #14:**
   * Creado `tests/test_pr14_modules.py` (13 pruebas offline para `interpretacion/`, `recuerdame/`, `reporte/`, unificación de reportes y `load_dotenv`), llevando la suite total a **27 pruebas pasando**.
4. **Configuración `.env`:**
   * Creado `.env.example` y cargador `load_dotenv()` en `src/config.py` (sin dependencias extra; respeta variables del sistema operativo).
5. **Documentación:**
   * Creados `docs/guias/CONVENCIONES.md` y `docs/guias/MANUAL_USUARIO.md`; actualizados `README.md`, `docs/README.md` y `docs/arquitectura/ARQUITECTURA_Y_LIBRERIAS.md`.
