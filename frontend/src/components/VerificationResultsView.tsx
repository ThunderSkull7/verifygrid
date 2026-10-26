import React, { useMemo, useState } from 'react';
import type { VerificationResponse, VerificationResultItem, VerificationRun } from '../types';
import { api } from '../services/api';
import {
  AlertCircle,
  ArrowDownUp,
  CheckCircle2,
  Download,
  Eye,
  Filter,
  Inbox,
  Info,
  RotateCcw,
  Search,
  ShieldCheck,
  TableProperties,
  X,
} from 'lucide-react';
import { StatusBadge } from './StatusBadge';
import { RecordInspectorDrawer } from './RecordInspectorDrawer';

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
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [minAmountFilter, setMinAmountFilter] = useState<string>('');
  const [maxAmountFilter, setMaxAmountFilter] = useState<string>('');
  const [sortOption, setSortOption] = useState<string>('exposure_desc');
  const [downloadingFormat, setDownloadingFormat] = useState<'csv' | 'xlsx' | 'json' | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [searchKey, setSearchKey] = useState<string>('');
  const [visibleCount, setVisibleCount] = useState<number>(PAGE_SIZE);
  const [selectedRecord, setSelectedRecord] = useState<VerificationResultItem | null>(null);

  const summary = response.summary;
  const currencySymbol = summary.currency === 'EUR' ? '€' : '$';

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

      if (sortOption === 'exposure_desc') {
        return expB - expA;
      }
      if (sortOption === 'exposure_asc') {
        return expA - expB;
      }
      if (sortOption === 'variance_desc') {
        return varB - varA;
      }
      if (sortOption === 'variance_asc') {
        return varA - varB;
      }
      if (sortOption === 'row_asc') {
        return (a.source_row_number ?? 0) - (b.source_row_number ?? 0);
      }
      return 0;
    });
  }, [
    response.results,
    categoryFilter,
    statusFilter,
    searchKey,
    minAmountFilter,
    maxAmountFilter,
    sortOption,
  ]);

  const visibleResults = filteredResults.slice(0, visibleCount);
  const hasActiveFilters =
    categoryFilter !== 'all' ||
    statusFilter !== 'all' ||
    searchKey.trim().length > 0 ||
    minAmountFilter.trim() !== '' ||
    maxAmountFilter.trim() !== '' ||
    sortOption !== 'exposure_desc';

  const clearFilters = () => {
    setCategoryFilter('all');
    setStatusFilter('all');
    setMinAmountFilter('');
    setMaxAmountFilter('');
    setSearchKey('');
    setSortOption('exposure_desc');
  };

  const isZeroExceptions =
    summary.total_discrepancies === 0 ||
    ((summary.gross_exposure ?? 0) === 0 && summary.field_mismatches === 0 && summary.unmatched_source_records === 0);

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

        {!run && (
          <div className="alert alert-info" style={{ marginBottom: 18 }}>
            <Info size={16} />
            <span>
              This was an ad-hoc comparison. Enable “Save persistent audit run” before executing to
              unlock exports and audit history.
            </span>
          </div>
        )}

        {exportError && (
          <div className="alert alert-error" role="alert" style={{ marginBottom: 16 }}>
            <AlertCircle size={16} />
            <span>{exportError}</span>
          </div>
        )}

        {/* 4 Core Financial Materiality KPI Cards */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 16,
            marginBottom: 20,
          }}
        >
          {/* Gross Exception Exposure */}
          <div
            className="metric-card flat"
            style={{
              borderLeft: '4px solid var(--danger-color, #ef4444)',
              backgroundColor: 'rgba(239, 68, 68, 0.05)',
            }}
          >
            <span className="metric-label">Gross Exception Exposure</span>
            <span
              className="metric-value text-danger"
              style={{ fontSize: '1.6rem', fontFamily: 'var(--font-mono)' }}
            >
              {currencySymbol}
              {(summary.gross_exposure ?? 0).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </span>
            <span className="metric-foot">
              Absolute sum of all variances across {summary.total_discrepancies} exceptions
            </span>
          </div>

          {/* Net Directional Variance */}
          <div
            className="metric-card flat"
            style={{
              borderLeft: '4px solid var(--accent, #6366f1)',
              backgroundColor: 'rgba(99, 102, 241, 0.05)',
            }}
          >
            <span className="metric-label">Net Variance</span>
            <span
              className="metric-value"
              style={{
                fontSize: '1.6rem',
                fontFamily: 'var(--font-mono)',
                color: (summary.net_variance ?? 0) === 0 ? 'var(--text-dim)' : 'var(--accent)',
              }}
            >
              {(summary.net_variance ?? 0) > 0 ? `+${currencySymbol}` : (summary.net_variance ?? 0) < 0 ? `-${currencySymbol}` : currencySymbol}
              {Math.abs(summary.net_variance ?? 0).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </span>
            <span className="metric-foot">
              {(summary.net_variance ?? 0) > 0
                ? 'Source exceeds target overall'
                : (summary.net_variance ?? 0) < 0
                ? 'Target exceeds source overall'
                : 'Balanced net directional variance'}
            </span>
          </div>

          {/* Verified Amount */}
          <div
            className="metric-card flat"
            style={{
              borderLeft: '4px solid var(--success-color, #10b981)',
              backgroundColor: 'rgba(16, 185, 129, 0.05)',
            }}
          >
            <span className="metric-label">Verified Total</span>
            <span
              className="metric-value text-success"
              style={{ fontSize: '1.6rem', fontFamily: 'var(--font-mono)' }}
            >
              {currencySymbol}
              {(summary.verified_amount ?? 0).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </span>
            <span className="metric-foot">
              {summary.identical_matches.toLocaleString()} records reconciled with zero variance
            </span>
          </div>

          {/* Outstanding Variance */}
          <div
            className="metric-card flat"
            style={{
              borderLeft: '4px solid var(--warning-color, #f59e0b)',
              backgroundColor: 'rgba(245, 158, 11, 0.05)',
            }}
          >
            <span className="metric-label">Outstanding Variance</span>
            <span
              className="metric-value text-warning"
              style={{ fontSize: '1.6rem', fontFamily: 'var(--font-mono)' }}
            >
              {currencySymbol}
              {(summary.outstanding_amount ?? summary.gross_exposure ?? 0).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </span>
            <span className="metric-foot">
              Total value currently disputed or unreconciled
            </span>
          </div>
        </div>

        {/* Operational Volume Metrics Grid */}
        <div className="metric-grid">
          <div className="metric-card flat">
            <span className="metric-label">Identical Matches</span>
            <span className="metric-value text-success">
              {summary.identical_matches.toLocaleString()}
            </span>
            <span className="metric-foot">
              {summary.matched_records.toLocaleString()} records paired
            </span>
          </div>

          <div className="metric-card flat">
            <span className="metric-label">Field Mismatches</span>
            <span className="metric-value text-danger">
              {summary.field_mismatches.toLocaleString()}
            </span>
            <span className="metric-foot">
              {(summary.records_with_differences ?? summary.field_mismatches).toLocaleString()} with diffs
            </span>
          </div>

          <div className="metric-card flat">
            <span className="metric-label">Missing in Target</span>
            <span className="metric-value text-warning">
              {summary.unmatched_source_records.toLocaleString()}
            </span>
            <span className="metric-foot">Present only in source</span>
          </div>

          <div className="metric-card flat">
            <span className="metric-label">Missing in Source</span>
            <span className="metric-value text-warning">
              {summary.unmatched_target_records.toLocaleString()}
            </span>
            <span className="metric-foot">Present only in target</span>
          </div>

          <div className="metric-card flat">
            <span className="metric-label">Duplicate Keys</span>
            <span className="metric-value text-violet">
              {(summary.duplicate_source_keys_count + summary.duplicate_target_keys_count).toLocaleString()}
            </span>
            <span className="metric-foot">
              {summary.duplicate_source_records} source · {summary.duplicate_target_records} target rows
            </span>
          </div>

          <div className="metric-card flat">
            <span className="metric-label">Total Discrepancies</span>
            <span className="metric-value">{summary.total_discrepancies.toLocaleString()}</span>
            <span className="metric-foot">Exceptions flagged</span>
          </div>
        </div>
      </div>

      {/* Zero Exceptions State Banner */}
      {isZeroExceptions && !hasActiveFilters && (
        <div
          className="card"
          style={{
            marginBottom: 20,
            padding: '24px',
            backgroundColor: 'rgba(16, 185, 129, 0.08)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            display: 'flex',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <div
            style={{
              padding: 12,
              borderRadius: '50%',
              backgroundColor: 'rgba(16, 185, 129, 0.15)',
              color: 'var(--success-color, #10b981)',
            }}
          >
            <ShieldCheck size={32} />
          </div>
          <div>
            <h3 style={{ margin: '0 0 4px 0', fontSize: '1.1rem', color: 'var(--success-text)' }}>
              100% Reconciled — Zero Financial Discrepancies
            </h3>
            <p style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-dim)' }}>
              All submitted data records match their target counterparts with complete field-level precision and zero outstanding monetary exposure.
            </p>
          </div>
        </div>
      )}

      {/* Records Grid */}
      <div className="card">
        <div className="section-head">
          <h3 className="section-title">
            <TableProperties size={17} /> Results Grid &amp; Exception Inspector
          </h3>
          <span className="text-xs text-dim">
            Showing {Math.min(visibleCount, filteredResults.length).toLocaleString()} of{' '}
            {filteredResults.length.toLocaleString()} matching records
          </span>
        </div>

        {/* Toolbar: Search, Filters, Range, and Sorting */}
        <div className="toolbar" style={{ flexWrap: 'wrap', gap: 10 }}>
          <div className="search-box" style={{ minWidth: 200 }}>
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
              <option value="partial_payment">Partial payment</option>
              <option value="overpayment">Overpayment</option>
            </select>

            {/* Sort Dropdown */}
            <select
              className="form-select filter-select"
              value={sortOption}
              onChange={(e) => setSortOption(e.target.value)}
              aria-label="Sort records"
            >
              <option value="exposure_desc">Exposure: High → Low</option>
              <option value="exposure_asc">Exposure: Low → High</option>
              <option value="variance_desc">Net Variance: High → Low</option>
              <option value="variance_asc">Net Variance: Low → High</option>
              <option value="row_asc">Source Row Index</option>
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
                <th style={{ width: '18%' }}>Key Columns</th>
                <th style={{ width: '14%' }}>Match Status</th>
                <th style={{ width: '14%' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <span>Exposure</span>
                    <ArrowDownUp size={12} className="text-dim" />
                  </div>
                </th>
                <th style={{ width: '12%' }}>Source Row</th>
                <th style={{ width: '12%' }}>Target Row</th>
                <th style={{ width: '22%' }}>Differences / Message</th>
                <th style={{ width: '8%', textAlign: 'center' }}>Inspect</th>
              </tr>
            </thead>
            <tbody>
              {visibleResults.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ padding: 0, border: 'none' }}>
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
                  return (
                    <tr
                      key={row.id}
                      style={{ cursor: 'pointer' }}
                      onClick={() => setSelectedRecord(row)}
                      className="hover-row"
                    >
                      <td>
                        <code className="key-code">{JSON.stringify(row.key_values)}</code>
                      </td>
                      <td>
                        <StatusBadge status={row.match_status} />
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
                          {exposure.toFixed(2)}
                        </span>
                      </td>
                      <td className="cell-muted">{row.source_row_number ?? row.source_row_index ?? '—'}</td>
                      <td className="cell-muted">{row.target_row_number ?? row.target_row_index ?? '—'}</td>
                      <td>
                        {row.field_differences && row.field_differences.length > 0 ? (
                          <div className="diff-list">
                            {row.field_differences.slice(0, 2).map((diff, idx) => (
                              <div key={idx} className="diff-line">
                                <span className="diff-field">{diff.field_name}:</span>{' '}
                                <span className="diff-source">{String(diff.source_value)}</span> ≠{' '}
                                <span className="diff-target">{String(diff.target_value)}</span>
                              </div>
                            ))}
                            {row.field_differences.length > 2 && (
                              <span className="text-xs text-dim">
                                +{row.field_differences.length - 2} more differences
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="cell-muted">{row.message || 'Identical match'}</span>
                        )}
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          style={{ padding: '4px 8px' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedRecord(row);
                          }}
                          title="Open Side-by-Side Record Inspector"
                          aria-label={`Inspect record ${JSON.stringify(row.key_values)}`}
                        >
                          <Eye size={15} />
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

      {/* Slide-Out Record Inspector Drawer */}
      <RecordInspectorDrawer
        isOpen={Boolean(selectedRecord)}
        onClose={() => setSelectedRecord(null)}
        record={selectedRecord}
        projectId={projectId}
        runId={run?.id}
      />
    </div>
  );
};
