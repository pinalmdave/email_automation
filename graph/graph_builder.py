"""
Builds and compiles the LangGraph StateGraph for the email pipeline.

Hub-and-spoke topology: every node returns to the supervisor, which
inspects state and routes to the next node (agent or tool).
"""

from langgraph.graph import END, StateGraph

from agents.analyze_and_reply_followup_agent import analyze_and_reply_followup
from agents.generate_resume_agent import generate_resume
from agents.supervisor_agent import supervisor
from tools.finalize_tool import finalize
from tools.render_and_draft_tool import render_and_draft
from tools.scan_followup_emails_tool import scan_followup_emails
from tools.scan_recruiter_emails_tool import scan_recruiter_emails
from graph.state import EmailPipelineState


def _supervisor_router(state: EmailPipelineState) -> str:
    """Read the supervisor's routing decision from state."""
    return state.get("next_agent", "finalize_tool")


def build_graph() -> StateGraph:
    """Construct the email pipeline graph (uncompiled)."""
    graph = StateGraph(EmailPipelineState)

    # -- Add nodes: agents (call LLM) --
    graph.add_node("supervisor_agent", supervisor)
    graph.add_node("generate_resume_agent", generate_resume)
    graph.add_node("analyze_and_reply_followup_agent", analyze_and_reply_followup)

    # -- Add nodes: tools (no LLM) --
    graph.add_node("scan_recruiter_emails_tool", scan_recruiter_emails)
    graph.add_node("render_and_draft_tool", render_and_draft)
    graph.add_node("scan_followup_emails_tool", scan_followup_emails)
    graph.add_node("finalize_tool", finalize)

    # -- Entry point: always start at the supervisor --
    graph.set_entry_point("supervisor_agent")

    # -- Supervisor routes to any node --
    graph.add_conditional_edges("supervisor_agent", _supervisor_router)

    # -- Every agent/tool returns to the supervisor --
    for node_name in [
        "scan_recruiter_emails_tool",
        "generate_resume_agent",
        "render_and_draft_tool",
        "scan_followup_emails_tool",
        "analyze_and_reply_followup_agent",
    ]:
        graph.add_edge(node_name, "supervisor_agent")

    # -- Finalize terminates the graph --
    graph.add_edge("finalize_tool", END)

    return graph


def compile_graph():
    """Build and compile the graph, ready for .invoke()."""
    return build_graph().compile()
