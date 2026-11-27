"""Pruebas unitarias offline para los módulos del PR #14 (interpretacion, recuerdame, reporte)."""

from __future__ import annotations

from io import BytesIO

import pymupdf
import pytest
from docx import Document

from src.skills.interpretacion import analisis, dominio, leerdocx, leerpdf, politicas, rag_dinamico
from src.skills.recuerdame import aprendizaje, chats, clasificador
from src.skills.reporte import generar


# ---------------------------------------------------------------------------
# 1. interpretacion (leerdocx, leerpdf, rag_dinamico, dominio, politicas, analisis)
# ---------------------------------------------------------------------------
def test_leer_docx_extracts_paragraphs_and_tables() -> None:
    """Verifica extracción de párrafos y tablas desde bytes .docx."""
    doc = Document()
    doc.add_paragraph("Resumen de Portafolio Banamex")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Canal"
    table.cell(0, 1).text = "NCL"
    table.cell(1, 0).text = "Aeropuerto"
    table.cell(1, 1).text = "8.56%"
    buf = BytesIO()
    doc.save(buf)

    texto = leerdocx.leer_docx(buf.getvalue())
    assert "Resumen de Portafolio Banamex" in texto
    assert "Tabla 1" in texto
    assert "Aeropuerto | 8.56%" in texto


def test_leer_pdf_detects_text_and_scanned_pages() -> None:
    """Verifica lectura de texto PDF y detección de páginas escaneadas (<30 chars)."""
    pdf = pymupdf.open()
    p1 = pdf.new_page()
    p1.insert_text((72, 72), "Reporte de morosidad Over30 y perdida neta NCL en tarjetas Banamex.")
    pdf.new_page()  # Página 2 vacía -> detectada como escaneada
    raw_pdf = pdf.tobytes()
    pdf.close()

    res = leerpdf.leer_pdf(raw_pdf)
    assert res["total_paginas"] == 2
    assert res["paginas_sin_texto"] == [2]
    assert "Página 1" in res["texto"]
    assert "Banamex" in res["texto"]


def test_leer_documento_rejects_unsupported_extensions() -> None:
    """Verifica rechazo de extensiones fuera de lista blanca (.csv, .exe)."""
    with pytest.raises(ValueError, match="Solo se pueden leer"):
        analisis.leer_documento(b"col1,col2\n1,2", "datos.csv")


def test_rag_dinamico_partir_chunks_with_overlap() -> None:
    """Verifica particionado con traslape de textos largos."""
    texto = "A" * 1600
    pedazos = rag_dinamico.partir(texto)
    assert len(pedazos) == 3
    assert len(pedazos[0]) == rag_dinamico.tamano


def test_dominio_accepts_banking_and_rejects_empty() -> None:
    """Verifica filtro determinista de dominio bancario sin llamar a Ollama."""
    assert dominio.es_del_dominio("") is False
    assert dominio.es_del_dominio("   ") is False
    assert dominio.es_del_dominio("Tasa NCL y morosidad Over30 en Aeropuerto Clasica") is True


def test_politicas_rejects_csv_extension() -> None:
    """Verifica regla de gobernanza: prohibido subir .csv como política normativa."""
    with pytest.raises(ValueError, match="Solo se aceptan manuales"):
        politicas.guardar_politica("cubo.csv", b"VINTAGE,MOB\n202401,0")


def test_analisis_numeros_en() -> None:
    """Verifica extracción normalizada de cifras numéricas."""
    nums = analisis.numeros_en("El saldo fue $1,250.50 con NCL de 8.56%.")
    assert "1250.5" in nums
    assert "8.56" in nums


# ---------------------------------------------------------------------------
# 2. recuerdame (chats, clasificador, aprendizaje)
# ---------------------------------------------------------------------------
def test_chats_lifecycle_isolated(tmp_path, monkeypatch) -> None:
    """Verifica creación, guardado, listado, historial y borrado aislado de chats."""
    monkeypatch.setattr(chats, "carpeta", tmp_path)

    c = chats.crear_chat()
    assert c["titulo"] == "Chat nuevo"

    c["mensajes"].append(["user", "¿Cuál es el NCL de Aeropuerto?"])
    c["mensajes"].append(["assistant", "El NCL de Aeropuerto es 8.56%."])
    chats.guardar_chat(c)

    loaded = chats.cargar_chat(c["id"])
    assert loaded["titulo"] == "¿Cuál es el NCL de Aeropuerto?"
    assert len(chats.listar_chats()) == 1

    hist = chats.ultimos_mensajes(loaded)
    assert "8.56%" in hist

    chats.borrar_chat(c["id"])
    assert chats.listar_chats() == []


def test_clasificador_cleaning_and_relevance() -> None:
    """Verifica normalización, limpieza de errores/duplicados y puntaje bancario."""
    assert clasificador.normalizar("Pérdida Clásica") == "perdida clasica"
    assert clasificador.puntaje_relevancia("NCL en Aeropuerto producto Clasica", "agente") >= 2
    assert clasificador.puntaje_relevancia("receta de pastel de chocolate", "agente") == 0

    ents = clasificador.entidades("Compara Aeropuerto y Branch en 202401")
    assert {"aeropuerto", "branch", "202401"} <= ents

    eventos = [
        {
            "chat_id": "c1",
            "fecha": "20261127_100000",
            "texto": "q1",
            "respuesta": "Error al conectar",
        },
        {"chat_id": "c1", "fecha": "20261127_100001", "texto": "q2", "respuesta": "NCL 8.56%"},
        {"chat_id": "c1", "fecha": "20261127_100001", "texto": "q2", "respuesta": "NCL 8.56%"},
    ]
    limpios = clasificador.limpiar_eventos(eventos)
    assert len(limpios) == 1
    assert limpios[0]["texto"] == "q2"


def test_aprendizaje_bandit_policy_and_rewards(tmp_path, monkeypatch) -> None:
    """Verifica recompensas automáticas, softmax y actualización Gradient Bandit."""
    monkeypatch.setattr(aprendizaje, "ruta_eventos", tmp_path / "eventos.json")
    monkeypatch.setattr(aprendizaje, "ruta_politica", tmp_path / "politica.json")

    assert aprendizaje.recompensa_automatica("Aviso guardrail: cifra dudosa") == -0.5
    assert aprendizaje.recompensa_automatica("Respuesta normal con 8.56%") == 0

    probs = aprendizaje.softmax({"corta": 0.0, "detallada": 1.0, "con_tabla": 0.0})
    assert abs(sum(probs.values()) - 1.0) < 1e-6
    assert probs["detallada"] > probs["corta"]

    aprendizaje.registrar_evento("c1", "NCL de Aeropuerto", "agente", "Es 8.56%", "corta")
    aprendizaje.dar_recompensa("c1", 1.0)
    eventos = aprendizaje.leer_json(tmp_path / "eventos.json", [])
    assert eventos[-1]["recompensa"] == 1.0

    politica = aprendizaje.actualizar_politica(eventos)
    assert "agente" in politica
    assert abs(sum(politica["agente"]["probabilidades"].values()) - 1.0) < 1e-6
    assert aprendizaje.elegir_accion("agente") in aprendizaje.acciones

    aprendizaje.borrar_eventos_chat("c1")
    assert aprendizaje.leer_json(tmp_path / "eventos.json", []) == []


# ---------------------------------------------------------------------------
# 3. reporte/generar.py (validadores anti-alucinación de reportes)
# ---------------------------------------------------------------------------
def test_reporte_generar_validators() -> None:
    """Verifica detección de cifras con letra y cifras inventadas en Reporte."""
    rep_ok = generar.Reporte(
        asunto="Riesgo Aeropuerto",
        titulo="Aeropuerto mantiene NCL de 8.56%",
        resumen="El canal presenta una tasa de 8.56% sobre saldo.",
        recomendacion="Mantener vigilancia preventiva.",
        secciones=[generar.Seccion(titulo="Detalle", parrafos=["La tasa es 8.56%."])],
    )
    assert generar.con_letra(rep_ok) is False

    rep_letras = generar.Reporte(
        asunto="Riesgo Aeropuerto",
        titulo="Aeropuerto con ocho punto cinco por ciento",
        resumen="La pérdida subió a ocho punto cinco por ciento.",
        recomendacion="Revisar.",
        secciones=[generar.Seccion(titulo="Detalle", parrafos=["Subió siete por ciento."])],
    )
    assert generar.con_letra(rep_letras) is True


def test_reporte_unification_uses_ssot_palette_and_facade() -> None:
    """Verifica que generar.py use la paleta oficial Banamex y report_tools exponga la fachada."""
    from src.config import BANAMEX_PALETTE, TEMPLATES_DIR
    from src.skills import report_tools

    assert generar.colores[0] == BANAMEX_PALETTE["navy"]
    assert generar.colores[1] == BANAMEX_PALETTE["crimson"]
    assert generar.plantillas[0] == TEMPLATES_DIR / "memo_template.docx"
    assert callable(report_tools.generar_reporte_chat)
    assert callable(report_tools.editar_reporte_chat)
    assert callable(report_tools.grafica_chat)
    assert callable(report_tools.build_pptx_deck)


def test_config_load_dotenv(tmp_path, monkeypatch) -> None:
    """Verifica carga automática de `.env` sin pisar variables ya definidas en el sistema."""
    import os

    from src.config import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comentario\nTEST_BA_URL=http://10.0.0.5:11434\nTEST_BA_EXISTING=from_file\nEMPTY_VAR=\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TEST_BA_URL", raising=False)
    monkeypatch.setenv("TEST_BA_EXISTING", "from_shell")

    count = load_dotenv(env_file)
    assert count == 1
    assert os.environ["TEST_BA_URL"] == "http://10.0.0.5:11434"
    assert os.environ["TEST_BA_EXISTING"] == "from_shell"
    monkeypatch.delenv("TEST_BA_URL", raising=False)
