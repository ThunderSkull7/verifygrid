import React, { useMemo, useState } from 'react';
import type { VerificationResponse, VerificationRun } from '../types';
import { api } from '../services/api';
import {
  CheckCircle2,
  Download,
  Filter,
  Search,
  X,
  AlertCircle,
  Info,
  Inbox,
  TableProperties,
} from 'lucide-react';
import { StatusBadge } from './StatusBadge';

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
  const [downloadingFormat, setDownloadingFormat] = useState<'csv' | 'xlsx' | 'json' | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [searchKey, setSearchKey] = useState<string>('');
  const [visibleCount, setVisibleCount] = useState<number>(PAGE_SIZE);

  const summary = response.summary;

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

  const filteredResults = useMemo(
    () =>
      response.results.filter((item) => {
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
        return true;
      }),
    [response.results, categoryFilter, statusFilter, searchKey]
  );

  const visibleResults = filteredResults.slice(0, visibleCount);
  const hasActiveFilters =
    categoryFilter !== 'all' || statusFilter !== 'all' || searchKey.trim().length > 0;

  const clearFilters = () => {
    setCategoryFilter('all');
    setStatusFilter('all');
    setSearchKey('');
  };

  return (
    <div>
      {/* Summary */}
      <div className="card">
        <div className="card-header" style={{ marginBottom: 18 }}>
          <div>
            <h2 className="card-title">
              <CheckCircle2 size={20} /> Reconciliation summary
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
                  {downloadingFormat === 'csv' ? (
                    <span className="spinner" aria-hidden="true" />
                  ) : (
                    <Download size={14} />
                  )}
                  CSV
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleDownload('xlsx')}
                  disabled={downloadingFormat !== null}
                >
                  {downloadingFormat === 'xlsx' ? (
                    <span className="spinner" aria-hidden="true" />
                  ) : (
                    <Download size={14} />
                  )}
                  Excel
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleDownload('json')}
                  disabled={downloadingFormat !== null}
                >
                  {downloadingFormat === 'json' ? (
                    <span className="spinner" aria-hidden="true" />
                  ) : (
                    <Download size={14} />
                  )}
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
          <div className="alert alert-error" role="alert">
            <AlertCircle size={16} />
            <span>{exportError}</span>
          </div>
        )}

        <div className="metric-grid">
          <div className="metric-card flat">
            <span className="metric-label">Identical matches</span>
            <span className="metric-value text-success">
              {summary.identical_matches.toLocaleString()}
            </span>
            <span className="metric-foot">
              {summary.matched_records.toLocaleString()} records paired
            </span>
          </div>

          <div className="metric-card flat">
            <span className="metric-label">Field mismatches</span>
            <span className="metric-value text-danger">
              {summary.field_mismatches.toLocaleString()}
            </span>
            <span className="metric-foot">
              {(summary.records_with_differences ?? summary.field_mismatches).toLocaleString()}{' '}
              records with differences
            </span>
          </div>

          <div className="metric-card flat">
            <span className="metric-label">Missing in target</span>
            <span className="metric-value text-warning">
              {summary.unmatched_source_records.toLocaleString()}
            </span>
            <span className="metric-foot">Present only in source</span>
          </div>

          <div className="metric-card flat">
            <span className="metric-label">Missing in source</span>
            <span className="metric-value text-warning">
              {summary.unmatched_target_records.toLocaleString()}
            </span>
            <span className="metric-foot">Present only in target</span>
          </div>

          <div className="metric-card flat">
            <span className="metric-label">Duplicate keys</span>
            <span className="metric-value text-violet">
              {(
                summary.duplicate_source_keys_count + summary.duplicate_target_keys_count
              ).toLocaleString()}
            </span>
            <span className="metric-foot">
              {summary.duplicate_source_records.toLocaleString()} source ·{' '}
              {summary.duplicate_target_records.toLocaleString()} target rows
            </span>
          </div>

          <div className="metric-card flat">
            <span className="metric-label">Total discrepancies</span>
            <span className="metric-value">{summary.total_discrepancies.toLocaleString()}</span>
            <span className="metric-foot">Requires review or export</span>
          </div>
        </div>
      </div>

      {/* Records table */}
      <div className="card">
        <div className="section-head">
          <h3 className="section-title">
            <TableProperties size={17} /> Record-level results
          </h3>
          <span className="text-xs text-dim">
            Showing {Math.min(visibleCount, filteredResults.length).toLocaleString()} of{' '}
            {filteredResults.length.toLocaleString()}
          </span>
        </div>

        <div className="toolbar">
          <div className="search-box">
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

          <div className="row" style={{ gap: 8 }}>
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
            </select>
            {hasActiveFilters && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={clearFilters}>
                <X size={14} /> Clear
              </button>
            )}
          </div>
        </div>

        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Key columns</th>
                <th>Match status</th>
                <th>Source row</th>
                <th>Target row</th>
                <th>Field differences / details</th>
              </tr>
            </thead>
            <tbody>
              {visibleResults.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ padding: 0, border: 'none' }}>
                    <div className="empty-state" style={{ padding: '38px 20px' }}>
                      <div className="empty-icon">
                        {hasActiveFilters ? <Search size={22} /> : <Inbox size={22} />}
                      </div>
                      <h3 className="empty-title">
                        {hasActiveFilters ? 'No records match your filters' : 'No records'}
                      </h3>
                      <p className="empty-text" style={{ marginBottom: hasActiveFilters ? 14 : 0 }}>
                        {hasActiveFilters
                          ? 'Try broadening the category, status, or search filters.'
                          : 'This verification returned no individual records.'}
                      </p>
                      {hasActiveFilters && (
                        <button type="button" className="btn btn-secondary btn-sm" onClick={clearFilters}>
                          <X size={14} /> Clear filters
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                visibleResults.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <code className="key-code">{JSON.stringify(row.key_values)}</code>
                    </td>
                    <td>
                      <StatusBadge status={row.match_status} />
                    </td>
                    <td className="cell-muted">{row.source_row_number ?? '—'}</td>
                    <td className="cell-muted">{row.target_row_number ?? '—'}</td>
                    <td>
                      {row.field_differences && row.field_differences.length > 0 ? (
                        <div className="diff-list">
                          {row.field_differences.map((diff, idx) => (
                            <div key={idx} className="diff-line">
                              <span className="diff-field">{diff.field_name}:</span>{' '}
                              <span className="diff-source">{String(diff.source_value)}</span> ≠{' '}
                              <span className="diff-target">{String(diff.target_value)}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="cell-muted">{row.message || 'No field differences'}</span>
                      )}
                    </td>
                  </tr>
                ))
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
    </div>
  );
};
