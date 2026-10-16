import React, { useMemo, useState } from 'react';
import type {
  Project,
  PreprocessingResult,
  VerificationRequest,
  VerificationResponse,
  VerificationRun,
} from '../types';
import { api } from '../services/api';
import {
  Play,
  Sliders,
  AlertCircle,
  AlertTriangle,
  Check,
  GitCompareArrows,
  KeyRound,
} from 'lucide-react';

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
  const targetProfile = datasets.find((d) => d.id === targetId)?.profile;

  const keyColumns = useMemo(
    () =>
      keyColumnInput
        .split(',')
        .map((k) => k.trim())
        .filter((k) => k.length > 0),
    [keyColumnInput]
  );

  // Columns present (by normalized name) in both selected datasets.
  const matchedColumns = useMemo(() => {
    if (!sourceProfile || !targetProfile) return null;
    const targetNames = new Set(targetProfile.columns.map((c) => c.normalized_name));
    return sourceProfile.columns
      .map((c) => c.normalized_name)
      .filter((name) => targetNames.has(name));
  }, [sourceProfile, targetProfile]);

  // Key columns that are not present in the matched column set.
  const unmatchedKeyColumns = useMemo(() => {
    if (!matchedColumns) return [];
    const matched = new Set(matchedColumns);
    return keyColumns.filter((k) => !matched.has(k));
  }, [matchedColumns, keyColumns]);

  const toggleColumnInKeys = (column: string) => {
    const next = keyColumns.includes(column)
      ? keyColumns.filter((k) => k !== column)
      : [...keyColumns, column];
    setKeyColumnInput(next.join(', '));
  };

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
    if (keyColumns.length === 0) {
      setError('Please specify at least one key column for record matching.');
      return;
    }

    setError(null);
    setExecuting(true);

    const payload: VerificationRequest = {
      source_file_id: sourceId,
      target_file_id: targetId,
      key_columns: keyColumns,
      numeric_tolerance: numericTolerance,
      ignore_case: ignoreCase,
      ignore_whitespace: ignoreWhitespace,
      include_identical: true,
    };

    try {
      if (persistRun) {
        const run = await api.createVerificationRun(project.id, payload);
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

  const sourceColumns = sourceProfile?.columns.map((c) => c.normalized_name) ?? [];

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h3 className="card-title">
            <Sliders size={19} /> Verification rules
          </h3>
          <p className="card-description">
            Define the matching keys, tolerances, and comparison rules between the selected
            datasets.
          </p>
        </div>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleExecute}>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label" htmlFor="source-dataset">
              Baseline dataset (source)
            </label>
            <select
              id="source-dataset"
              className="form-select"
              value={sourceId}
              onChange={(e) => setSourceId(e.target.value)}
              required
            >
              <option value="">Select source dataset…</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="target-dataset">
              Comparison dataset (target)
            </label>
            <select
              id="target-dataset"
              className="form-select"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              required
            >
              <option value="">Select target dataset…</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="key-columns">
            <span className="row" style={{ display: 'inline-flex', gap: 6 }}>
              <KeyRound size={13} /> Matching key columns <span className="text-dim">(comma separated)</span>
            </span>
          </label>
          <input
            id="key-columns"
            type="text"
            className="form-input"
            placeholder="e.g. account_id, transaction_id"
            value={keyColumnInput}
            onChange={(e) => setKeyColumnInput(e.target.value)}
            required
          />
          <span className="form-hint">
            Primary identifier or composite keys used to pair records between datasets.
          </span>
        </div>

        {sourceColumns.length > 0 && (
          <div className="form-group">
            <span className="form-hint" style={{ marginBottom: 8 }}>
              Source columns — click to toggle them as matching keys:
            </span>
            <div className="chip-list">
              {sourceColumns.map((column) => {
                const selected = keyColumns.includes(column);
                const isMatched = matchedColumns === null || matchedColumns.includes(column);
                return (
                  <button
                    key={column}
                    type="button"
                    className={`chip ${selected ? 'selected' : ''}`}
                    onClick={() => toggleColumnInKeys(column)}
                    title={
                      isMatched
                        ? 'Present in both datasets'
                        : 'Only present in the source dataset'
                    }
                  >
                    {selected && <Check size={12} />}
                    {column}
                    {!isMatched && <AlertTriangle size={11} className="text-warning" />}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {matchedColumns !== null && (
          <div className="info-strip">
            <GitCompareArrows size={15} />
            <span>
              <strong>{matchedColumns.length}</strong> column
              {matchedColumns.length === 1 ? '' : 's'} auto-matched between the selected datasets.
              {matchedColumns.length === 0 && ' No shared columns were detected — verify your file selections.'}
              {unmatchedKeyColumns.length > 0 && (
                <>
                  {' '}
                  Key column{unmatchedKeyColumns.length === 1 ? '' : 's'}{' '}
                  <strong>{unmatchedKeyColumns.join(', ')}</strong> not found in both schemas.
                </>
              )}
            </span>
          </div>
        )}

        <div className="config-grid">
          <div className="form-group">
            <label className="form-label" htmlFor="numeric-tolerance">
              Numeric tolerance (absolute difference)
            </label>
            <input
              id="numeric-tolerance"
              type="number"
              step="any"
              min="0"
              className="form-input"
              value={numericTolerance}
              onChange={(e) => setNumericTolerance(parseFloat(e.target.value) || 0)}
            />
            <span className="form-hint">
              Values within this tolerance are treated as equal. Use 0 for exact comparison.
            </span>
          </div>

          <div className="switch-stack">
            <label className="switch">
              <input
                type="checkbox"
                checked={ignoreWhitespace}
                onChange={(e) => setIgnoreWhitespace(e.target.checked)}
              />
              <span className="switch-track" aria-hidden="true" />
              <span className="switch-label">
                Ignore whitespace
                <span className="switch-sub">Trim leading and trailing spaces before comparing</span>
              </span>
            </label>

            <label className="switch">
              <input
                type="checkbox"
                checked={ignoreCase}
                onChange={(e) => setIgnoreCase(e.target.checked)}
              />
              <span className="switch-track" aria-hidden="true" />
              <span className="switch-label">
                Ignore string case
                <span className="switch-sub">Treat "Active" and "active" as equal</span>
              </span>
            </label>

            <label className="switch">
              <input
                type="checkbox"
                checked={persistRun}
                onChange={(e) => setPersistRun(e.target.checked)}
              />
              <span className="switch-track" aria-hidden="true" />
              <span className="switch-label">
                Save persistent audit run
                <span className="switch-sub">Stores results in audit history and enables exports</span>
              </span>
            </label>
          </div>
        </div>

        <button
          type="submit"
          className="btn btn-primary btn-lg btn-block"
          disabled={executing || datasets.length < 2}
          style={{ marginTop: 8 }}
        >
          {executing ? (
            <>
              <span className="spinner on-primary" aria-hidden="true" /> Reconciling datasets…
            </>
          ) : (
            <>
              <Play size={17} /> Execute reconciliation
            </>
          )}
        </button>
        {!persistRun && (
          <span className="form-hint" style={{ textAlign: 'center', marginTop: 8 }}>
            Without a persistent run, results can be reviewed on screen but not exported or listed
            in audit history.
          </span>
        )}
      </form>
    </div>
  );
};
