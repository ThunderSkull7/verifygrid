import type {
  ColumnMetadata,
  PreprocessingResult,
  Project,
  TemplateApplyResponse,
  TemplateConfigurationV1,
  UploadedDataset,
  VerificationTemplate,
} from '../../src/types';

const column = (name: string): ColumnMetadata => ({
  original_name: name,
  normalized_name: name,
  detected_type: 'text',
  null_count: 0,
  non_null_count: 10,
  sample_values: [],
});

const profile = (
  sourceFileId: string,
  filename: string,
  names: string[],
  sheetNames: string[] | null = null,
): PreprocessingResult => ({
  source_file_id: sourceFileId,
  project_id: 'project-1',
  original_filename: filename,
  file_type: filename.endsWith('.xlsx') ? 'xlsx' : 'csv',
  total_source_rows: 11,
  data_rows_count: 10,
  empty_rows_count: 0,
  duplicate_rows_count: 0,
  columns: names.map(column),
  column_mapping: Object.fromEntries(names.map((name) => [name, name])),
  duplicate_record_row_numbers: [],
  issues: [],
  preview_rows: [],
  sheet_names: sheetNames,
  selected_worksheet: null,
});

export const templateConfiguration: TemplateConfigurationV1 = {
  version: 1,
  sources: [
    {
      alias: 'academic',
      label: 'Academic Records',
      is_primary: true,
      key_columns: ['student_id'],
      field_mapping: { student_id: 'student_id', name: 'name', email: 'email' },
      sheet_name: null,
    },
    {
      alias: 'hostel',
      label: 'Hostel Allocation',
      is_primary: false,
      key_columns: ['student_id'],
      field_mapping: { student_id: 'student_id', name: 'name', room: 'room' },
      sheet_name: 'Roster',
    },
    {
      alias: 'library',
      label: 'Library Records',
      is_primary: false,
      key_columns: ['student_id'],
      field_mapping: { student_id: 'student_id', name: 'name', book: 'book' },
      sheet_name: null,
    },
  ],
  unified_keys: ['student_id'],
  compare_attributes: ['name'],
  ignore_attributes: [],
  numeric_tolerance: 0.01,
  ignore_whitespace: true,
  ignore_case: false,
  include_identical: true,
};

export const savedTemplate: VerificationTemplate = {
  id: 'template-college',
  name: 'College pilot',
  description: 'Three-source student reconciliation',
  mode: 'organization',
  visibility: 'personal',
  config_version: 1,
  configuration: templateConfiguration,
  source_count: 3,
  created_at: '2026-10-28T00:00:00Z',
  updated_at: '2026-10-28T00:00:00Z',
};

// Deliberately reversed relative to template slot order so tests prove bindings
// — not upload position — decide where each slot is applied.
export const datasetLibrary: UploadedDataset = {
  id: 'file-library',
  name: 'library.csv',
  label: 'Library Records',
  isPrimary: false,
  selectedSheet: null,
  profile: profile('file-library', 'library.csv', ['student_id', 'name', 'book']),
};

export const datasetHostel: UploadedDataset = {
  id: 'file-hostel',
  name: 'hostel.xlsx',
  label: 'Hostel Allocation',
  isPrimary: false,
  selectedSheet: 'Archive',
  profile: profile('file-hostel', 'hostel.xlsx', ['student_id', 'name', 'room'], ['Roster', 'Archive']),
};

export const datasetAcademic: UploadedDataset = {
  id: 'file-academic',
  name: 'academic.csv',
  label: 'Academic Records',
  isPrimary: true,
  selectedSheet: null,
  profile: profile('file-academic', 'academic.csv', ['student_id', 'name', 'email']),
};

export const uploadedDatasets: UploadedDataset[] = [
  datasetLibrary,
  datasetHostel,
  datasetAcademic,
];

export const applyResponse: TemplateApplyResponse = {
  template_id: savedTemplate.id,
  project_id: 'project-1',
  mode: 'organization',
  effective_request: {
    sources: templateConfiguration.sources.map((slot) => ({
      alias: slot.alias,
      file_id:
        slot.alias === 'academic'
          ? datasetAcademic.id
          : slot.alias === 'hostel'
            ? datasetHostel.id
            : datasetLibrary.id,
      is_primary: slot.is_primary,
      label: slot.label,
      key_columns: slot.key_columns,
      field_mapping: slot.field_mapping,
      sheet_name: slot.sheet_name,
    })),
    unified_keys: ['student_id'],
    compare_attributes: ['name'],
    include_identical: true,
  },
  validation_report: {
    blocking: false,
    issues: [],
    warnings: [],
  },
};

export const project: Project = {
  id: 'project-1',
  name: 'College pilot',
  description: null,
  owner_id: 'user-1',
  created_at: '2026-10-28T00:00:00Z',
  updated_at: '2026-10-28T00:00:00Z',
};
