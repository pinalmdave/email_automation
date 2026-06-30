import { useState } from "react";
import { activateAccount, addAccount, deleteAccount } from "../api";
import type { EmailAccount } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
  accounts: EmailAccount[];
  onChanged: (accounts?: EmailAccount[]) => void;
}

export function AccountsModal({ open, onClose, accounts, onChanged }: Props) {
  const [email, setEmail] = useState("");
  const [appPassword, setAppPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const run = async (fn: () => Promise<unknown>, refresh?: (r: unknown) => EmailAccount[] | undefined) => {
    setBusy(true);
    setError(null);
    try {
      const r = await fn();
      onChanged(refresh ? refresh(r) : undefined);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleAdd = async () => {
    if (!email.trim() || !appPassword.trim()) {
      setError("Enter an email and its Gmail App Password");
      return;
    }
    await run(
      () => addAccount(email.trim(), appPassword.trim()),
      undefined
    );
    setEmail("");
    setAppPassword("");
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <h3>Connected Email Accounts</h3>
          <button className="btn btn--tiny" onClick={onClose}>Close</button>
        </div>
        <p className="modal__note">
          Add Gmail accounts with an <b>App Password</b> (not your login password). The
          selected account is used for scanning and sending. Credentials are verified on add.
        </p>

        {error ? <div className="pane pane--error" style={{ marginBottom: 12 }}>{error}</div> : null}

        <table className="tbl">
          <thead>
            <tr>
              <th>Email</th>
              <th>App Password</th>
              <th>Active</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {accounts.length === 0 ? (
              <tr><td colSpan={4} className="tbl__muted">No accounts connected yet.</td></tr>
            ) : accounts.map((a) => (
              <tr key={a.id}>
                <td>{a.email}{a.env_default ? " (env default)" : ""}</td>
                <td className="tbl__muted">{a.password_masked || "—"}</td>
                <td>{a.active ? <span className="tag tag--sent">active</span> : ""}</td>
                <td className="tbl__actions">
                  {!a.active && !a.env_default ? (
                    <button className="btn btn--tiny" disabled={busy}
                      onClick={() => run(() => activateAccount(a.id), (r) => (r as EmailAccount[]))}>
                      Use this
                    </button>
                  ) : null}
                  {!a.env_default ? (
                    <button className="btn btn--tiny btn--ghost" disabled={busy}
                      onClick={() => run(() => deleteAccount(a.id), (r) => (r as EmailAccount[]))}>
                      Remove
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="accounts-add">
          <h4 className="accounts-add__title">Connect a new account</h4>
          <div className="accounts-add__row">
            <input
              className="select input--text"
              type="email"
              placeholder="you@gmail.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <input
              className="select input--text"
              type="password"
              placeholder="16-char App Password"
              value={appPassword}
              onChange={(e) => setAppPassword(e.target.value)}
            />
            <button className="btn btn--primary btn--sm" disabled={busy} onClick={handleAdd}>
              {busy ? "Verifying…" : "Add account"}
            </button>
          </div>
          <p className="modal__note" style={{ marginTop: 6 }}>
            Generate an App Password at <b>myaccount.google.com/apppasswords</b> (requires 2-Step Verification).
          </p>
        </div>
      </div>
    </div>
  );
}
