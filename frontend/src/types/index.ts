/**
 * VerifyGrid TypeScript Domain Models matching FastAPI Pydantic Schemas
 */

export interface User {
  id: string;
  email: string;
  full_name?: string | null;
  role?: string;
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
  rule_id?: string | null;
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
  source_row_indices?: Record<string, number | null> | null;
  source_records?: Record<string, Record<string, any> | null> | null;
  missing_in_sources?: string[] | null;
  source_presence?: Record<string, boolean> | null;
  source_record?: Record<string, any> | null;
  target_record?: Record<string, any> | null;
  child_records?: any[] | null;
  aggregated_amount?: number | null;
  expected_amount?: number | null;
  source_amount?: number | null;
  target_amount?: number | null;
  variance_amount?: number | null;
  exposure_amount?: number | null;
  currency?: string | null;
  severity?: string | null;
  resolution_status?: string | null;
  resolution_note?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
  cluster_id?: string | null;
  cluster_name?: string | null;
  assigned_to?: string | null;
  assigned_at?: string | null;
  side_by_side?: Record<string, any> | null;
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
  status: string;

  // Financial Materiality & Exposure Metrics
  gross_exposure?: number;
  net_variance?: number;
  claimed_amount?: number;
  verified_amount?: number;
  outstanding_amount?: number;
  currency?: string;
  exposure_by_currency?: Record<string, Record<string, number>> | null;
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
  sign_off_status?: string | null;
  sign_off_proposed_by?: string | null;
  sign_off_proposed_by_name?: string | null;
  sign_off_proposal_note?: string | null;
  sign_off_proposed_at?: string | null;
  sign_off_approved_by?: string | null;
  sign_off_approved_by_name?: string | null;
  sign_off_decision_note?: string | null;
  sign_off_decided_at?: string | null;
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
  source_row_index?: number | null;
  target_row_index?: number | null;
  source_row_numbers?: number[] | null;
  target_row_numbers?: number[] | null;
  source_row_indices?: Record<string, number | null> | null;
  source_records?: Record<string, Record<string, any> | null> | null;
  missing_in_sources?: string[] | null;
  source_presence?: Record<string, boolean> | null;
  source_record?: Record<string, any> | null;
  target_record?: Record<string, any> | null;
  child_records?: any[] | null;
  aggregated_amount?: number | null;
  expected_amount?: number | null;
  source_amount?: number | null;
  target_amount?: number | null;
  variance_amount?: number | null;
  exposure_amount?: number | null;
  currency?: string | null;
  severity?: string | null;
  resolution_status?: string | null;
  resolution_note?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
  cluster_id?: string | null;
  cluster_name?: string | null;
  assigned_to?: string | null;
  assigned_at?: string | null;
  side_by_side?: Record<string, any> | null;
  reason_code?: string | null;
  confidence_score?: number | null;
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

export interface FieldComparisonDiff {
  field_name: string;
  source_field?: string | null;
  target_field?: string | null;
  raw_source_value?: any;
  normalized_source_value?: any;
  raw_target_value?: any;
  normalized_target_value?: any;
  is_match: boolean;
  difference_type?: string | null;
  reason_code?: string | null;
  message?: string | null;
}

export interface SideBySideInspectionResponse {
  id: string;
  run_id?: string | null;
  key_values: Record<string, any>;
  match_status: MatchStatus;
  discrepancy_category: DiscrepancyCategory;
  reason_code?: string | null;
  confidence_score?: number | null;
  severity: string;

  source_amount?: number | null;
  target_amount?: number | null;
  variance_amount?: number | null;
  exposure_amount?: number | null;
  currency?: string | null;

  source_row_index?: number | null;
  target_row_index?: number | null;
  source_row_indices?: Record<string, number | null> | null;
  missing_in_sources?: string[] | null;
  source_presence?: Record<string, boolean> | null;

  raw_source_record?: Record<string, any> | null;
  normalized_source_record?: Record<string, any> | null;
  raw_target_record?: Record<string, any> | null;
  normalized_target_record?: Record<string, any> | null;

  field_comparisons: FieldComparisonDiff[];
  failed_rules: Array<{
    rule?: string;
    field?: string;
    description?: string;
    discrepancy_category?: string;
  }>;
  child_records?: any[] | null;
  message?: string | null;
  resolution_status?: string | null;
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
  key_columns: string[];
  field_mapping?: Record<string, string>;
  excluded_row_indices?: number[];
}

export interface MultiSourceVerificationRequest {
  sources: SourceDefinition[];
  unified_keys: string[];
  compare_attributes?: string[] | null;
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

// --- Batch 6: Exception Clustering, Signatures & Bulk Human Review Types ---

export interface ExceptionCluster {
  cluster_id: string;
  cluster_name: string;
  reason_code: string;
  rule_id?: string | null;
  failed_field_names: string[];
  source_alias?: string | null;
  discrepancy_category: string;
  severity: string;
  total_records: number;
  total_exposure: number;
  currency: string;
  root_cause_explanation: string;
  status_counts: Record<string, number>;
  sample_record?: Record<string, any> | null;
  discrepancy_ids?: string[] | null;
  assigned_to?: string | null;
}

export interface ClusterListResponse {
  total_clusters: number;
  total_exceptions: number;
  total_cluster_exposure: number;
  clusters: ExceptionCluster[];
}

export interface ClusterRecordsResponse {
  cluster_id: string;
  cluster_name: string;
  total: number;
  items: DiscrepancyItemResponse[];
  skip: number;
  limit: number;
}

export interface ReviewDecisionRequest {
  decision: string;
  justification: string;
  reviewer_id?: string;
  reviewer_email?: string;
}

export interface ReviewDecisionItem {
  id: string;
  discrepancy_id: string;
  run_id: string;
  decision: string;
  justification: string;
  reviewer_id?: string | null;
  reviewer_email?: string | null;
  previous_status?: string | null;
  new_status: string;
  is_bulk_action: boolean;
  cluster_id?: string | null;
  created_at: string;
}

export interface BulkReviewRequest {
  decision: string;
  justification: string;
  cluster_id?: string;
  discrepancy_ids?: string[];
  max_exposure_threshold?: number;
  allow_blocking_override?: boolean;
}

export interface BulkReviewResponse {
  total_requested: number;
  succeeded_count: number;
  failed_count: number;
  ineligible_count: number;
  succeeded_ids: string[];
  failed_records: Array<{ id: string; reason: string }>;
  message: string;
}

export interface AssignmentRequest {
  reviewer_id: string;
  reviewer_email?: string;
  cluster_id?: string;
  discrepancy_ids?: string[];
}

export interface AssignmentResponse {
  assigned_count: number;
  reviewer_id: string;
  discrepancy_ids: string[];
  message: string;
}

// --- Batch 7: Maker–Checker Governance & Tamper-Evident Audit Types ---

export type UserRole = 'MAKER' | 'CHECKER' | 'ADMIN' | 'VIEWER';
export type SignOffStatus = 'DRAFT' | 'AWAITING_SIGN_OFF' | 'APPROVED' | 'REJECTED';

export interface ProposeSignOffRequest {
  note?: string;
  proposed_by_name?: string;
  proposal_note?: string;
}

export interface ApproveSignOffRequest {
  note?: string;
  approved_by_name?: string;
  approval_note?: string;
}

export interface RejectSignOffRequest {
  note?: string;
  rejection_reason?: string;
}

export interface SignOffDetailsResponse {
  run_id: string;
  project_id: string;
  sign_off_status: SignOffStatus | string;
  status?: SignOffStatus | string;
  sign_off_proposed_by?: string | null;
  proposed_by?: string | null;
  sign_off_proposed_by_name?: string | null;
  proposed_by_name?: string | null;
  sign_off_proposal_note?: string | null;
  proposal_note?: string | null;
  sign_off_proposed_at?: string | null;
  proposed_at?: string | null;
  sign_off_approved_by?: string | null;
  approved_by?: string | null;
  sign_off_approved_by_name?: string | null;
  approved_by_name?: string | null;
  sign_off_decision_note?: string | null;
  decision_note?: string | null;
  sign_off_decided_at?: string | null;
  decided_at?: string | null;
  can_approve: boolean;
  can_propose?: boolean;
  can_reject?: boolean;
  is_maker: boolean;
  effective_role?: string;
}

export interface AuditEventResponse {
  id: string;
  event_id: string;
  sequence_number: number;
  run_id?: string | null;
  project_id: string;
  user_id?: string | null;
  user_email?: string | null;
  user_role: string;
  event_type: string;
  timestamp_utc: string;
  timestamp_str: string;
  event_payload: Record<string, any>;
  previous_event_hash: string;
  current_event_hash: string;
}

export interface AuditTrailResponse {
  total: number;
  items: AuditEventResponse[];
  is_chain_valid: boolean;
  head_hash?: string | null;
  genesis_hash: string;
}

export interface AuditVerificationBrokenLink {
  sequence_number: number;
  event_id: string;
  reason: string;
  expected_hash: string;
  actual_hash: string;
}

export interface AuditVerificationResponse {
  status: 'VALID' | 'TAMPERED';
  is_valid: boolean;
  total_events: number;
  head_hash?: string | null;
  genesis_hash: string;
  broken_link?: AuditVerificationBrokenLink | null;
  message: string;
}




