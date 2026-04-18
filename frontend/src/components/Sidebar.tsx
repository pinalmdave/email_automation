export type TabKey = "processed" | "conversations" | "chat";

interface Props {
  active: TabKey;
  onChange: (tab: TabKey) => void;
  pendingCount: number;
  processedCount: number;
}

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: "processed",     label: "Processed Emails", icon: "✉" },
  { key: "conversations", label: "Conversations",    icon: "✎" },
  { key: "chat",          label: "Chat (paste JD)",  icon: "💬" },
];

export function Sidebar({ active, onChange, pendingCount, processedCount }: Props) {
  return (
    <nav className="sidebar">
      <div className="sidebar__brand">Smart Email</div>
      <ul className="sidebar__list">
        {TABS.map((t) => {
          const badge =
            t.key === "processed" && processedCount > 0 ? processedCount :
            t.key === "conversations" && pendingCount > 0 ? pendingCount :
            undefined;
          const isActive = active === t.key;
          return (
            <li key={t.key}>
              <button
                className={`sidebar__item ${isActive ? "sidebar__item--active" : ""}`}
                onClick={() => onChange(t.key)}
              >
                <span className="sidebar__icon" aria-hidden>{t.icon}</span>
                <span className="sidebar__label">{t.label}</span>
                {badge !== undefined ? (
                  <span className="sidebar__badge">{badge}</span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
