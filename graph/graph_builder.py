"""
Builds and compiles the LangGraph StateGraph for the email pipeline.

Hub-and-spoke topology: every agent returns to the supervisor, which
inspects state and routes to the next agent.
"""

from langgraph.graph import END, StateGraph

from agents.analyze_and_reply_followup_agent import analyze_and_reply_followup
from agents.finalize_agent import finalize
from agents.generate_resume_agent import generate_resume
from agents.pick_next_email_agent import pick_next_email
from agents.pick_next_followup_agent import pick_next_followup
from agents.render_and_draft_agent import render_and_draft
from agents.scan_followup_emails_agent import scan_followup_emails
from agents.scan_recruiter_emails_agent import scan_recruiter_emails
from agents.supervisor_agent import supervisor
from graph.state import EmailPipelineState


def _supervisor_router(state: EmailPipelineState) -> str:
    """Read the supervisor's routing decision from state."""
    return state.get("next_agent", "finalize_agent")


def build_graph() -> StateGraph:
    """Construct the email pipeline graph (uncompiled)."""
    graph = StateGraph(EmailPipelineState)

    # -- Add nodes --
    graph.add_node("supervisor_agent", supervisor)
    graph.add_node("scan_recruiter_emails_agent", scan_recruiter_emails)
    graph.add_node("pick_next_email_agent", pick_next_email)
    graph.add_node("generate_resume_agent", generate_resume)
    graph.add_node("render_and_draft_agent", render_and_draft)
    graph.add_node("scan_followup_emails_agent", scan_followup_emails)
    graph.add_node("pick_next_followup_agent", pick_next_followup)
    graph.add_node("analyze_and_reply_followup_agent", analyze_and_reply_followup)
    graph.add_node("finalize_agent", finalize)

    # -- Entry point: always start at the supervisor --
    graph.set_entry_point("supervisor_agent")

    # -- Supervisor routes to any agent --
    graph.add_conditional_edges("supervisor_agent", _supervisor_router)

    # -- Every agent returns to the supervisor --
    for agent_name in [
        "scan_recruiter_emails_agent",
        "pick_next_email_agent",
        "generate_resume_agent",
        "render_and_draft_agent",
        "scan_followup_emails_agent",
        "pick_next_followup_agent",
        "analyze_and_reply_followup_agent",
    ]:
        graph.add_edge(agent_name, "supervisor_agent")

    # -- Finalize terminates the graph --
    graph.add_edge("finalize_agent", END)

    return graph


def compile_graph():
    """Build and compile the graph, ready for .invoke()."""
    return build_graph().compile()
