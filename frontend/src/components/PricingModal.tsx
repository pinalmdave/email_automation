interface Props {
  open: boolean;
  onClose: () => void;
}

interface Row {
  provider: string;
  model: string;
  inPerMtok: number;
  outPerMtok: number;
  cacheReadPerMtok: number | null;
  notes: string;
}

// Reference pricing only — USD per million tokens. Verify with each provider
// before relying on these numbers for billing decisions.
const ROWS: Row[] = [
  { provider: "Anthropic", model: "Claude Sonnet 4",   inPerMtok: 3.00,  outPerMtok: 15.00, cacheReadPerMtok: 0.30, notes: "Prompt caching available (ephemeral)" },
  { provider: "Anthropic", model: "Claude Opus 4",     inPerMtok: 15.00, outPerMtok: 75.00, cacheReadPerMtok: 1.50, notes: "Top Claude model; best reasoning" },
  { provider: "Anthropic", model: "Claude Haiku 3.5",  inPerMtok: 0.80,  outPerMtok: 4.00,  cacheReadPerMtok: 0.08, notes: "Fastest / cheapest Claude" },
  { provider: "OpenAI",    model: "GPT-4o",            inPerMtok: 2.50,  outPerMtok: 10.00, cacheReadPerMtok: 1.25, notes: "Flagship GPT-4 family" },
  { provider: "OpenAI",    model: "GPT-4o-mini",       inPerMtok: 0.15,  outPerMtok: 0.60,  cacheReadPerMtok: 0.075, notes: "Cheap tier" },
  { provider: "Google",    model: "Gemini 1.5 Pro",    inPerMtok: 1.25,  outPerMtok: 5.00,  cacheReadPerMtok: null, notes: "Up to 2M context" },
  { provider: "Google",    model: "Gemini 1.5 Flash",  inPerMtok: 0.075, outPerMtok: 0.30,  cacheReadPerMtok: null, notes: "Cheapest multimodal" },
];

export function PricingModal({ open, onClose }: Props) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <h3>Model Pricing Comparison</h3>
          <button className="btn btn--tiny" onClick={onClose}>Close</button>
        </div>
        <p className="modal__note">
          Reference pricing only. USD per 1M tokens. Currently the app routes all LLM
          calls to Claude — switching providers requires extra SDK wiring and API keys.
        </p>
        <table className="tbl tbl--pricing">
          <thead>
            <tr>
              <th>Provider</th>
              <th>Model</th>
              <th className="num">Input $/MTok</th>
              <th className="num">Output $/MTok</th>
              <th className="num">Cache read $/MTok</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r, i) => (
              <tr key={i}>
                <td>{r.provider}</td>
                <td><b>{r.model}</b></td>
                <td className="num">{r.inPerMtok.toFixed(2)}</td>
                <td className="num">{r.outPerMtok.toFixed(2)}</td>
                <td className="num">{r.cacheReadPerMtok === null ? "—" : r.cacheReadPerMtok.toFixed(2)}</td>
                <td className="tbl__muted">{r.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
