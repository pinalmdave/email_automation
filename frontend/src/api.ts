import type { AppConfig, Conversation, ProcessedEmail, UsageSnapshot } from "./types";

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

export async function fetchProcessedEmails(): Promise<ProcessedEmail[]> {
  const r = await jsonFetch<{ items: ProcessedEmail[] }>("/api/processed-emails");
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

export function resumeDownloadHref(downloadUrl: string): string {
  if (!downloadUrl) return "";
  return `${BASE}${downloadUrl}`;
}
