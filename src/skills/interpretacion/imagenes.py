from pathlib import Path

import ollama
import pymupdf

from src.config import OLLAMA_BASE_URL, OLLAMA_VISION_MODEL

prompt_vision = """Transcribe todo el texto que aparece en la imagen tal cual, con las cifras exactas como vienen.
Si hay tablas pásalas fila por fila separando las columnas con  |  .
Si hay gráficas di qué tipo son, qué mide cada eje y los valores que se alcancen a leer.
No inventes datos que no se vean en la imagen. Responde en español."""


def leer_imagen(archivo):
    # aceptamos la ruta de la imagen o los bytes que manda streamlit
    if isinstance(archivo, (str, Path)):
        archivo = Path(archivo).read_bytes()
    cliente = ollama.Client(host=OLLAMA_BASE_URL)
    res = cliente.chat(
        model=OLLAMA_VISION_MODEL,
        messages=[{"role": "user", "content": prompt_vision, "images": [archivo]}],
        options={"temperature": 0.1},
    )
    return res["message"]["content"].strip()


def leer_pdf_escaneado(archivo, numeros):
    if isinstance(archivo, (str, Path)):
        doc = pymupdf.open(str(archivo))
    else:
        doc = pymupdf.open(stream=archivo, filetype="pdf")

    paginas = []
    for n in numeros:
        # convertimos la pagina a png a 150 dpi para que qwen alcance a leer las letras chicas
        png = doc[n - 1].get_pixmap(dpi=150).tobytes("png")
        paginas.append(f"Página {n}\n{leer_imagen(png)}")
    doc.close()
    return "\n\n".join(paginas)