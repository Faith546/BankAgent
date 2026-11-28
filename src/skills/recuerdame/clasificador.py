import json
import re
import unicodedata
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB

from src.config import (
    MEMORIA_UTIL_DIR,
    VALID_AGE_TAGS,
    VALID_CHANNELS,
    VALID_PRODUCTS,
    VALID_SCORE_TAGS,
    VALID_STRATEGIES,
)

ruta_modelo = Path(__file__).resolve().parent / "modelo_clasificador.joblib"
umbral = 2
minimo_entrenar = 20
modelo = None

meses = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
palabras_clave = [
    "perdida",
    "morosidad",
    "over30",
    "ncl",
    "roa",
    "utilidad",
    "ingresos",
    "saldo",
    "recuperacion",
    "cobranza",
    "cosecha",
    "vintage",
    "mob",
    "canal",
    "producto",
    "score",
    "segmento",
    "limite",
    "apetito",
    "politica",
    "reporte",
    "grafica",
    "compara",
    "ranking",
    "riesgo",
    "cartera",
    "portafolio",
    "dictamen",
    "documento",
]
errores = ["no se pudo", "error al conectar", "sin respuesta del agente"]


def normalizar(texto):
    # pasamos a minusculas y quitamos acentos para comparar sin problemas
    texto = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return texto


# paso 1 reglas para quitar lo que esta roto


def limpiar_eventos(eventos):
    limpios = []
    vistos = set()
    for e in eventos:
        # si la respuesta fue un error el agente no se equivoco, se cayo algo
        if any(normalizar(e["respuesta"]).startswith(x) for x in errores):
            continue
        # si el mismo chat mando lo mismo en el mismo segundo es un repetido
        firma = (e["chat_id"], e["fecha"], e["texto"])
        if firma in vistos:
            continue
        vistos.add(firma)
        limpios.append(e)
    return limpios


# paso 2 puntaje de relevancia con el catalogo del cubo


def puntaje_relevancia(texto, tipo):
    if tipo in ["reporte", "documento"]:
        return umbral
    t = normalizar(texto)
    puntos = 0
    catalogo = (
        VALID_CHANNELS + VALID_PRODUCTS + VALID_SCORE_TAGS + VALID_AGE_TAGS + VALID_STRATEGIES
    )
    puntos += sum(1 for v in catalogo if normalizar(v) in t)
    puntos += sum(1 for m in meses if m in t)
    puntos += len(re.findall(r"\b20\d{4}\b", t))
    puntos += sum(1 for p in palabras_clave if p in t)
    return puntos


def entidades(texto):
    # sacamos los temas del cubo que menciona el mensaje para saber si sigue el mismo tema
    t = normalizar(texto)
    catalogo = (
        VALID_CHANNELS + VALID_PRODUCTS + VALID_SCORE_TAGS + VALID_AGE_TAGS + VALID_STRATEGIES
    )
    temas = {normalizar(v) for v in catalogo if normalizar(v) in t}
    temas |= {m for m in meses if m in t}
    temas |= set(re.findall(r"\b20\d{4}\b", t))
    return temas


# paso 3 naive bayes con tf-idf


def etiqueta(e):
    # si el usuario hizo algo con la respuesta el mensaje fue util aunque tenga pocos puntos
    if e.get("recompensa", 0) > 0:
        return 1
    return 1 if puntaje_relevancia(e["texto"], e["tipo"]) >= umbral else 0


def entrenar(eventos):
    global modelo
    eventos = limpiar_eventos(eventos)
    textos = [normalizar(e["texto"]) for e in eventos]
    y = [etiqueta(e) for e in eventos]
    # sin suficientes ejemplos de las dos clases nos quedamos con el puntaje
    if len(textos) < minimo_entrenar or len(set(y)) < 2:
        print("todavia no hay datos para entrenar, se usa el puntaje", len(textos))
        return None
    tfidf = TfidfVectorizer()
    x = tfidf.fit_transform(textos)
    nb = MultinomialNB()
    nb.fit(x, y)
    modelo = (tfidf, nb)
    joblib.dump(modelo, ruta_modelo)
    print("clasificador entrenado con", len(textos), "eventos")
    return modelo


def cargar_modelo():
    global modelo
    if modelo is None and ruta_modelo.exists():
        modelo = joblib.load(ruta_modelo)
    return modelo


def es_util(texto, tipo):
    if tipo in ["reporte", "documento"]:
        return True
    m = cargar_modelo()
    if m is None:
        return puntaje_relevancia(texto, tipo) >= umbral
    tfidf, nb = m
    probabilidad = nb.predict_proba(tfidf.transform([normalizar(texto)]))[0][1]
    return probabilidad >= 0.5


# paso 4 juntamos todo, lo que sale de aqui es lo que aprende el epsilon greedy


def filtrar(eventos):
    return [e for e in limpiar_eventos(eventos) if es_util(e["texto"], e["tipo"])]


def guardar_utiles(eventos):
    # guardamos aparte solo lo que paso el filtro para tener el conjunto limpio
    utiles = filtrar(eventos)
    MEMORIA_UTIL_DIR.mkdir(parents=True, exist_ok=True)
    ruta = MEMORIA_UTIL_DIR / "eventos_utiles.json"
    ruta.write_text(json.dumps(utiles, ensure_ascii=False, indent=2), encoding="utf-8")
    return utiles
