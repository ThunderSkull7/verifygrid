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
  onFileUploaded: (file: SourceFile, profile?: PreprocessingResult, contentHash?: string) => void;
  datasets: UploadedDataset[];
  mode?: VerificationMode;
  /** Batch 2: editable labels / explicit roles (organization mode). */
  onLabelChange?: (fileId: string, label: string) => void;
  onRoleChange?: (fileId: string, isPrimary: boolean) => void;
  onRemoveFile?: (fileId: string) => void;
  /** Batch 7: explicit XLSX worksheet selection per file (null = deselect). */
  onWorksheetChange?: (fileId: string, sheet: string | null) => void;
  /** Batch 7: Single vs Multiple authoritative sources setup. */
  multiPrimary?: boolean;
  onMultiPrimaryChange?: (enabled: boolean) => void;
  /** Batch 7: explicit header row selection per file. */
  onHeaderRowChange?: (fileId: string, headerRow: number | null) => void;
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
  multiPrimary = false,
  onMultiPrimaryChange,
  onHeaderRowChange,
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

  const handleSetPrimary = (targetId: string) => {
    if (!multiPrimary) {
      // Single-source mode: exactly one primary source
      datasets.forEach((d) => {
        if (d.id === targetId) {
          onRoleChange?.(d.id, true);
        } else if (d.isPrimary) {
          onRoleChange?.(d.id, false);
        }
      });
    } else {
      // Multiple-source mode: toggle independently
      onRoleChange?.(targetId, true);
    }
  };

  const computeFileHash = async (file: File): Promise<string> => {
    try {
      if (typeof crypto !== 'undefined' && crypto.subtle) {
        const buffer = await file.arrayBuffer();
        const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
      }
    } catch {
      // Fallback if subtle crypto is unsupported
    }
    return '';
  };

  const uploadAndProfileOne = async (file: File, contentHash?: string) => {
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

      onFileUploaded(sourceFile, preprocessed, contentHash);
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
  const uploadMany = async (items: { file: File; hash: string }[]) => {
    setError(null);
    setFailedFiles([]);
    let succeeded = 0;
    for (let i = 0; i < items.length; i += 1) {
      const { file, hash } = items[i];
      setUploadProgress(`File ${i + 1} of ${items.length}`);
      const ok = await uploadAndProfileOne(file, hash);
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

  const handleFiles = async (files: File[]) => {
    const supported = files.filter((f) => /\.(csv|xlsx)$/i.test(f.name));
    const unsupported = files.filter((f) => !/\.(csv|xlsx)$/i.test(f.name));
    if (unsupported.length > 0) {
      setFailedFiles((prev) => [
        ...prev,
        ...unsupported.map((f) => ({
          filename: f.name,
          message: 'Only CSV and XLSX spreadsheet files are supported.',
        })),
      ]);
    }
    if (supported.length === 0) return;

    // Batch 8: Content-hash duplicate detection.
    // Filename similarity or file size alone never blocks upload.
    const toUpload: { file: File; hash: string }[] = [];
    for (const f of supported) {
      const hash = await computeFileHash(f);
      if (hash) {
        const existingDuplicate = datasets.find((d) => d.contentHash && d.contentHash === hash);
        if (existingDuplicate) {
          setFailedFiles((prev) => [
            ...prev,
            {
              filename: f.name,
              message: `Identical contents to "${existingDuplicate.label || existingDuplicate.name}". To replace it, remove the existing file first.`,
            },
          ]);
          continue;
        }
      }
      toUpload.push({ file: f, hash });
    }

    if (toUpload.length === 0) return;
    if (isOrganization && toUpload.length > 1) {
      void uploadMany(toUpload);
    } else {
      void uploadAndProfileOne(toUpload[0].file, toUpload[0].hash);
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
            {isOrganization ? 'Upload files & check data' : 'Upload spreadsheets & check data'}
          </h3>
          <p className="card-description">
            {isOrganization
              ? 'Add your CSV or Excel files (e.g. academic register, hostel allocation, ID card export). Each file is checked for data quality before any records are compared.'
              : 'Upload CSV or Excel files to check column names, count rows, and find potential matching keys before comparing.'}
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
        aria-label={isOrganization ? 'Upload one or more CSV or Excel files' : 'Upload spreadsheet file'}
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
              ? 'Checking spreadsheet…'
              : isOrganization
                ? 'Drop your CSV or Excel files here'
                : 'Drop a CSV or Excel file here'}
        </h4>
        <p className="dropzone-hint">
          or <span className="link-accent">browse local files</span>
          {isOrganization ? ' — you can select several files at once' : ''} — up to 100,000 data rows per
          file
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
            Checking columns &amp; data format
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
              Check Data &amp; Review Items
            </button>
            <span className="badge badge-success">
              <span className="badge-dot" aria-hidden="true" /> Checked
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
            <h5 className="schema-title">Detected columns &amp; data types</h5>
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

      {isOrganization && (
        <div
          className="source-mode-panel card"
          style={{
            marginTop: 16,
            marginBottom: 16,
            padding: '14px 16px',
            backgroundColor: 'var(--bg-subtle, rgba(255,255,255,0.02))',
            border: '1px solid var(--border-color, rgba(255,255,255,0.08))',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <Database size={16} className="text-accent" />
            <strong style={{ fontSize: '0.92rem' }}>Authoritative source setup</strong>
          </div>
          <p className="text-dim" style={{ fontSize: '0.82rem', margin: '0 0 12px 0' }}>
            Choose whether comparison relies on one main file or multiple authoritative files before assigning file roles below:
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 10 }}>
            <label
              className={`setup-mode-card ${!multiPrimary ? 'selected' : ''}`}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 10,
                padding: '10px 12px',
                borderRadius: 'var(--radius-sm, 6px)',
                border: !multiPrimary ? '1px solid var(--accent, #3b82f6)' : '1px solid var(--border-color, rgba(255,255,255,0.1))',
                backgroundColor: !multiPrimary ? 'var(--accent-subtle, rgba(59,130,246,0.08))' : 'transparent',
                cursor: 'pointer',
              }}
            >
              <input
                type="radio"
                name="authoritative-source-mode"
                checked={!multiPrimary}
                onChange={() => onMultiPrimaryChange?.(false)}
                style={{ marginTop: 3 }}
              />
              <div>
                <strong style={{ fontSize: '0.88rem', display: 'block' }}>Single authoritative source (default)</strong>
                <span className="text-dim" style={{ fontSize: '0.78rem', lineHeight: 1.35, display: 'block', marginTop: 2 }}>
                  Exactly one main file to trust (e.g. Academic Register). All other files are checked against it.
                </span>
              </div>
            </label>
            <label
              className={`setup-mode-card ${multiPrimary ? 'selected' : ''}`}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 10,
                padding: '10px 12px',
                borderRadius: 'var(--radius-sm, 6px)',
                border: multiPrimary ? '1px solid var(--accent, #3b82f6)' : '1px solid var(--border-color, rgba(255,255,255,0.1))',
                backgroundColor: multiPrimary ? 'var(--accent-subtle, rgba(59,130,246,0.08))' : 'transparent',
                cursor: 'pointer',
              }}
            >
              <input
                type="radio"
                name="authoritative-source-mode"
                checked={multiPrimary}
                onChange={() => onMultiPrimaryChange?.(true)}
                style={{ marginTop: 3 }}
              />
              <div>
                <strong style={{ fontSize: '0.88rem', display: 'block' }}>Multiple authoritative sources</strong>
                <span className="text-dim" style={{ fontSize: '0.78rem', lineHeight: 1.35, display: 'block', marginTop: 2 }}>
                  Multiple files can be authoritative. Each field can have its own authoritative source (e.g. SIS for student info, Hostel for allocations).
                </span>
              </div>
            </label>
          </div>
        </div>
      )}

      {datasets.length > 0 && (
        <div className="file-list">
          <div className="file-list-title">
            {isOrganization ? 'Session files' : 'Session spreadsheets'} ({datasets.length})
            {isOrganization
              ? multiPrimary
                ? ' — mark one or more authoritative files; assign field ownership in Step 2'
                : ' — mark one file as the main file to trust; the rest are checked against it'
              : ' — upload at least two to compare'}
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
                  {/* Batch 7: explicit worksheet selection for XLSX workbooks. */}
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
                  {/* Batch 7: explicit header row selection when candidate rows exist */}
                  {(dataset.profile?.header_row_candidates?.length ?? 0) > 1 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
                      <span className="text-dim" style={{ fontSize: '0.78rem' }}>Header row:</span>
                      <select
                        className="form-select"
                        value={dataset.headerRow ?? dataset.profile?.detected_header_row ?? 1}
                        onChange={(e) => onHeaderRowChange?.(dataset.id, parseInt(e.target.value, 10))}
                        aria-label={`Header row for ${dataset.label || dataset.name}`}
                        style={{ fontSize: '0.78rem', padding: '2px 6px', maxWidth: 220 }}
                      >
                        {dataset.profile!.header_row_candidates!.map((cand) => (
                          <option key={cand.row_number} value={cand.row_number}>
                            Row {cand.row_number} ({cand.columns.length} columns){cand.is_likely_header ? ' — Recommended' : ''}
                          </option>
                        ))}
                      </select>
                      {dataset.profile?.detected_header_row && dataset.profile.detected_header_row > 1 && (
                        <span className="badge badge-neutral" style={{ fontSize: '0.72rem' }} title="Row 1 appeared to be a title banner; headers were automatically detected at Row 2">
                          Auto-detected Row {dataset.profile.detected_header_row}
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
                        onClick={() => handleSetPrimary(dataset.id)}
                        aria-pressed={dataset.isPrimary}
                        title={
                          multiPrimary
                            ? "Authoritative source — this file provides authoritative values for fields it owns"
                            : "Main file to trust — authoritative values other files are checked against"
                        }
                      >
                        <Star size={12} /> {multiPrimary ? 'Authoritative source' : 'Main file to trust'}
                      </button>
                      <button
                        type="button"
                        className={`btn btn-xs ${dataset.isPrimary ? 'btn-secondary' : 'btn-primary'}`}
                        onClick={() => onRoleChange?.(dataset.id, false)}
                        aria-pressed={!dataset.isPrimary}
                        title="File to check — its values are compared with the authoritative file"
                      >
                        File to check
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
                  title="Inspect spreadsheet metrics and review flagged items"
                >
                  <ShieldAlert size={12} className="text-accent" />
                  Check Data
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
                <strong>Tip:</strong> add your main file to trust first (e.g. academic register), then the files to
                check against it (e.g. ID cards, hostel list).
              </>
            ) : (
              <>
                <strong>Tip:</strong> upload both a main file to trust and a comparison file
                to start comparing records.
              </>
            )}
          </span>
        </div>
      )}

      {profileResult && profileResult.issues.length > 0 && (
        <div className="info-strip" style={{ marginTop: 16, marginBottom: 0 }}>
          <ListChecks size={15} />
          <span>
            {profileResult.issues.length} item
            {profileResult.issues.length === 1 ? '' : 's'} needing attention found during checking (e.g.{' '}
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
