from pathlib import Path
from typing import Literal

from langchain_ollama import ChatOllama
from pydantic import BaseModel

from src.config import MAX_NCL_RATE_PCT, MAX_OVER30_RATE_PCT, OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_NUM_CTX
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

    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.2, reasoning=False,
                     num_ctx=OLLAMA_NUM_CTX, num_predict=1500)
    # cortamos el texto para que quepa en el contexto del modelo
    texto = texto[:OLLAMA_NUM_CTX * 2]
    prompt = f"""Eres analista senior de riesgos del portafolio de tarjetas de Banamex.
Regla principal, todas las cifras van con dígitos copiadas tal cual del documento, por ejemplo 5.57% o $242.1 millones. Nunca escribas un número con letra.
Las cantidades de dinero son pesos mexicanos, nunca digas dólares.
Responde la pregunta usando solo lo que dice el documento de abajo, no inventes ni recalcules.
Si la respuesta no está en el documento dilo.
Cuando uses un dato di de qué página o tabla sale si el documento lo indica.
Responde en un solo párrafo de 3 a 6 oraciones.
Escribe en prosa, sin viñetas, sin markdown y sin dos puntos.

Pregunta  {pregunta}

Documento {nombre}
{texto}"""
    return llm.invoke(prompt).content.strip()


def responder_con_documentos(pregunta, fragmentos, historial="", modelo=OLLAMA_MODEL, estilo=""):
    # respondemos con los pedazos que encontro el rag y con la conversacion previa del chat
    if not fragmentos:
        return "No se encontró texto en el documento."
    llm = ChatOllama(model=modelo, base_url=OLLAMA_BASE_URL, temperature=0.2, reasoning=False,
                     num_ctx=OLLAMA_NUM_CTX, num_predict=1500)
    prompt = f"""Eres analista senior de riesgos del portafolio de tarjetas de Banamex.
Regla principal, todas las cifras van con dígitos copiadas tal cual del documento, por ejemplo 5.57% o $242.1 millones. Nunca escribas un número con letra.
Las cantidades de dinero son pesos mexicanos, nunca digas dólares.
Responde la pregunta usando solo lo que dicen los fragmentos de abajo, no inventes ni recalcules.
Usa la conversación previa solo para entender de qué se está hablando.
Si la respuesta no está en los fragmentos dilo.
Cuando uses un dato di de qué documento o tabla sale.
{estilo or "Responde en un solo párrafo de 3 a 6 oraciones. Escribe en prosa, sin viñetas, sin markdown y sin dos puntos."}

Conversación previa
{historial}

Pregunta  {pregunta}

Fragmentos de los documentos del chat
{fragmentos}"""
    return llm.invoke(prompt).content.strip()


def numeros_en(texto):
    import re
    return {f"{float(n.replace(',', '').rstrip('.')):g}" for n in re.findall(r"\d[\d,]*\.?\d*", texto)}


def analizar_datos_grafica(titulo, datos_grafica, segmento, historial="", modelo=OLLAMA_MODEL, estilo=""):
    # analizamos la grafica con sus datos en texto, sin captura ni modelo de vision, asi gasta muchos menos tokens
    llm = ChatOllama(model=modelo, base_url=OLLAMA_BASE_URL, temperature=0.2, reasoning=False,
                     num_ctx=OLLAMA_NUM_CTX, num_predict=900)
    prompt = f"""Eres analista senior de riesgos del portafolio de tarjetas de Banamex.
Analiza la gráfica {titulo} del segmento {segmento} usando solo los datos de abajo.
Regla principal, todas las cifras van con dígitos copiadas tal cual de los datos. Nunca escribas un número con letra.
Usa el símbolo % en lugar de la palabra por ciento y escribe los meses con dígitos, por ejemplo MOB 7. Si las series cruzan su límite en meses distintos, dilo por separado.
No inventes ni recalcules cifras. Las cantidades de dinero son pesos mexicanos.
Los valores de las series son porcentajes sobre el saldo y el eje x de las curvas son meses en libros (MOB).
Explica qué muestra la gráfica, la tendencia, dónde está lo más alto y lo más bajo y si algo pasa los límites de apetito.
Para el máximo, el mínimo y si una serie pasa su límite usa exactamente las líneas que empiezan con Hechos y Límite, no lo deduzcas tú.
Si una serie está ARRIBA del límite dilo claramente como un riesgo, nunca digas que está dentro del apetito.
{estilo or "Responde en un párrafo de 4 a 6 oraciones, en prosa, sin viñetas, sin markdown y sin dos puntos."}

Conversación previa
{historial or "ninguna"}

Datos de la gráfica
{datos_grafica}"""
    # revisamos que no traiga cifras que no salen de los datos, igual que el guardrail
    validas = numeros_en(f"{datos_grafica} {MAX_NCL_RATE_PCT} {MAX_OVER30_RATE_PCT} 30 100")
    aviso = ""
    texto = ""
    for intento in range(2):
        texto = llm.invoke(prompt + aviso).content.strip()
        malas = sorted(n for n in numeros_en(texto) if n not in validas and len(n.replace(".", "")) > 1)
        if not malas:
            return texto
        print("cifras que no salen de la grafica", malas)
        aviso = "\nAntes usaste cifras que no están en los datos (" + ", ".join(malas) + "), no las uses."
    return texto


def responder_conversacion(mensaje, historial="", modelo=OLLAMA_MODEL):
    # cuando el usuario solo comenta o agradece contestamos breve, sin consultar el cubo ni dar cifras
    llm = ChatOllama(model=modelo, base_url=OLLAMA_BASE_URL, temperature=0.3, reasoning=False, num_predict=80)
    prompt = f"""Eres el copiloto de riesgos del portafolio de tarjetas de Banamex.
El usuario solo hizo un comentario, no pidió datos. Contéstale en una oración, amable y natural, sin cifras.

Conversación previa
{historial or "ninguna"}

Comentario del usuario
{mensaje}"""
    return llm.invoke(prompt).content.strip()


class Intencion(BaseModel):
    destino: Literal["reporte", "grafica", "grafica_en_pantalla", "conversacion", "agente"]
    opinion: Literal["pide_mas_detalle", "pide_menos", "pide_tabla", "le_gusto", "nada"]


def leer_intencion(mensaje, respuesta_anterior="", modelo=OLLAMA_MODEL):
    # el modelo que escogio el usuario lee el mensaje y nos dice a donde va y que opina de la respuesta anterior
    llm = ChatOllama(model=modelo, base_url=OLLAMA_BASE_URL, temperature=0.0, reasoning=False,
                     num_predict=60)
    prompt = f"""Clasifica el mensaje de un usuario que platica con un agente de riesgos de tarjetas de crédito.

destino es a dónde va el mensaje.
reporte si pide que se le arme un reporte o documento.
grafica si pide que se le haga una gráfica nueva.
grafica_en_pantalla si pregunta por la gráfica que ya está viendo en pantalla, por ejemplo qué significa o qué muestra.
conversacion si solo es un comentario, agradecimiento o saludo y no pide ningún dato.
agente para cualquier pregunta que necesite datos del portafolio.
Si el usuario dice que no quiere un reporte o una gráfica, ese destino no aplica.

opinion es lo que el mensaje dice de la respuesta anterior del agente.
pide_mas_detalle si quiere que le explique más o no entendió.
pide_menos si quiere algo más corto o directo.
pide_tabla si quiere las cifras en una tabla.
le_gusto si agradece o dice que la respuesta estuvo bien.
nada si no opina de la respuesta anterior.

Respuesta anterior del agente
{respuesta_anterior[:800] or "ninguna"}

Mensaje del usuario
{mensaje}"""
    try:
        return llm.with_structured_output(Intencion, method="json_schema").invoke(prompt)
    except Exception as exc:  # noqa: BLE001
        # si ollama falla mandamos la pregunta al agente y no premiamos ni castigamos
        print("no se pudo leer la intencion", exc)
        return Intencion(destino="agente", opinion="nada")