import React, { useState } from 'react';
import {
  FileSpreadsheet,
  FileCode,
  FileText,
  Bookmark,
  ChevronDown,
  Check,
  AlertCircle,
  Sparkles,
} from 'lucide-react';
import { api } from '../services/api';

interface ExportActionControlsProps {
  projectId: string;
  runId: string;
  runName?: string;
  size?: 'sm' | 'md';
}

export const ExportActionControls: React.FC<ExportActionControlsProps> = ({
  projectId,
  runId,
  size = 'sm',
}) => {
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Golden Record dropdown state
  const [showGoldenDropdown, setShowGoldenDropdown] = useState(false);
  const [goldenPolicy, setGoldenPolicy] = useState<'ONLY_VERIFIED_AND_APPROVED' | 'ALL_WITH_STATUS_METADATA'>(
    'ONLY_VERIFIED_AND_APPROVED'
  );

  const clearMessages = () => {
    setError(null);
    setSuccess(null);
  };

  const handleDownloadWorkbook = async () => {
    clearMessages();
    setDownloading('workbook');
    try {
      await api.downloadAuditWorkbook(projectId, runId);
      setSuccess('Executive Audit Workbook downloaded successfully.');
      setTimeout(() => setSuccess(null), 4000);
    } catch (err: any) {
      setError(`Failed to download workbook: ${err.message || 'Unknown error'}`);
    } finally {
      setDownloading(null);
    }
  };

  const handleDownloadGolden = async (format: 'csv' | 'xlsx' | 'json') => {
    clearMessages();
    setDownloading(`golden-${format}`);
    setShowGoldenDropdown(false);
    try {
      await api.downloadGoldenRecord(projectId, runId, format, goldenPolicy);
      setSuccess(`Golden record (${format.toUpperCase()}) downloaded successfully.`);
      setTimeout(() => setSuccess(null), 4000);
    } catch (err: any) {
      setError(`Failed to download golden record: ${err.message || 'Unknown error'}`);
    } finally {
      setDownloading(null);
    }
  };

  const handleExportRecipe = async () => {
    clearMessages();
    setDownloading('recipe');
    try {
      await api.getRecipe(projectId, runId, true);
      setSuccess('Reconciliation recipe (.verifygrid.json) exported.');
      setTimeout(() => setSuccess(null), 4000);
    } catch (err: any) {
      setError(`Failed to export recipe: ${err.message || 'Unknown error'}`);
    } finally {
      setDownloading(null);
    }
  };

  const btnClass = size === 'sm' ? 'btn btn-secondary btn-sm' : 'btn btn-secondary';

  return (
    <div style={{ display: 'inline-flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {/* Executive Multi-Tab Audit Workbook Button */}
        <button
          type="button"
          className={btnClass}
          onClick={handleDownloadWorkbook}
          disabled={downloading !== null}
          title="Download comprehensive 4-tab audit workbook (Executive Summary, Detailed Comparison, Decisions, Golden Record)"
          style={{
            borderColor: 'var(--primary)',
            color: 'var(--primary)',
            fontWeight: 600,
          }}
        >
          {downloading === 'workbook' ? (
            <span className="spinner" />
          ) : (
            <FileSpreadsheet size={14} className="text-primary" />
          )}
          Executive Audit Workbook (XLSX)
        </button>

        {/* Golden Record Download Dropdown */}
        <div style={{ position: 'relative', display: 'inline-block' }}>
          <button
            type="button"
            className={btnClass}
            onClick={() => setShowGoldenDropdown((prev) => !prev)}
            disabled={downloading !== null}
            title="Download authoritative merged golden records"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            {downloading?.startsWith('golden') ? (
              <span className="spinner" />
            ) : (
              <Sparkles size={14} className="text-warning" />
            )}
            Golden Record Dataset
            <ChevronDown size={13} />
          </button>

          {showGoldenDropdown && (
            <div
              className="card"
              style={{
                position: 'absolute',
                top: '100%',
                left: 0,
                marginTop: 4,
                zIndex: 100,
                minWidth: 260,
                padding: '10px 12px',
                boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--bg-card)',
              }}
            >
              <div style={{ marginBottom: 8, paddingBottom: 6, borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                  EXPORT FILTER POLICY
                </span>
                <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <label
                    style={{
                      fontSize: '0.78rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      cursor: 'pointer',
                    }}
                  >
                    <input
                      type="radio"
                      name={`golden-policy-${runId}`}
                      checked={goldenPolicy === 'ONLY_VERIFIED_AND_APPROVED'}
                      onChange={() => setGoldenPolicy('ONLY_VERIFIED_AND_APPROVED')}
                    />
                    Only Verified &amp; Approved
                  </label>
                  <label
                    style={{
                      fontSize: '0.78rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      cursor: 'pointer',
                    }}
                  >
                    <input
                      type="radio"
                      name={`golden-policy-${runId}`}
                      checked={goldenPolicy === 'ALL_WITH_STATUS_METADATA'}
                      onChange={() => setGoldenPolicy('ALL_WITH_STATUS_METADATA')}
                    />
                    All with Status Metadata
                  </label>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                  CHOOSE FORMAT
                </span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ justifyContent: 'flex-start', padding: '6px 8px', fontSize: '0.82rem' }}
                  onClick={() => handleDownloadGolden('csv')}
                >
                  <FileText size={13} /> Golden Dataset (.CSV)
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ justifyContent: 'flex-start', padding: '6px 8px', fontSize: '0.82rem' }}
                  onClick={() => handleDownloadGolden('xlsx')}
                >
                  <FileSpreadsheet size={13} /> Golden Dataset (.XLSX)
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ justifyContent: 'flex-start', padding: '6px 8px', fontSize: '0.82rem' }}
                  onClick={() => handleDownloadGolden('json')}
                >
                  <FileCode size={13} /> Golden Dataset (.JSON)
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Recipe Export Button */}
        <button
          type="button"
          className={btnClass}
          onClick={handleExportRecipe}
          disabled={downloading !== null}
          title="Save this blueprint and rule setup as a reusable .verifygrid.json recipe"
        >
          {downloading === 'recipe' ? (
            <span className="spinner" />
          ) : (
            <Bookmark size={14} className="text-accent" />
          )}
          Export Recipe (.verifygrid.json)
        </button>
      </div>

      {/* Inline Feedback Alerts */}
      {error && (
        <div className="alert alert-error" style={{ margin: 0, padding: '4px 8px', fontSize: '0.78rem' }}>
          <AlertCircle size={13} />
          <span>{error}</span>
        </div>
      )}
      {success && (
        <div className="alert alert-success" style={{ margin: 0, padding: '4px 8px', fontSize: '0.78rem' }}>
          <Check size={13} />
          <span>{success}</span>
        </div>
      )}
    </div>
  );
};
