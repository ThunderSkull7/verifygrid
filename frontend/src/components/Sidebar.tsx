import React from 'react';
import { useAuth } from '../context/useAuth';
import { ShieldCheck, FolderKanban, CheckCircle2, LogOut } from 'lucide-react';

interface SidebarProps {
  currentTab: string;
  onSelectTab: (tab: string) => void;
  selectedProjectName?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({ currentTab, onSelectTab, selectedProjectName }) => {
  const { user, logout } = useAuth();

  const getInitials = (name?: string | null, email?: string) => {
    if (name) {
      return name
        .split(' ')
        .map((n) => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2);
    }
    return email ? email[0].toUpperCase() : 'U';
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-icon">
          <ShieldCheck size={20} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span className="brand-title">VerifyGrid</span>
          {selectedProjectName && (
            <span
              style={{
                fontSize: '0.75rem',
                color: 'var(--text-dim)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: '160px',
                whiteSpace: 'nowrap',
              }}
              title={selectedProjectName}
            >
              Project: {selectedProjectName}
            </span>
          )}
        </div>
      </div>

      <nav className="sidebar-nav">
        <button
          className={`nav-link ${currentTab === 'projects' ? 'active' : ''}`}
          onClick={() => onSelectTab('projects')}
        >
          <FolderKanban size={18} />
          <span>Projects</span>
        </button>

        <button
          className={`nav-link ${currentTab === 'verify' ? 'active' : ''}`}
          onClick={() => onSelectTab('verify')}
        >
          <CheckCircle2 size={18} />
          <span>Reconciliation</span>
        </button>
      </nav>

      {user && (
        <div className="sidebar-footer">
          <div className="user-info">
            <div className="user-avatar">{getInitials(user.full_name, user.email)}</div>
            <div className="user-details">
              <span className="user-name">{user.full_name || user.email.split('@')[0]}</span>
              <span className="user-email">{user.email}</span>
            </div>
          </div>
          <button
            onClick={logout}
            title="Log out"
            style={{ color: 'var(--text-dim)', padding: 6, borderRadius: '4px' }}
            className="hover:text-white"
          >
            <LogOut size={16} />
          </button>
        </div>
      )}
    </aside>
  );
};
