import React, { useCallback, useEffect, useState } from 'react';
import type {
  MultiSourceKeyRecommendation,
  MultiSourceVerificationRequest,
  MultiSourceVerificationResponse,
  PreprocessingResult,
  Project,
  SourceDefinition,
  SourceFile,
  VerificationRun,
} from '../types';
import { api } from '../services/api';
import { FileUploadSection } from './FileUploadSection';
import { ProfilingQuarantineDrawer } from './ProfilingQuarantineDrawer';
import { StatusBadge } from './StatusBadge';
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  FileCheck,
  FileSpreadsheet,
  Filter,
  Layers,
  Play,
  RotateCcw,
  Search,
  ShieldCheck,
  Sliders,
  Sparkles,
  TableProperties,
} from 'lucide-react';

interface ReconciliationWizardProps {
  project: Project;
  uploadedDatasets: { id: string; name: string; profile?: PreprocessingResult }[];
  onFileUploaded: (file: SourceFile, profile?: PreprocessingResult) => void;
  onRunCompleted?: (run: VerificationRun) => void;
}

type WizardStep = 1 | 2 | 3 | 4 | 5;

const STEPS = [
  { num: 1, title: 'Ingestion', desc: 'Upload & Pre-flight' },
  { num: 2, title: 'Blueprint', desc: 'Aliases & Keys' },
  { num: 3, title: 'Rules', desc: 'Tolerances & Logic' },
  { num: 4, title: 'Exception Grid', desc: 'Multi-source Lineage' },
  { num: 5, title: 'Sign-off', desc: 'Audit & Exports' },
];

const DEFAULT_NAMES = ['erp', 'bank', 'gateway', 'pos', 'ledger', 'crm'];

export const ReconciliationWizard: React.FC<ReconciliationWizardProps> = ({
  project,
  uploadedDatasets,
  onFileUploaded,
  onRunCompleted,
}) => {
  const [currentStep, setCurrentStep] = useState<WizardStep>(1);

  // --- Step 1: Ingestion & Drawer ---
  const [drawerFile, setDrawerFile] = useState<{ id: string; name: string } | null>(null);

  // --- Step 2: Blueprint & Multi-source Mapping ---
  // Map file_id -> alias name
  const [sourceAliases, setSourceAliases] = useState<Record<string, string>>({});
  // Primary baseline file_id
  const [primaryFileId, setPrimaryFileId] = useState<string>('');
  // Unified join key name(s)
  const [unifiedKeys, setUnifiedKeys] = useState<string[]>(['id']);
  // Key columns per file_id: Record<file_id, string[]>
  const [fileKeyColumns, setFileKeyColumns] = useState<Record<string, string[]>>({});
  // Key recommendations from backend
  const [recommendations, setRecommendations] = useState<MultiSourceKeyRecommendation[]>([]);
  const [loadingRecommendations, setLoadingRecommendations] = useState<boolean>(false);
  const [recError, setRecError] = useState<string | null>(null);

  // --- Step 3: Rules ---
  const [numericTolerance, setNumericTolerance] = useState<number>(0.0);
  const [ignoreWhitespace, setIgnoreWhitespace] = useState<boolean>(true);
  const [ignoreCase, setIgnoreCase] = useState<boolean>(false);
  const [enableStatusEquivalence, setEnableStatusEquivalence] = useState<boolean>(true);

  // --- Step 4: Verification Results & Running ---
  const [running, setRunning] = useState<boolean>(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [verificationResponse, setVerificationResponse] =
    useState<MultiSourceVerificationResponse | null>(null);
  const [createdRun, setCreatedRun] = useState<VerificationRun | null>(null);

  // Filters for Exception Grid
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [searchKey, setSearchKey] = useState<string>('');

  // --- Step 5: Sign-off ---
  const [signOffNote, setSignOffNote] = useState<string>('');
  const [isSignedOff, setIsSignedOff] = useState<boolean>(false);
  const [exportingFormat, setExportingFormat] = useState<'csv' | 'xlsx' | 'json' | null>(null);

  // Helper to derive alias for a dataset
  const getAlias = useCallback(
    (dsId: string, idx: number) =>
      sourceAliases[dsId] || DEFAULT_NAMES[idx] || `source_${idx + 1}`,
    [sourceAliases],
  );
  const effectivePrimaryId = primaryFileId || uploadedDatasets[0]?.id || '';
  const getKeyCols = (ds: { id: string; name: string; profile?: PreprocessingResult }) =>
    fileKeyColumns[ds.id] || [ds.profile?.columns[0]?.normalized_name || 'id'];

  // Fetch candidate key recommendations when entering Step 2
  useEffect(() => {
    if (currentStep !== 2 || uploadedDatasets.length < 2) return;

    let cancelled = false;
    const fetchRecommendations = async () => {
      setLoadingRecommendations(true);
      setRecError(null);
      try {
        const fileIds = uploadedDatasets.map((d) => d.id);
        const aliases = uploadedDatasets.map((d, idx) => getAlias(d.id, idx));
        const res = await api.recommendCandidateKeys(project.id, {
          file_ids: fileIds,
          aliases,
        });
        if (!cancelled) {
          setRecommendations(res.recommendations);
          if (res.recommendations.length > 0 && res.recommendations[0].overall_score >= 0.7) {
            const top = res.recommendations[0];
            setUnifiedKeys(top.key_name.split(' + '));
          }
        }
      } catch (err: any) {
        if (!cancelled) {
          setRecError(err.message || 'Could not fetch candidate key recommendations.');
        }
      } finally {
        if (!cancelled) setLoadingRecommendations(false);
      }
    };

    void fetchRecommendations();
    return () => {
      cancelled = true;
    };
  }, [currentStep, project.id, uploadedDatasets, getAlias]);

  // Apply a candidate key recommendation
  const applyRecommendation = (rec: MultiSourceKeyRecommendation) => {
    const keys = rec.key_name.split(' + ');
    setUnifiedKeys(keys);

    setFileKeyColumns((prev) => {
      const next = { ...prev };
      uploadedDatasets.forEach((ds) => {
        const alias = sourceAliases[ds.id];
        if (alias && rec.source_columns[alias]) {
          next[ds.id] = rec.source_columns[alias];
        }
      });
      return next;
    });
  };

  // Execute multi-source reconciliation
  const handleExecuteVerification = async () => {
    setRunning(true);
    setRunError(null);

    const sourcesPayload: SourceDefinition[] = uploadedDatasets.map((ds, idx) => ({
      alias: getAlias(ds.id, idx),
      file_id: ds.id,
      is_primary: ds.id === effectivePrimaryId,
      key_columns: getKeyCols(ds),
      field_mapping: {},
    }));

    const statusRuleConfig = enableStatusEquivalence
      ? {
          permitted_pairs: [
            ['settled', 'completed'],
            ['settled', 'cleared'],
            ['completed', 'cleared'],
            ['active', 'current'],
            ['pending', 'processing'],
          ],
        }
      : undefined;

    const payload: MultiSourceVerificationRequest = {
      sources: sourcesPayload,
      unified_keys: unifiedKeys,
      numeric_tolerance: numericTolerance,
      ignore_whitespace: ignoreWhitespace,
      ignore_case: ignoreCase,
      include_identical: true,
      status_rules: statusRuleConfig,
    };

    try {
      // 1. Run in-memory calculation
      const resp = await api.verifyMultiSourceFiles(project.id, payload);
      setVerificationResponse(resp);

      // 2. Persist to audit history
      try {
        const runObj = await api.createMultiSourceVerificationRun(project.id, payload);
        setCreatedRun(runObj);
        if (onRunCompleted) {
          onRunCompleted(runObj);
        }
      } catch (runErr) {
        console.warn('Persistent run creation error (in-memory results preserved):', runErr);
      }

      setCurrentStep(4);
    } catch (err: any) {
      setRunError(err.message || 'Multi-source reconciliation failed.');
    } finally {
      setRunning(false);
    }
  };

  // Export report
  const handleExport = async (format: 'csv' | 'xlsx' | 'json') => {
    if (!createdRun) return;
    setExportingFormat(format);
    try {
      await api.downloadExport(project.id, createdRun.id, format);
    } catch (err: any) {
      alert(`Export failed: ${err.message}`);
    } finally {
      setExportingFormat(null);
    }
  };

  // Filtered results in Exception Grid
  const filteredResults = (verificationResponse?.results || []).filter((item) => {
    if (categoryFilter !== 'all' && item.discrepancy_category !== categoryFilter) return false;
    if (statusFilter !== 'all' && item.match_status !== statusFilter) return false;
    if (searchKey.trim()) {
      const kStr = JSON.stringify(item.key_values).toLowerCase();
      if (!kStr.includes(searchKey.toLowerCase())) return false;
    }
    return true;
  });

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      {/* 5-Step Stepper Header */}
      <div
        className="wizard-stepper-header"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(5, 1fr)',
          borderBottom: '1px solid var(--border-color)',
          backgroundColor: 'var(--bg-secondary)',
        }}
      >
        {STEPS.map((s) => {
          const isCompleted = currentStep > s.num;
          const isActive = currentStep === s.num;
          return (
            <button
              key={s.num}
              type="button"
              className={`stepper-step ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}
              onClick={() => {
                // Allow jumping to completed or active steps freely without losing state
                if (isCompleted || isActive) {
                  setCurrentStep(s.num as WizardStep);
                }
              }}
              style={{
                padding: '14px 16px',
                border: 'none',
                background: isActive ? 'var(--bg-subtle)' : 'transparent',
                borderBottom: isActive ? '3px solid var(--primary)' : '3px solid transparent',
                cursor: isCompleted || isActive ? 'pointer' : 'not-allowed',
                textAlign: 'left',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                transition: 'var(--transition)',
              }}
            >
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  backgroundColor: isCompleted
                    ? 'var(--success)'
                    : isActive
                      ? 'var(--primary)'
                      : 'var(--bg-card-hover)',
                  color: isCompleted || isActive ? '#ffffff' : 'var(--text-muted)',
                }}
              >
                {isCompleted ? <Check size={15} /> : s.num}
              </div>
              <div style={{ overflow: 'hidden' }}>
                <div
                  style={{
                    fontSize: '0.88rem',
                    fontWeight: isActive ? 600 : 500,
                    color: isActive ? 'var(--text-main)' : 'var(--text-muted)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {s.title}
                </div>
                <div style={{ fontSize: '0.74rem', color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
                  {s.desc}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Step Content Shell */}
      <div style={{ padding: '24px' }}>
        {/* ================= STEP 1: INGESTION ================= */}
        {currentStep === 1 && (
          <div>
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileSpreadsheet size={18} className="text-accent" /> Step 1: Multi-Source Dataset Ingestion
              </h3>
              <p className="text-dim" style={{ margin: '4px 0 0 0', fontSize: '0.85rem' }}>
                Upload 2 or more datasets (e.g. ERP ledger, bank statement, gateway settlements). Inspect pre-flight schemas and resolve quarantine anomalies.
              </p>
            </div>

            <FileUploadSection
              project={project}
              datasets={uploadedDatasets}
              onFileUploaded={onFileUploaded}
            />

            {/* List of uploaded files with pre-flight badges */}
            {uploadedDatasets.length >= 2 && (
              <div style={{ marginTop: 20, padding: '16px', backgroundColor: 'var(--bg-subtle)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <ShieldCheck size={18} className="text-success" />
                    <strong>{uploadedDatasets.length} datasets ready for reconciliation</strong>
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => setCurrentStep(2)}
                  >
                    Proceed to Blueprint <ArrowRight size={15} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ================= STEP 2: BLUEPRINT ================= */}
        {currentStep === 2 && (
          <div>
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Layers size={18} className="text-accent" /> Step 2: Blueprint &amp; Multi-Source Key Mapping
              </h3>
              <p className="text-dim" style={{ margin: '4px 0 0 0', fontSize: '0.85rem' }}>
                Assign meaningful aliases, select the primary baseline source, and configure matching join keys.
              </p>
            </div>

            {/* Candidate Key Recommendations Banner */}
            <div
              className="card"
              style={{
                marginBottom: 20,
                backgroundColor: 'var(--bg-card-hover)',
                border: '1px solid var(--border-color)',
                padding: '16px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Sparkles size={16} className="text-accent" />
                  <strong>AI &amp; Heuristic Join Key Recommendations</strong>
                </div>
                {loadingRecommendations && <span className="spinner" />}
              </div>

              {recError && <p className="text-danger" style={{ fontSize: '0.85rem' }}>{recError}</p>}

              {recommendations.length > 0 ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
                  {recommendations.map((rec) => (
                    <div
                      key={rec.key_name}
                      className="card"
                      style={{
                        padding: '12px',
                        borderLeft: rec.overall_score >= 0.8 ? '4px solid var(--success)' : '4px solid var(--warning)',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                          <strong style={{ fontSize: '0.9rem' }}>{rec.key_name}</strong>
                          <span className="badge badge-success">{(rec.overall_score * 100).toFixed(0)}% Match</span>
                        </div>
                        <p style={{ fontSize: '0.78rem', color: 'var(--text-dim)', margin: '0 0 8px 0' }}>
                          {rec.recommendation_reason}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="btn btn-secondary btn-xs"
                        style={{ width: 'fit-content' }}
                        onClick={() => applyRecommendation(rec)}
                      >
                        Apply this Key
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-dim" style={{ fontSize: '0.85rem', margin: 0 }}>
                  Analyzing cross-source column uniqueness and value overlap…
                </p>
              )}
            </div>

            {/* Source Aliases & Key Columns Table */}
            <div className="table-container" style={{ border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', marginBottom: 20 }}>
              <table className="data-table" style={{ width: '100%', fontSize: '0.85rem' }}>
                <thead>
                  <tr>
                    <th style={{ width: 140 }}>Role</th>
                    <th style={{ width: 180 }}>Source Alias</th>
                    <th>File Name</th>
                    <th>Key Column(s)</th>
                  </tr>
                </thead>
                <tbody>
                  {uploadedDatasets.map((ds, idx) => {
                    const isPrimary = ds.id === effectivePrimaryId;
                    const cols = ds.profile?.columns.map((c) => c.normalized_name) || [];
                    const currentAlias = getAlias(ds.id, idx);
                    const currentKeyCols = getKeyCols(ds);
                    return (
                      <tr key={ds.id} style={{ backgroundColor: isPrimary ? 'var(--bg-subtle)' : undefined }}>
                        <td>
                          <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                            <input
                              type="radio"
                              name="primarySourceRadio"
                              checked={isPrimary}
                              onChange={() => setPrimaryFileId(ds.id)}
                            />
                            {isPrimary ? (
                              <span className="badge badge-success">Primary Golden</span>
                            ) : (
                              <span className="text-dim">Secondary</span>
                            )}
                          </label>
                        </td>
                        <td>
                          <input
                            type="text"
                            className="form-input"
                            value={currentAlias}
                            onChange={(e) =>
                              setSourceAliases({ ...sourceAliases, [ds.id]: e.target.value })
                            }
                            placeholder="e.g. erp, bank, gateway"
                            style={{ fontSize: '0.85rem', padding: '4px 8px' }}
                          />
                        </td>
                        <td>
                          <strong>{ds.name}</strong>
                          <span className="text-dim" style={{ marginLeft: 8 }}>
                            ({ds.profile?.data_rows_count.toLocaleString() || '—'} rows)
                          </span>
                        </td>
                        <td>
                          <select
                            className="form-select"
                            value={currentKeyCols[0] || ''}
                            onChange={(e) =>
                              setFileKeyColumns({ ...fileKeyColumns, [ds.id]: [e.target.value] })
                            }
                            style={{ fontSize: '0.85rem', padding: '4px 8px', maxWidth: 220 }}
                          >
                            {cols.map((colName) => (
                              <option key={colName} value={colName}>
                                {colName}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Unified Join Key Input */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
              <label style={{ fontSize: '0.9rem', fontWeight: 500 }}>Unified Join Key:</label>
              <input
                type="text"
                className="form-input"
                style={{ maxWidth: 260 }}
                value={unifiedKeys.join(' + ')}
                onChange={(e) => setUnifiedKeys(e.target.value.split('+').map((s) => s.trim()))}
                placeholder="e.g. id or order_id + date"
              />
              <span className="text-dim" style={{ fontSize: '0.8rem' }}>
                (Composite keys can be combined with &apos;+&apos;)
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setCurrentStep(1)}>
                <ChevronLeft size={16} /> Back to Ingestion
              </button>
              <button type="button" className="btn btn-primary" onClick={() => setCurrentStep(3)}>
                Proceed to Rules <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* ================= STEP 3: RULES ================= */}
        {currentStep === 3 && (
          <div>
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Sliders size={18} className="text-accent" /> Step 3: Reconciliation Rules &amp; Tolerances
              </h3>
              <p className="text-dim" style={{ margin: '4px 0 0 0', fontSize: '0.85rem' }}>
                Configure numeric float/amount tolerances, string normalization, and state-aware status equivalence.
              </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginBottom: 28 }}>
              {/* Tolerance Rule */}
              <div className="card" style={{ padding: '16px' }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: '0.95rem' }}>Numeric &amp; Currency Tolerance</h4>
                <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                  Acceptable difference when comparing floating-point numbers or monetary amounts across systems.
                </p>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>±</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    className="form-input"
                    style={{ maxWidth: 120 }}
                    value={numericTolerance}
                    onChange={(e) => setNumericTolerance(parseFloat(e.target.value) || 0)}
                  />
                  <span className="text-dim" style={{ fontSize: '0.82rem' }}>
                    {numericTolerance === 0 ? '(Strict exact match)' : `(Differences ≤ ${numericTolerance} pass as identical)`}
                  </span>
                </div>
              </div>

              {/* Status Equivalence Rule */}
              <div className="card" style={{ padding: '16px' }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: '0.95rem' }}>Cross-System Status Equivalence</h4>
                <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                  Maps equivalent state terms across disparate source vendors.
                </p>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', marginBottom: 8 }}>
                  <input
                    type="checkbox"
                    checked={enableStatusEquivalence}
                    onChange={(e) => setEnableStatusEquivalence(e.target.checked)}
                  />
                  <span>Enable status equivalence rules</span>
                </label>
                {enableStatusEquivalence && (
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', backgroundColor: 'var(--bg-subtle)', padding: '6px 10px', borderRadius: 'var(--radius-xs)' }}>
                    • &apos;settled&apos; ↔ &apos;completed&apos; ↔ &apos;cleared&apos;
                    <br />
                    • &apos;active&apos; ↔ &apos;current&apos;
                  </div>
                )}
              </div>

              {/* String Normalization */}
              <div className="card" style={{ padding: '16px' }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: '0.95rem' }}>Text Cleaning</h4>
                <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                  Case and whitespace rules applied during field comparison.
                </p>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', marginBottom: 8 }}>
                  <input
                    type="checkbox"
                    checked={ignoreWhitespace}
                    onChange={(e) => setIgnoreWhitespace(e.target.checked)}
                  />
                  <span>Ignore leading and trailing whitespace</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={ignoreCase}
                    onChange={(e) => setIgnoreCase(e.target.checked)}
                  />
                  <span>Ignore case sensitivity</span>
                </label>
              </div>
            </div>

            {runError && (
              <div className="alert alert-error" style={{ marginBottom: 16 }}>
                <AlertCircle size={16} />
                <span>{runError}</span>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setCurrentStep(2)}>
                <ChevronLeft size={16} /> Back to Blueprint
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void handleExecuteVerification()}
                disabled={running}
              >
                {running ? <span className="spinner" /> : <Play size={16} />}
                Execute Reconciliation Run
              </button>
            </div>
          </div>
        )}

        {/* ================= STEP 4: EXCEPTION GRID ================= */}
        {currentStep === 4 && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <TableProperties size={18} className="text-accent" /> Step 4: Multi-Source Exception Grid &amp; Lineage
                </h3>
                <p className="text-dim" style={{ margin: '4px 0 0 0', fontSize: '0.85rem' }}>
                  Inspect cross-source match statuses and trace full row indices across all {uploadedDatasets.length} participating files.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => setCurrentStep(5)}
              >
                Proceed to Sign-off <ArrowRight size={15} />
              </button>
            </div>

            {/* Quick Metrics Bar */}
            {verificationResponse && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(4, 1fr)',
                  gap: 12,
                  marginBottom: 16,
                  backgroundColor: 'var(--bg-subtle)',
                  padding: '12px',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <div>
                  <span className="metric-label">Total Evaluated</span>
                  <span className="metric-value" style={{ fontSize: '1.2rem' }}>
                    {verificationResponse.results.length.toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="metric-label">Identical Matches</span>
                  <span className="metric-value text-success" style={{ fontSize: '1.2rem' }}>
                    {verificationResponse.summary.identical_matches.toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="metric-label">Field Mismatches</span>
                  <span className="metric-value text-warning" style={{ fontSize: '1.2rem' }}>
                    {verificationResponse.summary.field_mismatches.toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="metric-label">Missing Across Sources</span>
                  <span className="metric-value text-danger" style={{ fontSize: '1.2rem' }}>
                    {(
                      verificationResponse.summary.unmatched_source_records +
                      verificationResponse.summary.unmatched_target_records
                    ).toLocaleString()}
                  </span>
                </div>
              </div>
            )}

            {/* Filters Toolbar */}
            <div className="toolbar" style={{ marginBottom: 12 }}>
              <div className="search-box">
                <Search size={15} />
                <input
                  type="text"
                  className="form-input"
                  placeholder="Search by key values…"
                  value={searchKey}
                  onChange={(e) => setSearchKey(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Filter size={15} className="text-dim" />
                <select
                  className="form-select filter-select"
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                >
                  <option value="all">All categories</option>
                  <option value="none">Identical</option>
                  <option value="field_mismatch">Field mismatches</option>
                  <option value="missing_record">Missing records</option>
                  <option value="duplicate_key">Duplicate keys</option>
                </select>

                <select
                  className="form-select filter-select"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <option value="all">All statuses</option>
                  <option value="identical">Identical</option>
                  <option value="field_mismatch">Field mismatch</option>
                  <option value="missing_in_target">Missing in target</option>
                  <option value="missing_in_source">Missing in primary</option>
                </select>
              </div>
            </div>

            {/* Exception Grid Table */}
            <div className="table-container" style={{ border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', marginBottom: 20 }}>
              <table className="data-table" style={{ width: '100%', fontSize: '0.85rem' }}>
                <thead>
                  <tr>
                    <th style={{ width: 140 }}>Key Values</th>
                    <th style={{ width: 130 }}>Match Status</th>
                    <th>Source Lineage (Row # by Source)</th>
                    <th>Differences / Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredResults.length === 0 ? (
                    <tr>
                      <td colSpan={4} style={{ textAlign: 'center', padding: '36px' }}>
                        No records match your filters.
                      </td>
                    </tr>
                  ) : (
                    filteredResults.slice(0, 50).map((row) => (
                      <tr key={row.id}>
                        <td>
                          <code className="key-code">{JSON.stringify(row.key_values)}</code>
                        </td>
                        <td>
                          <StatusBadge status={row.match_status} />
                        </td>
                        <td>
                          {row.source_row_indices ? (
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                              {Object.entries(row.source_row_indices).map(([alias, rIdx]) => (
                                <span
                                  key={alias}
                                  className="badge"
                                  style={{
                                    backgroundColor: rIdx ? 'var(--bg-card-hover)' : 'var(--danger-soft)',
                                    color: rIdx ? 'var(--text-main)' : 'var(--danger-text)',
                                    fontFamily: 'var(--font-mono)',
                                    fontSize: '0.75rem',
                                  }}
                                >
                                  <strong>{alias}:</strong> {rIdx ? `Row ${rIdx}` : 'Missing'}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-dim">Row {row.source_row_number ?? '—'}</span>
                          )}
                        </td>
                        <td>
                          {row.field_differences && row.field_differences.length > 0 ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                              {row.field_differences.map((d, i) => (
                                <div key={i} style={{ fontSize: '0.78rem' }}>
                                  <strong className="text-accent">{d.field_name}:</strong>{' '}
                                  <span>{String(d.source_value)}</span> ≠{' '}
                                  <span style={{ color: 'var(--warning-text)' }}>{String(d.target_value)}</span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <span className="text-dim">{row.message || 'Identical match'}</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setCurrentStep(3)}>
                <ChevronLeft size={16} /> Back to Rules
              </button>
              <button type="button" className="btn btn-primary" onClick={() => setCurrentStep(5)}>
                Proceed to Sign-off <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* ================= STEP 5: SIGN-OFF ================= */}
        {currentStep === 5 && (
          <div>
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileCheck size={18} className="text-accent" /> Step 5: Run Sign-off, Audit Entry &amp; Exports
              </h3>
              <p className="text-dim" style={{ margin: '4px 0 0 0', fontSize: '0.85rem' }}>
                Complete the reconciliation audit entry, verify final metrics, and export audit-ready reports.
              </p>
            </div>

            {verificationResponse && (
              <div
                className="card"
                style={{
                  padding: '20px',
                  marginBottom: 24,
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border-color)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                  <ShieldCheck size={24} className="text-success" />
                  <div>
                    <h4 style={{ margin: 0, fontSize: '1.05rem' }}>Reconciliation Complete</h4>
                    <span className="text-dim" style={{ fontSize: '0.82rem' }}>
                      Aligned across {uploadedDatasets.length} sources · {verificationResponse.summary.matched_records} matched pairs
                    </span>
                  </div>
                </div>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                    gap: 12,
                    marginBottom: 20,
                  }}
                >
                  {Object.entries(verificationResponse.records_by_source || {}).map(([alias, count]) => (
                    <div key={alias} className="metric-card flat" style={{ padding: '10px 14px' }}>
                      <span className="metric-label">{alias} records</span>
                      <span className="metric-value" style={{ fontSize: '1.15rem' }}>
                        {count.toLocaleString()}
                      </span>
                    </div>
                  ))}
                  <div className="metric-card flat" style={{ padding: '10px 14px' }}>
                    <span className="metric-label">Identical Matches</span>
                    <span className="metric-value text-success" style={{ fontSize: '1.15rem' }}>
                      {verificationResponse.summary.identical_matches.toLocaleString()}
                    </span>
                  </div>
                  <div className="metric-card flat" style={{ padding: '10px 14px' }}>
                    <span className="metric-label">Discrepancies</span>
                    <span className="metric-value text-danger" style={{ fontSize: '1.15rem' }}>
                      {verificationResponse.summary.total_discrepancies.toLocaleString()}
                    </span>
                  </div>
                </div>

                {/* Export Report Actions */}
                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 16, marginBottom: 16 }}>
                  <label style={{ fontSize: '0.9rem', fontWeight: 600, display: 'block', marginBottom: 10 }}>
                    Export Discrepancy &amp; Reconciliation Reports:
                  </label>
                  <div style={{ display: 'flex', gap: 10 }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void handleExport('csv')}
                      disabled={Boolean(exportingFormat)}
                    >
                      <Download size={14} /> CSV Report
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void handleExport('xlsx')}
                      disabled={Boolean(exportingFormat)}
                    >
                      <Download size={14} /> Excel Spreadsheet
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void handleExport('json')}
                      disabled={Boolean(exportingFormat)}
                    >
                      <Download size={14} /> JSON Dataset
                    </button>
                  </div>
                </div>

                {/* Sign-off Form */}
                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 16 }}>
                  <label style={{ fontSize: '0.9rem', fontWeight: 600, display: 'block', marginBottom: 8 }}>
                    Sign-off Notes / Auditor Attestation:
                  </label>
                  <textarea
                    className="form-textarea"
                    rows={3}
                    placeholder="e.g. Reviewed multi-source exceptions between ERP, Bank, and Gateway. Approved differences within tolerance."
                    value={signOffNote}
                    onChange={(e) => setSignOffNote(e.target.value)}
                    disabled={isSignedOff}
                    style={{ width: '100%', marginBottom: 12, fontSize: '0.85rem' }}
                  />
                  {!isSignedOff ? (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => setIsSignedOff(true)}
                    >
                      <CheckCircle2 size={16} /> Sign-off &amp; Seal Reconciliation
                    </button>
                  ) : (
                    <div className="alert alert-success" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <CheckCircle2 size={16} />
                      <strong>Reconciliation signed-off and committed to audit record.</strong>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setCurrentStep(4)}>
                <ChevronLeft size={16} /> Back to Exception Grid
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setCurrentStep(1);
                  setIsSignedOff(false);
                }}
              >
                <RotateCcw size={15} /> Start New Reconciliation
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Quarantine Drawer Modal if triggered */}
      {drawerFile && (
        <ProfilingQuarantineDrawer
          projectId={project.id}
          fileId={drawerFile.id}
          filename={drawerFile.name}
          isOpen={Boolean(drawerFile)}
          onClose={() => setDrawerFile(null)}
        />
      )}
    </div>
  );
};
