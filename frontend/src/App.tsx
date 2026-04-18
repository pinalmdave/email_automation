import { useEffect, useState } from "react";
import { fetchApplyPlans, fetchConfig, fetchConversations, fetchProcessedEmails, fetchUsage } from "./api";
import { ApplyHistory } from "./components/ApplyHistory";
import { ChatUI } from "./components/ChatUI";
import { Conversations } from "./components/Conversations";
import { DashboardHeader } from "./components/DashboardHeader";
import { PricingModal } from "./components/PricingModal";
import { ProcessedEmails } from "./components/ProcessedEmails";
import { ProgressLog } from "./components/ProgressLog";
import { Sidebar, type TabKey } from "./components/Sidebar";
import { usePipelineWS } from "./hooks/usePipelineWS";
import type { AppConfig, UsageSnapshot } from "./types";

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [initialUsage, setInitialUsage] = useState<UsageSnapshot | null>(null);
  const [tab, setTab] = useState<TabKey>("processed");
  const [selectedFolders, setSelectedFolders] = useState<string[]>([]);
  const [selectedHours, setSelectedHours] = useState<number>(24);
  const [selectedModel, setSelectedModel] = useState<string>("claude-sonnet-4-20250514");
  const [pricingOpen, setPricingOpen] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [processedCount, setProcessedCount] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);
  const [applyReadyCount, setApplyReadyCount] = useState(0);
  const pipeline = usePipelineWS(initialUsage);

  useEffect(() => {
    fetchConfig().then((c) => {
      setConfig(c);
      setSelectedHours(c.default_hours || 24);
    }).catch(() => { /* backend may not be up */ });
    fetchUsage().then(setInitialUsage).catch(() => { /* same */ });
  }, []);

  useEffect(() => {
    fetchProcessedEmails().then((items) => setProcessedCount(items.length)).catch(() => {});
    fetchConversations("pending").then((items) => setPendingCount(items.length)).catch(() => {});
    fetchApplyPlans("all")
      .then((items) => setApplyReadyCount(items.filter((i) => i.status === "ready").length))
      .catch(() => {});
  }, [reloadKey]);

  // Refresh lists whenever the pipeline finishes a run.
  useEffect(() => {
    if (!pipeline.running && pipeline.events.some((e) => e.event === "done")) {
      setReloadKey((k) => k + 1);
    }
  }, [pipeline.running, pipeline.events]);

  const handleProcessEmails = () => {
    pipeline.start("/ws/process-emails", (ws) => {
      const payload: Record<string, unknown> = {};
      if (selectedFolders.length > 0) payload.folders = selectedFolders;
      if (selectedHours > 0) payload.hours = selectedHours;
      ws.send(JSON.stringify(payload));
    });
  };

  const handleSubmitJD = (jd: string) => {
    pipeline.start("/ws/process-jd", (ws) => {
      ws.send(JSON.stringify({ job_description: jd }));
    });
  };

  const handleSubmitURL = (url: string) => {
    pipeline.start("/ws/apply-from-url", (ws) => {
      ws.send(JSON.stringify({ url }));
    });
    // Switch the user to the Apply History tab so they see the plan appear.
    setTab("apply");
  };

  return (
    <div className="app">
      <Sidebar
        active={tab}
        onChange={setTab}
        pendingCount={pendingCount}
        processedCount={processedCount}
        applyReadyCount={applyReadyCount}
      />
      <div className="app__main">
        <DashboardHeader
          config={config}
          usage={pipeline.usage ?? initialUsage}
          running={pipeline.running}
          selectedFolders={selectedFolders}
          onFoldersChange={setSelectedFolders}
          selectedHours={selectedHours}
          onHoursChange={setSelectedHours}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
          onProcessEmails={handleProcessEmails}
          onOpenChat={() => setTab("chat")}
          onComparePricing={() => setPricingOpen(true)}
          onAddGmail={() => alert("Adding another Gmail account is coming soon.")}
        />

        <div className="app__content">
          {tab === "processed" ? (
            <ProcessedEmails reloadKey={reloadKey} />
          ) : tab === "conversations" ? (
            <Conversations reloadKey={reloadKey} onChange={() => setReloadKey((k) => k + 1)} />
          ) : tab === "apply" ? (
            <ApplyHistory reloadKey={reloadKey} onChange={() => setReloadKey((k) => k + 1)} />
          ) : (
            <div className="chat-layout">
              <ChatUI
                running={pipeline.running}
                onSubmitJD={handleSubmitJD}
                onSubmitURL={handleSubmitURL}
                onProcessEmails={handleProcessEmails}
              />
              <ProgressLog
                events={pipeline.events}
                running={pipeline.running}
                error={pipeline.error}
              />
            </div>
          )}
        </div>

        {(pipeline.running || pipeline.events.length > 0) && tab !== "chat" ? (
          <div className="app__progress-dock">
            <ProgressLog
              events={pipeline.events}
              running={pipeline.running}
              error={pipeline.error}
            />
          </div>
        ) : null}
      </div>

      <PricingModal open={pricingOpen} onClose={() => setPricingOpen(false)} />
    </div>
  );
}
