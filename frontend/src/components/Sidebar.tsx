import React from 'react';
import { useAuth } from '../context/useAuth';
import { ShieldCheck, FolderKanban, Building2, Landmark, History, LogOut, X } from 'lucide-react';
import { AppearanceControl } from './AppearanceControl';

export type AppTab = 'projects' | 'verify' | 'financial' | 'runs';

interface SidebarProps {
  currentTab: AppTab;
  onSelectTab: (tab: AppTab) => void;
  selectedProjectName?: string;
  onClose?: () => void;
  showClose?: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  selectedProjectName,
  onClose,
  showClose = false,
}) => {
  const brandSubtitle = currentTab === 'financial' ? 'Financial Auditing' : 'Data Reconciliation';
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
          <span className="brand-subtitle">{brandSubtitle}</span>
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
        <button
          type="button"
          className={`nav-link ${currentTab === 'projects' ? 'active' : ''}`}
          onClick={() => onSelectTab('projects')}
          aria-current={currentTab === 'projects' ? 'page' : undefined}
        >
          <FolderKanban size={18} />
          <span>Projects</span>
        </button>
        <button
          type="button"
          className={`nav-link ${currentTab === 'verify' ? 'active' : ''}`}
          onClick={() => onSelectTab('verify')}
          aria-current={currentTab === 'verify' ? 'page' : undefined}
        >
          <Building2 size={18} />
          <span>Organization Verification</span>
        </button>
        <button
          type="button"
          className={`nav-link ${currentTab === 'financial' ? 'active' : ''}`}
          onClick={() => onSelectTab('financial')}
          aria-current={currentTab === 'financial' ? 'page' : undefined}
        >
          <Landmark size={18} />
          <span>Financial Auditing</span>
        </button>
        <button
          type="button"
          className={`nav-link ${currentTab === 'runs' ? 'active' : ''}`}
          onClick={() => onSelectTab('runs')}
          aria-current={currentTab === 'runs' ? 'page' : undefined}
        >
          <History size={18} />
          <span>Audit History</span>
        </button>

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
