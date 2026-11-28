import chromadb
from chromadb.utils import embedding_functions

from src.config import CHROMADB_DIR, OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL

# coleccion aparte de la de politicas para no mezclar los manuales con lo que suben
nombre_coleccion = "documentos_chats"
tamano = 800
traslape = 100


def obtener_coleccion():
    # misma conexion y mismos embeddings que rag_tools.py
    CHROMADB_DIR.mkdir(parents=True, exist_ok=True)
    embed_fn = embedding_functions.OllamaEmbeddingFunction(
        url=f"{OLLAMA_BASE_URL}/api/embeddings",
        model_name=OLLAMA_EMBED_MODEL,
    )
    cliente = chromadb.PersistentClient(path=str(CHROMADB_DIR))
    return cliente.get_or_create_collection(name=nombre_coleccion, embedding_function=embed_fn)


def partir(texto):
    # cortamos el texto en pedazos con un poco de traslape para no partir ideas a la mitad
    pedazos = []
    inicio = 0
    while inicio < len(texto):
        pedazo = texto[inicio : inicio + tamano].strip()
        if pedazo:
            pedazos.append(pedazo)
        inicio += tamano - traslape
    return pedazos


def guardar_documento(chat_id, nombre, texto):
    pedazos = partir(texto)
    if not pedazos:
        return 0
    coleccion = obtener_coleccion()
    # si suben otra vez el mismo documento en el chat borramos el anterior
    coleccion.delete(where={"$and": [{"chat_id": chat_id}, {"nombre": nombre}]})
    coleccion.add(
        ids=[f"{chat_id}_{nombre}_{i}" for i in range(len(pedazos))],
        documents=pedazos,
        metadatas=[
            {"chat_id": chat_id, "nombre": nombre, "pedazo": i} for i in range(len(pedazos))
        ],
    )
    return len(pedazos)


def tiene_documentos(chat_id):
    coleccion = obtener_coleccion()
    return len(coleccion.get(where={"chat_id": chat_id}, limit=1)["ids"]) > 0


def buscar(chat_id, pregunta, cuantos=4):
    # buscamos solo en los documentos de este chat
    coleccion = obtener_coleccion()
    total = len(coleccion.get(where={"chat_id": chat_id})["ids"])
    if total == 0:
        return ""
    res = coleccion.query(
        query_texts=[pregunta], n_results=min(cuantos, total), where={"chat_id": chat_id}
    )
    partes = []
    for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
        partes.append(f"Documento {meta['nombre']}, fragmento {meta['pedazo'] + 1}\n{doc}")
    return "\n\n".join(partes)


def borrar_documentos_chat(chat_id):
    # cuando se borra un chat tambien se tiran sus pedazos
    obtener_coleccion().delete(where={"chat_id": chat_id})
