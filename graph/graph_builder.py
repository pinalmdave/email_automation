"""
Builds and compiles the LangGraph StateGraph for the email pipeline.
"""

from langgraph.graph import END, StateGraph

from graph.nodes import (
    analyze_and_reply_followup,
    finalize,
    generate_resume,
    pick_next_email,
    pick_next_followup,
    render_and_draft,
    route_phases,
    scan_followup_emails,
    scan_recruiter_emails,
)
from graph.state import EmailPipelineState


def _phase_router(state: EmailPipelineState) -> str:
    """Route after the supervisor based on which phase to enter."""
    phase = state.get("phase", "done")
    if phase == "phase1":
        return "scan_recruiter_emails"
    if phase == "phase2":
        return "scan_followup_emails"
    return "finalize"


def _email_picker_router(state: EmailPipelineState) -> str:
    """Route after pick_next_email: continue processing or go back to supervisor."""
    if state.get("current_email"):
        return "generate_resume"
    return "route_phases"


def _followup_picker_router(state: EmailPipelineState) -> str:
    """Route after pick_next_followup: continue or go back to supervisor."""
    if state.get("current_followup"):
        return "analyze_and_reply_followup"
    return "route_phases"


def build_graph() -> StateGraph:
    """Construct the email pipeline graph (uncompiled)."""
    graph = StateGraph(EmailPipelineState)

    # -- Add nodes --
    graph.add_node("route_phases", route_phases)
    graph.add_node("scan_recruiter_emails", scan_recruiter_emails)
    graph.add_node("pick_next_email", pick_next_email)
    graph.add_node("generate_resume", generate_resume)
    graph.add_node("render_and_draft", render_and_draft)
    graph.add_node("scan_followup_emails", scan_followup_emails)
    graph.add_node("pick_next_followup", pick_next_followup)
    graph.add_node("analyze_and_reply_followup", analyze_and_reply_followup)
    graph.add_node("finalize", finalize)

    # -- Entry point --
    graph.set_entry_point("route_phases")

    # -- Edges --
    # Supervisor routes to the appropriate phase
    graph.add_conditional_edges("route_phases", _phase_router)

    # Phase 1 flow
    graph.add_edge("scan_recruiter_emails", "pick_next_email")
    graph.add_conditional_edges("pick_next_email", _email_picker_router)
    graph.add_edge("generate_resume", "render_and_draft")
    graph.add_edge("render_and_draft", "pick_next_email")

    # Phase 2 flow
    graph.add_edge("scan_followup_emails", "pick_next_followup")
    graph.add_conditional_edges("pick_next_followup", _followup_picker_router)
    graph.add_edge("analyze_and_reply_followup", "pick_next_followup")

    # Finalize terminates the graph
    graph.add_edge("finalize", END)

    return graph


def compile_graph():
    """Build and compile the graph, ready for .invoke()."""
    return build_graph().compile()
