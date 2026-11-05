import React, { useEffect, useMemo, useRef, useState } from 'react';
import type {
  DiscrepancyItemResponse,
  FieldComparisonDiff,
  SideBySideInspectionResponse,
  VerificationResultItem,
} from '../types';
import { api } from '../services/api';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { StatusBadge } from './StatusBadge';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRightLeft,
  CheckCircle,
  FileSpreadsheet,
  Maximize2,
  Minimize2,
  ShieldAlert,
  Tag,
  X,
} from 'lucide-react';

interface RecordInspectorDrawerProps {
  mode?: 'organization' | 'financial';
  fileLabels?: Record<string, string>;
  isOpen: boolean;
  onClose: () => void;
  record: VerificationResultItem | DiscrepancyItemResponse | null;
  projectId?: string;
  runId?: string;
}

export const RecordInspectorDrawer: React.FC<RecordInspectorDrawerProps> = ({
  mode = 'organization',
  fileLabels,
  isOpen,
  onClose,
  record,
  projectId,
  runId,
}) => {
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedDiff, setExpandedDiff] = useState<boolean>(false);
  const [apiInspectionData, setApiInspectionData] = useState<SideBySideInspectionResponse | null>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Focus trapping and Escape key management
  useFocusTrap(isOpen, onClose, drawerRef);

  // If record already has side_by_side structure populated, derive it directly
  const embeddedInspectionData = useMemo<SideBySideInspectionResponse | null>(() => {
    if (!record || !record.side_by_side || !record.side_by_side.field_comparisons) {
      return null;
    }
    return {
      id: record.id,
      run_id: 'run_id' in record ? (record as DiscrepancyItemResponse).run_id : runId,
      key_values: record.key_values || {},
      match_status: record.match_status,
      discrepancy_category: record.discrepancy_category,
      reason_code: record.reason_code,
      confidence_score: record.confidence_score,
      severity: record.severity || 'medium',
      source_amount: record.source_amount,
      target_amount: record.target_amount,
      variance_amount: record.variance_amount,
      exposure_amount: record.exposure_amount,
      currency: record.currency || 'USD',
      source_row_index: record.source_row_index ?? record.source_row_number,
      target_row_index: record.target_row_index ?? record.target_row_number,
      source_row_indices: record.source_row_indices,
      raw_source_record: record.side_by_side.raw_source_record || record.source_record,
      normalized_source_record: record.side_by_side.normalized_source_record,
      raw_target_record: record.side_by_side.raw_target_record || record.target_record,
      normalized_target_record: record.side_by_side.normalized_target_record,
      field_comparisons: record.side_by_side.field_comparisons || [],
      failed_rules: record.side_by_side.failed_rules || [],
      child_records: record.child_records,
      message: record.message,
      resolution_status: record.resolution_status || 'unresolved',
    };
  }, [record, runId]);

  // Load inspection data from API if not embedded
  useEffect(() => {
    if (!isOpen || !record || embeddedInspectionData) {
      return;
    }

    let cancelled = false;
    const fetchInspection = async () => {
      if (!projectId || !runId || !record.id) return;
      setLoading(true);
      setError(null);
      try {
        const data = await api.inspectDiscrepancy(projectId, runId, record.id);
        if (!cancelled) {
          setApiInspectionData(data);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message || 'Failed to load side-by-side inspection details');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void fetchInspection();
    return () => {
      cancelled = true;
    };
  }, [isOpen, record, embeddedInspectionData, projectId, runId]);

  const inspectionData = embeddedInspectionData || apiInspectionData;

  // Determine severity styling
  const severity = inspectionData?.severity || record?.severity || 'medium';
  const getSeverityBadgeClass = (s: string) => {
    switch (s.toLowerCase()) {
      case 'high':
        return 'badge-danger';
      case 'medium':
        return 'badge-warning';
      case 'low':
        return 'badge-info';
      default:
        return 'badge-neutral';
    }
  };

  const currencySymbol = (inspectionData?.currency || record?.currency) === 'EUR' ? '€' : '$';
  const exposureAmt = inspectionData?.exposure_amount ?? record?.exposure_amount ?? 0;
  const varianceAmt = inspectionData?.variance_amount ?? record?.variance_amount ?? 0;
  const sourceAmt = inspectionData?.source_amount ?? record?.source_amount ?? 0;
  const targetAmt = inspectionData?.target_amount ?? record?.target_amount ?? 0;

  // Field comparisons
  const comparisons: FieldComparisonDiff[] = inspectionData?.field_comparisons || [];

  // Clean record identifier for non-technical users (e.g. "student_id: S101 · name: Aarav")
  const recordIdentifier = useMemo(() => {
    if (!record?.key_values) return 'Record';
    const entries = Object.entries(record.key_values);
    if (entries.length === 0) return 'Record';
    return entries.map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(' · ');
  }, [record]);

  const isFinancialMode = mode === 'financial' || exposureAmt > 0 || varianceAmt !== 0;

  // Unified side-by-side comparison rows (Field | Trusted value | Submitted value | Result)
  const unifiedRows = useMemo(() => {
    if (comparisons.length > 0) {
      return comparisons.map((comp) => {
        const trusted = comp.raw_source_value ?? comp.normalized_source_value;
        const submitted = comp.raw_target_value ?? comp.normalized_target_value;
        const isMatch = Boolean(comp.is_match);
        const trustedBlank = trusted === undefined || trusted === null || String(trusted).trim() === '';
        const submittedBlank = submitted === undefined || submitted === null || String(submitted).trim() === '';
        const isMissing = !isMatch && (trustedBlank || submittedBlank || comp.difference_type?.toLowerCase().includes('missing'));

        let resultLabel: 'Match' | 'Difference' | 'Missing' = 'Match';
        if (!isMatch) {
          resultLabel = isMissing ? 'Missing' : 'Difference';
        }

        return {
          fieldName: comp.field_name,
          trustedValue: trustedBlank ? 'Blank' : String(trusted),
          trustedFile: fileLabels?.['source'] || fileLabels?.['primary'] || 'Main File (Trusted)',
          submittedValue: submittedBlank ? 'Blank' : String(submitted),
          submittedFile: fileLabels?.['target'] || 'Comparison File',
          result: resultLabel,
          differenceType: comp.difference_type,
          isMatch,
        };
      });
    }

    // Synthesize comparison rows from record data
    if (!record) return [];

    const recAny = record as any;
    const rows: Array<{
      fieldName: string;
      trustedValue: string;
      trustedFile: string;
      submittedValue: string;
      submittedFile: string;
      result: 'Match' | 'Difference' | 'Missing' | 'Not checked';
      differenceType?: string;
      isMatch: boolean;
    }> = [];

    const diffMap = new Map<string, any>();
    ((recAny.field_differences as any[]) || []).forEach((d) => diffMap.set(d.field_name, d));
    const unverifiedSet = new Set<string>((recAny.unverified_fields as string[]) || []);

    const sourceRecs = (recAny.source_records as Record<string, Record<string, unknown>>) || {};
    const primaryAlias = recAny.lineage?.primary_alias || Object.keys(sourceRecs)[0] || 'primary';
    const primaryRec = sourceRecs[primaryAlias] || recAny.source_record || {};
    const primaryLabel = fileLabels?.[primaryAlias] || 'Main File (Trusted)';

    const otherAliases = Object.keys(sourceRecs).filter((a) => a !== primaryAlias);
    const targetRec = (otherAliases.length > 0 ? sourceRecs[otherAliases[0]] : null) || recAny.target_record || {};
    const targetLabel = (otherAliases.length > 0 && fileLabels?.[otherAliases[0]]) || fileLabels?.['target'] || 'Comparison File';

    const allKeys = new Set<string>([
      ...Object.keys(primaryRec),
      ...Object.keys(targetRec),
      ...Array.from(diffMap.keys()),
      ...Array.from(unverifiedSet),
    ]);

    // Exclude matching keys from field differences
    Object.keys(recAny.key_values || {}).forEach((k) => allKeys.delete(k));

    allKeys.forEach((field) => {
      const diff = diffMap.get(field);
      const isUnverified = unverifiedSet.has(field);

      let tVal = primaryRec[field];
      let sVal = targetRec[field];

      if (diff) {
        if (diff.source_value !== undefined) tVal = diff.source_value;
        if (diff.target_value !== undefined) sVal = diff.target_value;
      }

      const tBlank = tVal === undefined || tVal === null || String(tVal).trim() === '';
      const sBlank = sVal === undefined || sVal === null || String(sVal).trim() === '';

      let res: 'Match' | 'Difference' | 'Missing' | 'Not checked' = 'Match';
      let dType = diff?.difference_type;
      let match = false;

      if (isUnverified) {
        res = 'Not checked';
        dType = 'unverified';
      } else if (diff) {
        res = (tBlank || sBlank) ? 'Missing' : 'Difference';
      } else if (tBlank && sBlank) {
        res = 'Match';
        match = true;
      } else if (tBlank || sBlank) {
        res = 'Missing';
        dType = 'missing_value';
      } else if (String(tVal).trim().toLowerCase() === String(sVal).trim().toLowerCase()) {
        res = 'Match';
        match = true;
      } else {
        res = 'Difference';
        dType = 'field_mismatch';
      }

      rows.push({
        fieldName: field,
        trustedValue: tBlank ? 'Blank' : String(tVal),
        trustedFile: primaryLabel,
        submittedValue: sBlank ? 'Blank' : String(sVal),
        submittedFile: targetLabel,
        result: res,
        differenceType: dType,
        isMatch: match,
      });
    });

    return rows;
  }, [comparisons, record, fileLabels]);

  if (!isOpen || !record) return null;

  return (
    <div
      className="modal-backdrop"
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(3px)',
        zIndex: 1000,
        display: 'flex',
        justifyContent: 'flex-end',
        padding: 0,
      }}
      onClick={onClose}
    >
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Record Inspector Side-by-Side Details"
        tabIndex={-1}
        className="record-inspector-drawer"
        style={{
          width: expandedDiff ? 'min(88vw, 1100px)' : 'min(640px, 100vw)',
          maxWidth: '100vw',
          height: '100dvh',
          maxHeight: '100dvh',
          minWidth: 0,
          backgroundColor: 'var(--bg-card, #11141d)',
          borderLeft: '1px solid var(--border-color, #222738)',
          boxShadow: '-8px 0 32px rgba(0, 0, 0, 0.45)',
          display: 'flex',
          flexDirection: 'column',
          transition: 'width 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
          overflow: 'hidden',
          zIndex: 1001,
          outline: 'none',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '18px 24px',
            borderBottom: '1px solid var(--border-color, #222738)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
            backgroundColor: 'var(--bg-subtle, #161a26)',
          }}
        >
          <div style={{ flex: '1 1 240px', minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-dim)' }}>
                RECORD DETAILS
              </span>
              <span className={`badge ${getSeverityBadgeClass(severity)}`} style={{ textTransform: 'uppercase', fontSize: '0.72rem' }}>
                <ShieldAlert size={12} style={{ marginRight: 3 }} />
                {severity} Severity
              </span>
            </div>
            <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 600, overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
              {recordIdentifier}
            </h3>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setExpandedDiff((v) => !v)}
              title={expandedDiff ? 'Collapse panel' : 'Expand panel'}
              aria-label="Toggle drawer expansion"
            >
              {expandedDiff ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={onClose}
              title="Close drawer (Esc)"
              aria-label="Close drawer"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Content body */}
        <div style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '24px' }}>
          {loading && (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-dim)' }}>
              <span className="spinner" style={{ marginBottom: 12, display: 'inline-block' }} />
              <p>Loading record details and differences…</p>
            </div>
          )}

          {error && (
            <div className="alert alert-error" style={{ marginBottom: 16 }}>
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {/* Status & Reason Summary Bar */}
          <div
            style={{
              display: 'flex',
              gap: 12,
              alignItems: 'center',
              flexWrap: 'wrap',
              marginBottom: 20,
              padding: '12px 16px',
              backgroundColor: 'var(--bg-subtle, #161a26)',
              borderRadius: 'var(--radius-sm, 6px)',
              border: '1px solid var(--border-color, #222738)',
            }}
          >
            <div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                Match Status
              </span>
              <StatusBadge status={record.match_status} />
            </div>

            {record.reason_code && (
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                  Difference Code
                </span>
                <span className="badge badge-accent" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem' }}>
                  <Tag size={12} style={{ marginRight: 4 }} />
                  {record.reason_code}
                </span>
              </div>
            )}

            {record.confidence_score !== undefined && record.confidence_score !== null && (
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                  Match Confidence
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', fontWeight: 600 }}>
                  {(record.confidence_score * 100).toFixed(1)}%
                </span>
              </div>
            )}

            <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: 2 }}>
                Review Status
              </span>
              <span
                className="badge"
                style={{
                  backgroundColor: record.resolution_status === 'resolved' ? 'var(--success-soft)' : 'var(--bg-card-hover)',
                  color: record.resolution_status === 'resolved' ? 'var(--success-text)' : 'var(--text-dim)',
                  fontSize: '0.75rem',
                }}
              >
                {record.resolution_status || 'unresolved'}
              </span>
            </div>
          </div>

          {/* KPI Panel: Financial or Organization */}
          {isFinancialMode ? (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
                gap: 12,
                marginBottom: 24,
                backgroundColor: 'rgba(239, 68, 68, 0.04)',
                border: '1px solid rgba(239, 68, 68, 0.15)',
                borderRadius: 'var(--radius-sm, 6px)',
                padding: '16px',
              }}
            >
              <div>
                <span className="metric-label" style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  Total Difference Amount
                </span>
                <span
                  style={{
                    display: 'block',
                    fontSize: '1.25rem',
                    fontWeight: 700,
                    fontFamily: 'var(--font-mono)',
                    color: exposureAmt > 0 ? 'var(--danger-text, #ef4444)' : 'var(--success-text, #10b981)',
                  }}
                >
                  {currencySymbol}
                  {exposureAmt.toFixed(2)}
                </span>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>|Main file - Comparison file|</span>
              </div>

              <div>
                <span className="metric-label" style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  Net Difference
                </span>
                <span
                  style={{
                    display: 'block',
                    fontSize: '1.25rem',
                    fontWeight: 700,
                    fontFamily: 'var(--font-mono)',
                    color:
                      varianceAmt > 0
                        ? 'var(--warning-text, #f59e0b)'
                        : varianceAmt < 0
                        ? 'var(--accent, #6366f1)'
                        : 'var(--text-dim)',
                  }}
                >
                  {varianceAmt > 0 ? `+${currencySymbol}` : varianceAmt < 0 ? `-${currencySymbol}` : currencySymbol}
                  {Math.abs(varianceAmt).toFixed(2)}
                </span>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                  {varianceAmt > 0 ? 'Main file exceeds comparison file' : varianceAmt < 0 ? 'Comparison file exceeds main file' : 'Balanced'}
                </span>
              </div>

              <div>
                <span className="metric-label" style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  Main File Amount
                </span>
                <span
                  style={{
                    display: 'block',
                    fontSize: '1.15rem',
                    fontWeight: 600,
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {currencySymbol}
                  {sourceAmt.toFixed(2)}
                </span>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Main File Value</span>
              </div>

              <div>
                <span className="metric-label" style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  Comparison File Amount
                </span>
                <span
                  style={{
                    display: 'block',
                    fontSize: '1.15rem',
                    fontWeight: 600,
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {currencySymbol}
                  {targetAmt.toFixed(2)}
                </span>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Comparison File Value</span>
              </div>
            </div>
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
                gap: 12,
                marginBottom: 24,
                backgroundColor: 'var(--bg-subtle, #161a26)',
                border: '1px solid var(--border-color, #222738)',
                borderRadius: 'var(--radius-sm, 6px)',
                padding: '14px 16px',
              }}
            >
              <div>
                <span className="metric-label" style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  Fields Evaluated
                </span>
                <span style={{ display: 'block', fontSize: '1.25rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                  {unifiedRows.length}
                </span>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Total compared fields</span>
              </div>

              <div>
                <span className="metric-label" style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  Matching Fields
                </span>
                <span style={{ display: 'block', fontSize: '1.25rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--success-text)' }}>
                  {unifiedRows.filter((r) => r.result === 'Match').length}
                </span>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Identical values</span>
              </div>

              <div>
                <span className="metric-label" style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  Differences
                </span>
                <span style={{ display: 'block', fontSize: '1.25rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: unifiedRows.some((r) => r.result === 'Difference') ? 'var(--danger-text)' : 'var(--text-main)' }}>
                  {unifiedRows.filter((r) => r.result === 'Difference').length}
                </span>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Conflicting values</span>
              </div>

              <div>
                <span className="metric-label" style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  Missing / Blank
                </span>
                <span style={{ display: 'block', fontSize: '1.25rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: unifiedRows.some((r) => r.result === 'Missing' || r.result === 'Not checked') ? 'var(--warning-text)' : 'var(--text-main)' }}>
                  {unifiedRows.filter((r) => r.result === 'Missing' || r.result === 'Not checked').length}
                </span>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Blank or not present</span>
              </div>
            </div>
          )}

          {/* Lineage Coordinates Bar */}
          <div style={{ marginBottom: 24 }}>
            <h4 style={{ margin: '0 0 8px 0', fontSize: '0.88rem', display: 'flex', alignItems: 'center', gap: 6 }}>
              <FileSpreadsheet size={15} className="text-accent" /> Row Location in Each Spreadsheet
            </h4>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {record.source_row_indices ? (
                Object.entries(record.source_row_indices).map(([alias, rNum]) => (
                  <div
                    key={alias}
                    style={{
                      padding: '6px 12px',
                      backgroundColor: rNum ? 'var(--bg-subtle, #161a26)' : 'var(--danger-soft, rgba(239, 68, 68, 0.1))',
                      border: `1px solid ${rNum ? 'var(--border-color, #222738)' : 'rgba(239, 68, 68, 0.3)'}`,
                      borderRadius: 'var(--radius-xs, 4px)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      fontSize: '0.82rem',
                    }}
                  >
                    <span style={{ fontWeight: 600 }}>{alias}:</span>
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        color: rNum ? 'var(--accent)' : 'var(--danger-text)',
                      }}
                    >
                      {rNum ? `Row #${rNum}` : 'Missing in file'}
                    </span>
                  </div>
                ))
              ) : (
                <div style={{ display: 'flex', gap: 12 }}>
                  <span className="badge" style={{ fontSize: '0.8rem' }}>
                    <strong>Main file:</strong> Row #{record.source_row_number ?? record.source_row_index ?? '—'}
                  </span>
                  <span className="badge" style={{ fontSize: '0.8rem' }}>
                    <strong>Comparison file:</strong> Row #{record.target_row_number ?? record.target_row_index ?? '—'}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Failed Rules & Explanations */}
          {inspectionData?.failed_rules && inspectionData.failed_rules.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h4 style={{ margin: '0 0 8px 0', fontSize: '0.88rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                <AlertTriangle size={15} className="text-warning" /> Why This Record Flagged a Difference
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {inspectionData.failed_rules.map((rule, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '8px 12px',
                      backgroundColor: 'rgba(245, 158, 11, 0.08)',
                      border: '1px solid rgba(245, 158, 11, 0.25)',
                      borderRadius: 'var(--radius-xs, 4px)',
                      display: 'flex',
                      gap: 8,
                      alignItems: 'flex-start',
                      fontSize: '0.82rem',
                    }}
                  >
                    <span
                      className="badge badge-warning"
                      style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', flexShrink: 0 }}
                    >
                      {rule.rule || 'RULE_FAILED'}
                    </span>
                    <div>
                      {rule.field && (
                        <strong style={{ marginRight: 6, color: 'var(--text-main)' }}>
                          Field [{rule.field}]:
                        </strong>
                      )}
                      <span>{rule.description}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Side-by-Side Raw vs. Normalized Field Comparison */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <h4 style={{ margin: 0, fontSize: '0.88rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                <ArrowRightLeft size={15} className="text-accent" /> Side-by-Side Column Comparison
              </h4>
              <span className="text-xs text-dim">
                {unifiedRows.filter((c) => !c.isMatch).length} differences detected
              </span>
            </div>

            {unifiedRows.length === 0 ? (
              <div
                style={{
                  padding: '24px',
                  textAlign: 'center',
                  backgroundColor: 'var(--bg-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-color)',
                }}
              >
                <CheckCircle size={20} className="text-success" style={{ marginBottom: 6 }} />
                <p style={{ margin: 0, fontSize: '0.85rem' }}>All columns match identically.</p>
              </div>
            ) : (
              <div
                className="table-container"
                style={{
                  border: '1px solid var(--border-color, #222738)',
                  borderRadius: 'var(--radius-sm, 6px)',
                  overflowX: 'auto',
                }}
              >
                <table className="data-table inspector-diff-table" style={{ width: '100%', fontSize: '0.82rem' }}>
                  <thead>
                    <tr>
                      <th style={{ width: '22%' }}>Field Name</th>
                      <th style={{ width: '32%' }}>Main File (Original)</th>
                      <th style={{ width: '32%' }}>Comparison File (Original)</th>
                      <th style={{ width: '14%' }}>Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {unifiedRows.map((row) => {
                      const isDifference = row.result === 'Difference';
                      const isMissing = row.result === 'Missing';
                      const isUnverified = row.result === 'Not checked';
                      const bg = isDifference
                        ? 'rgba(239, 68, 68, 0.08)'
                        : isMissing
                        ? 'rgba(245, 158, 11, 0.06)'
                        : isUnverified
                        ? 'rgba(100, 116, 139, 0.05)'
                        : 'transparent';

                      return (
                        <tr key={row.fieldName} style={{ backgroundColor: bg }}>
                          <td>
                            <strong style={{ fontFamily: 'var(--font-mono)' }}>{row.fieldName}</strong>
                          </td>
                          <td>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                              <span
                                style={{
                                  fontFamily: 'var(--font-mono)',
                                  fontWeight: isDifference ? 600 : 400,
                                  color: row.trustedValue === 'Blank' ? 'var(--text-dim)' : 'var(--text-main)',
                                  fontStyle: row.trustedValue === 'Blank' ? 'italic' : 'normal',
                                }}
                              >
                                {row.trustedValue}
                              </span>
                              <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>{row.trustedFile}</span>
                            </div>
                          </td>
                          <td>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                              <span
                                style={{
                                  fontFamily: 'var(--font-mono)',
                                  fontWeight: isDifference ? 600 : 400,
                                  color: isDifference
                                    ? 'var(--danger-text)'
                                    : row.submittedValue === 'Blank'
                                    ? 'var(--text-dim)'
                                    : 'var(--text-main)',
                                  fontStyle: row.submittedValue === 'Blank' ? 'italic' : 'normal',
                                }}
                              >
                                {row.submittedValue}
                              </span>
                              <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>{row.submittedFile}</span>
                            </div>
                          </td>
                          <td>
                            {row.result === 'Match' && (
                              <span className="badge badge-success" style={{ fontSize: '0.72rem', padding: '2px 8px' }}>
                                Match
                              </span>
                            )}
                            {row.result === 'Difference' && (
                              <span className="badge badge-danger" style={{ fontSize: '0.72rem', padding: '2px 8px' }}>
                                Difference
                              </span>
                            )}
                            {row.result === 'Missing' && (
                              <span className="badge badge-warning" style={{ fontSize: '0.72rem', padding: '2px 8px' }}>
                                Missing
                              </span>
                            )}
                            {row.result === 'Not checked' && (
                              <span className="badge badge-neutral" style={{ fontSize: '0.72rem', padding: '2px 8px' }}>
                                Not checked
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Split Payment Child Installments */}
          {record.child_records && record.child_records.length > 0 && (
            <div style={{ marginTop: 24 }}>
              <h4 style={{ margin: '0 0 8px 0', fontSize: '0.88rem' }}>
                Split Payments ({record.child_records.length} Installments)
              </h4>
              <div
                className="table-container"
                style={{
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <table className="data-table" style={{ width: '100%', fontSize: '0.8rem' }}>
                  <thead>
                    <tr>
                      <th># Row</th>
                      <th>Receipt ID</th>
                      <th>Installment Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {record.child_records.map((c, i) => (
                      <tr key={i}>
                        <td className="cell-muted">Row {c.source_row ?? c.source_row_index ?? i + 1}</td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{c.receipt_id || c.record_id || '—'}</td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                          {currencySymbol}
                          {Number(c.amount || 0).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '16px 24px',
            borderTop: '1px solid var(--border-color, #222738)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
            backgroundColor: 'var(--bg-subtle, #161a26)',
          }}
        >
          <span className="text-xs text-dim" style={{ flex: '1 1 200px', minWidth: 0 }}>
            Press <kbd style={{ padding: '2px 4px', borderRadius: 3, border: '1px solid var(--border-color)' }}>Esc</kbd> to close
          </span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Close Details
          </button>
        </div>
      </div>
    </div>
  );
};
