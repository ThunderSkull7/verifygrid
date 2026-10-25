import React, { useEffect, useState } from 'react';
import type {
  FileProfileSummary,
  QuarantineListResponse,
  QuarantinedRecord,
  ResolutionAction,
} from '../types';
import { api } from '../services/api';
import {
  AlertOctagon,
  AlertTriangle,
  Check,
  CheckCircle2,
  Database,
  Filter,
  Key,
  Layers,
  Save,
  ShieldAlert,
  ShieldCheck,
  Table,
  X,
} from 'lucide-react';

interface ProfilingQuarantineDrawerProps {
  projectId: string;
  fileId: string;
  filename: string;
  isOpen: boolean;
  onClose: () => void;
  onResolutionsUpdated?: () => void;
}

export const ProfilingQuarantineDrawer: React.FC<ProfilingQuarantineDrawerProps> = ({
  projectId,
  fileId,
  filename,
  isOpen,
  onClose,
  onResolutionsUpdated,
}) => {
  const [activeTab, setActiveTab] = useState<'profiling' | 'quarantine'>('profiling');
  const [profile, setProfile] = useState<FileProfileSummary | null>(null);
  const [quarantineData, setQuarantineData] = useState<QuarantineListResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Local pending resolutions: map source_row_index -> action
  const [pendingResolutions, setPendingResolutions] = useState<Record<number, ResolutionAction>>({});
  const [reasonFilter, setReasonFilter] = useState<string>('all');
  const [severityFilter, setSeverityFilter] = useState<string>('all');

  useEffect(() => {
    if (!isOpen) return;

    let cancelled = false;
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      setSuccessMessage(null);
      try {
        const [prof, quar] = await Promise.all([
          api.getFileProfile(projectId, fileId),
          api.getFileQuarantine(projectId, fileId),
        ]);
        if (!cancelled) {
          setProfile(prof);
          setQuarantineData(quar);
          // Initialize local resolution state from loaded quarantine data
          const initialMap: Record<number, ResolutionAction> = {};
          quar.records.forEach((r) => {
            initialMap[r.source_row_index] = r.resolution_action;
          });
          setPendingResolutions(initialMap);
          if (quar.records.length > 0) {
            setActiveTab('quarantine');
          }
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message || 'Failed to load file profile and quarantine data.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void fetchData();
    return () => {
      cancelled = true;
    };
  }, [isOpen, projectId, fileId]);

  if (!isOpen) return null;

  const handleActionToggle = (rowIndex: number, action: ResolutionAction) => {
    setPendingResolutions((prev) => {
      const current = prev[rowIndex] || 'PENDING';
      const updated = current === action ? 'PENDING' : action;
      return { ...prev, [rowIndex]: updated };
    });
    setSuccessMessage(null);
  };

  const handleBatchAction = (action: ResolutionAction, targetSeverity?: string) => {
    if (!quarantineData) return;
    setPendingResolutions((prev) => {
      const next = { ...prev };
      quarantineData.records.forEach((r) => {
        if (!targetSeverity || r.severity === targetSeverity) {
          next[r.source_row_index] = action;
        }
      });
      return next;
    });
    setSuccessMessage(null);
  };

  const handleSaveResolutions = async () => {
    if (!quarantineData) return;
    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    const items = Object.entries(pendingResolutions).map(([rowIdxStr, action]) => ({
      source_row_index: parseInt(rowIdxStr, 10),
      action,
    }));

    try {
      const resp = await api.resolveQuarantine(projectId, fileId, { resolutions: items });
      setQuarantineData((prev) =>
        prev
          ? {
              ...prev,
              records: resp.quarantined_records,
              impact_preview: resp.impact_preview,
            }
          : null
      );
      if (profile) {
        setProfile({ ...profile, impact_preview: resp.impact_preview });
      }
      setSuccessMessage(`Saved decisions for ${resp.resolved_count} flagged row(s).`);
      if (onResolutionsUpdated) {
        onResolutionsUpdated();
      }
    } catch (err: any) {
      setError(err.message || 'Failed to save quarantine resolutions.');
    } finally {
      setSaving(false);
    }
  };

  const impact = quarantineData?.impact_preview || profile?.impact_preview;

  // Filter quarantined records
  const filteredQuarantined = (quarantineData?.records || []).filter((r) => {
    if (reasonFilter !== 'all' && r.quarantine_reason !== reasonFilter) return false;
    if (severityFilter !== 'all' && r.severity !== severityFilter) return false;
    return true;
  });

  return (
    <div
      className="modal-backdrop"
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'var(--bg-overlay)',
        zIndex: 1000,
        display: 'flex',
        justifyContent: 'flex-end',
        backdropFilter: 'blur(3px)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="drawer-panel"
        style={{
          width: '100%',
          maxWidth: '920px',
          height: '100vh',
          backgroundColor: 'var(--bg-card)',
          boxShadow: 'var(--shadow-lg)',
          display: 'flex',
          flexDirection: 'column',
          borderLeft: '1px solid var(--border-color)',
          overflow: 'hidden',
          animation: 'slideIn 0.22s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid var(--border-color)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'var(--bg-secondary)',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Database size={20} className="text-accent" />
              <h2 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 600 }}>
                Pre-flight Profiling &amp; Quarantine
              </h2>
              <span className="badge badge-neutral">{filename}</span>
            </div>
            <p className="text-dim" style={{ margin: '4px 0 0 0', fontSize: '0.85rem' }}>
              Inspect data health, candidate key uniqueness, and resolve flagged anomalies before reconciliation.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onClose}
            aria-label="Close drawer"
          >
            <X size={16} />
          </button>
        </div>

        {/* Impact Preview Metrics Strip */}
        {impact && (
          <div
            style={{
              padding: '14px 24px',
              backgroundColor: 'var(--bg-subtle)',
              borderBottom: '1px solid var(--border-color)',
              display: 'grid',
              gridTemplateColumns: 'repeat(5, 1fr)',
              gap: 12,
            }}
          >
            <div className="metric-card flat" style={{ padding: '8px 12px' }}>
              <span className="metric-label" style={{ fontSize: '0.75rem' }}>Total Rows</span>
              <span className="metric-value" style={{ fontSize: '1.2rem' }}>
                {impact.total_source_rows.toLocaleString()}
              </span>
            </div>
            <div className="metric-card flat" style={{ padding: '8px 12px' }}>
              <span className="metric-label" style={{ fontSize: '0.75rem' }}>Eligible for Run</span>
              <span className="metric-value text-success" style={{ fontSize: '1.2rem' }}>
                {impact.eligible_rows_count.toLocaleString()}
              </span>
            </div>
            <div className="metric-card flat" style={{ padding: '8px 12px' }}>
              <span className="metric-label" style={{ fontSize: '0.75rem' }}>Excluded Rows</span>
              <span className="metric-value text-danger" style={{ fontSize: '1.2rem' }}>
                {impact.excluded_rows_count.toLocaleString()}
              </span>
            </div>
            <div className="metric-card flat" style={{ padding: '8px 12px' }}>
              <span className="metric-label" style={{ fontSize: '0.75rem' }}>Blocking Flags</span>
              <span className="metric-value" style={{ fontSize: '1.2rem', color: impact.blocking_quarantine_count > 0 ? 'var(--danger)' : 'var(--text-main)' }}>
                {impact.blocking_quarantine_count}
              </span>
            </div>
            <div className="metric-card flat" style={{ padding: '8px 12px' }}>
              <span className="metric-label" style={{ fontSize: '0.75rem' }}>Warnings</span>
              <span className="metric-value" style={{ fontSize: '1.2rem', color: impact.warning_quarantine_count > 0 ? 'var(--warning)' : 'var(--text-main)' }}>
                {impact.warning_quarantine_count}
              </span>
            </div>
          </div>
        )}

        {/* Tab Navigation */}
        <div
          style={{
            display: 'flex',
            borderBottom: '1px solid var(--border-color)',
            padding: '0 24px',
            backgroundColor: 'var(--bg-secondary)',
          }}
        >
          <button
            type="button"
            className={`tab-btn ${activeTab === 'profiling' ? 'active' : ''}`}
            onClick={() => setActiveTab('profiling')}
            style={{
              padding: '12px 18px',
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.9rem',
              color: activeTab === 'profiling' ? 'var(--primary-text)' : 'var(--text-muted)',
              borderBottom: activeTab === 'profiling' ? '2px solid var(--primary)' : '2px solid transparent',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <Table size={16} /> Column Profiles &amp; Keys
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'quarantine' ? 'active' : ''}`}
            onClick={() => setActiveTab('quarantine')}
            style={{
              padding: '12px 18px',
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.9rem',
              color: activeTab === 'quarantine' ? 'var(--primary-text)' : 'var(--text-muted)',
              borderBottom: activeTab === 'quarantine' ? '2px solid var(--primary)' : '2px solid transparent',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <ShieldAlert size={16} /> Flagged Quarantine Records
            {quarantineData && quarantineData.records.length > 0 && (
              <span
                className="badge"
                style={{
                  backgroundColor: 'var(--danger-soft)',
                  color: 'var(--danger-text)',
                  fontSize: '0.75rem',
                  padding: '1px 6px',
                }}
              >
                {quarantineData.records.length}
              </span>
            )}
          </button>
        </div>

        {/* Body content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
          {error && (
            <div className="alert alert-error" style={{ marginBottom: 16 }}>
              <AlertTriangle size={16} />
              <span>{error}</span>
            </div>
          )}

          {successMessage && (
            <div className="alert alert-success" style={{ marginBottom: 16 }}>
              <CheckCircle2 size={16} />
              <span>{successMessage}</span>
            </div>
          )}

          {loading ? (
            <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-muted)' }}>
              <div className="spinner" style={{ margin: '0 auto 12px auto' }} />
              <p>Analyzing dataset schema, candidate keys, and anomaly flags…</p>
            </div>
          ) : activeTab === 'profiling' && profile ? (
            <div>
              {/* Candidate Keys Section */}
              <div style={{ marginBottom: 28 }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 12px 0' }}>
                  <Key size={16} className="text-accent" /> Candidate Key Evaluation
                </h4>
                {profile.candidate_keys.length === 0 ? (
                  <p className="text-dim">No natural candidate keys detected with &gt;50% uniqueness.</p>
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
                    {profile.candidate_keys.map((ck) => (
                      <div
                        key={ck.column_name}
                        className="card"
                        style={{
                          padding: '14px',
                          borderLeft: ck.is_viable_key ? '4px solid var(--success)' : '4px solid var(--warning)',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                          <strong style={{ fontSize: '0.95rem' }}>{ck.column_name}</strong>
                          {ck.is_viable_key ? (
                            <span className="badge badge-success">Viable Key</span>
                          ) : (
                            <span className="badge badge-warning">Collisions / Nulls</span>
                          )}
                        </div>
                        <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 6 }}>
                          Uniqueness: {(ck.uniqueness_ratio * 100).toFixed(1)}% · Nulls: {ck.null_count} · Collisions: {ck.duplicate_count}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                          {ck.recommendation}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Column Profiling Table */}
              <div>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 12px 0' }}>
                  <Layers size={16} className="text-accent" /> Inferred Schema &amp; Column Metrics ({profile.columns.length})
                </h4>
                <div className="table-container" style={{ overflowX: 'auto', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)' }}>
                  <table className="data-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                    <thead>
                      <tr>
                        <th>Column</th>
                        <th>Inferred Type</th>
                        <th>Nulls (%)</th>
                        <th>Distinct</th>
                        <th>Uniqueness</th>
                        <th>Sample Values</th>
                        <th>Anomalies</th>
                      </tr>
                    </thead>
                    <tbody>
                      {profile.columns.map((col) => (
                        <tr key={col.column_name}>
                          <td>
                            <strong>{col.original_name}</strong>
                            {col.is_candidate_key && (
                              <span className="badge badge-success" style={{ marginLeft: 6, fontSize: '0.7rem' }}>
                                Key
                              </span>
                            )}
                          </td>
                          <td>
                            <code className="key-code">{col.inferred_type}</code>
                          </td>
                          <td>
                            {col.null_count > 0 ? (
                              <span style={{ color: 'var(--warning-text)' }}>
                                {col.null_count} ({(col.null_percentage * 100).toFixed(1)}%)
                              </span>
                            ) : (
                              <span className="text-dim">0 (0%)</span>
                            )}
                          </td>
                          <td>{col.distinct_count}</td>
                          <td>{(col.uniqueness_ratio * 100).toFixed(1)}%</td>
                          <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            <span className="text-dim">{col.sample_values.join(', ') || '—'}</span>
                          </td>
                          <td>
                            {col.anomalies_count > 0 ? (
                              <span className="badge" style={{ backgroundColor: 'var(--danger-soft)', color: 'var(--danger-text)' }}>
                                {col.anomalies_count}
                              </span>
                            ) : (
                              <span className="text-dim">0</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : activeTab === 'quarantine' ? (
            <div>
              {/* Quarantine Header Controls */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 16,
                  flexWrap: 'wrap',
                  gap: 12,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Filter size={15} className="text-dim" />
                  <select
                    className="form-select filter-select"
                    value={reasonFilter}
                    onChange={(e) => setReasonFilter(e.target.value)}
                    aria-label="Filter by quarantine reason"
                    style={{ fontSize: '0.85rem' }}
                  >
                    <option value="all">All reasons</option>
                    <option value="MALFORMED_DATE">Malformed Date</option>
                    <option value="INVALID_NUMBER">Invalid Number</option>
                    <option value="DUPLICATE_KEY">Duplicate Key</option>
                    <option value="UNEXPECTED_NEGATIVE_AMOUNT">Unexpected Negative Amount</option>
                    <option value="SHIFTED_ROW">Shifted Row</option>
                  </select>

                  <select
                    className="form-select filter-select"
                    value={severityFilter}
                    onChange={(e) => setSeverityFilter(e.target.value)}
                    aria-label="Filter by severity"
                    style={{ fontSize: '0.85rem' }}
                  >
                    <option value="all">All severities</option>
                    <option value="BLOCKING">Blocking</option>
                    <option value="WARNING">Warning</option>
                  </select>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleBatchAction('EXCLUDE')}
                  >
                    Exclude All
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleBatchAction('ACCEPT_AS_VALID', 'WARNING')}
                  >
                    Accept All Warnings
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={() => void handleSaveResolutions()}
                    disabled={saving}
                  >
                    {saving ? <span className="spinner" /> : <Save size={14} />} Save Decisions
                  </button>
                </div>
              </div>

              {filteredQuarantined.length === 0 ? (
                <div className="card empty-state" style={{ padding: '36px 20px', textAlign: 'center' }}>
                  <div className="empty-icon" style={{ margin: '0 auto 12px auto' }}>
                    <ShieldCheck size={28} className="text-success" />
                  </div>
                  <h3 className="empty-title">Zero records in quarantine</h3>
                  <p className="empty-text">
                    All rows in this source file passed pre-flight validation clean without blocking anomalies.
                  </p>
                </div>
              ) : (
                <div className="table-container" style={{ border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)' }}>
                  <table className="data-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                    <thead>
                      <tr>
                        <th style={{ width: 80 }}>Row #</th>
                        <th style={{ width: 140 }}>Column</th>
                        <th style={{ width: 140 }}>Raw Value</th>
                        <th style={{ width: 150 }}>Reason</th>
                        <th>Message</th>
                        <th style={{ width: 180, textAlign: 'right' }}>Pre-flight Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredQuarantined.map((item: QuarantinedRecord) => {
                        const currentDecision = pendingResolutions[item.source_row_index] || item.resolution_action;
                        return (
                          <tr key={item.id}>
                            <td>
                              <span className="badge badge-neutral" style={{ fontFamily: 'var(--font-mono)' }}>
                                Row {item.source_row_index}
                              </span>
                            </td>
                            <td>
                              <strong>{item.column_name}</strong>
                            </td>
                            <td>
                              <code className="key-code" style={{ fontSize: '0.8rem' }}>
                                {String(item.raw_value ?? '—')}
                              </code>
                            </td>
                            <td>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                <span
                                  className="badge"
                                  style={{
                                    backgroundColor:
                                      item.severity === 'BLOCKING' ? 'var(--danger-soft)' : 'var(--warning-soft)',
                                    color:
                                      item.severity === 'BLOCKING' ? 'var(--danger-text)' : 'var(--warning-text)',
                                    fontSize: '0.72rem',
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: 4,
                                    width: 'fit-content',
                                  }}
                                >
                                  {item.severity === 'BLOCKING' ? <AlertOctagon size={11} /> : <AlertTriangle size={11} />}
                                  {item.quarantine_reason}
                                </span>
                              </div>
                            </td>
                            <td style={{ color: 'var(--text-muted)' }}>{item.message}</td>
                            <td style={{ textAlign: 'right' }}>
                              <div style={{ display: 'inline-flex', gap: 6 }}>
                                <button
                                  type="button"
                                  className={`btn btn-xs ${
                                    currentDecision === 'EXCLUDE' ? 'btn-danger' : 'btn-secondary'
                                  }`}
                                  style={{
                                    fontSize: '0.75rem',
                                    padding: '3px 8px',
                                    backgroundColor: currentDecision === 'EXCLUDE' ? 'var(--danger)' : undefined,
                                    color: currentDecision === 'EXCLUDE' ? '#ffffff' : undefined,
                                  }}
                                  onClick={() => handleActionToggle(item.source_row_index, 'EXCLUDE')}
                                  title="Omit this row from reconciliation execution"
                                >
                                  {currentDecision === 'EXCLUDE' && <Check size={12} />} Exclude
                                </button>
                                <button
                                  type="button"
                                  className={`btn btn-xs ${
                                    currentDecision === 'ACCEPT_AS_VALID' ? 'btn-success' : 'btn-secondary'
                                  }`}
                                  style={{
                                    fontSize: '0.75rem',
                                    padding: '3px 8px',
                                    backgroundColor: currentDecision === 'ACCEPT_AS_VALID' ? 'var(--success)' : undefined,
                                    color: currentDecision === 'ACCEPT_AS_VALID' ? '#ffffff' : undefined,
                                  }}
                                  onClick={() => handleActionToggle(item.source_row_index, 'ACCEPT_AS_VALID')}
                                  title="Include row in reconciliation run despite anomaly"
                                >
                                  {currentDecision === 'ACCEPT_AS_VALID' && <Check size={12} />} Accept
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '14px 24px',
            borderTop: '1px solid var(--border-color)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'var(--bg-secondary)',
          }}
        >
          <span className="text-dim" style={{ fontSize: '0.8rem' }}>
            Raw files are strictly immutable. Pre-flight resolutions are persisted to isolation sidecars.
          </span>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
