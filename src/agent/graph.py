"""Orquestación del agente en LangGraph con los 5 guardrails, telemetría y Human-in-the-Loop."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from src.agent.guardrails import verify_response_numbers
from src.agent.prompts import SYSTEM_PROMPT
from src.config import (
    AGENT_MAX_TURNS,
    CHECKPOINTS_DB_PATH,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_REASONING,
    OLLAMA_TEMPERATURE,
    OLLAMA_TOP_K,
    OLLAMA_TOP_P,
    STATE_DIR,
)
from src.skills.cubo_sql_tools import (
    ejecutar_sql_select_seguro,
    obtener_curva_maduracion,
    obtener_resumen_portafolio,
)
from src.skills.rag_tools import consultar_politica_riesgo
from src.skills.report_tools import compilar_entregables_ejecutivos
from src.skills.viz_tools import generar_grafica_portafolio

TOOLS = [
    obtener_resumen_portafolio,
    obtener_curva_maduracion,
    ejecutar_sql_select_seguro,
    consultar_politica_riesgo,
    generar_grafica_portafolio,
    compilar_entregables_ejecutivos,
]

# Guardrail 1: Lista blanca explícita de herramientas (nunca eval ni getattr)
TOOL_MAP = {t.name: t for t in TOOLS}


class AgentState(TypedDict):
    """Estado compartido a lo largo del grafo de LangGraph."""

    messages: Annotated[list[AnyMessage], add_messages]
    case_id: str
    sql_queries: list[str]
    evidence: list[Any]
    draft_dictamen: str
    guardrail_passed: bool
    guardrail_issues: list[str]
    retry_count: int
    turn_count: int
    seen_calls: list[str]
    token_usage: dict[str, Any]


def make_initial_state(prompt: str, case_id: str = "CASO-2026-0001") -> AgentState:
    """Construye el estado inicial limpio para invocar el grafo."""
    return {
        "messages": [HumanMessage(content=prompt)],
        "case_id": case_id,
        "sql_queries": [],
        "evidence": [],
        "draft_dictamen": "",
        "guardrail_passed": True,
        "guardrail_issues": [],
        "retry_count": 0,
        "turn_count": 0,
        "seen_calls": [],
        "token_usage": {
            "prompt_eval_count": 0,
            "eval_count": 0,
            "total_calls": 0,
            "last_latency_s": 0.0,
            "num_ctx": OLLAMA_NUM_CTX,
        },
    }


def _get_llm_with_tools():
    kwargs: dict[str, Any] = {
        "base_url": OLLAMA_BASE_URL,
        "model": OLLAMA_MODEL,
        "temperature": OLLAMA_TEMPERATURE,
        "reasoning": OLLAMA_REASONING,
        "num_ctx": OLLAMA_NUM_CTX,
    }
    if OLLAMA_TOP_K is not None:
        kwargs["top_k"] = OLLAMA_TOP_K
    if OLLAMA_TOP_P is not None:
        kwargs["top_p"] = OLLAMA_TOP_P
    return ChatOllama(**kwargs).bind_tools(TOOLS)


def _extract_token_usage(
    response: AIMessage,
    prev_usage: dict[str, Any],
    latency_s: float,
) -> dict[str, Any]:
    """Extrae contadores reales de tokens de Ollama para vigilar la ventana de contexto."""
    meta = getattr(response, "response_metadata", None) or {}
    usage = getattr(response, "usage_metadata", None) or {}
    prompt_tokens = meta.get("prompt_eval_count") or usage.get("input_tokens") or 0
    gen_tokens = meta.get("eval_count") or usage.get("output_tokens") or 0
    return {
        "prompt_eval_count": int(prompt_tokens),
        "eval_count": int(gen_tokens),
        "total_calls": int(prev_usage.get("total_calls", 0)) + 1,
        "last_latency_s": round(latency_s, 2),
        "num_ctx": OLLAMA_NUM_CTX,
    }


def _agent_node(state: AgentState) -> dict[str, Any]:
    llm_tools = _get_llm_with_tools()
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    t0 = time.perf_counter()
    response = llm_tools.invoke(messages)
    elapsed = time.perf_counter() - t0
    token_usage = _extract_token_usage(response, state.get("token_usage", {}), elapsed)
    return {
        "messages": [response],
        "turn_count": state.get("turn_count", 0) + 1,
        "token_usage": token_usage,
    }


def _route_after_agent(state: AgentState) -> str:
    last_msg = state["messages"][-1]
    # Guardrail 2: Tope explícito de vueltas para evitar bucles infinitos
    if state.get("turn_count", 0) >= AGENT_MAX_TURNS:
        return "guardrail"
    if isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None):
        return "tools"
    return "guardrail"


def _tools_node(state: AgentState) -> dict[str, Any]:
    """Ejecuta tool_calls con Guardrail 1 (lista blanca), 3 (antirrepetición) y 4 (validación)."""
    last_msg = state["messages"][-1]
    tool_calls = getattr(last_msg, "tool_calls", None) or []
    seen = list(state.get("seen_calls", []))
    out_messages: list[ToolMessage] = []

    for call in tool_calls:
        name = call.get("name", "")
        args = call.get("args", {})
        call_id = call.get("id", f"call_{len(seen)}")

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                out_messages.append(
                    ToolMessage(
                        tool_call_id=call_id,
                        name=name,
                        content=json.dumps({"error": f"Unparseable JSON arguments: {args!r}"}),
                    )
                )
                continue

        signature = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"

        # Guardrail 1: Lista blanca
        if name not in TOOL_MAP:
            payload = json.dumps(
                {
                    "error": f"Tool '{name}' does not exist.",
                    "disponibles": sorted(TOOL_MAP.keys()),
                },
                ensure_ascii=False,
            )
        # Guardrail 3: Antirrepetición (evita ciclos idénticos)
        elif signature in seen:
            payload = json.dumps(
                {
                    "error": (
                        f"You already executed `{name}` with identical arguments. "
                        "Use the result already in context or change the arguments."
                    )
                },
                ensure_ascii=False,
            )
        else:
            seen.append(signature)
            try:
                result = TOOL_MAP[name].invoke(args)
                payload = (
                    result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                )
            except Exception as exc:  # noqa: BLE001
                # Guardrail 4: Errores de validación / ejecución regresan como datos, no crashes
                payload = json.dumps(
                    {"error": f"Invalid arguments or execution error in `{name}`: {exc}"},
                    ensure_ascii=False,
                )

        out_messages.append(ToolMessage(tool_call_id=call_id, name=name, content=payload))

    return {"messages": out_messages, "seen_calls": seen}


def _guardrail_node(state: AgentState) -> dict[str, Any]:
    tool_evidence: list[Any] = []
    sql_queries: list[str] = []

    for msg in state["messages"]:
        if isinstance(msg, ToolMessage):
            tool_evidence.append(msg.content)
            try:
                parsed = json.loads(str(msg.content))
                if isinstance(parsed, dict) and "sql_ejecutado" in parsed:
                    sql_queries.append(parsed["sql_ejecutado"])
            except json.JSONDecodeError:
                pass

    last_ai = next(
        (m for m in reversed(state["messages"]) if isinstance(m, AIMessage)),
        None,
    )
    draft = str(last_ai.content).strip() if last_ai else ""
    if not draft and state.get("turn_count", 0) >= AGENT_MAX_TURNS:
        draft = (
            f"Se alcanzó el límite máximo de {AGENT_MAX_TURNS} vueltas sin respuesta final. "
            "Revisa la evidencia en las herramientas o reformula la consulta."
        )

    passed, issues = verify_response_numbers(draft, tool_evidence)

    retry_count = state.get("retry_count", 0)
    if not passed and retry_count < 1 and state.get("turn_count", 0) < AGENT_MAX_TURNS:
        correction = HumanMessage(
            content=(
                "GUARDRAIL: Some numbers in your response do not match tool outputs "
                f"({', '.join(issues)}). Rewrite your Spanish response citing ONLY exact "
                "figures returned by DuckDB tools."
            )
        )
        return {
            "messages": [correction],
            "sql_queries": sql_queries,
            "evidence": tool_evidence,
            "guardrail_passed": False,
            "guardrail_issues": issues,
            "retry_count": retry_count + 1,
        }

    return {
        "sql_queries": sql_queries,
        "evidence": tool_evidence,
        "draft_dictamen": draft,
        "guardrail_passed": passed,
        "guardrail_issues": issues,
    }


def _route_after_guardrail(state: AgentState) -> str:
    if not state.get("guardrail_passed", True) and state.get("retry_count", 0) <= 1:
        last_msg = state["messages"][-1]
        if isinstance(last_msg, HumanMessage) and str(last_msg.content).startswith("GUARDRAIL:"):
            return "agent"
    return "human_review"


def _human_review_node(state: AgentState) -> dict[str, Any]:
    """Guardrail 5: Punto de control para revisión/aprobación humana en Streamlit."""
    return {}


def build_agent_graph(with_interrupt: bool = True):
    """Compila el StateGraph de LangGraph con persistencia SqliteSaver."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CHECKPOINTS_DB_PATH), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    builder = StateGraph(AgentState)
    builder.add_node("agent", _agent_node)
    builder.add_node("tools", _tools_node)
    builder.add_node("guardrail", _guardrail_node)
    builder.add_node("human_review", _human_review_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        _route_after_agent,
        {"tools": "tools", "guardrail": "guardrail"},
    )
    builder.add_edge("tools", "agent")
    builder.add_conditional_edges(
        "guardrail",
        _route_after_guardrail,
        {"agent": "agent", "human_review": "human_review"},
    )
    builder.add_edge("human_review", END)

    interrupts = ["human_review"] if with_interrupt else []
    return builder.compile(checkpointer=checkpointer, interrupt_before=interrupts)
