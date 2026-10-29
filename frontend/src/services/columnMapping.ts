/**
 * Batch 3: deterministic, explainable column-mapping suggestions for
 * Organization Verification. Pure functions — no React, no API calls.
 *
 * Suggestion model:
 *  - 'suggested'          → exact normalized-name match (safe to auto-apply, still visible/editable)
 *  - 'needs_confirmation' → matched only via the explicit synonym dictionary; NEVER auto-submitted
 *  - 'confirmed'          → user accepted or chose the mapping manually
 *  - not mapped           → the attribute will simply not be compared (never counted as verified)
 */

import type { ColumnMappingEntry, FileColumnMappings, UploadedDataset } from '../types';

/** Small, explicit synonym dictionary. Keys are canonical attribute names; values are
 *  additional normalized column names that may denote the same attribute. Matches via
 *  this dictionary always require user confirmation — they are never auto-applied. */
export const COLUMN_SYNONYMS: Record<string, string[]> = {
  student_id: ['student_number', 'studentno', 'studentid'],
  enrollment_number: ['enrolment_number', 'enrollment_no', 'enrolment_no', 'enrol_no', 'enrolment', 'enrollment', 'enrol'],
  student_name: ['full_name', 'name_of_student'],
  course: ['course_name', 'program', 'programme', 'course_title'],
  batch_year: ['batch', 'batchyear', 'year'],
  hostel_name: ['hostel'],
  block: ['hostel_block', 'block_name'],
  room_number: ['room', 'room_no', 'roomno'],
};

/** Normalize a column name the same way the backend's normalize_column_name does
 *  (lower snake case, non-alphanumerics collapsed to underscores). */
export const normalizeColumn = (name: string): string =>
  name
    .replace(/(.)([A-Z][a-z]+)/g, '$1_$2')
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase();

/** Canonical attributes under consideration: the union of normalized column names
 *  across all uploaded files, minus the unified matching keys (keys are excluded
 *  from field comparison by the engine). */
export const collectCanonicalAttributes = (datasets: UploadedDataset[], unifiedKeys: string[]): string[] => {
  const keys = new Set(unifiedKeys.map((k) => k.trim()).filter(Boolean));
  const attrs = new Set<string>();
  datasets.forEach((ds) => {
    ds.profile?.columns.forEach((col) => {
      const norm = normalizeColumn(col.normalized_name);
      if (norm && !keys.has(norm) && !keys.has(col.normalized_name)) attrs.add(norm);
    });
  });
  return Array.from(attrs).sort();
};

/** Suggest a column mapping for every canonical attribute in one file. */
export const suggestMappingsForFile = (
  dataset: UploadedDataset,
  attributes: string[],
): FileColumnMappings => {
  const byNorm = new Map<string, string>();
  dataset.profile?.columns.forEach((col) => {
    const norm = normalizeColumn(col.normalized_name);
    if (!byNorm.has(norm)) byNorm.set(norm, col.normalized_name); // keep first; backend dedupes names
  });

  const result: FileColumnMappings = {};
  attributes.forEach((attr) => {
    const exact = byNorm.get(attr);
    if (exact) {
      result[attr] = { column: exact, state: 'suggested' };
      return;
    }
    const synonyms = COLUMN_SYNONYMS[attr] || [];
    const synonymMatch = dataset.profile?.columns.find((col) =>
      synonyms.includes(normalizeColumn(col.normalized_name)),
    );
    if (synonymMatch) {
      result[attr] = { column: synonymMatch.normalized_name, state: 'needs_confirmation' };
    }
    // else: leave undefined → not mapped → not compared.
  });
  return result;
};

/** Build the complete initial mapping state for all files (fills only missing files). */
export const buildAllSuggestions = (
  datasets: UploadedDataset[],
  unifiedKeys: string[],
  existing: Record<string, FileColumnMappings>,
): Record<string, FileColumnMappings> => {
  const attributes = collectCanonicalAttributes(datasets, unifiedKeys);
  const next: Record<string, FileColumnMappings> = { ...existing };
  datasets.forEach((ds) => {
    if (!next[ds.id]) next[ds.id] = suggestMappingsForFile(ds, attributes);
  });
  return next;
};

/** Attributes that will actually be compared: mapped (suggested or confirmed) in the
 *  primary source AND in every other participating file, excluding unified keys. */
export const computeComparedAttributes = (
  datasets: UploadedDataset[],
  mappings: Record<string, FileColumnMappings>,
  unifiedKeys: string[],
): string[] => {
  if (datasets.length === 0) return [];
  const keys = new Set(unifiedKeys.map((k) => k.trim()).filter(Boolean));
  const primary = datasets.find((d) => d.isPrimary) || datasets[0];
  const primaryMap = mappings[primary.id] || {};
  const attrs = Object.entries(primaryMap)
    .filter(([attr, entry]) => {
      if (!entry?.column || keys.has(attr)) return false;
      return entry.state === 'confirmed' || entry.state === 'suggested';
    })
    .map(([attr]) => attr)
    .filter((attr) =>
      datasets.every((ds) => {
        if (ds.id === primary.id) return true;
        const m = mappings[ds.id]?.[attr];
        return Boolean(m?.column) && (m!.state === 'confirmed' || m!.state === 'suggested');
      }),
    );
  return attrs.sort();
};

/** Columns already consumed by another attribute (or used as a key column) in a file —
 *  used to disable options and prevent ambiguous duplicate assignments in the UI. */
export const usedColumnsForFile = (
  fileId: string,
  mappings: Record<string, FileColumnMappings>,
  exceptAttr?: string,
): Set<string> => {
  const used = new Set<string>();
  const fileMap = mappings[fileId] || {};
  Object.entries(fileMap).forEach(([attr, entry]) => {
    if (attr !== exceptAttr && entry?.column) used.add(entry.column);
  });
  return used;
};

/**
 * Batch 5 (multi-primary): compared attributes only need to be mapped in at least
 * two sources — each attribute is compared against its configured owner, and the
 * engine skips sources that do not carry the attribute. Unmapped attributes are
 * still never counted as verified.
 */
export const computeComparedAttributesMultiPrimary = (
  datasets: UploadedDataset[],
  mappings: Record<string, FileColumnMappings>,
  unifiedKeys: string[],
): string[] => {
  const keys = new Set(unifiedKeys.map((k) => k.trim()).filter(Boolean));
  const counts = new Map<string, number>();
  datasets.forEach((ds) => {
    const fileMap = mappings[ds.id] || {};
    Object.entries(fileMap).forEach(([attr, entry]) => {
      if (!entry?.column || keys.has(attr)) return;
      if (entry.state === 'confirmed' || entry.state === 'suggested') {
        counts.set(attr, (counts.get(attr) || 0) + 1);
      }
    });
  });
  return [...counts.entries()].filter(([, n]) => n >= 2).map(([attr]) => attr).sort();
};

/**
 * Batch 5: build the outgoing field_ownership payload. Only entries whose owner
 * is an uploaded source that maps the attribute (suggested/confirmed) are sent;
 * identity key attributes can never have owners.
 */
export const buildFieldOwnershipPayload = (
  datasets: UploadedDataset[],
  mappings: Record<string, FileColumnMappings>,
  fieldOwners: Record<string, string>,
  unifiedKeys: string[],
  aliasFor: (fileId: string) => string,
): Record<string, string> | undefined => {
  const keys = new Set(unifiedKeys.map((k) => k.trim()).filter(Boolean));
  const out: Record<string, string> = {};
  Object.entries(fieldOwners).forEach(([attr, fileId]) => {
    if (!attr || keys.has(attr)) return;
    const ds = datasets.find((d) => d.id === fileId);
    if (!ds) return;
    const entry = mappings[ds.id]?.[attr];
    if (!entry?.column || (entry.state !== 'confirmed' && entry.state !== 'suggested')) return;
    out[attr] = aliasFor(ds.id);
  });
  return Object.keys(out).length > 0 ? out : undefined;
};

/**
 * Batch 4: build the outgoing `fallback_keys` payload from the ordered UI state.
 * Only complete, fully-confirmed definitions are sent: every attribute of a
 * fallback must be mapped (suggested or confirmed) in EVERY participating file so
 * the engine can resolve it through field_mapping. Definitions that duplicate the
 * primary key combination or each other are dropped. Returns undefined when no
 * valid fallback remains (existing requests stay unchanged).
 */
export const buildFallbackPayload = (
  datasets: UploadedDataset[],
  mappings: Record<string, FileColumnMappings>,
  fallbackKeys: string[][],
  unifiedKeys: string[],
): string[][] | undefined => {
  const keySet = [...unifiedKeys].sort().join('\u0000');
  const seen = new Set<string>();
  const out: string[][] = [];
  fallbackKeys.forEach((fb) => {
    const attrs = [...new Set(fb.map((a) => a.trim()).filter(Boolean))];
    if (attrs.length === 0) return;
    // Must not duplicate the primary key combination or an earlier fallback.
    const sig = [...attrs].sort().join('\u0000');
    if (sig === keySet || seen.has(sig)) return;
    // Every attribute must be mapped (suggested/confirmed) in every file.
    const fullyMapped = attrs.every((attr) =>
      datasets.every((ds) => {
        const entry = mappings[ds.id]?.[attr];
        return Boolean(entry?.column) && (entry!.state === 'confirmed' || entry!.state === 'suggested');
      }),
    );
    if (!fullyMapped) return;
    seen.add(sig);
    out.push(attrs);
  });
  return out.length > 0 ? out : undefined;
};

export type { ColumnMappingEntry };
