import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from langchain_ollama import ChatOllama

from src.config import OLLAMA_BASE_URL, OLLAMA_MODEL

carpeta = Path(__file__).resolve().parent / "chats_pasados"
# Cuando lo no resumido pasa de este tamaño se comprime, dejando los ultimos tal cual
umbral_comprimir = 3000
recientes = 4


def ruta_chat(chat_id):
    return carpeta / f"{chat_id}.json"


def ruta_resumen(chat_id):
    # el resumen va en su propio archivo para que el hilo de fondo nunca pise los mensajes del chat
    return carpeta / f"resumen_{chat_id}.json"


def leer_resumen(chat_id):
    ruta = ruta_resumen(chat_id)
    if not ruta.exists():
        return {"resumen": "", "comprimidos": 0}
    return json.loads(ruta.read_text(encoding="utf-8"))


def crear_chat():
    # el id es la fecha y hora para que nunca se repita y quede ordenado
    chat = {
        "id": f"chat_{datetime.now():%Y%m%d_%H%M%S}",
        "titulo": "Chat nuevo",
        "creado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "mensajes": [],
        "documento": None,
    }
    guardar_chat(chat)
    return chat


def guardar_chat(chat):
    carpeta.mkdir(parents=True, exist_ok=True)
    # el titulo sale de la primera pregunta del usuario
    if chat["titulo"] == "Chat nuevo" and chat["mensajes"]:
        chat["titulo"] = chat["mensajes"][0][1][:40]
    ruta_chat(chat["id"]).write_text(
        json.dumps(chat, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def cargar_chat(chat_id):
    return json.loads(ruta_chat(chat_id).read_text(encoding="utf-8"))


def listar_chats():
    # regresamos los chats del mas nuevo al mas viejo
    if not carpeta.exists():
        return []
    chats = [json.loads(r.read_text(encoding="utf-8")) for r in carpeta.glob("chat_*.json")]
    return sorted(chats, key=lambda c: c["id"], reverse=True)


def borrar_chat(chat_id):
    for ruta in [ruta_chat(chat_id), ruta_resumen(chat_id)]:
        if ruta.exists():
            ruta.unlink()


def ultimos_mensajes(chat, limite=6000):
    # arriba va el resumen de lo viejo y abajo los mensajes que todavia no se resumen
    guardado = leer_resumen(chat["id"])
    resumen = guardado["resumen"]
    lineas = []
    total = len(resumen)
    for m in reversed(chat["mensajes"][guardado["comprimidos"] :]):
        quien = "Usuario" if m[0] == "user" else "Asistente"
        linea = f"{quien}  {m[1]}"
        if total + len(linea) > limite:
            break
        lineas.insert(0, linea)
        total += len(linea)
    if resumen:
        return (
            "Resumen de la conversación anterior\n"
            + resumen
            + "\n\nMensajes recientes\n"
            + "\n".join(lineas)
        )
    return "\n".join(lineas)


def nombrar_chat(chat):
    # el agente le pone un nombre clave al chat con la primera pregunta
    pregunta = chat["mensajes"][0][1]
    prompt = (
        "Ponle un nombre clave de 2 a 4 palabras a esta conversación sobre el portafolio.\n"
        "Responde solo con el nombre, sin comillas ni puntos.\n\n"
        f"Pregunta  {pregunta}"
    )
    try:
        llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.2,
            reasoning=False,
            num_predict=20,
        )
        titulo = llm.invoke(prompt).content.strip().strip('"').strip(".")[:40]
    except Exception as e:
        print("no se pudo nombrar el chat", e)
        return chat

    # quitamos acentos y simbolos para que el nombre sirva como nombre de archivo
    clave = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode().lower()
    clave = re.sub(r"[^a-z0-9]+", "_", clave).strip("_")
    if not clave:
        return chat

    viejo = ruta_chat(chat["id"])
    viejo_resumen = ruta_resumen(chat["id"])
    chat["titulo"] = titulo
    # dejamos la fecha al inicio para que sigan ordenados y no se repitan
    chat["id"] = chat["id"][:20] + "_" + clave
    guardar_chat(chat)
    if viejo.exists():
        viejo.unlink()
    if viejo_resumen.exists():
        viejo_resumen.replace(ruta_resumen(chat["id"]))
    return chat


def numeros(texto):
    return {
        f"{float(n.replace(',', '').rstrip('.')):g}" for n in re.findall(r"\d[\d,]*\.?\d*", texto)
    }


def comprimir_chat(chat_id):
    # se corre en segundo plano despues de cada respuesta, si no hace falta no hace nada
    if not ruta_chat(chat_id).exists():
        return None
    mensajes = cargar_chat(chat_id)["mensajes"]
    guardado = leer_resumen(chat_id)
    pendientes = mensajes[guardado["comprimidos"] :]
    if sum(len(m[1]) for m in pendientes) < umbral_comprimir or len(pendientes) <= recientes:
        return None

    # resumimos todo lo pendiente menos los ultimos mensajes, esos se quedan tal cual
    hasta = len(mensajes) - recientes
    viejos = mensajes[guardado["comprimidos"] : hasta]
    texto_viejo = "\n".join(
        f"{'Usuario' if m[0] == 'user' else 'Asistente'}  {m[1]}" for m in viejos
    )
    prompt = (
        (
            "Resume esta conversación sobre el portafolio de tarjetas de Banamex para que el\n"
            "analista no pierda el hilo. Usa exactamente estos cinco campos, uno por renglón,\n"
            "y si un campo no tiene nada pon ninguno.\n"
            "Segmentos y filtros  canales, productos, vintages, scores o MOB analizados\n"
            "Documentos  nombres de los documentos que se subieron y de qué tratan\n"
            "Reportes y gráficas  qué reportes o gráficas se generaron y de qué\n"
            "Cifras clave  cifras importantes copiadas tal cual con dígitos y a qué se refieren\n"
            "Conclusiones  decisiones, recomendaciones o dudas pendientes\n"
            "No inventes nada que no esté abajo. Máximo 120 palabras.\n\n"
            f"Resumen anterior\n{guardado['resumen'] or 'ninguno'}\n\n"
        )
        + f"""Mensajes nuevos
{texto_viejo}"""
    )

    # revisamos que el resumen no traiga cifras que no salen de la conversacion
    validas = numeros(guardado["resumen"] + " " + texto_viejo)
    llm = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.0,
        reasoning=False,
        num_predict=600,
    )
    aviso = ""
    for intento in range(2):
        resumen = llm.invoke(prompt + aviso).content.strip()
        # los numeros de un solo digito como MOB 6 no se revisan, igual que en el reporte
        malas = sorted(
            n for n in numeros(resumen) if n not in validas and len(n.replace(".", "")) > 1
        )
        if not malas:
            datos = {"resumen": resumen, "comprimidos": hasta}
            ruta = ruta_resumen(chat_id)
            temporal = ruta.with_suffix(".tmp")
            temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
            temporal.replace(ruta)
            print("chat comprimido", chat_id, hasta, "mensajes")
            return datos
        aviso = (
            "\nAntes pusiste cifras que no están en la conversación ("
            + ", ".join(malas)
            + "), no las uses."
        )
    # si sigue inventando no guardamos nada y se intenta en la siguiente respuesta
    print("no se pudo comprimir sin inventar cifras", chat_id)
    return None
