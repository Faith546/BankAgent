from langchain_ollama import ChatOllama

from src.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from src.skills.recuerdame.clasificador import puntaje_relevancia

aviso_fuera = ("Este archivo no parece estar relacionado con banca, crédito o el portafolio de tarjetas, "
               "por eso no lo analicé. Sube un reporte, una tabla o una gráfica del portafolio.")


def es_del_dominio(texto):
    if not texto.strip():
        return False
    # si ya menciona cosas del cubo (canales, productos, perdida, morosidad) lo aceptamos sin preguntar
    if puntaje_relevancia(texto[:3000], "agente") >= 2:
        return True
    # si no, le preguntamos al modelo con el inicio del texto
    prompt = f"""Decide si este contenido pertenece al dominio de banca, crédito, tarjetas de crédito, riesgo financiero,
finanzas o análisis de datos de un portafolio. Responde solo SI o NO.

Contenido
{texto[:2000]}"""
    try:
        llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.0, reasoning=False, num_predict=5)
        respuesta = llm.invoke(prompt).content.strip().lower()
    except Exception as e:
        # si el modelo falla no bloqueamos, el analisis normal avisara si hay error
        print("no se pudo revisar el dominio", e)
        return True
    return respuesta.startswith("si") or respuesta.startswith("sí")
