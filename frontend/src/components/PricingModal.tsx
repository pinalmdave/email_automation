import { useEffect, useState } from "react";
import { fetchPricing } from "../api";
import type { PricingModel } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function PricingModal({ open, onClose }: Props) {
  const [models, setModels] = useState<PricingModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    fetchPricing()
      .then((r) => setModels(r.models))
      .catch((e: Error) => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  }, [open]);

  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <h3>Claude Model Pricing</h3>
          <button className="btn btn--tiny" onClick={onClose}>Close</button>
        </div>
        <p className="modal__note">
          Live pricing pulled from the server. USD per 1M tokens.
        </p>
        {loading ? (
          <div className="pane pane--loading">Loading pricing…</div>
        ) : error ? (
          <div className="pane pane--error">Error: {error}</div>
        ) : (
          <table className="tbl tbl--pricing">
            <thead>
              <tr>
                <th>Model</th>
                <th className="num">Input $/MTok</th>
                <th className="num">Output $/MTok</th>
                <th className="num">Cache write $/MTok</th>
                <th className="num">Cache read $/MTok</th>
                <th className="num">Context</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id}>
                  <td><b>{m.label}</b></td>
                  <td className="num">{m.input.toFixed(2)}</td>
                  <td className="num">{m.output.toFixed(2)}</td>
                  <td className="num">{m.cache_write.toFixed(2)}</td>
                  <td className="num">{m.cache_read.toFixed(2)}</td>
                  <td className="num">{m.context}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
