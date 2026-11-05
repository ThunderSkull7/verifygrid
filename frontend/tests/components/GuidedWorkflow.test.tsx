import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ReconciliationWizard } from '../../src/components/ReconciliationWizard';
import type {
  MultiSourceVerificationResponse,
  UploadedDataset,
  VerificationRun,
  VerificationTemplate,
} from '../../src/types';
import {
  applyResponse,
  datasetAcademic,
  datasetHostel,
  datasetLibrary,
  project,
  savedTemplate,
  uploadedDatasets,
} from './fixtures';

const apiMocks = vi.hoisted(() => ({
  listTemplates: vi.fn(),
  applyTemplate: vi.fn(),
  createTemplate: vi.fn(),
  updateTemplate: vi.fn(),
  deleteTemplate: vi.fn(),
  recommendCandidateKeys: vi.fn(),
  previewRules: vi.fn(),
  verifyMultiSourceFiles: vi.fn(),
  createMultiSourceVerificationRun: vi.fn(),
}));

vi.mock('../../src/services/api', () => ({ api: apiMocks }));

const mockVerificationResponse: MultiSourceVerificationResponse = {
  sources: [
    { alias: 'academic_records', file_id: datasetAcademic.id, is_primary: true, key_columns: ['student_id'], field_mapping: {} },
    { alias: 'hostel_allocation', file_id: datasetHostel.id, is_primary: false, key_columns: ['student_id'], field_mapping: {} },
  ],
  results: [
    {
      id: 'res-1',
      match_status: 'identical',
      discrepancy_category: 'none',
      key_values: { student_id: 'S101' },
      source_row: 1,
      target_row: 1,
      source_values: { name: 'Alice' },
      target_values: { name: 'Alice' },
      differences: [],
      applied_rules: [],
      financial_impact: 0,
      severity: 'INFO',
    },
    {
      id: 'res-2',
      match_status: 'field_mismatch',
      discrepancy_category: 'field_mismatch',
      key_values: { student_id: 'S102' },
      source_row: 2,
      target_row: 2,
      source_values: { name: 'Bob' },
      target_values: { name: 'Robert' },
      differences: [{ field: 'name', source_value: 'Bob', target_value: 'Robert', diff_amount: 0, severity: 'WARNING' }],
      applied_rules: [],
      financial_impact: 0,
      severity: 'WARNING',
    },
  ],
  summary: {
    total_source_records: 2,
    total_target_records: 2,
    identical_matches: 1,
    field_mismatches: 1,
    unmatched_source_records: 0,
    unmatched_target_records: 0,
    duplicate_source_keys_count: 0,
    duplicate_target_keys_count: 0,
    invalid_key_records: 0,
    total_discrepancy_amount: 0,
    attribute_comparisons_completed: 2,
    attributes_not_checked: 0,
    fallback_matched_records: 0,
    duration_ms: 15,
  },
};

const mockCreatedRun: VerificationRun = {
  id: 'run-1',
  project_id: project.id,
  run_number: 1,
  status: 'completed',
  triggered_by: 'user-1',
  started_at: '2026-11-04T10:00:00Z',
  completed_at: '2026-11-04T10:00:01Z',
  duration_ms: 1000,
  source_file_id: datasetAcademic.id,
  target_file_id: datasetHostel.id,
  total_source_records: 2,
  total_target_records: 2,
  matched_records_count: 1,
  unmatched_source_count: 0,
  unmatched_target_count: 0,
  field_discrepancies_count: 1,
  financial_discrepancy_total: 0,
  integrity_hash: 'hash-123',
};

function GuidedWorkflowHarness({
  initialDatasets = uploadedDatasets,
}: {
  initialDatasets?: UploadedDataset[];
}) {
  const [datasets, setDatasets] = useState<UploadedDataset[]>(initialDatasets);

  const handleRoleChange = (fileId: string, isPrimary: boolean) => {
    setDatasets((prev) =>
      prev.map((d) => (d.id === fileId ? { ...d, isPrimary } : d)),
    );
  };

  const handleLabelChange = (fileId: string, label: string) => {
    setDatasets((prev) =>
      prev.map((d) => (d.id === fileId ? { ...d, label } : d)),
    );
  };

  return (
    <ReconciliationWizard
      mode="organization"
      project={project}
      uploadedDatasets={datasets}
      onFileUploaded={vi.fn()}
      onRoleChange={handleRoleChange}
      onLabelChange={handleLabelChange}
    />
  );
}

beforeEach(() => {
  apiMocks.listTemplates.mockResolvedValue([]);
  apiMocks.recommendCandidateKeys.mockResolvedValue({
    recommendations: [
      {
        key_name: 'student_id',
        overall_score: 0.95,
        source_columns: {
          academic_records: ['student_id'],
          hostel_allocation: ['student_id'],
          library_records: ['student_id'],
        },
      },
    ],
  });
  apiMocks.verifyMultiSourceFiles.mockResolvedValue(mockVerificationResponse);
  apiMocks.createMultiSourceVerificationRun.mockResolvedValue(mockCreatedRun);
});

describe('Batch 4 Guided Comparison Workflow', () => {
  it('guides user through the 7-stage comparison journey with state preservation and pre-comparison summary', async () => {
    const user = userEvent.setup();
    render(<GuidedWorkflowHarness />);

    // Stage 1: Upload step guidance
    expect(screen.getByText(/3 spreadsheets ready to compare/)).toBeInTheDocument();
    const continueToSetupBtn = screen.getByRole('button', { name: /Continue to file setup/ });
    await user.click(continueToSetupBtn);

    // Stage 2: Name Your Files & Matching Keys
    expect(
      await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ }),
    ).toBeInTheDocument();

    // Verify sub-sections: Identify File Roles & Select Matching Column
    expect(screen.getByRole('heading', { name: /1\. Identify File Roles/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /2\. Select Matching Column/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /3\. Match Column Names/ })).toBeInTheDocument();

    // Verify student_id is automatically preferred and detected
    expect(screen.getByText(/student_id detected/)).toBeInTheDocument();
    const matchingKeyInputs = screen.getAllByDisplayValue('student_id');
    expect(matchingKeyInputs.length).toBeGreaterThanOrEqual(1);

    // Stage 3: Navigate to Settings & Review
    await user.click(screen.getByRole('button', { name: /Continue to settings/ }));

    expect(
      await screen.findByRole('heading', { name: /Step 3: Comparison Settings & Review/ }),
    ).toBeInTheDocument();

    // Verify Pre-Comparison Review Summary card is present
    expect(screen.getByText('Pre-Comparison Review Summary')).toBeInTheDocument();
    expect(screen.getByText('Main Trusted File')).toBeInTheDocument();
    expect(screen.getByText('Academic Records')).toBeInTheDocument();
    expect(screen.getByText('2 comparison file(s)')).toBeInTheDocument();

    // Verify essential settings are visible
    expect(screen.getByText(/Text & Spacing Cleanup/)).toBeInTheDocument();
    expect(screen.getByText(/Number & Amount Differences/)).toBeInTheDocument();

    // Verify advanced settings are collapsed
    expect(screen.getByText(/Advanced comparison settings/)).toBeInTheDocument();

    // Backward navigation: Back to file setup preserves state
    await user.click(screen.getByRole('button', { name: /Back to file setup/ }));

    expect(
      await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ }),
    ).toBeInTheDocument();
    expect(screen.getAllByDisplayValue('student_id').length).toBeGreaterThanOrEqual(1);

    // Forward navigation: Return to settings
    await user.click(screen.getByRole('button', { name: /Continue to settings/ }));
    expect(
      await screen.findByRole('heading', { name: /Step 3: Comparison Settings & Review/ }),
    ).toBeInTheDocument();

    // Stage 4: Run comparison
    const compareBtn = screen.getByRole('button', { name: /Compare Records/ });
    expect(compareBtn).toBeEnabled();
    await user.click(compareBtn);

    // Verify execution call
    await waitFor(() => expect(apiMocks.verifyMultiSourceFiles).toHaveBeenCalledTimes(1));

    // Stage 5: Results step transition
    expect(
      await screen.findByRole('heading', { name: /Step 4: Comparison Results/ }),
    ).toBeInTheDocument();
    expect(screen.getByText('Total Records Compared')).toBeInTheDocument();
    expect(screen.getByText('Matching Records')).toBeInTheDocument();
    expect(screen.getByText('Records with Differences')).toBeInTheDocument();
  });

  it('blocks comparison and shows clear guidance when no file is marked as primary source', async () => {
    const user = userEvent.setup();
    const datasetsWithoutPrimary = uploadedDatasets.map((d) => ({
      ...d,
      isPrimary: false,
    }));

    render(<GuidedWorkflowHarness initialDatasets={datasetsWithoutPrimary} />);

    // Advance to Step 2
    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    expect(
      await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ }),
    ).toBeInTheDocument();

    // Advance to Step 3
    await user.click(screen.getByRole('button', { name: /Continue to settings/ }));
    expect(
      await screen.findByRole('heading', { name: /Step 3: Comparison Settings & Review/ }),
    ).toBeInTheDocument();

    // Blocker message displayed and Compare Records button disabled
    expect(
      screen.getByText(/Verification needs at least one source of truth\. Mark one file as the primary source/),
    ).toBeInTheDocument();

    const compareBtn = screen.getByRole('button', { name: /Compare Records/ });
    expect(compareBtn).toBeDisabled();
    expect(apiMocks.verifyMultiSourceFiles).not.toHaveBeenCalled();
  });

  it('displays error message and remains on Step 3 when verification fails', async () => {
    const user = userEvent.setup();
    apiMocks.verifyMultiSourceFiles.mockRejectedValueOnce(
      new Error('Connection to comparison engine timed out'),
    );

    render(<GuidedWorkflowHarness />);

    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    await user.click(screen.getByRole('button', { name: /Continue to settings/ }));
    await screen.findByRole('heading', { name: /Step 3: Comparison Settings & Review/ });

    const compareBtn = screen.getByRole('button', { name: /Compare Records/ });
    await user.click(compareBtn);

    // Verify error is shown and does NOT advance to Step 4
    expect(
      await screen.findByText('Connection to comparison engine timed out'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /Step 4: Comparison Results/ })).not.toBeInTheDocument();
  });
});

describe('Batch 4 Matching-Key Safety & Selection', () => {
  it('Scenario 1: automatically preselects student_id when present in all files and recommended with high score', async () => {
    const user = userEvent.setup();
    apiMocks.recommendCandidateKeys.mockResolvedValue({
      recommendations: [
        {
          key_name: 'student_id',
          overall_score: 0.95,
          source_columns: {
            academic_records: ['student_id'],
            hostel_allocation: ['student_id'],
            library_records: ['student_id'],
          },
        },
      ],
    });

    render(<GuidedWorkflowHarness />);
    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    // Badge indicates all files
    expect(screen.getByText(/student_id detected \(all files\)/)).toBeInTheDocument();

    // Primary dropdown and composite input preselected with student_id
    const primarySelect = screen.getByLabelText(/Select primary matching column/);
    expect(primarySelect).toHaveValue('student_id');

    const compositeInput = screen.getByPlaceholderText(/e\.g\. student_id or id \+ term/);
    expect(compositeInput).toHaveValue('student_id');
  });

  it('Scenario 2: does NOT automatically preselect student_id when present in only some files', async () => {
    const user = userEvent.setup();
    const partialDatasets: UploadedDataset[] = [
      datasetAcademic, // has student_id
      {
        ...datasetLibrary,
        profile: {
          ...datasetLibrary.profile!,
          columns: datasetLibrary.profile!.columns.filter((c) => c.normalized_name !== 'student_id'),
        },
      }, // does NOT have student_id
    ];

    apiMocks.recommendCandidateKeys.mockResolvedValue({
      recommendations: [
        {
          key_name: 'student_id',
          overall_score: 0.85,
          source_columns: {},
        },
      ],
    });

    render(<GuidedWorkflowHarness initialDatasets={partialDatasets} />);
    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    // Badge indicates some files
    expect(screen.getByText(/student_id detected \(some files\)/)).toBeInTheDocument();

    // Primary select retains default 'id', NOT student_id
    const primarySelect = screen.getByLabelText(/Select primary matching column/);
    expect(primarySelect).toHaveValue('');
    const compositeInput = screen.getByPlaceholderText(/e\.g\. student_id or id \+ term/);
    expect(compositeInput).toHaveValue('id');
  });

  it('Scenario 3: does NOT automatically preselect student_id when recommendation score is below 0.7', async () => {
    const user = userEvent.setup();
    apiMocks.recommendCandidateKeys.mockResolvedValue({
      recommendations: [
        {
          key_name: 'student_id',
          overall_score: 0.45, // below 0.7 threshold
          source_columns: {},
        },
      ],
    });

    render(<GuidedWorkflowHarness />);
    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    // Badge still detects student_id in all files
    expect(screen.getByText(/student_id detected \(all files\)/)).toBeInTheDocument();

    // But not preselected because recommendation score is low
    const compositeInput = screen.getByPlaceholderText(/e\.g\. student_id or id \+ term/);
    expect(compositeInput).toHaveValue('id');
  });

  it('Scenario 4: preserves user explicit selection of id and does NOT overwrite with student_id recommendation', async () => {
    const user = userEvent.setup();
    const datasetsWithId: UploadedDataset[] = uploadedDatasets.map((d) => ({
      ...d,
      profile: {
        ...d.profile!,
        columns: [
          {
            original_name: 'id',
            normalized_name: 'id',
            detected_type: 'text',
            null_count: 0,
            non_null_count: 10,
            sample_values: [],
          },
          ...d.profile!.columns,
        ],
      },
    }));

    let resolveRecs: (val: any) => void;
    const recPromise = new Promise((resolve) => {
      resolveRecs = resolve;
    });
    apiMocks.recommendCandidateKeys.mockReturnValue(recPromise);

    render(<GuidedWorkflowHarness initialDatasets={datasetsWithId} />);
    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    // User explicitly selects 'id' in the primary matching column selector
    const primarySelect = screen.getByLabelText(/Select primary matching column/);
    await user.selectOptions(primarySelect, 'id');

    // Now recommendations resolve with high student_id score
    resolveRecs!({
      recommendations: [
        {
          key_name: 'student_id',
          overall_score: 0.95,
          source_columns: {},
        },
      ],
    });

    // Verify 'id' is NOT overwritten
    const compositeInput = screen.getByPlaceholderText(/e\.g\. student_id or id \+ term/);
    expect(compositeInput).toHaveValue('id');
  });

  it('Scenario 5: preserves user custom key selection (e.g. roll_no) without overwriting', async () => {
    const user = userEvent.setup();
    let resolveRecs: (val: any) => void;
    const recPromise = new Promise((resolve) => {
      resolveRecs = resolve;
    });
    apiMocks.recommendCandidateKeys.mockReturnValue(recPromise);

    render(<GuidedWorkflowHarness />);
    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    const compositeInput = screen.getByPlaceholderText(/e\.g\. student_id or id \+ term/);
    await user.clear(compositeInput);
    await user.type(compositeInput, 'roll_no');
    expect(compositeInput).toHaveValue('roll_no');

    resolveRecs!({
      recommendations: [
        {
          key_name: 'student_id',
          overall_score: 0.99,
          source_columns: {},
        },
      ],
    });

    expect(compositeInput).toHaveValue('roll_no');
  });

  it('Scenario 6: preserves matching key specified by a saved template when recommendations resolve', async () => {
    const user = userEvent.setup();
    const customTemplate: VerificationTemplate = {
      ...savedTemplate,
      configuration: {
        ...savedTemplate.configuration,
        unified_keys: ['registration_no'],
        sources: savedTemplate.configuration.sources.map((s) => ({
          ...s,
          key_columns: ['registration_no'],
        })),
      },
    };
    apiMocks.listTemplates.mockResolvedValue([customTemplate]);
    apiMocks.applyTemplate.mockResolvedValue({
      ...applyResponse,
      effective_request: {
        ...applyResponse.effective_request,
        unified_keys: ['registration_no'],
      },
    });

    render(<GuidedWorkflowHarness />);
    // Apply template on Step 1 with slot bindings
    const picker = await screen.findByLabelText('Choose a saved template');
    await user.selectOptions(picker, customTemplate.id);
    await user.selectOptions(
      screen.getByLabelText('Uploaded file for slot academic'),
      'file-academic',
    );
    await user.selectOptions(screen.getByLabelText('Uploaded file for slot hostel'), 'file-hostel');
    await user.selectOptions(
      screen.getByLabelText('Uploaded file for slot library'),
      'file-library',
    );
    await user.click(screen.getByRole('button', { name: 'Apply to uploaded files' }));
    await screen.findByText(/Template 'College pilot' validated successfully/);

    // Recommendations return student_id
    apiMocks.recommendCandidateKeys.mockResolvedValue({
      recommendations: [
        {
          key_name: 'student_id',
          overall_score: 0.95,
          source_columns: {},
        },
      ],
    });

    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    // Template key 'registration_no' is preserved, not overwritten by student_id
    const compositeInput = screen.getByPlaceholderText(/e\.g\. student_id or id \+ term/);
    expect(compositeInput).toHaveValue('registration_no');
  });

  it('Scenario 7: maintains key selection stability when files are added or removed after selection', async () => {
    const user = userEvent.setup();
    function DynamicHarness() {
      const [datasets, setDatasets] = useState<UploadedDataset[]>([datasetAcademic, datasetLibrary]);
      return (
        <div>
          <button
            onClick={() => setDatasets([datasetAcademic, datasetLibrary, datasetHostel])}
          >
            Add Hostel File
          </button>
          <button onClick={() => setDatasets([datasetAcademic])}>Remove Library File</button>
          <ReconciliationWizard
            mode="organization"
            project={project}
            uploadedDatasets={datasets}
            onFileUploaded={vi.fn()}
          />
        </div>
      );
    }

    apiMocks.recommendCandidateKeys.mockResolvedValue({
      recommendations: [
        {
          key_name: 'student_id',
          overall_score: 0.95,
          source_columns: {},
        },
      ],
    });

    render(<DynamicHarness />);
    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    const compositeInput = screen.getByPlaceholderText(/e\.g\. student_id or id \+ term/);
    // User changes key to custom 'custom_code'
    await user.clear(compositeInput);
    await user.type(compositeInput, 'custom_code');
    expect(compositeInput).toHaveValue('custom_code');

    // Add another file dynamically
    await user.click(screen.getByRole('button', { name: 'Add Hostel File' }));
    // Key must still remain 'custom_code'
    expect(compositeInput).toHaveValue('custom_code');

    // Remove a file dynamically
    await user.click(screen.getByRole('button', { name: 'Remove Library File' }));
    expect(compositeInput).toHaveValue('custom_code');
  });

  it('Scenario 8: preserves composite keys and fallback key configurations', async () => {
    const user = userEvent.setup();
    render(<GuidedWorkflowHarness />);
    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    // Set composite key
    const compositeInput = screen.getByPlaceholderText(/e\.g\. student_id or id \+ term/);
    await user.clear(compositeInput);
    await user.type(compositeInput, 'id + term');
    expect(compositeInput).toHaveValue('id + term');

    // Open backup matching columns details
    const backupSummary = screen.getByText(/Backup matching columns \(optional\)/);
    expect(backupSummary).toBeInTheDocument();

    // Add a fallback key
    const addFallbackBtn = screen.getByRole('button', { name: /\+ Add backup matching column/ });
    await user.click(addFallbackBtn);

    // Navigate forward to Step 3 and back to Step 2
    await user.click(screen.getByRole('button', { name: /Continue to settings/ }));
    await screen.findByRole('heading', { name: /Step 3: Comparison Settings & Review/ });

    await user.click(screen.getByRole('button', { name: /Back to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    // Composite key preserved
    expect(screen.getByPlaceholderText(/e\.g\. student_id or id \+ term/)).toHaveValue('id + term');
    // Fallback key row preserved
    expect(screen.getByText(/Priority 1/)).toBeInTheDocument();
  });
});

describe('Batch 7 Upload Workflow & Multiple Authoritative Sources', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.listTemplates.mockResolvedValue([]);
    apiMocks.recommendCandidateKeys.mockResolvedValue({
      single_column_keys: [],
      composite_keys: [],
      column_analysis: {},
    });
  });

  function Batch7Harness({
    initialDatasets = uploadedDatasets,
  }: {
    initialDatasets?: UploadedDataset[];
  }) {
    const [datasets, setDatasets] = useState<UploadedDataset[]>(initialDatasets);

    const handleRoleChange = (fileId: string, isPrimary: boolean) => {
      setDatasets((prev) =>
        prev.map((d) => (d.id === fileId ? { ...d, isPrimary } : d)),
      );
    };

    const handleLabelChange = (fileId: string, label: string) => {
      setDatasets((prev) =>
        prev.map((d) => (d.id === fileId ? { ...d, label } : d)),
      );
    };

    const handleHeaderRowChange = (fileId: string, headerRow: number | null) => {
      setDatasets((prev) =>
        prev.map((d) => (d.id === fileId ? { ...d, headerRow } : d)),
      );
    };

    return (
      <ReconciliationWizard
        mode="organization"
        project={project}
        uploadedDatasets={datasets}
        onFileUploaded={vi.fn()}
        onRoleChange={handleRoleChange}
        onLabelChange={handleLabelChange}
        onHeaderRowChange={handleHeaderRowChange}
      />
    );
  }

  it('renders single vs multiple authoritative sources selection before file list in Step 1', () => {
    render(<Batch7Harness />);

    expect(screen.getByText('Authoritative source setup')).toBeInTheDocument();
    expect(
      screen.getByText('Single authoritative source (default)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Multiple authoritative sources'),
    ).toBeInTheDocument();

    const singleRadio = screen.getByRole('radio', {
      name: /Single authoritative source \(default\)/,
    });
    const multiRadio = screen.getByRole('radio', {
      name: /Multiple authoritative sources/,
    });

    expect(singleRadio).toBeChecked();
    expect(multiRadio).not.toBeChecked();
  });

  it('enforces radio behavior for main trusted file in single-source mode', async () => {
    const user = userEvent.setup();
    render(<Batch7Harness />);

    const libraryGroup = screen.getByRole('group', {
      name: /Role for Library Records/,
    });
    const libraryMainBtn = within(libraryGroup).getByRole('button', {
      name: /Main file to trust/,
    });
    const academicGroup = screen.getByRole('group', {
      name: /Role for Academic Records/,
    });
    const academicMainBtn = within(academicGroup).getByRole('button', {
      name: /Main file to trust/,
    });

    expect(academicMainBtn).toHaveAttribute('aria-pressed', 'true');
    expect(libraryMainBtn).toHaveAttribute('aria-pressed', 'false');

    // Click to make Library the main trusted file
    await user.click(libraryMainBtn);

    expect(libraryMainBtn).toHaveAttribute('aria-pressed', 'true');
    expect(academicMainBtn).toHaveAttribute('aria-pressed', 'false');
  });

  it('allows multiple primary sources in multi-source mode and prunes excess when switched back', async () => {
    const user = userEvent.setup();
    render(<Batch7Harness />);

    const multiRadio = screen.getByRole('radio', {
      name: /Multiple authoritative sources/,
    });
    await user.click(multiRadio);
    expect(multiRadio).toBeChecked();

    const libraryGroup = screen.getByRole('group', {
      name: /Role for Library Records/,
    });
    const libraryAuthBtn = within(libraryGroup).getByRole('button', {
      name: /Authoritative source/,
    });
    const academicGroup = screen.getByRole('group', {
      name: /Role for Academic Records/,
    });
    const academicAuthBtn = within(academicGroup).getByRole('button', {
      name: /Authoritative source/,
    });

    expect(academicAuthBtn).toHaveAttribute('aria-pressed', 'true');
    expect(libraryAuthBtn).toHaveAttribute('aria-pressed', 'false');

    // Promote library to authoritative source too
    await user.click(libraryAuthBtn);

    expect(academicAuthBtn).toHaveAttribute('aria-pressed', 'true');
    expect(libraryAuthBtn).toHaveAttribute('aria-pressed', 'true');

    // Switch back to single-source mode
    const singleRadio = screen.getByRole('radio', {
      name: /Single authoritative source \(default\)/,
    });
    await user.click(singleRadio);
    expect(singleRadio).toBeChecked();

    // In single-source mode, excess primary is pruned back to 1
    const libraryMainBtn = within(libraryGroup).getByRole('button', {
      name: /Main file to trust/,
    });
    const academicMainBtn = within(academicGroup).getByRole('button', {
      name: /Main file to trust/,
    });

    // First primary in dataset order is retained; subsequent primaries are pruned back to secondary
    expect(libraryMainBtn).toHaveAttribute('aria-pressed', 'true');
    expect(academicMainBtn).toHaveAttribute('aria-pressed', 'false');
  });

  it('renders header-row candidate selector and updates selection on change', async () => {
    const user = userEvent.setup();
    const datasetWithHeaderCandidates: UploadedDataset = {
      ...datasetAcademic,
      profile: {
        ...datasetAcademic.profile!,
        detected_header_row: 2,
        header_row_candidates: [
          {
            row_number: 1,
            columns: ['ANNUAL REPORT TITLE BANNER'],
            sample_preview: ['ANNUAL REPORT TITLE BANNER'],
            is_likely_header: false,
          },
          {
            row_number: 2,
            columns: ['student_id', 'name', 'email'],
            sample_preview: ['student_id', 'name', 'email'],
            is_likely_header: true,
          },
        ],
      },
      headerRow: 2,
    };

    render(
      <Batch7Harness
        initialDatasets={[datasetWithHeaderCandidates, datasetHostel]}
      />,
    );

    const select = screen.getByRole('combobox', {
      name: /Header row for Academic Records/,
    });
    expect(select).toBeInTheDocument();
    expect(select).toHaveValue('2');

    await user.selectOptions(select, '1');
    expect(select).toHaveValue('1');
  });
});

describe('Batch 8 Matching, Column Mapping & Comparison Engine Correctness', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.listTemplates.mockResolvedValue([]);
    apiMocks.recommendCandidateKeys.mockResolvedValue({
      single_column_keys: [],
      composite_keys: [],
      column_analysis: {},
    });
  });

  it('blocks comparison and shows critical safeguard error when zero comparable fields are mapped', async () => {
    const user = userEvent.setup();
    // Datasets with only an identifier column and unmapped disjoint columns
    const ds1: UploadedDataset = {
      ...datasetAcademic,
      profile: {
        ...datasetAcademic.profile!,
        columns: [{ original_name: 'student_id', normalized_name: 'student_id', detected_type: 'text', null_count: 0, non_null_count: 5, sample_values: [] }],
        column_mapping: { student_id: 'student_id' },
      },
    };
    const ds2: UploadedDataset = {
      ...datasetHostel,
      profile: {
        ...datasetHostel.profile!,
        columns: [{ original_name: 'student_id', normalized_name: 'student_id', detected_type: 'text', null_count: 0, non_null_count: 5, sample_values: [] }],
        column_mapping: { student_id: 'student_id' },
      },
    };

    render(
      <ReconciliationWizard
        mode="organization"
        project={project}
        uploadedDatasets={[ds1, ds2]}
        onFileUploaded={vi.fn()}
      />,
    );

    // Navigate to Step 2
    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    // Explicitly select student_id as primary matching column
    const selectKey = screen.getByRole('combobox', { name: /Select primary matching column/i });
    await user.selectOptions(selectKey, 'student_id');

    // Navigate to Step 3
    await user.click(screen.getByRole('button', { name: /Continue to settings/ }));
    await screen.findByRole('heading', { name: /Step 3: Comparison Settings & Review/ });

    // Safeguard check: zero comparable fields blocker must be visible
    expect(
      screen.getByText(/No comparable fields are mapped across your files/i),
    ).toBeInTheDocument();

    // Compare Records button must be disabled
    const compareBtn = screen.getByRole('button', { name: /Compare Records/i });
    expect(compareBtn).toBeDisabled();
  });

  it('displays low key suitability warning when recommendation indicates high duplicates or blanks', async () => {
    const user = userEvent.setup();
    apiMocks.recommendCandidateKeys.mockResolvedValue({
      recommendations: [
        {
          key_name: 'student_id',
          is_composite: false,
          overall_score: 0.45,
          overlap_score: 0.3,
          source_columns: { academic_records: ['student_id'], hostel_allocation: ['student_id'], library_records: ['student_id'] },
          uniqueness_by_source: { academic_records: 0.4, hostel_allocation: 0.5, library_records: 0.4 },
          null_rate_by_source: { academic_records: 0.2, hostel_allocation: 0.1, library_records: 0.1 },
          recommendation_reason: 'Student identifier detected but unsuitable as unique key: contains duplicate values (40.0% uniqueness).',
        },
      ],
    });

    render(
      <ReconciliationWizard
        mode="organization"
        project={project}
        uploadedDatasets={uploadedDatasets}
        onFileUploaded={vi.fn()}
      />,
    );

    // Navigate to Step 2
    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    // Wait for recommendation and verify suitability badge appears
    await waitFor(() => {
      expect(
        screen.getByText(/Low key suitability: check duplicates or blank values/i),
      ).toBeInTheDocument();
    });
  });
});
