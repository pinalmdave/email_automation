import { useCallback, useRef, useState } from "react";
import type { ProgressEvent, UsageSnapshot } from "../types";

export interface PipelineState {
  running: boolean;
  events: ProgressEvent[];
  usage: UsageSnapshot | null;
  error: string | null;
}

export function usePipelineWS(initialUsage: UsageSnapshot | null) {
  const [state, setState] = useState<PipelineState>({
    running: false,
    events: [],
    usage: initialUsage,
    error: null,
  });
  const wsRef = useRef<WebSocket | null>(null);

  const stop = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setState((s) => ({ ...s, running: false }));
  }, []);

  const start = useCallback((path: string, onOpen?: (ws: WebSocket) => void) => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    setState((s) => ({ ...s, running: true, events: [], error: null }));

    // Resolve WS URL: use VITE_API_BASE_URL if set (prod), else same origin (dev proxy).
    const apiBase = (import.meta as any).env?.VITE_API_BASE_URL as string | undefined;
    let wsUrl: string;
    if (apiBase) {
      const u = new URL(apiBase);
      const wsProto = u.protocol === "https:" ? "wss:" : "ws:";
      wsUrl = `${wsProto}//${u.host}${path}`;
    } else {
      const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
      wsUrl = `${wsProto}//${window.location.host}${path}`;
    }
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (onOpen) onOpen(ws);
    };

    ws.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data) as ProgressEvent;
        setState((s) => ({
          ...s,
          events: [...s.events, evt],
          usage: evt.usage ?? s.usage,
          error: evt.event === "error" ? evt.message ?? "Unknown error" : s.error,
        }));
      } catch (err) {
        console.error("Bad WS message", err);
      }
    };

    ws.onerror = () => {
      setState((s) => ({ ...s, error: "WebSocket error", running: false }));
    };

    ws.onclose = () => {
      setState((s) => ({ ...s, running: false }));
      wsRef.current = null;
    };
  }, []);

  return { ...state, start, stop };
}
