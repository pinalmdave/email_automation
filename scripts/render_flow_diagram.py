"""
Render smart_email_agentic_flow.png — the architecture diagram showing
the React UI → FastAPI → LangGraph supervisor hub-and-spoke pipeline,
external services (Gmail, Claude), and Azure Blob persistence.

Run: python scripts/render_flow_diagram.py
"""

from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent / "smart_email_agentic_flow.png"

# ---- Palette ---------------------------------------------------------------
C_BG         = "#0f1115"
C_SUPERVISOR = "#f2c94c"  # amber
C_AGENT_LLM  = "#8a6cff"  # purple — nodes that call Claude
C_NODE       = "#4a5563"  # slate — deterministic nodes
C_USER       = "#4fd1c5"  # teal — user-facing
C_API        = "#7aa2ff"  # blue — FastAPI layer
C_EXT        = "#4ade80"  # green — external services
C_STORE      = "#ff9f43"  # orange — persistence
C_FINAL      = "#2dd4bf"  # teal-green — terminal
C_EDGE       = "#c0c7d1"
C_TEXT       = "#ffffff"
C_TEXT_SOFT  = "#c7ced9"

FIG_W, FIG_H = 18, 11


def box(ax, x, y, w, h, label, color, text_color=C_TEXT, sub=None, fontsize=10):
    """Rounded box with primary label + optional subtitle."""
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.15",
        linewidth=1.2, edgecolor="#1b1f27", facecolor=color, zorder=2,
    )
    ax.add_patch(patch)
    if sub:
        ax.text(x + w/2, y + h*0.62, label, ha="center", va="center",
                color=text_color, fontsize=fontsize, fontweight="bold", zorder=3)
        ax.text(x + w/2, y + h*0.30, sub, ha="center", va="center",
                color=text_color, fontsize=fontsize - 2, alpha=0.85, zorder=3)
    else:
        ax.text(x + w/2, y + h/2, label, ha="center", va="center",
                color=text_color, fontsize=fontsize, fontweight="bold", zorder=3)
    return (x + w/2, y + h/2)


def arrow(ax, a, b, color=C_EDGE, style="-|>", lw=1.4, ls="-", rad=0.0, label=None):
    patch = FancyArrowPatch(
        a, b,
        arrowstyle=style,
        mutation_scale=16,
        linewidth=lw,
        linestyle=ls,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
        zorder=1,
    )
    ax.add_patch(patch)
    if label:
        mx = (a[0] + b[0]) / 2
        my = (a[1] + b[1]) / 2
        ax.text(mx, my, label, ha="center", va="center", color=C_TEXT_SOFT,
                fontsize=8, bbox=dict(facecolor=C_BG, edgecolor="none", pad=1.2))


def port(center, wh, side):
    """Return an edge point on a box for nicer arrow attachment."""
    cx, cy = center
    w, h = wh
    if side == "top":    return (cx, cy + h/2)
    if side == "bottom": return (cx, cy - h/2)
    if side == "left":   return (cx - w/2, cy)
    if side == "right":  return (cx + w/2, cy)
    return center


# ---------------------------------------------------------------------------

def render():
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), facecolor=C_BG)
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, FIG_W)
    ax.set_ylim(0, FIG_H)
    ax.set_axis_off()

    # ── Title ───────────────────────────────────────────────────────────────
    ax.text(FIG_W/2, FIG_H - 0.35, "Claude Smart Email App  —  Agentic Flow",
            ha="center", va="top", color=C_TEXT, fontsize=18, fontweight="bold")
    ax.text(FIG_W/2, FIG_H - 0.85,
            "React SWA  →  FastAPI (WebSocket)  →  LangGraph supervisor  →  Claude API + Gmail + Azure Blob",
            ha="center", va="top", color=C_TEXT_SOFT, fontsize=11)

    # ── Row 1: User entry points ────────────────────────────────────────────
    ui_wh = (3.6, 0.9)
    ui = box(ax, 1.2, FIG_H - 2.4, *ui_wh,
             "React UI  (Azure Static Web App)", C_USER, text_color="#08201d",
             sub="Process Job Emails  •  Paste JD  •  Usage panel  •  Progress log")

    cli_wh = (2.8, 0.9)
    cli = box(ax, 13.8, FIG_H - 2.4, *cli_wh,
              "CLI  main.py", C_USER, text_color="#08201d",
              sub="--phase1-only / --phase2-only / --job-description")

    # ── Row 2: FastAPI layer ────────────────────────────────────────────────
    api_wh = (10.4, 1.2)
    api = box(ax, 3.8, FIG_H - 4.3, *api_wh, "FastAPI  (Azure Web App — B1 Linux)", C_API,
              text_color="#0b1022",
              sub="/ws/process-emails   •   /ws/process-jd   •   /api/usage   •   /api/resume/{f}")

    # ── Row 3: Supervisor (center hub) ──────────────────────────────────────
    sup_wh = (3.8, 1.0)
    sup_x = (FIG_W - sup_wh[0]) / 2
    sup_y = 4.4
    sup = box(ax, sup_x, sup_y, *sup_wh, "supervisor_agent", C_SUPERVISOR,
              text_color="#3b2e00",
              sub="inspects state → routes to next node")

    # ── Row 4: Spoke nodes around the supervisor ────────────────────────────
    node_wh = (3.0, 0.9)
    # left column
    scan_rec = box(ax, 0.4, 5.7, *node_wh, "scan_recruiter_emails_node", C_NODE,
                   sub="Gmail IMAP  •  filter + dedup")
    scan_fu  = box(ax, 0.4, 4.3, *node_wh, "scan_followup_emails_node", C_NODE,
                   sub="Gmail IMAP  •  recruiter follow-ups")
    proc_jd  = box(ax, 0.4, 2.9, *node_wh, "process_job_description_node", C_NODE,
                   sub="NEW  •  wraps pasted JD as email")

    # right column
    gen_res  = box(ax, FIG_W - 0.4 - node_wh[0], 5.7, *node_wh,
                   "generate_resume_agent", C_AGENT_LLM,
                   sub="Claude Sonnet  •  JSON → DOCX")
    anal_fu  = box(ax, FIG_W - 0.4 - node_wh[0], 4.3, *node_wh,
                   "analyze_and_reply_followup_agent", C_AGENT_LLM,
                   sub="Claude Sonnet  •  intent + reply")
    render_draft = box(ax, FIG_W - 0.4 - node_wh[0], 2.9, *node_wh,
                       "render_and_draft_node", C_NODE,
                       sub="Gmail draft  •  attaches resume")

    # bottom center
    final_wh = (2.8, 0.8)
    final = box(ax, (FIG_W - final_wh[0])/2, 3.0, *final_wh,
                "finalize_node  →  END", C_FINAL, text_color="#08201d",
                sub="builds summary  •  terminates graph")

    # ── External services & storage ─────────────────────────────────────────
    ext_wh = (2.6, 0.7)
    gmail = box(ax, 0.3, 0.8, *ext_wh, "Gmail IMAP / SMTP", C_EXT,
                text_color="#08201d", sub="App-password auth")
    claude = box(ax, (FIG_W - ext_wh[0])/2, 0.8, *ext_wh,
                 "Claude API  (Anthropic)", C_EXT, text_color="#08201d",
                 sub="Sonnet 4  •  token + cost tracked")
    blob = box(ax, FIG_W - 0.3 - ext_wh[0], 0.8, *ext_wh,
               "Azure Blob Storage", C_STORE, text_color="#3b1f00",
               sub="resumes/  •  state/  •  SAS URLs")

    # ── Edges ───────────────────────────────────────────────────────────────
    # UI → FastAPI (WebSocket)
    arrow(ax, port(ui, ui_wh, "bottom"), port(api, api_wh, "top"),
          color=C_USER, lw=2.2, label="WebSocket")

    # CLI → graph (dashed, bypasses FastAPI)
    arrow(ax, port(cli, cli_wh, "bottom"), port(sup, sup_wh, "top"),
          color=C_USER, ls="--", lw=1.5, rad=-0.35)
    ax.text(15.0, FIG_H - 3.3, "direct invoke", ha="center", va="center",
            color=C_TEXT_SOFT, fontsize=8,
            bbox=dict(facecolor=C_BG, edgecolor="none", pad=1.2))

    # FastAPI → supervisor (graph.stream)
    arrow(ax, port(api, api_wh, "bottom"), (sup_x + sup_wh[0]*0.55, sup_y + sup_wh[1]),
          color=C_API, lw=2.2)
    ax.text(FIG_W/2 + 0.9, FIG_H - 4.7, "graph.stream()", ha="center", va="center",
            color=C_TEXT_SOFT, fontsize=8,
            bbox=dict(facecolor=C_BG, edgecolor="none", pad=1.2))

    # Supervisor <-> spokes (every node returns to supervisor)
    for node, wh, side_to, side_from, rad in [
        (scan_rec,     node_wh, "left",  "right", 0.1),
        (scan_fu,      node_wh, "left",  "right", 0.0),
        (proc_jd,      node_wh, "left",  "right", -0.1),
        (gen_res,      node_wh, "right", "left",  -0.1),
        (anal_fu,      node_wh, "right", "left",  0.0),
        (render_draft, node_wh, "right", "left",  0.1),
    ]:
        arrow(ax, port(sup, sup_wh, side_to), port(node, wh, side_from),
              color=C_EDGE, lw=1.2, rad=rad)
        arrow(ax, port(node, wh, side_from), port(sup, sup_wh, side_to),
              color="#6b7280", lw=1.0, ls=":", rad=-rad)

    # Supervisor → finalize
    arrow(ax, port(sup, sup_wh, "bottom"), port(final, final_wh, "top"),
          color=C_FINAL, lw=1.8, label="when idle")

    # Nodes → external services
    arrow(ax, port(scan_rec, node_wh, "bottom"), port(gmail, ext_wh, "top"),
          color=C_EXT, lw=1.2, rad=-0.2)
    arrow(ax, port(scan_fu, node_wh, "bottom"), port(gmail, ext_wh, "top"),
          color=C_EXT, lw=1.2, rad=-0.3)
    arrow(ax, port(render_draft, node_wh, "bottom"), port(gmail, ext_wh, "top"),
          color=C_EXT, lw=1.2, rad=0.5, label=None)

    arrow(ax, port(gen_res, node_wh, "bottom"), port(claude, ext_wh, "top"),
          color=C_EXT, lw=1.4, rad=0.3)
    arrow(ax, port(anal_fu, node_wh, "bottom"), port(claude, ext_wh, "top"),
          color=C_EXT, lw=1.4, rad=0.2)

    # Resume + state → blob
    arrow(ax, port(gen_res, node_wh, "bottom"), port(blob, ext_wh, "top"),
          color=C_STORE, lw=1.3, rad=-0.15, label="upload resume")
    arrow(ax, port(render_draft, node_wh, "bottom"), port(blob, ext_wh, "top"),
          color=C_STORE, lw=1.2, rad=-0.25, label="processed_emails")
    arrow(ax, port(scan_fu, node_wh, "bottom"), port(blob, ext_wh, "top"),
          color=C_STORE, lw=1.0, ls=":", rad=-0.4, label=None)

    # FastAPI ↔ blob (usage + SAS)
    arrow(ax, port(api, api_wh, "right"), (FIG_W - 0.3 - ext_wh[0]/2, 1.15),
          color=C_STORE, lw=1.0, ls=":", rad=-0.35, label=None)

    # Progress events back to UI (dashed, on the left)
    arrow(ax, (sup_x + sup_wh[0]*0.25, sup_y + sup_wh[1]),
          (api_wh[0]/2 + 3.8 - 0.5, FIG_H - 4.3),
          color=C_USER, lw=1.0, ls="--", rad=-0.3, label=None)
    ax.text(sup_x - 0.8, FIG_H - 4.9, "progress events\n(node + usage)",
            ha="center", va="center", color=C_TEXT_SOFT, fontsize=8,
            bbox=dict(facecolor=C_BG, edgecolor="none", pad=1.2))

    # ── Legend ──────────────────────────────────────────────────────────────
    legend_items = [
        ("Supervisor (LangGraph hub)", C_SUPERVISOR),
        ("LLM agent node (Claude API)", C_AGENT_LLM),
        ("Plain node (deterministic)",  C_NODE),
        ("User / entry point",          C_USER),
        ("FastAPI layer",               C_API),
        ("External service",            C_EXT),
        ("Persistent storage",          C_STORE),
        ("Terminal node",               C_FINAL),
    ]
    handles = [mpatches.Patch(facecolor=c, edgecolor="#1b1f27", label=lbl)
               for lbl, c in legend_items]
    leg = ax.legend(
        handles=handles, loc="lower center", ncol=4,
        bbox_to_anchor=(0.5, -0.02), frameon=False,
        labelcolor=C_TEXT_SOFT, fontsize=9,
    )
    for txt in leg.get_texts():
        txt.set_color(C_TEXT_SOFT)

    fig.tight_layout()
    fig.savefig(OUT, dpi=160, facecolor=C_BG, bbox_inches="tight", pad_inches=0.25)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    render()
