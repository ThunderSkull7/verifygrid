import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ReconciliationWizard } from '../../src/components/ReconciliationWizard';
import type { PreprocessingResult, UploadedDataset } from '../../src/types';
import {
  applyResponse,
  datasetHostel,
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

// Worksheet change is controlled by App in production. This harness mirrors
// that contract and supplies an Archive profile that lacks the mapped `name`
// column, proving stale mappings are not emitted.
const archiveProfile: PreprocessingResult = {
  ...datasetHostel.profile!,
  data_rows_count: 4,
  selected_worksheet: 'Archive',
  columns: datasetHostel.profile!.columns.filter((column) => column.normalized_name !== 'name'),
};

function WizardHarness() {
  const [datasets, setDatasets] = useState<UploadedDataset[]>(uploadedDatasets);
  const handleWorksheetChange = (fileId: string, sheet: string | null) => {
    setDatasets((previous) =>
      previous.map((dataset) =>
        dataset.id === fileId
          ? {
              ...dataset,
              selectedSheet: sheet,
              profile:
                fileId === datasetHostel.id && sheet === 'Archive'
                  ? archiveProfile
                  : dataset.profile,
            }
          : dataset,
      ),
    );
  };

  return (
    <ReconciliationWizard
      mode="organization"
      project={project}
      uploadedDatasets={datasets}
      onFileUploaded={vi.fn()}
      onWorksheetChange={handleWorksheetChange}
    />
  );
}

async function applyTemplateWithExplicitBindings(user: ReturnType<typeof userEvent.setup>) {
  const picker = await screen.findByLabelText('Choose a saved template');
  await user.selectOptions(picker, savedTemplate.id);
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
}

beforeEach(() => {
  apiMocks.listTemplates.mockResolvedValue([savedTemplate]);
  apiMocks.applyTemplate.mockResolvedValue(applyResponse);
  apiMocks.createTemplate.mockResolvedValue(savedTemplate);
  apiMocks.recommendCandidateKeys.mockResolvedValue({ recommendations: [] });
});

describe('ReconciliationWizard template application', () => {
  it('binds reversed upload order by slot, aligns the worksheet, and never executes verification', async () => {
    const user = userEvent.setup();
    render(<WizardHarness />);

    await applyTemplateWithExplicitBindings(user);

    // Upload order is library, hostel, academic; template order is academic,
    // hostel, library. Payload order follows template slots, not upload position.
    expect(apiMocks.applyTemplate).toHaveBeenCalledWith(savedTemplate.id, {
      project_id: project.id,
      sources: [
        { slot: 'academic', file_id: 'file-academic' },
        { slot: 'hostel', file_id: 'file-hostel' },
        { slot: 'library', file_id: 'file-library' },
      ],
    });
    expect(screen.getByLabelText('Worksheet to use from Hostel Allocation')).toHaveValue('Roster');
    expect(apiMocks.verifyMultiSourceFiles).not.toHaveBeenCalled();
    expect(apiMocks.createMultiSourceVerificationRun).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));

    expect(
      await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ }),
    ).toBeInTheDocument();

    // The bound dataset — not the upload slot — received each mapping.
    expect(screen.getByLabelText("Column for 'name' in Academic Records")).toHaveValue('name');
    expect(screen.getByLabelText("Column for 'name' in Hostel Allocation")).toHaveValue('name');
    expect(screen.getByLabelText("Column for 'name' in Library Records")).toHaveValue('name');
    expect(screen.getAllByText('Suggested')).toHaveLength(3);

    const academicRow = screen
      .getAllByRole('row', { name: /Academic Records/ })
      .find((row) => within(row).queryAllByRole('combobox').length > 0);
    expect(academicRow).toBeDefined();
    expect(within(academicRow!).getAllByRole('combobox')[1]).toHaveValue('student_id');
    const hostelRow = screen
      .getAllByRole('row', { name: /Hostel Allocation/ })
      .find((row) => within(row).queryAllByRole('combobox').length > 0);
    expect(hostelRow).toBeDefined();
    expect(within(hostelRow!).getAllByRole('combobox')[1]).toHaveValue('student_id');
  });

  it('revalidates worksheet choice and excludes a mapping missing from the new worksheet when saving a template', async () => {
    const user = userEvent.setup();
    render(<WizardHarness />);

    await applyTemplateWithExplicitBindings(user);
    await user.click(screen.getByRole('button', { name: /Continue to file setup/ }));
    await screen.findByRole('heading', { name: /Step 2: Name Your Files & Matching Keys/ });

    // Return to the upload step, then switch the workbook to a worksheet that
    // does not contain the previously mapped `name` column.
    await user.click(screen.getByRole('button', { name: /Upload.*Add files & pre-flight/ }));
    const worksheetSelect = await screen.findByLabelText('Worksheet to use from Hostel Allocation');
    await user.selectOptions(worksheetSelect, 'Archive');
    expect(worksheetSelect).toHaveValue('Archive');

    await user.click(screen.getByRole('button', { name: /Save as new template/ }));
    await user.type(screen.getByLabelText('New template name'), 'Archive-safe template');
    await user.click(screen.getByRole('button', { name: /Save as new$/ }));

    await waitFor(() => expect(apiMocks.createTemplate).toHaveBeenCalledTimes(1));
    const payload = apiMocks.createTemplate.mock.calls[0][0];
    const hostelSlot = payload.configuration.sources.find(
      (source: { alias: string }) => source.alias === 'hostel_allocation',
    );
    expect(hostelSlot).toBeDefined();
    expect(hostelSlot.sheet_name).toBe('Archive');
    expect(hostelSlot.field_mapping).toMatchObject({
      student_id: 'student_id',
      room: 'room',
    });
    expect(hostelSlot.field_mapping).not.toHaveProperty('name');

    // Other slots keep their valid mappings.
    const academicSlot = payload.configuration.sources.find(
      (source: { alias: string }) => source.alias === 'academic_records',
    );
    expect(academicSlot.field_mapping).toMatchObject({
      student_id: 'student_id',
      name: 'name',
      email: 'email',
    });
  });
});
