export type TabKey =
  | "dashboard"
  | "tracker"
  | "conversations"
  | "apply"
  | "apply_url"
  | "paste_jd"
  | "archived";

interface Props {
  active: TabKey;
  onChange: (tab: TabKey) => void;
  newEmailCount: number;
  archivedCount: number;
  pendingCount: number;
  applyReadyCount: number;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: "dashboard",     label: "Dashboard",           icon: "▤" },
  { key: "tracker",       label: "Application Tracker", icon: "✉" },
  { key: "conversations", label: "Conversations",       icon: "✎" },
  { key: "apply",         label: "Apply History",       icon: "⇢" },
  { key: "apply_url",     label: "Apply from URL",      icon: "🔗" },
  { key: "paste_jd",      label: "Paste JD",            icon: "💬" },
  { key: "archived",      label: "Archived",            icon: "🗄" },
];

export function Sidebar({ active, onChange, newEmailCount, archivedCount, pendingCount, applyReadyCount, collapsed, onToggleCollapse }: Props) {
  return (
    <nav className={`sidebar ${collapsed ? "sidebar--collapsed" : ""}`}>
      <div className="sidebar__brand">
        <button className="sidebar__toggle" onClick={onToggleCollapse} title={collapsed ? "Expand" : "Collapse"} aria-label="Toggle navigation">
          ☰
        </button>
        <span className="sidebar__brand-text">Smart Email</span>
      </div>
      <ul className="sidebar__list">
        {TABS.map((t) => {
          const badge =
            t.key === "tracker"       && newEmailCount > 0   ? newEmailCount :
            t.key === "archived"      && archivedCount > 0   ? archivedCount :
            t.key === "conversations" && pendingCount > 0    ? pendingCount :
            t.key === "apply"         && applyReadyCount > 0 ? applyReadyCount :
            undefined;
          const isActive = active === t.key;
          return (
            <li key={t.key}>
              <button
                className={`sidebar__item ${isActive ? "sidebar__item--active" : ""}`}
                onClick={() => onChange(t.key)}
                title={collapsed ? t.label : undefined}
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
