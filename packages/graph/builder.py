"""Compile the MediShield document-processing state graph."""

from langgraph.graph import END, START, StateGraph

from packages.core.enums import AgentStatus
from packages.graph.nodes import GraphRuntime, build_nodes
from packages.graph.routing import classification_needs_review
from packages.graph.state import GraphState
from packages.graph.wrapper import InfrastructureFailure


def build_graph(runtime: GraphRuntime):
    raw_nodes = build_nodes(runtime)

    def guarded(name: str):
        def run(state: GraphState):
            try:
                return raw_nodes[name](state)
            except InfrastructureFailure as error:
                return {"infrastructure_error": f"{name}: {type(error).__name__}"}

        return run

    nodes = {name: guarded(name) for name in raw_nodes}
    graph = StateGraph(GraphState)
    for name in (
        "load_document",
        "classify",
        "ocr",
        "route_specialists",
        "kyc",
        "claims",
        "policy",
        "join",
        "fraud",
        "orchestrator",
        "aggregate",
        "mark_needs_review",
        "mark_failed",
    ):
        graph.add_node(name, nodes[name])

    graph.add_edge(START, "load_document")
    graph.add_conditional_edges(
        "load_document",
        lambda state: "mark_failed" if state.get("infrastructure_error") else "classify",
        {"mark_failed": "mark_failed", "classify": "classify"},
    )
    graph.add_conditional_edges(
        "classify",
        lambda state: (
            "mark_failed"
            if state.get("infrastructure_error")
            else "mark_needs_review"
            if state["classification"].status == AgentStatus.ERROR
            or classification_needs_review(
                state["classification"].doc_type, state["classification"].routing_tags
            )
            else "ocr"
        ),
        {"mark_failed": "mark_failed", "mark_needs_review": "mark_needs_review", "ocr": "ocr"},
    )
    graph.add_conditional_edges(
        "ocr",
        lambda state: (
            "mark_failed"
            if state.get("infrastructure_error")
            else "mark_needs_review"
            if state["ocr"].status == AgentStatus.ERROR
            else "route_specialists"
        ),
        {
            "mark_failed": "mark_failed",
            "mark_needs_review": "mark_needs_review",
            "route_specialists": "route_specialists",
        },
    )
    graph.add_edge("route_specialists", "kyc")
    graph.add_edge("route_specialists", "claims")
    graph.add_edge("claims", "policy")
    graph.add_edge(["kyc", "policy"], "join")
    graph.add_conditional_edges(
        "join",
        lambda state: "mark_failed" if state.get("infrastructure_error") else "fraud",
        {"mark_failed": "mark_failed", "fraud": "fraud"},
    )
    graph.add_conditional_edges(
        "fraud",
        lambda state: "mark_failed" if state.get("infrastructure_error") else "orchestrator",
        {"mark_failed": "mark_failed", "orchestrator": "orchestrator"},
    )
    graph.add_conditional_edges(
        "orchestrator",
        lambda state: "mark_failed" if state.get("infrastructure_error") else "aggregate",
        {"mark_failed": "mark_failed", "aggregate": "aggregate"},
    )
    graph.add_edge("aggregate", END)
    graph.add_edge("mark_needs_review", END)
    graph.add_edge("mark_failed", END)
    return graph.compile()


def initial_state(case_id: str, pipeline_run: str) -> GraphState:
    return {"case_id": case_id, "pipeline_run": pipeline_run, "errors": [], "audit": []}
