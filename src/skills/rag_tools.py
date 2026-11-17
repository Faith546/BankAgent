"""Skill 3: Memoria normativa RAG en ChromaDB local con embeddings de Ollama."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.config import CHROMADB_DIR, OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL, POLICIES_DIR

COLLECTION_NAME = "politicas_riesgo_banamex"


class RagQueryInput(BaseModel):
    """Consulta semántica contra el manual de apetito de riesgo."""

    consulta: str = Field(
        description="Pregunta o regla de negocio a buscar en el manual de políticas internas."
    )


def _split_markdown_sections(text: str) -> list[str]:
    """Divide un documento Markdown en fragmentos por secciones o párrafos."""
    chunks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and current:
            chunks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current).strip())
    return [c for c in chunks if c]


def _get_collection():
    """Obtiene o crea la colección ChromaDB con OllamaEmbeddingFunction."""
    CHROMADB_DIR.mkdir(parents=True, exist_ok=True)
    embed_fn = embedding_functions.OllamaEmbeddingFunction(
        url=f"{OLLAMA_BASE_URL}/api/embeddings",
        model_name=OLLAMA_EMBED_MODEL,
    )
    client = chromadb.PersistentClient(path=str(CHROMADB_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
    )


def ingest_policies(policies_dir: Path | None = None) -> int:
    """Ingesta todos los archivos .md de políticas internas en ChromaDB."""
    target_dir = policies_dir or POLICIES_DIR
    if not target_dir.exists():
        raise FileNotFoundError(f"No existe el directorio de políticas: {target_dir}")

    collection = _get_collection()
    docs: list[str] = []
    ids: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for md_file in sorted(target_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        sections = _split_markdown_sections(content)
        for idx, section in enumerate(sections):
            docs.append(section)
            ids.append(f"{md_file.stem}_sec_{idx}")
            metadatas.append({"source": md_file.name, "section_index": idx})

    if docs:
        collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
    return len(docs)


@tool(args_schema=RagQueryInput)
def consultar_politica_riesgo(consulta: str) -> str:
    """Consulta las políticas internas y umbrales de apetito de riesgo en ChromaDB."""
    try:
        collection = _get_collection()
        if collection.count() == 0:
            ingest_policies()

        results = collection.query(query_texts=[consulta], n_results=3)
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        if not documents:
            return json.dumps(
                {"aviso": "No se encontraron políticas relevantes para la consulta."},
                ensure_ascii=False,
            )

        matches = [
            {"fuente": meta.get("source", "manual"), "contenido": doc}
            for doc, meta in zip(documents, metadatas)
        ]
        return json.dumps({"consulta": consulta, "politicas": matches}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {
                "error_rag": str(exc),
                "aviso": "No se pudo consultar ChromaDB/Ollama embeddings; verifica que Ollama esté activo.",
            },
            ensure_ascii=False,
        )
