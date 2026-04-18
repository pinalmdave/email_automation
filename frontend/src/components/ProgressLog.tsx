import type { ProgressEvent } from "../types";

interface Props {
  events: ProgressEvent[];
  running: boolean;
  error: string | null;
}

function renderEvent(evt: ProgressEvent, idx: number) {
  if (evt.event === "started") {
    return (
      <li key={idx} className="log-item log-item--start">
        <span className="dot" /> Pipeline started
      </li>
    );
  }
  if (evt.event === "done") {
    return (
      <li key={idx} className="log-item log-item--done">
        <span className="dot dot--done" /> Done
        {evt.summary ? <div className="log-summary">{evt.summary}</div> : null}
      </li>
    );
  }
  if (evt.event === "error") {
    return (
      <li key={idx} className="log-item log-item--err">
        <span className="dot dot--err" /> Error: {evt.message}
      </li>
    );
  }
  // node_complete
  return (
    <li key={idx} className="log-item">
      <span className="dot" />
      <div className="log-item__body">
        <div className="log-item__label">{evt.label ?? evt.node}</div>
        {evt.current_email ? (
          <div className="log-item__sub">
            {evt.current_email.subject} · {evt.current_email.from_email}
          </div>
        ) : null}
        {evt.scanned_count !== undefined ? (
          <div className="log-item__sub">{evt.scanned_count} email(s) scanned</div>
        ) : null}
        {evt.resume ? (
          <div className="log-item__sub">
            Resume ready:{" "}
            <a
              href={`${(import.meta as any).env?.VITE_API_BASE_URL ?? ""}${evt.resume.download_url}`}
              target="_blank"
              rel="noreferrer"
            >
              {evt.resume.filename}
            </a>
            {evt.resume.role ? ` — ${evt.resume.role}` : ""}
          </div>
        ) : null}
        {evt.errors && evt.errors.length ? (
          <div className="log-item__sub log-item__sub--err">
            {evt.errors.map((e, i) => <div key={i}>• {e}</div>)}
          </div>
        ) : null}
      </div>
    </li>
  );
}

export function ProgressLog({ events, running, error }: Props) {
  return (
    <div className="progress-log">
      <div className="progress-log__title">
        Progress
        {running ? <span className="spinner" aria-label="running" /> : null}
      </div>
      {error ? <div className="progress-log__error">{error}</div> : null}
      {events.length === 0 && !running ? (
        <div className="progress-log__empty">No activity yet.</div>
      ) : (
        <ul className="progress-log__list">
          {events.map((e, i) => renderEvent(e, i))}
        </ul>
      )}
    </div>
  );
}
