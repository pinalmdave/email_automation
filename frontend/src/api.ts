import type { ApplyPlan, AppConfig, Conversation, EmailAccount, PricingModel, ProcessedEmail, UsageSnapshot } from "./types";

const BASE = (import.meta as any).env?.VITE_API_BASE_URL ?? "";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`${resp.status} ${resp.statusText}: ${text}`);
  }
  return resp.json();
}

export async function fetchConfig(): Promise<AppConfig> {
  return jsonFetch<AppConfig>("/api/config");
}

export async function fetchUsage(): Promise<UsageSnapshot> {
  return jsonFetch<UsageSnapshot>("/api/usage");
}

export async function fetchProcessedEmails(status?: string): Promise<ProcessedEmail[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  const r = await jsonFetch<{ items: ProcessedEmail[] }>(`/api/processed-emails${qs}`);
  return r.items;
}

export async function fetchConversations(status = "pending"): Promise<Conversation[]> {
  const r = await jsonFetch<{ items: Conversation[] }>(`/api/conversations?status=${encodeURIComponent(status)}`);
  return r.items;
}

export async function editConversation(
  id: string,
  subject?: string,
  body?: string
): Promise<Conversation> {
  return jsonFetch<Conversation>(`/api/conversations/${id}/edit`, {
    method: "POST",
    body: JSON.stringify({ subject, body }),
  });
}

export async function approveConversation(id: string): Promise<Conversation> {
  return jsonFetch<Conversation>(`/api/conversations/${id}/approve`, { method: "POST" });
}

export async function cancelConversation(id: string): Promise<Conversation> {
  return jsonFetch<Conversation>(`/api/conversations/${id}/cancel`, { method: "POST" });
}

export async function fetchApplyPlans(status = "all"): Promise<ApplyPlan[]> {
  const r = await jsonFetch<{ items: ApplyPlan[] }>(`/api/apply-plans?status=${encodeURIComponent(status)}`);
  return r.items;
}

export async function applyPlanMarkApplied(id: string, notes = ""): Promise<ApplyPlan> {
  return jsonFetch<ApplyPlan>(`/api/apply-plans/${id}/mark-applied`, {
    method: "POST",
    body: JSON.stringify({ notes }),
  });
}

export async function applyPlanCancel(id: string): Promise<ApplyPlan> {
  return jsonFetch<ApplyPlan>(`/api/apply-plans/${id}/cancel`, { method: "POST" });
}

export async function applyPlanDelete(id: string): Promise<void> {
  await jsonFetch<{ deleted: string }>(`/api/apply-plans/${id}`, { method: "DELETE" });
}

export async function updateProcessedEmailStatus(messageId: string, status: string): Promise<void> {
  await jsonFetch(`/api/processed-emails/${encodeURIComponent(messageId)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function sendProcessedEmail(messageId: string): Promise<void> {
  await jsonFetch(`/api/processed-emails/${encodeURIComponent(messageId)}/send`, {
    method: "POST",
  });
}

export async function bulkArchiveEmails(messageIds: string[]): Promise<{ count: number }> {
  return jsonFetch("/api/processed-emails/bulk-status", {
    method: "POST",
    body: JSON.stringify({ message_ids: messageIds, status: "archived" }),
  });
}

export async function bulkUnarchiveEmails(messageIds: string[]): Promise<{ count: number }> {
  return jsonFetch("/api/processed-emails/bulk-status", {
    method: "POST",
    body: JSON.stringify({ message_ids: messageIds, status: "new" }),
  });
}

export async function approveSendEmail(messageId: string): Promise<void> {
  await jsonFetch(`/api/processed-emails/${encodeURIComponent(messageId)}/approve-send`, {
    method: "POST",
  });
}

export async function bulkApproveSend(messageIds: string[]): Promise<{ sent_count: number; failed: { message_id: string; error: string }[] }> {
  return jsonFetch("/api/processed-emails/bulk-approve-send", {
    method: "POST",
    body: JSON.stringify({ message_ids: messageIds }),
  });
}

export async function bulkSetStatus(messageIds: string[], status: string): Promise<{ count: number }> {
  return jsonFetch("/api/processed-emails/bulk-status", {
    method: "POST",
    body: JSON.stringify({ message_ids: messageIds, status }),
  });
}

export async function fetchPricing(): Promise<{ currency: string; unit: string; models: PricingModel[] }> {
  return jsonFetch("/api/pricing");
}

export async function fetchAccounts(): Promise<EmailAccount[]> {
  const r = await jsonFetch<{ items: EmailAccount[] }>("/api/accounts");
  return r.items;
}

export async function addAccount(email: string, appPassword: string): Promise<EmailAccount> {
  return jsonFetch<EmailAccount>("/api/accounts", {
    method: "POST",
    body: JSON.stringify({ email, app_password: appPassword }),
  });
}

export async function activateAccount(id: string): Promise<EmailAccount[]> {
  const r = await jsonFetch<{ items: EmailAccount[] }>(`/api/accounts/${encodeURIComponent(id)}/activate`, { method: "POST" });
  return r.items;
}

export async function deleteAccount(id: string): Promise<EmailAccount[]> {
  const r = await jsonFetch<{ items: EmailAccount[] }>(`/api/accounts/${encodeURIComponent(id)}`, { method: "DELETE" });
  return r.items;
}

export function resumeDownloadHref(downloadUrl: string): string {
  if (!downloadUrl) return "";
  return `${BASE}${downloadUrl}`;
}
