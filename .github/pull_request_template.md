## Resumen del Cambio
<!-- Describe brevemente qué resuelve este PR y enlaza la issue (ej. Closes #10) -->

## Tipo de Cambio
- [ ] `feat` (nueva funcionalidad / skill)
- [ ] `fix` (corrección de error)
- [ ] `refactor` (mejora interna / contratos)
- [ ] `docs` (documentación / contexto)
- [ ] `test` (pruebas / benchmark)

## Checklist Obligatorio (Definition of Done)
- [ ] **PEP 8 limpio:** `uv run ruff format --check src app tests` y `uv run ruff check src app tests` pasan con 0 errores.
- [ ] **Nombrado limpio:** Sin `camelCase`, espacios ni acentos en nombres de archivos/carpetas; sin `print()` sueltos al importar.
- [ ] **Pruebas:** `uv run pytest` pasa completo y los módulos nuevos tienen pruebas en `tests/`.
- [ ] **Sin duplicidad (SSOT):** No se duplicaron consultas DuckDB, gráficas, paletas ni plantillas existentes.
- [ ] **Sandbox y dominio bancario:** Cero APIs externas, `DuckDB(read_only=True)`, sin `shell=True` ni secretos/CSVs pesados.
- [ ] **Documentación y contexto:** Si se agregaron módulos, librerías o variables de config, se actualizó `docs/contexto/` y `docs/arquitectura/ARQUITECTURA_Y_LIBRERIAS.md`.
