/**
 * PipelineGraph — animated SVG diagram of the LangGraph node topology.
 *
 * - Nodes are laid out in a hub-and-spoke pattern around the Supervisor.
 * - The most recently active node pulses blue; completed nodes stay green.
 * - While the pipeline is running the Supervisor pulses to indicate it is
 *   always routing between steps.
 */
import { useMemo } from "react";
import type { ProgressEvent } from "../types";

interface Props {
  events: ProgressEvent[];
  running: boolean;
}

// ── Layout constants ───────────────────────────────────────────────────────
const W = 620;
const H = 420;
const NW = 148;   // node box width
const NH = 36;    // node box height
const R  = 5;     // corner radius

// Positions: [cx, cy] where cx/cy is the centre of each box
const POSITIONS: Record<string, [number, number]> = {
  supervisor_agent:                    [310, 200],

  // Left column — input / scan nodes
  scan_recruiter_emails_node:          [ 90,  70],
  scan_followup_emails_node:           [ 90, 150],
  process_job_description_node:        [ 90, 230],
  process_job_url_node:                [ 90, 310],

  // Right column — generation / output nodes
  generate_resume_agent:               [530,  70],
  evaluate_resume_agent:               [530, 150],
  render_and_draft_node:               [530, 230],
  analyze_and_reply_followup_agent:    [530, 310],

  // Bottom — finalize
  finalize_node:                       [310, 370],
};

const NODE_LABELS: Record<string, string[]> = {
  supervisor_agent:                    ["Supervisor"],
  scan_recruiter_emails_node:          ["Scan Recruiter", "Emails"],
  scan_followup_emails_node:           ["Scan", "Follow-ups"],
  process_job_description_node:        ["Process Job", "Description"],
  process_job_url_node:                ["Fetch Job URL"],
  generate_resume_agent:               ["Generate", "Resume"],
  evaluate_resume_agent:               ["Evaluate", "Resume"],
  render_and_draft_node:               ["Render &", "Draft"],
  analyze_and_reply_followup_agent:    ["Analyze &", "Reply"],
  finalize_node:                       ["Finalize"],
};

// Every node connects to supervisor (bidirectional), finalize → END
const EDGES: [string, string][] = [
  ["supervisor_agent", "scan_recruiter_emails_node"],
  ["supervisor_agent", "scan_followup_emails_node"],
  ["supervisor_agent", "process_job_description_node"],
  ["supervisor_agent", "process_job_url_node"],
  ["supervisor_agent", "generate_resume_agent"],
  ["supervisor_agent", "evaluate_resume_agent"],
  ["supervisor_agent", "render_and_draft_node"],
  ["supervisor_agent", "analyze_and_reply_followup_agent"],
  ["supervisor_agent", "finalize_node"],
];

// Colour palette
const C = {
  idle:        "#1e293b",  // dark navy box
  idleBorder:  "#334155",
  idleText:    "#94a3b8",
  active:      "#1d4ed8",  // blue — currently running
  activeBorder:"#3b82f6",
  activeText:  "#eff6ff",
  done:        "#166534",  // green — completed
  doneBorder:  "#22c55e",
  doneText:    "#dcfce7",
  edge:        "#475569",
  edgeActive:  "#3b82f6",
  supervisor:  "#312e81",  // indigo hub
  supBorder:   "#6366f1",
  supText:     "#e0e7ff",
};

function arrowPath(from: string, to: string): string {
  const [ax, ay] = POSITIONS[from];
  const [bx, by] = POSITIONS[to];
  const dx = bx - ax;
  const dy = by - ay;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < 1) return "";
  const nx = dx / len;
  const ny = dy / len;
  // Clip to box edges
  const halfW = NW / 2 + 2;
  const halfH = NH / 2 + 2;
  const tFrom = Math.min(
    Math.abs(halfW / (nx || 0.0001)),
    Math.abs(halfH / (ny || 0.0001))
  );
  const tTo = Math.min(
    Math.abs(halfW / (nx || 0.0001)),
    Math.abs(halfH / (ny || 0.0001))
  );
  const sx = ax + nx * tFrom;
  const sy = ay + ny * tFrom;
  const ex = bx - nx * tTo;
  const ey = by - ny * tTo;
  return `M${sx.toFixed(1)},${sy.toFixed(1)} L${ex.toFixed(1)},${ey.toFixed(1)}`;
}

export function PipelineGraph({ events, running }: Props) {
  // Derive active/completed node sets from events
  const { activeNode, completedNodes } = useMemo(() => {
    const completed = new Set<string>();
    let active: string | null = null;
    for (const e of events) {
      if (e.event === "node_complete" && e.node) {
        completed.add(e.node);
        active = e.node;
      }
      if (e.event === "done") active = null;
    }
    return { activeNode: active, completedNodes: completed };
  }, [events]);

  const nodeState = (id: string): "active" | "done" | "idle" | "supervisor" => {
    if (id === "supervisor_agent") return "supervisor";
    if (id === activeNode) return "active";
    if (completedNodes.has(id)) return "done";
    return "idle";
  };

  const boxFill   = (id: string) => {
    const s = nodeState(id);
    if (s === "supervisor") return C.supervisor;
    if (s === "active")     return C.active;
    if (s === "done")       return C.done;
    return C.idle;
  };
  const boxStroke = (id: string) => {
    const s = nodeState(id);
    if (s === "supervisor") return C.supBorder;
    if (s === "active")     return C.activeBorder;
    if (s === "done")       return C.doneBorder;
    return C.idleBorder;
  };
  const textColor = (id: string) => {
    const s = nodeState(id);
    if (s === "supervisor") return C.supText;
    if (s === "active")     return C.activeText;
    if (s === "done")       return C.doneText;
    return C.idleText;
  };

  const isEdgeActive = (a: string, b: string) =>
    activeNode === a || activeNode === b ||
    (running && (a === "supervisor_agent" || b === "supervisor_agent"));

  return (
    <div className="pipeline-graph">
      <div className="pipeline-graph__title">
        Pipeline Graph
        {running ? <span className="spinner" style={{ marginLeft: 8 }} /> : null}
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height="100%"
        preserveAspectRatio="xMidYMid meet"
        aria-label="LangGraph pipeline diagram"
      >
        <defs>
          {/* Arrow marker — idle */}
          <marker id="arr-idle" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill={C.edge} />
          </marker>
          {/* Arrow marker — active */}
          <marker id="arr-active" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill={C.edgeActive} />
          </marker>
          {/* Glow filter for active node */}
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Edges */}
        {EDGES.map(([a, b]) => {
          const active = isEdgeActive(a, b);
          return (
            <path
              key={`${a}-${b}`}
              d={arrowPath(a, b)}
              stroke={active ? C.edgeActive : C.edge}
              strokeWidth={active ? 2 : 1.2}
              fill="none"
              markerEnd={active ? "url(#arr-active)" : "url(#arr-idle)"}
              strokeDasharray={active && running ? "6 3" : undefined}
              style={active && running ? { animation: "dash 1s linear infinite" } : undefined}
            />
          );
        })}

        {/* Nodes */}
        {Object.entries(POSITIONS).map(([id, [cx, cy]]) => {
          const lines = NODE_LABELS[id] ?? [id];
          const isActive = id === activeNode;
          const isSup = id === "supervisor_agent";
          const supPulse = isSup && running;
          const lineH = 14;
          const totalH = lines.length * lineH;
          const topY = cy - totalH / 2 + lineH / 2;
          // Supervisor is slightly larger
          const bw = isSup ? NW + 10 : NW;
          const bh = isSup ? NH + 4 : NH;
          return (
            <g key={id}>
              <rect
                x={cx - bw / 2}
                y={cy - bh / 2}
                width={bw}
                height={bh}
                rx={R}
                ry={R}
                fill={boxFill(id)}
                stroke={boxStroke(id)}
                strokeWidth={isActive || isSup ? 2 : 1}
                filter={isActive || (supPulse) ? "url(#glow)" : undefined}
                style={(isActive || supPulse) ? { animation: "pulse-node 1.2s ease-in-out infinite" } : undefined}
              />
              {lines.map((line, li) => (
                <text
                  key={li}
                  x={cx}
                  y={topY + li * lineH}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill={textColor(id)}
                  fontSize={isSup ? 11 : 10}
                  fontWeight={isSup ? "700" : "500"}
                  fontFamily="system-ui, sans-serif"
                >
                  {line}
                </text>
              ))}
              {/* Completed checkmark */}
              {completedNodes.has(id) && id !== activeNode && (
                <text x={cx + bw / 2 - 8} y={cy - bh / 2 + 10}
                  fontSize="10" fill={C.doneBorder} fontFamily="system-ui">✓</text>
              )}
            </g>
          );
        })}

        {/* START / END labels */}
        <text x={310} y={18} textAnchor="middle" fill="#64748b" fontSize={10} fontFamily="system-ui">▼ START</text>
        <text x={310} y={H - 8} textAnchor="middle" fill="#64748b" fontSize={10} fontFamily="system-ui">▼ END</text>
      </svg>
    </div>
  );
}
