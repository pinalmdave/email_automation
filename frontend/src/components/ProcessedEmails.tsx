import { useEffect, useState } from "react";
import {
  fetchProcessedEmails,
  resumeDownloadHref,
  sendProcessedEmail,
  updateProcessedEmailStatus,
} from "../api";
import type { ProcessedEmail, ProcessedEmailStatus } from "../types";

interface Props {
  reloadKey: number;
  onChange: () => void;
}

const ARCHIVE_STATUSES: ProcessedEmailStatus[] = ["approved", "rejected", "cancelled", "sent"];

function formatDate(iso: string): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

const STATUS_LABELS: Record<string, string> = {
  approved: "Approved",
  rejected: "Rejected / Redo",
  cancelled: "Cancelled",
  sent: "Sent",
};

export function ProcessedEmails({ reloadKey, onChange }: Props) {
  const [items, setItems] = useState<ProcessedEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<ProcessedEmailStatus | "all">("all");
  const [busyId, setBusyId] = useState<string | null>(null);

  const reload = () => {
    setLoading(true);
    // Fetch all, then client-filter to archive statuses
    fetchProcessedEmails()
      .then((data) => {
        setItems(data.filter((i) => (ARCHIVE_STATUSES as string[]).includes(i.status)));
        setError(null);
      })
      .catch((e: Error) => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(reload, [reloadKey]);

  const act = async (messageId: string, fn: () => Promise<void>) => {
    setBusyId(messageId);
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

  if (loading) return <div className="pane pane--loading">Loading processed emails…</div>;
  if (error)   return <div className="pane pane--error">Error: {error}</div>;

  if (items.length === 0) {
    return (
      <div className="pane pane--empty">
        <h3>No processed emails yet</h3>
        <p>Approve, reject, or cancel emails from <b>Email Scan</b> to see them here.</p>
      </div>
    );
  }

  const counts: Record<string, number> = { all: items.length };
  ARCHIVE_STATUSES.forEach((s) => { counts[s] = items.filter((i) => i.status === s).length; });

  const filtered = statusFilter === "all" ? items : items.filter((i) => i.status === statusFilter);

  return (
    <div className="pane">
      <div className="pane__header">
        <h2 className="pane__title">Processed Emails</h2>
        <div className="pane__filters">
          {(["all", ...ARCHIVE_STATUSES] as const).map((s) => (
            <button
              key={s}
              className={`filter-chip ${statusFilter === s ? "filter-chip--active" : ""}`}
              onClick={() => setStatusFilter(s)}
            >
              {s === "all" ? "all" : STATUS_LABELS[s] ?? s}
              <span className="filter-chip__count">{counts[s] ?? 0}</span>
            </button>
          ))}
        </div>
      </div>

      <table className="tbl">
        <thead>
          <tr>
            <th>Status</th>
            <th>Subject</th>
            <th>From</th>
            <th>Processed</th>
            <th>Resume</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((e) => {
            const busy = busyId === e.message_id;
            return (
              <tr key={e.message_id}>
                <td>
                  <span className={`tag tag--${e.status}`}>{STATUS_LABELS[e.status] ?? e.status}</span>
                </td>
                <td className="tbl__subject" title={e.subject}>{e.subject || "(no subject)"}</td>
                <td className="tbl__from" title={e.from_email}>{e.from_email}</td>
                <td className="tbl__date">{formatDate(e.processed_at)}</td>
                <td>
                  {e.resume_filename ? (
                    <a
                      className="link link--download"
                      href={resumeDownloadHref(e.resume_download_url)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {e.resume_filename}
                    </a>
                  ) : (
                    <span className="tbl__muted">—</span>
                  )}
                </td>
                <td className="tbl__actions">
                  {e.status === "approved" ? (
                    <button
                      className="btn btn--tiny btn--send"
                      disabled={busy}
                      onClick={() => act(e.message_id, () => sendProcessedEmail(e.message_id))}
                      title="Send email with attached resume via SMTP"
                    >
                      Send Email
                    </button>
                  ) : null}
                  {e.status === "rejected" ? (
                    <button
                      className="btn btn--tiny"
                      disabled={busy}
                      onClick={() => act(e.message_id, () => updateProcessedEmailStatus(e.message_id, "new"))}
                      title="Move back to Email Scan for regeneration"
                    >
                      Regenerate Resume
                    </button>
                  ) : null}
                  {e.status === "cancelled" ? (
                    <button
                      className="btn btn--tiny btn--ghost"
                      disabled={busy}
                      onClick={() => act(e.message_id, () => updateProcessedEmailStatus(e.message_id, "new"))}
                      title="Restore to Email Scan"
                    >
                      Restore
                    </button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
