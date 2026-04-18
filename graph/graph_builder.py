"""
Builds and compiles the LangGraph StateGraph for the email pipeline.

Hub-and-spoke topology: every node returns to the supervisor, which
inspects state and routes to the next node.

Nodes are classified as:
  - Agent nodes (_agent): use an LLM to reason / generate content
  - Plain nodes (_node):  deterministic logic, no LLM calls
"""

from langgraph.graph import END, StateGraph

from agents.analyze_and_reply_followup_agent import analyze_and_reply_followup
from agents.evaluate_resume_agent import evaluate_resume
from agents.finalize_node import finalize
from agents.generate_resume_agent import generate_resume
from agents.process_job_description_node import process_job_description
from agents.render_and_draft_node import render_and_draft
from agents.scan_followup_emails_node import scan_followup_emails
from agents.scan_recruiter_emails_node import scan_recruiter_emails
from agents.supervisor_agent import supervisor
from graph.state import EmailPipelineState


def _supervisor_router(state: EmailPipelineState) -> str:
    """Read the supervisor's routing decision from state."""
    return state.get("next_node", "finalize_node")


def build_graph() -> StateGraph:
    """Construct the email pipeline graph (uncompiled)."""
    graph = StateGraph(EmailPipelineState)

    # -- Agent nodes (call LLM) --
    graph.add_node("supervisor_agent", supervisor)
    graph.add_node("generate_resume_agent", generate_resume)
    graph.add_node("evaluate_resume_agent", evaluate_resume)
    graph.add_node("analyze_and_reply_followup_agent", analyze_and_reply_followup)

    # -- Plain nodes (no LLM) --
    graph.add_node("scan_recruiter_emails_node", scan_recruiter_emails)
    graph.add_node("render_and_draft_node", render_and_draft)
    graph.add_node("scan_followup_emails_node", scan_followup_emails)
    graph.add_node("process_job_description_node", process_job_description)
    graph.add_node("finalize_node", finalize)

    # -- Entry point: always start at the supervisor --
    graph.set_entry_point("supervisor_agent")

    # -- Supervisor routes to any node --
    graph.add_conditional_edges("supervisor_agent", _supervisor_router)

    # -- Every node returns to the supervisor --
    for node_name in [
        "scan_recruiter_emails_node",
        "generate_resume_agent",
        "evaluate_resume_agent",
        "render_and_draft_node",
        "scan_followup_emails_node",
        "analyze_and_reply_followup_agent",
        "process_job_description_node",
    ]:
        graph.add_edge(node_name, "supervisor_agent")

    # -- Finalize terminates the graph --
    graph.add_edge("finalize_node", END)

    return graph


def compile_graph():
    """Build and compile the graph, ready for .invoke()."""
    return build_graph().compile()
