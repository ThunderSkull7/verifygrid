import React from 'react';
import { useAuth } from '../context/useAuth';
import { ShieldCheck, FolderKanban, CheckCircle2, History, LogOut, X } from 'lucide-react';
import { AppearanceControl } from './AppearanceControl';

export type AppTab = 'projects' | 'verify' | 'runs';

interface SidebarProps {
  currentTab: AppTab;
  onSelectTab: (tab: AppTab) => void;
  selectedProjectName?: string;
  onClose?: () => void;
  showClose?: boolean;
}

const NAV_ITEMS: { tab: AppTab; label: string; icon: React.ComponentType<{ size?: number }> }[] = [
  { tab: 'projects', label: 'Projects', icon: FolderKanban },
  { tab: 'verify', label: 'Reconciliation', icon: CheckCircle2 },
  { tab: 'runs', label: 'Audit History', icon: History },
];

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  selectedProjectName,
  onClose,
  showClose = false,
}) => {
  const { user, logout } = useAuth();

  const getInitials = (name?: string | null, email?: string) => {
    if (name) {
      return name
        .split(' ')
        .filter(Boolean)
        .map((n) => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2);
    }
    return email ? email[0].toUpperCase() : 'U';
  };

  return (
    <aside className="sidebar" id="app-sidebar">
      <div className="sidebar-header">
        <div className="brand-icon">
          <ShieldCheck size={20} />
        </div>
        <div className="brand-text">
          <span className="brand-title">VerifyGrid</span>
          <span className="brand-subtitle">Data Reconciliation</span>
        </div>
        {showClose && (
          <button
            type="button"
            className="icon-btn sidebar-close"
            onClick={onClose}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        )}
      </div>

      <nav className="sidebar-nav" aria-label="Primary navigation">
        <span className="nav-section-label">Workspace</span>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.tab}
            type="button"
            className={`nav-link ${currentTab === item.tab ? 'active' : ''}`}
            onClick={() => onSelectTab(item.tab)}
            aria-current={currentTab === item.tab ? 'page' : undefined}
          >
            <item.icon size={18} />
            <span>{item.label}</span>
          </button>
        ))}

        {selectedProjectName && (
          <div className="sidebar-project">
            <span className="sidebar-project-label">Active project</span>
            <span className="sidebar-project-name" title={selectedProjectName}>
              {selectedProjectName}
            </span>
          </div>
        )}
      </nav>

      <div className="sidebar-spacer" />

      <AppearanceControl variant="sidebar" />

      {user && (
        <div className="sidebar-footer">
          <div className="user-info">
            <div className="user-avatar">{getInitials(user.full_name, user.email)}</div>
            <div className="user-details">
              <span className="user-name">{user.full_name || user.email.split('@')[0]}</span>
              <span className="user-email" title={user.email}>
                {user.email}
              </span>
            </div>
          </div>
          <button type="button" onClick={logout} title="Log out" aria-label="Log out" className="icon-btn">
            <LogOut size={16} />
          </button>
        </div>
      )}
    </aside>
  );
};
