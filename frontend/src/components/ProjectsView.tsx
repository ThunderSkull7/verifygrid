import React, { useEffect, useRef, useState } from 'react';
import type { Project } from '../types';
import { FolderKanban, Plus, Clock, ArrowRight, X, AlertCircle, Search, ArrowUpDown } from 'lucide-react';

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
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest' | 'name'>('newest');
  const nameInputRef = useRef<HTMLInputElement>(null);

  // Focus the name field when the modal opens and allow Escape to close it.
  useEffect(() => {
    if (!showCreateModal) return;
    nameInputRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !submitting) {
        setShowCreateModal(false);
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [showCreateModal, submitting]);

  const closeModal = () => {
    if (submitting) return;
    setShowCreateModal(false);
    setError(null);
  };

  const filteredProjects = projects
    .filter((project) => {
      const query = searchQuery.trim().toLocaleLowerCase();
      return (
        !query ||
        project.name.toLocaleLowerCase().includes(query) ||
        (project.description || '').toLocaleLowerCase().includes(query)
      );
    })
    .sort((a, b) => {
      if (sortOrder === 'name') return a.name.localeCompare(b.name);
      const aTime = new Date(a.created_at).getTime();
      const bTime = new Date(b.created_at).getTime();
      if (Number.isNaN(aTime) || Number.isNaN(bTime)) return 0;
      return sortOrder === 'newest' ? bTime - aTime : aTime - bTime;
    });

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
      <div className="page-header">
        <div>
          <h1 className="page-title">Projects</h1>
          <p className="page-subtitle">
            Organise datasets and verification workflows by workspace or audit cycle.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
          <Plus size={16} /> New project
        </button>
      </div>

      {showCreateModal && (
        <div className="modal-backdrop" onClick={closeModal}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-project-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <h3 className="card-title" id="create-project-title">
                  New verification project
                </h3>
                <p className="card-description">
                  Group related datasets and reconciliation runs into a single audit workspace.
                </p>
              </div>
              <button
                type="button"
                className="icon-btn"
                onClick={closeModal}
                aria-label="Close dialog"
              >
                <X size={18} />
              </button>
            </div>

            {error && (
              <div className="alert alert-error" role="alert">
                <AlertCircle size={16} />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label className="form-label" htmlFor="project-name">
                  Project name
                </label>
                <input
                  id="project-name"
                  ref={nameInputRef}
                  type="text"
                  required
                  className="form-input"
                  placeholder="e.g. Q4 general ledger reconciliation"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="project-description">
                  Description <span className="text-dim">(optional)</span>
                </label>
                <textarea
                  id="project-description"
                  className="form-textarea"
                  rows={3}
                  placeholder="Details regarding audit scope, datasets, or target systems…"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={closeModal}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={submitting || !name.trim()}>
                  {submitting ? (
                    <>
                      <span className="spinner on-primary" aria-hidden="true" /> Creating…
                    </>
                  ) : (
                    'Create project'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {loading && (
        <div className="project-grid" aria-busy="true" aria-label="Loading projects">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton skeleton-card" />
          ))}
        </div>
      )}

      {!loading && projects.length === 0 && (
        <div className="card empty-state">
          <div className="empty-icon">
            <FolderKanban size={26} />
          </div>
          <h3 className="empty-title">No projects yet</h3>
          <p className="empty-text">
            Create your first verification project to begin uploading CSV/XLSX files and
            reconciling records.
          </p>
          <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
            <Plus size={16} /> Create project
          </button>
        </div>
      )}

      {!loading && projects.length > 0 && (
        <>
          <div className="project-toolbar">
            <div className="project-search">
              <Search size={16} aria-hidden="true" />
              <input
                type="search"
                className="form-input"
                aria-label="Search projects"
                placeholder="Search by project name or description"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
            <label className="project-sort">
              <ArrowUpDown size={15} aria-hidden="true" />
              <span className="sr-only">Sort projects</span>
              <select
                className="form-input"
                aria-label="Sort projects"
                value={sortOrder}
                onChange={(event) => setSortOrder(event.target.value as 'newest' | 'oldest' | 'name')}
              >
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
                <option value="name">Name A–Z</option>
              </select>
            </label>
            <span className="project-count" role="status">
              {filteredProjects.length} of {projects.length} projects
            </span>
          </div>
          {filteredProjects.length > 0 ? (
            <div className="project-grid">
              {filteredProjects.map((proj) => {
            const isSelected = activeProject?.id === proj.id;
            const created = new Date(proj.created_at);
            return (
              <article key={proj.id} className={`project-card ${isSelected ? 'active' : ''}`}>
                <div className="project-card-top">
                  <div className="project-icon">
                    <FolderKanban size={18} />
                  </div>
                  {isSelected && (
                    <span className="badge badge-success">
                      <span className="badge-dot" aria-hidden="true" />
                      Active
                    </span>
                  )}
                </div>
                <h3 className="project-name">{proj.name}</h3>
                <p className="project-desc">{proj.description || 'No description provided.'}</p>
                <div className="project-meta">
                  <span>
                    <Clock size={12} /> Created{' '}
                    {Number.isNaN(created.getTime())
                      ? '—'
                      : created.toLocaleDateString(undefined, {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric',
                        })}
                  </span>
                </div>
                <button
                  className={`btn ${isSelected ? 'btn-secondary' : 'btn-primary'} btn-block`}
                  onClick={() => onSelectProject(proj)}
                >
                  {isSelected ? 'Open workspace' : 'Select project'} <ArrowRight size={14} />
                </button>
              </article>
            );
              })}
            </div>
          ) : (
            <div className="card empty-state">
              <div className="empty-icon">
                <Search size={24} />
              </div>
              <h3 className="empty-title">No matching projects</h3>
              <p className="empty-text">Try another search term or clear your search.</p>
              <button className="btn btn-secondary" onClick={() => setSearchQuery('')}>
                Clear search
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};
