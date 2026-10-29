import React, { useCallback, useEffect, useState } from 'react';
import {
  BookmarkPlus,
  CheckCircle2,
  FileInput,
  Pencil,
  RefreshCw,
  Save,
  Trash,
  XCircle,
} from 'lucide-react';
import { api } from '../services/api';
import type {
  TemplateApplyResponse,
  TemplateConfigurationV1,
  TemplateValidationIssue,
  UploadedDataset,
  VerificationTemplate,
} from '../types';

interface TemplatePanelProps {
  mode: 'organization' | 'financial';
  project: { id: string };
  uploadedDatasets: UploadedDataset[];
  /** Current reusable configuration derived from wizard state (org mode only).
   *  Returns null when the setup is not yet captureable (e.g. fewer than 2 files). */
  getCurrentConfiguration: () => TemplateConfigurationV1 | null;
  /** Called after a template applies successfully: populates wizard state from
   *  the validated effective configuration. `bindings` maps slot alias -> file id. */
  onTemplateApplied: (
    config: TemplateConfigurationV1,
    report: TemplateApplyResponse,
    bindings: Record<string, string>,
  ) => void;
}

/**
 * Batch 13: reusable personal-template workflow.
 *
 * - Explicit per-slot binding: every template source slot is bound to a chosen
 *   uploaded file (no positional guessing). Bindings are only *suggestions* —
 *   the backend apply endpoint performs the authoritative validation of
 *   worksheets, columns, identity keys and configuration invariants.
 * - Personal templates only: organization sharing stays disabled server-side.
 * - Management: rename / edit description (details only), update the saved
 *   configuration (separate, explicitly confirmed action), save as new, and
 *   delete behind an explicit confirmation.
 * - Applying never executes verification; execution continues through the
 *   existing wizard flow.
 */
export const TemplatePanel: React.FC<TemplatePanelProps> = ({
  mode,
  project,
  uploadedDatasets,
  getCurrentConfiguration,
  onTemplateApplied,
}) => {
  // --- Hooks (registered unconditionally, same order on every render) -------

  const [templates, setTemplates] = useState<VerificationTemplate[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');
  const [slotBindings, setSlotBindings] = useState<Record<string, string>>({});

  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [issues, setIssues] = useState<TemplateValidationIssue[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [report, setReport] = useState<TemplateApplyResponse | null>(null);

  const [saveOpen, setSaveOpen] = useState<boolean>(false);
  const [saveName, setSaveName] = useState<string>('');
  const [saveDescription, setSaveDescription] = useState<string>('');

  const [detailsOpen, setDetailsOpen] = useState<boolean>(false);
  const [detailsName, setDetailsName] = useState<string>('');
  const [detailsDescription, setDetailsDescription] = useState<string>('');

  const [configUpdateOpen, setConfigUpdateOpen] = useState<boolean>(false);

  const [deleteOpen, setDeleteOpen] = useState<boolean>(false);

  const modeIsOrg = mode === 'organization';

  const loadTemplates = useCallback(async () => {
    try {
      const list = await api.listTemplates('organization');
      setTemplates(list);
    } catch (err: any) {
      setError(err.message || 'Failed to load templates.');
    }
  }, []);

  useEffect(() => {
    if (modeIsOrg) {
      void loadTemplates();
    }
  }, [modeIsOrg, loadTemplates]);

  // --- Helpers (pure) -------------------------------------------------------

  const issueText = (issue: TemplateValidationIssue): string => {
    const scope = issue.slot ? `[${issue.slot}] ` : issue.field ? `[${issue.field}] ` : '';
    return `${scope}${issue.message}`;
  };

  const resetFeedback = () => {
    setMessage(null);
    setError(null);
    setIssues([]);
    setWarnings([]);
    setReport(null);
  };

  const applyErrorFeedback = (err: any) => {
    const detail = (err as {
      detail?: {
        validation_report?: {
          issues?: TemplateValidationIssue[];
          warnings?: string[];
        };
      };
    }).detail;
    const blocking = detail?.validation_report?.issues ?? [];
    const warningList = detail?.validation_report?.warnings ?? [];
    if (blocking.length > 0) {
      setIssues(blocking);
      setWarnings(warningList);
      setReport(null);
      setMessage(null);
      setError('Template application blocked — fix the issues below, then apply again.');
    } else {
      setIssues([]);
      setWarnings([]);
      setError(err.message || 'Failed to apply template.');
    }
  };

  // --- Early return after all hooks ----------------------------------------

  if (!modeIsOrg) return null; // Financial Auditing stays separate

  const selectedTemplate = templates.find((t) => t.id === selectedId) ?? null;
  const slots = selectedTemplate?.configuration?.sources ?? [];
  const unassignedSlots = slots
    .filter((slot) => !slotBindings[slot.alias])
    .map((slot) => slot.alias);
  const assignedCount = slots.length - unassignedSlots.length;

  const boundFileIds = Object.values(slotBindings).filter(Boolean);
  const duplicatedFileIds = Array.from(
    boundFileIds.reduce((acc, id) => {
      acc.set(id, (acc.get(id) ?? 0) + 1);
      return acc;
    }, new Map<string, number>()),
  )
    .filter(([, count]) => count > 1)
    .map(([id]) => id);

  const fileName = (fileId: string): string =>
    uploadedDatasets.find((d) => d.id === fileId)?.name || `${fileId.slice(0, 8)}…`;

  const selectTemplate = (templateId: string) => {
    setSelectedId(templateId);
    resetFeedback();
    setSaveOpen(false);
    setDetailsOpen(false);
    setConfigUpdateOpen(false);
    setDeleteOpen(false);
    const nextBindings: Record<string, string> = {};
    const tpl = templates.find((t) => t.id === templateId);
    tpl?.configuration.sources.forEach((slot) => {
      nextBindings[slot.alias] = '';
    });
    setSlotBindings(nextBindings);
  };

  const bindSlot = (alias: string, fileId: string) => {
    setSlotBindings((prev) => {
      const next = { ...prev };
      if (fileId) {
        next[alias] = fileId;
      } else {
        delete next[alias];
      }
      return next;
    });
  };

  // --- Apply (backend revalidates every binding) ----------------------------

  const handleApply = async () => {
    if (!selectedId || !selectedTemplate) return;
    if (slots.length < 2) {
      setError('This template has fewer than two source slots and cannot be applied.');
      return;
    }
    if (unassignedSlots.length > 0) {
      setError(
        `Assign a file to every template slot before applying. Unassigned: ${unassignedSlots.join(', ')}.`,
      );
      return;
    }

    setBusy('apply');
    resetFeedback();
    try {
      const resp = await api.applyTemplate(selectedId, {
        project_id: project.id,
        sources: slots.map((slot) => ({
          slot: slot.alias,
          file_id: slotBindings[slot.alias],
        })),
      });
      setReport(resp);
      setWarnings(resp.validation_report?.warnings ?? []);
      setMessage(
        `Template '${selectedTemplate.name}' validated successfully. Review the suggested mappings below.`,
      );
      // Hand the validated bindings back so the wizard can populate the right
      // dataset for each slot (mappings stay 'suggested' and are rechecked).
      onTemplateApplied(selectedTemplate.configuration, resp, { ...slotBindings });
      await loadTemplates();
    } catch (err: any) {
      applyErrorFeedback(err);
    } finally {
      setBusy(null);
    }
  };

  // --- Create a NEW template from the current wizard configuration ----------

  const handleCreate = async () => {
    const config = getCurrentConfiguration();
    if (!config) {
      setError('Upload and map at least 2 files before saving a template.');
      return;
    }
    const name = saveName.trim();
    if (!name) {
      setError('Enter a template name.');
      return;
    }
    setBusy('create');
    resetFeedback();
    try {
      const created = await api.createTemplate({
        name,
        description: saveDescription.trim() || null,
        mode: 'organization',
        configuration: config,
      });
      setMessage(`Saved new template '${created.name}'.`);
      setSaveName('');
      setSaveDescription('');
      setSaveOpen(false);
      await loadTemplates();
    } catch (err: any) {
      setError(err.message || 'Failed to save template.');
    } finally {
      setBusy(null);
    }
  };

  // --- Rename / edit description only (never touches the configuration) -----

  const openDetails = () => {
    if (!selectedTemplate) return;
    resetFeedback();
    setSaveOpen(false);
    setConfigUpdateOpen(false);
    setDeleteOpen(false);
    setDetailsName(selectedTemplate.name);
    setDetailsDescription(selectedTemplate.description ?? '');
    setDetailsOpen((open) => !open);
  };

  const handleDetailsSave = async () => {
    if (!selectedId) return;
    const name = detailsName.trim();
    if (!name) {
      setError('Enter a valid template name.');
      return;
    }
    setBusy('details');
    resetFeedback();
    try {
      const updated = await api.updateTemplate(selectedId, {
        name,
        // '' clears the description; the backend stores empty as NULL.
        description: detailsDescription.trim(),
      });
      setMessage(`Updated template details for '${updated.name}'.`);
      setDetailsOpen(false);
      await loadTemplates();
    } catch (err: any) {
      setError(err.message || 'Failed to update template details.');
    } finally {
      setBusy(null);
    }
  };

  // --- Update the saved configuration (explicit, confirmed overwrite) -------

  const openConfigUpdate = () => {
    if (!selectedTemplate) return;
    resetFeedback();
    setSaveOpen(false);
    setDetailsOpen(false);
    setDeleteOpen(false);
    setConfigUpdateOpen((open) => !open);
  };

  const handleConfigUpdate = async () => {
    if (!selectedId || !selectedTemplate) return;
    const config = getCurrentConfiguration();
    if (!config) {
      setError('Upload and map at least 2 files before updating a template.');
      return;
    }
    setBusy('config');
    resetFeedback();
    try {
      const updated = await api.updateTemplate(selectedId, { configuration: config });
      setMessage(
        `Replaced the saved configuration of '${updated.name}'. Name and description were not changed.`,
      );
      setConfigUpdateOpen(false);
      await loadTemplates();
    } catch (err: any) {
      setError(err.message || 'Failed to update template configuration.');
    } finally {
      setBusy(null);
    }
  };

  // --- Delete (explicit confirmation) --------------------------------------

  const handleDelete = async () => {
    if (!selectedId || !selectedTemplate) return;
    setBusy('delete');
    resetFeedback();
    try {
      await api.deleteTemplate(selectedId);
      setDeleteOpen(false);
      // Reset selection first: selectTemplate clears transient feedback, so the
      // success message must be set afterwards (otherwise it is immediately lost).
      selectTemplate('');
      setMessage(`Deleted template '${selectedTemplate.name}'.`);
      await loadTemplates();
    } catch (err: any) {
      setError(err.message || 'Failed to delete template.');
    } finally {
      setBusy(null);
    }
  };

  const workspaceReady = Boolean(getCurrentConfiguration());

  // --- Render ---------------------------------------------------------------

  return (
    <div
      style={{
        marginTop: 16,
        padding: '14px 16px',
        backgroundColor: 'var(--bg-subtle)',
        borderRadius: 'var(--radius-sm)',
        border: '1px solid var(--border-subtle, transparent)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <FileInput size={16} className="text-accent" />
        <strong style={{ fontSize: '0.9rem' }}>Reusable verification templates</strong>
        <span className="text-dim" style={{ fontSize: '0.75rem' }}>
          personal templates — validate columns, worksheets &amp; keys against your new uploads
        </span>
      </div>

      {/* Template picker + primary actions */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <select
          value={selectedId}
          onChange={(e) => selectTemplate(e.target.value)}
          className="input"
          style={{ minWidth: 260, maxWidth: 420 }}
          aria-label="Choose a saved template"
        >
          <option value="">— Start without a template —</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} ({t.source_count} files, v{t.config_version})
            </option>
          ))}
        </select>

        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={!selectedId || busy === 'apply' || uploadedDatasets.length < 2}
          onClick={() => void handleApply()}
        >
          {busy === 'apply' ? 'Validating…' : 'Apply to uploaded files'}
        </button>

        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={busy === 'create'}
          onClick={() => {
            resetFeedback();
            setDetailsOpen(false);
            setConfigUpdateOpen(false);
            setDeleteOpen(false);
            setSaveOpen((open) => !open);
          }}
        >
          <BookmarkPlus size={14} /> Save as new template…
        </button>

        {selectedId && selectedTemplate && (
          <>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={busy === 'details'}
              onClick={openDetails}
            >
              <Pencil size={14} /> Rename / description…
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={busy === 'config'}
              onClick={openConfigUpdate}
            >
              <RefreshCw size={14} /> Update saved configuration…
            </button>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              disabled={busy === 'delete'}
              onClick={() => {
                resetFeedback();
                setSaveOpen(false);
                setDetailsOpen(false);
                setConfigUpdateOpen(false);
                setDeleteOpen((open) => !open);
              }}
            >
              <Trash size={14} /> Delete…
            </button>
          </>
        )}
      </div>

      {/* Save-as-new panel */}
      {saveOpen && (
        <div style={{ marginTop: 12, padding: 10, border: '1px solid var(--border-subtle)', borderRadius: 4 }}>
          <strong style={{ fontSize: '0.82rem' }}>Save current setup as a NEW template</strong>
          <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              className="input"
              style={{ maxWidth: 280 }}
              placeholder="Template name"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              maxLength={255}
              aria-label="New template name"
            />
            <input
              className="input"
              style={{ maxWidth: 340 }}
              placeholder="Description (optional)"
              value={saveDescription}
              onChange={(e) => setSaveDescription(e.target.value)}
              aria-label="New template description"
            />
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy === 'create' || !workspaceReady}
              onClick={() => void handleCreate()}
            >
              <Save size={14} /> {busy === 'create' ? 'Saving…' : 'Save as new'}
            </button>
          </div>
          {!workspaceReady && (
            <div className="text-dim" style={{ marginTop: 6, fontSize: '0.75rem' }}>
              Upload and map at least 2 files (Steps 1–2) before saving a template of the current setup.
            </div>
          )}
        </div>
      )}

      {/* Rename / description panel (configuration untouched) */}
      {detailsOpen && selectedTemplate && (
        <div style={{ marginTop: 12, padding: 10, border: '1px solid var(--border-subtle)', borderRadius: 4 }}>
          <strong style={{ fontSize: '0.82rem' }}>
            Rename / edit description — configuration of '{selectedTemplate.name}' stays unchanged
          </strong>
          <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              className="input"
              style={{ maxWidth: 280 }}
              placeholder="Template name"
              value={detailsName}
              onChange={(e) => setDetailsName(e.target.value)}
              maxLength={255}
              aria-label="Template name"
            />
            <input
              className="input"
              style={{ maxWidth: 340 }}
              placeholder="Description (optional)"
              value={detailsDescription}
              onChange={(e) => setDetailsDescription(e.target.value)}
              aria-label="Template description"
            />
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy === 'details'}
              onClick={() => void handleDetailsSave()}
            >
              <Save size={14} /> {busy === 'details' ? 'Saving…' : 'Save details'}
            </button>
          </div>
        </div>
      )}

      {/* Update-configuration panel (explicit overwrite confirmation) */}
      {configUpdateOpen && selectedTemplate && (
        <div
          style={{
            marginTop: 12,
            padding: 10,
            border: '1px solid var(--border-critical, var(--border-subtle))',
            borderRadius: 4,
          }}
        >
          <strong style={{ fontSize: '0.82rem' }}>
            Replace the saved configuration of '{selectedTemplate.name}'?
          </strong>
          <p className="text-dim" style={{ fontSize: '0.75rem', margin: '6px 0' }}>
            The template's saved columns, worksheets, keys and options will be overwritten by the
            current wizard setup. Its name and description will NOT change. This cannot be undone.
          </p>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={busy === 'config'}
              onClick={() => setConfigUpdateOpen(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              disabled={busy === 'config' || !workspaceReady}
              onClick={() => void handleConfigUpdate()}
            >
              <RefreshCw size={14} /> {busy === 'config' ? 'Updating…' : 'Replace configuration'}
            </button>
          </div>
          {!workspaceReady && (
            <div className="text-dim" style={{ marginTop: 6, fontSize: '0.75rem' }}>
              Upload and map at least 2 files before replacing a template's configuration.
            </div>
          )}
        </div>
      )}

      {/* Delete confirmation */}
      {deleteOpen && selectedTemplate && (
        <div
          style={{
            marginTop: 12,
            padding: 10,
            border: '1px solid var(--border-critical, var(--border-subtle))',
            borderRadius: 4,
          }}
        >
          <strong style={{ fontSize: '0.82rem' }}>
            Delete template '{selectedTemplate.name}'?
          </strong>
          <p className="text-dim" style={{ fontSize: '0.75rem', margin: '6px 0' }}>
            This permanently removes the saved template. Projects, files and verification results
            are not affected.
          </p>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={busy === 'delete'}
              onClick={() => setDeleteOpen(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              disabled={busy === 'delete'}
              onClick={() => void handleDelete()}
            >
              <Trash size={14} /> {busy === 'delete' ? 'Deleting…' : 'Delete template'}
            </button>
          </div>
        </div>
      )}

      {/* Per-slot binding UI */}
      {selectedTemplate && slots.length > 0 && (
        <div
          style={{
            marginTop: 16,
            padding: 12,
            backgroundColor: 'var(--bg-subtle)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <strong style={{ fontSize: '0.85rem' }}>Source slot bindings</strong>
            <span className="text-dim" style={{ fontSize: '0.75rem' }}>
              {assignedCount} of {slots.length} slot{slots.length === 1 ? '' : 's'} assigned
            </span>
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', margin: '4px 0 10px 0' }}>
            Choose which uploaded file fills each template slot. Validation (worksheet, columns,
            identity keys) always runs on the server when you apply.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {slots.map((slotDef) => {
              const boundFileId = slotBindings[slotDef.alias] || '';
              const isUnassigned = !boundFileId;
              return (
                <div
                  key={slotDef.alias}
                  style={{
                    padding: 8,
                    borderRadius: 4,
                    border: `1px solid ${isUnassigned ? 'var(--border-critical, var(--border-subtle))' : 'var(--border-subtle)'}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <span style={{ fontWeight: 600 }}>{slotDef.alias}</span>
                    {slotDef.label && <span className="text-dim">{slotDef.label}</span>}
                    <span
                      style={{
                        fontSize: '0.68rem',
                        padding: '1px 6px',
                        borderRadius: 999,
                        backgroundColor: slotDef.is_primary ? 'rgba(46, 160, 67, 0.15)' : 'var(--bg-card-hover)',
                        color: slotDef.is_primary ? 'var(--success)' : 'var(--text-dim)',
                      }}
                    >
                      {slotDef.is_primary ? 'primary' : 'secondary'}
                    </span>
                    {isUnassigned && (
                      <span className="text-error" style={{ fontSize: '0.72rem' }}>
                        unassigned
                      </span>
                    )}
                  </div>

                  <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginBottom: 6 }}>
                    Identity key{slotDef.key_columns.length === 1 ? '' : 's'}:{' '}
                    {slotDef.key_columns.join(', ')}
                    {slotDef.sheet_name ? ` · worksheet: ${slotDef.sheet_name}` : ''}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <select
                      value={boundFileId}
                      onChange={(e) => bindSlot(slotDef.alias, e.target.value)}
                      className="input"
                      style={{ minWidth: 280, maxWidth: 420 }}
                      aria-label={`Uploaded file for slot ${slotDef.alias}`}
                    >
                      <option value="">— Select an uploaded file —</option>
                      {uploadedDatasets.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                          {duplicatedFileIds.includes(d.id) ? ' (used in multiple slots)' : ''}
                        </option>
                      ))}
                    </select>
                    {boundFileId && (
                      <span className="text-success" style={{ fontSize: '0.75rem' }}>
                        Bound to {fileName(boundFileId)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {unassignedSlots.length > 0 && (
            <div
              style={{
                marginTop: 10,
                padding: 8,
                borderRadius: 4,
                border: '1px solid var(--border-critical, var(--border-subtle))',
              }}
            >
              <span className="text-error" style={{ fontSize: '0.76rem' }}>
                Unassigned required slot{unassignedSlots.length === 1 ? '' : 's'}:{' '}
                {unassignedSlots.join(', ')}. Assign a file to every slot before applying.
              </span>
            </div>
          )}

          {duplicatedFileIds.length > 0 && (
            <div style={{ marginTop: 8, fontSize: '0.76rem' }}>
              <span className="text-dim">
                Note: the same uploaded file is bound to more than one slot (
                {duplicatedFileIds.map(fileName).join(', ')}). The backend allows this — only do it
                when the files are genuinely identical.
              </span>
            </div>
          )}
        </div>
      )}

      {/* Feedback: success / generic error / structured blocking issues / warnings */}
      {message && (
        <div className="text-success" style={{ marginTop: 10, fontSize: '0.8rem', display: 'flex', gap: 6 }}>
          <CheckCircle2 size={14} /> {message}
        </div>
      )}

      {error && (
        <div className="text-error" style={{ marginTop: 10, fontSize: '0.8rem', display: 'flex', gap: 6 }}>
          <XCircle size={14} /> {error}
        </div>
      )}

      {issues.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <strong style={{ fontSize: '0.8rem' }}>Blocking issues</strong>
          <ul style={{ margin: '4px 0 0 18px', padding: 0, fontSize: '0.78rem' }}>
            {issues.map((issue, idx) => (
              <li key={`${issue.slot ?? issue.field ?? 'general'}-${idx}`} style={{ marginBottom: 4 }}>
                {issue.slot && (
                  <span
                    style={{
                      fontSize: '0.68rem',
                      padding: '1px 6px',
                      borderRadius: 999,
                      backgroundColor: 'var(--bg-card-hover)',
                      marginRight: 6,
                    }}
                  >
                    slot: {issue.slot}
                  </span>
                )}
                {issue.field && (
                  <span
                    style={{
                      fontSize: '0.68rem',
                      padding: '1px 6px',
                      borderRadius: 999,
                      backgroundColor: 'var(--bg-card-hover)',
                      marginRight: 6,
                    }}
                  >
                    {issue.field}
                  </span>
                )}
                {issueText(issue)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {warnings.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <strong style={{ fontSize: '0.8rem' }}>Non-blocking warnings</strong>
          <ul style={{ margin: '4px 0 0 18px', padding: 0, fontSize: '0.78rem' }}>
            {warnings.map((warning, idx) => (
              <li key={`warning-${idx}`} style={{ marginBottom: 2 }}>
                {warning}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report && report.validation_report && (
        <div style={{ marginTop: 8, fontSize: '0.76rem' }}>
          <span className="text-dim">
            Server validation passed: {report.validation_report.blocking ? 'blocking' : 'no blocking issues'};
            {' '}effective keys: {report.effective_request.unified_keys.join(', ') || '—'}.
            Verification has NOT been executed.
          </span>
        </div>
      )}
    </div>
  );
};
