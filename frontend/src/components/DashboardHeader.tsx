import { useMemo, useState } from "react";
import type { AppConfig, EmailAccount, UsageSnapshot } from "../types";
import { UsagePanel } from "./UsagePanel";

interface Props {
  config: AppConfig | null;
  usage: UsageSnapshot | null;
  running: boolean;
  selectedFolders: string[];
  onFoldersChange: (v: string[]) => void;
  selectedHours: number;
  onHoursChange: (v: number) => void;
  selectedMaxIterations: number;
  onMaxIterationsChange: (v: number) => void;
  selectedThreshold: number;
  onThresholdChange: (v: number) => void;
  onProcessEmails: () => void;
  selectedAutoApplyHours: number;
  onAutoApplyHoursChange: (v: number) => void;
  onAutoApply: () => void;
  selectedModel: string;
  onModelChange: (m: string) => void;
  targetRoles: string;
  onTargetRolesChange: (v: string) => void;
  onComparePricing: () => void;
  accounts: EmailAccount[];
  onActivateAccount: (id: string) => void;
  onOpenAccounts: () => void;
}

const FALLBACK_MODELS = [
  { id: "claude-opus-4-8",   label: "Claude Opus 4.8" },
  { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
  { id: "claude-haiku-4-5",  label: "Claude Haiku 4.5" },
];

export function DashboardHeader({
  config, usage, running,
  selectedFolders, onFoldersChange,
  selectedHours, onHoursChange,
  selectedMaxIterations, onMaxIterationsChange,
  selectedThreshold, onThresholdChange,
  onProcessEmails,
  selectedAutoApplyHours, onAutoApplyHoursChange, onAutoApply,
  selectedModel, onModelChange,
  targetRoles, onTargetRolesChange,
  onComparePricing,
  accounts, onActivateAccount, onOpenAccounts,
}: Props) {
  const [foldersOpen, setFoldersOpen] = useState(false);
  const folders = config?.available_folders ?? [];
  const durations = config?.duration_options_hours ?? [24, 48, 72, 168];
  const autoApplyDurations = config?.auto_apply_duration_options_hours ?? [24, 48, 72, 120];
  const iterOptions = config?.max_iteration_options ?? [1, 2, 3, 4, 5];
  const thresholdOptions = config?.threshold_options ?? [0.70, 0.75, 0.80, 0.85, 0.90];
  const modelOptions = config?.model_options ?? FALLBACK_MODELS;
  const activeAccount = accounts.find((a) => a.active) ?? accounts[0];

  const folderSummary = useMemo(() => {
    if (selectedFolders.length === 0) return "All defaults";
    if (selectedFolders.length <= 2) return selectedFolders.join(", ");
    return `${selectedFolders.length} selected`;
  }, [selectedFolders]);

  const toggleFolder = (f: string) => {
    onFoldersChange(
      selectedFolders.includes(f)
        ? selectedFolders.filter((x) => x !== f)
        : [...selectedFolders, f]
    );
  };

  return (
    <header className="dashboard-header">
      <div className="dashboard-header__row dashboard-header__row--top">
        <div className="dashboard-header__title">Claude Smart Email App</div>
        <UsagePanel usage={usage} />
      </div>

      <div className="dashboard-header__row dashboard-header__row--controls">
        {/* Connected email accounts */}
        <div className="ctrl">
          <label className="ctrl__label">Connected Email Accounts</label>
          <div className="ctrl__value">
            <select
              className="select"
              value={activeAccount?.id ?? ""}
              onChange={(e) => onActivateAccount(e.target.value)}
              disabled={running || accounts.length === 0}
              title="Select the email account to use for scanning and sending"
            >
              {accounts.length === 0 ? (
                <option value="">No account connected</option>
              ) : (
                accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.email}{a.env_default ? " (default)" : ""}
                  </option>
                ))
              )}
            </select>
            <button className="btn btn--ghost btn--tiny" onClick={onOpenAccounts} title="Connect / manage email accounts">
              Manage
            </button>
          </div>
        </div>

        {/* Folders */}
        <div className="ctrl">
          <label className="ctrl__label">Folders</label>
          <div className="ctrl__value">
            <button
              className="pill pill--button"
              onClick={() => setFoldersOpen((v) => !v)}
              aria-expanded={foldersOpen}
            >
              {folderSummary} ▾
            </button>
            {foldersOpen ? (
              <div className="dropdown">
                {folders.length === 0 ? (
                  <div className="dropdown__empty">No folders configured</div>
                ) : folders.map((f) => (
                  <label key={f} className="dropdown__check">
                    <input
                      type="checkbox"
                      checked={selectedFolders.includes(f)}
                      onChange={() => toggleFolder(f)}
                    />
                    {f}
                  </label>
                ))}
                <div className="dropdown__footer">
                  <button className="btn btn--tiny" onClick={() => onFoldersChange([])}>Reset</button>
                  <button className="btn btn--tiny" onClick={() => setFoldersOpen(false)}>Done</button>
                </div>
              </div>
            ) : null}
          </div>
        </div>

        {/* Duration */}
        <div className="ctrl">
          <label className="ctrl__label">Lookback</label>
          <select
            className="select"
            value={selectedHours}
            onChange={(e) => onHoursChange(Number(e.target.value))}
          >
            {durations.map((h) => (
              <option key={h} value={h}>{h >= 168 ? `${h / 168} week${h/168>1?'s':''}` : `${h}h`}</option>
            ))}
          </select>
        </div>

        {/* Resume-loop quality controls */}
        <div className="ctrl" title="Max times the evaluator-optimizer loop re-generates per email">
          <label className="ctrl__label">Max iters</label>
          <select
            className="select"
            value={selectedMaxIterations}
            onChange={(e) => onMaxIterationsChange(Number(e.target.value))}
          >
            {iterOptions.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
        <div className="ctrl" title="Minimum evaluator score to accept a resume">
          <label className="ctrl__label">Quality</label>
          <select
            className="select"
            value={selectedThreshold}
            onChange={(e) => onThresholdChange(Number(e.target.value))}
          >
            {thresholdOptions.map((t) => (
              <option key={t} value={t}>{t.toFixed(2)}</option>
            ))}
          </select>
        </div>

        {/* Model */}
        <div className="ctrl">
          <label className="ctrl__label">Model</label>
          <div className="ctrl__value">
            <select
              className="select"
              value={selectedModel}
              onChange={(e) => onModelChange(e.target.value)}
            >
              {modelOptions.map((m) => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
            <button className="btn btn--ghost btn--tiny" onClick={onComparePricing}>
              Compare pricing
            </button>
          </div>
        </div>

        {/* Target roles */}
        <div className="ctrl ctrl--grow" title="Only emails whose role matches these are processed">
          <label className="ctrl__label">Target Roles (comma-separated)</label>
          <input
            className="select input--text"
            type="text"
            placeholder="e.g. AI Architect, AI Engineer, Cloud Architect"
            value={targetRoles}
            onChange={(e) => onTargetRolesChange(e.target.value)}
          />
        </div>

        <div className="dashboard-header__spacer" />

        <button className="btn btn--primary" onClick={onProcessEmails} disabled={running}>
          {running ? "Processing…" : "Process Job Emails"}
        </button>

        {/* Auto-Apply: scan INBOX for new positions within the chosen lookback */}
        <div className="ctrl ctrl--inline" title="Scan INBOX for new job positions in this lookback window, generate a resume for each, and queue drafts for 1-click review">
          <select
            className="select"
            value={selectedAutoApplyHours}
            onChange={(e) => onAutoApplyHoursChange(Number(e.target.value))}
            disabled={running}
            aria-label="Auto-Apply lookback window"
          >
            {autoApplyDurations.map((h) => (
              <option key={h} value={h}>{h}h</option>
            ))}
          </select>
          <button className="btn btn--primary" onClick={onAutoApply} disabled={running}>
            {running ? "Working…" : "Auto-Apply"}
          </button>
        </div>
      </div>
    </header>
  );
}
