/**
 * VerifyGrid TypeScript Domain Models matching FastAPI Pydantic Schemas
 */

export interface User {
  id: string;
  email: string;
  full_name?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  owner_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
}

export interface SourceFile {
  id: string;
  project_id: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  status: string;
  created_at: string;
}

export interface PreprocessingConfig {
  strip_whitespace?: boolean;
  normalize_column_names?: boolean;
  null_values?: string[];
  normalize_dates?: boolean;
  normalize_numbers?: boolean;
  identifier_columns?: string[];
  max_rows?: number;
  /** Batch 7: exact worksheet name for XLSX preprocessing (see batch 7 report). */
  selected_worksheet?: string | null;
}

export interface ValidationIssue {
  level: 'error' | 'warning' | 'info';
  issue_type: string;
  message: string;
  row_number?: number | null;
  column_name?: string | null;
}

export interface ColumnMetadata {
  original_name: string;
  normalized_name: string;
  detected_type: string;
  null_count: number;
  non_null_count: number;
  sample_values: any[];
}

export interface PreprocessingResult {
  source_file_id: string;
  project_id: string;
  original_filename: string;
  file_type: string;
  total_source_rows: number;
  data_rows_count: number;
  empty_rows_count: number;
  duplicate_rows_count: number;
  columns: ColumnMetadata[];
  column_mapping: Record<string, string>;
  duplicate_record_row_numbers: number[][];
  issues: ValidationIssue[];
  preview_rows: Record<string, any>[];
  /** Batch 7: for XLSX workbooks only — worksheet names in workbook order for
   *  explicit selection. null/undefined for CSV files. */
  sheet_names?: string[] | null;
  /** Batch 7: the worksheet this preprocessing run parsed (XLSX only; null = active sheet). */
  selected_worksheet?: string | null;
}

export type MatchStatus =
  | 'identical'
  | 'field_mismatch'
  | 'missing_in_target'
  | 'missing_in_source'
  | 'duplicate_key_source'
  | 'duplicate_key_target'
  | 'duplicate_key_both'
  | 'ambiguous_duplicate'
  | 'needs_review'
  | 'partial_payment'
  | 'overpayment'
  | 'unmatched_split_record'
  | 'duplicate_receipt';

export type DiscrepancyCategory =
  | 'none'
  | 'field_mismatch'
  | 'missing_record'
  | 'duplicate_key'
  | 'schema_mismatch'
  | 'needs_review'
  | 'aggregation_mismatch'
  | 'rule_violation';

export interface FieldDifference {
  field_name: string;
  source_field: string;
  target_field: string;
  source_value: any;
  target_value: any;
  source_type?: string | null;
  target_type?: string | null;
  difference_type: string;
  reason_code?: string | null;
  confidence_score?: number | null;
  message?: string | null;
}

export interface VerificationResultItem {
  id: string;
  key_values: Record<string, any>;
  match_status: MatchStatus;
  discrepancy_category: DiscrepancyCategory;
  reason_code?: string | null;
  confidence_score?: number | null;
  source_row_number?: number | null;
  target_row_number?: number | null;
  source_row_index?: number | null;
  target_row_index?: number | null;
  source_row_numbers?: number[];
  target_row_numbers?: number[];
  source_file_id?: string | null;
  target_file_id?: string | null;
  lineage?: Record<string, any> | null;
  /** Batch 5: attributes configured but NOT compared for this record (owner blank,
   *  or attribute not carried by a source) — explicitly not verified. */
  unverified_fields?: string[] | null;
  source_row_indices?: Record<string, number | null> | null;
  source_records?: Record<string, Record<string, any> | null> | null;
  missing_in_sources?: string[] | null;
  source_presence?: Record<string, boolean> | null;
  source_record?: Record<string, any> | null;
  target_record?: Record<string, any> | null;
  child_records?: any[] | null;
  aggregated_amount?: number | null;
  expected_amount?: number | null;
  field_differences?: FieldDifference[];
  message?: string | null;
}

export interface VerificationSummary {
  total_source_records: number;
  total_target_records: number;
  matched_records: number;
  identical_matches: number;
  field_mismatches: number;
  records_with_differences?: number;
  needs_review_records?: number;
  unmatched_source_records: number;
  unmatched_target_records: number;
  duplicate_source_records: number;
  duplicate_target_records: number;
  duplicate_source_keys_count: number;
  duplicate_target_keys_count: number;
  conflicting_duplicate_records?: number;
  total_discrepancies: number;
  /** Batch 4: records matched via a fallback key after primary-key matching failed. */
  fallback_matched_records?: number;
  /** Batch 6: (record, attribute) pairs with ≥1 executed comparison. */
  attribute_comparisons_completed?: number;
  /** Batch 6: (record, attribute) pairs with no executed comparison (owner blank,
   *  attribute unavailable). completed + not_checked = all-present, non-duplicate
   *  records × configured compare attributes. */
  attributes_not_checked?: number;
  /** Batch 8: records with missing/blank/incomplete identity keys — surfaced as
   *  needs_review, never counted as matches or confirmed duplicates. */
  invalid_key_records?: number;
  status: string;
}

export interface VerificationRequest {
  source_file_id: string;
  target_file_id: string;
  key_columns: string[];
  column_mapping?: Record<string, string>;
  compare_columns?: string[] | null;
  ignore_columns?: string[];
  numeric_tolerance?: number;
  ignore_whitespace?: boolean;
  ignore_case?: boolean;
  include_identical?: boolean;
  enable_fuzzy_matching?: boolean;
  fuzzy_match_columns?: string[];
  fuzzy_threshold?: number;
  status_rules?: Record<string, any>;
  preprocessing_config?: PreprocessingConfig | null;
  excluded_source_rows?: number[];
  excluded_target_rows?: number[];
}

export interface VerificationResponse {
  project_id?: string;
  source_file_id?: string;
  target_file_id?: string;
  key_columns: string[];
  column_mapping: Record<string, string>;
  summary: VerificationSummary;
  results: VerificationResultItem[];
  discrepancies: VerificationResultItem[];
  warnings: ValidationIssue[];
  errors: string[];
}

export interface VerificationRun {
  id: string;
  project_id: string;
  source_file_id?: string | null;
  target_file_id?: string | null;
  status: string;
  key_columns: string[];
  column_mapping?: Record<string, string> | null;
  sources?: SourceDefinition[] | null;
  configuration?: Record<string, any> | null;
  summary?: VerificationSummary | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface VerificationRunListResponse {
  total: number;
  items: VerificationRun[];
  skip: number;
  limit: number;
}

export interface DiscrepancyItemResponse {
  id: string;
  run_id: string;
  match_status: MatchStatus;
  discrepancy_category: DiscrepancyCategory;
  key_values: Record<string, any>;
  source_row_number?: number | null;
  target_row_number?: number | null;
  source_row_numbers?: number[] | null;
  target_row_numbers?: number[] | null;
  source_row_indices?: Record<string, number | null> | null;
  source_records?: Record<string, Record<string, any> | null> | null;
  missing_in_sources?: string[] | null;
  source_presence?: Record<string, boolean> | null;
  source_record?: Record<string, any> | null;
  target_record?: Record<string, any> | null;
  field_differences?: FieldDifference[] | null;
  message?: string | null;
  created_at: string;
}

export interface DiscrepancyListResponse {
  total: number;
  items: DiscrepancyItemResponse[];
  skip: number;
  limit: number;
}

// --- Batch 2: Data Profiling & Quarantine Types ---

export type QuarantineReasonCode =
  | 'MALFORMED_DATE'
  | 'INVALID_NUMBER'
  | 'DUPLICATE_KEY'
  | 'UNEXPECTED_NEGATIVE_AMOUNT'
  | 'SHIFTED_ROW'
  | 'SCHEMA_DRIFT';

export type QuarantineSeverity = 'WARNING' | 'BLOCKING';

export type ResolutionAction = 'PENDING' | 'EXCLUDE' | 'ACCEPT_AS_VALID';

export interface QuarantinedRecord {
  id: string;
  source_row_index: number;
  column_name: string;
  raw_value: any;
  quarantine_reason: QuarantineReasonCode;
  severity: QuarantineSeverity;
  message: string;
  resolution_action: ResolutionAction;
  resolution_note?: string | null;
  raw_record?: Record<string, any> | null;
}

export interface ColumnProfile {
  column_name: string;
  original_name: string;
  inferred_type: string;
  total_count: number;
  null_count: number;
  null_percentage: number;
  distinct_count: number;
  uniqueness_ratio: number;
  is_candidate_key: boolean;
  sample_values: any[];
  min_value?: any;
  max_value?: any;
  anomalies_count: number;
}

export interface CandidateKeyQuality {
  column_name: string;
  uniqueness_ratio: number;
  duplicate_count: number;
  null_count: number;
  is_viable_key: boolean;
  recommendation: string;
}

export interface PreFlightImpactPreview {
  total_source_rows: number;
  total_quarantined_records: number;
  blocking_quarantine_count: number;
  warning_quarantine_count: number;
  excluded_rows_count: number;
  accepted_rows_count: number;
  eligible_rows_count: number;
  quarantined_rows_count: number;
}

export interface FileProfileSummary {
  file_id: string;
  project_id: string;
  filename: string;
  file_type: string;
  total_rows: number;
  column_count: number;
  columns: ColumnProfile[];
  candidate_keys: CandidateKeyQuality[];
  impact_preview: PreFlightImpactPreview;
  quarantine_records_sample: QuarantinedRecord[];
  created_at: string;
}

export interface QuarantineListResponse {
  file_id: string;
  total_quarantined: number;
  records: QuarantinedRecord[];
  impact_preview: PreFlightImpactPreview;
}

export interface QuarantineResolutionItem {
  source_row_index: number;
  action: ResolutionAction;
  note?: string;
}

export interface QuarantineResolutionRequest {
  resolutions: QuarantineResolutionItem[];
}

export interface QuarantineResolutionResponse {
  file_id: string;
  resolved_count: number;
  excluded_row_indices: number[];
  accepted_row_indices: number[];
  impact_preview: PreFlightImpactPreview;
  quarantined_records: QuarantinedRecord[];
}

// --- Batch 3: Multi-Source Ingestion & Wizard Types ---

export interface SourceDefinition {
  alias: string;
  file_id: string;
  is_primary?: boolean;
  /** Batch 2: optional user-editable display label (backend max 120 chars, trimmed). */
  label?: string | null;
  key_columns: string[];
  field_mapping?: Record<string, string>;
  excluded_row_indices?: number[];
  /** Batch 7: exact worksheet name for XLSX sources (undefined/None = legacy
   *  active-sheet behavior). Ignored by the engine for CSV sources. */
  sheet_name?: string | null;
}

/** Batch 3 (organization mode): per-file column mapping state.
 *  Maps a canonical/unified attribute name to the source column carrying it,
 *  with a transparent confirmation state. Only 'suggested' (exact normalized
 *  match) and 'confirmed' mappings are sent to the engine; 'needs_confirmation'
 *  suggestions are never auto-submitted. */
export type MappingState = 'suggested' | 'needs_confirmation' | 'confirmed';

export interface ColumnMappingEntry {
  column: string | null;
  state: MappingState;
}

/** Mapping state per file: canonical attribute -> column entry. */
export type FileColumnMappings = Record<string, ColumnMappingEntry | undefined>;
/** A dataset held in wizard state for the active session. */
export interface UploadedDataset {
  id: string;
  name: string;
  /** Editable, institution-friendly display label (defaults derived from the filename). */
  label: string;
  /** Explicit source role. Sources of truth for matching remains backend-validated
   *  `is_primary` inside SourceDefinition (exactly one primary until Batch 5). */
  isPrimary: boolean;
  profile?: PreprocessingResult;
  /** Batch 7: user-selected worksheet for XLSX sources. Must be set (org mode)
   *  before the source is eligible for verification. */
  selectedSheet?: string | null;
}

export interface MultiSourceVerificationRequest {
  sources: SourceDefinition[];
  unified_keys: string[];
  compare_attributes?: string[] | null;
  /** Batch 4 (organization mode): ordered fallback matching keys. Each entry is a
   *  list of canonical attribute names (composite supported), resolved per source
   *  through field_mapping. Tried in order when the primary key cannot match. */
  fallback_keys?: string[][] | null;
  /** Batch 5 (organization mode): explicit multi-primary opt-in with per-field
   *  ownership ({unified_attribute -> owner alias}). Legacy requests omit both. */
  multi_primary?: boolean;
  field_ownership?: Record<string, string> | null;
  ignore_attributes?: string[];
  numeric_tolerance?: number;
  ignore_whitespace?: boolean;
  ignore_case?: boolean;
  include_identical?: boolean;
  status_rules?: Record<string, any>;
  rule_config?: VersionedRuleConfig | null;
  preprocessing_config?: PreprocessingConfig | null;
}

export interface MultiSourceKeyRecommendation {
  key_name: string;
  is_composite: boolean;
  overall_score: number;
  overlap_score: number;
  source_columns: Record<string, string[]>;
  uniqueness_by_source: Record<string, number>;
  null_rate_by_source: Record<string, number>;
  recommendation_reason: string;
}

export interface MultiSourceKeyRecommendRequest {
  file_ids: string[];
  aliases?: string[];
}

export interface MultiSourceKeyRecommendResponse {
  recommendations: MultiSourceKeyRecommendation[];
  total_evaluated_columns: number;
}

export interface MultiSourceVerificationResponse {
  project_id: string;
  run_id?: string | null;
  sources: SourceDefinition[];
  unified_keys: string[];
  summary: VerificationSummary;
  records_by_source: Record<string, number>;
  missing_by_source: Record<string, number>;
  results: VerificationResultItem[];
  discrepancies: VerificationResultItem[];
  warnings: any[];
  errors: string[];
}

// --- Batch 4: Advanced Rule Engine & Aggregation Types ---

export type RuleSeverity = 'BLOCKING' | 'WARNING' | 'INFO';

export type PredicateOperator =
  | 'equal'
  | 'not_equal'
  | 'in'
  | 'not_in'
  | 'greater_than'
  | 'less_than'
  | 'greater_equal'
  | 'less_equal'
  | 'between'
  | 'regex'
  | 'is_null'
  | 'is_not_null';

export type ToleranceMode = 'absolute' | 'percentage' | 'both_or' | 'both_and';

export interface WhereCondition {
  field: string;
  operator: PredicateOperator;
  value?: any;
  target_field?: string | null;
  source_alias?: string | null;
  severity?: RuleSeverity;
  description?: string | null;
}

export interface DateWindowRule {
  source_date_field: string;
  target_date_field: string;
  source_alias?: string | null;
  target_alias?: string | null;
  lag_days_before: number;
  lag_days_after: number;
  date_format?: string | null;
  severity?: RuleSeverity;
  description?: string | null;
}

export interface NumericToleranceRule {
  source_amount_field: string;
  target_amount_field: string;
  source_alias?: string | null;
  target_alias?: string | null;
  absolute_tolerance: number;
  percentage_tolerance: number;
  tolerance_mode?: ToleranceMode;
  severity?: RuleSeverity;
  description?: string | null;
}

export interface StatusTransitionRule {
  source_field: string;
  target_field: string;
  source_alias?: string | null;
  target_alias?: string | null;
  allowed_transitions: Record<string, string[]>;
  case_sensitive?: boolean;
  severity?: RuleSeverity;
  description?: string | null;
}

export interface CompoundRule {
  id?: string | null;
  name: string;
  description?: string | null;
  severity?: RuleSeverity;
  conjunction?: 'AND' | 'OR';
  conditions: WhereCondition[];
}

export interface AggregationConfig {
  enabled: boolean;
  parent_source_alias: string;
  child_source_alias: string;
  parent_key: string;
  child_grouping_key: string;
  parent_amount_field: string;
  child_amount_field: string;
  child_receipt_id_field?: string | null;
  child_date_field?: string | null;
  parent_date_field?: string | null;
  numeric_tolerance?: number;
  percentage_tolerance?: number;
  allow_partial_payment?: boolean;
  allow_overpayment?: boolean;
}

export interface VersionedRuleConfig {
  version: string;
  name?: string | null;
  description?: string | null;
  where_conditions: WhereCondition[];
  date_window_rules: DateWindowRule[];
  numeric_tolerance_rules: NumericToleranceRule[];
  status_transition_rules: StatusTransitionRule[];
  custom_rules: CompoundRule[];
  aggregation_config?: AggregationConfig | null;
}

export interface RuleValidateRequest {
  rules: VersionedRuleConfig;
  file_ids?: string[];
  sources?: SourceDefinition[];
}

export interface RuleValidateResponse {
  valid: boolean;
  errors: string[];
  warnings: string[];
  total_rules_checked: number;
  field_resolutions: Record<string, boolean>;
}

export interface RulePreviewRequest {
  rules: VersionedRuleConfig;
  sources: SourceDefinition[];
  unified_keys?: string[] | null;
  sample_size?: number;
}

export interface RulePreviewResponse {
  total_evaluated: number;
  passed_count: number;
  exception_count: number;
  exceptions_by_rule: Record<string, number>;
  exceptions_by_severity: Record<string, number>;
  sample_discrepancies: Array<{
    source_row?: number;
    target_row?: number;
    key?: Record<string, any>;
    status?: string;
    reason?: string;
    message?: string;
    aggregated_amount?: number;
    expected_amount?: number;
    violations?: Array<{
      rule: string;
      severity: string;
      reason_code: string;
      message?: string;
    }>;
  }>;
}



// ===================== Batch 11: Verification Templates =====================

/** Reusable per-source slot of a template. Deliberately has no file binding,
 *  no row indices, and no quarantine state — templates store configuration only. */
export interface TemplateSourceSlot {
  alias: string;
  label?: string | null;
  is_primary: boolean;
  key_columns: string[];
  field_mapping: Record<string, string>;
  /** Batch 7 worksheet selection; revalidated against every new XLSX upload. */
  sheet_name?: string | null;
}

/** Versioned template configuration snapshot (organization mode, schema v1). */
export interface TemplateConfigurationV1 {
  version: 1;
  sources: TemplateSourceSlot[];
  unified_keys: string[];
  compare_attributes?: string[] | null;
  ignore_attributes?: string[];
  numeric_tolerance?: number;
  ignore_whitespace?: boolean;
  ignore_case?: boolean;
  include_identical?: boolean;
  fallback_keys?: string[][] | null;
  multi_primary?: boolean;
  field_ownership?: Record<string, string> | null;
}

export type TemplateMode = 'organization';
export type TemplateVisibility = 'personal';

export interface VerificationTemplate {
  id: string;
  name: string;
  description?: string | null;
  mode: TemplateMode;
  /** Personal-only launch: organization sharing is disabled (deny-by-default). */
  visibility: TemplateVisibility;
  config_version: number;
  configuration: TemplateConfigurationV1;
  source_count: number;
  created_at: string;
  updated_at: string;
}

export interface TemplateApplySourceBinding {
  slot: string;
  file_id: string;
}

export interface TemplateApplyRequest {
  project_id: string;
  sources: TemplateApplySourceBinding[];
}

export interface TemplateValidationIssue {
  slot?: string | null;
  field?: string | null;
  message: string;
}

export interface TemplateValidationReport {
  blocking: boolean;
  issues: TemplateValidationIssue[];
  warnings: string[];
}

export interface TemplateApplyResponse {
  template_id: string;
  project_id: string;
  mode: TemplateMode;
  /** Effective MultiSourceVerificationRequest (file IDs substituted), ready for
   *  the existing verification endpoints. */
  effective_request: MultiSourceVerificationRequest;
  validation_report: TemplateValidationReport;
}
