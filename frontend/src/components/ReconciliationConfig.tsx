import React, { useState } from 'react';
import type { Project, PreprocessingResult, VerificationRequest, VerificationResponse, VerificationRun } from '../types';
import { api } from '../services/api';
import { Play, Sliders, AlertCircle } from 'lucide-react';

interface ReconciliationConfigProps {
  project: Project;
  datasets: { id: string; name: string; profile?: PreprocessingResult }[];
  onVerificationComplete: (response: VerificationResponse, run?: VerificationRun) => void;
}

export const ReconciliationConfig: React.FC<ReconciliationConfigProps> = ({
  project,
  datasets,
  onVerificationComplete,
}) => {
  const [sourceId, setSourceId] = useState<string>(datasets[0]?.id || '');
  const [targetId, setTargetId] = useState<string>(datasets[1]?.id || '');
  const [keyColumnInput, setKeyColumnInput] = useState<string>('id');
  const [numericTolerance, setNumericTolerance] = useState<number>(0.0);
  const [ignoreCase, setIgnoreCase] = useState<boolean>(false);
  const [ignoreWhitespace, setIgnoreWhitespace] = useState<boolean>(true);
  const [persistRun, setPersistRun] = useState<boolean>(true);
  const [executing, setExecuting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const sourceProfile = datasets.find((d) => d.id === sourceId)?.profile;

  const handleExecute = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceId || !targetId) {
      setError('Please select both a baseline and a comparison dataset.');
      return;
    }
    if (sourceId === targetId) {
      setError('Source and target datasets must be different files.');
      return;
    }

    const keyCols = keyColumnInput
      .split(',')
      .map((k) => k.trim())
      .filter((k) => k.length > 0);

    if (keyCols.length === 0) {
      setError('Please specify at least one key column for record matching.');
      return;
    }

    setError(null);
    setExecuting(true);

    const payload: VerificationRequest = {
      source_file_id: sourceId,
      target_file_id: targetId,
      key_columns: keyCols,
      numeric_tolerance: numericTolerance,
      ignore_case: ignoreCase,
      ignore_whitespace: ignoreWhitespace,
      include_identical: true,
    };

    try {
      if (persistRun) {
        // Execute persistent run
        const run = await api.createVerificationRun(project.id, payload);
        // Also call on-demand verify for immediate client view with full items
        const response = await api.verifyProjectFiles(project.id, payload);
        onVerificationComplete(response, run);
      } else {
        const response = await api.verifyProjectFiles(project.id, payload);
        onVerificationComplete(response);
      }
    } catch (err: any) {
      setError(err.message || 'Reconciliation execution failed');
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h3 className="card-title">
            <Sliders size={20} /> Configure Verification & Reconciliation
          </h3>
          <p className="card-description">
            Specify matching key columns, numeric tolerances, and comparison rules between two uploaded datasets.
          </p>
        </div>
      </div>

      {error && (
        <div className="alert-box alert-error">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleExecute}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div className="form-group">
            <label className="form-label">Baseline Dataset (Source File)</label>
            <select
              className="form-select"
              value={sourceId}
              onChange={(e) => setSourceId(e.target.value)}
              required
            >
              <option value="">Select source dataset...</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Comparison Dataset (Target File)</label>
            <select
              className="form-select"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              required
            >
              <option value="">Select target dataset...</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">
            Matching Key Columns (comma separated)
          </label>
          <input
            type="text"
            className="form-input"
            placeholder="e.g. account_id, transaction_id"
            value={keyColumnInput}
            onChange={(e) => setKeyColumnInput(e.target.value)}
            required
          />
          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: 4, display: 'block' }}>
            Primary identifier or composite keys used to pair records between datasets.
          </span>
        </div>

        {/* Available columns hints */}
        {sourceProfile && (
          <div style={{ marginBottom: 16 }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Source normalized columns: {sourceProfile.columns.map((c) => c.normalized_name).join(', ')}
            </span>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 20 }}>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Numeric Tolerance (Abs Diff)</label>
            <input
              type="number"
              step="any"
              min="0"
              className="form-input"
              value={numericTolerance}
              onChange={(e) => setNumericTolerance(parseFloat(e.target.value) || 0)}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 8 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.875rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={ignoreWhitespace}
                onChange={(e) => setIgnoreWhitespace(e.target.checked)}
              />
              Ignore Whitespace
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.875rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={ignoreCase}
                onChange={(e) => setIgnoreCase(e.target.checked)}
              />
              Ignore String Case
            </label>
          </div>

          <div style={{ display: 'flex', alignItems: 'center' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.875rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={persistRun}
                onChange={(e) => setPersistRun(e.target.checked)}
              />
              Save Persistent Audit Run
            </label>
          </div>
        </div>

        <button
          type="submit"
          className="btn btn-primary"
          style={{ width: '100%', padding: '12px 20px', fontSize: '0.95rem' }}
          disabled={executing || datasets.length < 2}
        >
          {executing ? (
            'Reconciling Datasets...'
          ) : (
            <>
              <Play size={18} /> Execute Reconciliation Engine
            </>
          )}
        </button>
      </form>
    </div>
  );
};
