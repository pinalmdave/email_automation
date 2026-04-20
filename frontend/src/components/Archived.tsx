import { useEffect, useState } from "react";
import { bulkUnarchiveEmails, fetchProcessedEmails, resumeDownloadHref } from "../api";
import type { ProcessedEmail } from "../types";

interface Props {
  reloadKey: number;
  onChange: () => void;
}

function formatDate(iso: string): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

export function Archived({ reloadKey, onChange }: Props) {
  const [items, setItems] = useState<ProcessedEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [unarchiving, setUnarchiving] = useState(false);

  const reload = () => {
    setLoading(true);
    fetchProcessedEmails("archived")
      .then((data) => { setItems(data); setSelected(new Set()); setError(null); })
      .catch((e: Error) => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(reload, [reloadKey]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const s = new Set(prev);
      s.has(id) ? s.delete(id) : s.add(id);
      return s;
    });
  };

  const allChecked = items.length > 0 && selected.size === items.length;
  const toggleAll = () => {
    setSelected(allChecked ? new Set() : new Set(items.map((i) => i.message_id)));
  };

  const unarchiveSelected = async () => {
    if (selected.size === 0) return;
    setUnarchiving(true);
    try {
      await bulkUnarchiveEmails([...selected]);
      setItems((prev) => prev.filter((i) => !selected.has(i.message_id)));
      setSelected(new Set());
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUnarchiving(false);
    }
  };

  if (loading) return <div className="pane pane--loading">Loading archived emails…</div>;
  if (error)   return <div className="pane pane--error">Error: {error}</div>;

  if (items.length === 0) {
    return (
      <div className="pane pane--empty">
        <h3>No archived emails</h3>
        <p>Select emails in <b>Email Scan</b> and click <b>Archive Selected</b> to move them here.</p>
      </div>
    );
  }

  return (
    <div className="pane">
      <div className="pane__header">
        <h2 className="pane__title">Archived</h2>
        <div className="pane__meta">{items.length} archived</div>
        {selected.size > 0 && (
          <button
            className="btn btn--ghost btn--sm"
            onClick={unarchiveSelected}
            disabled={unarchiving}
            title="Move selected back to Email Scan"
          >
            {unarchiving ? "Restoring…" : `↩ Unarchive Selected (${selected.size})`}
          </button>
        )}
      </div>
      <table className="tbl">
        <thead>
          <tr>
            <th className="tbl__check">
              <input
                type="checkbox"
                checked={allChecked}
                onChange={toggleAll}
                title={allChecked ? "Deselect all" : "Select all"}
              />
            </th>
            <th>Subject</th>
            <th>From</th>
            <th>Archived</th>
            <th>Resume</th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => {
            const checked = selected.has(e.message_id);
            return (
              <tr key={e.message_id} className={checked ? "tbl__row--selected" : ""}>
                <td className="tbl__check">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleSelect(e.message_id)}
                  />
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
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
