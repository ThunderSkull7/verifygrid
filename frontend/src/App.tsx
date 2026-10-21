import React, { useEffect, useState } from 'react';
import { useAuth } from './context/useAuth';
import { AuthScreen } from './components/AuthScreen';
import { Sidebar } from './components/Sidebar';
import type { AppTab } from './components/Sidebar';
import { ProjectsView } from './components/ProjectsView';
import { FileUploadSection } from './components/FileUploadSection';
import { ReconciliationConfig } from './components/ReconciliationConfig';
import { VerificationResultsView } from './components/VerificationResultsView';
import { AuditHistoryView } from './components/AuditHistoryView';
import { AppearanceControl } from './components/AppearanceControl';
import type { Project, PreprocessingResult, VerificationResponse, VerificationRun } from './types';
import { api } from './services/api';
import { AlertCircle, Menu, ShieldCheck } from 'lucide-react';

type ApiStatus = 'checking' | 'online' | 'offline';

const TAB_META: Record<AppTab, { title: string; crumb: string }> = {
  projects: { title: 'Projects', crumb: 'Workspaces' },
  verify: { title: 'Reconciliation workspace', crumb: 'Compare datasets' },
  runs: { title: 'Audit history', crumb: 'Persistent runs' },
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
  const [uploadedDatasets, setUploadedDatasets] = useState<
    { id: string; name: string; profile?: PreprocessingResult }[]
  >([]);
  const [verificationResult, setVerificationResult] = useState<VerificationResponse | null>(null);
  const [currentRun, setCurrentRun] = useState<VerificationRun | undefined>(undefined);

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
    setVerificationResult(null);
  };

  const handleSelectProject = (project: Project) => {
    setActiveProject(project);
    setActiveTab('verify');
    setMobileNavOpen(false);
    setUploadedDatasets([]);
    setVerificationResult(null);
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

          {activeTab === 'verify' && (
            <div>
              {!activeProject ? (
                <div className="card empty-state">
                  <div className="empty-icon">
                    <AlertCircle size={24} />
                  </div>
                  <h3 className="empty-title">Select or create a project</h3>
                  <p className="empty-text">
                    You need an active project to upload datasets and run verification
                    reconciliations.
                  </p>
                  <button className="btn btn-primary" onClick={() => setActiveTab('projects')}>
                    Go to projects
                  </button>
                </div>
              ) : (
                <div>
                  <div className="page-header">
                    <div>
                      <h1 className="page-title">Dataset reconciliation</h1>
                      <p className="page-subtitle">
                        Upload baseline and target CSV/XLSX files, configure matching keys, and
                        reconcile records against{' '}
                        <strong>{activeProject.name}</strong>.
                      </p>
                    </div>
                  </div>

                  <FileUploadSection
                    project={activeProject}
                    datasets={uploadedDatasets}
                    onFileUploaded={(file, profile) => {
                      setUploadedDatasets((prev) => [
                        ...prev,
                        { id: file.id, name: file.original_filename, profile },
                      ]);
                    }}
                  />

                  {uploadedDatasets.length >= 2 ? (
                    <ReconciliationConfig
                      project={activeProject}
                      datasets={uploadedDatasets}
                      onVerificationComplete={(resp, run) => {
                        setVerificationResult(resp);
                        setCurrentRun(run);
                      }}
                    />
                  ) : (
                    <div className="info-strip">
                      <AlertCircle size={15} />
                      <span>
                        <strong>Next step:</strong> upload at least two files (source and target) to
                        configure matching keys and trigger verification.
                      </span>
                    </div>
                  )}

                  {verificationResult && (
                    <VerificationResultsView
                      projectId={activeProject.id}
                      response={verificationResult}
                      run={currentRun}
                    />
                  )}
                </div>
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
