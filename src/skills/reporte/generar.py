import base64
import html
import json
import re
import sys
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import duckdb
import pandas as pd
import plotly.express as px
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from src.config import DUCKDB_PATH, MAX_NCL_RATE_PCT, MAX_OVER30_RATE_PCT, OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_NUM_CTX

raiz = Path(__file__).resolve().parent
plantillas = [raiz / "plantilla.docx"]
carpeta = raiz.parents[2] / "outputs" / "reportes"
columnas = ["VINTAGE", "STRATEGY", "STRATEGY_SEGMENT", "PRODUCT", "CHANNEL", "AGE_TAG", "SCORE_TAG"]
Columna = Literal["VINTAGE", "STRATEGY", "STRATEGY_SEGMENT", "PRODUCT", "CHANNEL", "AGE_TAG", "SCORE_TAG"]
version = "v10"
print("generar.py", version)
colores = ["#0E3A47", "#E4002B", "#7A9CA5", "#F28C9B", "#3D6E7A", "#B5B5B5"]


class Filtro(BaseModel):
    columna: Columna
    valor: str


class Grupo(BaseModel):
    etiqueta: str
    filtros: list[Filtro] = []


class Peticion(BaseModel):
    tipo: Literal["segmento", "comparar", "ranking"]
    grupos: list[Grupo]
    dimension: Optional[Columna] = None
    orden: Literal["ncl_rate_pct", "over30_rate_pct", "net_roa_pct"] = "ncl_rate_pct"
    maduras: bool = True
    grafica: Literal["ninguna", "barras", "curva", "ambas"] = "ninguna"


# los topes de largo obligan a qwen a terminar el json y no ciclarse
class Seccion(BaseModel):
    titulo: str = Field(max_length=90)
    parrafos: list[str] = Field(min_length=1, max_length=3)


class Reporte(BaseModel):
    asunto: str = Field(max_length=110)
    titulo: str = Field(max_length=130)
    resumen: str = Field(max_length=900)
    recomendacion: str = Field(max_length=500)
    secciones: list[Seccion] = Field(min_length=1, max_length=3)


# paso 1 la pregunta se convierte en filtros

def catalogo(con):
    cat = {}
    for c in columnas:
        cat[c] = [str(r[0]) for r in con.execute(f"SELECT DISTINCT {c} FROM cubo ORDER BY {c}").fetchall()]
    return cat


def interpretar(llm, pregunta, cat):
    valores = "\n".join(c + "  " + ", ".join(v) for c, v in cat.items())
    prompt = f"""Convierte la pregunta en filtros sobre el cubo de tarjetas.
tipo es segmento si pide un solo grupo, comparar si pide dos o más grupos y ranking si pide el peor o el mejor.
Para comparar pon un grupo por cada cosa que se compara, pueden ser dos, tres o más.
Para segmento y ranking pon un solo grupo (puede ir sin filtros). En ranking dimension es la columna que se ordena.
Los meses se refieren a VINTAGE en formato AAAAMM, por ejemplo junio de 2025 es 202506.
Si mencionan meses sin año usa el año más reciente de la lista que tenga ese mes.
maduras es true salvo que la pregunta pida otra cosa.
Cohortes maduras no es un filtro, ya se maneja aparte con MOB, nunca lo pongas como AGE_TAG. El valor 03| Mature >30 solo se usa si piden clientes mayores de 30 años.
grafica
  barras si sirve ver lado a lado los indicadores de los grupos o un ranking
  curva si importa ver cómo evoluciona la pérdida mes a mes de maduración, por ejemplo al comparar vintages
  ambas si sirven las dos
  ninguna si la pregunta es sencilla y una gráfica no aporta, o si el usuario pide que no lleve
Si el usuario pide gráfica explícitamente nunca pongas ninguna.
Usa solo valores que esten exactamente en esta lista.

{valores}

Pregunta  {pregunta}"""
    aviso = ""
    for intento in range(3):
        pet = llm.with_structured_output(Peticion, method="json_schema").invoke(prompt + aviso)
        malos = [f"{f.valor} en {f.columna}" for g in pet.grupos for f in g.filtros if f.valor not in cat[f.columna]]
        firmas = [tuple(sorted((f.columna, f.valor) for f in g.filtros)) for g in pet.grupos]
        if malos:
            aviso = "\nEstos valores no existen, usa solo los de la lista  " + ", ".join(malos)
        elif len(pet.grupos) > 1 and (any(not f for f in firmas) or len(set(firmas)) < len(firmas)):
            # al comparar cada grupo debe tener sus propios filtros
            aviso = "\nAl comparar cada grupo debe llevar sus propios filtros y no pueden quedar vacíos ni iguales. Si la pregunta menciona un canal o producto ponlo en todos los grupos."
        else:
            return pet
        print("qwen armo mal los filtros, se intenta otra vez", aviso.strip())
    # si qwen no pudo, intentamos sacar los filtros directo de la pregunta con el catalogo
    pet = peticion_por_reglas(pregunta, cat)
    if pet is not None:
        print("se usan filtros por reglas", [(g.etiqueta, [(f.columna, f.valor) for f in g.filtros]) for g in pet.grupos])
        return pet
    raise ValueError("No se pudieron entender los filtros de la pregunta, intenta escribirla más clara")


meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def normalizar(texto):
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


def peticion_por_reglas(pregunta, cat):
    t = normalizar(pregunta)

    # buscamos en la pregunta los valores del catalogo, canal primero porque es lo que mas se pregunta
    orden = ["CHANNEL", "PRODUCT", "SCORE_TAG", "AGE_TAG", "STRATEGY", "STRATEGY_SEGMENT"]
    if "producto" in t:
        orden = ["PRODUCT"] + [c for c in orden if c != "PRODUCT"]
    encontrados = {}
    for col in orden:
        valores = [v for v in cat.get(col, []) if len(v) > 2 and re.search(r"(?<![a-z0-9])" + re.escape(normalizar(v)) + r"(?![a-z0-9])", t)]
        # ordenamos por como aparecen en la pregunta
        valores.sort(key=lambda v: t.find(normalizar(v)))
        if valores:
            encontrados[col] = valores
            break

    # los meses se vuelven vintages, si no dicen año usamos el mas reciente que exista
    # si dicen un año para un mes, por ejemplo junio y julio de 2025, ese año aplica a todos
    anio_general = re.search(r"20\d{2}", t)
    anio_general = anio_general.group(0) if anio_general else None
    vintages = []
    for i, m in enumerate(meses, start=1):
        for encontrado in re.finditer(m + r"(?:\s+(?:de\s+)?(20\d{2}))?", t):
            anio = encontrado.group(1) or anio_general
            opciones = [v for v in cat.get("VINTAGE", []) if v.endswith(f"{i:02d}") and (anio is None or v.startswith(anio))]
            if opciones:
                vintages.append((encontrado.start(), max(opciones), f"{m.capitalize()} {max(opciones)[:4]}"))
    vintages = [(v, e) for _, v, e in sorted(vintages)]

    grafica = "ninguna"
    if re.search(r"curva|maduracion|evolucion", t):
        grafica = "curva"
    elif re.search(r"grafic", t):
        grafica = "barras"

    if re.search(r"peor|mejor|ranking", t) and not (len(vintages) > 1 or any(len(v) > 1 for v in encontrados.values())):
        dimension = "CHANNEL"
        for palabra, col in [("producto", "PRODUCT"), ("score", "SCORE_TAG"), ("edad", "AGE_TAG"), ("estrategia", "STRATEGY")]:
            if palabra in t:
                dimension = col
        orden_metrica = "over30_rate_pct" if re.search(r"over30|morosidad", t) else ("net_roa_pct" if re.search(r"roa|rentab", t) else "ncl_rate_pct")
        return Peticion(tipo="ranking", grupos=[Grupo(etiqueta="Todos", filtros=[])], dimension=dimension,
                        orden=orden_metrica, grafica=grafica if grafica != "ninguna" else "barras")

    if len(vintages) > 1:
        grupos = [Grupo(etiqueta=e, filtros=[Filtro(columna="VINTAGE", valor=v)]) for v, e in vintages]
        return Peticion(tipo="comparar", grupos=grupos, grafica=grafica)

    for col, valores in encontrados.items():
        filtros_mes = [Filtro(columna="VINTAGE", valor=vintages[0][0])] if vintages else []
        if len(valores) > 1:
            grupos = [Grupo(etiqueta=v, filtros=[Filtro(columna=col, valor=v)] + filtros_mes) for v in valores]
            return Peticion(tipo="comparar", grupos=grupos, grafica=grafica)
        return Peticion(tipo="segmento", grupos=[Grupo(etiqueta=valores[0], filtros=[Filtro(columna=col, valor=valores[0])] + filtros_mes)], grafica=grafica)

    if vintages:
        v, e = vintages[0]
        return Peticion(tipo="segmento", grupos=[Grupo(etiqueta=e, filtros=[Filtro(columna="VINTAGE", valor=v)])], grafica=grafica)
    return None


# paso 2 consulta en duckdb

sql_metricas = """
SELECT
    ROUND(SUM(ENRAMTS), 2) AS saldo_total,
    ROUND(SUM(REVENUE), 2) AS ingresos,
    ROUND(SUM(NCLAMTS), 2) AS perdida_neta,
    ROUND(SUM(EXPENSES_TOTAL), 2) AS gastos_totales,
    ROUND(SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL), 2) AS utilidad_neta,
    ROUND(SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0) * 100, 2) AS ncl_rate_pct,
    ROUND(SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0) * 100, 2) AS over30_rate_pct,
    ROUND(SUM(RECOVERYAMTS) / NULLIF(SUM(GCLAMTS), 0) * 100, 2) AS recovery_rate_pct,
    ROUND((SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL)) / NULLIF(SUM(ENRAMTS), 0) * 100, 2) AS net_roa_pct
FROM cubo
WHERE {where}
"""

sql_curva = """
SELECT MOB,
    ROUND(SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0) * 100, 2) AS ncl_rate_pct,
    ROUND(SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0) * 100, 2) AS over30_rate_pct
FROM cubo
WHERE {where}
GROUP BY MOB ORDER BY MOB
"""


def armar_where(filtros, mob_min=None, mob_max=None):
    partes = []
    params = []
    for f in filtros:
        partes.append(f"{f.columna} = ?")
        params.append(int(f.valor) if f.columna == "VINTAGE" else f.valor)
    if mob_min is not None:
        partes.append("MOB >= ?")
        params.append(mob_min)
    if mob_max is not None:
        partes.append("MOB <= ?")
        params.append(mob_max)
    if not partes:
        return "TRUE", params
    return " AND ".join(partes), params


def consultar(con, pet):
    mob_min = None
    mob_max = None
    periodo = "todos los MOB"

    # si se comparan vintages se cortan todos en el mismo MOB
    varios_vintages = len(pet.grupos) > 1 and all(any(f.columna == "VINTAGE" for f in g.filtros) for g in pet.grupos)
    if varios_vintages:
        topes = []
        for g in pet.grupos:
            where, params = armar_where(g.filtros)
            topes.append(con.execute(f"SELECT MAX(MOB) FROM cubo WHERE {where}", params).fetchone()[0])
        mob_max = min(t for t in topes if t is not None)
        periodo = f"MOB 0 a {mob_max} en todos los vintages"
    elif pet.maduras:
        mob_min = 6
        periodo = "cohortes maduras, MOB 6 o más"

    if len(pet.grupos) > 1:
        pet.tipo = "comparar"

    if pet.tipo == "ranking":
        col = pet.dimension or "CHANNEL"
        filtros = pet.grupos[0].filtros if pet.grupos else []
        where, params = armar_where(filtros, mob_min, mob_max)
        direccion = "ASC" if pet.orden == "net_roa_pct" else "DESC"
        sql = f"""
        SELECT {col} AS valor,
            ROUND(SUM(NCLAMTS) / NULLIF(SUM(ENRAMTS), 0) * 100, 2) AS ncl_rate_pct,
            ROUND(SUM(OVER30AMTS) / NULLIF(SUM(ENRAMTS), 0) * 100, 2) AS over30_rate_pct,
            ROUND((SUM(REVENUE) - SUM(NCLAMTS) - SUM(EXPENSES_TOTAL)) / NULLIF(SUM(ENRAMTS), 0) * 100, 2) AS net_roa_pct
        FROM cubo WHERE {where}
        GROUP BY {col} HAVING SUM(ENRAMTS) > 0
        ORDER BY {pet.orden} {direccion}
        """
        cur = con.execute(sql, params)
        nombres = [d[0] for d in cur.description]
        filas = [dict(zip(nombres, f)) for f in cur.fetchall()]
        return {"tipo": "ranking", "dimension": col, "orden": pet.orden, "periodo": periodo, "filas": filas, "curvas": []}

    grupos = []
    curvas = []
    for g in pet.grupos:
        where, params = armar_where(g.filtros, mob_min, mob_max)
        cur = con.execute(sql_metricas.format(where=where), params)
        nombres = [d[0] for d in cur.description]
        grupos.append({"etiqueta": g.etiqueta, "m": dict(zip(nombres, cur.fetchone()))})

        # la curva siempre arranca en MOB 0 para ver la maduración completa
        if pet.grafica in ["curva", "ambas"]:
            where, params = armar_where(g.filtros, None, mob_max)
            df = con.execute(sql_curva.format(where=where), params).df()
            df["grupo"] = g.etiqueta
            curvas.append(df)
    return {"tipo": pet.tipo, "periodo": periodo, "grupos": grupos, "curvas": curvas}


# paso 3 qwen redacta con los numeros

def dinero(x):
    x = x or 0
    if abs(x) >= 1e9:
        return f"${x / 1e9:,.1f} mil millones"
    if abs(x) >= 1e6:
        return f"${x / 1e6:,.1f} millones"
    return f"${x:,.0f}"


def pct(x):
    return f"{(x or 0):.2f}%"


indicadores = [
    ("Pérdida neta / saldo", "ncl_rate_pct", pct),
    ("Morosidad Over30 / saldo", "over30_rate_pct", pct),
    ("Recuperación / pérdida bruta", "recovery_rate_pct", pct),
    ("ROA neto", "net_roa_pct", pct),
    ("Saldo total", "saldo_total", dinero),
    ("Ingresos", "ingresos", dinero),
    ("Pérdida neta", "perdida_neta", dinero),
    ("Gastos totales", "gastos_totales", dinero),
    ("Utilidad neta", "utilidad_neta", dinero),
]


def cifras(datos):
    lineas = ["Periodo  " + datos["periodo"]]
    if datos["tipo"] == "ranking":
        lineas.append("Ranking por " + datos["dimension"])
        for f in datos["filas"]:
            # le decimos si esta arriba o debajo del limite para que qwen no lo compare solo
            ncl = "arriba" if (f["ncl_rate_pct"] or 0) > MAX_NCL_RATE_PCT else "debajo"
            o30 = "arriba" if (f["over30_rate_pct"] or 0) > MAX_OVER30_RATE_PCT else "debajo"
            lineas.append(f"{f['valor']}  pérdida neta {pct(f['ncl_rate_pct'])} {ncl} del límite, Over30 {pct(f['over30_rate_pct'])} {o30} del límite, ROA neto {pct(f['net_roa_pct'])}")
        lineas.append(f"Son {len(datos['filas'])} valores, el peor es {datos['filas'][0]['valor']} y el mejor es {datos['filas'][-1]['valor']}. Si das un rango inclúyelos a todos.")
    else:
        for g in datos["grupos"]:
            lineas.append("Grupo " + g["etiqueta"])
            for nombre, campo, fmt in indicadores:
                lineas.append(f"  {nombre}  {fmt(g['m'][campo])}")
            if g["m"]["ingresos"]:
                lineas.append(f"  Pérdida neta entre ingresos  {g['m']['perdida_neta'] / g['m']['ingresos']:.1f} veces")
            ncl = "arriba" if (g["m"]["ncl_rate_pct"] or 0) > MAX_NCL_RATE_PCT else "debajo"
            o30 = "arriba" if (g["m"]["over30_rate_pct"] or 0) > MAX_OVER30_RATE_PCT else "debajo"
            lineas.append(f"  Pérdida neta {ncl} del límite y Over30 {o30} del límite")
        base = datos["grupos"][0]
        for g in datos["grupos"][1:]:
            lineas.append(f"Diferencia de {g['etiqueta']} contra {base['etiqueta']}")
            for nombre, campo, fmt in indicadores[:4]:
                dif = (g["m"][campo] or 0) - (base["m"][campo] or 0)
                # en pérdida y morosidad bajar es bueno, en recuperación y ROA subir es bueno
                bueno = dif < 0 if campo in ["ncl_rate_pct", "over30_rate_pct"] else dif > 0
                sentido = "sin cambio" if dif == 0 else ("mejora" if bueno else "empeora")
                lineas.append(f"  {nombre}  {dif:+.2f} puntos, {sentido}")
    lineas.append(f"Límites de apetito  pérdida neta {MAX_NCL_RATE_PCT}% y Over30 {MAX_OVER30_RATE_PCT}%")
    return "\n".join(lineas)


def redactar(llm, pregunta, datos, extra=""):
    nota_grafica = ""
    if datos.get("graficas"):
        nota_grafica = "El reporte lleva estas gráficas, puedes mencionarlas en el texto  " + ", ".join(t for _, t in datos["graficas"])
    prompt = f"""Eres analista senior de riesgos del portafolio de tarjetas de Banamex y escribes un memorándum para el Comité de Crédito.
Regla principal, todas las cifras van con dígitos copiadas tal cual de abajo, por ejemplo 7.59% o $353.1 millones. Nunca escribas un número con letra.
Usa solo las cifras de abajo, no inventes ni recalcules. Las cantidades son pesos mexicanos.
El titulo dice la conclusión en máximo 15 palabras. El resumen es un párrafo de 3 a 5 oraciones con la respuesta directa.
Pon de 1 a 3 secciones, las que la pregunta necesite. No repitas la misma idea en varias partes.
Explica qué significa cada cifra y si una diferencia es grande o chica.
Evalúa riesgo y rentabilidad juntos. Si la pérdida neta es mayor que los ingresos o la utilidad neta es negativa, el segmento pierde dinero y eso es lo más importante del reporte, aunque las tasas estén debajo de los límites.
Una morosidad Over30 arriba de 10% es alta aunque esté debajo del límite, dilo.
No expliques causas que no salgan de las cifras, nada de gastos de tecnología, campañas o supuestos parecidos.
Si la utilidad neta es negativa nunca recomiendes mantener sin cambios ni expandir. Recomienda vigilar, restringir línea o suspender originación según qué tan grave sea.
La recomendación va solo en el campo recomendacion, no la repitas dentro de las secciones.
Si los datos son poco maduros dilo.
Escribe todas las cifras con dígitos tal como vienen, por ejemplo 7.59% o $353.1 millones, nunca con letra.
Para decir si algo mejora o empeora usa lo que dicen las diferencias, no lo deduzcas tú.
El asunto es corto, máximo 12 palabras.
Escribe en prosa, sin viñetas, sin markdown y sin dos puntos.
{nota_grafica}

Pregunta  {pregunta}

{cifras(datos)}
{extra}"""
    rep = llm.with_structured_output(Reporte, method="json_schema").invoke(prompt)
    for s in rep.secciones:
        # a veces qwen deja el nombre del campo como texto, por ejemplo parrafos[2], esos se quitan
        # tambien quitamos parrafos que solo dicen el nombre de un campo, como titulo o resumen
        s.parrafos = [
            p[:1200] for p in s.parrafos
            if not re.match(r"^\s*p[aá]rrafos?\b", p, re.I)
            and not re.fullmatch(r"\W*(t[ií]tulo|secci[oó]n(es)?|asunto|resumen|recomendaci[oó]n|p[aá]rrafos?)\W*\d*\W*", p, re.I)
        ]
        if re.match(r"^\s*(p[aá]rrafos?|secciones?|titulo)\b", s.titulo, re.I):
            s.titulo = ""
    return rep


# paso 4 revisar que no invente cifras

def numeros(texto):
    return {f"{float(n.replace(',', '').rstrip('.')):g}" for n in re.findall(r"\d[\d,]*\.?\d*", texto)}


def con_letra(rep):
    texto = " ".join([rep.titulo, rep.resumen, rep.recomendacion] + [p for s in rep.secciones for p in s.parrafos]).lower()
    return bool(re.search(r"por ciento| coma (cero|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)|punto (cero|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)", texto))


def inventadas(rep, datos, pregunta):
    validas = numeros(cifras(datos) + " " + pregunta + " 10 30 100")
    # los años de los vintages tambien son validos, por ejemplo 202405 da 2024
    for v in re.findall(r"\b(20\d{2})(0[1-9]|1[0-2])\b", cifras(datos) + " " + pregunta):
        validas.add(v[0])
    texto = " ".join([rep.titulo, rep.resumen, rep.recomendacion] + [p for s in rep.secciones for p in s.parrafos])
    return sorted(n for n in numeros(texto) if n not in validas and len(n.replace(".", "")) > 1)


# paso 5 graficas con plotly express

def estilo(fig, titulo_y):
    fig.update_layout(
        template="simple_white",
        font=dict(family="Arial", size=13, color="#333333"),
        legend_title_text="",
        yaxis_title=titulo_y,
        margin=dict(l=60, r=20, t=30, b=50),
        width=900,
        height=420,
    )
    return fig


def guardar_png(fig, ruta):
    try:
        fig.write_image(str(ruta), scale=2)
    except Exception:
        import kaleido
        kaleido.write_fig_sync(fig, path=str(ruta), opts={"format": "png", "scale": 2})


def armar_figuras(datos, tipo_grafica):
    # arma las figuras de plotly sin guardarlas, las usan el word y el chat
    figuras = []

    if tipo_grafica in ["barras", "ambas"]:
        if datos["tipo"] == "ranking":
            df = pd.DataFrame(datos["filas"])
            campo = datos["orden"]
            nombre = {"ncl_rate_pct": "Pérdida neta / saldo (%)", "over30_rate_pct": "Over30 / saldo (%)", "net_roa_pct": "ROA neto (%)"}[campo]
            df["valor"] = df["valor"].astype(str)
            fig = px.bar(df, x="valor", y=campo, color_discrete_sequence=[colores[0]], text=campo)
            fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside")
            limite = {"ncl_rate_pct": MAX_NCL_RATE_PCT, "over30_rate_pct": MAX_OVER30_RATE_PCT}.get(campo)
            if limite:
                # dibujamos el limite como trazo punteado para que si salga en el png
                fig.add_scatter(x=df["valor"], y=[limite] * len(df), mode="lines",
                                line=dict(dash="dash", color="#6B6B6B"), name=f"Límite {limite}%")
                fig.update_yaxes(range=[0, max(limite, df[campo].max()) * 1.2])
            estilo(fig, nombre).update_layout(xaxis_title="")
            titulo = f"{nombre} por {datos['dimension']}"
        else:
            filas = []
            for g in datos["grupos"]:
                for nombre, campo in [("Pérdida neta / saldo", "ncl_rate_pct"), ("Over30 / saldo", "over30_rate_pct"), ("ROA neto", "net_roa_pct")]:
                    filas.append({"grupo": g["etiqueta"], "indicador": nombre, "valor": g["m"][campo] or 0})
            df = pd.DataFrame(filas)
            fig = px.bar(df, x="indicador", y="valor", color="grupo", barmode="group", color_discrete_sequence=colores, text="valor")
            fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside")
            estilo(fig, "Porcentaje (%)").update_layout(xaxis_title="")
            titulo = "Indicadores de riesgo y rentabilidad por grupo"
        figuras.append(("barras", fig, titulo))

    if tipo_grafica in ["curva", "ambas"] and datos["curvas"]:
        df = pd.concat(datos["curvas"])
        fig = px.line(df, x="MOB", y="ncl_rate_pct", color="grupo", markers=True, color_discrete_sequence=colores)
        mobs = sorted(df["MOB"].unique())
        fig.add_scatter(x=mobs, y=[MAX_NCL_RATE_PCT] * len(mobs), mode="lines",
                        line=dict(dash="dash", color="#6B6B6B"), name=f"Límite {MAX_NCL_RATE_PCT}%")
        fig.update_yaxes(range=[0, max(MAX_NCL_RATE_PCT, df["ncl_rate_pct"].max()) * 1.2])
        estilo(fig, "Pérdida neta / saldo (%)").update_layout(xaxis_title="Meses en libros (MOB)")
        figuras.append(("curva", fig, "Curva de maduración de la pérdida neta"))

    return figuras


def hacer_graficas(datos, tipo_grafica, destino=None, prefijo=""):
    # para el word guardamos cada figura como png, junto al reporte para poder editarlo despues
    graficas = []
    tmp = Path(destino) if destino else Path(tempfile.mkdtemp())
    tmp.mkdir(parents=True, exist_ok=True)
    for nombre, fig, titulo in armar_figuras(datos, tipo_grafica):
        ruta = tmp / f"{prefijo}{nombre}.png"
        guardar_png(fig, ruta)
        graficas.append((ruta, titulo))
    return graficas


# paso 6 se llena la plantilla

def borde(celda, color, grosor):
    tcpr = celda._tc.get_or_add_tcPr()
    bordes = OxmlElement("w:tcBorders")
    for lado in ["top", "left", "right", "bottom"]:
        b = OxmlElement(f"w:{lado}")
        if lado == "bottom":
            b.set(qn("w:val"), "single")
            b.set(qn("w:sz"), grosor)
            b.set(qn("w:color"), color)
        else:
            b.set(qn("w:val"), "nil")
        bordes.append(b)
    tcpr.append(bordes)


def escribir(doc, texto, negrita=False, tam=11, antes=0, despues=8, gris=False, justificar=True, color=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(antes)
    p.paragraph_format.space_after = Pt(despues)
    p.paragraph_format.line_spacing = 1.15
    if justificar:
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run(texto)
    r.bold = negrita
    r.font.size = Pt(tam)
    r.font.name = "Arial"
    if gris:
        r.font.color.rgb = RGBColor(0x6B, 0x6B, 0x6B)
    if color:
        r.font.color.rgb = RGBColor.from_string(color)
    return p


def dato(doc, etiqueta, valor, antes=0):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(antes)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(etiqueta + "   ")
    r.bold = True
    r.font.name = "Arial"
    r.font.size = Pt(10.5)
    r = p.add_run(valor)
    r.font.name = "Arial"
    r.font.size = Pt(10.5)


def linea(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    ppr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    b = OxmlElement("w:bottom")
    b.set(qn("w:val"), "single")
    b.set(qn("w:sz"), "6")
    b.set(qn("w:color"), "BFBFBF")
    bdr.append(b)
    ppr.append(bdr)


def filas_tabla(datos):
    # la misma tabla la usan el word, el html y la pestaña de resultados
    if datos["tipo"] == "ranking":
        encabezado = [datos["dimension"], "Pérdida neta / saldo", "Over30 / saldo", "ROA neto"]
        filas = [[str(f["valor"]), pct(f["ncl_rate_pct"]), pct(f["over30_rate_pct"]), pct(f["net_roa_pct"])] for f in datos["filas"]]
    else:
        encabezado = ["Indicador"] + [g["etiqueta"] for g in datos["grupos"]]
        filas = [[nombre] + [fmt(g["m"][campo]) for g in datos["grupos"]] for nombre, campo, fmt in indicadores]
    return encabezado, filas


def tabla(doc, datos):
    encabezado, filas = filas_tabla(datos)

    t = doc.add_table(rows=1, cols=len(encabezado))
    for i, texto in enumerate(encabezado):
        r = t.rows[0].cells[i].paragraphs[0].add_run(str(texto))
        r.bold = True
        r.font.size = Pt(9.5)
        r.font.name = "Arial"
        borde(t.rows[0].cells[i], "404040", "8")
    for fila in filas:
        celdas = t.add_row().cells
        for i, texto in enumerate(fila):
            r = celdas[i].paragraphs[0].add_run(texto)
            r.font.size = Pt(9.5)
            r.font.name = "Arial"
            borde(celdas[i], "BFBFBF", "4")
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def poner_graficas(doc, graficas):
    for ruta, titulo in graficas:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(6)
        p.add_run().add_picture(str(ruta), width=Cm(15.5))
        pie = escribir(doc, titulo, tam=9, gris=True, justificar=False, despues=12)
        pie.alignment = WD_ALIGN_PARAGRAPH.CENTER


def crear_word(rep, datos, pregunta, ruta=None, fecha=None):
    doc = None
    for p in plantillas:
        try:
            doc = Document(str(p))
            break
        except Exception:
            print("no se pudo abrir", p)
    if doc is None:
        doc = Document()

    # google docs guarda medidas con decimales y python-docx no las lee
    for el in doc.element.iter():
        for k, v in el.attrib.items():
            if re.fullmatch(r"-?\d+\.\d+", v):
                el.set(k, str(round(float(v))))

    # damos mas margen arriba para que el logo del encabezado no tape las graficas
    for s in doc.sections:
        s.top_margin = Cm(4)

    dato(doc, "Para", "Comité de Crédito")
    dato(doc, "De", "Análisis de Riesgos, Portafolio de Tarjetas")
    dato(doc, "Fecha", fecha or datetime.now().strftime("%d/%m/%Y"))
    dato(doc, "Asunto", rep.asunto)
    linea(doc)

    escribir(doc, rep.titulo, negrita=True, tam=14, antes=10, despues=12, justificar=False, color="0E3A47")
    escribir(doc, rep.resumen)

    secciones = [s for s in rep.secciones if "recomend" not in s.titulo.lower()]
    if not secciones:
        tabla(doc, datos)
        poner_graficas(doc, datos.get("graficas", []))
    for i, s in enumerate(secciones):
        if s.titulo:
            escribir(doc, s.titulo, negrita=True, tam=12, antes=14, despues=6, justificar=False, color="0E3A47")
        for p in s.parrafos:
            escribir(doc, p)
        if i == 0:
            tabla(doc, datos)
            poner_graficas(doc, datos.get("graficas", []))

    escribir(doc, "Recomendación", negrita=True, tam=12, antes=14, despues=6, justificar=False, color="0E3A47")
    escribir(doc, rep.recomendacion)

    nota = f"Pregunta original  {pregunta.strip()}. Cifras del cubo base_cards_sintetica, {datos['periodo']}. Borrador sujeto a revisión. BankAgent {version}."
    escribir(doc, nota, tam=8.5, antes=20, gris=True)

    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = Path(ruta) if ruta else carpeta / f"reporte_{datetime.now():%Y%m%d_%H%M%S}.docx"
    doc.save(str(ruta))
    return ruta


# paso 6b la misma version en html para verla en la app antes de descargar

def logo_base64():
    # sacamos el logo de la plantilla para que el html se vea igual que el word
    try:
        doc = Document(str(plantillas[0]))
        for parte in doc.part.package.iter_parts():
            if parte.content_type.startswith("image/"):
                return parte.content_type, base64.b64encode(parte.blob).decode()
    except Exception as e:
        print("no se pudo sacar el logo", e)
    return None, None


def crear_html(rep, datos, pregunta, ruta_docx, fecha=None):
    # cada texto lleva data-campo para que el editor de la app sepa que campo se cambio
    e = html.escape
    tipo_logo, logo = logo_base64()
    partes = []
    if logo:
        partes.append(f'<img class="logo" src="data:{tipo_logo};base64,{logo}">')
    partes.append(
        f'<p class="dato"><b>Para</b> Comité de Crédito</p>'
        f'<p class="dato"><b>De</b> Análisis de Riesgos, Portafolio de Tarjetas</p>'
        f'<p class="dato"><b>Fecha</b> {fecha or datetime.now().strftime("%d/%m/%Y")}</p>'
        f'<p class="dato"><b>Asunto</b> <span data-campo="asunto">{e(rep.asunto)}</span></p><hr>'
    )
    partes.append(f'<h1 data-campo="titulo">{e(rep.titulo)}</h1><p data-campo="resumen">{e(rep.resumen)}</p>')

    encabezado, filas = filas_tabla(datos)
    tabla_html = "<table><tr>" + "".join(f"<th>{e(str(c))}</th>" for c in encabezado) + "</tr>"
    tabla_html += "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in fila) + "</tr>" for fila in filas) + "</table>"
    graficas_html = ""
    for ruta, titulo in datos.get("graficas", []):
        imagen = base64.b64encode(Path(ruta).read_bytes()).decode()
        graficas_html += (
            f'<div class="figura"><img src="data:image/png;base64,{imagen}" width="460">'
            f'<p class="pie">{e(titulo)}</p></div>'
        )

    # mismo orden que el word, la tabla y las graficas van despues de la primera seccion
    # guardamos el indice original de cada seccion para que el editor cambie la correcta
    secciones = [(i, s) for i, s in enumerate(rep.secciones) if "recomend" not in s.titulo.lower()]
    if not secciones:
        partes.append(tabla_html + graficas_html)
    for n, (i, s) in enumerate(secciones):
        if s.titulo:
            partes.append(f'<h2 data-campo="sec-{i}-titulo">{e(s.titulo)}</h2>')
        partes.extend(f'<p data-campo="sec-{i}-p-{j}">{e(p)}</p>' for j, p in enumerate(s.parrafos))
        if n == 0:
            partes.append(tabla_html + graficas_html)
    partes.append(f'<h2>Recomendación</h2><p data-campo="recomendacion">{e(rep.recomendacion)}</p>')
    partes.append(
        f'<p class="nota">Pregunta original  {e(pregunta.strip())}. Cifras del cubo base_cards_sintetica, '
        f'{e(datos["periodo"])}. Borrador sujeto a revisión. BankAgent {version}.</p>'
    )

    estilo_css = """
    body { font-family: Arial, sans-serif; color: #333; background: #fff; max-width: 800px; margin: 0 auto; padding: 32px; }
    .logo { height: 48px; margin-bottom: 24px; }
    .dato { margin: 2px 0; font-size: 14px; }
    hr { border: none; border-bottom: 1px solid #BFBFBF; margin: 12px 0 18px; }
    h1 { color: #0E3A47; font-size: 20px; }
    h2 { color: #0E3A47; font-size: 16px; margin-top: 22px; }
    p { text-align: justify; line-height: 1.5; font-size: 14px; }
    table { border-collapse: collapse; width: 100%; font-size: 12.5px; margin: 12px 0; }
    th { text-align: left; border-bottom: 1.5px solid #404040; padding: 4px 6px; }
    td { border-bottom: 1px solid #BFBFBF; padding: 4px 6px; }
    .figura { text-align: center; margin: 16px 0; }
    .figura img { max-width: 100%; height: auto; }
    .pie { color: #6B6B6B; font-size: 12px; text-align: center; }
    .nota { color: #6B6B6B; font-size: 11px; margin-top: 28px; }
    """
    contenido = (
        f'<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>{e(rep.asunto)}</title>'
        f"<style>{estilo_css}</style></head><body>{''.join(partes)}</body></html>"
    )
    ruta_html = Path(ruta_docx).with_suffix(".html")
    ruta_html.write_text(contenido, encoding="utf-8")
    return ruta_html


def crear_pdf(ruta_html):
    # el pdf sale del mismo html de la vista previa
    from xhtml2pdf import pisa

    ruta_pdf = Path(ruta_html).with_suffix(".pdf")
    with open(ruta_pdf, "wb") as salida:
        resultado = pisa.CreatePDF(Path(ruta_html).read_text(encoding="utf-8"), dest=salida, encoding="utf-8")
    if resultado.err:
        raise ValueError("No se pudo convertir el reporte a pdf")
    return ruta_pdf


def guardar_piezas(rep, datos, pregunta, ruta_docx, fecha):
    # guardamos el reporte por partes para poder editarlo y volver a armar el word, html y pdf
    sin_curvas = {k: v for k, v in datos.items() if k != "curvas"}
    sin_curvas["graficas"] = [[str(r), t] for r, t in datos.get("graficas", [])]
    piezas = {"rep": rep.model_dump(), "datos": sin_curvas, "pregunta": pregunta, "fecha": fecha}
    Path(ruta_docx).with_suffix(".json").write_text(json.dumps(piezas, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def armar_archivos(rep, datos, pregunta, ruta_docx, fecha):
    # word, html, pdf y piezas, todos con el mismo nombre
    crear_word(rep, datos, pregunta, ruta=ruta_docx, fecha=fecha)
    guardar_piezas(rep, datos, pregunta, ruta_docx, fecha)
    try:
        ruta_html = crear_html(rep, datos, pregunta, ruta_docx, fecha=fecha)
        crear_pdf(ruta_html)
    except Exception as e:
        print("no se pudo hacer el html o el pdf", e)


def editar_reporte(ruta_docx, cambios):
    # aplica lo que el usuario escribio en la vista previa y vuelve a armar los archivos
    ruta_docx = Path(ruta_docx)
    piezas = json.loads(ruta_docx.with_suffix(".json").read_text(encoding="utf-8"))
    rep = Reporte.model_construct(**piezas["rep"])
    rep.secciones = [Seccion.model_construct(**s) for s in piezas["rep"]["secciones"]]
    datos = piezas["datos"]

    for campo, texto in cambios.items():
        texto = re.sub(r"\s+", " ", str(texto)).strip()
        if campo in ["asunto", "titulo", "resumen", "recomendacion"]:
            setattr(rep, campo, texto)
            continue
        partes = re.fullmatch(r"sec-(\d+)-(titulo|p-(\d+))", campo)
        if not partes:
            continue
        i = int(partes.group(1))
        if i >= len(rep.secciones):
            continue
        if partes.group(2) == "titulo":
            rep.secciones[i].titulo = texto
        elif int(partes.group(3)) < len(rep.secciones[i].parrafos):
            rep.secciones[i].parrafos[int(partes.group(3))] = texto
    # si el usuario borro todo un parrafo lo quitamos
    for s in rep.secciones:
        s.parrafos = [p for p in s.parrafos if p]

    armar_archivos(rep, datos, piezas["pregunta"], ruta_docx, piezas.get("fecha"))
    # avisamos de cifras que no salen del cubo, pero se guarda igual porque decide el usuario
    return inventadas(rep, datos, piezas["pregunta"])


def generar(pregunta):
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.2, reasoning=False,
                     num_ctx=OLLAMA_NUM_CTX, num_predict=2500, repeat_penalty=1.15)

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    pet = interpretar(llm, pregunta, catalogo(con))
    # si la pregunta dice madura se fuerza MOB 6 o mas aunque qwen no lo haya marcado
    if re.search(r"madur", pregunta.lower()):
        pet.maduras = True
    # si el usuario pide grafica se pone aunque qwen diga que no
    if re.search(r"gr[aá]fic", pregunta.lower()) and pet.grafica == "ninguna":
        pet.grafica = "ambas"
    print("filtros", pet.tipo, pet.grafica, [(g.etiqueta, [(f.columna, f.valor) for f in g.filtros]) for g in pet.grupos])
    datos = consultar(con, pet)
    con.close()

    # todos los archivos del reporte llevan el mismo nombre base
    nombre = f"reporte_{datetime.now():%Y%m%d_%H%M%S}"
    ruta = carpeta / f"{nombre}.docx"
    datos["graficas"] = []
    if pet.grafica != "ninguna":
        try:
            datos["graficas"] = hacer_graficas(datos, pet.grafica, destino=carpeta, prefijo=f"{nombre}_")
        except Exception as e:
            print("no se pudo hacer la grafica", e)

    rep = None
    aviso = ""
    for intento in range(3):
        try:
            rep = redactar(llm, pregunta, datos, aviso)
        except Exception as e:
            print("qwen no termino el reporte, se intenta otra vez", str(e)[:150])
            aviso = "Tu respuesta anterior fue demasiado larga y no terminó. Sé breve, máximo 3 párrafos por sección."
            continue
        malas = inventadas(rep, datos, pregunta)
        if con_letra(rep):
            print("escribio cifras con letra, se intenta otra vez")
            aviso = "Escribiste cifras con letra. Escríbelas con dígitos, por ejemplo 7.59% o $353.1 millones."
            continue
        if malas:
            print("cifras que no salen del cubo", malas)
            aviso = "Antes usaste cifras que no existen (" + ", ".join(malas) + "), no las uses."
            continue
        break
    if rep is None:
        raise ValueError("Qwen no pudo escribir el reporte, intenta con una pregunta más corta")

    # junto al word guardamos el html de la vista previa, el pdf y las piezas para poder editarlo
    armar_archivos(rep, datos, pregunta, ruta, datetime.now().strftime("%d/%m/%Y"))
    print("listo", ruta)
    return ruta


# paso 7 graficas para el chat

def explicar_grafica(llm, pregunta, datos, titulos, extra=""):
    prompt = f"""Eres analista senior de riesgos del portafolio de tarjetas de Banamex.
Explica en un solo párrafo de 2 a 4 oraciones lo que muestran estas gráficas  {", ".join(titulos)}.
Regla principal, todas las cifras van con dígitos copiadas tal cual de abajo, por ejemplo 7.59%. Nunca escribas un número con letra.
Usa solo las cifras de abajo, no inventes ni recalcules. Las cantidades son pesos mexicanos.
Di cuál grupo está peor y si alguno pasa los límites de apetito, usa lo que dicen las cifras.
Escribe en prosa, sin viñetas, sin markdown y sin dos puntos.

Pregunta  {pregunta}

{cifras(datos)}
{extra}"""
    return llm.invoke(prompt).content.strip()


def grafica_chat(pregunta):
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.2, reasoning=False,
                     num_ctx=OLLAMA_NUM_CTX, num_predict=600, repeat_penalty=1.15)

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    pet = interpretar(llm, pregunta, catalogo(con))
    # si la pregunta dice madura se fuerza MOB 6 o mas aunque qwen no lo haya marcado
    if re.search(r"madur", pregunta.lower()):
        pet.maduras = True
    # en el chat siempre pidieron grafica, si qwen dice que ninguna ponemos las dos
    if pet.grafica == "ninguna":
        pet.grafica = "ambas"
    print("grafica chat", pet.tipo, pet.grafica, [(g.etiqueta, [(f.columna, f.valor) for f in g.filtros]) for g in pet.grupos])
    datos = consultar(con, pet)
    con.close()

    figuras = armar_figuras(datos, pet.grafica)
    titulos = [t for _, _, t in figuras]

    # revisamos que la explicacion no invente cifras igual que en el reporte
    validas = numeros(cifras(datos) + " " + pregunta + " 10 30 100")
    texto = ""
    aviso = ""
    for intento in range(2):
        texto = explicar_grafica(llm, pregunta, datos, titulos, aviso)
        malas = sorted(n for n in numeros(texto) if n not in validas and len(n.replace(".", "")) > 1)
        if not malas:
            break
        print("cifras que no salen del cubo en la grafica", malas)
        aviso = "Antes usaste cifras que no existen (" + ", ".join(malas) + "), no las uses."

    encabezado, filas = filas_tabla(datos)
    return {
        "texto": texto,
        "figuras": [fig.to_json() for _, fig, _ in figuras],
        "titulos": titulos,
        "tabla": {"encabezado": encabezado, "filas": filas},
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('uv run python reporte/generar.py "pregunta"')
    else:
        generar(" ".join(sys.argv[1:]))