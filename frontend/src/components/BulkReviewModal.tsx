import React, { useState } from 'react';
import type { ExceptionCluster } from '../types';
import { api } from '../services/api';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Layers,
  ShieldAlert,
  UserCheck,
  X,
} from 'lucide-react';

interface BulkReviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  projectId: string;
  runId: string;
  cluster?: ExceptionCluster | null;
  selectedRecordIds?: string[];
  selectedExposure?: number;
  totalSelectedCount?: number;
}

export const BulkReviewModal: React.FC<BulkReviewModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  projectId,
  runId,
  cluster,
  selectedRecordIds = [],
  selectedExposure,
  totalSelectedCount,
}) => {
  const [activeTab, setActiveTab] = useState<'decision' | 'assignment'>('decision');
  const [decision, setDecision] = useState<'APPROVE' | 'REJECT' | 'FORCE_MATCH' | 'ESCALATE' | 'REOPEN'>('APPROVE');
  const [justification, setJustification] = useState<string>('');
  const [reviewerInput, setReviewerInput] = useState<string>('');
  const [allowBlockingOverride, setAllowBlockingOverride] = useState<boolean>(false);
  const [maxExposureLimit, setMaxExposureLimit] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [resultReport, setResultReport] = useState<{
    succeeded: number;
    failed: number;
    ineligible: number;
    failedRecords: Array<{ id: string; reason: string }>;
  } | null>(null);

  if (!isOpen) return null;

  const count = cluster ? cluster.total_records : (totalSelectedCount ?? selectedRecordIds.length);
  const exposure = cluster ? cluster.total_exposure : (selectedExposure ?? 0);
  const currency = cluster?.currency || 'USD';
  const currSym = currency === 'EUR' ? '€' : '$';

  const isHighExposure = exposure >= 5000;
  const isBlocking = cluster?.severity?.toUpperCase() === 'BLOCKING';

  const handleSubmitDecision = async () => {
    if (!justification.trim()) {
      setError('A mandatory justification note is required to apply review decisions.');
      return;
    }

    setLoading(true);
    setError(null);
    setResultReport(null);

    try {
      const maxThresh = maxExposureLimit.trim() ? parseFloat(maxExposureLimit) : undefined;
      const res = await api.applyBulkReview(projectId, runId, {
        decision,
        justification: justification.trim(),
        cluster_id: cluster ? cluster.cluster_id : undefined,
        discrepancy_ids: !cluster && selectedRecordIds.length > 0 ? selectedRecordIds : undefined,
        max_exposure_threshold: maxThresh,
        allow_blocking_override: allowBlockingOverride,
      });

      if (res.failed_count > 0) {
        setResultReport({
          succeeded: res.succeeded_count,
          failed: res.failed_count,
          ineligible: res.ineligible_count,
          failedRecords: res.failed_records,
        });
      } else {
        onSuccess();
        onClose();
      }
    } catch (err: any) {
      setError(err.message || 'Failed to submit bulk review decision.');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitAssignment = async () => {
    if (!reviewerInput.trim()) {
      setError('Please provide a reviewer name or email address.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await api.assignReviewer(projectId, runId, {
        reviewer_id: reviewerInput.trim(),
        reviewer_email: reviewerInput.includes('@') ? reviewerInput.trim() : undefined,
        cluster_id: cluster ? cluster.cluster_id : undefined,
        discrepancy_ids: !cluster && selectedRecordIds.length > 0 ? selectedRecordIds : undefined,
      });
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to assign reviewer.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="modal-backdrop"
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        backdropFilter: 'blur(3px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1100,
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        className="card"
        style={{
          width: '100%',
          maxWidth: 640,
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-color)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: '0 20px 40px rgba(0,0,0,0.4)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          maxHeight: '90vh',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid var(--border-color)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'var(--bg-card-hover)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Layers size={20} className="text-accent" />
            <div>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600 }}>
                {cluster ? 'Bulk Cluster Review' : 'Bulk Record Review'}
              </h3>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-dim)' }}>
                {cluster ? cluster.cluster_name : `${count} selected exceptions`}
              </span>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            style={{ padding: 6 }}
            onClick={onClose}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Tab Switcher */}
        <div
          style={{
            display: 'flex',
            borderBottom: '1px solid var(--border-color)',
            backgroundColor: 'var(--bg-card)',
          }}
        >
          <button
            type="button"
            className="btn btn-ghost"
            style={{
              flex: 1,
              borderRadius: 0,
              borderBottom: activeTab === 'decision' ? '2px solid var(--accent-primary)' : '2px solid transparent',
              color: activeTab === 'decision' ? 'var(--text-main)' : 'var(--text-dim)',
              fontWeight: activeTab === 'decision' ? 600 : 400,
              padding: '10px 16px',
            }}
            onClick={() => {
              setActiveTab('decision');
              setError(null);
            }}
          >
            Resolution Decision
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            style={{
              flex: 1,
              borderRadius: 0,
              borderBottom: activeTab === 'assignment' ? '2px solid var(--accent-primary)' : '2px solid transparent',
              color: activeTab === 'assignment' ? 'var(--text-main)' : 'var(--text-dim)',
              fontWeight: activeTab === 'assignment' ? 600 : 400,
              padding: '10px 16px',
            }}
            onClick={() => {
              setActiveTab('assignment');
              setError(null);
            }}
          >
            Assign Reviewer
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ padding: 20, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Target Impact Banner */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 12,
              padding: 12,
              backgroundColor: 'var(--bg-card-hover)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            <div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Total Affected Records
              </span>
              <div style={{ fontSize: '1.2rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                {count.toLocaleString()}
              </div>
            </div>
            <div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>
                Aggregated Financial Exposure
              </span>
              <div
                style={{
                  fontSize: '1.2rem',
                  fontWeight: 700,
                  fontFamily: 'var(--font-mono)',
                  color: exposure > 0 ? 'var(--warning-text)' : 'var(--text-main)',
                }}
              >
                {currSym}
                {exposure.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>
          </div>

          {/* Warnings for Exposure or Blocking */}
          {isHighExposure && (
            <div
              className="alert alert-warning"
              style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.82rem' }}
            >
              <AlertTriangle size={18} style={{ flexShrink: 0 }} />
              <div>
                <strong>High Materiality Exception Cluster:</strong> Total exposure exceeds $5,000. Ensure you provide a
                detailed audit justification before confirming resolution.
              </div>
            </div>
          )}

          {isBlocking && (
            <div
              className="alert alert-danger"
              style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.82rem' }}
            >
              <ShieldAlert size={18} style={{ flexShrink: 0 }} />
              <div>
                <strong>Hard Blocking Rule Safeguard:</strong> This cluster contains BLOCKING rule failures. Bulk
                approval requires explicit override attestation.
              </div>
            </div>
          )}

          {error && (
            <div
              className="alert alert-danger"
              style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.85rem' }}
            >
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {/* Partial Success Report if returned */}
          {resultReport && (
            <div
              style={{
                backgroundColor: 'var(--bg-card-hover)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-sm)',
                padding: 12,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <AlertTriangle size={16} className="text-warning" />
                <strong style={{ fontSize: '0.9rem' }}>
                  Partial Bulk Resolution ({resultReport.succeeded} resolved, {resultReport.failed} blocked)
                </strong>
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: '0.8rem', color: 'var(--danger-text)' }}>
                {resultReport.failedRecords.slice(0, 5).map((f) => (
                  <li key={f.id}>{f.reason}</li>
                ))}
              </ul>
              <div style={{ marginTop: 10 }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    onSuccess();
                    onClose();
                  }}
                >
                  Close &amp; Refresh Results
                </button>
              </div>
            </div>
          )}

          {/* TAB 1: DECISION */}
          {activeTab === 'decision' && !resultReport && (
            <>
              <div>
                <label style={{ fontSize: '0.85rem', fontWeight: 600, display: 'block', marginBottom: 8 }}>
                  Select Resolution Action:
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: 8 }}>
                  {(['APPROVE', 'REJECT', 'FORCE_MATCH', 'ESCALATE', 'REOPEN'] as const).map((opt) => {
                    const isSelected = decision === opt;
                    const colors: Record<string, { bg: string; text: string }> = {
                      APPROVE: { bg: 'var(--success-soft)', text: 'var(--success-text)' },
                      REJECT: { bg: 'var(--danger-soft)', text: 'var(--danger-text)' },
                      FORCE_MATCH: { bg: 'var(--accent-soft)', text: 'var(--accent-primary)' },
                      ESCALATE: { bg: 'var(--warning-soft)', text: 'var(--warning-text)' },
                      REOPEN: { bg: 'var(--bg-card-hover)', text: 'var(--text-main)' },
                    };
                    const c = colors[opt];
                    return (
                      <button
                        key={opt}
                        type="button"
                        className="btn"
                        style={{
                          backgroundColor: isSelected ? c.bg : 'var(--bg-card-hover)',
                          color: isSelected ? c.text : 'var(--text-dim)',
                          border: isSelected ? `2px solid ${c.text}` : '1px solid var(--border-color)',
                          fontWeight: isSelected ? 600 : 400,
                          fontSize: '0.78rem',
                          padding: '8px 10px',
                        }}
                        onClick={() => setDecision(opt)}
                      >
                        {opt.replace('_', ' ')}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Safeguard Options */}
              {(decision === 'APPROVE' || decision === 'FORCE_MATCH') && (
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10,
                    padding: 10,
                    backgroundColor: 'var(--bg-card-hover)',
                    borderRadius: 'var(--radius-sm)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <label style={{ fontSize: '0.82rem', color: 'var(--text-dim)', flex: 1 }}>
                      Max Record Exposure Threshold ($):
                    </label>
                    <input
                      type="number"
                      className="form-input"
                      placeholder="e.g. 5000"
                      value={maxExposureLimit}
                      onChange={(e) => setMaxExposureLimit(e.target.value)}
                      style={{ width: 120, fontSize: '0.8rem', padding: '4px 8px' }}
                    />
                  </div>

                  {isBlocking && (
                    <label
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        fontSize: '0.82rem',
                        cursor: 'pointer',
                        color: 'var(--danger-text)',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={allowBlockingOverride}
                        onChange={(e) => setAllowBlockingOverride(e.target.checked)}
                      />
                      <span>Allow override on hard BLOCKING rule failures</span>
                    </label>
                  )}
                </div>
              )}

              {/* Mandatory Justification Note */}
              <div>
                <label style={{ fontSize: '0.85rem', fontWeight: 600, display: 'block', marginBottom: 6 }}>
                  Mandatory Audit Justification Note: <span style={{ color: 'var(--danger-text)' }}>*</span>
                </label>
                <textarea
                  className="form-textarea"
                  rows={3}
                  placeholder="e.g. Approved differences: verified with partner bank that lag was caused by public holiday settlement schedule."
                  value={justification}
                  onChange={(e) => setJustification(e.target.value)}
                  style={{ width: '100%', fontSize: '0.82rem' }}
                />
              </div>
            </>
          )}

          {/* TAB 2: ASSIGNMENT */}
          {activeTab === 'assignment' && (
            <div>
              <label style={{ fontSize: '0.85rem', fontWeight: 600, display: 'block', marginBottom: 6 }}>
                Assignee Name or Email Address: <span style={{ color: 'var(--danger-text)' }}>*</span>
              </label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. auditor@enterprise.com or Jane Doe"
                value={reviewerInput}
                onChange={(e) => setReviewerInput(e.target.value)}
                style={{ width: '100%', marginBottom: 12, fontSize: '0.85rem' }}
              />
              <p style={{ fontSize: '0.78rem', color: 'var(--text-dim)', margin: 0 }}>
                Assigning will flag all {count} records in this cluster to the designated reviewer and enable
                quick-filtering via the &quot;Assigned to Me&quot; filter.
              </p>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '14px 20px',
            borderTop: '1px solid var(--border-color)',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 10,
            backgroundColor: 'var(--bg-card-hover)',
          }}
        >
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={loading}>
            Cancel
          </button>
          {activeTab === 'decision' ? (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void handleSubmitDecision()}
              disabled={loading}
            >
              {loading ? (
                'Submitting...'
              ) : (
                <>
                  <CheckCircle2 size={16} /> Apply {decision.replace('_', ' ')} ({count})
                </>
              )}
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void handleSubmitAssignment()}
              disabled={loading}
            >
              {loading ? (
                'Assigning...'
              ) : (
                <>
                  <UserCheck size={16} /> Assign {count} Records
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
