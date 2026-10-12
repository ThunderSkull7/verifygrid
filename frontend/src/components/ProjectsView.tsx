import React, { useState } from 'react';
import type { Project } from '../types';
import { FolderKanban, Plus, Clock, FileSpreadsheet, ArrowRight } from 'lucide-react';

interface ProjectsViewProps {
  projects: Project[];
  activeProject: Project | null;
  onSelectProject: (project: Project) => void;
  onCreateProject: (name: string, description?: string) => Promise<void>;
  loading: boolean;
}

export const ProjectsView: React.FC<ProjectsViewProps> = ({
  projects,
  activeProject,
  onSelectProject,
  onCreateProject,
  loading,
}) => {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setError(null);
    setSubmitting(true);
    try {
      await onCreateProject(name.trim(), description.trim() || undefined);
      setName('');
      setDescription('');
      setShowCreateModal(false);
    } catch (err: any) {
      setError(err.message || 'Failed to create project');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 className="page-title">Projects</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginTop: 4 }}>
            Organize datasets and verification workflows by workspace or audit cycle.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
          <Plus size={16} /> New Project
        </button>
      </div>

      {showCreateModal && (
        <div className="card" style={{ maxWidth: 600, margin: '0 0 24px 0', border: '1px solid var(--primary)' }}>
          <div className="card-header">
            <h3 className="card-title">Create New Verification Project</h3>
            <button className="btn btn-secondary btn-sm" onClick={() => setShowCreateModal(false)}>
              Cancel
            </button>
          </div>
          {error && <div className="alert-box alert-error">{error}</div>}
          <form onSubmit={handleCreate}>
            <div className="form-group">
              <label className="form-label">Project Name</label>
              <input
                type="text"
                required
                className="form-input"
                placeholder="e.g. Q4 General Ledger Reconciliation"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Description (Optional)</label>
              <textarea
                className="form-input"
                rows={3}
                placeholder="Details regarding audit scopes, datasets, or target systems..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowCreateModal(false)}
              >
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? 'Creating...' : 'Create Project'}
              </button>
            </div>
          </form>
        </div>
      )}

      {loading && (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)' }}>
          Loading projects...
        </div>
      )}

      {!loading && projects.length === 0 && (
        <div className="card empty-state">
          <FolderKanban size={48} className="empty-state-icon" />
          <h3 className="empty-state-title">No projects found</h3>
          <p style={{ marginBottom: 20 }}>
            Create your first verification project to begin uploading CSV/XLSX files and reconciling records.
          </p>
          <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
            <Plus size={16} /> Create Project
          </button>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 20 }}>
        {projects.map((proj) => {
          const isSelected = activeProject?.id === proj.id;
          return (
            <div
              key={proj.id}
              className="card"
              style={{
                marginBottom: 0,
                borderColor: isSelected ? 'var(--primary)' : 'var(--border-color)',
                backgroundColor: isSelected ? 'rgba(59, 130, 246, 0.05)' : 'var(--bg-card)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: 8 }}>
                    {proj.name}
                  </h3>
                  {isSelected && (
                    <span className="badge badge-identical" style={{ fontSize: '0.7rem' }}>
                      Active
                    </span>
                  )}
                </div>
                <p
                  style={{
                    fontSize: '0.875rem',
                    color: 'var(--text-muted)',
                    marginBottom: 16,
                    minHeight: '40px',
                  }}
                >
                  {proj.description || 'No description provided.'}
                </p>
              </div>

              <div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 16,
                    fontSize: '0.75rem',
                    color: 'var(--text-dim)',
                    paddingTop: 12,
                    borderTop: '1px solid var(--border-subtle)',
                    marginBottom: 14,
                  }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Clock size={12} /> {new Date(proj.created_at).toLocaleDateString()}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <FileSpreadsheet size={12} /> Ready
                  </span>
                </div>

                <button
                  className={`btn ${isSelected ? 'btn-secondary' : 'btn-primary'}`}
                  style={{ width: '100%' }}
                  onClick={() => onSelectProject(proj)}
                >
                  {isSelected ? 'Open Workspace' : 'Select Project'} <ArrowRight size={14} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
