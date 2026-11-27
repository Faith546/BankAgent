import json
import math
import random
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from src.config import STATE_DIR
from src.skills.recuerdame import clasificador

ruta_eventos = STATE_DIR / "eventos.json"
ruta_politica = Path(__file__).resolve().parent / "politica.json"
alpha = 0.1

# cada accion es cuantos caracteres del historial del chat le mandamos al modelo
acciones = {"historial_corto": 2000, "historial_medio": 4000, "historial_largo": 6000}
sin_respuesta = "el agente no alcanzo a escribir la respuesta"


def leer_json(ruta, vacio):
    if not ruta.exists():
        return vacio
    return json.loads(ruta.read_text(encoding="utf-8"))


def escribir_json(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # escribimos primero en un temporal y luego lo cambiamos, asi nunca se lee un archivo a medias
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(ruta)


# paso 1 registramos lo que pasa en el chat y sacamos recompensas automaticas

def recompensa_automatica(respuesta):
    r = clasificador.normalizar(respuesta)
    # si no hubo respuesta pudo ser por mandarle demasiado historial
    if r.startswith(sin_respuesta):
        return -1
    # si el guardrail aviso es que hubo cifras que no se pudieron comprobar
    if "aviso guardrail" in r:
        return -0.5
    return 0


def registrar_evento(chat_id, texto, tipo, respuesta, accion):
    eventos = leer_json(ruta_eventos, [])
    anteriores = [e for e in eventos if e["chat_id"] == chat_id]
    if anteriores:
        ultimo = anteriores[-1]
        parecido = SequenceMatcher(None, clasificador.normalizar(ultimo["texto"]), clasificador.normalizar(texto)).ratio()
        # si repite casi la misma pregunta es que la respuesta anterior no le sirvio
        if parecido > 0.8:
            ultimo["recompensa"] = -1
        # si sigue preguntando del mismo tema la respuesta anterior si le sirvio
        elif ultimo["recompensa"] == 0 and clasificador.entidades(ultimo["texto"]) & clasificador.entidades(texto):
            ultimo["recompensa"] = 0.5
    eventos.append({
        "chat_id": chat_id,
        "fecha": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "texto": texto,
        "tipo": tipo,
        "respuesta": respuesta,
        "accion": accion,
        "recompensa": recompensa_automatica(respuesta),
    })
    escribir_json(ruta_eventos, eventos)


def dar_recompensa(chat_id, recompensa):
    # la recompensa va al ultimo evento del chat (descargo, pulgar arriba o abajo)
    eventos = leer_json(ruta_eventos, [])
    for e in reversed(eventos):
        if e["chat_id"] == chat_id:
            e["recompensa"] = recompensa
            break
    escribir_json(ruta_eventos, eventos)


# paso 2 policy learning con gradient bandit

def softmax(preferencias):
    # pi(a) = e^H(a) / suma de e^H(b)
    maximo = max(preferencias.values())
    exps = {a: math.exp(h - maximo) for a, h in preferencias.items()}
    total = sum(exps.values())
    return {a: e / total for a, e in exps.items()}


def elegir_accion(tipo):
    politica = leer_json(ruta_politica, {})
    preferencias = politica.get(tipo, {}).get("H", {a: 0.0 for a in acciones})
    # sorteamos la accion con las probabilidades de la politica, asi explora solo sin epsilon
    pi = softmax(preferencias)
    return random.choices(list(pi), weights=list(pi.values()))[0]


def actualizar_politica(utiles):
    # recalculamos desde cero con los eventos limpios para no contar dos veces el mismo
    politica = {}
    for e in utiles:
        if e.get("accion") not in acciones:
            continue
        tabla = politica.setdefault(e["tipo"], {"H": {a: 0.0 for a in acciones}, "promedio": 0.0, "n": 0})
        r = e["recompensa"]
        pi = softmax(tabla["H"])
        for a in acciones:
            # la accion usada sube si r fue mejor que el promedio y las demas bajan
            if a == e["accion"]:
                tabla["H"][a] += alpha * (r - tabla["promedio"]) * (1 - pi[a])
            else:
                tabla["H"][a] -= alpha * (r - tabla["promedio"]) * pi[a]
        # el promedio de recompensas es la linea base R barra
        tabla["n"] += 1
        tabla["promedio"] += (r - tabla["promedio"]) / tabla["n"]
    for tabla in politica.values():
        tabla["probabilidades"] = softmax(tabla["H"])
    escribir_json(ruta_politica, politica)
    return politica


# paso 3 endpoint de limpieza, limpia y aprende de un jalon

def limpieza():
    eventos = leer_json(ruta_eventos, [])
    utiles = clasificador.guardar_utiles(eventos)
    clasificador.entrenar(eventos)
    politica = actualizar_politica(utiles)
    print("limpieza", len(eventos), "eventos,", len(utiles), "utiles")
    return {"eventos": len(eventos), "utiles": len(utiles), "politica": politica}


def borrar_eventos_chat(chat_id):
    # cuando se borra un chat tambien se van sus eventos
    eventos = [e for e in leer_json(ruta_eventos, []) if e["chat_id"] != chat_id]
    escribir_json(ruta_eventos, eventos)