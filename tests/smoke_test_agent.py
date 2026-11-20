"""Smoke test (4 pruebas de efecto) y Benchmark del Golden Dataset para BankAgent.

Uso:
    uv run python -m tests.smoke_test_agent
    uv run python -m tests.smoke_test_agent --benchmark
    uv run python -m tests.smoke_test_agent --benchmark --limit 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama

from src.agent.graph import TOOLS, build_agent_graph, make_initial_state
from src.agent.prompts import SYSTEM_PROMPT
from src.config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_REASONING,
    OLLAMA_TEMPERATURE,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOLDEN_PATH = Path(__file__).resolve().parent / "golden_dataset.json"


def run_smoke_4_checks(model: str) -> int:
    """Ejecuta las 4 pruebas de efecto (adaptadas de agents_intro/scripts/smoke_test_tools.py)."""
    print(f"Ollama    : {OLLAMA_BASE_URL}")
    print(
        f"Modelo    : {model} "
        f"(temp={OLLAMA_TEMPERATURE}, reasoning={OLLAMA_REASONING}, ctx={OLLAMA_NUM_CTX})"
    )
    print("-" * 72)

    llm_raw = ChatOllama(
        base_url=OLLAMA_BASE_URL,
        model=model,
        temperature=OLLAMA_TEMPERATURE,
        reasoning=OLLAMA_REASONING,
        num_ctx=OLLAMA_NUM_CTX,
    )
    llm_tools = llm_raw.bind_tools(TOOLS)
    fallas: list[str] = []

    # [1/4] Responde texto no vacío (no se queda atrapado pensando)
    print("[1/4] ¿Produce respuesta no vacía con reasoning=False?")
    t0 = time.perf_counter()
    r1 = llm_raw.invoke([HumanMessage(content="Di 'listo' y nada más.")])
    dt1 = time.perf_counter() - t0
    txt1 = str(r1.content).strip()
    print(f"      respuesta : {txt1[:80]!r} ({dt1:.2f}s)")
    if not txt1:
        print("      FALLA — respuesta vacía (posible modo thinking sin apagar).")
        fallas.append("respuesta vacía")
    else:
        print("      OK")

    # [2/4] Pide tool con argumentos bien formados cuando se solicitan datos del cubo
    print("\n[2/4] ¿Pide la tool correcta con argumentos válidos?")
    q2 = "¿Cuál es el resumen del portafolio para el canal Aeropuerto y producto Clasica?"
    t0 = time.perf_counter()
    r2 = llm_tools.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=q2)])
    dt2 = time.perf_counter() - t0
    calls2 = getattr(r2, "tool_calls", None) or []
    print(f"      tool_calls: {calls2} ({dt2:.2f}s)")
    if not calls2:
        print(f"      FALLA — no pidió tool. Respondió: {str(r2.content)[:120]!r}")
        fallas.append("no emite tool_calls")
    else:
        first = calls2[0]
        if first.get("name") not in {"obtener_resumen_portafolio", "ejecutar_sql_select_seguro"}:
            print(f"      FALLA — tool inesperada: {first.get('name')}")
            fallas.append("tool inesperada")
        else:
            print("      OK")

    # [3/4] Cita el dato real devuelto por la tool (verifica por efecto, no por texto exacto)
    print("\n[3/4] ¿Cita la cifra exacta devuelta por DuckDB en lugar de inventar?")
    if not calls2:
        print("      SALTADO (sin tool_call en [2/4])")
    else:
        fake_tool_id = calls2[0].get("id", "smoke_1")
        fake_result = json.dumps({"cuentas_iniciales_mob0": 28152, "ncl_rate_pct": 8.56})
        t0 = time.perf_counter()
        r3 = llm_tools.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=q2),
                r2,
                ToolMessage(
                    content=fake_result, tool_call_id=fake_tool_id, name=calls2[0]["name"]
                ),
            ]
        )
        dt3 = time.perf_counter() - t0
        txt3 = str(r3.content).strip()
        print(f"      respuesta : {txt3[:160]!r} ({dt3:.2f}s)")
        if "8.56" in txt3 and ("28,152" in txt3 or "28152" in txt3):
            print("      OK — citó las cifras exactas.")
        else:
            print("      FALLA — no citó 8.56 y 28,152.")
            fallas.append("ignora resultado de tool")

    # [4/4] Se abstiene de llamar tools ante un saludo simple
    print("\n[4/4] ¿Se abstiene de llamar tools en un saludo simple?")
    t0 = time.perf_counter()
    r4 = llm_tools.invoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content="Hola, ¿cómo estás?")]
    )
    dt4 = time.perf_counter() - t0
    calls4 = getattr(r4, "tool_calls", None) or []
    print(f"      tool_calls: {len(calls4)} | texto: {str(r4.content)[:80]!r} ({dt4:.2f}s)")
    if calls4:
        print("      FALLA — llamó tool para un saludo.")
        fallas.append("llama tools sin necesidad")
    else:
        print("      OK")

    print("\n" + "=" * 72)
    if fallas:
        print(f"RESULTADO SMOKE TEST: {len(fallas)} falla(s) -> {', '.join(fallas)}")
        return 1
    print(f"RESULTADO SMOKE TEST: 4/4 OK. '{model}' listo para BankAgent.")
    print("=" * 72)
    return 0


def run_golden_benchmark(limit: int | None = None) -> int:
    """Evalúa el grafo completo contra el Golden Dataset (verificación por efecto)."""
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    if limit is not None:
        cases = cases[:limit]

    graph = build_agent_graph(with_interrupt=False)
    passed_count = 0

    print(f"\nEJECUTANDO BENCHMARK GOLDEN DATASET ({len(cases)} casos) | Modelo: {OLLAMA_MODEL}")
    print("=" * 72)

    for case in cases:
        cid = case["id"]
        t0 = time.perf_counter()
        res = graph.invoke(
            make_initial_state(prompt=case["pregunta"], case_id=f"BENCH-{cid}"),
            config={"configurable": {"thread_id": f"bench-{cid}-{int(t0)}"}},
        )
        elapsed = time.perf_counter() - t0
        answer = res.get("draft_dictamen", "")
        tu = res.get("token_usage", {})
        guardrail_ok = res.get("guardrail_passed", True)

        # Verifica si al menos una cifra esperada o palabra clave aparece en la respuesta
        hits = [kw for kw in case["palabras_clave_esperadas"] if kw.lower() in answer.lower()]
        ok = len(hits) > 0 and guardrail_ok
        if ok:
            passed_count += 1

        status = "PASS" if ok else "FAIL"
        print(
            f"[{status}] {cid} (N{case['nivel']}) | {elapsed:.1f}s | "
            f"ctx={tu.get('prompt_eval_count', 0)}/{tu.get('num_ctx', OLLAMA_NUM_CTX)} | "
            f"calls={tu.get('total_calls', 0)} | guardrail={guardrail_ok} | hits={hits}"
        )
        if not ok:
            print(f"       Respuesta: {answer[:180]!r}")

    print("=" * 72)
    pct = (passed_count / len(cases)) * 100
    print(f"SCORE FINAL BENCHMARK: {passed_count}/{len(cases)} ({pct:.1f}%)")
    return 0 if passed_count == len(cases) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test y benchmark de BankAgent.")
    parser.add_argument("--modelo", default=OLLAMA_MODEL, help="Nombre del modelo en Ollama.")
    parser.add_argument(
        "--benchmark", action="store_true", help="Ejecuta el Golden Dataset completo."
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limita el número de casos del benchmark."
    )
    args = parser.parse_args()

    rc = run_smoke_4_checks(args.modelo)
    if args.benchmark:
        rc_bench = run_golden_benchmark(limit=args.limit)
        return max(rc, rc_bench)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
