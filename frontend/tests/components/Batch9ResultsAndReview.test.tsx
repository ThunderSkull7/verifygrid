import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { VerificationResultsView } from '../../src/components/VerificationResultsView';
import { RecordInspectorDrawer } from '../../src/components/RecordInspectorDrawer';
import type { VerificationResponse, VerificationResultItem } from '../../src/types';

describe('Batch 9: VerificationResultsView & RecordInspectorDrawer', () => {
  const mockOrgResponse: VerificationResponse = {
    summary: {
      total_source_records: 150,
      total_target_records: 148,
      matched_records: 145,
      identical_matches: 135,
      field_mismatches: 10,
      unmatched_source_records: 5,
      unmatched_target_records: 3,
      duplicate_source_records: 0,
      duplicate_target_records: 0,
      duplicate_source_keys_count: 0,
      duplicate_target_keys_count: 0,
      total_discrepancies: 18,
      status: 'completed',
      attribute_comparisons_completed: 4,
    },
    results: [
      {
        id: 'rec-1',
        match_status: 'identical',
        discrepancy_category: 'none',
        key_values: { student_id: 'S101', term: 'Fall 2025' },
        source_row_number: 2,
        target_row_number: 2,
        source_record: { student_id: 'S101', name: 'Aarav Sharma', status: 'Enrolled' },
        target_record: { student_id: 'S101', name: 'Aarav Sharma', status: 'Enrolled' },
        field_differences: [],
        exposure_amount: 0,
        variance_amount: 0,
      },
      {
        id: 'rec-2',
        match_status: 'field_mismatch',
        discrepancy_category: 'field_mismatch',
        key_values: { student_id: 'S102', term: 'Fall 2025' },
        source_row_number: 3,
        target_row_number: 4,
        source_record: { student_id: 'S102', name: 'Diya Patel', status: 'Enrolled' },
        target_record: { student_id: 'S102', name: 'Diya Patel', status: 'Leave of Absence' },
        field_differences: [
          {
            field_name: 'status',
            source_value: 'Enrolled',
            target_value: 'Leave of Absence',
            difference_type: 'value_mismatch',
          },
        ],
        exposure_amount: 0,
        variance_amount: 0,
      },
    ],
  };

  it('renders Organization Records mode with non-technical headers and cards', () => {
    render(
      <VerificationResultsView
        projectId="test-proj"
        response={mockOrgResponse}
        mode="organization"
        fileLabels={{ primary: 'Registrar Master', target: 'LMS Sync' }}
      />
    );

    // Header title for organization records
    expect(screen.getByText(/Verification Results & Summary/i)).toBeInTheDocument();
    expect(screen.getByText(/150 records evaluated across source files/i)).toBeInTheDocument();

    // 4 KPI Cards in Organization mode
    expect(screen.getByText('Total Records')).toBeInTheDocument();
    expect(screen.getByText('150')).toBeInTheDocument();

    expect(screen.getByText('Clean Matches')).toBeInTheDocument();
    expect(screen.getByText('135')).toBeInTheDocument();

    expect(screen.getByText('Differences Found')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();

    expect(screen.getByText('Attention Required')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument(); // 5 unmatched src + 3 unmatched tgt

    // Key values formatted cleanly without raw JSON
    expect(screen.getByText('student_id: S101 · term: Fall 2025')).toBeInTheDocument();
    expect(screen.getByText('student_id: S102 · term: Fall 2025')).toBeInTheDocument();
    expect(screen.queryByText(/\{"student_id":/)).not.toBeInTheDocument();

    // Friendly file row labels
    expect(screen.getByText(/Registrar Master: 2 \| LMS Sync: 2/i)).toBeInTheDocument();
  });

  it('renders Financial Auditing mode with dollar exposure and financial cards', () => {
    const financialResponse: VerificationResponse = {
      ...mockOrgResponse,
      summary: {
        ...mockOrgResponse.summary,
        gross_exposure: 12500.5,
        net_variance: -3400.0,
        verified_amount: 98000.0,
        outstanding_amount: 12500.5,
      },
    };

    render(
      <VerificationResultsView
        projectId="test-proj"
        response={financialResponse}
        mode="financial"
      />
    );

    expect(screen.getByText(/Financial Materiality & Reconciliation Summary/i)).toBeInTheDocument();
    expect(screen.getByText('Gross Exposure')).toBeInTheDocument();
    expect(screen.getByText('Net Variance')).toBeInTheDocument();
    expect(screen.getByText('Reconciled Value')).toBeInTheDocument();
    expect(screen.getByText('Outstanding Variance')).toBeInTheDocument();
    expect(screen.getAllByText('$12,500.50').length).toBeGreaterThanOrEqual(1);
  });

  it('RecordInspectorDrawer renders human-readable record identification and side-by-side comparison', () => {
    const record: VerificationResultItem = {
      id: 'rec-2',
      match_status: 'field_mismatch',
      discrepancy_category: 'field_mismatch',
      key_values: { student_id: 'S102', full_name: 'Diya Patel' },
      source_row_number: 3,
      target_row_number: 4,
      source_record: { student_id: 'S102', full_name: 'Diya Patel', status: 'Enrolled' },
      target_record: { student_id: 'S102', full_name: 'Diya Patel', status: 'Leave of Absence' },
      field_differences: [
        {
          field_name: 'status',
          source_value: 'Enrolled',
          target_value: 'Leave of Absence',
          difference_type: 'value_mismatch',
        },
      ],
      exposure_amount: 0,
      variance_amount: 0,
    };

    render(
      <RecordInspectorDrawer
        isOpen={true}
        onClose={vi.fn()}
        record={record}
        projectId="test-proj"
        mode="organization"
        fileLabels={{ primary: 'Official Registrar', target: 'Hostel System' }}
      />
    );

    // Plain-language record identifier in title
    expect(screen.getByText(/student id: S102 · full name: Diya Patel/i)).toBeInTheDocument();

    // Side-by-side table headings
    expect(screen.getByText('Main File (Original)')).toBeInTheDocument();
    expect(screen.getByText('Comparison File (Original)')).toBeInTheDocument();

    // Values in side-by-side cells
    expect(screen.getByText('Enrolled')).toBeInTheDocument();
    expect(screen.getByText('Leave of Absence')).toBeInTheDocument();

    // Mode-aware organization overview section
    expect(screen.getByText('Fields Evaluated')).toBeInTheDocument();
    expect(screen.getByText('Matching Fields')).toBeInTheDocument();
  });

  it('displays unmistakable warning when zero fields are evaluated', () => {
    const untestedResponse: VerificationResponse = {
      ...mockOrgResponse,
      summary: {
        ...mockOrgResponse.summary,
        attribute_comparisons_completed: 0,
        matched_records: 145,
      },
    };

    render(
      <VerificationResultsView
        projectId="test-proj"
        response={untestedResponse}
        mode="organization"
      />
    );

    expect(screen.getByText(/Keys Matched — No Fields Evaluated/i)).toBeInTheDocument();
    expect(screen.getByText(/zero comparable fields were evaluated/i)).toBeInTheDocument();
    expect(screen.queryByText(/100% Record Match Verified/i)).not.toBeInTheDocument();
  });

  it('displays clean verified state when 100% records match with evaluated fields', () => {
    const cleanResponse: VerificationResponse = {
      summary: {
        total_source_records: 100,
        total_target_records: 100,
        matched_records: 100,
        identical_matches: 100,
        field_mismatches: 0,
        unmatched_source_records: 0,
        unmatched_target_records: 0,
        duplicate_source_records: 0,
        duplicate_target_records: 0,
        duplicate_source_keys_count: 0,
        duplicate_target_keys_count: 0,
        total_discrepancies: 0,
        status: 'completed',
        attribute_comparisons_completed: 3,
        gross_exposure: 0,
      },
      results: [],
    };

    render(
      <VerificationResultsView
        projectId="test-proj"
        response={cleanResponse}
        mode="organization"
      />
    );

    expect(screen.getByText(/100% Record Match Verified/i)).toBeInTheDocument();
    expect(screen.getByText(/All matched records have identical values/i)).toBeInTheDocument();
  });
});
