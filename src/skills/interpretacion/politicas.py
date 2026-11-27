from datetime import datetime
from pathlib import Path

from src.config import POLICIES_DIR
from src.skills.interpretacion.analisis import leer_documento
from src.skills.interpretacion.dominio import aviso_fuera, es_del_dominio
from src.skills.interpretacion.ragDynamico import partir
from src.skills.rag_tools import _get_collection, _split_markdown_sections

extensiones = [".md", ".pdf", ".docx"]


def texto_de(nombre, contenido):
    # los markdown se leen directo, los pdf y word con leer_documento
    if Path(nombre).suffix.lower() == ".md":
        return contenido.decode("utf-8", errors="ignore")
    return leer_documento(contenido, nombre)


def secciones_de(texto):
    # cortamos por secciones ## igual que rag_tools y si una sale muy larga la partimos en pedazos
    secciones = []
    for s in _split_markdown_sections(texto):
        secciones.extend(partir(s) if len(s) > 1500 else [s])
    return secciones


def indexar(nombre, texto):
    coleccion = _get_collection()
    # borramos las secciones viejas de este manual para que no queden dos versiones
    coleccion.delete(where={"source": nombre})
    secciones = secciones_de(texto)
    if secciones:
        coleccion.upsert(
            ids=[f"{nombre}_sec_{i}" for i in range(len(secciones))],
            documents=secciones,
            metadatas=[{"source": nombre, "section_index": i} for i in range(len(secciones))],
        )
    return len(secciones)


def guardar_politica(nombre, contenido):
    # usamos solo el nombre del archivo para que no se pueda escribir fuera de la carpeta
    nombre = Path(nombre).name
    if Path(nombre).suffix.lower() not in extensiones:
        raise ValueError("Solo se aceptan manuales en md, pdf o docx")
    texto = texto_de(nombre, contenido)
    if not es_del_dominio(texto):
        raise ValueError(aviso_fuera)
    # primero indexamos y despues guardamos el archivo, asi si falla ollama no queda a medias
    total = indexar(nombre, texto)
    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    (POLICIES_DIR / nombre).write_bytes(contenido)
    return total


def listar_politicas():
    if not POLICIES_DIR.exists():
        return []
    try:
        coleccion = _get_collection()
    except Exception as e:
        print("no se pudo abrir chromadb", e)
        coleccion = None
    lista = []
    for archivo in sorted(POLICIES_DIR.iterdir()):
        if archivo.suffix.lower() not in extensiones:
            continue
        secciones = None
        if coleccion is not None:
            secciones = len(coleccion.get(where={"source": archivo.name})["ids"])
        # sacamos la fecha de cuando se subio para mostrarla en la tarjeta
        fecha = datetime.fromtimestamp(archivo.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        lista.append({"nombre": archivo.name, "secciones": secciones, "fecha": fecha})
    return lista


def borrar_politica(nombre):
    nombre = Path(nombre).name
    _get_collection().delete(where={"source": nombre})
    archivo = POLICIES_DIR / nombre
    if archivo.exists():
        archivo.unlink()


def contenido_politica(nombre):
    nombre = Path(nombre).name
    archivo = POLICIES_DIR / nombre
    # los markdown los mostramos tal cual, los pdf y word con las secciones que ya leimos al subirlos
    if archivo.suffix.lower() == ".md" and archivo.exists():
        return archivo.read_text(encoding="utf-8", errors="ignore")
    datos = _get_collection().get(where={"source": nombre})
    piezas = sorted(zip(datos["metadatas"], datos["documents"]), key=lambda x: x[0].get("section_index", 0))
    return "\n\n".join(doc for _, doc in piezas)
