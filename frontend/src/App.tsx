import React, { useEffect, useState } from 'react';
import { useAuth } from './context/useAuth';
import { AuthScreen } from './components/AuthScreen';
import { Sidebar } from './components/Sidebar';
import type { AppTab } from './components/Sidebar';
import { ProjectsView } from './components/ProjectsView';
import { ReconciliationWizard } from './components/ReconciliationWizard';
import { AuditHistoryView } from './components/AuditHistoryView';
import { AppearanceControl } from './components/AppearanceControl';
import type { Project, PreprocessingResult, SourceFile, UploadedDataset } from './types';
import { api } from './services/api';
import { AlertCircle, Menu, ShieldCheck } from 'lucide-react';

/** Suggest a neutral, institution-friendly label from the uploaded filename.
 *  Recognisable categories map to familiar names; everything else keeps the
 *  filename base. This is only a displayed suggestion, never a role inference. */
const suggestDatasetLabel = (filename: string, existing: UploadedDataset[]): string => {
  const lower = filename.toLowerCase();
  let base = 'Records';
  if (/academ/.test(lower)) base = 'Academic Records';
  else if (/hostel|dorm/.test(lower)) base = 'Hostel Records';
  else if (/id[_ -]?card|membership/.test(lower)) base = 'ID Card Records';
  else {
    // Filename-derived: drop extension, humanize a little.
    base = filename.replace(/\.(csv|xlsx)$/i, '').trim() || 'Records';
  }
  // Ensure uniqueness across the session list.
  if (!existing.some((d) => d.label === base)) return base;
  let n = 2;
  while (existing.some((d) => d.label === `${base} (${n})`)) n += 1;
  return `${base} (${n})`;
};

type ApiStatus = 'checking' | 'online' | 'offline';

const TAB_META: Record<AppTab, { title: string; crumb: string }> = {
  projects: { title: 'Projects', crumb: 'Workspaces' },
  verify: { title: 'Organization Verification', crumb: 'Verify records' },
  financial: { title: 'Financial Auditing', crumb: 'Reconcile financial datasets' },
  runs: { title: 'Verification history', crumb: 'Persistent runs' },
};

export const App: React.FC = () => {
  const { isAuthenticated, isLoading } = useAuth();
  const [activeTab, setActiveTab] = useState<AppTab>('projects');
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [loadingProjects, setLoadingProjects] = useState<boolean>(false);
  const [projectLoadError, setProjectLoadError] = useState<string | null>(null);
  const [projectReloadKey, setProjectReloadKey] = useState<number>(0);
  const [mobileNavOpen, setMobileNavOpen] = useState<boolean>(false);
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking');

  // Verification state for active workspace
  const [uploadedDatasets, setUploadedDatasets] = useState<UploadedDataset[]>([]);

  const updateDataset = (fileId: string, patch: Partial<UploadedDataset>) => {
    setUploadedDatasets((prev) => prev.map((d) => (d.id === fileId ? { ...d, ...patch } : d)));
  };
  const removeDataset = (fileId: string) => {
    setUploadedDatasets((prev) => prev.filter((d) => d.id !== fileId));
  };
  // Batch 7: explicit worksheet selection for XLSX sources. Re-profiles the file
  // against the chosen worksheet so mappings, keys, and pre-flight metrics reflect
  // the exact data that will be verified. A failed re-profile reverts the choice.
  const handleWorksheetChange = (fileId: string, sheet: string | null) => {
    const previous = uploadedDatasets.find((d) => d.id === fileId)?.selectedSheet ?? null;
    updateDataset(fileId, { selectedSheet: sheet });
    if (!sheet) return;
    if (!activeProject) return;
    api
      .preprocessFile(activeProject.id, fileId, { selected_worksheet: sheet })
      .then((profile) => updateDataset(fileId, { profile }))
      .catch(() => {
        updateDataset(fileId, { selectedSheet: previous });
      });
  };
  const handleFileUploaded = (file: SourceFile, profile?: PreprocessingResult) => {
    setUploadedDatasets((prev) => [
      ...prev,
      {
        id: file.id,
        name: file.original_filename,
        // Neutral label suggestion: recognizable institutional names when the filename
        // warrants them, otherwise the filename base. The user can edit these freely.
        label: suggestDatasetLabel(file.original_filename, prev),
        // Suggested role only — shown in the UI for confirmation and changeable.
        // The first file defaults to the authoritative source so a valid setup
        // exists immediately; the selector makes the choice visible and editable.
        isPrimary: prev.length === 0,
        profile,
      },
    ]);
  };

  useEffect(() => {
    if (!isAuthenticated) return;

    let cancelled = false;
    const loadProjects = async () => {
      setLoadingProjects(true);
      setProjectLoadError(null);
      try {
        const data = await api.listProjects();
        if (!cancelled) {
          setProjects(data);
          setActiveProject((prev) =>
            prev && data.some((project) => project.id === prev.id) ? prev : (data[0] ?? null),
          );
        }
      } catch (err) {
        console.error('Failed to load projects:', err);
        if (!cancelled) {
          setProjectLoadError(
            'We could not load your projects. Check your connection and try again.',
          );
        }
      } finally {
        if (!cancelled) setLoadingProjects(false);
      }
    };

    void loadProjects();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, projectReloadKey]);

  // Real connectivity check against the FastAPI service (no fabricated status).
  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;
    api
      .checkHealth()
      .then(() => {
        if (!cancelled) setApiStatus('online');
      })
      .catch(() => {
        if (!cancelled) setApiStatus('offline');
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  // Close the mobile drawer when Escape is pressed.
  useEffect(() => {
    if (!mobileNavOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileNavOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [mobileNavOpen]);

  const handleCreateProject = async (name: string, description?: string) => {
    const newProj = await api.createProject({ name, description });
    setProjects((prev) => [newProj, ...prev]);
    setActiveProject(newProj);
    setActiveTab('verify');
    setMobileNavOpen(false);
    setUploadedDatasets([]);
  };

  const handleSelectProject = (project: Project) => {
    setActiveProject(project);
    setActiveTab('verify');
    setMobileNavOpen(false);
    setUploadedDatasets([]);
  };

  const handleSelectTab = (tab: AppTab) => {
    setActiveTab(tab);
    setMobileNavOpen(false);
  };

  if (isLoading) {
    return (
      <div className="boot-splash">
        <div className="brand-icon">
          <ShieldCheck size={22} />
        </div>
        <span>Initialising VerifyGrid…</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AuthScreen />;
  }

  const tabMeta = TAB_META[activeTab];
  const connectionLabel =
    apiStatus === 'online' ? 'API connected' : apiStatus === 'offline' ? 'API offline' : 'Checking API…';

  return (
    <div className={`app-container ${mobileNavOpen ? 'sidebar-open' : ''}`}>
      <Sidebar
        currentTab={activeTab}
        onSelectTab={handleSelectTab}
        selectedProjectName={activeProject?.name}
        onClose={() => setMobileNavOpen(false)}
        showClose
      />

      {mobileNavOpen && (
        <div
          className="sidebar-backdrop"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden="true"
        />
      )}

      <div className="main-wrapper">
        <header className="top-bar">
          <div className="topbar-left">
            <button
              type="button"
              className="icon-btn mobile-menu-btn"
              onClick={() => setMobileNavOpen(true)}
              aria-label="Open navigation"
              aria-controls="app-sidebar"
              aria-expanded={mobileNavOpen}
            >
              <Menu size={19} />
            </button>
            <div className="topbar-heading">
              <span className="topbar-title">{tabMeta.title}</span>
              <span className="topbar-subtitle">
                {tabMeta.crumb}
                {activeProject ? ` · ${activeProject.name}` : ''}
              </span>
            </div>
          </div>

          <div className="topbar-right">
            <span className={`connection-pill ${apiStatus}`} role="status">
              <span className="connection-dot" aria-hidden="true" />
              <span className="connection-label">{connectionLabel}</span>
            </span>
            <div className="topbar-appearance">
              <AppearanceControl variant="compact" />
            </div>
          </div>
        </header>

        <main className="content-body">
          {activeTab === 'projects' && (
            <>
              {projectLoadError && (
                <div className="alert alert-error" role="alert">
                  <span>{projectLoadError}</span>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setProjectReloadKey((key) => key + 1)}
                    disabled={loadingProjects}
                  >
                    {loadingProjects ? 'Retrying…' : 'Retry'}
                  </button>
                </div>
              )}
              <ProjectsView
                projects={projects}
                activeProject={activeProject}
                onSelectProject={handleSelectProject}
                onCreateProject={handleCreateProject}
                loading={loadingProjects}
              />
            </>
          )}

          {(activeTab === 'verify' || activeTab === 'financial') && (
            <div>
              {!activeProject ? (
                <div className="card empty-state">
                  <div className="empty-icon">
                    <AlertCircle size={24} />
                  </div>
                  <h3 className="empty-title">Select or create a project</h3>
                  <p className="empty-text">
                    You need an active project before you can compare files.
                  </p>
                  <button className="btn btn-primary" onClick={() => setActiveTab('projects')}>
                    Go to projects
                  </button>
                </div>
              ) : (
                <WorkspaceVerification
                  project={activeProject}
                  mode={activeTab}
                  uploadedDatasets={uploadedDatasets}
                  onFileUploaded={handleFileUploaded}
                  onLabelChange={(fileId, label) => updateDataset(fileId, { label })}
                  onRoleChange={(fileId, isPrimary) => updateDataset(fileId, { isPrimary })}
                  onWorksheetChange={handleWorksheetChange}
                  onRemoveFile={removeDataset}
                />
              )}
            </div>
          )}

          {activeTab === 'runs' && (
            <div>
              {!activeProject ? (
                <div className="card empty-state">
                  <div className="empty-icon">
                    <AlertCircle size={24} />
                  </div>
                  <h3 className="empty-title">Select or create a project</h3>
                  <p className="empty-text">
                    Audit history is scoped to a project. Select one to view its verification runs.
                  </p>
                  <button className="btn btn-primary" onClick={() => setActiveTab('projects')}>
                    Go to projects
                  </button>
                </div>
              ) : (
                <AuditHistoryView key={activeProject.id} project={activeProject} />
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

export default App;

/** Shared workspace panel rendering the single (reused) 5-step verification wizard.
 *  mode === 'organization' (default) shows neutral, institution-friendly copy;
 *  mode === 'financial' preserves the existing financial reconciliation experience. */
export const WorkspaceVerification: React.FC<{
  project: Project;
  mode: 'verify' | 'financial';
  uploadedDatasets: UploadedDataset[];
  onFileUploaded: (file: SourceFile, profile?: PreprocessingResult) => void;
  onLabelChange: (fileId: string, label: string) => void;
  onRoleChange: (fileId: string, isPrimary: boolean) => void;
  onWorksheetChange?: (fileId: string, sheet: string | null) => void;
  onRemoveFile: (fileId: string) => void;
}> = ({
  project,
  mode,
  uploadedDatasets,
  onFileUploaded,
  onLabelChange,
  onRoleChange,
  onWorksheetChange,
  onRemoveFile,
}) => {
  const isFinancial = mode === 'financial';
  return (
    <div>
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div>
          <h1 className="page-title">{isFinancial ? 'Financial dataset reconciliation' : 'Verify organization records'}</h1>
          <p className="page-subtitle">
            {isFinancial
              ? (
                <>
                  Multi-source ingestion, candidate key discovery, and unified 5-step guided reconciliation against{' '}
                  <strong>{project.name}</strong>.
                </>
              ) : (
                <>
                  Upload files such as academic, hostel or membership registers, choose a matching key, and verify records across{' '}
                  <strong>{project.name}</strong>.
                </>
              )}
          </p>
        </div>
      </div>

      <ReconciliationWizard
        mode={isFinancial ? 'financial' : 'organization'}
        project={project}
        uploadedDatasets={uploadedDatasets}
        onFileUploaded={onFileUploaded}
        onLabelChange={onLabelChange}
        onRoleChange={onRoleChange}
        onWorksheetChange={onWorksheetChange}
        onRemoveFile={onRemoveFile}
        onRunCompleted={(_run) => {
          // Run completed successfully
        }}
      />
    </div>
  );
};
