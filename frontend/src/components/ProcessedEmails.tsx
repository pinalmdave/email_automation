import { useEffect, useState } from "react";
import { fetchProcessedEmails, resumeDownloadHref } from "../api";
import type { ProcessedEmail } from "../types";

interface Props {
  reloadKey: number;
}

function formatDate(iso: string): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export function ProcessedEmails({ reloadKey }: Props) {
  const [items, setItems] = useState<ProcessedEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchProcessedEmails()
      .then((data) => { if (!cancelled) { setItems(data); setError(null); } })
      .catch((e: Error) => { if (!cancelled) setError(e.message ?? String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [reloadKey]);

  if (loading) return <div className="pane pane--loading">Loading processed emails…</div>;
  if (error)   return <div className="pane pane--error">Error: {error}</div>;
  if (items.length === 0) {
    return (
      <div className="pane pane--empty">
        <h3>No processed emails yet</h3>
        <p>Click <b>Process Job Emails</b> in the header to scan your Gmail inbox.</p>
      </div>
    );
  }

  return (
    <div className="pane">
      <div className="pane__header">
        <h2 className="pane__title">Processed Emails</h2>
        <div className="pane__meta">{items.length} total</div>
      </div>
      <table className="tbl">
        <thead>
          <tr>
            <th>Subject</th>
            <th>From</th>
            <th>Processed</th>
            <th>Status</th>
            <th>Resume</th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.message_id}>
              <td className="tbl__subject" title={e.subject}>{e.subject || "(no subject)"}</td>
              <td className="tbl__from" title={e.from_email}>{e.from_email}</td>
              <td className="tbl__date">{formatDate(e.processed_at)}</td>
              <td>
                <span className={`tag tag--${e.status.replace(/_/g, '-')}`}>
                  {e.status.replace(/_/g, ' ')}
                </span>
              </td>
              <td>
                {e.resume_download_url ? (
                  <a
                    className="link link--download"
                    href={resumeDownloadHref(e.resume_download_url)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {e.resume_filename || "Download"}
                  </a>
                ) : (
                  <span className="tbl__muted">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
