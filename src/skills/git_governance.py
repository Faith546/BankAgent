"""Skill 5: Gobernanza y auditoría Git (Audit-as-Code) con subprocesos en lista blanca."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from src.config import CASES_DIR, PROJECT_ROOT


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Ejecuta comandos git seguros en lista blanca con shell=False."""
    return subprocess.run(
        ["git", *args],
        cwd=str(PROJECT_ROOT),
        shell=False,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def save_case_artifacts(
    case_id: str,
    queries: list[str],
    evidence: list[dict[str, Any]],
    draft_dictamen: str,
) -> Path:
    """Guarda queries.sql, evidence.json y draft_dictamen.md dentro de outputs/cases/{case_id}/."""
    case_dir = CASES_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    (case_dir / "queries.sql").write_text("\n\n-- ---\n\n".join(queries), encoding="utf-8")
    (case_dir / "evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (case_dir / "draft_dictamen.md").write_text(draft_dictamen, encoding="utf-8")
    return case_dir


def commit_ai_draft(case_id: str, model_name: str) -> str:
    """Registra en Git el borrador inicial generado por el agente."""
    case_dir = CASES_DIR / case_id
    rel_dir = case_dir.relative_to(PROJECT_ROOT).as_posix()
    _run_git(["add", rel_dir])

    status = _run_git(["status", "--porcelain", rel_dir]).stdout.strip()
    if not status:
        return "Sin cambios nuevos para commitear en borrador IA."

    msg = f"feat(case-{case_id}): borrador inicial IA [model: {model_name}]"
    _run_git(["commit", "-m", msg])
    return msg


def commit_human_approval(case_id: str) -> str:
    """Registra en Git la validación o edición final aprobada por el analista humano."""
    case_dir = CASES_DIR / case_id
    rel_dir = case_dir.relative_to(PROJECT_ROOT).as_posix()
    _run_git(["add", rel_dir])

    status = _run_git(["status", "--porcelain", rel_dir]).stdout.strip()
    if not status:
        return "Sin cambios nuevos para commitear en aprobación humana."

    msg = f"audit(case-{case_id}): dictamen validado por analista [status: approved]"
    _run_git(["commit", "-m", msg])
    return msg


def get_case_diff(case_id: str) -> str:
    """Devuelve el diff de Git del archivo draft_dictamen.md respecto al último commit."""
    draft_path = (CASES_DIR / case_id / "draft_dictamen.md").relative_to(PROJECT_ROOT).as_posix()
    try:
        unstaged = _run_git(["diff", "--", draft_path]).stdout
        if unstaged.strip():
            return unstaged
        last_commit_diff = _run_git(["diff", "HEAD~1", "HEAD", "--", draft_path]).stdout
        return last_commit_diff or "No hay diferencias registradas para este caso."
    except subprocess.CalledProcessError as exc:
        return f"No se pudo calcular git diff: {exc.stderr or exc}"
