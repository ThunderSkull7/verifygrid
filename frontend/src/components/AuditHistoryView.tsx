import React, { useCallback, useEffect, useRef, useState } from 'react';
import type {
  DiscrepancyItemResponse,
  Project,
  VerificationResponse,
  VerificationResultItem,
  VerificationRun,
  VerificationRunListResponse,
} from '../types';
import { api } from '../services/api';
import {
  History,
  RefreshCw,
  Eye,
  AlertCircle,
  Clock,
  Inbox,
  ShieldCheck,
  ShieldAlert,
} from 'lucide-react';
import { StatusBadge } from './StatusBadge';
import { VerificationResultsView } from './VerificationResultsView';
import { CryptographicAuditViewer } from './CryptographicAuditViewer';
import { ExportActionControls } from './ExportActionControls';

interface AuditHistoryViewProps {
  project: Project;
}

const PAGE_SIZE = 20;

const formatDateTime = (value?: string | null): string => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const mapDiscrepancy = (item: DiscrepancyItemResponse): VerificationResultItem => ({
  id: item.id,
  key_values: item.key_values,
  match_status: item.match_status,
  discrepancy_category: item.discrepancy_category,
  source_row_number: item.source_row_number ?? null,
  target_row_number: item.target_row_number ?? null,
  source_row_numbers: item.source_row_numbers ?? undefined,
  target_row_numbers: item.target_row_numbers ?? undefined,
  source_record: item.source_record ?? null,
  target_record: item.target_record ?? null,
  field_differences: item.field_differences ?? undefined,
  message: item.message ?? null,
});

export const AuditHistoryView: React.FC<AuditHistoryViewProps> = ({ project }) => {
  const [runs, setRuns] = useState<VerificationRun[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedRun, setSelectedRun] = useState<VerificationRun | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailResponse, setDetailResponse] = useState<VerificationResponse | null>(null);
  const [detailTotal, setDetailTotal] = useState<number>(0);
  const resultsAnchorRef = useRef<HTMLDivElement>(null);

  const fetchRuns = useCallback(
    async (nextLimit: number): Promise<VerificationRunListResponse> => {
      return api.listVerificationRuns(
        project.id,
        0,
        nextLimit,
        statusFilter !== 'all' ? statusFilter : undefined
      );
    },
    [project.id, statusFilter]
  );

  // Initial load and reload whenever the project or status filter changes.
  useEffect(() => {
    let cancelled = false;
    fetchRuns(PAGE_SIZE)
      .then((data) => {
        if (cancelled) return;
        setRuns(data.items);
        setTotal(data.total);
        setLoading(false);
      })
      .catch((err: any) => {
        if (cancelled) return;
        setError(err.message || 'Failed to load audit history');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fetchRuns]);

  const runLoad = async (nextLimit: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRuns(nextLimit);
      setRuns(data.items);
      setTotal(data.total);
    } catch (err: any) {
      setError(err.message || 'Failed to load audit history');
    } finally {
      setLoading(false);
    }
  };

  const handleStatusFilterChange = (value: string) => {
    setStatusFilter(value);
    setLimit(PAGE_SIZE);
    setLoading(true);
    setError(null);
    setSelectedRun(null);
    setDetailResponse(null);
    setDetailError(null);
    setDetailTotal(0);
  };

  const refresh = () => {
    void runLoad(limit);
  };

  const loadMore = () => {
    const next = limit + PAGE_SIZE;
    setLimit(next);
    void runLoad(next);
  };

  const handleViewRun = async (run: VerificationRun) => {
    setSelectedRun(run);
    setDetailResponse(null);
    setDetailError(null);

    if (run.status !== 'completed') {
      // Failed or pending runs have no result set to load — the panel below
      // renders the run status and any backend error message instead.
      resultsAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }

    setDetailLoading(true);
    try {
      // The backend caps the results page size at 200; full sets are available via exports.
      const [freshRun, discrepancies] = await Promise.all([
        api.getVerificationRun(project.id, run.id),
        api.listRunDiscrepancies(project.id, run.id, { skip: 0, limit: 200 }),
      ]);
      if (!freshRun.summary) {
        throw new Error('Run summary is not available yet.');
      }
      const results = discrepancies.items.map(mapDiscrepancy);
      setSelectedRun(freshRun);
      setDetailTotal(discrepancies.total);
      setDetailResponse({
        project_id: project.id,
        source_file_id: freshRun.source_file_id ?? undefined,
        target_file_id: freshRun.target_file_id ?? undefined,
        key_columns: freshRun.key_columns,
        column_mapping: freshRun.column_mapping ?? {},
        summary: freshRun.summary,
        results,
        discrepancies: results.filter((r) => r.discrepancy_category !== 'none'),
        warnings: [],
        errors: [],
      });
      requestAnimationFrame(() => {
        resultsAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    } catch (err: any) {
      setDetailError(err.message || 'Failed to load run results');
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    setSelectedRun(null);
    setDetailResponse(null);
    setDetailError(null);
    setDetailTotal(0);
  };

  const hasMore = runs.length < total;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Audit history</h1>
          <p className="page-subtitle">
            Persistent verification runs for <strong>{project.name}</strong> — inspect outcomes,
            review discrepancies, and re-export reports.
          </p>
        </div>
        <div className="row" style={{ gap: 10 }}>
          <select
            className="form-select filter-select"
            value={statusFilter}
            onChange={(e) => handleStatusFilterChange(e.target.value)}
            aria-label="Filter runs by status"
          >
            <option value="all">All statuses</option>
            <option value="pending">Pending</option>
            <option value="running">Processing</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            disabled={loading}
            title="Refresh audit history"
          >
            {loading ? <span className="spinner" aria-hidden="true" /> : <RefreshCw size={15} />}
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      <div className="card">
        <div className="section-head">
          <h3 className="section-title">
            <History size={17} /> Verification runs
          </h3>
          <span className="text-xs text-dim">
            {runs.length.toLocaleString()} of {total.toLocaleString()} run
            {total === 1 ? '' : 's'}
          </span>
        </div>

        {loading && runs.length === 0 ? (
          <div>
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton skeleton-line" style={{ height: 42, marginBottom: 8 }} />
            ))}
          </div>
        ) : runs.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">
              <Inbox size={22} />
            </div>
            <h3 className="empty-title">No audit runs yet</h3>
            <p className="empty-text">
              Execute a reconciliation with “Save persistent audit run” enabled and it will appear
              here with exportable results.
            </p>
          </div>
        ) : (
          <div className="table-container">
            <table className="data-table dense">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Created</th>
                  <th>Status</th>
                  <th>Sign-off</th>
                  <th>Key columns</th>
                  <th>Records compared</th>
                  <th>Discrepancies</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const summary = run.summary;
                  const isSelected = selectedRun?.id === run.id;
                  const signOff = run.sign_off_status || 'DRAFT';
                  return (
                    <tr key={run.id}>
                      <td>
                        <code className="run-id">{run.id.slice(0, 8)}</code>
                      </td>
                      <td className="cell-muted">
                        <span className="row" style={{ gap: 5 }}>
                          <Clock size={12} /> {formatDateTime(run.created_at)}
                        </span>
                      </td>
                      <td>
                        <StatusBadge status={run.status} />
                      </td>
                      <td>
                        {signOff === 'APPROVED' ? (
                          <span className="chip chip-success" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.74rem', fontWeight: 600 }}>
                            <ShieldCheck size={11} /> Approved
                          </span>
                        ) : signOff === 'AWAITING_SIGN_OFF' ? (
                          <span className="chip chip-warning" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.74rem', fontWeight: 600 }}>
                            <Clock size={11} /> Awaiting Sign-off
                          </span>
                        ) : signOff === 'REJECTED' ? (
                          <span className="chip chip-danger" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.74rem', fontWeight: 600 }}>
                            <ShieldAlert size={11} /> Rejected
                          </span>
                        ) : (
                          <span className="chip" style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                            Draft
                          </span>
                        )}
                      </td>
                      <td>
                        <div className="chip-list">
                          {run.key_columns.map((key) => (
                            <span key={key} className="chip">
                              {key}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="cell-muted">
                        {summary
                          ? `${summary.total_source_records.toLocaleString()} → ${summary.total_target_records.toLocaleString()}`
                          : '—'}
                      </td>
                      <td className="cell-muted">
                        {summary ? summary.total_discrepancies.toLocaleString() : '—'}
                      </td>
                      <td>
                        <button
                          type="button"
                          className={`btn btn-sm ${isSelected ? 'btn-secondary' : 'btn-ghost'}`}
                          onClick={() => handleViewRun(run)}
                          title={
                            run.status === 'completed'
                              ? 'View run results'
                              : 'Show run details'
                          }
                        >
                          <Eye size={14} /> View
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {hasMore && (
          <div className="table-footer-note">
            <span>Showing {runs.length.toLocaleString()} of {total.toLocaleString()} runs.</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={loadMore} disabled={loading}>
              {loading ? <span className="spinner" aria-hidden="true" /> : null}
              Load {PAGE_SIZE} more
            </button>
          </div>
        )}
      </div>

      <div ref={resultsAnchorRef} className="run-results-anchor" />

      {selectedRun && (
        <div>
          <div className="section-heading-row" style={{ flexWrap: 'wrap', gap: 12 }}>
            <h2 className="section-title">
              Run <code className="run-id">{selectedRun.id.slice(0, 8)}</code> —{' '}
              <StatusBadge status={selectedRun.status} />
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              {selectedRun.status === 'completed' && (
                <ExportActionControls
                  projectId={project.id}
                  runId={selectedRun.id}
                  size="sm"
                />
              )}
              <button type="button" className="btn btn-secondary btn-sm" onClick={closeDetail}>
                Close
              </button>
            </div>
          </div>

          {selectedRun.status === 'failed' && (
            <div className="alert alert-error" role="alert">
              <AlertCircle size={16} />
              <span>
                This run failed{selectedRun.error_message ? `: ${selectedRun.error_message}` : '.'}
              </span>
            </div>
          )}

          {(selectedRun.status === 'pending' || selectedRun.status === 'running') && (
            <div className="alert alert-info">
              <Clock size={16} />
              <span>This run has not finished processing yet. Refresh to check its status.</span>
            </div>
          )}

          {selectedRun.status === 'completed' && detailLoading && (
            <div className="card loading-inline">
              <span className="spinner" aria-hidden="true" /> Loading run results…
            </div>
          )}

          {detailError && selectedRun.status === 'completed' && !detailLoading && (
            <div className="alert alert-error" role="alert">
              <AlertCircle size={16} />
              <span>{detailError}</span>
            </div>
          )}

          {detailResponse && !detailLoading && (
            <>
              {detailTotal > detailResponse.results.length && (
                <div className="alert alert-info">
                  <Eye size={16} />
                  <span>
                    Showing the first {detailResponse.results.length.toLocaleString()} of{' '}
                    {detailTotal.toLocaleString()} recorded results in the browser. Use the export
                    buttons below for the complete dataset.
                  </span>
                </div>
              )}
              <VerificationResultsView
                projectId={project.id}
                response={detailResponse}
                run={selectedRun}
              />
              <div style={{ marginTop: 24 }}>
                <CryptographicAuditViewer
                  projectId={project.id}
                  runId={selectedRun.id}
                />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};
