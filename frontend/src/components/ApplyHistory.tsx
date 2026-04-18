import { useEffect, useState } from "react";
import {
  applyPlanCancel,
  applyPlanDelete,
  applyPlanMarkApplied,
  fetchApplyPlans,
  resumeDownloadHref,
} from "../api";
import type { ApplyPlan, ApplyPlanStatus } from "../types";

interface Props {
  reloadKey: number;
  onChange: () => void;
}

const STATUS_ORDER: ApplyPlanStatus[] = ["ready", "planning", "applied", "cancelled"];

function formatDate(iso: string): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function hostOf(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

export function ApplyHistory({ reloadKey, onChange }: Props) {
  const [items, setItems] = useState<ApplyPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<ApplyPlanStatus | "all">("all");
  const [busyId, setBusyId] = useState<string | null>(null);

  const reload = () => {
    setLoading(true);
    fetchApplyPlans("all")
      .then((data) => {
        setItems(data);
        setError(null);
      })
      .catch((e: Error) => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(reload, [reloadKey]);

  const act = async (id: string, fn: () => Promise<unknown>) => {
    setBusyId(id);
    try {
      await fn();
      await fetchApplyPlans("all").then(setItems);
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <div className="pane pane--loading">Loading apply history…</div>;
  if (error)   return <div className="pane pane--error">Error: {error}</div>;

  const filtered = statusFilter === "all" ? items : items.filter((i) => i.status === statusFilter);

  if (items.length === 0) {
    return (
      <div className="pane pane--empty">
        <h3>No job applications yet</h3>
        <p>Paste a job posting URL in <b>Chat / Apply URL</b> to start a tailored application plan.</p>
      </div>
    );
  }

  const counts: Record<string, number> = { all: items.length };
  STATUS_ORDER.forEach((s) => { counts[s] = items.filter((i) => i.status === s).length; });

  return (
    <div className="pane">
      <div className="pane__header">
        <h2 className="pane__title">Apply History</h2>
        <div className="pane__filters">
          {(["all", ...STATUS_ORDER] as const).map((s) => (
            <button
              key={s}
              className={`filter-chip ${statusFilter === s ? "filter-chip--active" : ""}`}
              onClick={() => setStatusFilter(s)}
            >
              {s} <span className="filter-chip__count">{counts[s] ?? 0}</span>
            </button>
          ))}
        </div>
      </div>

      <table className="tbl">
        <thead>
          <tr>
            <th>Status</th>
            <th>Job</th>
            <th>Source</th>
            <th>Created</th>
            <th>Resume</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((p) => (
            <tr key={p.id} className={p.recommendation === "decline" ? "tbl__row--warn" : ""}>
              <td>
                <span className={`tag tag--${p.status}`}>{p.status}</span>
                {p.recommendation === "decline" ? (
                  <div className="tag tag--decline" title={p.decline_reason}>⚠ poor fit</div>
                ) : null}
                {typeof p.evaluation_score === "number" && p.evaluation_score > 0 ? (
                  <div className="tbl__muted" style={{ fontSize: 11, marginTop: 2 }}>
                    score {p.evaluation_score.toFixed(2)}
                  </div>
                ) : null}
              </td>
              <td>
                <div className="tbl__subject" title={p.job_title}>
                  <a className="link" href={p.job_url} target="_blank" rel="noreferrer">
                    {p.job_title || "(title unknown)"}
                  </a>
                </div>
                <div className="tbl__muted">
                  {[p.company_name, p.staffing_company_name, p.target_role_title].filter(Boolean).join(" · ")}
                </div>
                {p.recommendation === "decline" && p.decline_reason ? (
                  <div className="tbl__warn-reason">⚠ {p.decline_reason}</div>
                ) : null}
              </td>
              <td><span className="pill pill--small">{p.source || hostOf(p.job_url)}</span></td>
              <td className="tbl__date">{formatDate(p.created_at)}</td>
              <td>
                {p.resume_filename ? (
                  <a
                    className="link link--download"
                    href={resumeDownloadHref(`/api/resume/${p.resume_filename}`)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {p.resume_filename}
                  </a>
                ) : (
                  <span className="tbl__muted">—</span>
                )}
              </td>
              <td className="tbl__actions">
                {p.status === "ready" ? (
                  <>
                    <a className="btn btn--tiny" href={p.job_url} target="_blank" rel="noreferrer">Open posting</a>
                    <button
                      className="btn btn--tiny btn--send"
                      onClick={() => act(p.id, () => applyPlanMarkApplied(p.id))}
                      disabled={busyId === p.id}
                      title="Mark as applied once you've submitted on the job site"
                    >
                      Mark applied
                    </button>
                  </>
                ) : null}
                {p.status !== "cancelled" && p.status !== "applied" ? (
                  <button
                    className="btn btn--tiny btn--ghost"
                    onClick={() => act(p.id, () => applyPlanCancel(p.id))}
                    disabled={busyId === p.id}
                  >
                    Cancel
                  </button>
                ) : null}
                {p.status === "cancelled" ? (
                  <button
                    className="btn btn--tiny btn--ghost"
                    onClick={() => act(p.id, () => applyPlanDelete(p.id))}
                    disabled={busyId === p.id}
                  >
                    Delete
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
