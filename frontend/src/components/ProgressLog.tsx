import type { ProgressEvent, QualitySettings } from "../types";

interface Props {
  events: ProgressEvent[];
  running: boolean;
  error: string | null;
  quality: QualitySettings | null;
}

function renderEvent(evt: ProgressEvent, idx: number, quality: QualitySettings | null) {
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
  const labelSuffix = evt.iteration ? ` (iteration ${evt.iteration})` : "";
  return (
    <li key={idx} className="log-item">
      <span className="dot" />
      <div className="log-item__body">
        <div className="log-item__label">
          {evt.label ?? evt.node}
          {labelSuffix}
        </div>
        {evt.current_email ? (
          <div className="log-item__sub">
            {evt.current_email.subject} · {evt.current_email.from_email}
          </div>
        ) : null}
        {evt.scanned_count !== undefined ? (
          <div className="log-item__sub">{evt.scanned_count} email(s) scanned</div>
        ) : null}
        {evt.evaluation ? (() => {
          const ev = evt.evaluation;
          const maxIters = quality?.max_iterations ?? 2;
          const capHit = !ev.accepted && typeof evt.iteration === "number" && evt.iteration >= maxIters;
          let verdict: string;
          let cls: string;
          if (ev.accepted) {
            verdict = "accepted ✓"; cls = "log-item__sub--ok";
          } else if (ev.recommend_decline) {
            verdict = "poor fit — recommending decline"; cls = "log-item__sub--err";
          } else if (capHit) {
            verdict = `rejected — iteration cap reached (${maxIters}), using last draft`; cls = "log-item__sub--warn";
          } else {
            verdict = "rejected — regenerating"; cls = "log-item__sub--warn";
          }
          return (
            <div className={`log-item__sub ${cls}`}>
              Score: {ev.score.toFixed(2)}{" · "}{verdict}
              {ev.recommend_decline && ev.decline_reason ? (
                <div className="log-item__feedback"><b>Why:</b> {ev.decline_reason}</div>
              ) : null}
              {ev.feedback ? (
                <div className="log-item__feedback">{ev.feedback}</div>
              ) : null}
            </div>
          );
        })() : null}
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

export function ProgressLog({ events, running, error, quality }: Props) {
  return (
    <div className="progress-log">
      <div className="progress-log__title">
        Progress
        {running ? <span className="spinner" aria-label="running" /> : null}
        {quality ? (
          <span className="progress-log__quality">
            cap {quality.max_iterations} · threshold {quality.acceptance_threshold.toFixed(2)}
          </span>
        ) : null}
      </div>
      {error ? <div className="progress-log__error">{error}</div> : null}
      {events.length === 0 && !running ? (
        <div className="progress-log__empty">No activity yet.</div>
      ) : (
        <ul className="progress-log__list">
          {events.map((e, i) => renderEvent(e, i, quality))}
        </ul>
      )}
    </div>
  );
}
