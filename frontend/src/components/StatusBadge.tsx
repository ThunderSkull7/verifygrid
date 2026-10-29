import React from 'react';
import {
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Copy,
  Clock,
  HelpCircle,
} from 'lucide-react';

interface StatusMeta {
  label: string;
  className: string;
  icon: React.ComponentType<{ size?: number; className?: string; 'aria-hidden'?: boolean | 'true' | 'false'; style?: React.CSSProperties }>;
}

/**
 * Canonical status labels/styling for pipeline, file, run, and reconciliation
 * statuses exposed by the backend (see backend/app/services).
 * Combines distinct semantic color, iconography, and text to satisfy WCAG AA
 * requirement that color alone is never the only differentiator.
 */
const STATUS_META: Record<string, StatusMeta> = {
  // Verification run statuses
  pending: { label: 'Pending', className: 'badge-pending', icon: Clock },
  running: { label: 'Processing', className: 'badge-running', icon: Clock },
  processing: { label: 'Processing', className: 'badge-processing', icon: Clock },
  completed: { label: 'Completed', className: 'badge-completed', icon: CheckCircle2 },
  completed_with_warnings: { label: 'Requires review', className: 'badge-requires_review', icon: AlertTriangle },
  requires_review: { label: 'Requires review', className: 'badge-requires_review', icon: AlertTriangle },
  failed: { label: 'Failed', className: 'badge-failed', icon: AlertCircle },
  // Source file statuses
  uploaded: { label: 'Uploaded', className: 'badge-uploaded', icon: Clock },
  preprocessed: { label: 'Preprocessed', className: 'badge-preprocessed', icon: CheckCircle2 },
  preprocessing_failed: { label: 'Preprocessing failed', className: 'badge-preprocessing_failed', icon: AlertCircle },
  // Match statuses and categories
  none: { label: 'Identical', className: 'badge-identical', icon: CheckCircle2 },
  field_mismatch: { label: 'Field mismatch', className: 'badge-field_mismatch', icon: AlertCircle },
  missing_record: { label: 'Missing record', className: 'badge-missing_record', icon: AlertTriangle },
  duplicate_key: { label: 'Duplicate key', className: 'badge-duplicate_key', icon: Copy },
  schema_mismatch: { label: 'Schema mismatch', className: 'badge-schema_mismatch', icon: AlertCircle },
  needs_review: { label: 'Needs review', className: 'badge-requires_review', icon: AlertTriangle },
  // Match statuses
  identical: { label: 'Identical', className: 'badge-identical', icon: CheckCircle2 },
  missing_in_target: { label: 'Missing in target', className: 'badge-missing_in_target', icon: AlertTriangle },
  missing_in_source: { label: 'Missing in source', className: 'badge-missing_in_source', icon: AlertTriangle },
  duplicate_key_source: { label: 'Duplicate in source', className: 'badge-duplicate_key_source', icon: Copy },
  duplicate_key_target: { label: 'Duplicate in target', className: 'badge-duplicate_key_target', icon: Copy },
  duplicate_key_both: { label: 'Duplicate in both', className: 'badge-duplicate_key_both', icon: Copy },
  ambiguous_duplicate: { label: 'Ambiguous duplicate', className: 'badge-ambiguous_duplicate', icon: Copy },
  // Aggregation & split-payment statuses
  partial_payment: { label: 'Partial Payment', className: 'badge-requires_review', icon: AlertTriangle },
  overpayment: { label: 'Overpayment', className: 'badge-requires_review', icon: AlertTriangle },
  unmatched_split_record: { label: 'Orphan Split', className: 'badge-missing_in_target', icon: AlertTriangle },
  duplicate_receipt: { label: 'Duplicate Receipt', className: 'badge-duplicate_key', icon: Copy },
  aggregation_mismatch: { label: 'Aggregation Mismatch', className: 'badge-field_mismatch', icon: AlertCircle },
  rule_violation: { label: 'Rule Violation', className: 'badge-field_mismatch', icon: AlertCircle },
};

interface StatusBadgeProps {
  status?: string | null;
  /** Optional override for the visible label. */
  label?: string;
  /** Show leading status icon. Default true. */
  dot?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, dot = true }) => {
  if (!status) {
    return <span className="badge badge-neutral">—</span>;
  }
  const meta = STATUS_META[status] ?? { label: status, className: 'badge-neutral', icon: HelpCircle };
  const IconComponent = meta.icon;
  const displayLabel = label ?? meta.label;

  return (
    <span
      className={`badge ${meta.className}`}
      role="status"
      aria-label={`Status: ${displayLabel}`}
    >
      {dot && <IconComponent size={12} aria-hidden={true} style={{ flexShrink: 0 }} />}
      <span>{displayLabel}</span>
    </span>
  );
};
