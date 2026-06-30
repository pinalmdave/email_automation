import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import {
  approveSendEmail,
  bulkApproveSend,
  bulkSetStatus,
  fetchProcessedEmails,
  resumeDownloadHref,
  sendProcessedEmail,
  updateProcessedEmailStatus,
} from "../api";
import type { ProcessedEmail } from "../types";

interface Props {
  reloadKey: number;
  onChange: () => void;
}

const STATUS_LABELS: Record<string, string> = {
  new: "New",
  approved: "Approved",
  rejected: "Rejected / Redo",
  cancelled: "Cancelled",
  sent: "Sent",
};

// Non-archived statuses shown in the tracker.
const VISIBLE_STATUSES = ["new", "approved", "rejected", "cancelled", "sent"];

const COLUMNS = [
  { key: "status",   label: "Status",            width: 120 },
  { key: "subject",  label: "Subject",           width: 320 },
  { key: "from",     label: "From",              width: 220 },
  { key: "location", label: "Job Location",      width: 150 },
  { key: "date",     label: "Processing Date",   width: 170 },
  { key: "resume",   label: "Generated Resume",  width: 200 },
  { key: "actions",  label: "Actions",           width: 320 },
];

function formatDate(iso: string): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

export function ApplicationTracker({ reloadKey, onChange }: Props) {
  const [items, setItems] = useState<ProcessedEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [widths, setWidths] = useState<number[]>(COLUMNS.map((c) => c.width));
  const resizeRef = useRef<{ idx: number; startX: number; startW: number } | null>(null);

  const reload = () => {
    setLoading(true);
    fetchProcessedEmails()
      .then((data) => {
        setItems(data.filter((i) => VISIBLE_STATUSES.includes(i.status)));
        setSelected(new Set());
        setError(null);
      })
      .catch((e: Error) => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(reload, [reloadKey]);

  // --- column resize ---
  const onResizeStart = (idx: number) => (e: ReactMouseEvent) => {
    e.preventDefault();
    resizeRef.current = { idx, startX: e.clientX, startW: widths[idx] };
    window.addEventListener("mousemove", onResizing);
    window.addEventListener("mouseup", onResizeEnd);
  };
  const onResizing = (e: MouseEvent) => {
    const r = resizeRef.current;
    if (!r) return;
    const next = Math.max(70, r.startW + (e.clientX - r.startX));
    setWidths((w) => { const c = [...w]; c[r.idx] = next; return c; });
  };
  const onResizeEnd = () => {
    resizeRef.current = null;
    window.removeEventListener("mousemove", onResizing);
    window.removeEventListener("mouseup", onResizeEnd);
  };

  const act = async (messageId: string, fn: () => Promise<unknown>) => {
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

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const s = new Set(prev);
      s.has(id) ? s.delete(id) : s.add(id);
      return s;
    });
  };
  const allChecked = items.length > 0 && selected.size === items.length;
  const toggleAll = () => setSelected(allChecked ? new Set() : new Set(items.map((i) => i.message_id)));

  const runBulk = async (fn: () => Promise<unknown>) => {
    if (selected.size === 0) return;
    setBulkBusy(true);
    try {
      await fn();
      reload();
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBulkBusy(false);
    }
  };
  const ids = () => [...selected];

  if (loading) return <div className="pane pane--loading">Loading applications…</div>;
  if (error)   return <div className="pane pane--error">Error: {error}</div>;

  if (items.length === 0) {
    return (
      <div className="pane pane--empty">
        <h3>No applications yet</h3>
        <p>Click <b>Auto-Apply</b> or <b>Process Job Emails</b> in the header to scan your inbox.</p>
      </div>
    );
  }

  return (
    <div className="pane">
      <div className="pane__header">
        <h2 className="pane__title">Application Tracker</h2>
        <div className="pane__meta">{items.length} application{items.length === 1 ? "" : "s"}</div>
        {selected.size > 0 ? (
          <div className="bulkbar">
            <span className="bulkbar__count">{selected.size} selected</span>
            <button className="btn btn--tiny btn--send" disabled={bulkBusy}
              onClick={() => runBulk(() => bulkApproveSend(ids()))}>Approve &amp; Send Selected</button>
            <button className="btn btn--tiny" disabled={bulkBusy}
              onClick={() => runBulk(() => bulkSetStatus(ids(), "rejected"))}>Reject Selected</button>
            <button className="btn btn--tiny btn--ghost" disabled={bulkBusy}
              onClick={() => runBulk(() => bulkSetStatus(ids(), "cancelled"))}>Cancel Selected</button>
            <button className="btn btn--tiny btn--ghost" disabled={bulkBusy}
              onClick={() => runBulk(() => bulkSetStatus(ids(), "archived"))}>🗄 Archive Selected</button>
          </div>
        ) : null}
      </div>

      <table className="tbl tbl--resizable">
        <colgroup>
          <col style={{ width: 36 }} />
          {COLUMNS.map((c, i) => <col key={c.key} style={{ width: widths[i] }} />)}
        </colgroup>
        <thead>
          <tr>
            <th className="tbl__check">
              <input type="checkbox" checked={allChecked} onChange={toggleAll}
                title={allChecked ? "Deselect all" : "Select all"} />
            </th>
            {COLUMNS.map((c, i) => (
              <th key={c.key}>
                <span className="th__label">{c.label}</span>
                {i < COLUMNS.length - 1 ? (
                  <span className="col-resizer" onMouseDown={onResizeStart(i)} />
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((e) => {
            const busy = busyId === e.message_id;
            const checked = selected.has(e.message_id);
            return (
              <tr key={e.message_id} className={checked ? "tbl__row--selected" : ""}>
                <td className="tbl__check">
                  <input type="checkbox" checked={checked} onChange={() => toggleSelect(e.message_id)} />
                </td>
                <td><span className={`tag tag--${e.status}`}>{STATUS_LABELS[e.status] ?? e.status}</span></td>
                <td className="tbl__subject" title={e.subject}>{e.subject || "(no subject)"}</td>
                <td className="tbl__from" title={e.from_email}>{e.from_email}</td>
                <td title={e.job_location || ""}>{e.job_location ? e.job_location : <span className="tbl__muted">—</span>}</td>
                <td className="tbl__date">{formatDate(e.processed_at)}</td>
                <td>
                  {e.resume_filename ? (
                    <a className="link link--download" href={resumeDownloadHref(e.resume_download_url)}
                      target="_blank" rel="noreferrer">{e.resume_filename}</a>
                  ) : <span className="tbl__muted">—</span>}
                </td>
                <td className="tbl__actions">
                  {e.status === "new" ? (
                    <>
                      <button className="btn btn--tiny btn--send" disabled={busy}
                        onClick={() => act(e.message_id, () => approveSendEmail(e.message_id))}
                        title="Approve and send the reply with attached resume">
                        Approve &amp; Send Email
                      </button>
                      <button className="btn btn--tiny" disabled={busy}
                        onClick={() => act(e.message_id, () => updateProcessedEmailStatus(e.message_id, "rejected"))}>
                        Reject
                      </button>
                      <button className="btn btn--tiny btn--ghost" disabled={busy}
                        onClick={() => act(e.message_id, () => updateProcessedEmailStatus(e.message_id, "cancelled"))}>
                        Cancel
                      </button>
                    </>
                  ) : null}
                  {e.status === "approved" ? (
                    <button className="btn btn--tiny btn--send" disabled={busy}
                      onClick={() => act(e.message_id, () => sendProcessedEmail(e.message_id))}>
                      Send Email
                    </button>
                  ) : null}
                  {e.status === "rejected" ? (
                    <button className="btn btn--tiny" disabled={busy}
                      onClick={() => act(e.message_id, () => updateProcessedEmailStatus(e.message_id, "new"))}>
                      Regenerate
                    </button>
                  ) : null}
                  {e.status === "cancelled" ? (
                    <button className="btn btn--tiny" disabled={busy}
                      onClick={() => act(e.message_id, () => updateProcessedEmailStatus(e.message_id, "new"))}>
                      Restore
                    </button>
                  ) : null}
                  <button className="btn btn--tiny btn--ghost" disabled={busy}
                    onClick={() => act(e.message_id, () => updateProcessedEmailStatus(e.message_id, "archived"))}
                    title="Archive">🗄</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
