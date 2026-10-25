import React, { useCallback, useEffect, useState } from 'react';
import type {
  AggregationConfig,
  DateWindowRule,
  MultiSourceKeyRecommendation,
  MultiSourceVerificationRequest,
  MultiSourceVerificationResponse,
  NumericToleranceRule,
  PredicateOperator,
  PreprocessingResult,
  Project,
  RulePreviewResponse,
  SourceDefinition,
  SourceFile,
  VerificationRun,
  VersionedRuleConfig,
  WhereCondition,
} from '../types';
import { api } from '../services/api';
import { FileUploadSection } from './FileUploadSection';
import { ProfilingQuarantineDrawer } from './ProfilingQuarantineDrawer';
import { StatusBadge } from './StatusBadge';
import {
  AlertCircle,
  ArrowRight,
  Calendar,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  Eye,
  FileCheck,
  FileSpreadsheet,
  Filter,
  Layers,
  Play,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  Sliders,
  Sparkles,
  Split,
  TableProperties,
  Trash2,
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

  // --- Step 3: Rules & Tolerances ---
  const [numericTolerance, setNumericTolerance] = useState<number>(0.0);
  const [numericPercentageTolerance, setNumericPercentageTolerance] = useState<number>(0.0);
  const [ignoreWhitespace, setIgnoreWhitespace] = useState<boolean>(true);
  const [ignoreCase, setIgnoreCase] = useState<boolean>(false);
  const [enableStatusEquivalence, setEnableStatusEquivalence] = useState<boolean>(true);

  // Date Window Rule state
  const [dateWindowEnabled, setDateWindowEnabled] = useState<boolean>(false);
  const [dateWindowSourceField, setDateWindowSourceField] = useState<string>('date');
  const [dateWindowTargetField, setDateWindowTargetField] = useState<string>('date');
  const [dateWindowLagBefore, setDateWindowLagBefore] = useState<number>(0);
  const [dateWindowLagAfter, setDateWindowLagAfter] = useState<number>(3);

  // Where Condition Predicates state
  const [whereConditions, setWhereConditions] = useState<WhereCondition[]>([]);
  const [newPredField, setNewPredField] = useState<string>('');
  const [newPredOp, setNewPredOp] = useState<PredicateOperator>('equal');
  const [newPredValue, setNewPredValue] = useState<string>('');

  // Split-Payment Aggregation state
  const [aggregationEnabled, setAggregationEnabled] = useState<boolean>(false);
  const [aggregationParentAlias, setAggregationParentAlias] = useState<string>('');
  const [aggregationChildAlias, setAggregationChildAlias] = useState<string>('');
  const [aggregationParentKey, setAggregationParentKey] = useState<string>('id');
  const [aggregationChildGroupKey, setAggregationChildGroupKey] = useState<string>('parent_id');
  const [aggregationParentAmountField, setAggregationParentAmountField] = useState<string>('amount');
  const [aggregationChildAmountField, setAggregationChildAmountField] = useState<string>('amount');
  const [aggregationChildReceiptIdField, setAggregationChildReceiptIdField] = useState<string>('');
  const [aggregationNumericTolerance, setAggregationNumericTolerance] = useState<number>(0.0);

  // Rule Impact Preview state
  const [previewingRules, setPreviewingRules] = useState<boolean>(false);
  const [rulePreviewResult, setRulePreviewResult] = useState<RulePreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

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

  // Build VersionedRuleConfig for preview and execution
  const buildRuleConfig = useCallback((): VersionedRuleConfig => {
    const dateWindowRules: DateWindowRule[] =
      dateWindowEnabled && dateWindowSourceField && dateWindowTargetField
        ? [
            {
              source_date_field: dateWindowSourceField,
              target_date_field: dateWindowTargetField,
              lag_days_before: dateWindowLagBefore,
              lag_days_after: dateWindowLagAfter,
              severity: 'WARNING',
            },
          ]
        : [];

    const numericRules: NumericToleranceRule[] =
      numericPercentageTolerance > 0
        ? [
            {
              source_amount_field: 'amount',
              target_amount_field: 'amount',
              absolute_tolerance: numericTolerance,
              percentage_tolerance: numericPercentageTolerance,
              tolerance_mode: 'both_or',
              severity: 'BLOCKING',
            },
          ]
        : [];

    const aggConfig: AggregationConfig | null = aggregationEnabled
      ? {
          enabled: true,
          parent_source_alias:
            aggregationParentAlias ||
            (uploadedDatasets[0] ? getAlias(uploadedDatasets[0].id, 0) : 'source_1'),
          child_source_alias:
            aggregationChildAlias ||
            (uploadedDatasets[1] ? getAlias(uploadedDatasets[1].id, 1) : 'source_2'),
          parent_key: aggregationParentKey,
          child_grouping_key: aggregationChildGroupKey,
          parent_amount_field: aggregationParentAmountField,
          child_amount_field: aggregationChildAmountField,
          child_receipt_id_field: aggregationChildReceiptIdField || null,
          numeric_tolerance: aggregationNumericTolerance,
        }
      : null;

    return {
      version: '1.0.0',
      where_conditions: whereConditions,
      date_window_rules: dateWindowRules,
      numeric_tolerance_rules: numericRules,
      status_transition_rules: enableStatusEquivalence
        ? [
            {
              source_field: 'status',
              target_field: 'status',
              allowed_transitions: {
                settled: ['completed', 'cleared'],
                completed: ['settled', 'cleared'],
                active: ['current'],
                pending: ['processing'],
              },
              case_sensitive: false,
              severity: 'BLOCKING',
            },
          ]
        : [],
      custom_rules: [],
      aggregation_config: aggConfig,
    };
  }, [
    dateWindowEnabled,
    dateWindowSourceField,
    dateWindowTargetField,
    dateWindowLagBefore,
    dateWindowLagAfter,
    numericTolerance,
    numericPercentageTolerance,
    aggregationEnabled,
    aggregationParentAlias,
    aggregationChildAlias,
    aggregationParentKey,
    aggregationChildGroupKey,
    aggregationParentAmountField,
    aggregationChildAmountField,
    aggregationChildReceiptIdField,
    aggregationNumericTolerance,
    uploadedDatasets,
    getAlias,
    whereConditions,
    enableStatusEquivalence,
  ]);

  const handleAddPredicate = () => {
    if (!newPredField.trim()) return;
    setWhereConditions((prev) => [
      ...prev,
      {
        field: newPredField.trim(),
        operator: newPredOp,
        value: newPredValue,
        severity: 'WARNING',
      },
    ]);
    setNewPredField('');
    setNewPredValue('');
  };

  const handleRemovePredicate = (idx: number) => {
    setWhereConditions((prev) => prev.filter((_, i) => i !== idx));
  };

  const handlePreviewRules = async () => {
    setPreviewingRules(true);
    setPreviewError(null);
    try {
      const sourcesPayload: SourceDefinition[] = uploadedDatasets.map((ds, idx) => ({
        alias: getAlias(ds.id, idx),
        file_id: ds.id,
        is_primary: ds.id === effectivePrimaryId,
        key_columns: getKeyCols(ds),
        field_mapping: {},
      }));

      const ruleCfg = buildRuleConfig();
      const res = await api.previewRules(project.id, {
        rules: ruleCfg,
        sources: sourcesPayload,
        unified_keys: unifiedKeys,
        sample_size: 100,
      });
      setRulePreviewResult(res);
    } catch (err: any) {
      setPreviewError(err.message || 'Failed to preview rules.');
    } finally {
      setPreviewingRules(false);
    }
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

    const ruleConfig = buildRuleConfig();

    const payload: MultiSourceVerificationRequest = {
      sources: sourcesPayload,
      unified_keys: unifiedKeys,
      numeric_tolerance: numericTolerance,
      ignore_whitespace: ignoreWhitespace,
      ignore_case: ignoreCase,
      include_identical: true,
      status_rules: statusRuleConfig,
      rule_config: ruleConfig,
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

            {/* Rules Cards Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginBottom: 20 }}>
              {/* Tolerance Rule */}
              <div className="card" style={{ padding: '16px' }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: '0.95rem' }}>Numeric &amp; Currency Tolerances</h4>
                <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                  Acceptable thresholds when comparing monetary amounts or numerical measures across systems.
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ minWidth: 100, fontSize: '0.85rem' }}>Absolute (±):</span>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      className="form-input"
                      style={{ maxWidth: 100 }}
                      value={numericTolerance}
                      onChange={(e) => setNumericTolerance(parseFloat(e.target.value) || 0)}
                    />
                    <span className="text-dim" style={{ fontSize: '0.78rem' }}>
                      {numericTolerance === 0 ? '(Exact match)' : `(Diff ≤ ${numericTolerance})`}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ minWidth: 100, fontSize: '0.85rem' }}>Percentage (%):</span>
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      max="100"
                      className="form-input"
                      style={{ maxWidth: 100 }}
                      value={numericPercentageTolerance}
                      onChange={(e) => setNumericPercentageTolerance(parseFloat(e.target.value) || 0)}
                    />
                    <span className="text-dim" style={{ fontSize: '0.78rem' }}>
                      {numericPercentageTolerance === 0 ? '(0% tolerance)' : `(Diff ≤ ${numericPercentageTolerance}%)`}
                    </span>
                  </div>
                </div>
              </div>

              {/* Settlement Date Window Rule */}
              <div className="card" style={{ padding: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <h4 style={{ margin: 0, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Calendar size={16} className="text-accent" /> Settlement Date Window
                  </h4>
                  <label className="switch" style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={dateWindowEnabled}
                      onChange={(e) => setDateWindowEnabled(e.target.checked)}
                    />
                    <span style={{ fontSize: '0.8rem' }}>{dateWindowEnabled ? 'Active' : 'Off'}</span>
                  </label>
                </div>
                <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                  Verify transaction lag (target date must fall within [source - N days, source + M days]).
                </p>
                {dateWindowEnabled && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: '0.82rem' }}>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <div style={{ flex: 1 }}>
                        <label style={{ display: 'block', marginBottom: 2 }}>Source Date Col</label>
                        <input
                          type="text"
                          className="form-input"
                          style={{ width: '100%', padding: '4px 8px' }}
                          value={dateWindowSourceField}
                          onChange={(e) => setDateWindowSourceField(e.target.value)}
                          placeholder="e.g. date, txn_date"
                        />
                      </div>
                      <div style={{ flex: 1 }}>
                        <label style={{ display: 'block', marginBottom: 2 }}>Target Date Col</label>
                        <input
                          type="text"
                          className="form-input"
                          style={{ width: '100%', padding: '4px 8px' }}
                          value={dateWindowTargetField}
                          onChange={(e) => setDateWindowTargetField(e.target.value)}
                          placeholder="e.g. date, settled_date"
                        />
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <div style={{ flex: 1 }}>
                        <label style={{ display: 'block', marginBottom: 2 }}>Lag Before (Days)</label>
                        <input
                          type="number"
                          min="0"
                          className="form-input"
                          style={{ width: '100%', padding: '4px 8px' }}
                          value={dateWindowLagBefore}
                          onChange={(e) => setDateWindowLagBefore(parseInt(e.target.value, 10) || 0)}
                        />
                      </div>
                      <div style={{ flex: 1 }}>
                        <label style={{ display: 'block', marginBottom: 2 }}>Lag After (Days)</label>
                        <input
                          type="number"
                          min="0"
                          className="form-input"
                          style={{ width: '100%', padding: '4px 8px' }}
                          value={dateWindowLagAfter}
                          onChange={(e) => setDateWindowLagAfter(parseInt(e.target.value, 10) || 0)}
                        />
                      </div>
                    </div>
                  </div>
                )}
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

            {/* Compound Predicates (Where Conditions) */}
            <div className="card" style={{ padding: '16px', marginBottom: 20 }}>
              <h4 style={{ margin: '0 0 6px 0', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Filter size={16} className="text-accent" /> Structured Record Predicates &amp; Compound Filters
              </h4>
              <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                Pre-filter or restrict dataset records before evaluating cross-source reconciliation.
              </p>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Field (e.g. currency, status)"
                  style={{ width: 180, fontSize: '0.85rem' }}
                  value={newPredField}
                  onChange={(e) => setNewPredField(e.target.value)}
                />
                <select
                  className="form-select"
                  style={{ width: 140, fontSize: '0.85rem' }}
                  value={newPredOp}
                  onChange={(e) => setNewPredOp(e.target.value as PredicateOperator)}
                >
                  <option value="equal">equal (==)</option>
                  <option value="not_equal">not_equal (!=)</option>
                  <option value="greater_than">greater_than (&gt;)</option>
                  <option value="less_than">less_than (&lt;)</option>
                  <option value="in">in (comma-sep)</option>
                  <option value="not_in">not_in (comma-sep)</option>
                  <option value="regex">regex matches</option>
                </select>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Target value"
                  style={{ flex: 1, minWidth: 150, fontSize: '0.85rem' }}
                  value={newPredValue}
                  onChange={(e) => setNewPredValue(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={handleAddPredicate}
                  disabled={!newPredField.trim()}
                >
                  <Plus size={14} /> Add Predicate
                </button>
              </div>

              {whereConditions.length > 0 ? (
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {whereConditions.map((cond, idx) => (
                    <span
                      key={idx}
                      className="badge"
                      style={{
                        backgroundColor: 'var(--bg-subtle)',
                        border: '1px solid var(--border-color)',
                        padding: '6px 10px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        fontSize: '0.82rem',
                      }}
                    >
                      <code>{cond.field}</code>
                      <span className="text-dim">{cond.operator}</span>
                      <strong>{String(cond.value)}</strong>
                      <button
                        type="button"
                        onClick={() => handleRemovePredicate(idx)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex', color: 'var(--danger-text)' }}
                      >
                        <Trash2 size={13} />
                      </button>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-dim" style={{ fontSize: '0.82rem', margin: 0 }}>
                  No predicates defined. All records from all sources will participate in reconciliation.
                </p>
              )}
            </div>

            {/* Split-Payment / Aggregation Toggle & Configuration */}
            <div className="card" style={{ padding: '16px', marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <h4 style={{ margin: 0, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Split size={16} className="text-accent" /> One-to-Many (1:N) &amp; Split-Payment Aggregation
                </h4>
                <label className="switch" style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={aggregationEnabled}
                    onChange={(e) => setAggregationEnabled(e.target.checked)}
                  />
                  <span style={{ fontSize: '0.8rem' }}>{aggregationEnabled ? 'Enabled' : 'Disabled'}</span>
                </label>
              </div>
              <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                Match a single parent order/invoice against multiple installment or settlement receipts on a secondary source.
              </p>
              {aggregationEnabled && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, fontSize: '0.82rem' }}>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Parent Source Alias</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationParentAlias || (uploadedDatasets[0] ? getAlias(uploadedDatasets[0].id, 0) : '')}
                      onChange={(e) => setAggregationParentAlias(e.target.value)}
                      placeholder="e.g. erp, invoice"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Child / Installments Alias</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationChildAlias || (uploadedDatasets[1] ? getAlias(uploadedDatasets[1].id, 1) : '')}
                      onChange={(e) => setAggregationChildAlias(e.target.value)}
                      placeholder="e.g. gateway, bank"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Parent Key Field</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationParentKey}
                      onChange={(e) => setAggregationParentKey(e.target.value)}
                      placeholder="e.g. id, invoice_id"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Child Grouping Key</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationChildGroupKey}
                      onChange={(e) => setAggregationChildGroupKey(e.target.value)}
                      placeholder="e.g. parent_id, order_id"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Parent Amount Field</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationParentAmountField}
                      onChange={(e) => setAggregationParentAmountField(e.target.value)}
                      placeholder="e.g. total_amount, amount"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Child Installment Amount Field</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationChildAmountField}
                      onChange={(e) => setAggregationChildAmountField(e.target.value)}
                      placeholder="e.g. installment_amount, amount"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Child Receipt ID Field (optional)</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationChildReceiptIdField}
                      onChange={(e) => setAggregationChildReceiptIdField(e.target.value)}
                      placeholder="e.g. receipt_id, txn_id"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Sum Tolerance (±)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationNumericTolerance}
                      onChange={(e) => setAggregationNumericTolerance(parseFloat(e.target.value) || 0)}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Live Rule Dry-Run / Preview Panel */}
            <div className="card" style={{ padding: '16px', marginBottom: 24, border: '1px solid var(--accent-border, var(--border-color))' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Sparkles size={16} className="text-accent" /> Live Rule Impact Dry-Run &amp; Simulation
                  </h4>
                  <p className="text-dim" style={{ fontSize: '0.82rem', margin: '2px 0 0 0' }}>
                    Evaluate your active rules against uploaded sources to view anticipated pass rates before executing.
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => void handlePreviewRules()}
                  disabled={previewingRules}
                >
                  {previewingRules ? <span className="spinner" /> : <Eye size={14} />}
                  Preview Rule Impact
                </button>
              </div>

              {previewError && (
                <div className="alert alert-error" style={{ marginBottom: 12 }}>
                  <AlertCircle size={15} />
                  <span>{previewError}</span>
                </div>
              )}

              {rulePreviewResult && (
                <div style={{ backgroundColor: 'var(--bg-subtle)', borderRadius: 'var(--radius-sm)', padding: '12px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 12 }}>
                    <div>
                      <span className="metric-label" style={{ fontSize: '0.75rem' }}>Evaluated</span>
                      <span className="metric-value" style={{ fontSize: '1.1rem' }}>
                        {rulePreviewResult.total_evaluated}
                      </span>
                    </div>
                    <div>
                      <span className="metric-label" style={{ fontSize: '0.75rem' }}>Projected Passes</span>
                      <span className="metric-value text-success" style={{ fontSize: '1.1rem' }}>
                        {rulePreviewResult.passed_count}
                      </span>
                    </div>
                    <div>
                      <span className="metric-label" style={{ fontSize: '0.75rem' }}>Projected Exceptions</span>
                      <span className="metric-value text-danger" style={{ fontSize: '1.1rem' }}>
                        {rulePreviewResult.exception_count}
                      </span>
                    </div>
                    <div>
                      <span className="metric-label" style={{ fontSize: '0.75rem' }}>Pass Rate</span>
                      <span className="metric-value" style={{ fontSize: '1.1rem' }}>
                        {rulePreviewResult.total_evaluated > 0
                          ? `${((rulePreviewResult.passed_count / rulePreviewResult.total_evaluated) * 100).toFixed(1)}%`
                          : '100%'}
                      </span>
                    </div>
                  </div>

                  {rulePreviewResult.exceptions_by_rule && Object.keys(rulePreviewResult.exceptions_by_rule).length > 0 && (
                    <div style={{ marginBottom: 10 }}>
                      <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-dim)', marginRight: 8 }}>
                        Reason Breakdown:
                      </span>
                      {Object.entries(rulePreviewResult.exceptions_by_rule).map(([k, count]) => (
                        <span key={k} className="badge badge-warning" style={{ fontSize: '0.75rem', marginRight: 6 }}>
                          {k}: {String(count)}
                        </span>
                      ))}
                    </div>
                  )}

                  {rulePreviewResult.sample_discrepancies && rulePreviewResult.sample_discrepancies.length > 0 && (
                    <div style={{ fontSize: '0.8rem' }}>
                      <span style={{ fontWeight: 600, color: 'var(--text-dim)', display: 'block', marginBottom: 4 }}>
                        Sample Exception Records:
                      </span>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {rulePreviewResult.sample_discrepancies.slice(0, 3).map((item, idx) => (
                          <div
                            key={idx}
                            style={{
                              padding: '6px 8px',
                              backgroundColor: 'var(--bg-card)',
                              borderRadius: 'var(--radius-xs)',
                              border: '1px solid var(--border-color)',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                            }}
                          >
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem' }}>
                              {item.key ? JSON.stringify(item.key) : `Row ${item.source_row ?? idx + 1}`}
                            </span>
                            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                              <StatusBadge status={item.status} />
                              <span className="text-dim" style={{ fontSize: '0.75rem' }}>
                                {item.reason || item.message}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
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
                  <option value="aggregation_mismatch">Aggregation mismatches</option>
                  <option value="rule_violation">Rule violations</option>
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
                  <option value="partial_payment">Partial payment</option>
                  <option value="overpayment">Overpayment</option>
                  <option value="unmatched_split_record">Orphan split record</option>
                  <option value="duplicate_receipt">Duplicate receipt</option>
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
                          {row.child_records && row.child_records.length > 0 && (
                            <div style={{ marginBottom: 6 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                <span className="badge badge-accent" style={{ fontSize: '0.75rem' }}>
                                  {row.child_records.length} Split Installments
                                </span>
                                {row.aggregated_amount != null && row.expected_amount != null && (
                                  <span style={{ fontSize: '0.78rem', fontFamily: 'var(--font-mono)' }}>
                                    Sum: <strong>${row.aggregated_amount.toFixed(2)}</strong> (Parent: ${row.expected_amount.toFixed(2)})
                                  </span>
                                )}
                              </div>
                              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                {row.child_records.map((c, i) => (
                                  <span
                                    key={i}
                                    className="badge"
                                    style={{
                                      backgroundColor: 'var(--bg-subtle)',
                                      fontSize: '0.72rem',
                                      padding: '2px 6px',
                                      fontFamily: 'var(--font-mono)',
                                    }}
                                  >
                                    #{c.source_row_index} {c.receipt_id ? `rcpt:${c.receipt_id}` : `rec:${c.record_id}`}: ${c.amount}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
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
