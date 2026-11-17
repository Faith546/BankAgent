"""Guardrail anti-alucinación: verifica que las cifras del LLM provengan de las herramientas."""

from __future__ import annotations

import json
import re
from typing import Any

# Números estructurales o de referencia de negocio que no requieren venir de una celda SQL
_ALLOWED_CONTEXT_NUMBERS = {
    0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 10.0, 12.0, 15.0, 18.0, 20.0, 25.0, 30.0, 32.0, 40.0, 100.0,
    2024.0, 2025.0, 2026.0,
}

_NUMBER_REGEX = re.compile(r"(?<![A-Za-z0-9_])(-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?)")


def extract_numbers_from_evidence(evidence_items: list[Any]) -> set[float]:
    """Extrae todos los valores numéricos presentes en las respuestas JSON de herramientas."""
    found: set[float] = set()

    def _walk(obj: Any) -> None:
        if isinstance(obj, bool):
            return
        if isinstance(obj, (int, float)):
            found.add(float(obj))
            found.add(round(float(obj), 2))
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)
        elif isinstance(obj, str):
            for match in _NUMBER_REGEX.findall(obj):
                try:
                    found.add(float(match.replace(",", "")))
                except ValueError:
                    pass

    for item in evidence_items:
        if isinstance(item, str):
            try:
                _walk(json.loads(item))
            except json.JSONDecodeError:
                _walk(item)
        else:
            _walk(item)

    return found


def verify_response_numbers(
    response_text: str,
    evidence_items: list[Any],
    tolerance: float = 0.05,
) -> tuple[bool, list[str]]:
    """Verifica que los números en la respuesta del LLM existan en la evidencia de herramientas."""
    if not evidence_items:
        return True, []

    # Ignorar rangos de edad/score conocidos como '01|', '25-30', '130-140', '202401'
    sanitized = re.sub(r"\b\d{3}-\d{3}\b", " ", response_text)
    sanitized = re.sub(r"\b202[4-6]\d{2}\b", " ", sanitized)
    sanitized = re.sub(r"\b0[1-3]\|\s*Young[^,\n]*", " ", sanitized)
    sanitized = re.sub(r"\bCASO-\d{4}-\d{4}\b", " ", sanitized)

    allowed_evidence = extract_numbers_from_evidence(evidence_items)
    ungrounded: list[str] = []

    for match in _NUMBER_REGEX.findall(sanitized):
        raw = match.replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue

        if val in _ALLOWED_CONTEXT_NUMBERS:
            continue
        if any(abs(val - ref) <= max(tolerance, abs(ref) * 1e-4) for ref in allowed_evidence):
            continue
        if match not in ungrounded:
            ungrounded.append(match)

    return len(ungrounded) == 0, ungrounded
