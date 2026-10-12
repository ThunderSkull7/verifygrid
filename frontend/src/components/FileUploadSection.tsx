import React, { useRef, useState } from 'react';
import type { Project, SourceFile, PreprocessingResult } from '../types';
import { api } from '../services/api';
import { UploadCloud, FileSpreadsheet, CheckCircle, AlertTriangle } from 'lucide-react';

interface FileUploadSectionProps {
  project: Project;
  onFileUploaded: (file: SourceFile, profile?: PreprocessingResult) => void;
}

export const FileUploadSection: React.FC<FileUploadSectionProps> = ({ project, onFileUploaded }) => {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUploaded, setLastUploaded] = useState<SourceFile | null>(null);
  const [profiling, setProfiling] = useState(false);
  const [profileResult, setProfileResult] = useState<PreprocessingResult | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    setUploading(true);
    setProfileResult(null);

    try {
      // 1. Upload to backend
      const sourceFile = await api.uploadSourceFile(project.id, file);
      setLastUploaded(sourceFile);

      // 2. Automatically profile / preprocess file
      setProfiling(true);
      const preprocessed = await api.preprocessFile(project.id, sourceFile.id);
      setProfileResult(preprocessed);

      onFileUploaded(sourceFile, preprocessed);
    } catch (err: any) {
      setError(err.message || 'File upload or preprocessing failed');
    } finally {
      setUploading(false);
      setProfiling(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h3 className="card-title">
            <UploadCloud size={20} /> Dataset Upload & Preprocessing
          </h3>
          <p className="card-description">
            Upload CSV or XLSX source files for normalization, schema inference, and verification.
          </p>
        </div>
      </div>

      {error && (
        <div className="alert-box alert-error">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}

      <div
        style={{
          border: '2px dashed var(--border-color)',
          borderRadius: 'var(--radius-md)',
          padding: '36px 20px',
          textAlign: 'center',
          backgroundColor: 'rgba(15, 23, 42, 0.4)',
          cursor: uploading ? 'wait' : 'pointer',
        }}
        onClick={() => !uploading && fileInputRef.current?.click()}
      >
        <input
          type="file"
          ref={fileInputRef}
          accept=".csv,.xlsx,.xls"
          style={{ display: 'none' }}
          onChange={handleFileChange}
          disabled={uploading}
        />
        <UploadCloud size={44} style={{ color: 'var(--primary)', marginBottom: 12 }} />
        <h4 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: 4 }}>
          {uploading ? 'Uploading and parsing file...' : 'Choose a CSV or XLSX dataset'}
        </h4>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          Supports comma-separated files and Excel spreadsheets up to 100,000 rows.
        </p>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          style={{ marginTop: 16 }}
          disabled={uploading}
          onClick={(e) => {
            e.stopPropagation();
            fileInputRef.current?.click();
          }}
        >
          {uploading ? 'Processing...' : 'Browse Local Files'}
        </button>
      </div>

      {profiling && (
        <div style={{ marginTop: 18, color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          Running automatic type inference and column normalization...
        </div>
      )}

      {lastUploaded && profileResult && (
        <div style={{ marginTop: 24, borderTop: '1px solid var(--border-subtle)', paddingTop: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <FileSpreadsheet size={20} color="var(--accent-emerald)" />
              <div>
                <strong style={{ fontSize: '0.95rem' }}>{profileResult.original_filename}</strong>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginLeft: 8 }}>
                  ({profileResult.data_rows_count.toLocaleString()} data rows, {profileResult.columns.length} columns)
                </span>
              </div>
            </div>
            <span className="badge badge-identical" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <CheckCircle size={12} /> Preprocessed
            </span>
          </div>

          <div className="metric-grid" style={{ marginBottom: 16 }}>
            <div className="metric-card" style={{ padding: 14 }}>
              <span className="metric-label">Data Rows</span>
              <span className="metric-value" style={{ fontSize: '1.25rem' }}>
                {profileResult.data_rows_count.toLocaleString()}
              </span>
            </div>
            <div className="metric-card" style={{ padding: 14 }}>
              <span className="metric-label">Detected Columns</span>
              <span className="metric-value" style={{ fontSize: '1.25rem' }}>
                {profileResult.columns.length}
              </span>
            </div>
            <div className="metric-card" style={{ padding: 14 }}>
              <span className="metric-label">Duplicate Rows</span>
              <span className="metric-value" style={{ fontSize: '1.25rem' }}>
                {profileResult.duplicate_rows_count}
              </span>
            </div>
          </div>

          {/* Column Inferred Types */}
          <div style={{ marginTop: 12 }}>
            <h5 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 8 }}>
              Inferred Schema & Normalized Columns:
            </h5>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {profileResult.columns.map((col) => (
                <div
                  key={col.normalized_name}
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid var(--border-subtle)',
                    padding: '6px 10px',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.8rem',
                  }}
                >
                  <strong style={{ color: 'var(--text-main)' }}>{col.normalized_name}</strong>
                  <span style={{ color: 'var(--text-dim)', marginLeft: 6 }}>({col.detected_type})</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
