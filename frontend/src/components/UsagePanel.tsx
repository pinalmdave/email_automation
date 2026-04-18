import type { UsageSnapshot } from "../types";

interface Props {
  usage: UsageSnapshot | null;
}

function fmtNumber(n: number): string {
  return n.toLocaleString();
}

function fmtCost(n: number): string {
  if (n === 0) return "$0.0000";
  if (n < 0.01) return `$${n.toFixed(6)}`;
  return `$${n.toFixed(4)}`;
}

export function UsagePanel({ usage }: Props) {
  const session = usage?.session;
  const total = usage?.total;

  return (
    <div className="usage-panel">
      <div className="usage-panel__title">Claude API Usage</div>
      <div className="usage-panel__grid">
        <div className="usage-col">
          <div className="usage-col__label">This session</div>
          <div className="usage-col__cost">{fmtCost(session?.cost_usd ?? 0)}</div>
          <div className="usage-col__tokens">
            {fmtNumber(session?.total_tokens ?? 0)} tokens · {session?.api_calls ?? 0} calls
          </div>
          <div className="usage-col__sub">
            in {fmtNumber(session?.input_tokens ?? 0)} · out {fmtNumber(session?.output_tokens ?? 0)}
          </div>
        </div>
        <div className="usage-col">
          <div className="usage-col__label">All time</div>
          <div className="usage-col__cost">{fmtCost(total?.cost_usd ?? 0)}</div>
          <div className="usage-col__tokens">
            {fmtNumber(total?.total_tokens ?? 0)} tokens · {total?.api_calls ?? 0} calls
          </div>
          <div className="usage-col__sub">
            in {fmtNumber(total?.input_tokens ?? 0)} · out {fmtNumber(total?.output_tokens ?? 0)}
          </div>
        </div>
      </div>
    </div>
  );
}
