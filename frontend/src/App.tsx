import { useEffect, useState } from "react";
import { ChatUI } from "./components/ChatUI";
import { ProgressLog } from "./components/ProgressLog";
import { UsagePanel } from "./components/UsagePanel";
import { usePipelineWS } from "./hooks/usePipelineWS";
import type { UsageSnapshot } from "./types";

export default function App() {
  const [initialUsage, setInitialUsage] = useState<UsageSnapshot | null>(null);
  const pipeline = usePipelineWS(initialUsage);

  useEffect(() => {
    const apiBase = (import.meta as any).env?.VITE_API_BASE_URL ?? "";
    fetch(`${apiBase}/api/usage`)
      .then((r) => r.json())
      .then((u: UsageSnapshot) => setInitialUsage(u))
      .catch(() => { /* backend might not be up yet */ });
  }, []);

  const handleProcessEmails = () => {
    pipeline.start("/ws/process-emails");
  };

  const handleSubmitJD = (jd: string) => {
    pipeline.start("/ws/process-jd", (ws) => {
      ws.send(JSON.stringify({ job_description: jd }));
    });
  };

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__title">Claude Smart Email App</div>
        <UsagePanel usage={pipeline.usage ?? initialUsage} />
      </header>

      <main className="app__main">
        <section className="app__pane">
          <ChatUI
            running={pipeline.running}
            onSubmit={handleSubmitJD}
            onProcessEmails={handleProcessEmails}
          />
        </section>
        <section className="app__pane">
          <ProgressLog
            events={pipeline.events}
            running={pipeline.running}
            error={pipeline.error}
          />
        </section>
      </main>
    </div>
  );
}
