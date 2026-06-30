import { useEffect, useState } from "react";
import {
  applyPlanCancel,
  applyPlanDelete,
  applyPlanMarkApplied,
  fetchApplyPlans,
  fetchProcessedEmails,
  resumeDownloadHref,
} from "../api";
import type { ApplyPlan } from "../types";

interface Props {
  reloadKey: number;
  onChange: () => void;
}

type RowStatus = "ready" | "planning" | "applied" | "cancelled";
const STATUS_ORDER: RowStatus[] = ["ready", "planning", "applied", "cancelled"];

// Unified row across two sources: URL apply-plans and SENT email applications.
interface Row {
  key: string;
  status: RowStatus;
  jobTitle: string;
  sub: string;
  source: string;
  created: string;
  resumeFilename: string;
  resumeUrl: string;
  jobUrl: string;
  kind: "plan" | "email";
  plan?: ApplyPlan;
  score?: number;
  recommendation?: string;
  declineReason?: string;
}

function formatDate(iso: string): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function hostOf(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

function domainOf(from: string): string {
  const m = from.match(/@([\w.-]+)/);
  return m ? m[1] : from;
}

export function ApplyHistory({ reloadKey, onChange }: Props) {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<RowStatus | "all">("all");
  const [busyId, setBusyId] = useState<string | null>(null);

  const reload = () => {
    setLoading(true);
    Promise.all([fetchApplyPlans("all"), fetchProcessedEmails("sent")])
      .then(([plans, sent]) => {
        const planRows: Row[] = plans.map((p) => ({
          key: `plan-${p.id}`,
          status: (p.status as RowStatus),
          jobTitle: p.job_title || "(title unknown)",
          sub: [p.company_name, p.staffing_company_name, p.target_role_title].filter(Boolean).join(" · "),
          source: p.source || hostOf(p.job_url),
          created: p.created_at,
          resumeFilename: p.resume_filename,
          resumeUrl: p.resume_filename ? `/api/resume/${p.resume_filename}` : "",
          jobUrl: p.job_url,
          kind: "plan",
          plan: p,
          score: p.evaluation_score,
          recommendation: p.recommendation,
          declineReason: p.decline_reason,
        }));
        // Sent email applications count as "applied".
        const emailRows: Row[] = sent.map((e) => ({
          key: `email-${e.message_id}`,
          status: "applied" as RowStatus,
          jobTitle: e.subject || "(no subject)",
          sub: e.from_email,
          source: domainOf(e.from_email) || "Email",
          created: e.processed_at,
          resumeFilename: e.resume_filename,
          resumeUrl: e.resume_download_url,
          jobUrl: "",
          kind: "email",
        }));
        const all = [...planRows, ...emailRows].sort((a, b) => (a.created < b.created ? 1 : -1));
        setRows(all);
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
      reload();
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <div className="pane pane--loading">Loading apply history…</div>;
  if (error)   return <div className="pane pane--error">Error: {error}</div>;

  if (rows.length === 0) {
    return (
      <div className="pane pane--empty">
        <h3>No applications yet</h3>
        <p>Use <b>Auto-Apply</b> / <b>Approve &amp; Send</b>, or paste a job URL in <b>Apply from URL</b>.</p>
      </div>
    );
  }

  const counts: Record<string, number> = { all: rows.length };
  STATUS_ORDER.forEach((s) => { counts[s] = rows.filter((r) => r.status === s).length; });
  const filtered = statusFilter === "all" ? rows : rows.filter((r) => r.status === statusFilter);

  return (
    <div className="pane">
      <div className="pane__header">
        <h2 className="pane__title">Apply History</h2>
        <div className="pane__meta">{rows.length} total · {counts["applied"] ?? 0} applied</div>
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
            <th>Applied / Created</th>
            <th>Resume</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((r) => (
            <tr key={r.key} className={r.recommendation === "decline" ? "tbl__row--warn" : ""}>
              <td>
                <span className={`tag tag--${r.status}`}>{r.status}</span>
                {r.kind === "email" ? <div className="tbl__muted" style={{ fontSize: 11, marginTop: 2 }}>via email</div> : null}
                {typeof r.score === "number" && r.score > 0 ? (
                  <div className="tbl__muted" style={{ fontSize: 11, marginTop: 2 }}>score {r.score.toFixed(2)}</div>
                ) : null}
              </td>
              <td>
                <div className="tbl__subject" title={r.jobTitle}>
                  {r.jobUrl ? (
                    <a className="link" href={r.jobUrl} target="_blank" rel="noreferrer">{r.jobTitle}</a>
                  ) : r.jobTitle}
                </div>
                <div className="tbl__muted">{r.sub}</div>
                {r.recommendation === "decline" && r.declineReason ? (
                  <div className="tbl__warn-reason">⚠ {r.declineReason}</div>
                ) : null}
              </td>
              <td><span className="pill pill--small">{r.source}</span></td>
              <td className="tbl__date">{formatDate(r.created)}</td>
              <td>
                {r.resumeFilename ? (
                  <a className="link link--download" href={resumeDownloadHref(r.resumeUrl)} target="_blank" rel="noreferrer">
                    {r.resumeFilename}
                  </a>
                ) : <span className="tbl__muted">—</span>}
              </td>
              <td className="tbl__actions">
                {r.kind === "plan" && r.plan ? (
                  <>
                    {r.status === "ready" ? (
                      <>
                        <a className="btn btn--tiny" href={r.jobUrl} target="_blank" rel="noreferrer">Open posting</a>
                        <button className="btn btn--tiny btn--send" disabled={busyId === r.key}
                          onClick={() => act(r.key, () => applyPlanMarkApplied(r.plan!.id))}>Mark applied</button>
                      </>
                    ) : null}
                    {r.status !== "cancelled" && r.status !== "applied" ? (
                      <button className="btn btn--tiny btn--ghost" disabled={busyId === r.key}
                        onClick={() => act(r.key, () => applyPlanCancel(r.plan!.id))}>Cancel</button>
                    ) : null}
                    {r.status === "cancelled" ? (
                      <button className="btn btn--tiny btn--ghost" disabled={busyId === r.key}
                        onClick={() => act(r.key, () => applyPlanDelete(r.plan!.id))}>Delete</button>
                    ) : null}
                  </>
                ) : (
                  <span className="tbl__muted">Sent</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
