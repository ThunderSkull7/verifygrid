import React, { useRef, useState } from 'react';
import type { Project, SourceFile, PreprocessingResult } from '../types';
import { api } from '../services/api';
import {
  UploadCloud,
  FileSpreadsheet,
  AlertTriangle,
  Check,
  Database,
  ListChecks,
} from 'lucide-react';

interface FileUploadSectionProps {
  project: Project;
  onFileUploaded: (file: SourceFile, profile?: PreprocessingResult) => void;
  datasets: { id: string; name: string; profile?: PreprocessingResult }[];
}

type UploadPhase = 'idle' | 'uploading' | 'profiling' | 'done';

export const FileUploadSection: React.FC<FileUploadSectionProps> = ({
  project,
  onFileUploaded,
  datasets,
}) => {
  const [phase, setPhase] = useState<UploadPhase>('idle');
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUploaded, setLastUploaded] = useState<SourceFile | null>(null);
  const [profileResult, setProfileResult] = useState<PreprocessingResult | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const busy = phase === 'uploading' || phase === 'profiling';

  const handleFile = async (file: File) => {
    setError(null);
    setPhase('uploading');
    setProfileResult(null);

    try {
      // 1. Upload to backend
      const sourceFile = await api.uploadSourceFile(project.id, file);
      setLastUploaded(sourceFile);

      // 2. Automatically profile / preprocess file
      setPhase('profiling');
      const preprocessed = await api.preprocessFile(project.id, sourceFile.id);
      setProfileResult(preprocessed);
      setPhase('done');

      onFileUploaded(sourceFile, preprocessed);
    } catch (err: any) {
      setError(err.message || 'File upload or preprocessing failed');
      setPhase('idle');
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    void handleFile(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    if (busy) return;
    const file = e.dataTransfer.files?.[0];
    if (file) void handleFile(file);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!busy) setDragActive(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
  };

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h3 className="card-title">
            <UploadCloud size={19} /> Dataset upload &amp; preprocessing
          </h3>
          <p className="card-description">
            Upload CSV or XLSX source files for normalization, schema inference, and verification.
          </p>
        </div>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      <div
        className={`dropzone ${dragActive ? 'dragging' : ''} ${busy ? 'disabled' : ''}`}
        onClick={() => !busy && fileInputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        role="button"
        tabIndex={0}
        aria-label="Upload dataset file"
        aria-disabled={busy}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !busy) {
            e.preventDefault();
            fileInputRef.current?.click();
          }
        }}
      >
        <input
          type="file"
          ref={fileInputRef}
          accept=".csv,.xlsx,.xls"
          style={{ display: 'none' }}
          onChange={handleFileChange}
          disabled={busy}
        />
        <div className="dropzone-icon">
          <UploadCloud size={22} />
        </div>
        <h4 className="dropzone-title">
          {phase === 'uploading'
            ? 'Uploading file…'
            : phase === 'profiling'
              ? 'Preprocessing dataset…'
              : 'Drop a CSV or XLSX file here'}
        </h4>
        <p className="dropzone-hint">
          or <span className="link-accent">browse local files</span> — up to 100,000 data rows per
          dataset
        </p>
      </div>

      {busy && (
        <div className="upload-steps" aria-live="polite">
          <span className={`step-pill ${phase === 'uploading' ? 'active' : 'done'}`}>
            {phase === 'uploading' ? <span className="spinner" /> : <Check size={13} />}
            Uploading file
          </span>
          <span className={`step-pill ${phase === 'profiling' ? 'active' : 'done'}`}>
            {phase === 'profiling' ? <span className="spinner" /> : <Check size={13} />}
            Inferring schema &amp; normalizing
          </span>
        </div>
      )}

      {lastUploaded && profileResult && (
        <div className="upload-result">
          <div className="upload-result-head">
            <FileSpreadsheet size={19} className="text-accent" />
            <span className="upload-result-name">{profileResult.original_filename}</span>
            <span className="upload-result-meta">
              {profileResult.data_rows_count.toLocaleString()} data rows ·{' '}
              {profileResult.columns.length} columns
            </span>
            <span className="badge badge-success">
              <span className="badge-dot" aria-hidden="true" /> Preprocessed
            </span>
          </div>

          <div className="metric-grid" style={{ marginBottom: 4 }}>
            <div className="metric-card flat">
              <span className="metric-label">Data rows</span>
              <span className="metric-value" style={{ fontSize: '1.25rem' }}>
                {profileResult.data_rows_count.toLocaleString()}
              </span>
            </div>
            <div className="metric-card flat">
              <span className="metric-label">Detected columns</span>
              <span className="metric-value" style={{ fontSize: '1.25rem' }}>
                {profileResult.columns.length}
              </span>
            </div>
            <div className="metric-card flat">
              <span className="metric-label">Duplicate rows</span>
              <span className="metric-value" style={{ fontSize: '1.25rem' }}>
                {profileResult.duplicate_rows_count}
              </span>
            </div>
          </div>

          <div className="schema-block">
            <h5 className="schema-title">Inferred schema &amp; normalized columns</h5>
            <div className="chip-list">
              {profileResult.columns.map((col) => (
                <div key={col.normalized_name} className="chip" title={col.original_name}>
                  <strong>{col.normalized_name}</strong>
                  <span className="text-dim">· {col.detected_type}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {datasets.length > 0 && (
        <div className="file-list">
          <div className="file-list-title">
            Session datasets ({datasets.length}) — upload at least two to reconcile
          </div>
          {datasets.map((dataset, index) => (
            <div key={`${dataset.id}-${index}`} className="file-item">
              <FileSpreadsheet size={17} className="file-item-icon" />
              <div className="file-item-info">
                <span className="file-item-name" title={dataset.name}>
                  {dataset.name}
                </span>
                <span className="file-item-meta">
                  {dataset.profile
                    ? `${dataset.profile.data_rows_count.toLocaleString()} rows · ${dataset.profile.columns.length} columns`
                    : 'Uploaded'}
                </span>
              </div>
              {dataset.profile ? (
                <span className="badge badge-success">
                  <span className="badge-dot" aria-hidden="true" /> Ready
                </span>
              ) : (
                <span className="badge badge-neutral">Uploaded</span>
              )}
            </div>
          ))}
        </div>
      )}

      {datasets.length === 0 && !busy && (
        <div className="info-strip" style={{ marginTop: 16, marginBottom: 0 }}>
          <Database size={15} />
          <span>
            <strong>Tip:</strong> upload both a baseline (source) and a comparison (target) dataset
            to unlock the reconciliation engine.
          </span>
        </div>
      )}

      {profileResult && profileResult.issues.length > 0 && (
        <div className="info-strip" style={{ marginTop: 16, marginBottom: 0 }}>
          <ListChecks size={15} />
          <span>
            {profileResult.issues.length} validation note
            {profileResult.issues.length === 1 ? '' : 's'} detected during preprocessing (e.g.{' '}
            {profileResult.issues[0].message}).
          </span>
        </div>
      )}
    </div>
  );
};
