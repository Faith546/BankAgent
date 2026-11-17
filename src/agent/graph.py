"""Orquestación del agente en LangGraph con Tools, Guardrail y pausa Human-in-the-Loop."""

from __future__ import annotations

import json
import sqlite3
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from src.agent.guardrails import verify_response_numbers
from src.agent.prompts import SYSTEM_PROMPT
from src.config import (
    CHECKPOINTS_DB_PATH,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_TEMPERATURE,
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


def _get_llm_with_tools():
    llm = ChatOllama(
        base_url=OLLAMA_BASE_URL,
        model=OLLAMA_MODEL,
        temperature=OLLAMA_TEMPERATURE,
        num_ctx=OLLAMA_NUM_CTX,
    )
    return llm.bind_tools(TOOLS)


def _agent_node(state: AgentState) -> dict[str, Any]:
    llm_tools = _get_llm_with_tools()
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    response = llm_tools.invoke(messages)
    return {"messages": [response]}


def _route_after_agent(state: AgentState) -> str:
    last_msg = state["messages"][-1]
    if isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None):
        return "tools"
    return "guardrail"


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
    draft = str(last_ai.content) if last_ai else ""
    passed, issues = verify_response_numbers(draft, tool_evidence)

    retry_count = state.get("retry_count", 0)
    if not passed and retry_count < 1:
        correction = HumanMessage(
            content=(
                "GUARDRAIL: Detecté cifras en tu respuesta que no coinciden con la salida de "
                f"tus herramientas ({', '.join(issues)}). Corrige tu respuesta citando "
                "únicamente números exactos devueltos por DuckDB."
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
    """Nodo de punto de control para revisión/aprobación humana en Streamlit."""
    return {}


def build_agent_graph(with_interrupt: bool = True):
    """Compila el StateGraph de LangGraph con persistencia SqliteSaver."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CHECKPOINTS_DB_PATH), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    builder = StateGraph(AgentState)
    builder.add_node("agent", _agent_node)
    builder.add_node("tools", ToolNode(TOOLS))
    builder.add_node("guardrail", _guardrail_node)
    builder.add_node("human_review", _human_review_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", _route_after_agent, {"tools": "tools", "guardrail": "guardrail"})
    builder.add_edge("tools", "agent")
    builder.add_conditional_edges(
        "guardrail",
        _route_after_guardrail,
        {"agent": "agent", "human_review": "human_review"},
    )
    builder.add_edge("human_review", END)

    interrupts = ["human_review"] if with_interrupt else []
    return builder.compile(checkpointer=checkpointer, interrupt_before=interrupts)
