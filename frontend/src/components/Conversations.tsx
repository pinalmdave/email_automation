import { useEffect, useState } from "react";
import {
  approveConversation,
  cancelConversation,
  editConversation,
  fetchConversations,
  resumeDownloadHref,
} from "../api";
import type { Conversation } from "../types";

interface Props {
  reloadKey: number;
  onChange: () => void;
}

export function Conversations({ reloadKey, onChange }: Props) {
  const [items, setItems] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchConversations("pending")
      .then((data) => {
        if (cancelled) return;
        setItems(data);
        setError(null);
        if (data.length > 0 && !data.find((x) => x.id === selectedId)) {
          setSelectedId(data[0].id);
        } else if (data.length === 0) {
          setSelectedId(null);
        }
      })
      .catch((e: Error) => { if (!cancelled) setError(e.message ?? String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadKey]);

  const selected = items.find((x) => x.id === selectedId) ?? null;

  const reload = async () => {
    try {
      const data = await fetchConversations("pending");
      setItems(data);
      if (!data.find((x) => x.id === selectedId)) {
        setSelectedId(data[0]?.id ?? null);
      }
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (loading) return <div className="pane pane--loading">Loading conversations…</div>;
  if (error)   return <div className="pane pane--error">Error: {error}</div>;
  if (items.length === 0) {
    return (
      <div className="pane pane--empty">
        <h3>No pending replies</h3>
        <p>Run <b>Process Job Emails</b> to scan your inbox; drafts will appear here for review.</p>
      </div>
    );
  }

  return (
    <div className="pane pane--split">
      <aside className="conv-list">
        {items.map((c) => (
          <button
            key={c.id}
            className={`conv-list__item ${c.id === selectedId ? "conv-list__item--active" : ""}`}
            onClick={() => setSelectedId(c.id)}
          >
            <div className="conv-list__subject">{c.reply.subject || "(no subject)"}</div>
            <div className="conv-list__meta">
              <span className={`tag tag--${c.kind}`}>
                {c.kind === "followup" ? "Follow-up" : "New reply"}
              </span>
              {c.intent ? <span className="tag tag--intent">{c.intent}</span> : null}
              <span className="conv-list__to">to {c.reply.to}</span>
            </div>
          </button>
        ))}
      </aside>
      {selected ? (
        <ConversationDetail key={selected.id} conv={selected} onDone={reload} />
      ) : null}
    </div>
  );
}


function ConversationDetail({ conv, onDone }: { conv: Conversation; onDone: () => void }) {
  const [subject, setSubject] = useState(conv.reply.subject);
  const [body, setBody] = useState(conv.reply.body);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const dirty = subject !== conv.reply.subject || body !== conv.reply.body;

  const run = async (action: "approve" | "cancel" | "save") => {
    setBusy(action); setErr(null);
    try {
      if (action === "save") {
        await editConversation(conv.id, subject, body);
      } else if (action === "cancel") {
        await cancelConversation(conv.id);
      } else {
        if (dirty) await editConversation(conv.id, subject, body);
        await approveConversation(conv.id);
      }
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="conv-detail">
      <div className="conv-detail__header">
        <div className="conv-detail__meta">
          <div><b>To:</b> {conv.reply.to}</div>
          <div><b>In reply to:</b> {conv.original.subject} <span className="tbl__muted">· from {conv.original.from_email}</span></div>
          {conv.resume_filename ? (
            <div>
              <b>Attachment:</b>{" "}
              <a
                className="link link--download"
                href={resumeDownloadHref(`/api/resume/${conv.resume_filename}`)}
                target="_blank"
                rel="noreferrer"
              >
                {conv.resume_filename}
              </a>
            </div>
          ) : null}
        </div>
      </div>

      {err ? <div className="conv-detail__error">{err}</div> : null}

      <label className="conv-detail__field">
        <span className="conv-detail__label">Subject</span>
        <input
          className="conv-detail__input"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          disabled={busy !== null}
        />
      </label>
      <label className="conv-detail__field conv-detail__field--grow">
        <span className="conv-detail__label">Body</span>
        <textarea
          className="conv-detail__textarea"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          disabled={busy !== null}
          rows={18}
        />
      </label>

      <div className="conv-detail__actions">
        <button
          className="btn btn--ghost"
          onClick={() => run("cancel")}
          disabled={busy !== null}
        >
          {busy === "cancel" ? "Cancelling…" : "Cancel"}
        </button>
        <div className="conv-detail__spacer" />
        <button
          className="btn"
          onClick={() => run("save")}
          disabled={busy !== null || !dirty}
        >
          {busy === "save" ? "Saving…" : "Save edits"}
        </button>
        <button
          className="btn btn--send"
          onClick={() => run("approve")}
          disabled={busy !== null}
          title="Send this email via SMTP (this actually sends — no more drafts)"
        >
          {busy === "approve" ? "Sending…" : "Approve & Send"}
        </button>
      </div>
    </section>
  );
}
