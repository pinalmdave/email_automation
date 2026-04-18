import { useState } from "react";

export type ChatMode = "url" | "jd";

interface Props {
  mode: ChatMode;
  running: boolean;
  onSubmitJD: (jd: string) => void;
  onSubmitURL: (url: string) => void;
}

export function ChatUI({ mode, running, onSubmitJD, onSubmitURL }: Props) {
  const [jd, setJd] = useState("");
  const [url, setUrl] = useState("");

  const jdReady = !running && jd.trim().length > 0;
  const urlReady = !running && /^https?:\/\//i.test(url.trim());

  if (mode === "url") {
    return (
      <div className="chat-ui">
        <div className="chat-ui__section chat-ui__section--grow">
          <div className="chat-ui__section-label">Apply from URL</div>
          <div className="chat-ui__url-row">
            <input
              className="chat-ui__url"
              type="url"
              placeholder="https://www.linkedin.com/jobs/view/…  or Indeed/Dice/Monster/ZipRecruiter URL"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={running}
            />
            <button
              className="btn btn--primary"
              onClick={() => { if (urlReady) onSubmitURL(url.trim()); }}
              disabled={!urlReady}
            >
              {running ? "Running…" : "Fetch & generate"}
            </button>
          </div>
          <div className="chat-ui__hint">
            App fetches the posting, extracts the JD, generates a tailored
            resume, and creates a plan in <b>Apply History</b>. You review,
            then apply yourself on the job site.
          </div>
        </div>
      </div>
    );
  }

  // mode === "jd"
  return (
    <div className="chat-ui">
      <div className="chat-ui__section chat-ui__section--grow">
        <div className="chat-ui__section-label">Paste Job Description</div>
        <textarea
          className="chat-ui__input"
          placeholder="Paste a job description here..."
          value={jd}
          onChange={(e) => setJd(e.target.value)}
          disabled={running}
          rows={12}
        />
        <div className="chat-ui__composer-actions">
          <span className="chat-ui__chars">{jd.length} chars</span>
          <button
            className="btn btn--send"
            onClick={() => { if (jdReady) onSubmitJD(jd.trim()); }}
            disabled={!jdReady}
          >
            {running ? "Running…" : "Generate Resume"}
          </button>
        </div>
      </div>
    </div>
  );
}
