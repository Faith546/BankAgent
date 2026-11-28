from pathlib import Path

import pymupdf


def leer_pdf(archivo):
    # aceptamos la ruta del pdf o los bytes que manda streamlit
    if isinstance(archivo, (str, Path)):
        doc = pymupdf.open(str(archivo))
    else:
        doc = pymupdf.open(stream=archivo, filetype="pdf")

    paginas = []
    sin_texto = []
    for i, pagina in enumerate(doc, start=1):
        texto = pagina.get_text().strip()
        # si la pagina casi no trae texto es escaneada y la guardamos para el modelo de vision
        if len(texto) < 30:
            sin_texto.append(i)
        else:
            paginas.append(f"Página {i}\n{texto}")
    total = len(doc)
    doc.close()

    return {"texto": "\n\n".join(paginas), "total_paginas": total, "paginas_sin_texto": sin_texto}
