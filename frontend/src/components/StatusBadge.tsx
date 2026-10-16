import React from 'react';

interface StatusMeta {
  label: string;
  className: string;
}

/**
 * Canonical status labels/styling for pipeline, file, run, and reconciliation
 * statuses exposed by the backend (see backend/app/services).
 */
const STATUS_META: Record<string, StatusMeta> = {
  // Verification run statuses
  pending: { label: 'Pending', className: 'badge-pending' },
  running: { label: 'Processing', className: 'badge-running' },
  processing: { label: 'Processing', className: 'badge-processing' },
  completed: { label: 'Completed', className: 'badge-completed' },
  completed_with_warnings: { label: 'Requires review', className: 'badge-requires_review' },
  requires_review: { label: 'Requires review', className: 'badge-requires_review' },
  failed: { label: 'Failed', className: 'badge-failed' },
  // Source file statuses
  uploaded: { label: 'Uploaded', className: 'badge-uploaded' },
  preprocessed: { label: 'Preprocessed', className: 'badge-preprocessed' },
  preprocessing_failed: { label: 'Preprocessing failed', className: 'badge-preprocessing_failed' },
  // Discrepancy categories
  none: { label: 'Identical', className: 'badge-identical' },
  field_mismatch: { label: 'Field mismatch', className: 'badge-field_mismatch' },
  missing_record: { label: 'Missing record', className: 'badge-missing_record' },
  duplicate_key: { label: 'Duplicate key', className: 'badge-duplicate_key' },
  schema_mismatch: { label: 'Schema mismatch', className: 'badge-schema_mismatch' },
  // Match statuses
  identical: { label: 'Identical', className: 'badge-identical' },
  missing_in_target: { label: 'Missing in target', className: 'badge-missing_in_target' },
  missing_in_source: { label: 'Missing in source', className: 'badge-missing_in_source' },
  duplicate_key_source: { label: 'Duplicate in source', className: 'badge-duplicate_key_source' },
  duplicate_key_target: { label: 'Duplicate in target', className: 'badge-duplicate_key_target' },
  duplicate_key_both: { label: 'Duplicate in both', className: 'badge-duplicate_key_both' },
  ambiguous_duplicate: { label: 'Ambiguous duplicate', className: 'badge-ambiguous_duplicate' },
};

interface StatusBadgeProps {
  status?: string | null;
  /** Optional override for the visible label. */
  label?: string;
  /** Show a leading status dot. */
  dot?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, dot = true }) => {
  if (!status) {
    return <span className="badge badge-neutral">—</span>;
  }
  const meta = STATUS_META[status] ?? { label: status, className: 'badge-neutral' };
  return (
    <span className={`badge ${meta.className}`}>
      {dot && <span className="badge-dot" aria-hidden="true" />}
      {label ?? meta.label}
    </span>
  );
};
