import { useState } from "react";

interface Props {
  running: boolean;
  onSubmit: (jd: string) => void;
  onProcessEmails: () => void;
}

export function ChatUI({ running, onSubmit, onProcessEmails }: Props) {
  const [jd, setJd] = useState("");

  const handleSend = () => {
    const trimmed = jd.trim();
    if (!trimmed || running) return;
    onSubmit(trimmed);
  };

  return (
    <div className="chat-ui">
      <div className="chat-ui__actions">
        <button
          className="btn btn--primary"
          onClick={onProcessEmails}
          disabled={running}
          title="Scan Gmail and generate resumes for recruiter emails"
        >
          Process Job Emails
        </button>
        <div className="chat-ui__hint">
          Or paste a job description below to generate a tailored resume on demand.
        </div>
      </div>

      <div className="chat-ui__composer">
        <textarea
          className="chat-ui__input"
          placeholder="Paste a job description here..."
          value={jd}
          onChange={(e) => setJd(e.target.value)}
          disabled={running}
          rows={10}
        />
        <div className="chat-ui__composer-actions">
          <span className="chat-ui__chars">{jd.length} chars</span>
          <button
            className="btn btn--send"
            onClick={handleSend}
            disabled={running || jd.trim().length === 0}
          >
            {running ? "Running…" : "Generate Resume"}
          </button>
        </div>
      </div>
    </div>
  );
}
