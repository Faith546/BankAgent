"""Cargador del diccionario oficial de variables desde Excel hacia contexto Markdown."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import openpyxl

from src.config import DICTIONARY_XLSX_PATH


def load_dictionary(xlsx_path: Path | None = None) -> list[dict[str, Any]]:
    """Lee Sheet1 del Excel de diccionario y devuelve una lista estructurada de variables."""
    path = xlsx_path or DICTIONARY_XLSX_PATH
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el diccionario de variables en: {path}")

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb["Sheet1"] if "Sheet1" in wb.sheetnames else wb.active
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()

    if not rows:
        return []

    variables: list[dict[str, Any]] = []
    # La primera fila es el encabezado: (None, 'Variable', 'Descripción', 'Valor Mínimo', 'Valor Máximo')
    for row in rows[1:]:
        if not row or len(row) < 3:
            continue
        var_name = str(row[1]).strip() if row[1] is not None else ""
        if not var_name:
            continue
        description = str(row[2]).strip() if row[2] is not None else ""
        min_val = row[3] if len(row) > 3 and row[3] is not None else "NA"
        max_val = row[4] if len(row) > 4 and row[4] is not None else "NA"
        variables.append(
            {
                "variable": var_name,
                "descripcion": description,
                "valor_minimo": str(min_val),
                "valor_maximo": str(max_val),
            }
        )
    return variables


def dictionary_to_markdown(xlsx_path: Path | None = None) -> str:
    """Formatea el diccionario de variables como texto Markdown legible para prompts del LLM."""
    variables = load_dictionary(xlsx_path=xlsx_path)
    lines = ["# Diccionario de Variables — Cubo de Tarjetas Banamex", ""]
    for item in variables:
        desc_one_line = " ".join(item["descripcion"].splitlines())
        lines.append(
            f"- **`{item['variable']}`** "
            f"(Min: `{item['valor_minimo']}`, Max: `{item['valor_maximo']}`): "
            f"{desc_one_line}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(dictionary_to_markdown())

