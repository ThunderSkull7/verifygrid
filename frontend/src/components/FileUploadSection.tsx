import React, { useRef, useState } from 'react';
import type { Project, SourceFile, PreprocessingResult, UploadedDataset } from '../types';
import type { VerificationMode } from './ReconciliationWizard';
import { api } from '../services/api';
import {
  UploadCloud,
  FileSpreadsheet,
  AlertTriangle,
  Check,
  Database,
  ListChecks,
  ShieldAlert,
  Star,
  Trash2,
} from 'lucide-react';
import { ProfilingQuarantineDrawer } from './ProfilingQuarantineDrawer';

interface FileUploadSectionProps {
  project: Project;
  onFileUploaded: (file: SourceFile, profile?: PreprocessingResult) => void;
  datasets: UploadedDataset[];
  mode?: VerificationMode;
  /** Batch 2: editable labels / explicit roles (organization mode). */
  onLabelChange?: (fileId: string, label: string) => void;
  onRoleChange?: (fileId: string, isPrimary: boolean) => void;
  onRemoveFile?: (fileId: string) => void;
  /** Batch 7: explicit XLSX worksheet selection per file (null = deselect). */
  onWorksheetChange?: (fileId: string, sheet: string | null) => void;
}

type UploadPhase = 'idle' | 'uploading' | 'profiling' | 'done';

interface UploadFailure {
  filename: string;
  message: string;
}

export const FileUploadSection: React.FC<FileUploadSectionProps> = ({
  project,
  onFileUploaded,
  datasets,
  mode = 'financial',
  onLabelChange,
  onRoleChange,
  onRemoveFile,
  onWorksheetChange,
}) => {
  const isOrganization = mode === 'organization';
  const [phase, setPhase] = useState<UploadPhase>('idle');
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUploaded, setLastUploaded] = useState<SourceFile | null>(null);
  const [profileResult, setProfileResult] = useState<PreprocessingResult | null>(null);
  const [drawerFile, setDrawerFile] = useState<{ id: string; name: string; worksheet?: string | null } | null>(null);
  // Batch 2 (organization mode): per-file failures for multi-file selections.
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);
  const [failedFiles, setFailedFiles] = useState<UploadFailure[]>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const busy = phase === 'uploading' || phase === 'profiling';

  const uploadAndProfileOne = async (file: File) => {
    setPhase('uploading');
    setProfileResult(null);
    setUploadProgress(null);

    try {
      // 1. Upload to backend (existing single-file ingestion endpoint)
      const sourceFile = await api.uploadSourceFile(project.id, file);
      setLastUploaded(sourceFile);

      // 2. Automatically profile / preprocess file
      setPhase('profiling');
      const preprocessed = await api.preprocessFile(project.id, sourceFile.id);
      setProfileResult(preprocessed);
      setPhase('done');

      onFileUploaded(sourceFile, preprocessed);
      return true;
    } catch (err: any) {
      setError(err.message || 'File upload or preprocessing failed');
      setPhase('idle');
      return false;
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  /** Organization mode: upload several selected files sequentially through the
   *  existing ingestion path, reporting failures per file and letting the user
   *  retry only what failed. */
  const uploadMany = async (files: File[]) => {
    setError(null);
    setFailedFiles([]);
    let succeeded = 0;
    for (let i = 0; i < files.length; i += 1) {
      const file = files[i];
      setUploadProgress(`File ${i + 1} of ${files.length}`);
      const ok = await uploadAndProfileOne(file);
      if (ok) {
        succeeded += 1;
      } else {
        setFailedFiles((prev) => [
          ...prev,
          { filename: file.name, message: 'Upload or pre-processing failed' },
        ]);
      }
    }
    setUploadProgress(null);
  };

  const handleFiles = (files: File[]) => {
    const supported = files.filter((f) => /\.(csv|xlsx)$/i.test(f.name));
    const unsupported = files.filter((f) => !/\.(csv|xlsx)$/i.test(f.name));
    if (unsupported.length > 0) {
      setFailedFiles((prev) => [
        ...prev,
        ...unsupported.map((f) => ({ filename: f.name, message: 'Only CSV and XLSX files are supported' })),
      ]);
    }
    if (supported.length === 0) return;
    if (isOrganization && supported.length > 1) {
      void uploadMany(supported);
    } else {
      void uploadAndProfileOne(supported[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    void handleFiles(files);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    if (busy) return;
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length) void handleFiles(files);
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
            <UploadCloud size={19} />{' '}
            {isOrganization ? 'File upload & pre-flight check' : 'Dataset upload & preprocessing'}
          </h3>
          <p className="card-description">
            {isOrganization
              ? 'Add your CSV or XLSX files together (e.g. academic register, hostel allocation, ID card export). Each file is checked for quality before any records are compared.'
              : 'Upload CSV or XLSX source files for normalization, schema inference, and verification.'}
          </p>
        </div>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {failedFiles.length > 0 && (
        <div className="alert alert-error" role="alert">
          <AlertTriangle size={16} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600 }}>
              {failedFiles.length === 1 ? '1 file was not added:' : `${failedFiles.length} files were not added:`}
            </div>
            <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
              {failedFiles.slice(0, 5).map((f, i) => (
                <li key={`${f.filename}-${i}`} style={{ fontSize: '0.85rem' }}>
                  {f.filename} — {f.message}
                </li>
              ))}
            </ul>
            {failedFiles.length > 5 && (
              <div className="text-dim" style={{ fontSize: '0.8rem' }}>
                …and {failedFiles.length - 5} more.
              </div>
            )}
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-xs"
            onClick={() => setFailedFiles([])}
            aria-label="Dismiss failed file list"
          >
            Dismiss
          </button>
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
        aria-label={isOrganization ? 'Upload one or more CSV or XLSX files' : 'Upload dataset file'}
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
          multiple={isOrganization}
          style={{ display: 'none' }}
          onChange={handleFileChange}
          disabled={busy}
        />
        <div className="dropzone-icon">
          <UploadCloud size={22} />
        </div>
        <h4 className="dropzone-title">
          {phase === 'uploading'
            ? uploadProgress || 'Uploading file…'
            : phase === 'profiling'
              ? 'Preprocessing dataset…'
              : isOrganization
                ? 'Drop your CSV or XLSX files here'
                : 'Drop a CSV or XLSX file here'}
        </h4>
        <p className="dropzone-hint">
          or <span className="link-accent">browse local files</span>
          {isOrganization ? ' — you can select several files at once' : ''} — up to 100,000 data rows per
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

      {!isOrganization && lastUploaded && profileResult && (
        <div className="upload-result">
          <div className="upload-result-head">
            <FileSpreadsheet size={19} className="text-accent" />
            <span className="upload-result-name">{profileResult.original_filename}</span>
            <span className="upload-result-meta">
              {profileResult.data_rows_count.toLocaleString()} data rows ·{' '}
              {profileResult.columns.length} columns
            </span>
            <button
              type="button"
              className="btn btn-secondary btn-xs"
              style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6 }}
              onClick={() =>
                setDrawerFile({
                  id: lastUploaded.id,
                  name: lastUploaded.original_filename,
                  worksheet: null,
                })
              }
            >
              <ShieldAlert size={13} className="text-accent" />
              Pre-flight &amp; Quarantine
            </button>
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
            {isOrganization ? 'Session files' : 'Session datasets'} ({datasets.length})
            {isOrganization
              ? ' — mark one file as the primary source; the rest are checked against it'
              : ' — upload at least two to reconcile'}
          </div>
          {datasets.map((dataset) => {
            const dupeRows = dataset.profile?.duplicate_rows_count ?? 0;
            const emptyRows = dataset.profile?.empty_rows_count ?? 0;
            return (
              <div key={dataset.id} className="file-item">
                <FileSpreadsheet size={17} className="file-item-icon" />
                <div className="file-item-info">
                  {isOrganization ? (
                    <input
                      type="text"
                      className="form-input"
                      value={dataset.label}
                      onChange={(e) => onLabelChange?.(dataset.id, e.target.value)}
                      aria-label={`Display label for ${dataset.name}`}
                      maxLength={120}
                      style={{ fontSize: '0.9rem', padding: '5px 8px', maxWidth: 340 }}
                    />
                  ) : (
                    <span className="file-item-name" title={dataset.name}>
                      {dataset.name}
                    </span>
                  )}
                  <span className="file-item-meta">
                    {dataset.profile
                      ? `${dataset.profile.data_rows_count.toLocaleString()} rows · ${dataset.profile.columns.length} columns`
                      : 'Uploaded'}
                    {isOrganization && (
                      <span className="file-item-name" style={{ display: 'block', opacity: 0.75 }} title={dataset.name}>
                        {dataset.name}
                      </span>
                    )}
                  </span>
                  {/* Batch 7: explicit worksheet selection for XLSX workbooks. The
                      workbook's sheet names come from profiling metadata; no sheet is
                      used for verification until the user explicitly chooses one. */}
                  {isOrganization && (dataset.profile?.sheet_names?.length ?? 0) > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
                      <select
                        className="form-select"
                        value={dataset.selectedSheet ?? ''}
                        onChange={(e) => onWorksheetChange?.(dataset.id, e.target.value || null)}
                        aria-label={`Worksheet to use from ${dataset.label || dataset.name}`}
                        style={{ fontSize: '0.8rem', padding: '3px 6px', maxWidth: 220 }}
                      >
                        <option value="">— Select worksheet —</option>
                        {dataset.profile!.sheet_names!.map((sheetName) => (
                          <option key={sheetName} value={sheetName}>{sheetName}</option>
                        ))}
                      </select>
                      {!dataset.selectedSheet && (
                        <span className="badge badge-warning" style={{ fontSize: '0.72rem' }}>
                          Worksheet required
                        </span>
                      )}
                    </div>
                  )}
                </div>
                {isOrganization && (
                  <>
                    <div
                      role="group"
                      aria-label={`Role for ${dataset.label || dataset.name}`}
                      style={{ display: 'inline-flex', gap: 6 }}
                    >
                      <button
                        type="button"
                        className={`btn btn-xs ${dataset.isPrimary ? 'btn-primary' : 'btn-secondary'}`}
                        onClick={() => onRoleChange?.(dataset.id, true)}
                        aria-pressed={dataset.isPrimary}
                        title="Primary source — authoritative values other files are checked against"
                      >
                        <Star size={12} /> Primary source
                      </button>
                      <button
                        type="button"
                        className={`btn btn-xs ${dataset.isPrimary ? 'btn-secondary' : 'btn-primary'}`}
                        onClick={() => onRoleChange?.(dataset.id, false)}
                        aria-pressed={!dataset.isPrimary}
                        title="Target to verify — its values are compared with the primary source"
                      >
                        Target
                      </button>
                    </div>
                    {dupeRows > 0 && (
                      <span className="badge badge-neutral" title={`${dupeRows} duplicate row(s) detected`}>
                        {dupeRows} duplicate row{dupeRows === 1 ? '' : 's'}
                      </span>
                    )}
                    {emptyRows > 0 && (
                      <span className="badge badge-neutral" title={`${emptyRows} blank row(s) detected`}>
                        {emptyRows} blank row{emptyRows === 1 ? '' : 's'}
                      </span>
                    )}
                  </>
                )}
                <button
                  type="button"
                  className="btn btn-secondary btn-xs"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}
                  onClick={() => setDrawerFile({ id: dataset.id, name: dataset.label || dataset.name, worksheet: dataset.selectedSheet ?? null })}
                  title="Inspect profiling metrics and quarantine anomalies"
                >
                  <ShieldAlert size={12} className="text-accent" />
                  Pre-flight Profile
                </button>
                {isOrganization && onRemoveFile && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-xs"
                    onClick={() => onRemoveFile(dataset.id)}
                    aria-label={`Remove ${dataset.label || dataset.name}`}
                    title="Remove this file from the session"
                  >
                    <Trash2 size={12} style={{ color: 'var(--danger-text)' }} />
                  </button>
                )}
                {dataset.profile ? (
                  <span className="badge badge-success">
                    <span className="badge-dot" aria-hidden="true" /> Ready
                  </span>
                ) : (
                  <span className="badge badge-neutral">Uploaded</span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {datasets.length === 0 && !busy && (
        <div className="info-strip" style={{ marginTop: 16, marginBottom: 0 }}>
          <Database size={15} />
          <span>
            {isOrganization ? (
              <>
                <strong>Tip:</strong> add your authoritative file first (e.g. academic register), then the files to
                check against it (e.g. ID cards, hostel list).
              </>
            ) : (
              <>
                <strong>Tip:</strong> upload both a baseline (source) and a comparison (target) dataset
                to unlock the reconciliation engine.
              </>
            )}
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

      {drawerFile && (
        <ProfilingQuarantineDrawer
          projectId={project.id}
          fileId={drawerFile.id}
          filename={drawerFile.name}
          worksheet={drawerFile.worksheet ?? null}
          isOpen={Boolean(drawerFile)}
          onClose={() => setDrawerFile(null)}
        />
      )}
    </div>
  );
};
