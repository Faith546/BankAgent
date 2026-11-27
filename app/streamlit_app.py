"""Consola Híbrida Ejecutiva en Streamlit — Asistente de Portafolio Banamex (MVP).

Sigue las mejores prácticas de diseño y tematización de Streamlit:
- Tema corporativo nativo en `.streamlit/config.toml` (light/dark + sidebar navy).
- Jerarquía visual con `st.sidebar`, tarjetas `st.container(border=True)`,
  `st.metric(..., border=True)`, `st.badge`, `st.tabs`, `st.pills` e íconos Material.
"""

from __future__ import annotations

import base64
import json
import numbers
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.graph import build_agent_graph, make_initial_state  # noqa: E402
from src.config import (  # noqa: E402
    DUCKDB_PATH,
    HISTORIAL_CHARS,
    MAX_NCL_RATE_PCT,
    MAX_OVER30_RATE_PCT,
    MIN_MATURE_MOB,
    OLLAMA_MODEL,
    OLLAMA_MODELOS,
    OLLAMA_NUM_CTX,
    OLLAMA_REASONING,
    VALID_CHANNELS,
)
from src.skills.cubo_sql_tools import obtener_resumen_portafolio  # noqa: E402
from src.skills.git_governance import (  # noqa: E402
    commit_ai_draft,
    commit_human_approval,
    get_case_diff,
    save_case_artifacts,
)
from src.skills.interpretacion import politicas, ragDynamico  # noqa: E402
from src.skills.interpretacion.analisis import (  # noqa: E402
    analizar_datos_grafica,
    leer_documento,
    leer_intencion,
    responder_con_documentos,
    responder_conversacion,
)
from src.skills.interpretacion.dominio import aviso_fuera, es_del_dominio  # noqa: E402
from src.skills.recuerdame import aprendizaje  # noqa: E402
from src.skills.recuerdame import chats as memoria  # noqa: E402
from src.skills.report_tools import compilar_entregables_ejecutivos  # noqa: E402
from src.skills.reporte.generar import editar_reporte, grafica_chat  # noqa: E402
from src.skills.reporte.generar import generar as generar_reporte  # noqa: E402
from src.skills.viz_tools import (  # noqa: E402
    ChartType,
    build_plotly_figure,
    generar_grafica_portafolio,
)

# editor del reporte, un componente propio que deja escribir directo en la vista previa
_editor_reporte = components.declare_component(
    "editor_reporte", path=str(PROJECT_ROOT / "src" / "skills" / "reporte" / "editor")
)

CHART_LABELS: dict[ChartType, str] = {
    "curva_maduracion_s": "Curva S (Maduración)",
    "curva_j_roa": "Curva J (ROA Neto)",
    "puente_pnl_waterfall": "Puente P&L",
    "heatmap_severidad": "Heatmap Severidad",
    "matriz_cuadrantes": "Matriz Cuadrantes",
    "embudo_cobranza": "Embudo Cobranza",
}

QUICK_PROMPTS: list[str] = [
    "¿Qué canal tiene peor pérdida neta en MOB >= 6?",
    "Compara Aeropuerto vs Branch en MOB >= 6",
    "¿Cuál es la política de recuperación de cobranza?",
]


@st.cache_data(ttl=300)
def load_parametric_alerts(
    channel_filter: str | None = None, limit: int = 25
) -> list[dict[str, Any]]:
    """Consulta segmentos maduros (MOB >= 6) que exceden umbrales de apetito de riesgo."""
    if not DUCKDB_PATH.exists():
        return []

    where_extra = "AND CHANNEL = ?" if channel_filter and channel_filter != "Todos" else ""
    params: list[Any] = [channel_filter, limit] if where_extra else [limit]

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT
                CHANNEL,
                AGE_TAG,
                SCORE_TAG,
                COUNT(DISTINCT COHORT_ID) AS cohortes,
                ROUND((SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0, 2) AS ncl_rate_pct,
                ROUND((SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0, 2) AS over30_rate_pct,
                ROUND(SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL), 2) AS utilidad_neta,
                ROUND(SUM(ENRAMTS), 2) AS enr_total
            FROM v_cubo_metricas
            WHERE MOB >= {MIN_MATURE_MOB} {where_extra}
            GROUP BY CHANNEL, AGE_TAG, SCORE_TAG
            HAVING (SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 > {MAX_NCL_RATE_PCT}
                OR (SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0)) * 100.0 > {MAX_OVER30_RATE_PCT}
            ORDER BY ncl_rate_pct DESC, enr_total DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    finally:
        con.close()

    return [
        {
            "case_id": f"CASO-2026-{idx:04d}",
            "channel": r[0],
            "age_tag": r[1],
            "score_tag": r[2],
            "cohortes": r[3],
            "ncl_rate_pct": r[4],
            "over30_rate_pct": r[5],
            "utilidad_neta": r[6],
            "enr_total": r[7],
        }
        for idx, r in enumerate(rows, start=1)
    ]


def _init_session_state() -> None:
    defaults: dict[str, Any] = {
        "selected_case_key": "",
        "draft_dictamen": "",
        "sql_queries": [],
        "evidence": [],
        "guardrail_issues": [],
        "chat_history": [],
        "last_outputs": {},
        "git_diff_text": "",
        "token_usage": {},
        "last_quick_prompt": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # cada vez que se entra a la app se abre un chat nuevo, si el mas reciente quedo vacio se reusa
    if "chat_activo" not in st.session_state:
        guardados = memoria.listar_chats()
        if guardados and not guardados[0]["mensajes"]:
            st.session_state["chat_activo"] = guardados[0]
        else:
            st.session_state["chat_activo"] = memoria.crear_chat()
    # el historial que se muestra es el mismo que se guarda en el json del chat
    st.session_state["chat_history"] = st.session_state["chat_activo"]["mensajes"]


def _reset_case_state(case_key: str) -> None:
    st.session_state["selected_case_key"] = case_key
    st.session_state["draft_dictamen"] = ""
    st.session_state["sql_queries"] = []
    st.session_state["evidence"] = []
    st.session_state["guardrail_issues"] = []
    st.session_state["git_diff_text"] = ""
    st.session_state["last_outputs"] = {}


def _run_agent_for_case(case: dict[str, Any]) -> None:
    prompt = (
        f"Analiza el segmento CHANNEL='{case['channel']}', AGE_TAG='{case['age_tag']}', "
        f"SCORE_TAG='{case['score_tag']}'. Obtén su resumen de portafolio, revisa su curva de "
        "maduración, consulta el manual de apetito de riesgo y redacta un dictamen ejecutivo "
        "con recomendación concreta (Expandir, Restringir Línea o Suspender Originación)."
    )
    graph = build_agent_graph(with_interrupt=True)
    config = {"configurable": {"thread_id": f"case-{case['case_id']}"}}
    result = graph.invoke(
        make_initial_state(prompt=prompt, case_id=case["case_id"]), config=config
    )

    draft = result.get("draft_dictamen", "")
    queries = result.get("sql_queries", [])
    evidence = result.get("evidence", [])
    issues = result.get("guardrail_issues", [])

    st.session_state["draft_dictamen"] = draft
    st.session_state["sql_queries"] = queries
    st.session_state["evidence"] = evidence
    st.session_state["guardrail_issues"] = issues
    st.session_state["token_usage"] = result.get("token_usage", {})

    parsed_ev = []
    for item in evidence:
        try:
            parsed_ev.append(json.loads(item) if isinstance(item, str) else item)
        except json.JSONDecodeError:
            parsed_ev.append({"raw": str(item)})

    save_case_artifacts(case["case_id"], queries, parsed_ev, draft)
    try:
        commit_ai_draft(case["case_id"], OLLAMA_MODEL)
    except Exception as exc:  # noqa: BLE001
        st.toast(f"Borrador guardado (sin commit Git automático): {exc}", icon=":material/info:")


@st.cache_resource
def _candado_limpieza() -> threading.Lock:
    # un solo candado para toda la app, asi nunca corren dos limpiezas al mismo tiempo
    return threading.Lock()


def _limpiar_en_fondo(candado: threading.Lock) -> None:
    # corre en otro hilo para que el usuario no espere, si falla no afecta al chat
    if not candado.acquire(blocking=False):
        return
    try:
        aprendizaje.limpieza()
    except Exception as exc:  # noqa: BLE001
        print("no se pudo hacer la limpieza en segundo plano", exc)
    finally:
        candado.release()


def _separar_tablas(texto: str) -> tuple[str, list[str]]:
    # Extraemos tablas en markdown de la respuesta para la pestaña de resultados
    resto: list[str] = []
    tablas: list[str] = []
    actual: list[str] = []
    for linea in texto.split("\n") + [""]:
        if linea.strip().startswith("|"):
            actual.append(linea)
            continue
        es_tabla = len(actual) >= 2 and any(re.match(r"^\s*\|?\s*:?-{3,}", x) for x in actual)
        if es_tabla:
            tablas.append("\n".join(actual))
        else:
            resto.extend(actual)
        actual = []
        resto.append(linea)
    return "\n".join(resto[:-1]).strip(), tablas


def _agregar_resultado(chat: dict[str, Any], resultado: dict[str, Any], aviso: str) -> None:
    # lo que genera el agente se guarda en el chat y se muestra en la pestaña de resultados
    resultado["fecha"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    chat.setdefault("resultados", []).append(resultado)
    st.session_state["aviso_resultados"] = aviso


def _comprimir_en_fondo(chat_id: str) -> None:
    # resume lo viejo del chat en otro hilo para que el usuario no espere
    try:
        memoria.comprimir_chat(chat_id)
    except Exception as exc:  # noqa: BLE001
        print("no se pudo comprimir el chat", exc)


def _decodificar(valores):
    # Plotly guarda numeros en binario dentro del JSON (dtype/bdata); los pasamos a lista
    if isinstance(valores, dict) and "bdata" in valores:
        arreglo = np.frombuffer(
            base64.b64decode(valores["bdata"]), dtype=np.dtype(valores["dtype"])
        )
        if "shape" in valores:
            arreglo = arreglo.reshape([int(n) for n in str(valores["shape"]).split(",")])
        return arreglo.tolist()
    return valores


def _resumir_figura(fig) -> str:
    # pasamos la grafica a texto con sus datos, asi el agente la analiza sin tomarle captura
    def limpiar(valores):
        lista = list(valores) if valores is not None else []
        # si trae muchos puntos tomamos 40 repartidos para no gastar tokens
        if len(lista) > 40:
            paso = len(lista) / 40
            lista = [lista[int(i * paso)] for i in range(40)]
        limpios = []
        for v in lista:
            # Convertimos numeros de numpy a Python nativo para evitar np.float64(...)
            if isinstance(v, numbers.Real) and not isinstance(v, bool):
                v = float(v)
                v = int(v) if v.is_integer() else round(v, 2)
            limpios.append(v)
        return limpios

    titulo = fig.layout.title.text if fig.layout.title and fig.layout.title.text else ""
    lineas = [f"Título  {titulo}"] if titulo else []
    for traza in fig.data:
        nombre = getattr(traza, "name", None) or traza.type
        x = _decodificar(getattr(traza, "x", None))
        y = _decodificar(getattr(traza, "y", None))
        z = _decodificar(getattr(traza, "z", None))
        if z is not None:
            filas = [limpiar(f) for f in z]
            lineas.append(
                f"Serie {nombre} (mapa de calor)  columnas {limpiar(x)}  "
                f"filas {limpiar(y)}  valores {filas}"
            )
        else:
            lineas.append(f"Serie {nombre}  x {limpiar(x)}  y {limpiar(y)}")
            lineas.extend(_hechos_serie(nombre, x, y))
    return "\n".join(lineas)


def _hechos_serie(nombre, xs, ys) -> list[str]:
    # Calculamos maximo, minimo y cruces con limite para que el modelo no los estime
    try:
        puntos = [
            (x, float(y))
            for x, y in zip(list(xs), list(ys))
            if y is not None and not isinstance(y, str)
        ]
    except (TypeError, ValueError):
        return []
    if len(puntos) < 2:
        return []

    def bonito(v):
        v = float(v) if isinstance(v, numbers.Real) else v
        return (int(v) if v.is_integer() else round(v, 2)) if isinstance(v, float) else v

    x_max, y_max = max(puntos, key=lambda p: p[1])
    x_min, y_min = min(puntos, key=lambda p: p[1])
    x_ult, y_ult = puntos[-1]
    hechos = [
        f"Hechos de {nombre}  máximo {bonito(y_max)} en {bonito(x_max)}, "
        f"mínimo {bonito(y_min)} en {bonito(x_min)}, "
        f"último valor {bonito(y_ult)} en {bonito(x_ult)}"
    ]
    n = str(nombre).lower()
    limite = (
        MAX_OVER30_RATE_PCT
        if "over30" in n or "morosidad" in n
        else (MAX_NCL_RATE_PCT if "ncl" in n or "pérdida" in n or "perdida" in n else None)
    )
    if limite is not None:
        arriba = [x for x, y in puntos if y > limite]
        if arriba:
            hechos.append(
                f"Límite de {nombre} {bonito(limite)}%  la serie está ARRIBA del límite "
                f"desde {bonito(arriba[0])}, "
                f"en {len(arriba)} de {len(puntos)} puntos, y su máximo queda "
                f"{bonito(round(y_max - limite, 2))} puntos arriba del límite"
            )
        else:
            hechos.append(
                f"Límite de {nombre} {bonito(limite)}%  la serie nunca pasa el límite, "
                "su máximo queda "
                f"{bonito(round(limite - y_max, 2))} puntos debajo"
            )
    return hechos


def _grafica_en_pantalla(chat) -> dict[str, Any] | None:
    # En Resultados es la ultima grafica pedida; en las demas pestañas la de graficas financieras
    if st.session_state.get("pestana_activa") != PESTANA_RESULTADOS:
        return st.session_state.get("grafica_actual")
    graficas = [r for r in chat.get("resultados", []) if r["tipo"] == "grafica"]
    if not graficas:
        return None
    ultima = graficas[-1]
    figuras = [pio.from_json(f) for f in ultima["figuras"]]
    return {
        "titulo": " y ".join(f.layout.title.text or "sin título" for f in figuras),
        "datos": "\n".join(_resumir_figura(f) for f in figuras),
        "segmento": f"lo que pidió el usuario, {ultima['titulo']}",
    }


def _send_copilot_message(user_q: str, case_id: str, archivo=None, datos_grafica=None) -> None:
    # limpiamos y aprendemos en segundo plano con la primera pregunta y luego cada 6
    st.session_state["preguntas_sesion"] = st.session_state.get("preguntas_sesion", 0) + 1
    if st.session_state["preguntas_sesion"] % 6 == 1:
        threading.Thread(
            target=_limpiar_en_fondo, args=(_candado_limpieza(),), daemon=True
        ).start()

    chat = st.session_state["chat_activo"]
    anteriores = [m[1] for m in chat["mensajes"] if m[0] == "user"]

    # El modelo seleccionado clasifica el destino y la opinion sobre la respuesta anterior
    modelo = OLLAMA_MODELOS[st.session_state.get("modelo_elegido") or "Normal"]
    respuestas = [m[1] for m in chat["mensajes"] if m[0] == "assistant"]
    intencion = leer_intencion(user_q, respuestas[-1] if respuestas else "", modelo)

    # si pregunta por la grafica que tiene en pantalla usamos la de la pestaña que esta viendo
    if archivo is None and datos_grafica is None and intencion.destino == "grafica_en_pantalla":
        datos_grafica = _grafica_en_pantalla(chat)

    # vemos que tipo de pregunta es para saber a donde mandarla
    if archivo is not None:
        tipo = "documento"
    elif datos_grafica is not None:
        tipo = "grafica_panel"
    elif intencion.destino in ("reporte", "grafica", "conversacion"):
        tipo = intencion.destino
    else:
        tipo = "agente"
    # la politica escoge el estilo de respuesta en las preguntas al agente, el historial va fijo
    accion = aprendizaje.elegir_accion(tipo) if tipo == "agente" else None
    # Si el usuario pidio un estilo explicito lo aplicamos tambien en documentos y graficas
    # y esa respuesta no cuenta para aprender porque no la escogio la politica
    forzado = (
        tipo in ("agente", "documento", "grafica_panel")
        and intencion.opinion in aprendizaje.pedido_a_estilo
    )
    if forzado:
        accion = aprendizaje.pedido_a_estilo[intencion.opinion]
    # si no hay estilo, documentos y graficas usan su formato de siempre
    estilo = aprendizaje.acciones.get(accion, "")
    historial = memoria.ultimos_mensajes(chat, limite=HISTORIAL_CHARS)

    chat["mensajes"].append(["user", user_q])
    # con la primera pregunta el agente le pone nombre clave al chat
    if len(chat["mensajes"]) == 1:
        chat = memoria.nombrar_chat(chat)
        st.session_state["chat_activo"] = chat

    ruta = ""
    figuras = []
    # si el usuario mando un archivo lo guardamos en el rag del chat y respondemos con sus pedazos
    if tipo == "documento":
        try:
            texto = leer_documento(archivo.getvalue(), archivo.name)
            # filtro de dominio, si el archivo no es de banca no se analiza ni se guarda en el rag
            if not es_del_dominio(texto):
                answer = aviso_fuera
            else:
                ragDynamico.guardar_documento(chat["id"], archivo.name, texto)
                chat["documento"] = {"nombre": archivo.name}
                fragmentos = ragDynamico.buscar(chat["id"], user_q)
                answer = responder_con_documentos(user_q, fragmentos, historial, modelo, estilo)
        except Exception as exc:  # noqa: BLE001
            answer = f"No se pudo leer el documento. {exc}"

    elif tipo == "grafica_panel":
        # la grafica de graficas financieras se analiza con sus datos, sin vision
        try:
            answer = analizar_datos_grafica(
                datos_grafica["titulo"],
                datos_grafica["datos"],
                datos_grafica["segmento"],
                historial,
                modelo,
                estilo,
            )
        except Exception as exc:  # noqa: BLE001
            answer = f"No se pudo analizar la gráfica. {exc}"

    elif tipo == "conversacion":
        # si solo comenta o agradece no consultamos el cubo, contestamos breve
        try:
            answer = responder_conversacion(user_q, historial, modelo)
        except Exception as exc:  # noqa: BLE001
            answer = f"No se pudo contestar. {exc}"

    elif tipo == "reporte":
        pregunta = user_q
        if len(user_q.split()) <= 6 and anteriores:
            pregunta = anteriores[-1]
        try:
            ruta = generar_reporte(pregunta)
            if not ruta or not Path(str(ruta)).exists():
                hechos = sorted(
                    (PROJECT_ROOT / "outputs" / "reportes").glob("*.docx"),
                    key=lambda x: x.stat().st_mtime,
                )
                ruta = hechos[-1] if hechos else ""
            ruta_html = Path(str(ruta)).with_suffix(".html") if ruta else None
            _agregar_resultado(
                chat,
                {
                    "tipo": "reporte",
                    "titulo": pregunta,
                    "docx": str(ruta),
                    "html": str(ruta_html or ""),
                },
                "Tu reporte está listo en la pestaña Resultados",
            )
            answer = (
                f"Listo, el reporte de {pregunta} está en la pestaña Resultados "
                "para revisarlo y descargarlo."
            )
            # el boton de descarga ya no va en el chat sino en resultados
            ruta = ""
        except Exception as exc:  # noqa: BLE001
            answer = f"No se pudo generar el reporte. {exc}"

    elif tipo == "grafica":
        # Armamos la grafica con la misma logica del reporte y la enviamos a Resultados
        try:
            res_grafica = grafica_chat(user_q)
            _agregar_resultado(
                chat,
                {
                    "tipo": "grafica",
                    "titulo": user_q,
                    "texto": res_grafica["texto"],
                    "figuras": res_grafica["figuras"],
                    "tabla": res_grafica["tabla"],
                },
                "Tu gráfica está lista en la pestaña Resultados",
            )
            answer = (
                res_grafica["texto"] or "Listo."
            ) + "\n\nLa gráfica y la tabla están en la pestaña Resultados."
        except Exception as exc:  # noqa: BLE001
            answer = f"No se pudo generar la gráfica. {exc}"

    else:
        # Pasamos la conversacion y fragmentos de documentos del chat para mantener el hilo
        fragmentos = ""
        if chat.get("documento"):
            try:
                fragmentos = ragDynamico.buscar(chat["id"], user_q)
            except Exception as exc:  # noqa: BLE001
                print("no se pudo buscar en el rag", exc)
        # le pegamos a la pregunta el estilo que escogio la politica
        prompt_agente = f"{user_q}\n\n{aprendizaje.acciones[accion]}"
        if historial or fragmentos:
            # el historial solo sirve para entender referencias, no para limitar la pregunta nueva
            prompt_agente = (
                "Conversación previa, úsala solo para referencias como esas cifras o y Branch. "
                "Si la pregunta actual se entiende sola, respóndela completa "
                "sin limitarte a lo anterior.\n"
                f"{historial}\n\n"
            )
            if fragmentos:
                prompt_agente += f"Fragmentos de documentos del chat\n{fragmentos}\n\n"
            prompt_agente += f"Pregunta actual  {user_q}\n\n{aprendizaje.acciones[accion]}"
        try:
            chat_graph = build_agent_graph(with_interrupt=False)
            # cada pregunta va en su propio hilo porque el historial ya se lo pasamos nosotros,
            # si se usa el mismo hilo langgraph acumula todos los mensajes y se llena el contexto
            res = chat_graph.invoke(
                make_initial_state(prompt=prompt_agente, case_id=case_id, modelo=modelo),
                config={
                    "configurable": {"thread_id": f"copilot-{chat['id']}-{len(chat['mensajes'])}"}
                },
            )
            st.session_state["token_usage"] = res.get("token_usage", {})
            # guardamos las consultas del chat para verlas en la pestaña de auditoria
            st.session_state["sql_queries"] = res.get("sql_queries", [])
            answer = res.get("draft_dictamen", "")
            # si el agente termino sin escribir nada lo decimos en lugar de dejar el mensaje vacio
            if not answer.strip():
                answer = (
                    "El agente no alcanzó a escribir la respuesta, "
                    "intenta preguntarlo de otra forma."
                )
            # Si respondio con tablas las pasamos a Resultados y en chat queda la explicacion
            answer, tablas = _separar_tablas(answer)
            if tablas:
                _agregar_resultado(
                    chat,
                    {"tipo": "tabla", "titulo": user_q, "tablas": tablas},
                    "La tabla está en la pestaña Resultados",
                )
                answer += "\n\nLa tabla está en la pestaña Resultados."
            if not res.get("guardrail_passed", True):
                answer += (
                    "\n\n> :material/warning: *Aviso guardrail:* Algunas cifras no coincidieron "
                    f"exactamente con JSON: {', '.join(res.get('guardrail_issues', []))}"
                )
        except Exception as exc:  # noqa: BLE001
            answer = (
                f"Error al conectar con Ollama (`{OLLAMA_MODEL}`): `{exc}`. "
                "Verifica que Ollama esté corriendo en `http://localhost:11434`."
            )

    # guardamos la respuesta en el json del chat y el evento para que el agente aprenda
    # el tercer lugar es la ruta del word y el cuarto las graficas en json para volver a dibujarlas
    mensaje = ["assistant", answer]
    if ruta or figuras:
        mensaje += [str(ruta), figuras]
    chat["mensajes"].append(mensaje)
    memoria.guardar_chat(chat)
    aprendizaje.registrar_evento(
        chat["id"], user_q, tipo, answer, None if forzado else accion, intencion.opinion
    )
    # si la conversacion ya crecio se comprime en segundo plano
    threading.Thread(target=_comprimir_en_fondo, args=(chat["id"],), daemon=True).start()


def _guardar_pulgar(chat_id: str, key: str) -> None:
    # el pulgar arriba suma y el pulgar abajo resta en el ultimo evento del chat
    valor = st.session_state.get(key)
    if valor is not None:
        aprendizaje.dar_recompensa(chat_id, 1 if valor == 1 else -1)


def _render_chats() -> None:
    st.markdown("#### :material/chat: Conversaciones")
    chat = st.session_state["chat_activo"]
    # los chats que se quedaron vacios no se muestran, salvo el que esta abierto
    guardados = [c for c in memoria.listar_chats() if c["mensajes"]]
    titulos = {c["id"]: c["titulo"] for c in guardados}
    titulos[chat["id"]] = chat["titulo"]
    ids = list(titulos)
    elegido = st.selectbox(
        "Conversaciones",
        options=ids,
        index=ids.index(chat["id"]),
        format_func=lambda i: titulos[i],
        label_visibility="collapsed",
    )
    if elegido != chat["id"]:
        st.session_state["chat_activo"] = memoria.cargar_chat(elegido)
        st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Nuevo", icon=":material/add_comment:", use_container_width=True):
            # si el chat actual sigue vacio no creamos otro
            if chat["mensajes"]:
                st.session_state["chat_activo"] = memoria.crear_chat()
            st.rerun()
    with c2:
        if st.button("Borrar", icon=":material/delete:", use_container_width=True):
            # borramos el json, los eventos y los pedazos del rag de este chat
            memoria.borrar_chat(chat["id"])
            aprendizaje.borrar_eventos_chat(chat["id"])
            try:
                ragDynamico.borrar_documentos_chat(chat["id"])
            except Exception as exc:  # noqa: BLE001
                print("no se pudo borrar del rag", exc)
            restantes = memoria.listar_chats()
            st.session_state["chat_activo"] = restantes[0] if restantes else memoria.crear_chat()
            st.rerun()


def _render_sidebar() -> dict[str, Any] | None:
    with st.sidebar:
        st.markdown("### :material/account_balance: Banamex Risk Agent")
        st.caption("Consola Local de Portafolio de Tarjetas")
        st.divider()

        channel_filter = st.selectbox(
            "Filtrar alertas por canal",
            options=["Todos", *VALID_CHANNELS],
            index=0,
        )
        alerts = load_parametric_alerts(channel_filter=channel_filter)

        st.markdown(f"#### :material/warning: Alertas Activas ({len(alerts)})")
        st.caption(
            f"Cohortes MOB ≥ {MIN_MATURE_MOB} | "
            f"NCL > {MAX_NCL_RATE_PCT}% u Over30 > {MAX_OVER30_RATE_PCT}%"
        )

        if not alerts:
            st.info("Sin segmentos fuera de umbral para este canal.")
            return None

        labels = [
            f"{a['case_id']} · {a['channel']} · {a['score_tag']} ({a['ncl_rate_pct']}%)"
            for a in alerts
        ]
        selected_idx = st.radio(
            "Cola de investigación",
            options=range(len(alerts)),
            format_func=lambda i: labels[i],
            label_visibility="collapsed",
        )
        case = alerts[selected_idx]
        case_key = f"{case['channel']}|{case['age_tag']}|{case['score_tag']}"
        if st.session_state["selected_case_key"] != case_key:
            _reset_case_state(case_key)

        st.divider()
        with st.container(border=True):
            st.markdown(f"**{case['case_id']}**")
            st.caption(
                f"Canal: **{case['channel']}**  \n"
                f"Edad: **{case['age_tag']}**  \n"
                f"Score: **{case['score_tag']}**  \n"
                f"Cohortes: **{case['cohortes']}**"
            )

        st.divider()
        # mostramos como va aprendiendo la politica el estilo que le gusta al usuario
        with st.container(border=True):
            st.markdown("**:material/psychology: Lo que el agente ha aprendido de ti**")
            tabla_estilos = aprendizaje.leer_json(aprendizaje.ruta_politica, {}).get("agente", {})
            probabilidades = tabla_estilos.get("probabilidades", {})
            if set(probabilidades) != set(aprendizaje.acciones):
                probabilidades = aprendizaje.softmax({a: 0.0 for a in aprendizaje.acciones})
            nombres_estilos = {
                "corta": "Respuesta corta",
                "detallada": "Respuesta detallada",
                "con_tabla": "Con tabla",
            }
            for estilo, probabilidad in probabilidades.items():
                st.progress(probabilidad, text=f"{nombres_estilos[estilo]} {probabilidad:.0%}")
            st.caption(
                f"Aprendido de {tabla_estilos.get('n', 0)} respuestas "
                "(se actualiza cada 6 preguntas)."
            )

        st.divider()
        think_tag = "ON" if OLLAMA_REASONING else "OFF"
        st.caption(
            f":material/memory: `{OLLAMA_MODEL}` · think `{think_tag}` · ctx `{OLLAMA_NUM_CTX:,}`"
        )
        return case


# nombres de las pestañas, los usamos para pintarlas y para saber cual esta abierta
PESTANA_RESULTADOS = ":material/inventory_2: Resultados"
PESTANAS = [
    ":material/monitoring: Gráficas Financieras",
    ":material/edit_document: Dictamen & Human-in-the-Loop",
    ":material/database: Auditoría SQL & Telemetría",
    PESTANA_RESULTADOS,
    ":material/policy: Políticas",
]


def main() -> None:
    st.set_page_config(
        page_title="Banamex Risk Agent — Consola Ejecutiva",
        page_icon=":material/account_balance:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_session_state()

    if not DUCKDB_PATH.exists():
        st.error(
            f"No se encontró la base DuckDB en `{DUCKDB_PATH}`. "
            "Ejecuta primero `uv run python -m src.data.init_db`."
        )
        return

    case = _render_sidebar()
    if case is None:
        return

    # ------------------------------------------------------------------
    # ENCABEZADO EJECUTIVO CON BADGES DE ESTADO
    # ------------------------------------------------------------------
    header_l, header_r = st.columns([3, 1.4], vertical_alignment="bottom")
    with header_l:
        st.markdown(
            f"## :material/analytics: {case['case_id']} — {case['channel']} · {case['score_tag']}"
        )
        st.caption(
            f"Segmento de edad `{case['age_tag']}` · "
            f"{case['cohortes']} cohortes monitoreadas en DuckDB"
        )
    with header_r:
        with st.container(horizontal=True, horizontal_alignment="right"):
            if case["ncl_rate_pct"] > MAX_NCL_RATE_PCT:
                st.badge("Fuera de Apetito", icon=":material/gpp_bad:", color="red")
            elif case["ncl_rate_pct"] >= 12.0:
                st.badge("Vigilancia", icon=":material/visibility:", color="orange")
            else:
                st.badge("En Apetito", icon=":material/verified_user:", color="green")
            st.badge(f"MOB ≥ {MIN_MATURE_MOB}", color="blue")

    # ------------------------------------------------------------------
    # TARJETAS KPI (BORDERED METRICS CON DELTAS VS. POLÍTICA)
    # ------------------------------------------------------------------
    resumen = json.loads(
        obtener_resumen_portafolio.invoke(
            {
                "channel": case["channel"],
                "age_tag": case["age_tag"],
                "score_tag": case["score_tag"],
            }
        )
    )
    ncl_val = float(resumen["ncl_rate_pct"] or 0.0)
    over30_val = float(resumen["over30_rate_pct"] or 0.0)
    roa_val = float(resumen["net_roa_pct"] or 0.0)

    k1, k2, k3, k4 = st.columns(4, gap="small")
    k1.metric(
        "Cuentas Iniciales (MOB 0)",
        f"{resumen['cuentas_iniciales_mob0']:,}",
        delta=f"Líneas: ${resumen['lineas_credito_iniciales_mob0'] / 1e6:,.1f}M",
        delta_color="off",
        border=True,
    )
    k2.metric(
        "Severidad NCL / ENR",
        f"{ncl_val:.2f}%",
        delta=f"{ncl_val - MAX_NCL_RATE_PCT:+.2f} pp vs límite {MAX_NCL_RATE_PCT}%",
        delta_color="inverse",
        border=True,
    )
    k3.metric(
        "Morosidad Over30 / ENR",
        f"{over30_val:.2f}%",
        delta=f"{over30_val - MAX_OVER30_RATE_PCT:+.2f} pp vs límite {MAX_OVER30_RATE_PCT}%",
        delta_color="inverse",
        border=True,
    )
    k4.metric(
        "Utilidad Neta Acumulada",
        f"${resumen['utilidad_neta'] / 1e6:,.2f}M",
        delta=f"ROA Neto: {roa_val:.2f}%",
        delta_color="normal" if roa_val >= 0 else "inverse",
        border=True,
    )

    st.divider()

    # ------------------------------------------------------------------
    # LIENZO PRINCIPAL (IZQ: EVIDENCIA Y DICTAMEN | DER: COPILOTO)
    # ------------------------------------------------------------------
    col_main, col_chat = st.columns([1.75, 1.0], gap="medium")

    with col_main:
        # La llave indica que pestaña esta abierta para contextualizar la grafica visible
        tab_viz, tab_dictamen, tab_audit, tab_resultados, tab_politicas = st.tabs(
            PESTANAS, key="pestana_activa", on_change="rerun"
        )

        # Aviso de nuevo contenido en Resultados (Streamlit no cambia de pestaña solo)
        aviso_resultados = st.session_state.pop("aviso_resultados", None)
        if aviso_resultados:
            st.toast(aviso_resultados, icon=":material/inventory_2:")

        filtros = {
            "channel": case["channel"],
            "age_tag": case["age_tag"],
            "score_tag": case["score_tag"],
        }

        with tab_viz:
            with st.container(border=True):
                chart_type: ChartType = (
                    st.pills(
                        "Selecciona visualización",
                        options=list(CHART_LABELS.keys()),
                        format_func=lambda k: CHART_LABELS[k],
                        default="curva_maduracion_s",
                        selection_mode="single",
                        label_visibility="collapsed",
                    )
                    or "curva_maduracion_s"
                )

                fig = build_plotly_figure(tipo_grafica=chart_type, filtros=filtros)
                st.plotly_chart(fig, use_container_width=True)
                # Guardamos la grafica actual para cuando el usuario pregunte por ella en chat
                st.session_state["grafica_actual"] = {
                    "titulo": CHART_LABELS[chart_type],
                    "datos": _resumir_figura(fig),
                    "segmento": (
                        f"canal {case['channel']}, edad {case['age_tag']}, "
                        f"score {case['score_tag']}"
                    ),
                }

                # el copiloto analiza la grafica con sus datos, no con una captura
                if st.button(
                    "Analizar esta gráfica con el Copiloto",
                    icon=":material/insights:",
                    key=f"analizar_grafica_{chart_type}",
                ):
                    with st.spinner("El Copiloto está analizando la gráfica..."):
                        _send_copilot_message(
                            f"Analiza la gráfica {CHART_LABELS[chart_type]}",
                            case["case_id"],
                            datos_grafica=st.session_state["grafica_actual"],
                        )
                    st.session_state["aviso_resultados"] = (
                        "El análisis de la gráfica está en el chat del Copiloto"
                    )
                    st.rerun()

            with st.expander(
                ":material/table_view: Resumen Contable del Segmento (DuckDB)", expanded=False
            ):
                summary_df = pd.DataFrame(
                    [
                        (
                            "Ingresos acumulados (REVENUE)",
                            f"${resumen['ingresos_acumulados']:,.2f}",
                        ),
                        ("Pérdida bruta (GCLAMTS)", f"${resumen['perdida_bruta_gcl']:,.2f}"),
                        (
                            "Recuperación cobranza (RECOVERYAMTS)",
                            f"${resumen['recuperacion_cobranza']:,.2f}",
                        ),
                        ("Eficiencia recuperación (%)", f"{resumen['recovery_rate_pct']}%"),
                        ("Pérdida neta (NCLAMTS)", f"${resumen['perdida_neta_ncl']:,.2f}"),
                        ("Gastos totales (EXPENSES_TOTAL)", f"${resumen['gastos_totales']:,.2f}"),
                        ("Utilidad neta (NET_PROFIT)", f"${resumen['utilidad_neta']:,.2f}"),
                    ],
                    columns=["Métrica", "Valor Verificado"],
                )
                st.dataframe(summary_df, use_container_width=True, hide_index=True)

        with tab_dictamen:
            with st.container(border=True):
                act_l, act_r = st.columns([2, 1], vertical_alignment="center")
                with act_l:
                    st.markdown("#### Borrador de Dictamen Ejecutivo")
                    st.caption(
                        "Pausa Human-in-the-Loop: revisa y edita antes de compilar DOCX/PPTX."
                    )
                with act_r:
                    if st.button(
                        "Analizar con IA",
                        icon=":material/smart_toy:",
                        type="primary",
                        use_container_width=True,
                    ):
                        with st.spinner(f"Consultando DuckDB, RAG y `{OLLAMA_MODEL}`..."):
                            try:
                                _run_agent_for_case(case)
                                st.toast(
                                    "Borrador IA listo para revisión.",
                                    icon=":material/check_circle:",
                                )
                            except Exception as exc:  # noqa: BLE001
                                st.error(
                                    f"Error al ejecutar Ollama/LangGraph: {exc}. "
                                    "Verifica que Ollama esté abierto en `http://localhost:11434`."
                                )

                if st.session_state["guardrail_issues"]:
                    st.warning(
                        "Guardrail detectó cifras no respaldadas en herramienta: "
                        + ", ".join(st.session_state["guardrail_issues"]),
                        icon=":material/warning:",
                    )

                default_draft = st.session_state["draft_dictamen"] or (
                    f"Segmento {case['channel']} | {case['age_tag']} | {case['score_tag']}.\n"
                    f"- Cuentas iniciales (MOB 0): {resumen['cuentas_iniciales_mob0']:,}\n"
                    f"- Pérdida Neta (NCL/ENR): {resumen['ncl_rate_pct']}%\n"
                    f"- Morosidad Over30 (Over30/ENR): {resumen['over30_rate_pct']}%\n"
                    f"- Utilidad Neta acumulada: ${resumen['utilidad_neta']:,.2f}\n\n"
                    "Dictamen preliminar: presiona 'Analizar con IA' o edita este texto."
                )
                edited_draft = st.text_area(
                    "Texto del dictamen",
                    value=default_draft,
                    height=220,
                    label_visibility="collapsed",
                )
                st.session_state["draft_dictamen"] = edited_draft

                b1, b2 = st.columns(2)
                with b1:
                    if st.button(
                        "Aprobar y Generar DOCX/PPTX + Git Commit",
                        icon=":material/verified:",
                        type="primary",
                        use_container_width=True,
                    ):
                        with st.spinner(
                            "Exportando PNG, compilando DOCX/PPTX y commiteando en Git..."
                        ):
                            viz_res = json.loads(
                                generar_grafica_portafolio.invoke(
                                    {
                                        "tipo_grafica": chart_type,
                                        "case_id": case["case_id"],
                                        "filtros": filtros,
                                        "export_png": True,
                                    }
                                )
                            )
                            estado_riesgo = (
                                "FUERA DE APETITO"
                                if ncl_val > MAX_NCL_RATE_PCT or over30_val > MAX_OVER30_RATE_PCT
                                else ("VIGILANCIA" if ncl_val >= 12.0 else "EN APETITO")
                            )
                            lineas_m = resumen["lineas_credito_iniciales_mob0"] / 1e6
                            util_m = resumen["utilidad_neta"] / 1e6
                            ncl_delta = ncl_val - MAX_NCL_RATE_PCT
                            over30_delta = over30_val - MAX_OVER30_RATE_PCT
                            kpis_payload = [
                                {
                                    "label": "Cuentas Iniciales (MOB 0)",
                                    "value": f"{resumen['cuentas_iniciales_mob0']:,}",
                                    "delta": f"Líneas: ${lineas_m:,.1f}M",
                                    "status": "blue",
                                },
                                {
                                    "label": "Severidad NCL / ENR",
                                    "value": f"{ncl_val:.2f}%",
                                    "delta": f"{ncl_delta:+.2f} pp vs límite {MAX_NCL_RATE_PCT}%",
                                    "status": "red" if ncl_val > MAX_NCL_RATE_PCT else "green",
                                },
                                {
                                    "label": "Morosidad Over30 / ENR",
                                    "value": f"{over30_val:.2f}%",
                                    "delta": (
                                        f"{over30_delta:+.2f} pp vs límite {MAX_OVER30_RATE_PCT}%"
                                    ),
                                    "status": (
                                        "red" if over30_val > MAX_OVER30_RATE_PCT else "green"
                                    ),
                                },
                                {
                                    "label": "Utilidad Neta Acumulada",
                                    "value": f"${util_m:,.2f}M",
                                    "delta": f"ROA Neto: {roa_val:.2f}%",
                                    "status": "green" if roa_val >= 0 else "orange",
                                },
                            ]
                            tabla_payload = [
                                [
                                    "Ingresos acumulados (REVENUE)",
                                    f"${resumen['ingresos_acumulados']:,.2f}",
                                    "Cubo DuckDB",
                                ],
                                [
                                    "Pérdida bruta (GCLAMTS)",
                                    f"${resumen['perdida_bruta_gcl']:,.2f}",
                                    "Antes de cobranza",
                                ],
                                [
                                    "Recuperación cobranza",
                                    f"${resumen['recuperacion_cobranza']:,.2f}",
                                    f"Eficiencia: {resumen['recovery_rate_pct']}% (mín 40%)",
                                ],
                                [
                                    "Pérdida neta (NCLAMTS)",
                                    f"${resumen['perdida_neta_ncl']:,.2f}",
                                    f"NCL/ENR: {ncl_val:.2f}% (máx {MAX_NCL_RATE_PCT}%)",
                                ],
                                [
                                    "Gastos totales (EXPENSES_TOTAL)",
                                    f"${resumen['gastos_totales']:,.2f}",
                                    "ACQ + ECM Var/Fix",
                                ],
                                [
                                    "Utilidad neta (NET_PROFIT)",
                                    f"${resumen['utilidad_neta']:,.2f}",
                                    f"ROA Neto: {roa_val:.2f}%",
                                ],
                            ]
                            hallazgos = [
                                (
                                    f"Cuentas iniciales (MOB 0): "
                                    f"{resumen['cuentas_iniciales_mob0']:,} "
                                    f"con líneas por ${lineas_m:,.1f}M."
                                ),
                                (
                                    f"Severidad NCL / ENR de {ncl_val:.2f}% "
                                    f"({ncl_delta:+.2f} pp vs límite {MAX_NCL_RATE_PCT}%)."
                                ),
                                (
                                    f"Morosidad Over30 / ENR de {over30_val:.2f}% "
                                    f"(recuperación de cobranza: {resumen['recovery_rate_pct']}%)."
                                ),
                                (
                                    f"Utilidad Neta acumulada de ${util_m:,.2f}M "
                                    f"(ROA Neto {roa_val:.2f}%)."
                                ),
                            ]
                            deck_title = (
                                f"{case['channel']} · {case['age_tag']} · "
                                f"{case['score_tag']} ({estado_riesgo})"
                            )
                            rep_res = json.loads(
                                compilar_entregables_ejecutivos.invoke(
                                    {
                                        "case_id": case["case_id"],
                                        "titulo": deck_title,
                                        "hallazgos": hallazgos,
                                        "dictamen": edited_draft,
                                        "rutas_graficas": [viz_res["ruta_png"]],
                                        "estado_riesgo": estado_riesgo,
                                        "kpis": kpis_payload,
                                        "tabla_metricas": tabla_payload,
                                    }
                                )
                            )
                            save_case_artifacts(
                                case["case_id"],
                                st.session_state["sql_queries"],
                                [{"resumen_cubo": resumen}],
                                edited_draft,
                            )
                            try:
                                git_msg = commit_human_approval(case["case_id"])
                            except Exception as exc:  # noqa: BLE001
                                git_msg = f"Aviso Git: {exc}"
                            st.session_state["last_outputs"] = rep_res
                            st.success(
                                f"Entregables compilados. {git_msg}",
                                icon=":material/check_circle:",
                            )

                with b2:
                    if st.button(
                        "Ver Git Diff de Auditoría",
                        icon=":material/difference:",
                        use_container_width=True,
                    ):
                        st.session_state["git_diff_text"] = get_case_diff(case["case_id"])

                if st.session_state["git_diff_text"]:
                    st.code(st.session_state["git_diff_text"], language="diff")

                last_out = st.session_state.get("last_outputs", {})
                if last_out.get("ruta_docx") and Path(last_out["ruta_docx"]).exists():
                    d1, d2 = st.columns(2)
                    with d1:
                        st.download_button(
                            "Descargar Memorándum (.docx)",
                            data=Path(last_out["ruta_docx"]).read_bytes(),
                            file_name=Path(last_out["ruta_docx"]).name,
                            icon=":material/download:",
                            use_container_width=True,
                        )
                    with d2:
                        st.download_button(
                            "Descargar Presentación (.pptx)",
                            data=Path(last_out["ruta_pptx"]).read_bytes(),
                            file_name=Path(last_out["ruta_pptx"]).name,
                            icon=":material/download:",
                            use_container_width=True,
                        )

        with tab_audit:
            with st.container(border=True):
                st.markdown("#### :material/speed: Telemetría de Ventana de Contexto")
                tu = st.session_state.get("token_usage") or {}
                used_ctx = int(tu.get("prompt_eval_count", 0))
                max_ctx = max(int(tu.get("num_ctx", OLLAMA_NUM_CTX)), 1)
                ratio = min(used_ctx / max_ctx, 1.0)
                st.progress(
                    ratio,
                    text=f"Contexto usado: {used_ctx:,} / {max_ctx:,} tokens ({ratio * 100:.1f}%)",
                )

                t1, t2, t3 = st.columns(3)
                t1.metric("Tokens Generados", f"{tu.get('eval_count', 0):,}", border=True)
                t2.metric("Llamadas al LLM", f"{tu.get('total_calls', 0)}", border=True)
                t3.metric("Última Latencia", f"{tu.get('last_latency_s', 0)} s", border=True)

            with st.container(border=True):
                st.markdown("#### :material/code: Consultas SQL Ejecutadas por el Agente")
                if st.session_state["sql_queries"]:
                    for q in st.session_state["sql_queries"]:
                        st.code(q, language="sql")
                else:
                    st.caption("Aún no se han ejecutado consultas Text-to-SQL en este caso.")

        with tab_resultados:
            # Muestra graficas, tablas y reportes del chat abierto (lo mas nuevo arriba)
            chat_res = st.session_state["chat_activo"]
            resultados = chat_res.get("resultados", [])
            if not resultados:
                st.info(
                    "Aquí aparecerán las gráficas, tablas y reportes "
                    "que le pidas al Copiloto en este chat.",
                    icon=":material/inventory_2:",
                )
            for k in range(len(resultados) - 1, -1, -1):
                r = resultados[k]
                with st.container(border=True):
                    icono = {
                        "grafica": "bar_chart",
                        "reporte": "description",
                        "tabla": "table_chart",
                    }.get(r["tipo"], "inventory_2")
                    st.markdown(f"#### :material/{icono}: {r['titulo']}")
                    st.caption(r.get("fecha", ""))

                    if r["tipo"] == "grafica":
                        for j, figura_json in enumerate(r["figuras"]):
                            fig_res = pio.from_json(figura_json)
                            fig_res.update_layout(width=None, height=420)
                            st.plotly_chart(
                                fig_res,
                                use_container_width=True,
                                key=f"res_graf_{chat_res['id']}_{k}_{j}",
                            )
                        if r.get("tabla"):
                            st.dataframe(
                                pd.DataFrame(
                                    r["tabla"]["filas"], columns=r["tabla"]["encabezado"]
                                ),
                                hide_index=True,
                                use_container_width=True,
                            )
                        if r.get("texto"):
                            st.markdown(r["texto"])

                    elif r["tipo"] == "tabla":
                        for t in r["tablas"]:
                            st.markdown(t)

                    elif r["tipo"] == "reporte":
                        ruta_docx = Path(r["docx"])
                        ruta_html = Path(r["html"]) if r.get("html") else None
                        ruta_pdf = ruta_docx.with_suffix(".pdf")
                        llave = f"editor_{chat_res['id']}_{k}"
                        # vista previa editable, se da clic en el texto, se escribe y se guarda
                        if (
                            ruta_html
                            and ruta_html.exists()
                            and ruta_docx.with_suffix(".json").exists()
                        ):
                            guardado = _editor_reporte(
                                html=ruta_html.read_text(encoding="utf-8"),
                                guardado=st.session_state.get(f"guardado_{llave}", False),
                                key=llave,
                                default=None,
                            )
                            if guardado and guardado.get("nonce") != st.session_state.get(
                                f"nonce_{llave}"
                            ):
                                st.session_state[f"nonce_{llave}"] = guardado["nonce"]
                                try:
                                    avisos = editar_reporte(ruta_docx, guardado["cambios"])
                                    st.session_state[f"guardado_{llave}"] = True
                                    st.session_state[f"avisos_{llave}"] = avisos
                                except Exception as exc:  # noqa: BLE001
                                    st.session_state[f"avisos_{llave}"] = []
                                    st.error(f"No se pudieron guardar los cambios. {exc}")
                                st.rerun()
                            # Si hay cifras fuera del cubo se avisa, pero se respeta la edicion
                            if st.session_state.get(f"avisos_{llave}"):
                                st.warning(
                                    "Estas cifras no salen del cubo, "
                                    "revísalas antes de mandar el reporte: "
                                    + ", ".join(st.session_state[f"avisos_{llave}"]),
                                    icon=":material/warning:",
                                )
                        elif ruta_html and ruta_html.exists():
                            # reportes viejos sin piezas guardadas solo se pueden ver
                            components.html(
                                ruta_html.read_text(encoding="utf-8"), height=750, scrolling=True
                            )
                        else:
                            st.caption(
                                "No hay vista previa para este reporte, "
                                "pero puedes descargar el Word."
                            )
                        d1, d2 = st.columns(2)
                        with d1:
                            if ruta_docx.exists():
                                # si lo descarga es recompensa para el agente
                                st.download_button(
                                    "Descargar Word (.docx)",
                                    data=ruta_docx.read_bytes(),
                                    file_name=ruta_docx.name,
                                    icon=":material/download:",
                                    use_container_width=True,
                                    key=f"res_docx_{chat_res['id']}_{k}",
                                    on_click=aprendizaje.dar_recompensa,
                                    args=(chat_res["id"], 1),
                                )
                        with d2:
                            if ruta_pdf.exists():
                                st.download_button(
                                    "Descargar PDF",
                                    data=ruta_pdf.read_bytes(),
                                    file_name=ruta_pdf.name,
                                    icon=":material/picture_as_pdf:",
                                    use_container_width=True,
                                    key=f"res_pdf_{chat_res['id']}_{k}",
                                    on_click=aprendizaje.dar_recompensa,
                                    args=(chat_res["id"], 1),
                                )

        with tab_politicas:
            # Subida de manuales que consulta el agente en ChromaDB
            with st.container(border=True):
                st.markdown("#### :material/upload_file: Subir o actualizar una política")
                st.caption(
                    "Si el archivo se llama igual que uno que ya existe, lo reemplaza. "
                    "El agente usa la versión nueva desde la siguiente pregunta."
                )
                with st.form("form_politica", clear_on_submit=True):
                    nuevo_manual = st.file_uploader(
                        "Manual de política", type=["md", "pdf", "docx"]
                    )
                    if st.form_submit_button("Subir política", icon=":material/upload:"):
                        if nuevo_manual is None:
                            st.warning("Primero escoge un archivo.")
                        else:
                            with st.spinner("Leyendo el manual y guardándolo en ChromaDB..."):
                                try:
                                    total = politicas.guardar_politica(
                                        nuevo_manual.name, nuevo_manual.getvalue()
                                    )
                                    st.success(
                                        f"{nuevo_manual.name} quedó cargado con {total} secciones."
                                    )
                                except Exception as exc:  # noqa: BLE001
                                    st.error(f"No se pudo cargar la política. {exc}")

            manuales = politicas.listar_politicas()
            if not manuales:
                st.info(
                    "Aquí aparecerán las políticas que consulta el agente.",
                    icon=":material/policy:",
                )
            for manual in manuales:
                # cada politica va en su tarjeta como en resultados
                with st.container(border=True):
                    st.markdown(f"#### :material/description: {manual['nombre']}")
                    estado = (
                        f"{manual['secciones']} secciones en ChromaDB"
                        if manual["secciones"]
                        else "Sin indexar, vuelve a subirlo"
                    )
                    st.caption(f"{manual['fecha']} · {estado}")
                    with st.expander("Ver contenido", icon=":material/visibility:"):
                        try:
                            st.markdown(
                                politicas.contenido_politica(manual["nombre"])
                                or "Sin contenido guardado."
                            )
                        except Exception as exc:  # noqa: BLE001
                            st.caption(f"No se pudo leer el contenido. {exc}")
                    # el borrado pide confirmacion para no quitar una politica por accidente
                    with st.popover("Borrar", icon=":material/delete:"):
                        st.write(f"¿Seguro que quieres borrar {manual['nombre']}?")
                        if st.button(
                            "Sí, borrar", key=f"borrar_politica_{manual['nombre']}", type="primary"
                        ):
                            politicas.borrar_politica(manual["nombre"])
                            st.rerun()

    # ------------------------------------------------------------------
    # PANEL DERECHO: CHAT COPILOTO INVESTIGADOR
    # ------------------------------------------------------------------
    with col_chat:
        with st.container(border=True):
            ch_l, ch_h, ch_r = st.columns([2, 1, 1], vertical_alignment="center")
            with ch_l:
                st.markdown("#### :material/forum: Copiloto Investigador")
            with ch_h:
                # el historial de conversaciones vive aqui junto al chat
                with st.popover("Historial", icon=":material/history:", use_container_width=True):
                    _render_chats()
            with ch_r:
                if st.button(
                    "Nuevo",
                    icon=":material/add_comment:",
                    use_container_width=True,
                    key="nuevo_chat_panel",
                ):
                    # si el chat actual sigue vacio no creamos otro
                    if st.session_state["chat_activo"]["mensajes"]:
                        st.session_state["chat_activo"] = memoria.crear_chat()
                    st.rerun()

            st.caption("Consulta ad-hoc el cubo DuckDB y las políticas internas.")

            # el usuario escoge con que modelo habla el agente del chat
            st.segmented_control(
                "Modelo",
                options=list(OLLAMA_MODELOS),
                default="Normal",
                key="modelo_elegido",
                format_func=lambda m: f"{m} · {OLLAMA_MODELOS[m]}",
                label_visibility="collapsed",
            )

            quick_choice = st.pills(
                "Preguntas sugeridas",
                options=QUICK_PROMPTS,
                selection_mode="single",
                label_visibility="collapsed",
                key="quick_prompt_pills",
            )

            chat_box = st.container(height=420, border=False)
            with chat_box:
                if not st.session_state["chat_history"]:
                    st.info(
                        "Haz una pregunta sobre cohortes, canales, scores o políticas de riesgo. "
                        "El agente verificará todas las cifras en DuckDB.",
                        icon=":material/lightbulb:",
                    )
                chat_id = st.session_state["chat_activo"]["id"]
                historial_chat = st.session_state["chat_history"]
                for i, item in enumerate(historial_chat):
                    with st.chat_message(item[0]):
                        st.markdown(item[1])
                        if len(item) > 2 and item[2] and Path(item[2]).exists():
                            # si descarga el reporte es recompensa para el agente
                            st.download_button(
                                "Descargar reporte (.docx)",
                                data=Path(item[2]).read_bytes(),
                                file_name=Path(item[2]).name,
                                icon=":material/download:",
                                key=f"descarga_{chat_id}_{i}",
                                on_click=aprendizaje.dar_recompensa,
                                args=(chat_id, 1),
                            )
                        # Las graficas guardadas en JSON se reconstruyen interactivas
                        if len(item) > 3 and item[3]:
                            for k, figura_json in enumerate(item[3]):
                                fig_chat = pio.from_json(figura_json)
                                fig_chat.update_layout(width=None, height=360)
                                st.plotly_chart(
                                    fig_chat,
                                    use_container_width=True,
                                    key=f"grafica_{chat_id}_{i}_{k}",
                                )
                        # Los pulgares solo van en la ultima respuesta (recompensa al evento)
                        if item[0] == "assistant" and i == len(historial_chat) - 1:
                            st.feedback(
                                "thumbs",
                                key=f"pulgar_{chat_id}_{i}",
                                on_change=_guardar_pulgar,
                                args=(chat_id, f"pulgar_{chat_id}_{i}"),
                            )

            entrada = st.chat_input(
                "Pregunta sobre el portafolio...",
                accept_file=True,
                file_type=["pdf", "docx", "png", "jpg", "jpeg"],
            )
            active_q = None
            archivo = None
            if entrada:
                # si solo mandan el archivo sin texto pedimos un resumen
                active_q = entrada.text or "Resume este documento"
                archivo = entrada.files[0] if entrada.files else None
            elif quick_choice and quick_choice != st.session_state.get("last_quick_prompt"):
                st.session_state["last_quick_prompt"] = quick_choice
                active_q = quick_choice

            if active_q:
                with st.spinner("Consultando agente..."):
                    _send_copilot_message(active_q, case["case_id"], archivo)
                st.rerun()


if __name__ == "__main__":
    main()
