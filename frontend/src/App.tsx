import { useEffect, useMemo, useState } from "react";
import { activateAccount, fetchApplyPlans, fetchConfig, fetchConversations, fetchProcessedEmails, fetchUsage } from "./api";
import { AccountsModal } from "./components/AccountsModal";
import { ApplyHistory } from "./components/ApplyHistory";
import { Archived } from "./components/Archived";
import { ApplicationTracker } from "./components/ApplicationTracker";
import { ChatUI } from "./components/ChatUI";
import { Conversations } from "./components/Conversations";
import { Dashboard } from "./components/Dashboard";
import { DashboardHeader } from "./components/DashboardHeader";
import { PipelineGraph } from "./components/PipelineGraph";
import { PricingModal } from "./components/PricingModal";
import { ProgressLog } from "./components/ProgressLog";
import { Sidebar, type TabKey } from "./components/Sidebar";
import { usePipelineWS } from "./hooks/usePipelineWS";
import type { AppConfig, EmailAccount, UsageSnapshot } from "./types";

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [initialUsage, setInitialUsage] = useState<UsageSnapshot | null>(null);
  const [tab, setTab] = useState<TabKey>("dashboard");
  const [selectedFolders, setSelectedFolders] = useState<string[]>([]);
  const [selectedHours, setSelectedHours] = useState<number>(24);
  const [selectedAutoApplyHours, setSelectedAutoApplyHours] = useState<number>(24);
  const [selectedMaxIterations, setSelectedMaxIterations] = useState<number>(2);
  const [selectedThreshold, setSelectedThreshold] = useState<number>(0.80);
  const [selectedModel, setSelectedModel] = useState<string>("claude-opus-4-8");
  const [targetRoles, setTargetRoles] = useState<string>("");
  const [jobLocation, setJobLocation] = useState<string>("");
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const [pricingOpen, setPricingOpen] = useState(false);
  const [accountsOpen, setAccountsOpen] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [newEmailCount, setNewEmailCount] = useState(0);
  const [archivedCount, setArchivedCount] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);
  const [applyReadyCount, setApplyReadyCount] = useState(0);
  const pipeline = usePipelineWS(initialUsage);

  const loadConfig = () => {
    fetchConfig().then((c) => {
      setConfig(c);
      setSelectedHours(c.default_hours || 24);
      if (c.default_max_iterations) setSelectedMaxIterations(c.default_max_iterations);
      if (c.default_acceptance_threshold) setSelectedThreshold(c.default_acceptance_threshold);
      if (c.default_model) setSelectedModel((m) => m || c.default_model || m);
      if (c.accounts) setAccounts(c.accounts);
    }).catch(() => {});
  };

  useEffect(() => {
    loadConfig();
    fetchUsage().then(setInitialUsage).catch(() => {});
  }, []);

  useEffect(() => {
    fetchProcessedEmails("new").then((items) => setNewEmailCount(items.length)).catch(() => {});
    fetchProcessedEmails().then((items) => {
      setArchivedCount(items.filter((i) => i.status === "archived").length);
    }).catch(() => {});
    fetchConversations("pending").then((items) => setPendingCount(items.length)).catch(() => {});
    fetchApplyPlans("all").then((items) => setApplyReadyCount(items.filter((i) => i.status === "ready").length)).catch(() => {});
  }, [reloadKey]);

  useEffect(() => {
    if (!pipeline.running && pipeline.events.some((e) => e.event === "done")) {
      setReloadKey((k) => k + 1);
    }
  }, [pipeline.running, pipeline.events]);

  const lastSummary = useMemo(() => {
    for (let i = pipeline.events.length - 1; i >= 0; i--) {
      if (pipeline.events[i].summary) return pipeline.events[i].summary ?? null;
    }
    return null;
  }, [pipeline.events]);

  const qualityPayload = () => ({
    max_iterations: selectedMaxIterations,
    acceptance_threshold: selectedThreshold,
    model: selectedModel,
    target_roles: targetRoles,
    job_location: jobLocation,
  });

  const handleProcessEmails = () => {
    pipeline.start("/ws/process-emails", (ws) => {
      const payload: Record<string, unknown> = { ...qualityPayload() };
      if (selectedFolders.length > 0) payload.folders = selectedFolders;
      if (selectedHours > 0) payload.hours = selectedHours;
      ws.send(JSON.stringify(payload));
    });
    setTab("tracker");
  };

  const handleAutoApply = () => {
    pipeline.start("/ws/auto-apply", (ws) => {
      ws.send(JSON.stringify({ hours: selectedAutoApplyHours, ...qualityPayload() }));
    });
    setTab("tracker");
  };

  const handleSubmitJD = (jd: string) => {
    pipeline.start("/ws/process-jd", (ws) => {
      ws.send(JSON.stringify({ job_description: jd, ...qualityPayload() }));
    });
  };

  const handleSubmitURL = (url: string) => {
    pipeline.start("/ws/apply-from-url", (ws) => {
      ws.send(JSON.stringify({ url, ...qualityPayload() }));
    });
    setTab("apply");
  };

  const handleActivateAccount = (id: string) => {
    activateAccount(id).then((items) => { setAccounts(items); loadConfig(); }).catch(() => {});
  };

  const handleAccountsChanged = (next?: EmailAccount[]) => {
    if (next) setAccounts(next);
    loadConfig();
  };

  return (
    <div className={`app ${navCollapsed ? "app--nav-collapsed" : ""}`}>
      <Sidebar
        active={tab}
        onChange={setTab}
        newEmailCount={newEmailCount}
        archivedCount={archivedCount}
        pendingCount={pendingCount}
        applyReadyCount={applyReadyCount}
        collapsed={navCollapsed}
        onToggleCollapse={() => setNavCollapsed((v) => !v)}
      />
      <div className="app__main">
        {tab === "dashboard" ? (
          <DashboardHeader
            config={config}
            usage={pipeline.usage ?? initialUsage}
            running={pipeline.running}
            selectedFolders={selectedFolders}
            onFoldersChange={setSelectedFolders}
            selectedHours={selectedHours}
            onHoursChange={setSelectedHours}
            selectedMaxIterations={selectedMaxIterations}
            onMaxIterationsChange={setSelectedMaxIterations}
            selectedThreshold={selectedThreshold}
            onThresholdChange={setSelectedThreshold}
            selectedModel={selectedModel}
            onModelChange={setSelectedModel}
            targetRoles={targetRoles}
            onTargetRolesChange={setTargetRoles}
            jobLocation={jobLocation}
            onJobLocationChange={setJobLocation}
            onProcessEmails={handleProcessEmails}
            selectedAutoApplyHours={selectedAutoApplyHours}
            onAutoApplyHoursChange={setSelectedAutoApplyHours}
            onAutoApply={handleAutoApply}
            onComparePricing={() => setPricingOpen(true)}
            accounts={accounts}
            onActivateAccount={handleActivateAccount}
            onOpenAccounts={() => setAccountsOpen(true)}
          />
        ) : null}

        <div className="app__content">
          {tab === "dashboard" ? (
            <Dashboard
              usage={pipeline.usage ?? initialUsage}
              reloadKey={reloadKey}
              lastError={pipeline.error}
              lastSummary={lastSummary}
              onNavigate={setTab}
            />
          ) : tab === "tracker" ? (
            <ApplicationTracker reloadKey={reloadKey} onChange={() => setReloadKey((k) => k + 1)} />
          ) : tab === "archived" ? (
            <Archived reloadKey={reloadKey} onChange={() => setReloadKey((k) => k + 1)} />
          ) : tab === "conversations" ? (
            <Conversations reloadKey={reloadKey} onChange={() => setReloadKey((k) => k + 1)} />
          ) : tab === "apply" ? (
            <ApplyHistory reloadKey={reloadKey} onChange={() => setReloadKey((k) => k + 1)} />
          ) : (
            <div className="chat-layout">
              <ChatUI
                mode={tab === "apply_url" ? "url" : "jd"}
                running={pipeline.running}
                onSubmitJD={handleSubmitJD}
                onSubmitURL={handleSubmitURL}
              />
              <ProgressLog
                events={pipeline.events}
                running={pipeline.running}
                error={pipeline.error}
                quality={pipeline.quality}
              />
              <PipelineGraph events={pipeline.events} running={pipeline.running} />
            </div>
          )}
        </div>

        {(pipeline.running || pipeline.events.length > 0) &&
         tab !== "apply_url" && tab !== "paste_jd" ? (
          <div className="app__progress-dock">
            <ProgressLog
              events={pipeline.events}
              running={pipeline.running}
              error={pipeline.error}
              quality={pipeline.quality}
            />
            <PipelineGraph events={pipeline.events} running={pipeline.running} />
          </div>
        ) : null}
      </div>

      <PricingModal open={pricingOpen} onClose={() => setPricingOpen(false)} />
      <AccountsModal
        open={accountsOpen}
        onClose={() => setAccountsOpen(false)}
        accounts={accounts}
        onChanged={handleAccountsChanged}
      />
    </div>
  );
}
