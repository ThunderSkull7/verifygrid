import React, { useState } from 'react';
import type { VerificationResponse, VerificationRun } from '../types';
import { api } from '../services/api';
import {
  CheckCircle2,
  Download,
  Filter,
  Search,
} from 'lucide-react';

interface VerificationResultsViewProps {
  projectId: string;
  response: VerificationResponse;
  run?: VerificationRun;
}

export const VerificationResultsView: React.FC<VerificationResultsViewProps> = ({
  projectId,
  response,
  run,
}) => {
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [downloading, setDownloading] = useState<boolean>(false);
  const [searchKey, setSearchKey] = useState<string>('');

  const summary = response.summary;

  const handleDownload = async (format: 'csv' | 'xlsx' | 'json') => {
    if (!run) {
      alert('A persistent verification run is required for exported file generation.');
      return;
    }
    setDownloading(true);
    try {
      await api.downloadExport(
        projectId,
        run.id,
        format,
        categoryFilter !== 'all' ? categoryFilter : undefined,
        statusFilter !== 'all' ? statusFilter : undefined
      );
    } catch (err: any) {
      alert(`Export failed: ${err.message}`);
    } finally {
      setDownloading(false);
    }
  };

  const filteredResults = response.results.filter((item) => {
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
  });

  const getBadgeClass = (category: string) => {
    switch (category) {
      case 'none':
        return 'badge-identical';
      case 'field_mismatch':
        return 'badge-field_mismatch';
      case 'missing_record':
        return 'badge-missing_record';
      case 'duplicate_key':
        return 'badge-duplicate_key';
      default:
        return 'badge-field_mismatch';
    }
  };

  return (
    <div>
      {/* Top Summary Banner */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div>
            <h2 className="card-title">
              <CheckCircle2 size={24} color="var(--accent-emerald)" /> Reconciliation Results Summary
            </h2>
            <p className="card-description">
              Audit results across {summary.total_source_records.toLocaleString()} source records and{' '}
              {summary.total_target_records.toLocaleString()} target records.
            </p>
          </div>

          {run && (
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => handleDownload('csv')}
                disabled={downloading}
              >
                <Download size={14} /> Export CSV
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => handleDownload('xlsx')}
                disabled={downloading}
              >
                <Download size={14} /> Export Excel
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => handleDownload('json')}
                disabled={downloading}
              >
                <Download size={14} /> Export JSON
              </button>
            </div>
          )}
        </div>

        {/* Metric Cards Grid */}
        <div className="metric-grid">
          <div className="metric-card">
            <span className="metric-label">Identical Matches</span>
            <span className="metric-value" style={{ color: 'var(--accent-emerald)' }}>
              {summary.identical_matches.toLocaleString()}
            </span>
          </div>

          <div className="metric-card">
            <span className="metric-label">Field Mismatches</span>
            <span className="metric-value" style={{ color: 'var(--accent-rose)' }}>
              {summary.field_mismatches.toLocaleString()}
            </span>
          </div>

          <div className="metric-card">
            <span className="metric-label">Missing in Target</span>
            <span className="metric-value" style={{ color: 'var(--accent-amber)' }}>
              {summary.unmatched_source_records.toLocaleString()}
            </span>
          </div>

          <div className="metric-card">
            <span className="metric-label">Missing in Source</span>
            <span className="metric-value" style={{ color: 'var(--accent-amber)' }}>
              {summary.unmatched_target_records.toLocaleString()}
            </span>
          </div>

          <div className="metric-card">
            <span className="metric-label">Duplicate Keys</span>
            <span className="metric-value" style={{ color: '#c084fc' }}>
              {(summary.duplicate_source_keys_count + summary.duplicate_target_keys_count).toLocaleString()}
            </span>
          </div>

          <div className="metric-card">
            <span className="metric-label">Total Discrepancies</span>
            <span className="metric-value">
              {summary.total_discrepancies.toLocaleString()}
            </span>
          </div>
        </div>
      </div>

      {/* Discrepancy & Results Table */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, minWidth: 260 }}>
            <div style={{ position: 'relative', width: '100%', maxWidth: 300 }}>
              <input
                type="text"
                className="form-input"
                style={{ paddingLeft: 34 }}
                placeholder="Search by key values..."
                value={searchKey}
                onChange={(e) => setSearchKey(e.target.value)}
              />
              <Search size={16} style={{ position: 'absolute', left: 10, top: 12, color: 'var(--text-dim)' }} />
            </div>
          </div>

          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Filter size={16} color="var(--text-muted)" />
              <select
                className="form-select"
                style={{ width: 'auto', padding: '8px 12px' }}
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
              >
                <option value="all">All Categories</option>
                <option value="none">Identical Matches</option>
                <option value="field_mismatch">Field Mismatches</option>
                <option value="missing_record">Missing Records</option>
                <option value="duplicate_key">Duplicate Keys</option>
              </select>
            </div>

            <select
              className="form-select"
              style={{ width: 'auto', padding: '8px 12px' }}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">All Match Statuses</option>
              <option value="identical">identical</option>
              <option value="field_mismatch">field_mismatch</option>
              <option value="missing_in_target">missing_in_target</option>
              <option value="missing_in_source">missing_in_source</option>
              <option value="duplicate_key_source">duplicate_key_source</option>
              <option value="duplicate_key_target">duplicate_key_target</option>
            </select>
          </div>
        </div>

        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Key Columns</th>
                <th>Category</th>
                <th>Match Status</th>
                <th>Source Row</th>
                <th>Target Row</th>
                <th>Field Differences / Discrepancy Details</th>
              </tr>
            </thead>
            <tbody>
              {filteredResults.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)' }}>
                    No records match the selected filters.
                  </td>
                </tr>
              ) : (
                filteredResults.slice(0, 100).map((row) => (
                  <tr key={row.id}>
                    <td>
                      <code style={{ color: '#93c5fd', fontSize: '0.85rem' }}>
                        {JSON.stringify(row.key_values)}
                      </code>
                    </td>
                    <td>
                      <span className={`badge ${getBadgeClass(row.discrepancy_category)}`}>
                        {row.discrepancy_category}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        {row.match_status}
                      </span>
                    </td>
                    <td>{row.source_row_number ?? '-'}</td>
                    <td>{row.target_row_number ?? '-'}</td>
                    <td>
                      {row.field_differences && row.field_differences.length > 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                          {row.field_differences.map((diff, idx) => (
                            <div key={idx} style={{ fontSize: '0.8rem' }}>
                              <strong style={{ color: 'var(--text-main)' }}>{diff.field_name}:</strong>{' '}
                              <span style={{ color: 'var(--accent-amber)' }}>
                                {String(diff.source_value)}
                              </span>{' '}
                              ≠{' '}
                              <span style={{ color: 'var(--accent-cyan)' }}>
                                {String(diff.target_value)}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                          {row.message || 'No field differences'}
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {filteredResults.length > 100 && (
          <div style={{ marginTop: 12, fontSize: '0.8rem', color: 'var(--text-dim)', textAlign: 'right' }}>
            Showing first 100 of {filteredResults.length.toLocaleString()} records. Download full report for complete audit set.
          </div>
        )}
      </div>
    </div>
  );
};
