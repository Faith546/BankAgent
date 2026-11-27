from io import BytesIO
from pathlib import Path

from docx import Document


def leer_docx(archivo):
    # aceptamos la ruta del word o los bytes que manda streamlit
    if isinstance(archivo, (str, Path)):
        doc = Document(str(archivo))
    else:
        doc = Document(BytesIO(archivo))

    partes = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    # las tablas las pasamos fila por fila separando las columnas con  |
    for n, tabla in enumerate(doc.tables, start=1):
        filas = [" | ".join(c.text.strip() for c in fila.cells) for fila in tabla.rows]
        partes.append(f"Tabla {n}\n" + "\n".join(filas))

    return "\n\n".join(partes)
