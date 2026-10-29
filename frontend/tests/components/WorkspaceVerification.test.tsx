import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { WorkspaceVerification } from '../../src/App';
import { datasetHostel, project } from './fixtures';

const apiMocks = vi.hoisted(() => ({
  listTemplates: vi.fn(),
}));

vi.mock('../../src/services/api', () => ({ api: apiMocks }));

describe('App workspace wiring', () => {
  it('forwards worksheet changes from the upload section to App state', async () => {
    const user = userEvent.setup();
    const onWorksheetChange = vi.fn();
    apiMocks.listTemplates.mockResolvedValue([]);

    render(
      <WorkspaceVerification
        project={project}
        mode="verify"
        uploadedDatasets={[datasetHostel]}
        onFileUploaded={vi.fn()}
        onLabelChange={vi.fn()}
        onRoleChange={vi.fn()}
        onWorksheetChange={onWorksheetChange}
        onRemoveFile={vi.fn()}
      />,
    );

    await user.selectOptions(
      screen.getByLabelText('Worksheet to use from Hostel Allocation'),
      'Roster',
    );

    expect(onWorksheetChange).toHaveBeenCalledWith('file-hostel', 'Roster');
  });
});
