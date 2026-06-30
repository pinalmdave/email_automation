import { useEffect, useState } from "react";
import { fetchApplyPlans, fetchConversations, fetchProcessedEmails } from "../api";
import type { ApplyPlan, Conversation, ProcessedEmail, UsageSnapshot } from "../types";
import type { TabKey } from "./Sidebar";

interface Props {
  usage: UsageSnapshot | null;
  reloadKey: number;
  lastError: string | null;
  lastSummary: string | null;
  onNavigate: (tab: TabKey) => void;
}

function fmtCost(n: number): string {
  if (!n) return "$0.00";
  return n < 0.01 ? `$${n.toFixed(6)}` : `$${n.toFixed(2)}`;
}

function timeAgo(iso: string): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

export function Dashboard({ usage, reloadKey, lastError, lastSummary, onNavigate }: Props) {
  const [newEmails, setNewEmails] = useState<ProcessedEmail[]>([]);
  const [pending, setPending] = useState<Conversation[]>([]);
  const [readyPlans, setReadyPlans] = useState<ApplyPlan[]>([]);

  useEffect(() => {
    fetchProcessedEmails("new").then(setNewEmails).catch(() => {});
    fetchConversations("pending").then(setPending).catch(() => {});
    fetchApplyPlans("ready").then(setReadyPlans).catch(() => {});
  }, [reloadKey]);

  const cards = [
    { key: "tracker" as TabKey, label: "Applications to review", value: newEmails.length, hint: "New, awaiting Approve & Send", tone: "blue" },
    { key: "conversations" as TabKey, label: "Pending replies", value: pending.length, hint: "Follow-up drafts to approve", tone: "violet" },
    { key: "apply" as TabKey, label: "Apply plans ready", value: readyPlans.length, hint: "From Apply-from-URL", tone: "green" },
  ];

  const actionItems = [
    ...newEmails.slice(0, 6).map((e) => ({
      id: `e-${e.message_id}`, kind: "Application", title: e.subject || "(no subject)",
      sub: e.from_email, when: e.processed_at, tab: "tracker" as TabKey,
    })),
    ...pending.slice(0, 4).map((c) => ({
      id: `c-${c.id}`, kind: "Reply", title: c.reply?.subject || c.original?.subject || "(reply)",
      sub: c.original?.from_email || "", when: c.updated_at, tab: "conversations" as TabKey,
    })),
  ];

  return (
    <div className="dash">
      <div className="dash__cards">
        {cards.map((c) => (
          <button key={c.key} className={`dash-card dash-card--${c.tone}`} onClick={() => onNavigate(c.key)}>
            <div className="dash-card__value">{c.value}</div>
            <div className="dash-card__label">{c.label}</div>
            <div className="dash-card__hint">{c.hint}</div>
          </button>
        ))}
        <div className="dash-card dash-card--muted">
          <div className="dash-card__value">{fmtCost(usage?.total?.cost_usd ?? 0)}</div>
          <div className="dash-card__label">All-time Claude spend</div>
          <div className="dash-card__hint">
            {(usage?.total?.total_tokens ?? 0).toLocaleString()} tokens · {usage?.total?.api_calls ?? 0} calls
          </div>
        </div>
      </div>

      {lastError ? (
        <div className="dash-alert dash-alert--error">
          <b>Last run error:</b> {lastError}
        </div>
      ) : lastSummary ? (
        <div className="dash-alert dash-alert--ok">
          <b>Last run:</b> {lastSummary}
        </div>
      ) : null}

      <div className="dash__section">
        <div className="dash__section-head">
          <h2 className="pane__title">Needs your response</h2>
          <span className="pane__meta">{actionItems.length} item{actionItems.length === 1 ? "" : "s"}</span>
        </div>
        {actionItems.length === 0 ? (
          <div className="pane pane--empty">
            <h3>You're all caught up 🎉</h3>
            <p>Run <b>Auto-Apply</b> or <b>Process Job Emails</b> from the top bar to find new positions.</p>
          </div>
        ) : (
          <ul className="dash-list">
            {actionItems.map((it) => (
              <li key={it.id} className="dash-list__item" onClick={() => onNavigate(it.tab)}>
                <span className={`tag tag--${it.kind === "Reply" ? "violet" : "new"}`}>{it.kind}</span>
                <span className="dash-list__title" title={it.title}>{it.title}</span>
                <span className="dash-list__sub" title={it.sub}>{it.sub}</span>
                <span className="dash-list__when">{timeAgo(it.when)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
