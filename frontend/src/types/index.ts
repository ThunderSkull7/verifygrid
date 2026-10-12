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
  | 'ambiguous_duplicate';

export type DiscrepancyCategory =
  | 'none'
  | 'field_mismatch'
  | 'missing_record'
  | 'duplicate_key'
  | 'schema_mismatch';

export interface FieldDifference {
  field_name: string;
  source_field: string;
  target_field: string;
  source_value: any;
  target_value: any;
  source_type?: string | null;
  target_type?: string | null;
  difference_type: string;
  message?: string | null;
}

export interface VerificationResultItem {
  id: string;
  key_values: Record<string, any>;
  match_status: MatchStatus;
  discrepancy_category: DiscrepancyCategory;
  source_row_number?: number | null;
  target_row_number?: number | null;
  source_row_numbers?: number[];
  target_row_numbers?: number[];
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
  preprocessing_config?: PreprocessingConfig | null;
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
