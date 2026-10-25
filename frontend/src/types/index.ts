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
  | 'needs_review';

export type DiscrepancyCategory =
  | 'none'
  | 'field_mismatch'
  | 'missing_record'
  | 'duplicate_key'
  | 'schema_mismatch'
  | 'needs_review';

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
  source_row_indices?: Record<string, number | null> | null;
  source_records?: Record<string, Record<string, any> | null> | null;
  missing_in_sources?: string[] | null;
  source_presence?: Record<string, boolean> | null;
  source_record?: Record<string, any> | null;
  target_record?: Record<string, any> | null;
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


