import React, { useCallback, useEffect, useState } from 'react';
import type {
  AggregationConfig,
  DateWindowRule,
  FileColumnMappings,
  TemplateApplyResponse,
  TemplateConfigurationV1,
  UploadedDataset,
  MultiSourceKeyRecommendation,
  MultiSourceVerificationRequest,
  MultiSourceVerificationResponse,
  NumericToleranceRule,
  PredicateOperator,
  PreprocessingResult,
  Project,
  RulePreviewResponse,
  SourceDefinition,
  SourceFile,
  VerificationRun,
  VersionedRuleConfig,
  WhereCondition,
} from '../types';
import { api } from '../services/api';
import {
  buildAllSuggestions,
  buildFallbackPayload,
  buildFieldOwnershipPayload,
  collectCanonicalAttributes,
  computeComparedAttributes,
  computeComparedAttributesMultiPrimary,
  usedColumnsForFile,
} from '../services/columnMapping';
import { FileUploadSection } from './FileUploadSection';
import { ProfilingQuarantineDrawer } from './ProfilingQuarantineDrawer';
import { StatusBadge } from './StatusBadge';
import { TemplatePanel } from './TemplatePanel';
import {
  AlertCircle,
  ArrowRight,
  Calendar,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  Eye,
  FileCheck,
  FileSpreadsheet,
  Filter,
  Info,
  Layers,
  Play,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  Sliders,
  Sparkles,
  Split,
  TableProperties,
  Trash2,
} from 'lucide-react';

export type VerificationMode = 'organization' | 'financial';

interface ReconciliationWizardProps {
  project: Project;
  uploadedDatasets: UploadedDataset[];
  onFileUploaded: (file: SourceFile, profile?: PreprocessingResult) => void;
  onRunCompleted?: (run: VerificationRun) => void;
  /** Presentation mode. 'financial' (default) preserves all existing behaviour, labels
   *  and financial rule configuration. 'organization' renders neutral, institution-
   *  friendly copy and hides finance-specific rule setup. Engine and API are unchanged. */
  mode?: VerificationMode;
  /** Batch 2: editable labels / explicit roles, managed at App level. */
  onLabelChange?: (fileId: string, label: string) => void;
  onRoleChange?: (fileId: string, isPrimary: boolean) => void;
  onRemoveFile?: (fileId: string) => void;
  /** Batch 7: explicit XLSX worksheet selection per file (null = deselect). */
  onWorksheetChange?: (fileId: string, sheet: string | null) => void;
}

type WizardStep = 1 | 2 | 3 | 4 | 5;

const STEPS: { num: 1 | 2 | 3 | 4 | 5; title: string; desc: string; orgTitle: string; orgDesc: string }[] = [
  { num: 1, title: 'Ingestion', desc: 'Upload & Pre-flight', orgTitle: 'Upload', orgDesc: 'Add files & pre-flight' },
  { num: 2, title: 'Blueprint', desc: 'Aliases & Keys', orgTitle: 'Records', orgDesc: 'Names & keys' },
  { num: 3, title: 'Rules', desc: 'Tolerances & Logic', orgTitle: 'Settings', orgDesc: 'Tolerances & logic' },
  { num: 4, title: 'Exception Grid', desc: 'Multi-source Lineage', orgTitle: 'Results', orgDesc: 'Records & differences' },
  { num: 5, title: 'Sign-off', desc: 'Audit & Exports', orgTitle: 'Review', orgDesc: 'Summary & exports' },
];

const DEFAULT_NAMES = ['erp', 'bank', 'gateway', 'pos', 'ledger', 'crm'];

export const ReconciliationWizard: React.FC<ReconciliationWizardProps> = ({
  project,
  uploadedDatasets,
  onFileUploaded,
  onRunCompleted,
  mode = 'financial',
  onLabelChange,
  onRoleChange,
  onRemoveFile,
  onWorksheetChange,
}) => {
  const [currentStep, setCurrentStep] = useState<WizardStep>(1);

  // --- Step 1: Ingestion & Drawer ---
  const [drawerFile, setDrawerFile] = useState<{ id: string; name: string } | null>(null);

  // --- Step 2: Blueprint & Multi-source Mapping ---
  // Map file_id -> alias name
  const [sourceAliases, setSourceAliases] = useState<Record<string, string>>({});
  // Primary baseline file_id
  const [primaryFileId, setPrimaryFileId] = useState<string>('');
  // Unified join key name(s)
  const [unifiedKeys, setUnifiedKeys] = useState<string[]>(['id']);
  // Key columns per file_id: Record<file_id, string[]>
  const [fileKeyColumns, setFileKeyColumns] = useState<Record<string, string[]>>({});
  // Batch 3 (organization mode): canonical-attribute -> column mapping state per file.
  const [columnMappings, setColumnMappings] = useState<Record<string, FileColumnMappings>>({});
  // Batch 4 (organization mode): ordered fallback matching keys. Each entry is a list
  // of canonical attribute names; only complete, fully-mapped definitions are sent.
  const [fallbackKeys, setFallbackKeys] = useState<string[][]>([]);
  // Batch 5 (organization mode): explicit multi-primary opt-in and per-attribute
  // ownership ({canonical attribute -> owning file id}). Only validated entries
  // are sent to the engine.
  const [multiPrimary, setMultiPrimary] = useState(false);
  const [fieldOwners, setFieldOwners] = useState<Record<string, string>>({});
  // Key recommendations from backend
  const [recommendations, setRecommendations] = useState<MultiSourceKeyRecommendation[]>([]);
  const [loadingRecommendations, setLoadingRecommendations] = useState<boolean>(false);
  const [recError, setRecError] = useState<string | null>(null);

  // --- Step 3: Rules & Tolerances ---
  const [numericTolerance, setNumericTolerance] = useState<number>(0.0);
  const [numericPercentageTolerance, setNumericPercentageTolerance] = useState<number>(0.0);
  const [ignoreWhitespace, setIgnoreWhitespace] = useState<boolean>(true);
  const [ignoreCase, setIgnoreCase] = useState<boolean>(false);
  const [enableStatusEquivalence, setEnableStatusEquivalence] = useState<boolean>(true);

  // Date Window Rule state
  const [dateWindowEnabled, setDateWindowEnabled] = useState<boolean>(false);
  const [dateWindowSourceField, setDateWindowSourceField] = useState<string>('date');
  const [dateWindowTargetField, setDateWindowTargetField] = useState<string>('date');
  const [dateWindowLagBefore, setDateWindowLagBefore] = useState<number>(0);
  const [dateWindowLagAfter, setDateWindowLagAfter] = useState<number>(3);

  // Where Condition Predicates state
  const [whereConditions, setWhereConditions] = useState<WhereCondition[]>([]);
  const [newPredField, setNewPredField] = useState<string>('');
  const [newPredOp, setNewPredOp] = useState<PredicateOperator>('equal');
  const [newPredValue, setNewPredValue] = useState<string>('');

  // Split-Payment Aggregation state
  const [aggregationEnabled, setAggregationEnabled] = useState<boolean>(false);
  const [aggregationParentAlias, setAggregationParentAlias] = useState<string>('');
  const [aggregationChildAlias, setAggregationChildAlias] = useState<string>('');
  const [aggregationParentKey, setAggregationParentKey] = useState<string>('id');
  const [aggregationChildGroupKey, setAggregationChildGroupKey] = useState<string>('parent_id');
  const [aggregationParentAmountField, setAggregationParentAmountField] = useState<string>('amount');
  const [aggregationChildAmountField, setAggregationChildAmountField] = useState<string>('amount');
  const [aggregationChildReceiptIdField, setAggregationChildReceiptIdField] = useState<string>('');
  const [aggregationNumericTolerance, setAggregationNumericTolerance] = useState<number>(0.0);

  // Rule Impact Preview state
  const [previewingRules, setPreviewingRules] = useState<boolean>(false);
  const [rulePreviewResult, setRulePreviewResult] = useState<RulePreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // --- Step 4: Verification Results & Running ---
  const [running, setRunning] = useState<boolean>(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [verificationResponse, setVerificationResponse] =
    useState<MultiSourceVerificationResponse | null>(null);
  const [createdRun, setCreatedRun] = useState<VerificationRun | null>(null);

  // Filters for Exception Grid
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [searchKey, setSearchKey] = useState<string>('');

  // --- Step 5: Sign-off ---
  const [signOffNote, setSignOffNote] = useState<string>('');
  const [isSignedOff, setIsSignedOff] = useState<boolean>(false);
  const [exportingFormat, setExportingFormat] = useState<'csv' | 'xlsx' | 'json' | null>(null);

  // Helper to derive alias for a dataset.
  // Financial mode: unchanged 'erp'/'bank'/... progression unless the user names it.
  // Organization mode: derive a stable system alias from the editable display label
  // (keeps `alias` as the backend identity while the label stays human-friendly).
  const getAlias = useCallback(
    (dsId: string, idx: number) => {
      const explicit = sourceAliases[dsId];
      if (explicit) return explicit;
      if (mode === 'organization') {
        const ds = uploadedDatasets.find((d) => d.id === dsId);
        if (!ds) return `source_${idx + 1}`;
        const base = ds.label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || `source_${idx + 1}`;
        const taken = new Set(
          uploadedDatasets
            .filter((other) => other.id !== dsId)
            .map((other) => other.label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')),
        );
        return taken.has(base) ? `${base}_${idx + 1}` : base;
      }
      return DEFAULT_NAMES[idx] || `source_${idx + 1}`;
    },
    [sourceAliases, uploadedDatasets, mode],
  );
  const effectivePrimaryId = primaryFileId || uploadedDatasets[0]?.id || '';
  const getKeyCols = (ds: { id: string; name: string; profile?: PreprocessingResult }) =>
    fileKeyColumns[ds.id] || [ds.profile?.columns[0]?.normalized_name || 'id'];

  // Fetch candidate key recommendations when entering Step 2
  useEffect(() => {
    if (currentStep !== 2 || uploadedDatasets.length < 2) return;

    let cancelled = false;
    const fetchRecommendations = async () => {
      setLoadingRecommendations(true);
      setRecError(null);
      try {
        const fileIds = uploadedDatasets.map((d) => d.id);
        const aliases = uploadedDatasets.map((d, idx) => getAlias(d.id, idx));
        const res = await api.recommendCandidateKeys(project.id, {
          file_ids: fileIds,
          aliases,
        });
        if (!cancelled) {
          setRecommendations(res.recommendations);
          if (res.recommendations.length > 0 && res.recommendations[0].overall_score >= 0.7) {
            const top = res.recommendations[0];
            setUnifiedKeys(top.key_name.split(' + '));
          }
        }
      } catch (err: any) {
        if (!cancelled) {
          setRecError(err.message || 'Could not fetch candidate key recommendations.');
        }
      } finally {
        if (!cancelled) setLoadingRecommendations(false);
      }
    };

    void fetchRecommendations();
    return () => {
      cancelled = true;
    };
  }, [currentStep, project.id, uploadedDatasets, getAlias]);

  // Batch 3 (organization mode): auto-fill mapping suggestions when entering Step 2
  // (called from the Step 1 continue action, so no render-cascading effect is needed).
  // Exact normalized matches become 'suggested'; synonym matches become
  // 'needs_confirmation' and are never auto-submitted. Existing entries are preserved.
  const ensureMappingSuggestions = () => {
    if (mode !== 'organization') return;
    setColumnMappings((prev) => buildAllSuggestions(uploadedDatasets, unifiedKeys, prev));
  };

  const updateMappingCell = (fileId: string, attr: string, column: string | null, state: 'suggested' | 'needs_confirmation' | 'confirmed') => {
    setColumnMappings((prev) => {
      const fileMap = { ...(prev[fileId] || {}) };
      if (column === null) {
        delete fileMap[attr];
      } else {
        fileMap[attr] = { column, state };
      }
      return { ...prev, [fileId]: fileMap };
    });
  };

  // Apply a candidate key recommendation
  const applyRecommendation = (rec: MultiSourceKeyRecommendation) => {
    const keys = rec.key_name.split(' + ');
    setUnifiedKeys(keys);

    setFileKeyColumns((prev) => {
      const next = { ...prev };
      uploadedDatasets.forEach((ds) => {
        const alias = sourceAliases[ds.id];
        if (alias && rec.source_columns[alias]) {
          next[ds.id] = rec.source_columns[alias];
        }
      });
      return next;
    });
  };

  // Build VersionedRuleConfig for preview and execution
  const buildRuleConfig = useCallback((): VersionedRuleConfig => {
    const dateWindowRules: DateWindowRule[] =
      dateWindowEnabled && dateWindowSourceField && dateWindowTargetField
        ? [
            {
              source_date_field: dateWindowSourceField,
              target_date_field: dateWindowTargetField,
              lag_days_before: dateWindowLagBefore,
              lag_days_after: dateWindowLagAfter,
              severity: 'WARNING',
            },
          ]
        : [];

    const numericRules: NumericToleranceRule[] =
      numericPercentageTolerance > 0
        ? [
            {
              source_amount_field: 'amount',
              target_amount_field: 'amount',
              absolute_tolerance: numericTolerance,
              percentage_tolerance: numericPercentageTolerance,
              tolerance_mode: 'both_or',
              severity: 'BLOCKING',
            },
          ]
        : [];

    // Financial aggregation (split-payment / 1:N) is a Financial Auditing feature only.
    // Organization mode can never emit an aggregation configuration.
    const aggConfig: AggregationConfig | null = aggregationEnabled && mode === 'financial'
      ? {
          enabled: true,
          parent_source_alias:
            aggregationParentAlias ||
            (uploadedDatasets[0] ? getAlias(uploadedDatasets[0].id, 0) : 'source_1'),
          child_source_alias:
            aggregationChildAlias ||
            (uploadedDatasets[1] ? getAlias(uploadedDatasets[1].id, 1) : 'source_2'),
          parent_key: aggregationParentKey,
          child_grouping_key: aggregationChildGroupKey,
          parent_amount_field: aggregationParentAmountField,
          child_amount_field: aggregationChildAmountField,
          child_receipt_id_field: aggregationChildReceiptIdField || null,
          numeric_tolerance: aggregationNumericTolerance,
        }
      : null;

    return {
      version: '1.0.0',
      where_conditions: whereConditions,
      date_window_rules: dateWindowRules,
      numeric_tolerance_rules: numericRules,
      status_transition_rules: enableStatusEquivalence
        ? [
            {
              source_field: 'status',
              target_field: 'status',
              allowed_transitions: {
                settled: ['completed', 'cleared'],
                completed: ['settled', 'cleared'],
                active: ['current'],
                pending: ['processing'],
              },
              case_sensitive: false,
              severity: 'BLOCKING',
            },
          ]
        : [],
      custom_rules: [],
      aggregation_config: aggConfig,
    };
  }, [
    dateWindowEnabled,
    dateWindowSourceField,
    dateWindowTargetField,
    dateWindowLagBefore,
    dateWindowLagAfter,
    numericTolerance,
    numericPercentageTolerance,
    aggregationEnabled,
    aggregationParentAlias,
    aggregationChildAlias,
    aggregationParentKey,
    aggregationChildGroupKey,
    aggregationParentAmountField,
    aggregationChildAmountField,
    aggregationChildReceiptIdField,
    aggregationNumericTolerance,
    uploadedDatasets,
    getAlias,
    whereConditions,
    enableStatusEquivalence,
    mode,
  ]);

  const handleAddPredicate = () => {
    if (!newPredField.trim()) return;
    setWhereConditions((prev) => [
      ...prev,
      {
        field: newPredField.trim(),
        operator: newPredOp,
        value: newPredValue,
        severity: 'WARNING',
      },
    ]);
    setNewPredField('');
    setNewPredValue('');
  };

  const handleRemovePredicate = (idx: number) => {
    setWhereConditions((prev) => prev.filter((_, i) => i !== idx));
  };

  // Execution blocker preview (organization mode). Batch 5: multiple primaries are
  // allowed only when multi-primary mode is explicitly enabled; at least one
  // primary is always required.
  const orgPrimaryCount = uploadedDatasets.filter((d) => d.isPrimary).length;
  const roleBlocker =
    mode === 'organization' && uploadedDatasets.length > 0 && (orgPrimaryCount < 1 || uploadedDatasets.length < 2)
      ? uploadedDatasets.length < 2
        ? 'Upload at least two files so there is something to check against.'
        : 'Verification needs at least one source of truth. Mark one file as the primary source in the file setup.'
      : mode === 'organization' && orgPrimaryCount > 1 && !multiPrimary
        ? `${orgPrimaryCount} files are marked primary, but multi-primary comparison is not enabled. Enable "Multiple authoritative sources" below, or keep exactly one primary.`
        : null;
  // Batch 7 (organization mode): XLSX workbooks require an explicit worksheet
  // choice — no silent active/first-sheet ingestion.
  const missingWorksheetFile = mode === 'organization'
    ? uploadedDatasets.find(
        (d) => (d.profile?.sheet_names?.length ?? 0) > 0 && !d.selectedSheet,
      )
    : undefined;
  const worksheetBlocker = missingWorksheetFile
    ? `Select a worksheet for "${missingWorksheetFile.label || missingWorksheetFile.name}" in the file setup — verification cannot start without an explicit worksheet choice.`
    : null;

  // Batch 3 (organization mode): build field_mapping {source_column -> canonical attribute}
  // from confirmed/suggested mapping state. Key columns are explicitly mapped to their
  // unified key so the engine resolves join columns through the same contract.
  // 'needs_confirmation' suggestions are deliberately EXCLUDED until confirmed.
  const buildFieldMapping = (ds: UploadedDataset): Record<string, string> => {
    const mapping: Record<string, string> = {};
    const keys = getKeyCols(ds);
    unifiedKeys.forEach((uk, i) => {
      const col = keys[i];
      if (uk?.trim() && col) mapping[col] = uk.trim();
    });
    // Batch 7 safety guard: only emit mappings for columns that exist in the file's
    // currently-selected worksheet profile. Stale mapping state from a previously
    // selected sheet must never be sent (the engine would compare against None).
    const profileColumns = new Set(
      (ds.profile?.columns || []).map((c) => c.normalized_name),
    );
    const keyColsValid = keys.every((col) => profileColumns.size === 0 || profileColumns.has(col));
    const fileMap = columnMappings[ds.id] || {};
    Object.entries(fileMap).forEach(([attr, entry]) => {
      if (!entry?.column || (entry.state !== 'confirmed' && entry.state !== 'suggested')) return;
      if (profileColumns.size > 0 && !profileColumns.has(entry.column)) return;
      if (mapping[entry.column] && mapping[entry.column] !== attr) return; // column already bound to a key
      mapping[entry.column] = attr;
    });
    // Guard the whole mapping: if the selected worksheet changed and even a key
    // column is no longer present, refuse to emit a partial mapping (the wizard
    // blocker surfaces the stale configuration instead of executing on wrong data).
    if (!keyColsValid) return {};
    return mapping;
  };

  const isOrgMode = mode === 'organization';
  const comparedAttributes = isOrgMode
    ? (multiPrimary
        ? computeComparedAttributesMultiPrimary(uploadedDatasets, columnMappings, unifiedKeys)
        : computeComparedAttributes(uploadedDatasets, columnMappings, unifiedKeys))
    : undefined;

  // Batch 11: capture the current reusable configuration for "Save as template".
  // Per-upload state (file IDs, row indices, quarantine exclusions) is never
  // included — the template schema rejects those fields server-side.
  const getCurrentTemplateConfiguration = (): TemplateConfigurationV1 | null => {
    if (!isOrgMode || uploadedDatasets.length < 2) return null;
    const slots: TemplateConfigurationV1['sources'] = [];
    for (let idx = 0; idx < uploadedDatasets.length; idx++) {
      const ds = uploadedDatasets[idx];
      const mapping = buildFieldMapping(ds);
      if (!mapping || Object.keys(mapping).length === 0) return null;
      slots.push({
        alias: getAlias(ds.id, idx),
        label: ds.label || null,
        is_primary: Boolean(ds.isPrimary),
        key_columns: getKeyCols(ds),
        field_mapping: mapping,
        sheet_name: ds.selectedSheet || null,
      });
    }
    const fallbackPayload =
      !multiPrimary
        ? buildFallbackPayload(uploadedDatasets, columnMappings, fallbackKeys, unifiedKeys)
        : undefined;
    return {
      version: 1,
      sources: slots,
      unified_keys: unifiedKeys,
      compare_attributes:
        comparedAttributes && comparedAttributes.length > 0 ? comparedAttributes : undefined,
      ignore_attributes: [],
      numeric_tolerance: numericTolerance,
      ignore_whitespace: ignoreWhitespace,
      ignore_case: ignoreCase,
      include_identical: true,
      fallback_keys: fallbackPayload && fallbackPayload.length > 0 ? fallbackPayload : undefined,
      multi_primary: multiPrimary,
      field_ownership:
        multiPrimary && Object.keys(fieldOwners).length > 0 ? fieldOwners : undefined,
    };
  };

  // Batch 11/13: populate wizard state from a validated template. Explicit
  // slot bindings decide which uploaded dataset receives each slot's key
  // columns, suggested mappings and worksheet selection — positional order is
  // no longer assumed. Column mappings are applied as 'suggested' so the user
  // reviews them against the NEW files (missing/renamed columns surface
  // through the existing wizard blockers).
  const handleTemplateApplied = (
    config: TemplateConfigurationV1,
    _report?: TemplateApplyResponse,
    bindings?: Record<string, string>,
  ) => {
    setUnifiedKeys(config.unified_keys);
    setNumericTolerance(config.numeric_tolerance ?? 0);
    setIgnoreWhitespace(config.ignore_whitespace ?? true);
    setIgnoreCase(config.ignore_case ?? false);
    setFallbackKeys(config.multi_primary ? [] : (config.fallback_keys ?? []));
    setMultiPrimary(Boolean(config.multi_primary));
    setFieldOwners(config.field_ownership ?? {});
    const newMappings: Record<string, FileColumnMappings> = {};
    const newKeyCols: Record<string, string[]> = {};
    config.sources.forEach((slot, idx) => {
      // Prefer the explicit binding from the template panel; fall back to the
      // positional dataset only when no binding was supplied (legacy callers).
      const boundId = bindings?.[slot.alias];
      const ds = boundId
        ? uploadedDatasets.find((d) => d.id === boundId)
        : uploadedDatasets[idx];
      if (!ds) return;
      newKeyCols[ds.id] = [...slot.key_columns];
      const fm: FileColumnMappings = {};
      Object.entries(slot.field_mapping).forEach(([column, attr]) => {
        fm[attr] = { column, state: 'suggested' };
      });
      newMappings[ds.id] = fm;
      // Align the worksheet selection with the template slot (validated by the
      // apply endpoint before this callback runs).
      if (slot.sheet_name && ds.selectedSheet !== slot.sheet_name && onWorksheetChange) {
        onWorksheetChange(ds.id, slot.sheet_name);
      }
    });
    setFileKeyColumns((prev) => ({ ...prev, ...newKeyCols }));
    setColumnMappings((prev) => ({ ...prev, ...newMappings }));
  };

  const handlePreviewRules = async () => {
    setPreviewingRules(true);
    setPreviewError(null);
    try {
      const sourcesPayload: SourceDefinition[] = uploadedDatasets.map((ds, idx) => ({
        alias: getAlias(ds.id, idx),
        file_id: ds.id,
        is_primary: mode === 'organization' ? Boolean(ds.isPrimary) : ds.id === effectivePrimaryId,
        label: ds.label || null,
        key_columns: getKeyCols(ds),
        field_mapping: mode === 'organization' ? buildFieldMapping(ds) : {},
        // Batch 7: explicit worksheet selection for XLSX sources (validated against
        // the workbook at execution time; never silently substituted).
        sheet_name: ds.selectedSheet || undefined,
      }));

      const ruleCfg = buildRuleConfig();
      const res = await api.previewRules(project.id, {
        rules: ruleCfg,
        sources: sourcesPayload,
        unified_keys: unifiedKeys,
        sample_size: 100,
      });
      setRulePreviewResult(res);
    } catch (err: any) {
      setPreviewError(err.message || 'Failed to preview rules.');
    } finally {
      setPreviewingRules(false);
    }
  };

  // Execute multi-source reconciliation
  const handleExecuteVerification = async () => {
    if (roleBlocker) {
      setRunError(roleBlocker);
      return;
    }
    if (worksheetBlocker) {
      setRunError(worksheetBlocker);
      return;
    }
    setRunning(true);
    setRunError(null);

    const sourcesPayload: SourceDefinition[] = uploadedDatasets.map((ds, idx) => ({
      alias: getAlias(ds.id, idx),
      file_id: ds.id,
      is_primary: mode === 'organization' ? Boolean(ds.isPrimary) : ds.id === effectivePrimaryId,
      label: ds.label || null,
      key_columns: getKeyCols(ds),
      field_mapping: mode === 'organization' ? buildFieldMapping(ds) : {},
      // Batch 7: explicit worksheet selection for XLSX sources (validated against
      // the workbook at execution time; never silently substituted).
      sheet_name: ds.selectedSheet || undefined,
    }));

    const statusRuleConfig = enableStatusEquivalence
      ? {
          permitted_pairs: [
            ['settled', 'completed'],
            ['settled', 'cleared'],
            ['completed', 'cleared'],
            ['active', 'current'],
            ['pending', 'processing'],
          ],
        }
      : undefined;

    const ruleConfig = buildRuleConfig();

    const payload: MultiSourceVerificationRequest = {
      sources: sourcesPayload,
      unified_keys: unifiedKeys,
      // Organization mode: compare only attributes explicitly mapped (suggested/confirmed)
      // in the primary source and every other file. Unmapped attributes are never compared
      // and therefore never counted as verified.
      compare_attributes:
        comparedAttributes && comparedAttributes.length > 0 ? comparedAttributes : undefined,
      // Batch 4: only complete, fully-mapped fallback definitions are sent; financial
      // mode and requests without fallbacks behave exactly as before. Batch 5:
      // fallback matching is unavailable in multi-primary mode (engine constraint).
      fallback_keys:
        mode === 'organization' && !multiPrimary
          ? buildFallbackPayload(uploadedDatasets, columnMappings, fallbackKeys, unifiedKeys)
          : undefined,
      // Batch 5: explicit multi-primary opt-in with validated per-attribute ownership.
      multi_primary: mode === 'organization' && multiPrimary ? true : undefined,
      field_ownership:
        mode === 'organization' && multiPrimary
          ? buildFieldOwnershipPayload(uploadedDatasets, columnMappings, fieldOwners, unifiedKeys, (fid) => getAlias(fid, uploadedDatasets.findIndex((d) => d.id === fid)))
          : undefined,
      numeric_tolerance: numericTolerance,
      ignore_whitespace: ignoreWhitespace,
      ignore_case: ignoreCase,
      include_identical: true,
      status_rules: statusRuleConfig,
      rule_config: ruleConfig,
    };

    try {
      // 1. Run in-memory calculation
      const resp = await api.verifyMultiSourceFiles(project.id, payload);
      setVerificationResponse(resp);

      // 2. Persist to audit history
      try {
        const runObj = await api.createMultiSourceVerificationRun(project.id, payload);
        setCreatedRun(runObj);
        if (onRunCompleted) {
          onRunCompleted(runObj);
        }
      } catch (runErr) {
        console.warn('Persistent run creation error (in-memory results preserved):', runErr);
      }

      setCurrentStep(4);
    } catch (err: any) {
      setRunError(err.message || 'Multi-source reconciliation failed.');
    } finally {
      setRunning(false);
    }
  };

  // Export report
  const handleExport = async (format: 'csv' | 'xlsx' | 'json') => {
    if (!createdRun) return;
    setExportingFormat(format);
    try {
      await api.downloadExport(project.id, createdRun.id, format);
    } catch (err: any) {
      alert(`Export failed: ${err.message}`);
    } finally {
      setExportingFormat(null);
    }
  };

  // Filtered results in Exception Grid
  const filteredResults = (verificationResponse?.results || []).filter((item) => {
    if (categoryFilter !== 'all' && item.discrepancy_category !== categoryFilter) return false;
    if (statusFilter !== 'all' && item.match_status !== statusFilter) return false;
    if (searchKey.trim()) {
      const kStr = JSON.stringify(item.key_values).toLowerCase();
      if (!kStr.includes(searchKey.toLowerCase())) return false;
    }
    return true;
  });

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      {/* 5-Step Stepper Header */}
      <div
        className="wizard-stepper-header"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(5, 1fr)',
          borderBottom: '1px solid var(--border-color)',
          backgroundColor: 'var(--bg-secondary)',
        }}
      >
        {STEPS.map((s) => {
          const isCompleted = currentStep > s.num;
          const isActive = currentStep === s.num;
          return (
            <button
              key={s.num}
              type="button"
              className={`stepper-step ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}
              onClick={() => {
                // Allow jumping to completed or active steps freely without losing state
                if (isCompleted || isActive) {
                  setCurrentStep(s.num as WizardStep);
                }
              }}
              style={{
                padding: '14px 16px',
                border: 'none',
                background: isActive ? 'var(--bg-subtle)' : 'transparent',
                borderBottom: isActive ? '3px solid var(--primary)' : '3px solid transparent',
                cursor: isCompleted || isActive ? 'pointer' : 'not-allowed',
                textAlign: 'left',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                transition: 'var(--transition)',
              }}
            >
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  backgroundColor: isCompleted
                    ? 'var(--success)'
                    : isActive
                      ? 'var(--primary)'
                      : 'var(--bg-card-hover)',
                  color: isCompleted || isActive ? '#ffffff' : 'var(--text-muted)',
                }}
              >
                {isCompleted ? <Check size={15} /> : s.num}
              </div>
              <div style={{ overflow: 'hidden' }}>
                <div
                  style={{
                    fontSize: '0.88rem',
                    fontWeight: isActive ? 600 : 500,
                    color: isActive ? 'var(--text-main)' : 'var(--text-muted)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {mode === 'organization' ? s.orgTitle : s.title}
                </div>
                <div style={{ fontSize: '0.74rem', color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
                  {mode === 'organization' ? s.orgDesc : s.desc}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Step Content Shell */}
      <div style={{ padding: '24px' }}>
        {/* ================= STEP 1: INGESTION ================= */}
        {currentStep === 1 && (
          <div>
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileSpreadsheet size={18} className="text-accent" />{' '}
                {mode === 'organization' ? 'Step 1: Upload Your Files' : 'Step 1: Multi-Source Dataset Ingestion'}
              </h3>
              <p className="text-dim" style={{ margin: '4px 0 0 0', fontSize: '0.85rem' }}>
                {mode === 'organization'
                  ? 'Upload 2 or more files (e.g. academic register, hostel allocation, membership cards). We check the data quality before you compare anything.'
                  : 'Upload 2 or more datasets (e.g. ERP ledger, bank statement, gateway settlements). Inspect pre-flight schemas and resolve quarantine anomalies.'}
              </p>
            </div>

            <FileUploadSection
              project={project}
              datasets={uploadedDatasets}
              onFileUploaded={onFileUploaded}
              mode={mode}
              onLabelChange={onLabelChange}
              onRoleChange={onRoleChange}
              onRemoveFile={onRemoveFile}
              onWorksheetChange={onWorksheetChange}
            />

            {/* Batch 11/13: reusable templates (organization mode only; personal) */}
            <TemplatePanel
              mode={mode}
              project={project}
              uploadedDatasets={uploadedDatasets}
              getCurrentConfiguration={getCurrentTemplateConfiguration}
              onTemplateApplied={handleTemplateApplied}
            />

            {/* List of uploaded files with pre-flight badges */}
            {uploadedDatasets.length >= 2 && (
              <div style={{ marginTop: 20, padding: '16px', backgroundColor: 'var(--bg-subtle)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <ShieldCheck size={18} className="text-success" />
                    <strong>{uploadedDatasets.length} datasets ready for reconciliation</strong>
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => {
                      ensureMappingSuggestions();
                      setCurrentStep(2);
                    }}
                  >
                    {mode === 'organization' ? 'Continue to file setup' : 'Proceed to Blueprint'} <ArrowRight size={15} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ================= STEP 2: BLUEPRINT ================= */}
        {currentStep === 2 && (
          <div>
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Layers size={18} className="text-accent" /> Step 2: Name Your Files &amp; Matching Keys
              </h3>
              <p className="text-dim" style={{ margin: '4px 0 0 0', fontSize: '0.85rem' }}>
                {mode === 'organization'
                  ? 'Give each file a clear name, choose which file is the source of truth, and pick the matching key (e.g. enrolment number or student ID).'
                  : 'Assign meaningful aliases, select the primary baseline source, and configure matching join keys.'}
              </p>
              {mode === 'organization' && (
                <>
                  <div className="info-strip" style={{ marginTop: 12 }}>
                    <Info size={15} />
                    <span>
                      Roles recorded here decide which file every other file is checked against.
                      {multiPrimary
                        ? ' Multi-primary mode is ON: several files may be authoritative, but only for the fields they own (configured below).'
                        : ' By default one file is the single source of truth; enable multi-primary mode below to give each file authority over its own fields.'}
                    </span>
                  </div>
                  <label
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 8, marginTop: 10, cursor: 'pointer', fontSize: '0.88rem' }}
                    title="Allow several authoritative files, each owning specific fields. Each field is then compared against its configured owner instead of a single primary source."
                  >
                    <input
                      type="checkbox"
                      checked={multiPrimary}
                      onChange={(e) => setMultiPrimary(e.target.checked)}
                    />
                    <strong>Multiple authoritative sources (advanced)</strong>
                    <span className="text-dim" style={{ fontWeight: 400 }}>
                      — selecting a file as primary does not automatically make it authoritative for every field; each field is compared against its configured owner.
                    </span>
                  </label>
                  {multiPrimary && fallbackKeys.length > 0 && (
                    <div className="info-strip" style={{ marginTop: 8 }}>
                      <AlertCircle size={15} />
                      <span>
                        Fallback matching is unavailable while multiple authoritative sources are enabled —
                        configured fallback keys will not be sent with this run.
                      </span>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Candidate Key Recommendations Banner */}
            <div
              className="card"
              style={{
                marginBottom: 20,
                backgroundColor: 'var(--bg-card-hover)',
                border: '1px solid var(--border-color)',
                padding: '16px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Sparkles size={16} className="text-accent" />
                  <strong>AI &amp; Heuristic Join Key Recommendations</strong>
                </div>
                {loadingRecommendations && <span className="spinner" />}
              </div>

              {recError && <p className="text-danger" style={{ fontSize: '0.85rem' }}>{recError}</p>}

              {recommendations.length > 0 ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
                  {recommendations.map((rec) => (
                    <div
                      key={rec.key_name}
                      className="card"
                      style={{
                        padding: '12px',
                        borderLeft: rec.overall_score >= 0.8 ? '4px solid var(--success)' : '4px solid var(--warning)',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                          <strong style={{ fontSize: '0.9rem' }}>{rec.key_name}</strong>
                          <span className="badge badge-success">{(rec.overall_score * 100).toFixed(0)}% Match</span>
                        </div>
                        <p style={{ fontSize: '0.78rem', color: 'var(--text-dim)', margin: '0 0 8px 0' }}>
                          {rec.recommendation_reason}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="btn btn-secondary btn-xs"
                        style={{ width: 'fit-content' }}
                        onClick={() => applyRecommendation(rec)}
                      >
                        Apply this Key
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-dim" style={{ fontSize: '0.85rem', margin: 0 }}>
                  Analyzing cross-source column uniqueness and value overlap…
                </p>
              )}
            </div>

            {/* Source Aliases & Key Columns Table */}
            <div className="table-container" style={{ border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', marginBottom: 20 }}>
              <table className="data-table" style={{ width: '100%', fontSize: '0.85rem' }}>
                <thead>
                  <tr>
                    <th style={{ width: 140 }}>Role</th>
                    <th style={{ width: 180 }}>Source Alias</th>
                    <th>File Name</th>
                    <th>Key Column(s)</th>
                  </tr>
                </thead>
                <tbody>
                  {uploadedDatasets.map((ds, idx) => {
                    const isPrimary =
                      mode === 'organization' ? Boolean(ds.isPrimary) : ds.id === effectivePrimaryId;
                    const cols = ds.profile?.columns.map((c) => c.normalized_name) || [];
                    const currentAlias = getAlias(ds.id, idx);
                    const currentKeyCols = getKeyCols(ds);
                    return (
                      <tr key={ds.id} style={{ backgroundColor: isPrimary ? 'var(--bg-subtle)' : undefined }}>
                        <td>
                          {mode === 'organization' ? (
                            <select
                              className="form-select"
                              value={isPrimary ? 'primary' : 'target'}
                              onChange={(e) => onRoleChange?.(ds.id, e.target.value === 'primary')}
                              aria-label={`Role for ${ds.label || ds.name}`}
                              style={{ fontSize: '0.85rem', padding: '4px 8px', width: '100%' }}
                            >
                              <option value="primary">Primary source</option>
                              <option value="target">Target to verify</option>
                            </select>
                          ) : (
                            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                              <input
                                type="radio"
                                name="primarySourceRadio"
                                checked={isPrimary}
                                onChange={() => setPrimaryFileId(ds.id)}
                              />
                              {isPrimary ? (
                                <span className="badge badge-success">Primary Golden</span>
                              ) : (
                                <span className="text-dim">Secondary</span>
                              )}
                            </label>
                          )}
                        </td>
                        <td>
                          {mode === 'organization' ? (
                            <code title="System alias (derived from the file label)" style={{ fontSize: '0.78rem' }}>
                              {currentAlias}
                            </code>
                          ) : (
                          <input
                            type="text"
                            className="form-input"
                            value={currentAlias}
                            onChange={(e) =>
                              setSourceAliases({ ...sourceAliases, [ds.id]: e.target.value })
                            }
                            placeholder="e.g. erp, bank, gateway"
                            style={{ fontSize: '0.85rem', padding: '4px 8px' }}
                          />
                          )}
                        </td>
                        <td>
                          <strong>{ds.label || ds.name}</strong>
                          <span className="text-dim" style={{ marginLeft: 8 }}>
                            ({ds.profile?.data_rows_count.toLocaleString() || '—'} rows)
                          </span>
                        </td>
                        <td>
                          <select
                            className="form-select"
                            value={currentKeyCols[0] || ''}
                            onChange={(e) =>
                              setFileKeyColumns({ ...fileKeyColumns, [ds.id]: [e.target.value] })
                            }
                            style={{ fontSize: '0.85rem', padding: '4px 8px', maxWidth: 220 }}
                          >
                            {cols.map((colName) => (
                              <option key={colName} value={colName}>
                                {colName}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Batch 3 (organization mode): Column Mapping */}
            {mode === 'organization' && uploadedDatasets.length > 0 && (() => {
              const attrs = collectCanonicalAttributes(uploadedDatasets, unifiedKeys);
              const comparableAttrs = attrs.filter((attr) => {
                const filesWithCandidate = uploadedDatasets.filter((ds) => {
                  const m = columnMappings[ds.id]?.[attr];
                  if (m?.column) return true;
                  return ds.profile?.columns.some((c) => c.normalized_name === attr) || false;
                });
                return filesWithCandidate.length >= 2;
              });
              const notComparedAttrs = attrs.filter((a) => !comparableAttrs.includes(a));
              const confirmedOrSuggested = comparedAttributes ?? [];
              return (
                <div style={{ marginBottom: 24 }}>
                  <h4 style={{ margin: '0 0 4px 0', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Layers size={15} className="text-accent" /> Column Mapping
                  </h4>
                  <p className="text-dim" style={{ fontSize: '0.82rem', margin: '0 0 10px 0' }}>
                    Map each field to the same name across files so they can be compared. Exact name matches are
                    suggested automatically; close matches need your confirmation. Unmapped fields will{' '}
                    <strong>not</strong> be compared.
                  </p>

                  <div className="info-strip" style={{ marginBottom: 12 }}>
                    <Check size={15} />
                    <span>
                      <strong>{confirmedOrSuggested.length}</strong> field{confirmedOrSuggested.length === 1 ? '' : 's'} will be
                      compared across all files{notComparedAttrs.length > 0 ? ` · ${notComparedAttrs.length} field(s) not mapped and not compared` : ''}.
                    </span>
                  </div>

                  {comparableAttrs.length > 0 && (
                    <div className="table-container" style={{ border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', marginBottom: 12, overflowX: 'auto' }}>
                      <table className="data-table" style={{ width: '100%', fontSize: '0.82rem', minWidth: 480 }}>
                        <thead>
                          <tr>
                            <th>Field</th>
                            {uploadedDatasets.map((ds) => (
                              <th key={ds.id}>{ds.label || ds.name}</th>
                            ))}
                            {multiPrimary && <th title="The source whose value is authoritative for this field">Owner</th>}
                          </tr>
                        </thead>
                        <tbody>
                          {comparableAttrs.map((attr) => (
                            <tr key={attr}>
                              <td><code style={{ fontSize: '0.78rem' }}>{attr}</code></td>
                              {uploadedDatasets.map((ds) => {
                                const entry = columnMappings[ds.id]?.[attr];
                                const used = usedColumnsForFile(ds.id, columnMappings, attr);
                                const fileCols = ds.profile?.columns || [];
                                const hasCandidate = Boolean(entry?.column) || fileCols.some((c) => c.normalized_name === attr);
                                if (!hasCandidate) {
                                  return (
                                    <td key={ds.id} className="text-dim" style={{ opacity: 0.6 }}>
                                      Not in this file
                                    </td>
                                  );
                                }
                                return (
                                  <td key={ds.id}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                      <select
                                        className="form-select"
                                        value={entry?.column || ''}
                                        onChange={(e) =>
                                          updateMappingCell(
                                            ds.id,
                                            attr,
                                            e.target.value || null,
                                            'confirmed',
                                          )
                                        }
                                        aria-label={`Column for '${attr}' in ${ds.label || ds.name}`}
                                        style={{ fontSize: '0.8rem', padding: '3px 6px', maxWidth: 180 }}
                                      >
                                        <option value="">Not mapped</option>
                                        {fileCols.map((c) => (
                                          <option
                                            key={c.normalized_name}
                                            value={c.normalized_name}
                                            disabled={used.has(c.normalized_name) && c.normalized_name !== entry?.column}
                                            title={c.original_name}
                                          >
                                            {c.normalized_name}
                                          </option>
                                        ))}
                                      </select>
                                      {entry?.state === 'needs_confirmation' && (
                                        <>
                                          <span className="badge badge-neutral" title="Matched via a name dictionary — please confirm">
                                            Needs confirmation
                                          </span>
                                          <button
                                            type="button"
                                            className="btn btn-secondary btn-xs"
                                            onClick={() => updateMappingCell(ds.id, attr, entry.column, 'confirmed')}
                                            aria-label={`Confirm mapping of ${entry.column} to ${attr} in ${ds.label || ds.name}`}
                                          >
                                            Confirm
                                          </button>
                                        </>
                                      )}
                                      {entry?.state === 'suggested' && (
                                        <span className="badge badge-success" title="Exact name match">
                                          Suggested
                                        </span>
                                      )}
                                      {entry?.state === 'confirmed' && (
                                        <span className="badge badge-success">
                                          <Check size={11} /> Confirmed
                                        </span>
                                      )}
                                    </div>
                                  </td>
                                );
                              })}
                              {multiPrimary && (() => {
                                const ownerFileId = fieldOwners[attr];
                                const carryingFiles = uploadedDatasets.filter((ds) => {
                                  const m = columnMappings[ds.id]?.[attr];
                                  return Boolean(m?.column);
                                });
                                const currentValid = carryingFiles.some((ds) => ds.id === ownerFileId);
                                const effectiveOwner = currentValid
                                  ? ownerFileId
                                  : (uploadedDatasets.find((d) => d.isPrimary && carryingFiles.some((c) => c.id === d.id))?.id
                                      || carryingFiles[0]?.id || '');
                                return (
                                  <td key={`${attr}-owner`}>
                                    {carryingFiles.length === 0 ? (
                                      <span className="text-dim" style={{ fontSize: '0.78rem' }}>—</span>
                                    ) : (
                                      <select
                                        className="form-select"
                                        value={effectiveOwner}
                                        onChange={(e) => setFieldOwners((prev) => ({ ...prev, [attr]: e.target.value }))}
                                        aria-label={`Authoritative source for '${attr}'`}
                                        style={{ fontSize: '0.8rem', padding: '3px 6px', maxWidth: 180 }}
                                      >
                                        {carryingFiles.map((ds) => (
                                          <option key={ds.id} value={ds.id}>{ds.label || ds.name}</option>
                                        ))}
                                      </select>
                                    )}
                                  </td>
                                );
                              })()}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {notComparedAttrs.length > 0 && (
                    <p className="text-dim" style={{ fontSize: '0.8rem', margin: 0 }}>
                      Not compared (no matching field in at least two files): {notComparedAttrs.slice(0, 12).join(', ')}
                      {notComparedAttrs.length > 12 ? ` … and ${notComparedAttrs.length - 12} more` : ''}.
                    </p>
                  )}
                </div>
              );
            })()}

            {/* Batch 4 (organization mode): Fallback matching configuration */}
            {mode === 'organization' && uploadedDatasets.length >= 2 && (() => {
              const attrOptions = collectCanonicalAttributes(uploadedDatasets, unifiedKeys);
              const isFallbackSendable = (fb: string[]): boolean =>
                buildFallbackPayload(uploadedDatasets, columnMappings, [fb], unifiedKeys) !== undefined;
              return (
                <div style={{ marginBottom: 24 }}>
                  <h4 style={{ margin: '0 0 4px 0', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Layers size={15} className="text-accent" /> Fallback matching (optional)
                  </h4>
                  <p className="text-dim" style={{ fontSize: '0.82rem', margin: '0 0 10px 0' }}>
                    When the primary key cannot match a record (e.g. a missing enrolment number), VerifyGrid tries
                    these keys in order. Fallback values must match exactly and uniquely — ambiguous or blank values
                    are never matched. Only fallbacks whose fields are mapped in every file are sent.
                  </p>

                  {fallbackKeys.map((fb, i) => {
                    const sendable = isFallbackSendable(fb);
                    return (
                      <div
                        key={`${fb.join('|')}-${i}`}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
                          padding: '8px 10px', marginBottom: 6,
                          border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)',
                        }}
                      >
                        <span className="badge badge-neutral" title={`Tried after ${i} higher-priority fallback${i === 1 ? '' : 's'}`}>
                          Priority {i + 1}
                        </span>
                        {fb.map((attr) => (
                          <span key={attr} className="chip" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <code style={{ fontSize: '0.75rem' }}>{attr}</code>
                            <button
                              type="button"
                              className="btn btn-secondary btn-xs"
                              onClick={() =>
                                setFallbackKeys((prev) =>
                                  prev.map((f, j) => (j === i ? f.filter((a) => a !== attr) : f)).filter((f) => f.length > 0),
                                )
                              }
                              aria-label={`Remove ${attr} from fallback priority ${i + 1}`}
                            >
                              ×
                            </button>
                          </span>
                        ))}
                        <select
                          className="form-select"
                          value=""
                          onChange={(e) => {
                            if (!e.target.value) return;
                            setFallbackKeys((prev) =>
                              prev.map((f, j) => (j === i ? [...f, e.target.value] : f)),
                            );
                          }}
                          aria-label={`Add an attribute to fallback priority ${i + 1}`}
                          style={{ fontSize: '0.8rem', padding: '3px 6px', maxWidth: 200 }}
                        >
                          <option value="">+ add field…</option>
                          {attrOptions
                            .filter((a) => !fb.includes(a))
                            .map((a) => (
                              <option key={a} value={a}>{a}</option>
                            ))}
                        </select>
                        {!sendable && (
                          <span className="badge badge-neutral" title="Every file must have a confirmed/suggested mapping for each field before this fallback is sent">
                            Not sendable — map these fields in every file
                          </span>
                        )}
                        <div style={{ marginLeft: 'auto', display: 'inline-flex', gap: 4 }}>
                          <button
                            type="button"
                            className="btn btn-secondary btn-xs"
                            disabled={i === 0}
                            onClick={() =>
                              setFallbackKeys((prev) => {
                                const next = [...prev];
                                [next[i - 1], next[i]] = [next[i], next[i - 1]];
                                return next;
                              })
                            }
                            aria-label={`Move fallback priority ${i + 1} up`}
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-xs"
                            disabled={i === fallbackKeys.length - 1}
                            onClick={() =>
                              setFallbackKeys((prev) => {
                                const next = [...prev];
                                [next[i], next[i + 1]] = [next[i + 1], next[i]];
                                return next;
                              })
                            }
                            aria-label={`Move fallback priority ${i + 1} down`}
                          >
                            ↓
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-xs"
                            onClick={() => setFallbackKeys((prev) => prev.filter((_, j) => j !== i))}
                            aria-label={`Remove fallback priority ${i + 1}`}
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    );
                  })}

                  <button
                    type="button"
                    className="btn btn-secondary btn-xs"
                    onClick={() => setFallbackKeys((prev) => [...prev, []])}
                    disabled={attrOptions.length === 0 || multiPrimary}
                    title={multiPrimary ? 'Fallback matching is unavailable in multi-primary mode' : undefined}
                  >
                    + Add fallback key
                  </button>
                  {multiPrimary && (
                    <span className="text-dim" style={{ marginLeft: 10, fontSize: '0.8rem' }}>
                      Fallback matching is unavailable while multiple authoritative sources are enabled.
                    </span>
                  )}
                  {fallbackKeys.length > 0 && (
                    <span className="text-dim" style={{ marginLeft: 10, fontSize: '0.8rem' }}>
                      {fallbackKeys.filter((fb) => isFallbackSendable(fb)).length} of {fallbackKeys.length} configured
                      fallback{fallbackKeys.length === 1 ? '' : 's'} will be sent (priority order shown above).
                    </span>
                  )}
                </div>
              );
            })()}

            {/* Unified Join Key Input */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
              <label style={{ fontSize: '0.9rem', fontWeight: 500 }}>Unified Join Key:</label>
              <input
                type="text"
                className="form-input"
                style={{ maxWidth: 260 }}
                value={unifiedKeys.join(' + ')}
                onChange={(e) => setUnifiedKeys(e.target.value.split('+').map((s) => s.trim()))}
                placeholder="e.g. id or order_id + date"
              />
              <span className="text-dim" style={{ fontSize: '0.8rem' }}>
                (Composite keys can be combined with &apos;+&apos;)
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setCurrentStep(1)}>
                <ChevronLeft size={16} /> Back to Ingestion
              </button>
              <button type="button" className="btn btn-primary" onClick={() => setCurrentStep(3)}>
                Proceed to Rules <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* ================= STEP 3: RULES ================= */}
        {currentStep === 3 && (
          <div>
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Sliders size={18} className="text-accent" />{' '}
                {mode === 'organization' ? 'Step 3: Verification Settings' : 'Step 3: Reconciliation Rules & Tolerances'}
              </h3>
              <p className="text-dim" style={{ margin: '4px 0 0 0', fontSize: '0.85rem' }}>
                {mode === 'organization'
                  ? 'Adjust how strictly values are compared, and how records with multiple similar names are handled.'
                  : 'Configure numeric float/amount tolerances, string normalization, and state-aware status equivalence.'}
              </p>
            </div>

            {/* Rules Cards Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginBottom: 20 }}>
              {/* Tolerance Rule */}
              <div className="card" style={{ padding: '16px' }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: '0.95rem' }}>{'Numeric & Measurement Tolerances'}</h4>
                <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                  {mode === 'organization'
                    ? 'Allow small differences when comparing numbers (e.g. 25 vs 25.00). Leave at 0 for exact comparisons.'
                    : 'Acceptable thresholds when comparing monetary amounts or numerical measures across systems.'}
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ minWidth: 100, fontSize: '0.85rem' }}>Absolute (±):</span>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      className="form-input"
                      style={{ maxWidth: 100 }}
                      value={numericTolerance}
                      onChange={(e) => setNumericTolerance(parseFloat(e.target.value) || 0)}
                    />
                    <span className="text-dim" style={{ fontSize: '0.78rem' }}>
                      {numericTolerance === 0 ? '(Exact match)' : `(Diff ≤ ${numericTolerance})`}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ minWidth: 100, fontSize: '0.85rem' }}>Percentage (%):</span>
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      max="100"
                      className="form-input"
                      style={{ maxWidth: 100 }}
                      value={numericPercentageTolerance}
                      onChange={(e) => setNumericPercentageTolerance(parseFloat(e.target.value) || 0)}
                    />
                    <span className="text-dim" style={{ fontSize: '0.78rem' }}>
                      {numericPercentageTolerance === 0 ? '(0% tolerance)' : `(Diff ≤ ${numericPercentageTolerance}%)`}
                    </span>
                  </div>
                </div>
              </div>

              {/* Settlement Date Window Rule */}
              <div className="card" style={{ padding: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <h4 style={{ margin: 0, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Calendar size={16} className="text-accent" /> Settlement Date Window
                  </h4>
                  <label className="switch" style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={dateWindowEnabled}
                      onChange={(e) => setDateWindowEnabled(e.target.checked)}
                    />
                    <span style={{ fontSize: '0.8rem' }}>{dateWindowEnabled ? 'Active' : 'Off'}</span>
                  </label>
                </div>
                <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                  Verify transaction lag (target date must fall within [source - N days, source + M days]).
                </p>
                {dateWindowEnabled && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: '0.82rem' }}>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <div style={{ flex: 1 }}>
                        <label style={{ display: 'block', marginBottom: 2 }}>Source Date Col</label>
                        <input
                          type="text"
                          className="form-input"
                          style={{ width: '100%', padding: '4px 8px' }}
                          value={dateWindowSourceField}
                          onChange={(e) => setDateWindowSourceField(e.target.value)}
                          placeholder="e.g. date, txn_date"
                        />
                      </div>
                      <div style={{ flex: 1 }}>
                        <label style={{ display: 'block', marginBottom: 2 }}>Target Date Col</label>
                        <input
                          type="text"
                          className="form-input"
                          style={{ width: '100%', padding: '4px 8px' }}
                          value={dateWindowTargetField}
                          onChange={(e) => setDateWindowTargetField(e.target.value)}
                          placeholder="e.g. date, settled_date"
                        />
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <div style={{ flex: 1 }}>
                        <label style={{ display: 'block', marginBottom: 2 }}>Lag Before (Days)</label>
                        <input
                          type="number"
                          min="0"
                          className="form-input"
                          style={{ width: '100%', padding: '4px 8px' }}
                          value={dateWindowLagBefore}
                          onChange={(e) => setDateWindowLagBefore(parseInt(e.target.value, 10) || 0)}
                        />
                      </div>
                      <div style={{ flex: 1 }}>
                        <label style={{ display: 'block', marginBottom: 2 }}>Lag After (Days)</label>
                        <input
                          type="number"
                          min="0"
                          className="form-input"
                          style={{ width: '100%', padding: '4px 8px' }}
                          value={dateWindowLagAfter}
                          onChange={(e) => setDateWindowLagAfter(parseInt(e.target.value, 10) || 0)}
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Status Equivalence Rule */}
              <div className="card" style={{ padding: '16px' }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: '0.95rem' }}>Cross-System Status Equivalence</h4>
                <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                  Maps equivalent state terms across disparate source vendors.
                </p>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', marginBottom: 8 }}>
                  <input
                    type="checkbox"
                    checked={enableStatusEquivalence}
                    onChange={(e) => setEnableStatusEquivalence(e.target.checked)}
                  />
                  <span>Enable status equivalence rules</span>
                </label>
                {enableStatusEquivalence && (
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', backgroundColor: 'var(--bg-subtle)', padding: '6px 10px', borderRadius: 'var(--radius-xs)' }}>
                    • &apos;settled&apos; ↔ &apos;completed&apos; ↔ &apos;cleared&apos;
                    <br />
                    • &apos;active&apos; ↔ &apos;current&apos;
                  </div>
                )}
              </div>

              {/* String Normalization */}
              <div className="card" style={{ padding: '16px' }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: '0.95rem' }}>Text Cleaning</h4>
                <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                  Case and whitespace rules applied during field comparison.
                </p>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', marginBottom: 8 }}>
                  <input
                    type="checkbox"
                    checked={ignoreWhitespace}
                    onChange={(e) => setIgnoreWhitespace(e.target.checked)}
                  />
                  <span>Ignore leading and trailing whitespace</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={ignoreCase}
                    onChange={(e) => setIgnoreCase(e.target.checked)}
                  />
                  <span>Ignore case sensitivity</span>
                </label>
              </div>
            </div>

            {/* Compound Predicates (Where Conditions) */}
            <div className="card" style={{ padding: '16px', marginBottom: 20 }}>
              <h4 style={{ margin: '0 0 6px 0', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Filter size={16} className="text-accent" /> Structured Record Predicates &amp; Compound Filters
              </h4>
              <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                Pre-filter or restrict dataset records before evaluating cross-source reconciliation.
              </p>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Field (e.g. currency, status)"
                  style={{ width: 180, fontSize: '0.85rem' }}
                  value={newPredField}
                  onChange={(e) => setNewPredField(e.target.value)}
                />
                <select
                  className="form-select"
                  style={{ width: 140, fontSize: '0.85rem' }}
                  value={newPredOp}
                  onChange={(e) => setNewPredOp(e.target.value as PredicateOperator)}
                >
                  <option value="equal">equal (==)</option>
                  <option value="not_equal">not_equal (!=)</option>
                  <option value="greater_than">greater_than (&gt;)</option>
                  <option value="less_than">less_than (&lt;)</option>
                  <option value="in">in (comma-sep)</option>
                  <option value="not_in">not_in (comma-sep)</option>
                  <option value="regex">regex matches</option>
                </select>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Target value"
                  style={{ flex: 1, minWidth: 150, fontSize: '0.85rem' }}
                  value={newPredValue}
                  onChange={(e) => setNewPredValue(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={handleAddPredicate}
                  disabled={!newPredField.trim()}
                >
                  <Plus size={14} /> Add Predicate
                </button>
              </div>

              {whereConditions.length > 0 ? (
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {whereConditions.map((cond, idx) => (
                    <span
                      key={idx}
                      className="badge"
                      style={{
                        backgroundColor: 'var(--bg-subtle)',
                        border: '1px solid var(--border-color)',
                        padding: '6px 10px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        fontSize: '0.82rem',
                      }}
                    >
                      <code>{cond.field}</code>
                      <span className="text-dim">{cond.operator}</span>
                      <strong>{String(cond.value)}</strong>
                      <button
                        type="button"
                        onClick={() => handleRemovePredicate(idx)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex', color: 'var(--danger-text)' }}
                      >
                        <Trash2 size={13} />
                      </button>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-dim" style={{ fontSize: '0.82rem', margin: 0 }}>
                  No predicates defined. All records from all sources will participate in reconciliation.
                </p>
              )}
            </div>

            {/* Split-Payment / Aggregation Toggle & Configuration (Financial Auditing only) */}
            <div
              className="card"
              style={{ padding: '16px', marginBottom: 20, display: mode === 'financial' ? undefined : 'none' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <h4 style={{ margin: 0, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Split size={16} className="text-accent" /> One-to-Many (1:N) &amp; Split-Payment Aggregation
                </h4>
                <label className="switch" style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={aggregationEnabled}
                    onChange={(e) => setAggregationEnabled(e.target.checked)}
                  />
                  <span style={{ fontSize: '0.8rem' }}>{aggregationEnabled ? 'Enabled' : 'Disabled'}</span>
                </label>
              </div>
              <p className="text-dim" style={{ fontSize: '0.82rem', marginBottom: 12 }}>
                Match a single parent order/invoice against multiple installment or settlement receipts on a secondary source.
              </p>
              {aggregationEnabled && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, fontSize: '0.82rem' }}>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Parent Source Alias</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationParentAlias || (uploadedDatasets[0] ? getAlias(uploadedDatasets[0].id, 0) : '')}
                      onChange={(e) => setAggregationParentAlias(e.target.value)}
                      placeholder="e.g. erp, invoice"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Child / Installments Alias</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationChildAlias || (uploadedDatasets[1] ? getAlias(uploadedDatasets[1].id, 1) : '')}
                      onChange={(e) => setAggregationChildAlias(e.target.value)}
                      placeholder="e.g. gateway, bank"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Parent Key Field</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationParentKey}
                      onChange={(e) => setAggregationParentKey(e.target.value)}
                      placeholder="e.g. id, invoice_id"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Child Grouping Key</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationChildGroupKey}
                      onChange={(e) => setAggregationChildGroupKey(e.target.value)}
                      placeholder="e.g. parent_id, order_id"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Parent Amount Field</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationParentAmountField}
                      onChange={(e) => setAggregationParentAmountField(e.target.value)}
                      placeholder="e.g. total_amount, amount"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Child Installment Amount Field</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationChildAmountField}
                      onChange={(e) => setAggregationChildAmountField(e.target.value)}
                      placeholder="e.g. installment_amount, amount"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Child Receipt ID Field (optional)</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationChildReceiptIdField}
                      onChange={(e) => setAggregationChildReceiptIdField(e.target.value)}
                      placeholder="e.g. receipt_id, txn_id"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 2 }}>Sum Tolerance (±)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      className="form-input"
                      style={{ width: '100%', padding: '4px 8px' }}
                      value={aggregationNumericTolerance}
                      onChange={(e) => setAggregationNumericTolerance(parseFloat(e.target.value) || 0)}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Live Rule Dry-Run / Preview Panel */}
            <div className="card" style={{ padding: '16px', marginBottom: 24, border: '1px solid var(--accent-border, var(--border-color))' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Sparkles size={16} className="text-accent" /> Live Rule Impact Dry-Run &amp; Simulation
                  </h4>
                  <p className="text-dim" style={{ fontSize: '0.82rem', margin: '2px 0 0 0' }}>
                    Evaluate your active rules against uploaded sources to view anticipated pass rates before executing.
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => void handlePreviewRules()}
                  disabled={previewingRules}
                >
                  {previewingRules ? <span className="spinner" /> : <Eye size={14} />}
                  Preview Rule Impact
                </button>
              </div>

              {previewError && (
                <div className="alert alert-error" style={{ marginBottom: 12 }}>
                  <AlertCircle size={15} />
                  <span>{previewError}</span>
                </div>
              )}

              {rulePreviewResult && (
                <div style={{ backgroundColor: 'var(--bg-subtle)', borderRadius: 'var(--radius-sm)', padding: '12px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 12 }}>
                    <div>
                      <span className="metric-label" style={{ fontSize: '0.75rem' }}>Evaluated</span>
                      <span className="metric-value" style={{ fontSize: '1.1rem' }}>
                        {rulePreviewResult.total_evaluated}
                      </span>
                    </div>
                    <div>
                      <span className="metric-label" style={{ fontSize: '0.75rem' }}>Projected Passes</span>
                      <span className="metric-value text-success" style={{ fontSize: '1.1rem' }}>
                        {rulePreviewResult.passed_count}
                      </span>
                    </div>
                    <div>
                      <span className="metric-label" style={{ fontSize: '0.75rem' }}>Projected Exceptions</span>
                      <span className="metric-value text-danger" style={{ fontSize: '1.1rem' }}>
                        {rulePreviewResult.exception_count}
                      </span>
                    </div>
                    <div>
                      <span className="metric-label" style={{ fontSize: '0.75rem' }}>Pass Rate</span>
                      <span className="metric-value" style={{ fontSize: '1.1rem' }}>
                        {rulePreviewResult.total_evaluated > 0
                          ? `${((rulePreviewResult.passed_count / rulePreviewResult.total_evaluated) * 100).toFixed(1)}%`
                          : '100%'}
                      </span>
                    </div>
                  </div>

                  {rulePreviewResult.exceptions_by_rule && Object.keys(rulePreviewResult.exceptions_by_rule).length > 0 && (
                    <div style={{ marginBottom: 10 }}>
                      <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-dim)', marginRight: 8 }}>
                        Reason Breakdown:
                      </span>
                      {Object.entries(rulePreviewResult.exceptions_by_rule).map(([k, count]) => (
                        <span key={k} className="badge badge-warning" style={{ fontSize: '0.75rem', marginRight: 6 }}>
                          {k}: {String(count)}
                        </span>
                      ))}
                    </div>
                  )}

                  {rulePreviewResult.sample_discrepancies && rulePreviewResult.sample_discrepancies.length > 0 && (
                    <div style={{ fontSize: '0.8rem' }}>
                      <span style={{ fontWeight: 600, color: 'var(--text-dim)', display: 'block', marginBottom: 4 }}>
                        Sample Exception Records:
                      </span>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {rulePreviewResult.sample_discrepancies.slice(0, 3).map((item, idx) => (
                          <div
                            key={idx}
                            style={{
                              padding: '6px 8px',
                              backgroundColor: 'var(--bg-card)',
                              borderRadius: 'var(--radius-xs)',
                              border: '1px solid var(--border-color)',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                            }}
                          >
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem' }}>
                              {item.key ? JSON.stringify(item.key) : `Row ${item.source_row ?? idx + 1}`}
                            </span>
                            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                              <StatusBadge status={item.status} />
                              <span className="text-dim" style={{ fontSize: '0.75rem' }}>
                                {item.reason || item.message}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {runError && (
              <div className="alert alert-error" style={{ marginBottom: 16 }}>
                <AlertCircle size={16} />
                <span>{runError}</span>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setCurrentStep(2)}>
                                <ChevronLeft size={16} /> {mode === 'organization' ? 'Back to file setup' : 'Back to Blueprint'}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void handleExecuteVerification()}
                disabled={running || Boolean(roleBlocker) || Boolean(worksheetBlocker)}
              >
                {running ? <span className="spinner" /> : <Play size={16} />}
                Execute Reconciliation Run
              </button>
            </div>

            {(roleBlocker || worksheetBlocker) && !runError && (
              <div className="alert alert-error" style={{ marginTop: 12 }}>
                <AlertCircle size={16} />
                <span>{roleBlocker || worksheetBlocker}</span>
              </div>
            )}
          </div>
        )}

        {/* ================= STEP 4: EXCEPTION GRID ================= */}
        {currentStep === 4 && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <TableProperties size={18} className="text-accent" />{' '}
                  {mode === 'organization' ? 'Step 4: Verification Results' : 'Step 4: Multi-Source Exception Grid & Lineage'}
                </h3>
                <p className="text-dim" style={{ margin: '4px 0 0 0', fontSize: '0.85rem' }}>
                  {mode === 'organization'
                    ? `Review what matched and what differs. Every difference shows the file and row it came from.`
                    : 'Inspect cross-source match statuses and trace full row indices across all ' + uploadedDatasets.length + ' participating files.'}
                </p>
              </div>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => setCurrentStep(5)}
              >
                Proceed to Sign-off <ArrowRight size={15} />
              </button>
            </div>

            {/* Quick Metrics Bar */}
            {verificationResponse && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(4, 1fr)',
                  gap: 12,
                  marginBottom: 16,
                  backgroundColor: 'var(--bg-subtle)',
                  padding: '12px',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <div>
                  <span className="metric-label">Total Evaluated</span>
                  <span className="metric-value" style={{ fontSize: '1.2rem' }}>
                    {verificationResponse.results.length.toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="metric-label">Identical Matches</span>
                  <span className="metric-value text-success" style={{ fontSize: '1.2rem' }}>
                    {verificationResponse.summary.identical_matches.toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="metric-label">Field Mismatches</span>
                  <span className="metric-value text-warning" style={{ fontSize: '1.2rem' }}>
                    {verificationResponse.summary.field_mismatches.toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="metric-label">Missing Across Sources</span>
                  <span className="metric-value text-danger" style={{ fontSize: '1.2rem' }}>
                    {(
                      verificationResponse.summary.unmatched_source_records +
                      verificationResponse.summary.unmatched_target_records
                    ).toLocaleString()}
                  </span>
                </div>
              </div>
            )}

            {/* Batch 6 (organization mode): Verification Coverage panel with explicit
                metric definitions. Record counts and attribute counts use distinct
                denominators and are never mixed. */}
            {mode === 'organization' && verificationResponse && (
              <div
                style={{
                  backgroundColor: 'var(--bg-subtle)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-sm)',
                  padding: 12,
                  marginBottom: 16,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <strong style={{ fontSize: '0.9rem' }}>Verification Coverage</strong>
                  <span className="text-dim" style={{ fontSize: '0.78rem' }}>
                    Records and attribute pairs are counted separately — never mixed.
                  </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10 }}>
                  <div>
                    <span className="metric-label">Attribute Comparisons Completed</span>
                    <span className="metric-value text-success" style={{ fontSize: '1.1rem' }}>
                      {(verificationResponse.summary.attribute_comparisons_completed ?? 0).toLocaleString()}
                    </span>
                    <div className="text-dim" style={{ fontSize: '0.72rem', marginTop: 2 }}>
                      record-attribute pairs with ≥1 actual comparison
                    </div>
                  </div>
                  <div>
                    <span className="metric-label">Attributes Not Checked</span>
                    <span className="metric-value text-warning" style={{ fontSize: '1.1rem' }}>
                      {(verificationResponse.summary.attributes_not_checked ?? 0).toLocaleString()}
                    </span>
                    <div className="text-dim" style={{ fontSize: '0.72rem', marginTop: 2 }}>
                      pairs where no comparison could run (owner value blank, or attribute unavailable)
                    </div>
                  </div>
                  <div>
                    <span className="metric-label">Fallback-Matched Records</span>
                    <span className="metric-value" style={{ fontSize: '1.1rem' }}>
                      {(verificationResponse.summary.fallback_matched_records ?? 0).toLocaleString()}
                    </span>
                    <div className="text-dim" style={{ fontSize: '0.72rem', marginTop: 2 }}>
                      matched via a fallback key (subset of total — not double-counted)
                    </div>
                  </div>
                  <div>
                    <span className="metric-label">Duplicate / Missing Records</span>
                    <span className="metric-value text-danger" style={{ fontSize: '1.1rem' }}>
                      {(
                        verificationResponse.summary.unmatched_source_records +
                        verificationResponse.summary.unmatched_target_records +
                        verificationResponse.summary.duplicate_target_keys_count +
                        verificationResponse.summary.duplicate_source_keys_count
                      ).toLocaleString()}
                    </span>
                    <div className="text-dim" style={{ fontSize: '0.72rem', marginTop: 2 }}>
                      excluded from attribute-comparison denominators
                    </div>
                  </div>
                  <div>
                    <span className="metric-label">Invalid Identity Keys</span>
                    <span className="metric-value text-warning" style={{ fontSize: '1.1rem' }}>
                      {(verificationResponse.summary.invalid_key_records ?? 0).toLocaleString()}
                    </span>
                    <div className="text-dim" style={{ fontSize: '0.72rem', marginTop: 2 }}>
                      records with blank/missing key components — listed for review, never auto-matched
                    </div>
                  </div>
                </div>
                <div className="text-dim" style={{ fontSize: '0.72rem', marginTop: 8 }}>
                  Definitions: <strong>Completed + Not checked</strong> = (all-present, non-duplicate, valid-key
                  records) × (configured compare attributes). A pair is <strong>Not checked</strong> when the
                  authoritative value is blank, no applicable source carries the attribute, or the record's identity
                  key is invalid — such pairs are never counted as verified. Invalid-key records are surfaced for
                  review and are never auto-matched or labeled duplicates.
                </div>
              </div>
            )}

            {/* Filters Toolbar */}
            <div className="toolbar" style={{ marginBottom: 12 }}>
              <div className="search-box">
                <Search size={15} />
                <input
                  type="text"
                  className="form-input"
                  placeholder="Search by key values…"
                  value={searchKey}
                  onChange={(e) => setSearchKey(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Filter size={15} className="text-dim" />
                <select
                  className="form-select filter-select"
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                >
                  <option value="all">All categories</option>
                  <option value="none">Identical</option>
                  <option value="field_mismatch">Field mismatches</option>
                  <option value="missing_record">Missing records</option>
                  <option value="duplicate_key">Duplicate keys</option>
                  <option value="needs_review">Needs review (invalid identity key)</option>
                  <option value="aggregation_mismatch">Aggregation mismatches</option>
                  <option value="rule_violation">Rule violations</option>
                </select>

                <select
                  className="form-select filter-select"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <option value="all">All statuses</option>
                  <option value="identical">Identical</option>
                  <option value="field_mismatch">Field mismatch</option>
                  <option value="missing_in_target">Missing in target</option>
                  <option value="missing_in_source">Missing in primary</option>
                  <option value="partial_payment">Partial payment</option>
                  <option value="overpayment">Overpayment</option>
                  <option value="unmatched_split_record">Orphan split record</option>
                  <option value="duplicate_receipt">Duplicate receipt</option>
                </select>
              </div>
            </div>

            {/* Batch 5/6 (multi-primary only): strip showing which file is authoritative
                for each compared attribute, so ownership is visible on the results page. */}
            {mode === 'organization' && multiPrimary && comparedAttributes && comparedAttributes.length > 0 && (
              <div
                style={{
                  display: 'flex',
                  gap: 6,
                  flexWrap: 'wrap',
                  alignItems: 'center',
                  marginBottom: 12,
                  fontSize: '0.8rem',
                }}
              >
                <span className="text-dim">Authoritative source per field:</span>
                {comparedAttributes.map((attr) => {
                  const ownerDs = uploadedDatasets.find(
                    (ds) => fieldOwners[attr]
                      ? ds.id === fieldOwners[attr] && Boolean(columnMappings[ds.id]?.[attr]?.column)
                      : ds.isPrimary && Boolean(columnMappings[ds.id]?.[attr]?.column),
                  );
                  const ownerFile = ownerDs
                    ? ownerDs.label || ownerDs.name
                    : null;
                  return (
                    <span key={attr} className="badge" style={{ backgroundColor: 'var(--bg-subtle)', fontSize: '0.75rem' }}>
                      <strong>{attr}</strong>
                      {ownerFile ? ` ← ${ownerFile}` : ' ← default (first primary)'}
                    </span>
                  );
                })}
              </div>
            )}

            {/* Exception Grid Table */}
            <div className="table-container" style={{ border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', marginBottom: 20 }}>
              <table className="data-table" style={{ width: '100%', fontSize: '0.85rem' }}>
                <thead>
                  <tr>
                    <th style={{ width: 140 }}>Key Values</th>
                    <th style={{ width: 130 }}>Match Status</th>
                    <th>Source Lineage (Row # by Source)</th>
                    <th>Differences / Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredResults.length === 0 ? (
                    <tr>
                      <td colSpan={4} style={{ textAlign: 'center', padding: '36px' }}>
                        No records match your filters.
                      </td>
                    </tr>
                  ) : (
                    filteredResults.slice(0, 50).map((row) => (
                      <tr key={row.id}>
                        <td>
                          <code className="key-code">{JSON.stringify(row.key_values)}</code>
                        </td>
                        <td>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            <StatusBadge status={row.match_status} />
                            {/* Batch 6: fallback identity lineage. Identity matching is
                                separate from attribute verification — this badge explains
                                HOW the record was matched, not whether it passed. */}
                            {row.lineage?.matching_method === 'fallback_key' && (
                              <span
                                className="badge badge-accent"
                                style={{ fontSize: '0.72rem', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                                title={
                                  `Matched via fallback key #${row.lineage.fallback_key_index ?? '—'} ` +
                                  `[${(row.lineage.fallback_key || []).join(', ')}] = ` +
                                  `${JSON.stringify(row.lineage.fallback_values ?? {})}` +
                                  ((row.lineage.fallback_columns && Object.keys(row.lineage.fallback_columns).length > 0)
                                    ? ` (source columns: ${JSON.stringify(row.lineage.fallback_columns)})`
                                    : '')
                                }
                              >
                                Fallback key
                                {row.lineage.fallback_key_index != null ? ` #${row.lineage.fallback_key_index}` : ''}
                              </span>
                            )}
                          </div>
                        </td>
                        <td>
                          {row.source_row_indices ? (
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                              {Object.entries(row.source_row_indices).map(([alias, rIdx]) => (
                                <span
                                  key={alias}
                                  className="badge"
                                  style={{
                                    backgroundColor: rIdx ? 'var(--bg-card-hover)' : 'var(--danger-soft)',
                                    color: rIdx ? 'var(--text-main)' : 'var(--danger-text)',
                                    fontFamily: 'var(--font-mono)',
                                    fontSize: '0.75rem',
                                  }}
                                >
                                  <strong>{alias}:</strong> {rIdx ? `Row ${rIdx}` : 'Missing'}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-dim">Row {row.source_row_number ?? '—'}</span>
                          )}
                        </td>
                        <td>
                          {row.child_records && row.child_records.length > 0 && (
                            <div style={{ marginBottom: 6 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                <span className="badge badge-accent" style={{ fontSize: '0.75rem' }}>
                                  {row.child_records.length} Split Installments
                                </span>
                                {row.aggregated_amount != null && row.expected_amount != null && (
                                  <span style={{ fontSize: '0.78rem', fontFamily: 'var(--font-mono)' }}>
                                    Sum: <strong>${row.aggregated_amount.toFixed(2)}</strong> (Parent: ${row.expected_amount.toFixed(2)})
                                  </span>
                                )}
                              </div>
                              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                {row.child_records.map((c, i) => (
                                  <span
                                    key={i}
                                    className="badge"
                                    style={{
                                      backgroundColor: 'var(--bg-subtle)',
                                      fontSize: '0.72rem',
                                      padding: '2px 6px',
                                      fontFamily: 'var(--font-mono)',
                                    }}
                                  >
                                    #{c.source_row_index} {c.receipt_id ? `rcpt:${c.receipt_id}` : `rec:${c.record_id}`}: ${c.amount}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                          {(() => {
                            // Batch 6: explicit per-attribute statuses derived ONLY from
                            // backend-provided fields — never inferred from display text.
                            const unverified = row.unverified_fields || [];
                            const mismatchedFields = (row.field_differences || []).map((d) => d.field_name);
                            // Verified = configured compare attributes that are neither
                            // mismatched nor explicitly not checked.
                            const verifiedFields = (comparedAttributes || []).filter(
                              (attr) => !unverified.includes(attr) && !mismatchedFields.includes(attr),
                            );
                            const hasAny =
                              verifiedFields.length > 0 || mismatchedFields.length > 0 || unverified.length > 0;
                            const chip = (label: string, cls: string, title: string) => (
                              <span
                                key={label}
                                className={`badge ${cls}`}
                                style={{ fontSize: '0.72rem' }}
                                title={title}
                              >
                                {label}
                              </span>
                            );
                            return (
                              <div>
                                {hasAny && (
                                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 4 }}>
                                    {verifiedFields.length > 0 &&
                                      chip(`✓ Verified: ${verifiedFields.length}`, 'badge-success', `Verified: ${verifiedFields.join(', ')}`)}
                                    {mismatchedFields.length > 0 &&
                                      chip(`✗ Mismatched: ${mismatchedFields.length}`, 'badge-danger', `Mismatched: ${[...new Set(mismatchedFields)].join(', ')}`)}
                                    {unverified.length > 0 &&
                                      chip(
                                        `Not checked: ${unverified.length}`,
                                        'badge-warning',
                                        `Not checked — the authoritative value was blank or the attribute was unavailable: ${unverified.join(', ')}. This attribute is NOT verified.`,
                                      )}
                                  </div>
                                )}
                                {row.field_differences && row.field_differences.length > 0 ? (
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                    {row.field_differences.map((d, i) => (
                                      <div key={i} style={{ fontSize: '0.78rem' }}>
                                        <strong className="text-accent">{d.field_name}:</strong>{' '}
                                        <span>{String(d.source_value)}</span> ≠{' '}
                                        <span style={{ color: 'var(--warning-text)' }}>{String(d.target_value)}</span>
                                      </div>
                                    ))}
                                  </div>
                                ) : unverified.length > 0 ? (
                                  <span className="text-dim" style={{ fontSize: '0.78rem' }}>
                                    {unverified.map((f) => (
                                      <div key={f}>'{f}' could not be checked for this record — no comparison was performed (not verified).</div>
                                    ))}
                                  </span>
                                ) : (
                                  <span className="text-dim">{row.message || 'Identical match'}</span>
                                )}
                              </div>
                            );
                          })()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setCurrentStep(3)}>
                <ChevronLeft size={16} /> Back to Rules
              </button>
              <button type="button" className="btn btn-primary" onClick={() => setCurrentStep(5)}>
                Proceed to Sign-off <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* ================= STEP 5: SIGN-OFF ================= */}
        {currentStep === 5 && (
          <div>
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem', display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileCheck size={18} className="text-accent" />{' '}
                  {mode === 'organization' ? 'Step 5: Review & Download Results' : 'Step 5: Run Sign-off, Audit Entry & Exports'}
              </h3>
              <p className="text-dim" style={{ margin: '4px 0 0 0', fontSize: '0.85rem' }}>
                {mode === 'organization'
                  ? 'Save a record of this verification and download a spreadsheet report of the differences.'
                  : 'Complete the reconciliation audit entry, verify final metrics, and export audit-ready reports.'}
              </p>
            </div>

            {verificationResponse && (
              <div
                className="card"
                style={{
                  padding: '20px',
                  marginBottom: 24,
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border-color)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                  <ShieldCheck size={24} className="text-success" />
                  <div>
                    <h4 style={{ margin: 0, fontSize: '1.05rem' }}>{mode === 'organization' ? 'Verification Complete' : 'Reconciliation Complete'}</h4>
                    <span className="text-dim" style={{ fontSize: '0.82rem' }}>
                      Aligned across {uploadedDatasets.length} sources · {verificationResponse.summary.matched_records} matched pairs
                    </span>
                  </div>
                </div>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                    gap: 12,
                    marginBottom: 20,
                  }}
                >
                  {Object.entries(verificationResponse.records_by_source || {}).map(([alias, count]) => (
                    <div key={alias} className="metric-card flat" style={{ padding: '10px 14px' }}>
                      <span className="metric-label">{alias} records</span>
                      <span className="metric-value" style={{ fontSize: '1.15rem' }}>
                        {count.toLocaleString()}
                      </span>
                    </div>
                  ))}
                  <div className="metric-card flat" style={{ padding: '10px 14px' }}>
                    <span className="metric-label">Identical Matches</span>
                    <span className="metric-value text-success" style={{ fontSize: '1.15rem' }}>
                      {verificationResponse.summary.identical_matches.toLocaleString()}
                    </span>
                  </div>
                  <div className="metric-card flat" style={{ padding: '10px 14px' }}>
                    <span className="metric-label">Discrepancies</span>
                    <span className="metric-value text-danger" style={{ fontSize: '1.15rem' }}>
                      {verificationResponse.summary.total_discrepancies.toLocaleString()}
                    </span>
                  </div>
                </div>

                {/* Export Report Actions */}
                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 16, marginBottom: 16 }}>
                  <label style={{ fontSize: '0.9rem', fontWeight: 600, display: 'block', marginBottom: 10 }}>
                    Export Discrepancy &amp; Reconciliation Reports:
                  </label>
                  <div style={{ display: 'flex', gap: 10 }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void handleExport('csv')}
                      disabled={Boolean(exportingFormat)}
                    >
                      <Download size={14} /> CSV Report
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void handleExport('xlsx')}
                      disabled={Boolean(exportingFormat)}
                    >
                      <Download size={14} /> Excel Spreadsheet
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void handleExport('json')}
                      disabled={Boolean(exportingFormat)}
                    >
                      <Download size={14} /> JSON Dataset
                    </button>
                  </div>
                </div>

                {/* Sign-off Form */}
                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 16 }}>
                  <label style={{ fontSize: '0.9rem', fontWeight: 600, display: 'block', marginBottom: 8 }}>
                    Sign-off Notes / Auditor Attestation:
                  </label>
                  <textarea
                    className="form-textarea"
                    rows={3}
                    placeholder="e.g. Reviewed multi-source exceptions between ERP, Bank, and Gateway. Approved differences within tolerance."
                    value={signOffNote}
                    onChange={(e) => setSignOffNote(e.target.value)}
                    disabled={isSignedOff}
                    style={{ width: '100%', marginBottom: 12, fontSize: '0.85rem' }}
                  />
                  {!isSignedOff ? (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => setIsSignedOff(true)}
                    >
                      <CheckCircle2 size={16} /> Sign-off &amp; Seal Reconciliation
                    </button>
                  ) : (
                    <div className="alert alert-success" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <CheckCircle2 size={16} />
                      <strong>Reconciliation signed-off and committed to audit record.</strong>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setCurrentStep(4)}>
                <ChevronLeft size={16} /> Back to Exception Grid
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setCurrentStep(1);
                  setIsSignedOff(false);
                }}
              >
                <RotateCcw size={15} /> Start New Reconciliation
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Quarantine Drawer Modal if triggered */}
      {drawerFile && (
        <ProfilingQuarantineDrawer
          projectId={project.id}
          fileId={drawerFile.id}
          filename={drawerFile.name}
          isOpen={Boolean(drawerFile)}
          onClose={() => setDrawerFile(null)}
        />
      )}
    </div>
  );
};
