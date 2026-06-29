# Auto-Apply — Design Spec

**Date:** 2026-06-29
**Status:** Approved

## Goal

Add a one-click **Auto-Apply** button (with its own lookback dropdown) to the
dashboard. On click it scans the Gmail **INBOX** for new job positions within
the selected lookback window, generates a tailored resume for each, and queues
each application as a draft for **1-click human review/send**. Nothing is
emailed automatically.

## Key decisions

- **Human-in-the-loop, not auto-send.** Reuse the existing review/send flow:
  generated drafts land in *New Emails / Conversations* with status `new`; the
  user clicks Approve → Send. (No silent outbound email.)
- **New positions only, INBOX only.** Auto-Apply runs the recruiter scan and
  **skips** the follow-up-reply scan. The existing *Process Job Emails* button
  (recruiter + follow-ups, top Lookback control) is left untouched.
- **Own dropdown:** 24h / 48h / 72h / 120h, driving the scan lookback.
- Reuse the existing compiled LangGraph pipeline — no new agents/nodes.

## Backend — `api/server.py`

- `_auto_apply_state(hours, max_iters, threshold)`: base state with
  `run_recruiter_scan=True`, `run_followup_scan=False`,
  `scan_folders=["INBOX"]`, `scan_hours=hours`, plus quality overrides.
- `@app.websocket("/ws/auto-apply")`: read kickoff
  `{hours, max_iterations, acceptance_threshold}`; clamp `hours` to
  `{24, 48, 72, 120}` (default 24); run the existing `_stream_pipeline()`.
- `/api/config`: add `auto_apply_duration_options_hours: [24, 48, 72, 120]`.

## Frontend

- `DashboardHeader.tsx`: Auto-Apply dropdown (24/48/72/120h) + primary button,
  in the action row beside *Process Job Emails*. New props:
  `selectedAutoApplyHours`, `onAutoApplyHoursChange`, `onAutoApply`.
- `App.tsx`: `selectedAutoApplyHours` state (default 24); `handleAutoApply()`
  → `pipeline.start("/ws/auto-apply", ws => ws.send({ hours, ...quality }))`,
  then switch to the Email Scan tab. Reuses the existing progress dock.
- `types.ts`: add `auto_apply_duration_options_hours?: number[]` to `AppConfig`.

## Data flow

Click → WS scans INBOX (selected lookback) → resume generated + evaluated per
position → `render_and_draft_node` queues a draft → appears in New Emails /
Conversations (`new`) → user Approve → Send.

## Out of scope

- The `MODEL` dropdown (stale model list, not wired to backend — backend uses
  the `CLAUDE_MODEL` env var). Flagged separately.

## Deployment

Backend redeploy (zip) + frontend rebuild & Static Web App redeploy. Both go
fully live after the F1 CPU quota resets.
