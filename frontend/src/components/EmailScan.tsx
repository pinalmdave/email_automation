import { useEffect, useState } from "react";
import { fetchProcessedEmails, resumeDownloadHref, updateProcessedEmailStatus } from "../api";
import type { ProcessedEmail } from "../types";

interface Props {
  reloadKey: number;
  onChange: () => void;
}

function formatDate(iso: string): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

export function EmailScan({ reloadKey, onChange }: Props) {
  const [items, setItems] = useState<ProcessedEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const reload = () => {
    setLoading(true);
    fetchProcessedEmails("new")
      .then((data) => { setItems(data); setError(null); })
      .catch((e: Error) => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(reload, [reloadKey]);

  const act = async (messageId: string, status: string) => {
    setBusyId(messageId);
    try {
      await updateProcessedEmailStatus(messageId, status);
      setItems((prev) => prev.filter((i) => i.message_id !== messageId));
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <div className="pane pane--loading">Loading new emails…</div>;
  if (error)   return <div className="pane pane--error">Error: {error}</div>;

  if (items.length === 0) {
    return (
      <div className="pane pane--empty">
        <h3>No new emails</h3>
        <p>Click <b>Process Job Emails</b> in the header to scan your Gmail inbox.</p>
      </div>
    );
  }

  return (
    <div className="pane">
      <div className="pane__header">
        <h2 className="pane__title">New Emails</h2>
        <div className="pane__meta">{items.length} awaiting review</div>
      </div>
      <table className="tbl">
        <thead>
          <tr>
            <th>Subject</th>
            <th>From</th>
            <th>Processed</th>
            <th>Resume</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => {
            const busy = busyId === e.message_id;
            return (
              <tr key={e.message_id}>
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
                  <button
                    className="btn btn--tiny btn--send"
                    onClick={() => act(e.message_id, "approved")}
                    disabled={busy}
                    title="Approve — move to Processed Emails and enable Send"
                  >
                    Approve
                  </button>
                  <button
                    className="btn btn--tiny btn--ghost"
                    onClick={() => act(e.message_id, "rejected")}
                    disabled={busy}
                    title="Reject — move to Processed Emails for regeneration"
                  >
                    Reject
                  </button>
                  <button
                    className="btn btn--tiny btn--ghost"
                    onClick={() => act(e.message_id, "cancelled")}
                    disabled={busy}
                    title="Cancel — skip this email"
                  >
                    Cancel
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
