import React, { useEffect, useState } from 'react';
import { useAuth } from './context/useAuth';
import { AuthScreen } from './components/AuthScreen';
import { Sidebar } from './components/Sidebar';
import { ProjectsView } from './components/ProjectsView';
import { FileUploadSection } from './components/FileUploadSection';
import { ReconciliationConfig } from './components/ReconciliationConfig';
import { VerificationResultsView } from './components/VerificationResultsView';
import type { Project, PreprocessingResult, VerificationResponse, VerificationRun } from './types';
import { api } from './services/api';
import { AlertCircle, Database } from 'lucide-react';

export const App: React.FC = () => {
  const { isAuthenticated, isLoading } = useAuth();
  const [activeTab, setActiveTab] = useState<'projects' | 'verify'>('projects');
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [loadingProjects, setLoadingProjects] = useState<boolean>(false);

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
      try {
        const data = await api.listProjects();
        if (!cancelled) {
          setProjects(data);
          setActiveProject((prev) => (prev ? prev : data[0] ?? null));
        }
      } catch (err) {
        console.error('Failed to load projects:', err);
      } finally {
        if (!cancelled) setLoadingProjects(false);
      }
    };

    void loadProjects();
    return () => { cancelled = true; };
  }, [isAuthenticated]);

  const handleCreateProject = async (name: string, description?: string) => {
    const newProj = await api.createProject({ name, description });
    setProjects((prev) => [newProj, ...prev]);
    setActiveProject(newProj);
    setActiveTab('verify');
    setUploadedDatasets([]);
    setVerificationResult(null);
  };

  const handleSelectProject = (project: Project) => {
    setActiveProject(project);
    setActiveTab('verify');
    setUploadedDatasets([]);
    setVerificationResult(null);
  };

  if (isLoading) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: 'var(--bg-primary)',
          color: 'var(--text-muted)',
        }}
      >
        Initializing VerifyGrid...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AuthScreen />;
  }

  return (
    <div className="app-container">
      <Sidebar
        currentTab={activeTab}
        onSelectTab={(tab) => setActiveTab(tab as any)}
        selectedProjectName={activeProject?.name}
      />

      <div className="main-wrapper">
        <header className="top-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: '0.9rem', color: 'var(--text-dim)' }}>Workspace:</span>
            <strong style={{ color: 'var(--text-main)', fontSize: '0.95rem' }}>
              {activeProject ? activeProject.name : 'No Project Selected'}
            </strong>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                fontSize: '0.75rem',
                color: 'var(--accent-emerald)',
              }}
            >
              <Database size={13} /> FastAPI Service Connected
            </span>
          </div>
        </header>

        <main className="content-body">
          {activeTab === 'projects' && (
            <ProjectsView
              projects={projects}
              activeProject={activeProject}
              onSelectProject={handleSelectProject}
              onCreateProject={handleCreateProject}
              loading={loadingProjects}
            />
          )}

          {activeTab === 'verify' && (
            <div>
              {!activeProject ? (
                <div className="card empty-state">
                  <AlertCircle size={40} className="empty-state-icon" />
                  <h3 className="empty-state-title">Select or Create a Project</h3>
                  <p style={{ marginBottom: 16 }}>
                    You need an active project to upload datasets and run verification reconciliations.
                  </p>
                  <button className="btn btn-primary" onClick={() => setActiveTab('projects')}>
                    Go to Projects
                  </button>
                </div>
              ) : (
                <div>
                  <div style={{ marginBottom: 24 }}>
                    <h1 className="page-title">Dataset Reconciliation Workspace</h1>
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginTop: 4 }}>
                      Upload baseline and target CSV/XLSX files, configure matching keys, and reconcile records.
                    </p>
                  </div>

                  <FileUploadSection
                    project={activeProject}
                    onFileUploaded={(file, profile) => {
                      setUploadedDatasets((prev) => [
                        ...prev,
                        { id: file.id, name: file.original_filename, profile },
                      ]);
                    }}
                  />

                  {uploadedDatasets.length >= 2 && (
                    <ReconciliationConfig
                      project={activeProject}
                      datasets={uploadedDatasets}
                      onVerificationComplete={(resp, run) => {
                        setVerificationResult(resp);
                        setCurrentRun(run);
                      }}
                    />
                  )}

                  {uploadedDatasets.length < 2 && (
                    <div
                      className="card"
                      style={{
                        padding: '16px 20px',
                        backgroundColor: 'rgba(59, 130, 246, 0.05)',
                        border: '1px solid rgba(59, 130, 246, 0.2)',
                        color: 'var(--text-muted)',
                        fontSize: '0.875rem',
                      }}
                    >
                      💡 <strong>Next Step:</strong> Upload at least 2 files (source and target) to configure matching keys and trigger verification.
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
        </main>
      </div>
    </div>
  );
};

export default App;
