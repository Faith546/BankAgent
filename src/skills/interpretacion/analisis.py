from pathlib import Path

from langchain_ollama import ChatOllama

from src.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_NUM_CTX
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


def responder_con_documentos(pregunta, fragmentos, historial=""):
    # respondemos con los pedazos que encontro el rag y con la conversacion previa del chat
    if not fragmentos:
        return "No se encontró texto en el documento."
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.2, reasoning=False,
                     num_ctx=OLLAMA_NUM_CTX, num_predict=1500)
    prompt = f"""Eres analista senior de riesgos del portafolio de tarjetas de Banamex.
Regla principal, todas las cifras van con dígitos copiadas tal cual del documento, por ejemplo 5.57% o $242.1 millones. Nunca escribas un número con letra.
Las cantidades de dinero son pesos mexicanos, nunca digas dólares.
Responde la pregunta usando solo lo que dicen los fragmentos de abajo, no inventes ni recalcules.
Usa la conversación previa solo para entender de qué se está hablando.
Si la respuesta no está en los fragmentos dilo.
Cuando uses un dato di de qué documento o tabla sale.
Responde en un solo párrafo de 3 a 6 oraciones.
Escribe en prosa, sin viñetas, sin markdown y sin dos puntos.

Conversación previa
{historial}

Pregunta  {pregunta}

Fragmentos de los documentos del chat
{fragmentos}"""
    return llm.invoke(prompt).content.strip()


def numeros_en(texto):
    import re
    return {f"{float(n.replace(',', '').rstrip('.')):g}" for n in re.findall(r"\d[\d,]*\.?\d*", texto)}


def analizar_datos_grafica(titulo, datos_grafica, segmento, historial=""):
    # analizamos la grafica con sus datos en texto, sin captura ni modelo de vision, asi gasta muchos menos tokens
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.2, reasoning=False,
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
Responde en un párrafo de 4 a 6 oraciones, en prosa, sin viñetas, sin markdown y sin dos puntos.

Conversación previa
{historial or "ninguna"}

Datos de la gráfica
{datos_grafica}"""
    # revisamos que no traiga cifras que no salen de los datos, igual que el guardrail
    validas = numeros_en(datos_grafica + " 15 25 30 100")
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