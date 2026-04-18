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
  const [selectedMaxIterations, setSelectedMaxIterations] = useState<number>(2);
  const [selectedThreshold, setSelectedThreshold] = useState<number>(0.80);
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
      if (c.default_max_iterations) setSelectedMaxIterations(c.default_max_iterations);
      if (c.default_acceptance_threshold) setSelectedThreshold(c.default_acceptance_threshold);
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

  const qualityPayload = () => ({
    max_iterations: selectedMaxIterations,
    acceptance_threshold: selectedThreshold,
  });

  const handleProcessEmails = () => {
    pipeline.start("/ws/process-emails", (ws) => {
      const payload: Record<string, unknown> = { ...qualityPayload() };
      if (selectedFolders.length > 0) payload.folders = selectedFolders;
      if (selectedHours > 0) payload.hours = selectedHours;
      ws.send(JSON.stringify(payload));
    });
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
    // Switch to Apply History so the user watches the plan land.
    setTab("apply");
  };

  const handleOpenPasteJD = () => setTab("paste_jd");
  const handleOpenApplyURL = () => setTab("apply_url");

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
          selectedMaxIterations={selectedMaxIterations}
          onMaxIterationsChange={setSelectedMaxIterations}
          selectedThreshold={selectedThreshold}
          onThresholdChange={setSelectedThreshold}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
          onProcessEmails={handleProcessEmails}
          onOpenPasteJD={handleOpenPasteJD}
          onOpenApplyURL={handleOpenApplyURL}
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
          </div>
        ) : null}
      </div>

      <PricingModal open={pricingOpen} onClose={() => setPricingOpen(false)} />
    </div>
  );
}
