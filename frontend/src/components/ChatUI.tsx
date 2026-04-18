import { useState } from "react";

interface Props {
  running: boolean;
  onSubmitJD: (jd: string) => void;
  onSubmitURL: (url: string) => void;
  onProcessEmails: () => void;
}

export function ChatUI({ running, onSubmitJD, onSubmitURL, onProcessEmails }: Props) {
  const [jd, setJd] = useState("");
  const [url, setUrl] = useState("");

  const jdReady = !running && jd.trim().length > 0;
  const urlReady = !running && /^https?:\/\//i.test(url.trim());

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
          Or paste a job URL / JD below to generate a tailored resume.
        </div>
      </div>

      <div className="chat-ui__section">
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
          App fetches the posting, extracts the JD, generates a tailored resume,
          and creates a plan in <b>Apply History</b>. You review, then apply
          yourself on the job site.
        </div>
      </div>

      <div className="chat-ui__section chat-ui__section--grow">
        <div className="chat-ui__section-label">Paste Job Description</div>
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
