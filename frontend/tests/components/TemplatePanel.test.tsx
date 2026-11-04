import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TemplatePanel } from '../../src/components/TemplatePanel';
import {
  applyResponse,
  project,
  savedTemplate,
  templateConfiguration,
  uploadedDatasets,
} from './fixtures';

const apiMocks = vi.hoisted(() => ({
  listTemplates: vi.fn(),
  applyTemplate: vi.fn(),
  createTemplate: vi.fn(),
  updateTemplate: vi.fn(),
  deleteTemplate: vi.fn(),
}));

vi.mock('../../src/services/api', () => ({ api: apiMocks }));

const getCurrentConfiguration = vi.fn(() => templateConfiguration);
const onTemplateApplied = vi.fn();

function renderPanel(mode: 'organization' | 'financial' = 'organization') {
  return render(
    <TemplatePanel
      mode={mode}
      project={project}
      uploadedDatasets={uploadedDatasets}
      getCurrentConfiguration={getCurrentConfiguration}
      onTemplateApplied={onTemplateApplied}
    />,
  );
}

async function chooseTemplate(user: ReturnType<typeof userEvent.setup>) {
  const picker = await screen.findByLabelText('Choose a saved template');
  await user.selectOptions(picker, savedTemplate.id);
  return picker;
}

async function bindSlot(
  user: ReturnType<typeof userEvent.setup>,
  alias: string,
  fileId: string,
) {
  await user.selectOptions(screen.getByLabelText(`Uploaded file for slot ${alias}`), fileId);
}

beforeEach(() => {
  apiMocks.listTemplates.mockResolvedValue([savedTemplate]);
  apiMocks.applyTemplate.mockResolvedValue(applyResponse);
  apiMocks.createTemplate.mockResolvedValue(savedTemplate);
  apiMocks.updateTemplate.mockResolvedValue(savedTemplate);
  apiMocks.deleteTemplate.mockResolvedValue(undefined);
  getCurrentConfiguration.mockReturnValue(templateConfiguration);
});

describe('TemplatePanel selection and explicit slot bindings', () => {
  it('loads personal templates in organization mode and lists slot requirements', async () => {
    const user = userEvent.setup();
    renderPanel();

    await chooseTemplate(user);

    expect(apiMocks.listTemplates).toHaveBeenCalledWith('organization');
    expect(screen.getByLabelText('Uploaded file for slot academic')).toBeInTheDocument();
    expect(screen.getByLabelText('Uploaded file for slot hostel')).toBeInTheDocument();
    expect(screen.getByLabelText('Uploaded file for slot library')).toBeInTheDocument();
    expect(screen.getAllByText(/Identity key: student_id/)).toHaveLength(3);
    expect(screen.getByText(/worksheet: Roster/)).toBeInTheDocument();
    expect(screen.getByText('0 of 3 slots assigned')).toBeInTheDocument();
  });

  it('binds slots independently, shows the chosen filename, and preserves other slots', async () => {
    const user = userEvent.setup();
    renderPanel();
    await chooseTemplate(user);

    await bindSlot(user, 'academic', 'file-academic');
    expect(screen.getByText('Bound to academic.csv')).toBeInTheDocument();
    expect(screen.getByText('1 of 3 slots assigned')).toBeInTheDocument();

    await bindSlot(user, 'hostel', 'file-hostel');
    expect(screen.getByText('Bound to hostel.xlsx')).toBeInTheDocument();
    expect(screen.getByText('Bound to academic.csv')).toBeInTheDocument();
    expect(screen.getByText('2 of 3 slots assigned')).toBeInTheDocument();

    await bindSlot(user, 'academic', 'file-library');
    expect(screen.getByText('Bound to library.csv')).toBeInTheDocument();
    expect(screen.getByText('Bound to hostel.xlsx')).toBeInTheDocument();
    expect(screen.getByText('2 of 3 slots assigned')).toBeInTheDocument();
  });

  it('blocks apply when a required slot is unassigned and never calls the API', async () => {
    const user = userEvent.setup();
    renderPanel();
    await chooseTemplate(user);
    await bindSlot(user, 'academic', 'file-academic');

    await user.click(screen.getByRole('button', { name: 'Apply to uploaded files' }));

    expect(
      screen.getByText(
        /Assign a file to every template slot before applying\. Unassigned: hostel, library\./,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Unassigned required slots: hostel, library/)).toBeInTheDocument();
    expect(apiMocks.applyTemplate).not.toHaveBeenCalled();
    expect(onTemplateApplied).not.toHaveBeenCalled();
  });

  it('warns when the same uploaded file is bound to more than one slot', async () => {
    const user = userEvent.setup();
    renderPanel();
    await chooseTemplate(user);

    await bindSlot(user, 'academic', 'file-library');
    await bindSlot(user, 'hostel', 'file-library');

    expect(
      screen.getByText(
        /the same uploaded file is bound to more than one slot \(library\.csv\)\. The backend allows this/,
      ),
    ).toBeInTheDocument();
    // Every slot picker contains the full file list, so the shared file is
    // labelled in all three selects.
    expect(
      screen.getAllByRole('option', { name: /library\.csv \(used in multiple slots\)/ }),
    ).toHaveLength(3);
    expect(screen.getAllByText('library.csv (used in multiple slots)')).toHaveLength(3);
  });

  it('submits explicit slot-to-file bindings and reports the validated response', async () => {
    const user = userEvent.setup();
    renderPanel();
    await chooseTemplate(user);
    await bindSlot(user, 'academic', 'file-academic');
    await bindSlot(user, 'hostel', 'file-hostel');
    await bindSlot(user, 'library', 'file-library');

    await user.click(screen.getByRole('button', { name: 'Apply to uploaded files' }));

    await waitFor(() => expect(apiMocks.applyTemplate).toHaveBeenCalledTimes(1));
    expect(apiMocks.applyTemplate).toHaveBeenCalledWith(savedTemplate.id, {
      project_id: 'project-1',
      sources: [
        { slot: 'academic', file_id: 'file-academic' },
        { slot: 'hostel', file_id: 'file-hostel' },
        { slot: 'library', file_id: 'file-library' },
      ],
    });
    expect(onTemplateApplied).toHaveBeenCalledWith(templateConfiguration, applyResponse, {
      academic: 'file-academic',
      hostel: 'file-hostel',
      library: 'file-library',
    });
    expect(
      await screen.findByText(/Template 'College pilot' validated successfully/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Server validation passed: no blocking issues; effective keys: student_id\./),
    ).toBeInTheDocument();
    expect(screen.getByText(/Verification has NOT been executed\./)).toBeInTheDocument();
  });

  it('treats structured blocking issues as a failure and does not report success', async () => {
    const user = userEvent.setup();
    const blocked = Object.assign(new Error('Template application blocked'), {
      detail: {
        validation_report: {
          blocking: true,
          issues: [
            { slot: 'hostel', field: 'sheet_name', message: "Worksheet 'Roster' was not found." },
            { slot: 'library', message: 'Missing identity key column student_id.' },
          ],
          warnings: ['Header row contains trailing spaces.'],
        },
      },
    });
    apiMocks.applyTemplate.mockRejectedValue(blocked);

    renderPanel();
    await chooseTemplate(user);
    await bindSlot(user, 'academic', 'file-academic');
    await bindSlot(user, 'hostel', 'file-hostel');
    await bindSlot(user, 'library', 'file-library');
    await user.click(screen.getByRole('button', { name: 'Apply to uploaded files' }));

    expect(
      await screen.findByText(/Template application blocked — fix the issues below/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Worksheet 'Roster' was not found\./)).toBeInTheDocument();
    expect(screen.getByText(/Missing identity key column student_id\./)).toBeInTheDocument();
    expect(screen.getByText('Header row contains trailing spaces.')).toBeInTheDocument();
    expect(screen.getByText('slot: hostel')).toBeInTheDocument();
    expect(screen.getByText('sheet_name')).toBeInTheDocument();
    expect(onTemplateApplied).not.toHaveBeenCalled();
    expect(screen.queryByText(/validated successfully/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Verification has NOT been executed/)).not.toBeInTheDocument();
  });

  it('shows a generic failure without fabricating a successful apply', async () => {
    const user = userEvent.setup();
    apiMocks.applyTemplate.mockRejectedValue(new Error('Connection lost'));

    renderPanel();
    await chooseTemplate(user);
    await bindSlot(user, 'academic', 'file-academic');
    await bindSlot(user, 'hostel', 'file-hostel');
    await bindSlot(user, 'library', 'file-library');
    await user.click(screen.getByRole('button', { name: 'Apply to uploaded files' }));

    expect(await screen.findByText('Connection lost')).toBeInTheDocument();
    expect(onTemplateApplied).not.toHaveBeenCalled();
    expect(screen.queryByText(/validated successfully/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Server validation passed/)).not.toBeInTheDocument();
  });
});

describe('TemplatePanel lifecycle and management', () => {
  it('renders nothing and loads nothing in financial mode', () => {
    renderPanel('financial');

    expect(screen.queryByText('Reusable verification templates')).not.toBeInTheDocument();
    expect(apiMocks.listTemplates).not.toHaveBeenCalled();
  });

  it('surfaces template-list load failures', async () => {
    apiMocks.listTemplates.mockRejectedValue(new Error('Templates unavailable'));
    renderPanel();

    expect(await screen.findByText('Templates unavailable')).toBeInTheDocument();
  });

  it('saves the current setup as a NEW template with the current configuration', async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole('button', { name: /Save as new template/ }));
    await user.type(screen.getByLabelText('New template name'), 'Annual audit');
    await user.type(screen.getByLabelText('New template description'), 'Reusable college setup');
    await user.click(screen.getByRole('button', { name: /Save as new$/ }));

    await waitFor(() => expect(apiMocks.createTemplate).toHaveBeenCalledTimes(1));
    expect(apiMocks.createTemplate).toHaveBeenCalledWith({
      name: 'Annual audit',
      description: 'Reusable college setup',
      mode: 'organization',
      configuration: templateConfiguration,
    });
    expect(await screen.findByText("Saved new template 'College pilot'.")).toBeInTheDocument();
  });

  it('disables save-as-new when the wizard setup is not captureable', async () => {
    const user = userEvent.setup();
    getCurrentConfiguration.mockReturnValue(null);
    renderPanel();

    await user.click(screen.getByRole('button', { name: /Save as new template/ }));
    expect(screen.getByRole('button', { name: /Save as new$/ })).toBeDisabled();
    expect(
      screen.getByText(/Upload and map at least 2 files \(Steps 1–2\) before saving a template/),
    ).toBeInTheDocument();
  });

  it('updates configuration separately from name and description', async () => {
    const user = userEvent.setup();
    renderPanel();
    await chooseTemplate(user);

    await user.click(screen.getByRole('button', { name: /Update saved configuration/ }));
    expect(
      screen.getByText(/Its name and description will NOT change\. This cannot be undone\./),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Replace configuration/ }));

    await waitFor(() => expect(apiMocks.updateTemplate).toHaveBeenCalledTimes(1));
    expect(apiMocks.updateTemplate).toHaveBeenNthCalledWith(1, savedTemplate.id, {
      configuration: templateConfiguration,
    });
    expect(Object.keys(apiMocks.updateTemplate.mock.calls[0][1])).toEqual(['configuration']);
    expect(
      await screen.findByText(
        /Replaced the saved configuration of 'College pilot'\. Name and description were not changed\./,
      ),
    ).toBeInTheDocument();

    apiMocks.updateTemplate.mockResolvedValue({
      ...savedTemplate,
      name: 'College pilot (renamed)',
      description: 'Updated description',
    });
    await user.click(screen.getByRole('button', { name: /Rename \/ description/ }));
    const nameInput = screen.getByLabelText('Template name');
    const descriptionInput = screen.getByLabelText('Template description');
    await user.clear(nameInput);
    await user.type(nameInput, 'College pilot (renamed)');
    await user.clear(descriptionInput);
    await user.type(descriptionInput, 'Updated description');
    await user.click(screen.getByRole('button', { name: /Save details/ }));

    await waitFor(() => expect(apiMocks.updateTemplate).toHaveBeenCalledTimes(2));
    expect(apiMocks.updateTemplate).toHaveBeenNthCalledWith(2, savedTemplate.id, {
      name: 'College pilot (renamed)',
      description: 'Updated description',
    });
    expect(Object.keys(apiMocks.updateTemplate.mock.calls[1][1]).sort()).toEqual([
      'description',
      'name',
    ]);
  });

  it('requires explicit confirmation before deleting a template', async () => {
    const user = userEvent.setup();
    renderPanel();
    await chooseTemplate(user);

    await user.click(screen.getByRole('button', { name: /Delete/ }));
    expect(screen.getByText("Delete template 'College pilot'?")).toBeInTheDocument();
    expect(apiMocks.deleteTemplate).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByText("Delete template 'College pilot'?")).not.toBeInTheDocument();
    expect(apiMocks.deleteTemplate).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: /Delete/ }));
    await user.click(screen.getByRole('button', { name: /Delete template/ }));

    await waitFor(() => expect(apiMocks.deleteTemplate).toHaveBeenCalledWith(savedTemplate.id));
    expect(await screen.findByText("Deleted template 'College pilot'.")).toBeInTheDocument();
    expect(screen.getByLabelText('Choose a saved template')).toHaveValue('');
  });

  it('shows duplicate-name errors returned by the API', async () => {
    const user = userEvent.setup();
    apiMocks.createTemplate.mockRejectedValue(
      new Error("A template named 'College pilot' already exists."),
    );
    renderPanel();

    await user.click(screen.getByRole('button', { name: /Save as new template/ }));
    await user.type(screen.getByLabelText('New template name'), 'College pilot');
    await user.click(screen.getByRole('button', { name: /Save as new$/ }));

    expect(
      await screen.findByText("A template named 'College pilot' already exists."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('New template name')).toHaveValue('College pilot');
  });
});

describe('Batch 5: Template Reliability, Error Feedback & State Transitions', () => {
  it('displays loading state while templates are being fetched and transitions to loaded', async () => {
    let resolveList: (val: any) => void;
    const listPromise = new Promise((resolve) => {
      resolveList = resolve;
    });
    apiMocks.listTemplates.mockReturnValue(listPromise);

    renderPanel();

    // Check loading indicator and loading option in select
    expect(screen.getByText('Loading setups…')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Loading saved setups…' })).toBeInTheDocument();

    // Resolve templates
    resolveList!([savedTemplate]);

    // Transitions to ready: loading indicators disappear, template options available
    expect(await screen.findByRole('option', { name: /College pilot/ })).toBeInTheDocument();
    expect(screen.queryByText('Loading setups…')).not.toBeInTheDocument();
  });

  it('displays useful empty state when no saved templates exist', async () => {
    apiMocks.listTemplates.mockResolvedValue([]);
    renderPanel();

    expect(
      await screen.findByText(/No saved setups yet\. Once you set up and match your spreadsheet columns/),
    ).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '— No saved setups yet —' })).toBeInTheDocument();
  });

  it('allows user to retry after a failed template load request', async () => {
    const user = userEvent.setup();
    apiMocks.listTemplates.mockRejectedValueOnce(
      new Error('Network error connecting to VerifyGrid API: Failed to fetch'),
    );

    renderPanel();

    // Actionable network error shown
    expect(
      await screen.findByText('Network error connecting to VerifyGrid API: Failed to fetch'),
    ).toBeInTheDocument();
    const retryBtn = screen.getByRole('button', { name: /Retry/ });
    expect(retryBtn).toBeInTheDocument();

    // Setup success for retry
    apiMocks.listTemplates.mockResolvedValueOnce([savedTemplate]);
    await user.click(retryBtn);

    // Error cleared and templates loaded
    expect(await screen.findByRole('option', { name: /College pilot/ })).toBeInTheDocument();
    expect(
      screen.queryByText('Network error connecting to VerifyGrid API: Failed to fetch'),
    ).not.toBeInTheDocument();
  });

  it('prevents duplicate submissions under rapid synchronous clicks and releases lock upon completion', async () => {
    const user = userEvent.setup();
    let resolveFirstCreate: (val: any) => void;
    const firstPromise = new Promise((resolve) => {
      resolveFirstCreate = resolve;
    });
    apiMocks.createTemplate.mockReturnValueOnce(firstPromise);

    renderPanel();

    await user.click(screen.getByRole('button', { name: /Save as new template/ }));
    await user.type(screen.getByLabelText('New template name'), 'Unique Setup');
    const saveBtn = screen.getByRole('button', { name: /Save as new$/ });

    // Trigger multiple clicks synchronously within one event loop boundary using fireEvent
    fireEvent.click(saveBtn);
    fireEvent.click(saveBtn);
    fireEvent.click(saveBtn);

    // Exactly one API mutation request should be dispatched while pending
    expect(apiMocks.createTemplate).toHaveBeenCalledTimes(1);

    // Complete the first operation
    resolveFirstCreate!({ ...savedTemplate, name: 'Unique Setup' });
    await waitFor(() => expect(screen.queryByText('Saving…')).not.toBeInTheDocument());
    expect(await screen.findByText("Saved new template 'Unique Setup'.")).toBeInTheDocument();

    // Confirm the lock is released and another legitimate submission can succeed afterward
    apiMocks.createTemplate.mockResolvedValueOnce({ ...savedTemplate, name: 'Second Setup' });
    await user.click(screen.getByRole('button', { name: /Save as new template/ }));
    await user.type(screen.getByLabelText('New template name'), 'Second Setup');
    const secondSaveBtn = screen.getByRole('button', { name: /Save as new$/ });
    await user.click(secondSaveBtn);

    await waitFor(() => expect(apiMocks.createTemplate).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Saved new template 'Second Setup'.")).toBeInTheDocument();
  });

  it('renders actionable error message when save fails with network error', async () => {
    const user = userEvent.setup();
    apiMocks.createTemplate.mockRejectedValue(
      new Error('Network error connecting to VerifyGrid API: Failed to fetch'),
    );

    renderPanel();

    await user.click(screen.getByRole('button', { name: /Save as new template/ }));
    await user.type(screen.getByLabelText('New template name'), 'Test Setup');
    await user.click(screen.getByRole('button', { name: /Save as new$/ }));

    expect(
      await screen.findByText(
        "We couldn't connect to VerifyGrid to save this setup. Check your connection and try again.",
      ),
    ).toBeInTheDocument();
  });

  it('prevents misleading success message and reports blocking issues when backend apply returns blocking issues', async () => {
    const user = userEvent.setup();
    apiMocks.applyTemplate.mockResolvedValue({
      template_id: savedTemplate.id,
      project_id: project.id,
      mode: 'organization',
      effective_request: {} as any,
      validation_report: {
        blocking: true,
        issues: [{ slot: 'academic', message: 'Identity key column missing in file' }],
        warnings: [],
      },
    });

    renderPanel();
    await chooseTemplate(user);
    await bindSlot(user, 'academic', 'file-academic');
    await bindSlot(user, 'hostel', 'file-hostel');
    await bindSlot(user, 'library', 'file-library');
    await user.click(screen.getByRole('button', { name: 'Apply to uploaded files' }));

    // Blocking issues displayed, never misleading success
    expect(
      await screen.findByText(/Template application blocked — fix the issues below, then apply again\./),
    ).toBeInTheDocument();
    expect(screen.getByText(/Identity key column missing in file/)).toBeInTheDocument();
    expect(screen.queryByText(/validated successfully/)).not.toBeInTheDocument();
    expect(onTemplateApplied).not.toHaveBeenCalled();
  });
});
