import React, { useCallback, useEffect, useMemo, useState } from 'react';
import type { ExceptionCluster, VerificationResponse, VerificationResultItem, VerificationRun } from '../types';
import { api } from '../services/api';
import {
  AlertCircle,
  ArrowDownUp,
  CheckCircle2,
  CheckSquare,
  DollarSign,
  Download,
  Eye,
  Filter,
  Inbox,
  Info,
  Layers,
  RotateCcw,
  Search,
  ShieldCheck,
  Square,
  TableProperties,
  UserCheck,
  X,
} from 'lucide-react';
import { StatusBadge } from './StatusBadge';
import { RecordInspectorDrawer } from './RecordInspectorDrawer';
import { BulkReviewModal } from './BulkReviewModal';
import { computeLocalClusters } from '../utils/clustering';

interface VerificationResultsViewProps {
  projectId: string;
  response: VerificationResponse;
  run?: VerificationRun;
}

const PAGE_SIZE = 100;

export const VerificationResultsView: React.FC<VerificationResultsViewProps> = ({
  projectId,
  response,
  run,
}) => {
  // View mode: Record-by-record Grid vs Grouped Exception Clusters
  const [viewMode, setViewMode] = useState<'records' | 'clusters'>('records');

  // Filters
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [minAmountFilter, setMinAmountFilter] = useState<string>('');
  const [maxAmountFilter, setMaxAmountFilter] = useState<string>('');
  const [clusterFilter, setClusterFilter] = useState<string>('all');
  const [assignmentFilter, setAssignmentFilter] = useState<string>('all');
  const [sortOption, setSortOption] = useState<string>('exposure_desc');
  const [searchKey, setSearchKey] = useState<string>('');
  const [visibleCount, setVisibleCount] = useState<number>(PAGE_SIZE);

  // Selections & Modals
  const [selectedRecord, setSelectedRecord] = useState<VerificationResultItem | null>(null);
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set());
  const [bulkModalCluster, setBulkModalCluster] = useState<ExceptionCluster | null>(null);
  const [isBulkModalOpen, setIsBulkModalOpen] = useState<boolean>(false);

  // Clusters state
  const [clusters, setClusters] = useState<ExceptionCluster[]>(() => computeLocalClusters(response.results));
  const [loadingClusters, setLoadingClusters] = useState<boolean>(false);

  // Export state
  const [downloadingFormat, setDownloadingFormat] = useState<'csv' | 'xlsx' | 'json' | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const summary = response.summary;
  const currencySymbol = summary.currency === 'EUR' ? '€' : '$';

  const runId = run?.id;

  // Fetch clusters from API if run exists, else calculate local clusters
  const loadClusters = useCallback(() => {
    if (!runId) return;
    setLoadingClusters(true);
    api.getClusters(projectId, runId)
      .then((res) => {
        setClusters(res.clusters);
      })
      .catch(() => {
        setClusters(computeLocalClusters(response.results));
      })
      .finally(() => {
        setLoadingClusters(false);
      });
  }, [projectId, runId, response.results]);

  useEffect(() => {
    if (runId) {
      const timer = setTimeout(() => {
        loadClusters();
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [runId, loadClusters]);

  const handleDownload = async (format: 'csv' | 'xlsx' | 'json') => {
    if (!run) return;
    setExportError(null);
    setDownloadingFormat(format);
    try {
      await api.downloadExport(
        projectId,
        run.id,
        format,
        categoryFilter !== 'all' ? categoryFilter : undefined,
        statusFilter !== 'all' ? statusFilter : undefined
      );
    } catch (err: any) {
      setExportError(`Export failed: ${err.message}`);
    } finally {
      setDownloadingFormat(null);
    }
  };

  // Filtered and sorted record list
  const filteredResults = useMemo(() => {
    const minAmt = minAmountFilter.trim() !== '' ? parseFloat(minAmountFilter) : null;
    const maxAmt = maxAmountFilter.trim() !== '' ? parseFloat(maxAmountFilter) : null;

    const filtered = response.results.filter((item) => {
      if (categoryFilter !== 'all' && item.discrepancy_category !== categoryFilter) {
        return false;
      }
      if (statusFilter !== 'all' && item.match_status !== statusFilter) {
        return false;
      }
      if (clusterFilter !== 'all' && item.cluster_id !== clusterFilter) {
        return false;
      }
      if (assignmentFilter === 'ASSIGNED_TO_ME') {
        if (!item.assigned_to) return false;
      } else if (assignmentFilter === 'UNASSIGNED') {
        if (item.assigned_to) return false;
      }
      if (searchKey.trim()) {
        const keyString = JSON.stringify(item.key_values).toLowerCase();
        if (!keyString.includes(searchKey.toLowerCase())) {
          return false;
        }
      }
      if (minAmt !== null && !isNaN(minAmt)) {
        const exp = item.exposure_amount ?? 0;
        if (exp < minAmt) return false;
      }
      if (maxAmt !== null && !isNaN(maxAmt)) {
        const exp = item.exposure_amount ?? 0;
        if (exp > maxAmt) return false;
      }
      return true;
    });

    // Sorting
    return filtered.sort((a, b) => {
      const expA = a.exposure_amount ?? 0;
      const expB = b.exposure_amount ?? 0;
      const varA = a.variance_amount ?? 0;
      const varB = b.variance_amount ?? 0;

      if (sortOption === 'exposure_desc') return expB - expA;
      if (sortOption === 'exposure_asc') return expA - expB;
      if (sortOption === 'variance_desc') return varB - varA;
      if (sortOption === 'variance_asc') return varA - varB;
      if (sortOption === 'row_asc') return (a.source_row_number ?? 0) - (b.source_row_number ?? 0);
      return 0;
    });
  }, [
    response.results,
    categoryFilter,
    statusFilter,
    clusterFilter,
    assignmentFilter,
    searchKey,
    minAmountFilter,
    maxAmountFilter,
    sortOption,
  ]);

  const visibleResults = filteredResults.slice(0, visibleCount);
  const hasActiveFilters =
    categoryFilter !== 'all' ||
    statusFilter !== 'all' ||
    clusterFilter !== 'all' ||
    assignmentFilter !== 'all' ||
    searchKey.trim().length > 0 ||
    minAmountFilter.trim() !== '' ||
    maxAmountFilter.trim() !== '' ||
    sortOption !== 'exposure_desc';

  const clearFilters = () => {
    setCategoryFilter('all');
    setStatusFilter('all');
    setClusterFilter('all');
    setAssignmentFilter('all');
    setMinAmountFilter('');
    setMaxAmountFilter('');
    setSearchKey('');
    setSortOption('exposure_desc');
  };

  const isZeroExceptions =
    summary.total_discrepancies === 0 ||
    ((summary.gross_exposure ?? 0) === 0 && summary.field_mismatches === 0 && summary.unmatched_source_records === 0);

  // Row selection handlers
  const handleToggleRow = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedRowIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleToggleAllVisible = () => {
    if (selectedRowIds.size === visibleResults.length && visibleResults.length > 0) {
      setSelectedRowIds(new Set());
    } else {
      setSelectedRowIds(new Set(visibleResults.map((r) => r.id)));
    }
  };

  const selectedRowsExposure = useMemo(() => {
    let sum = 0;
    response.results.forEach((r) => {
      if (selectedRowIds.has(r.id)) {
        sum += r.exposure_amount ?? 0;
      }
    });
    return Math.round(sum * 100) / 100;
  }, [response.results, selectedRowIds]);

  const openBulkModalForSelected = () => {
    setBulkModalCluster(null);
    setIsBulkModalOpen(true);
  };

  const openBulkModalForCluster = (cl: ExceptionCluster) => {
    setBulkModalCluster(cl);
    setIsBulkModalOpen(true);
  };

  const handleClusterViewRecords = (clusterId: string) => {
    setClusterFilter(clusterId);
    setViewMode('records');
  };

  return (
    <div>
      {/* Financial Materiality Header */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header" style={{ marginBottom: 18 }}>
          <div>
            <h2 className="card-title">
              <CheckCircle2 size={20} /> Financial Materiality &amp; Reconciliation Summary
            </h2>
            <p className="card-description">
              {summary.total_source_records.toLocaleString()} source records compared against{' '}
              {summary.total_target_records.toLocaleString()} target records
              {run ? ` — run saved to audit history.` : '.'}
            </p>
          </div>
          <div className="row-wrap">
            <StatusBadge status={summary.status} />
            {run && (
              <div className="row-wrap">
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleDownload('csv')}
                  disabled={downloadingFormat !== null}
                >
                  {downloadingFormat === 'csv' ? <span className="spinner" /> : <Download size={14} />}
                  CSV
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleDownload('xlsx')}
                  disabled={downloadingFormat !== null}
                >
                  {downloadingFormat === 'xlsx' ? <span className="spinner" /> : <Download size={14} />}
                  Excel
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleDownload('json')}
                  disabled={downloadingFormat !== null}
                >
                  {downloadingFormat === 'json' ? <span className="spinner" /> : <Download size={14} />}
                  JSON
                </button>
              </div>
            )}
          </div>
        </div>

        {/* 4 Financial KPI Cards */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
            gap: 14,
            marginBottom: 20,
          }}
        >
          {/* 1. Gross Exception Exposure */}
          <div
            className="stat-card"
            style={{
              padding: '16px 18px',
              backgroundColor: 'var(--bg-card-hover)',
              borderRadius: 'var(--radius-md)',
              border: (summary.gross_exposure ?? 0) > 0 ? '1px solid var(--danger-border, #f87171)' : '1px solid var(--border-color)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-dim)' }}>
                Gross Exposure
              </span>
              <DollarSign size={16} className={(summary.gross_exposure ?? 0) > 0 ? 'text-danger' : 'text-dim'} />
            </div>
            <div
              style={{
                fontSize: '1.45rem',
                fontWeight: 700,
                fontFamily: 'var(--font-mono)',
                color: (summary.gross_exposure ?? 0) > 0 ? 'var(--danger-text, #ef4444)' : 'var(--text-main)',
              }}
            >
              {currencySymbol}
              {(summary.gross_exposure ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: 4, display: 'block' }}>
              Absolute monetary variance (|src - tgt|)
            </span>
          </div>

          {/* 2. Net Variance */}
          <div
            className="stat-card"
            style={{
              padding: '16px 18px',
              backgroundColor: 'var(--bg-card-hover)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-dim)' }}>
                Net Variance
              </span>
              <Info size={16} className="text-dim" />
            </div>
            <div
              style={{
                fontSize: '1.45rem',
                fontWeight: 700,
                fontFamily: 'var(--font-mono)',
                color:
                  (summary.net_variance ?? 0) > 0
                    ? 'var(--warning-text, #f59e0b)'
                    : (summary.net_variance ?? 0) < 0
                    ? 'var(--danger-text, #ef4444)'
                    : 'var(--text-main)',
              }}
            >
              {(summary.net_variance ?? 0) >= 0 ? '+' : ''}
              {currencySymbol}
              {(summary.net_variance ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: 4, display: 'block' }}>
              Directional balance (Source - Target)
            </span>
          </div>

          {/* 3. Reconciled / Verified Total */}
          <div
            className="stat-card"
            style={{
              padding: '16px 18px',
              backgroundColor: 'var(--bg-card-hover)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-dim)' }}>
                Reconciled Value
              </span>
              <ShieldCheck size={16} className="text-success" />
            </div>
            <div
              style={{
                fontSize: '1.45rem',
                fontWeight: 700,
                fontFamily: 'var(--font-mono)',
                color: 'var(--success-text, #10b981)',
              }}
            >
              {currencySymbol}
              {(summary.verified_amount ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: 4, display: 'block' }}>
              Verified clean match totals
            </span>
          </div>

          {/* 4. Outstanding Discrepancy Amount */}
          <div
            className="stat-card"
            style={{
              padding: '16px 18px',
              backgroundColor: 'var(--bg-card-hover)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-dim)' }}>
                Outstanding Variance
              </span>
              <AlertCircle size={16} className={(summary.outstanding_amount ?? 0) > 0 ? 'text-warning' : 'text-dim'} />
            </div>
            <div
              style={{
                fontSize: '1.45rem',
                fontWeight: 700,
                fontFamily: 'var(--font-mono)',
                color: (summary.outstanding_amount ?? 0) > 0 ? 'var(--warning-text, #f59e0b)' : 'var(--text-main)',
              }}
            >
              {currencySymbol}
              {(summary.outstanding_amount ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: 4, display: 'block' }}>
              Unreconciled / disputed values
            </span>
          </div>
        </div>

        {/* Resilient Alert: Zero Exceptions Clean State */}
        {isZeroExceptions && (
          <div
            className="alert alert-success"
            style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}
          >
            <CheckCircle2 size={20} className="text-success" style={{ flexShrink: 0 }} />
            <div>
              <strong style={{ fontSize: '0.95rem' }}>100% Financial Reconciliation Verified</strong>
              <p style={{ margin: '2px 0 0', fontSize: '0.82rem', color: 'var(--text-dim)' }}>
                Zero monetary exposure and zero record exceptions detected. All matched line items have identical values and balanced amounts.
              </p>
            </div>
          </div>
        )}

        {exportError && (
          <div className="alert alert-danger" style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <AlertCircle size={16} />
            <span>{exportError}</span>
          </div>
        )}
      </div>

      {/* Main Results Container */}
      <div className="card">
        {/* View Mode Toggle & Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 12,
            marginBottom: 16,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ display: 'flex', backgroundColor: 'var(--bg-card-hover)', borderRadius: 'var(--radius-sm)', padding: 3 }}>
              <button
                type="button"
                className="btn btn-sm"
                style={{
                  backgroundColor: viewMode === 'records' ? 'var(--bg-card)' : 'transparent',
                  color: viewMode === 'records' ? 'var(--text-main)' : 'var(--text-dim)',
                  boxShadow: viewMode === 'records' ? '0 1px 3px rgba(0,0,0,0.2)' : 'none',
                  fontWeight: viewMode === 'records' ? 600 : 400,
                }}
                onClick={() => setViewMode('records')}
              >
                <TableProperties size={14} /> Record Grid ({filteredResults.length})
              </button>
              <button
                type="button"
                className="btn btn-sm"
                style={{
                  backgroundColor: viewMode === 'clusters' ? 'var(--bg-card)' : 'transparent',
                  color: viewMode === 'clusters' ? 'var(--text-main)' : 'var(--text-dim)',
                  boxShadow: viewMode === 'clusters' ? '0 1px 3px rgba(0,0,0,0.2)' : 'none',
                  fontWeight: viewMode === 'clusters' ? 600 : 400,
                }}
                onClick={() => setViewMode('clusters')}
              >
                <Layers size={14} /> Exception Clusters ({clusters.length})
              </button>
            </div>

            {selectedRowIds.size > 0 && viewMode === 'records' && (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={openBulkModalForSelected}
              >
                <CheckSquare size={14} /> Bulk Review Selected ({selectedRowIds.size}) &mdash; {currencySymbol}{selectedRowsExposure.toLocaleString()}
              </button>
            )}
          </div>

          <span className="card-description" style={{ fontSize: '0.82rem' }}>
            {viewMode === 'records'
              ? `${filteredResults.length.toLocaleString()} matching records`
              : `${clusters.length} root-cause exception clusters`}
          </span>
        </div>

        {/* CLUSTER VIEW */}
        {viewMode === 'clusters' ? (
          <div>
            {loadingClusters ? (
              <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-dim)' }}>
                <span className="spinner" /> Loading exception clusters...
              </div>
            ) : clusters.length === 0 ? (
              <div className="empty-state" style={{ padding: '48px 20px' }}>
                <CheckCircle2 size={32} className="text-success" />
                <h3 className="empty-title">Zero Exception Clusters</h3>
                <p className="empty-text">No recurring exception signatures or discrepancies detected in this dataset.</p>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
                {clusters.map((cl) => {
                  const isHigh = cl.total_exposure >= 1000;
                  const isBlock = cl.severity.toUpperCase() === 'BLOCKING';
                  return (
                    <div
                      key={cl.cluster_id}
                      className="card"
                      style={{
                        backgroundColor: 'var(--bg-card-hover)',
                        border: isBlock
                          ? '1px solid var(--danger-border, #f87171)'
                          : isHigh
                          ? '1px solid var(--warning-border, #f59e0b)'
                          : '1px solid var(--border-color)',
                        padding: 18,
                        borderRadius: 'var(--radius-md)',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        {/* Cluster Header */}
                        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
                          <span
                            className={`badge ${isBlock ? 'badge-danger' : isHigh ? 'badge-warning' : 'badge-neutral'}`}
                            style={{ fontSize: '0.7rem' }}
                          >
                            {cl.severity.toUpperCase()}
                          </span>
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                            {cl.cluster_id}
                          </span>
                        </div>

                        <h4 style={{ margin: '0 0 6px', fontSize: '0.98rem', fontWeight: 600 }}>
                          {cl.cluster_name}
                        </h4>

                        <p style={{ margin: '0 0 12px', fontSize: '0.8rem', color: 'var(--text-dim)', lineHeight: 1.4 }}>
                          {cl.root_cause_explanation}
                        </p>

                        {/* Metric Row */}
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: '1fr 1fr',
                            gap: 10,
                            padding: '10px 12px',
                            backgroundColor: 'var(--bg-card)',
                            borderRadius: 'var(--radius-sm)',
                            marginBottom: 12,
                          }}
                        >
                          <div>
                            <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>Records</span>
                            <div style={{ fontSize: '1.1rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                              {cl.total_records.toLocaleString()}
                            </div>
                          </div>
                          <div>
                            <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>Exposure</span>
                            <div
                              style={{
                                fontSize: '1.1rem',
                                fontWeight: 700,
                                fontFamily: 'var(--font-mono)',
                                color: cl.total_exposure > 0 ? 'var(--warning-text)' : 'var(--text-main)',
                              }}
                            >
                              {currencySymbol}{cl.total_exposure.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </div>
                          </div>
                        </div>

                        {/* Assignee & Status Pills */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.76rem', color: 'var(--text-dim)' }}>
                            <UserCheck size={14} />
                            <span>{cl.assigned_to ? cl.assigned_to : 'Unassigned'}</span>
                          </div>
                          <div style={{ display: 'flex', gap: 4 }}>
                            {Object.entries(cl.status_counts).map(([st, c]) => (
                              <span
                                key={st}
                                className="badge"
                                style={{
                                  fontSize: '0.7rem',
                                  backgroundColor: st === 'APPROVED' ? 'var(--success-soft)' : 'var(--bg-card)',
                                  color: st === 'APPROVED' ? 'var(--success-text)' : 'var(--text-dim)',
                                }}
                              >
                                {st}: {c}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* Cluster Actions */}
                      <div style={{ display: 'flex', gap: 8, borderTop: '1px solid var(--border-color)', paddingTop: 12 }}>
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          style={{ flex: 1 }}
                          onClick={() => openBulkModalForCluster(cl)}
                        >
                          <CheckCircle2 size={13} /> Bulk Review
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleClusterViewRecords(cl.cluster_id)}
                          title="Filter Grid to this Cluster"
                        >
                          <Eye size={13} /> View ({cl.total_records})
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          /* RECORD GRID VIEW */
          <div>
            {/* Toolbar: Search, Filters, Range, and Sorting */}
            <div className="toolbar" style={{ flexWrap: 'wrap', gap: 10 }}>
              <div className="search-box" style={{ minWidth: 180 }}>
                <Search size={15} />
                <input
                  type="text"
                  className="form-input"
                  placeholder="Search by key values…"
                  value={searchKey}
                  onChange={(e) => {
                    setSearchKey(e.target.value);
                    setVisibleCount(PAGE_SIZE);
                  }}
                  aria-label="Search by key values"
                />
              </div>

              {/* Amount Range Filter */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: '0.78rem', color: 'var(--text-dim)' }}>Min {currencySymbol}:</span>
                <input
                  type="number"
                  min="0"
                  step="10"
                  className="form-input"
                  style={{ width: 85, padding: '4px 8px' }}
                  placeholder="Min"
                  value={minAmountFilter}
                  onChange={(e) => {
                    setMinAmountFilter(e.target.value);
                    setVisibleCount(PAGE_SIZE);
                  }}
                  aria-label="Filter by minimum amount"
                />
                <span style={{ fontSize: '0.78rem', color: 'var(--text-dim)' }}>Max:</span>
                <input
                  type="number"
                  min="0"
                  step="10"
                  className="form-input"
                  style={{ width: 85, padding: '4px 8px' }}
                  placeholder="Max"
                  value={maxAmountFilter}
                  onChange={(e) => {
                    setMaxAmountFilter(e.target.value);
                    setVisibleCount(PAGE_SIZE);
                  }}
                  aria-label="Filter by maximum amount"
                />
              </div>

              {/* Cluster Filter */}
              {clusters.length > 0 && (
                <select
                  className="form-select filter-select"
                  value={clusterFilter}
                  onChange={(e) => {
                    setClusterFilter(e.target.value);
                    setVisibleCount(PAGE_SIZE);
                  }}
                  aria-label="Filter by cluster"
                  style={{ maxWidth: 190 }}
                >
                  <option value="all">All Exception Clusters</option>
                  {clusters.map((c) => (
                    <option key={c.cluster_id} value={c.cluster_id}>
                      {c.cluster_name} ({c.total_records})
                    </option>
                  ))}
                </select>
              )}

              {/* Assignment Filter */}
              <select
                className="form-select filter-select"
                value={assignmentFilter}
                onChange={(e) => {
                  setAssignmentFilter(e.target.value);
                  setVisibleCount(PAGE_SIZE);
                }}
                aria-label="Filter by assignment"
              >
                <option value="all">All Assignees</option>
                <option value="ASSIGNED_TO_ME">Assigned to Me</option>
                <option value="UNASSIGNED">Unassigned</option>
              </select>

              {/* Select Filters */}
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <Filter size={15} className="text-dim" />
                <select
                  className="form-select filter-select"
                  value={categoryFilter}
                  onChange={(e) => {
                    setCategoryFilter(e.target.value);
                    setVisibleCount(PAGE_SIZE);
                  }}
                  aria-label="Filter by category"
                >
                  <option value="all">All categories</option>
                  <option value="none">Identical matches</option>
                  <option value="field_mismatch">Field mismatches</option>
                  <option value="missing_record">Missing records</option>
                  <option value="duplicate_key">Duplicate keys</option>
                  <option value="aggregation_mismatch">Aggregation mismatches</option>
                  <option value="rule_violation">Rule violations</option>
                </select>

                <select
                  className="form-select filter-select"
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    setVisibleCount(PAGE_SIZE);
                  }}
                  aria-label="Filter by match status"
                >
                  <option value="all">All match statuses</option>
                  <option value="identical">Identical</option>
                  <option value="field_mismatch">Field mismatch</option>
                  <option value="missing_in_target">Missing in target</option>
                  <option value="missing_in_source">Missing in source</option>
                  <option value="duplicate_key_source">Duplicate in source</option>
                  <option value="duplicate_key_target">Duplicate in target</option>
                  <option value="duplicate_key_both">Duplicate in both</option>
                  <option value="needs_review">Needs review</option>
                </select>

                <select
                  className="form-select filter-select"
                  value={sortOption}
                  onChange={(e) => setSortOption(e.target.value)}
                  aria-label="Sort by financial exposure"
                >
                  <option value="exposure_desc">Exposure: High → Low</option>
                  <option value="exposure_asc">Exposure: Low → High</option>
                  <option value="variance_desc">Net Variance: High → Low</option>
                  <option value="variance_asc">Net Variance: Low → High</option>
                  <option value="row_asc">Source Row: Low → High</option>
                </select>

                {hasActiveFilters && (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={clearFilters}>
                    <X size={14} /> Clear filters
                  </button>
                )}
              </div>
            </div>

            {/* Data Table */}
            <div className="table-container">
              <table className="data-table" style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th style={{ width: 36, textAlign: 'center' }}>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        style={{ padding: 2 }}
                        onClick={handleToggleAllVisible}
                        aria-label="Select all"
                      >
                        {selectedRowIds.size === visibleResults.length && visibleResults.length > 0 ? (
                          <CheckSquare size={16} className="text-accent" />
                        ) : (
                          <Square size={16} className="text-dim" />
                        )}
                      </button>
                    </th>
                    <th style={{ width: '17%' }}>Key Columns</th>
                    <th style={{ width: '12%' }}>Match Status</th>
                    <th style={{ width: '12%' }}>Resolution</th>
                    <th style={{ width: '13%' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span>Exposure</span>
                        <ArrowDownUp size={12} className="text-dim" />
                      </div>
                    </th>
                    <th style={{ width: '12%' }}>Assignee</th>
                    <th style={{ width: '10%' }}>Source / Target</th>
                    <th>Differences / Message</th>
                    <th style={{ width: 60, textAlign: 'center' }}>Inspect</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleResults.length === 0 ? (
                    <tr>
                      <td colSpan={9} style={{ padding: 0, border: 'none' }}>
                        <div className="empty-state" style={{ padding: '48px 20px' }}>
                          <div className="empty-icon">
                            {hasActiveFilters ? <Search size={24} /> : <Inbox size={24} />}
                          </div>
                          <h3 className="empty-title">
                            {hasActiveFilters ? 'No records match your filters' : 'No records'}
                          </h3>
                          <p className="empty-text" style={{ marginBottom: hasActiveFilters ? 14 : 0 }}>
                            {hasActiveFilters
                              ? 'Try broadening your category, status, monetary range, or search criteria.'
                              : 'This reconciliation returned no individual records.'}
                          </p>
                          {hasActiveFilters && (
                            <button type="button" className="btn btn-secondary btn-sm" onClick={clearFilters}>
                              <RotateCcw size={14} /> Reset all filters
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ) : (
                    visibleResults.map((row) => {
                      const exposure = row.exposure_amount ?? 0;
                      const isHighExposure = exposure >= 1000;
                      const isSelected = selectedRowIds.has(row.id);
                      const resStatus = (row.resolution_status || 'unresolved').toUpperCase();

                      return (
                        <tr
                          key={row.id}
                          style={{
                            cursor: 'pointer',
                            backgroundColor: isSelected ? 'var(--bg-card-hover)' : undefined,
                          }}
                          onClick={() => setSelectedRecord(row)}
                          className="hover-row"
                        >
                          <td style={{ textAlign: 'center' }} onClick={(e) => handleToggleRow(row.id, e)}>
                            {isSelected ? (
                              <CheckSquare size={16} className="text-accent" />
                            ) : (
                              <Square size={16} className="text-dim" />
                            )}
                          </td>
                          <td>
                            <code className="key-code">{JSON.stringify(row.key_values)}</code>
                          </td>
                          <td>
                            <StatusBadge status={row.match_status} />
                          </td>
                          <td>
                            <span
                              className="badge"
                              style={{
                                fontSize: '0.72rem',
                                backgroundColor:
                                  resStatus === 'APPROVED' || resStatus === 'RESOLVED'
                                    ? 'var(--success-soft)'
                                    : resStatus === 'REJECTED'
                                    ? 'var(--danger-soft)'
                                    : resStatus === 'ESCALATED'
                                    ? 'var(--warning-soft)'
                                    : 'var(--bg-card)',
                                color:
                                  resStatus === 'APPROVED' || resStatus === 'RESOLVED'
                                    ? 'var(--success-text)'
                                    : resStatus === 'REJECTED'
                                    ? 'var(--danger-text)'
                                    : resStatus === 'ESCALATED'
                                    ? 'var(--warning-text)'
                                    : 'var(--text-dim)',
                              }}
                            >
                              {resStatus}
                            </span>
                          </td>
                          <td>
                            <span
                              style={{
                                fontFamily: 'var(--font-mono)',
                                fontWeight: exposure > 0 ? 600 : 400,
                                color: isHighExposure
                                  ? 'var(--danger-text)'
                                  : exposure > 0
                                  ? 'var(--warning-text)'
                                  : 'var(--text-dim)',
                              }}
                            >
                              {currencySymbol}
                              {exposure.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </span>
                          </td>
                          <td>
                            <span style={{ fontSize: '0.78rem', color: row.assigned_to ? 'var(--text-main)' : 'var(--text-dim)' }}>
                              {row.assigned_to || '—'}
                            </span>
                          </td>
                          <td style={{ fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }}>
                            S: {row.source_row_number ?? row.source_row_index ?? '—'} | T: {row.target_row_number ?? row.target_row_index ?? '—'}
                          </td>
                          <td>
                            {row.field_differences && row.field_differences.length > 0 ? (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                {row.field_differences.slice(0, 2).map((diff, i) => (
                                  <div key={i} style={{ fontSize: '0.75rem' }}>
                                    <strong className="text-accent">{diff.field_name}:</strong>{' '}
                                    <span>{String(diff.source_value)}</span> ≠{' '}
                                    <span style={{ color: 'var(--warning-text)' }}>{String(diff.target_value)}</span>
                                  </div>
                                ))}
                                {row.field_differences.length > 2 && (
                                  <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                                    +{row.field_differences.length - 2} more differences
                                  </span>
                                )}
                              </div>
                            ) : (
                              <span className="text-dim" style={{ fontSize: '0.8rem' }}>
                                {row.message || 'Identical record match'}
                              </span>
                            )}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              style={{ padding: '3px 6px' }}
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedRecord(row);
                              }}
                              title="Inspect record side-by-side"
                            >
                              <Eye size={14} />
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {filteredResults.length > visibleCount && (
              <div className="table-footer-note">
                <span>
                  Showing first {visibleCount.toLocaleString()} of{' '}
                  {filteredResults.length.toLocaleString()} matching records.
                </span>
                <div className="row" style={{ gap: 8 }}>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
                  >
                    Show {PAGE_SIZE} more
                  </button>
                  {run && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => handleDownload('csv')}
                      disabled={downloadingFormat !== null}
                    >
                      <Download size={14} /> Download full report
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Slide-Out Record Inspector Drawer */}
      <RecordInspectorDrawer
        isOpen={Boolean(selectedRecord)}
        onClose={() => setSelectedRecord(null)}
        record={selectedRecord}
        projectId={projectId}
        runId={run?.id}
      />

      {/* Bulk Review & Assignment Modal */}
      {isBulkModalOpen && run && (
        <BulkReviewModal
          isOpen={isBulkModalOpen}
          onClose={() => setIsBulkModalOpen(false)}
          onSuccess={() => {
            void loadClusters();
            setSelectedRowIds(new Set());
          }}
          projectId={projectId}
          runId={run.id}
          cluster={bulkModalCluster}
          selectedRecordIds={Array.from(selectedRowIds)}
          selectedExposure={selectedRowsExposure}
          totalSelectedCount={selectedRowIds.size}
        />
      )}
    </div>
  );
};
