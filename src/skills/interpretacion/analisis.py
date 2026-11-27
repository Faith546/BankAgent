from pathlib import Path
from typing import Literal

from langchain_ollama import ChatOllama
from pydantic import BaseModel

from src.config import (
    MAX_NCL_RATE_PCT,
    MAX_OVER30_RATE_PCT,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
)
from src.skills.interpretacion.imagenes import leer_imagen, leer_pdf_escaneado
from src.skills.interpretacion.leerdocx import leer_docx
from src.skills.interpretacion.leerpdf import leer_pdf


def leer_documento(archivo, nombre):
    # por la extension sabemos si es pdf, word o imagen
    extension = Path(nombre).suffix.lower()
    if extension == ".pdf":
        pdf = leer_pdf(archivo)
        texto = pdf["texto"]
        if pdf["paginas_sin_texto"]:
            texto += "\n\n" + leer_pdf_escaneado(archivo, pdf["paginas_sin_texto"])
        return texto.strip()
    if extension == ".docx":
        return leer_docx(archivo)
    if extension in [".png", ".jpg", ".jpeg"]:
        return leer_imagen(archivo)
    raise ValueError("Solo se pueden leer archivos pdf, docx, png o jpg")


def analizar_documento(archivo, nombre, pregunta):
    texto = leer_documento(archivo, nombre)
    if not texto:
        return "No se encontró texto en el documento."

    llm = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.2,
        reasoning=False,
        num_ctx=OLLAMA_NUM_CTX,
        num_predict=1500,
    )
    # cortamos el texto para que quepa en el contexto del modelo
    texto = texto[: OLLAMA_NUM_CTX * 2]
    prompt = (
        "Eres analista senior de riesgos del portafolio de tarjetas de Banamex.\n"
        "Regla principal: todas las cifras van con dígitos copiadas tal cual del documento "
        "(ej. 5.57% o $242.1 millones). Nunca escribas un número con letra.\n"
        "Las cantidades de dinero son pesos mexicanos, nunca digas dólares.\n"
        "Responde la pregunta usando solo lo que dice el documento, no inventes ni recalcules.\n"
        "Si la respuesta no está en el documento dilo.\n"
        "Cuando uses un dato di de qué página o tabla sale si el documento lo indica.\n"
        "Responde en un solo párrafo de 3 a 6 oraciones.\n"
        "Escribe en prosa, sin viñetas, sin markdown y sin dos puntos.\n\n"
        f"Pregunta  {pregunta}\n\n"
        f"Documento {nombre}\n{texto}"
    )
    return llm.invoke(prompt).content.strip()


def responder_con_documentos(pregunta, fragmentos, historial="", modelo=OLLAMA_MODEL, estilo=""):
    # respondemos con los pedazos que encontro el rag y con la conversacion previa del chat
    if not fragmentos:
        return "No se encontró texto en el documento."
    llm = ChatOllama(
        model=modelo,
        base_url=OLLAMA_BASE_URL,
        temperature=0.2,
        reasoning=False,
        num_ctx=OLLAMA_NUM_CTX,
        num_predict=1500,
    )
    estilo_final = estilo or (
        "Responde en un solo párrafo de 3 a 6 oraciones. "
        "Escribe en prosa, sin viñetas, sin markdown y sin dos puntos."
    )
    prompt = (
        "Eres analista senior de riesgos del portafolio de tarjetas de Banamex.\n"
        "Regla principal: todas las cifras van con dígitos copiadas tal cual del documento "
        "(ej. 5.57% o $242.1 millones). Nunca escribas un número con letra.\n"
        "Las cantidades de dinero son pesos mexicanos, nunca digas dólares.\n"
        "Responde usando solo lo que dicen los fragmentos de abajo, no inventes ni recalcules.\n"
        "Usa la conversación previa solo para entender de qué se está hablando.\n"
        "Si la respuesta no está en los fragmentos dilo.\n"
        "Cuando uses un dato di de qué documento o tabla sale.\n"
        f"{estilo_final}\n\n"
        f"Conversación previa\n{historial}\n\n"
        f"Pregunta  {pregunta}\n\n"
        f"Fragmentos de los documentos del chat\n{fragmentos}"
    )
    return llm.invoke(prompt).content.strip()


def numeros_en(texto):
    import re

    return {
        f"{float(n.replace(',', '').rstrip('.')):g}" for n in re.findall(r"\d[\d,]*\.?\d*", texto)
    }


def analizar_datos_grafica(
    titulo, datos_grafica, segmento, historial="", modelo=OLLAMA_MODEL, estilo=""
):
    # Analizamos la grafica con sus datos en texto (sin vision) para ahorrar tokens
    llm = ChatOllama(
        model=modelo,
        base_url=OLLAMA_BASE_URL,
        temperature=0.2,
        reasoning=False,
        num_ctx=OLLAMA_NUM_CTX,
        num_predict=900,
    )
    estilo_final = estilo or (
        "Responde en un párrafo de 4 a 6 oraciones, en prosa, "
        "sin viñetas, sin markdown y sin dos puntos."
    )
    prompt = (
        "Eres analista senior de riesgos del portafolio de tarjetas de Banamex.\n"
        f"Analiza la gráfica {titulo} del segmento {segmento} usando solo los datos de abajo.\n"
        "Regla principal: todas las cifras van con dígitos copiadas tal cual de los datos. "
        "Nunca escribas un número con letra.\n"
        "Usa el símbolo % en lugar de la palabra por ciento y escribe los meses con dígitos "
        "(ej. MOB 7). Si las series cruzan su límite en meses distintos, dilo por separado.\n"
        "No inventes ni recalcules cifras. Las cantidades de dinero son pesos mexicanos.\n"
        "Los valores son porcentajes sobre el saldo y el eje x son meses en libros (MOB).\n"
        "Explica qué muestra la gráfica, la tendencia, máximos, mínimos y si pasa los límites.\n"
        "Para máximo, mínimo y cruces usa exactamente las líneas de Hechos y Límite.\n"
        "Si una serie está ARRIBA del límite dilo claramente como riesgo.\n"
        f"{estilo_final}\n\n"
        f"Conversación previa\n{historial or 'ninguna'}\n\n"
        f"Datos de la gráfica\n{datos_grafica}"
    )
    # revisamos que no traiga cifras que no salen de los datos, igual que el guardrail
    validas = numeros_en(f"{datos_grafica} {MAX_NCL_RATE_PCT} {MAX_OVER30_RATE_PCT} 30 100")
    aviso = ""
    texto = ""
    for intento in range(2):
        texto = llm.invoke(prompt + aviso).content.strip()
        malas = sorted(
            n for n in numeros_en(texto) if n not in validas and len(n.replace(".", "")) > 1
        )
        if not malas:
            return texto
        print("cifras que no salen de la grafica", malas)
        aviso = (
            "\nAntes usaste cifras que no están en los datos ("
            + ", ".join(malas)
            + "), no las uses."
        )
    return texto


def responder_conversacion(mensaje, historial="", modelo=OLLAMA_MODEL):
    # Cuando el usuario solo comenta o agradece contestamos breve, sin consultar el cubo
    llm = ChatOllama(
        model=modelo, base_url=OLLAMA_BASE_URL, temperature=0.3, reasoning=False, num_predict=80
    )
    prompt = (
        "Eres el copiloto de riesgos del portafolio de tarjetas de Banamex.\n"
        "El usuario solo hizo un comentario, no pidió datos. "
        "Contéstale en una oración, amable y natural, sin cifras.\n\n"
        f"Conversación previa\n{historial or 'ninguna'}\n\n"
        f"Comentario del usuario\n{mensaje}"
    )
    return llm.invoke(prompt).content.strip()


class Intencion(BaseModel):
    destino: Literal["reporte", "grafica", "grafica_en_pantalla", "conversacion", "agente"]
    opinion: Literal["pide_mas_detalle", "pide_menos", "pide_tabla", "le_gusto", "nada"]


def leer_intencion(mensaje, respuesta_anterior="", modelo=OLLAMA_MODEL):
    # Clasifica el destino del mensaje y la opinion sobre la respuesta anterior
    llm = ChatOllama(
        model=modelo, base_url=OLLAMA_BASE_URL, temperature=0.0, reasoning=False, num_predict=60
    )
    prompt = (
        "Clasifica el mensaje de un usuario con un agente de riesgos de tarjetas de crédito.\n\n"
        "destino es a dónde va el mensaje:\n"
        "reporte si pide que se le arme un reporte o documento.\n"
        "grafica si pide que se le haga una gráfica nueva.\n"
        "grafica_en_pantalla si pregunta por la gráfica que ya está viendo en pantalla.\n"
        "conversacion si solo es un comentario, agradecimiento o saludo sin pedir datos.\n"
        "agente para cualquier pregunta que necesite datos del portafolio.\n"
        "Si el usuario dice que no quiere un reporte o una gráfica, ese destino no aplica.\n\n"
        "opinion es lo que el mensaje dice de la respuesta anterior del agente:\n"
        "pide_mas_detalle si quiere que le explique más o no entendió.\n"
        "pide_menos si quiere algo más corto o directo.\n"
        "pide_tabla si quiere las cifras en una tabla.\n"
        "le_gusto si agradece o dice que la respuesta estuvo bien.\n"
        "nada si no opina de la respuesta anterior.\n\n"
        f"Respuesta anterior del agente\n{respuesta_anterior[:800] or 'ninguna'}\n\n"
        f"Mensaje del usuario\n{mensaje}"
    )
    try:
        return llm.with_structured_output(Intencion, method="json_schema").invoke(prompt)
    except Exception as exc:  # noqa: BLE001
        # si ollama falla mandamos la pregunta al agente y no premiamos ni castigamos
        print("no se pudo leer la intencion", exc)
        return Intencion(destino="agente", opinion="nada")
