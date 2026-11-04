/**
 * Batch 14: minimal zero-dependency frontend harness.
 *
 * Runs pure TypeScript mapping logic with Node's built-in test runner and
 * type stripping (Node >= 22.6). No Vitest/jsdom/testing-library stack is
 * added; React interaction coverage remains a documented manual procedure.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  buildAllSuggestions,
  buildFieldOwnershipPayload,
  collectCanonicalAttributes,
  COLUMN_SYNONYMS,
  computeComparedAttributes,
  computeComparedAttributesMultiPrimary,
  normalizeColumn,
  suggestMappingsForFile,
  usedColumnsForFile,
} from '../src/services/columnMapping.ts';
import type {
  ColumnMetadata,
  FileColumnMappings,
  PreprocessingResult,
  UploadedDataset,
} from '../src/types/index.ts';

const column = (name: string): ColumnMetadata => ({
  original_name: name,
  normalized_name: name,
  detected_type: 'text',
  null_count: 0,
  non_null_count: 1,
  sample_values: [],
});

const profile = (columns: string[]): PreprocessingResult => ({
  source_file_id: 'file',
  project_id: 'project',
  original_filename: 'synthetic.csv',
  file_type: 'csv',
  total_source_rows: 1,
  data_rows_count: 1,
  empty_rows_count: 0,
  duplicate_rows_count: 0,
  columns: columns.map(column),
  column_mapping: {},
  duplicate_record_row_numbers: [],
  issues: [],
  preview_rows: [],
});

const dataset = (
  id: string,
  columns: string[],
  isPrimary = false,
): UploadedDataset => ({
  id,
  name: `${id}.csv`,
  label: id,
  isPrimary,
  profile: profile(columns),
});

test('normalizeColumn matches the backend snake-case convention', () => {
  assert.equal(normalizeColumn('Enrolment No'), 'enrolment_no');
  assert.equal(normalizeColumn('HostelName'), 'hostel_name');
  assert.equal(normalizeColumn('Student-ID'), 'student_id');
  assert.equal(normalizeColumn('  Batch  Year  '), 'batch_year');
});

test('collectCanonicalAttributes unions columns and excludes unified keys', () => {
  const datasets = [
    dataset('academic', ['student_id', 'name', 'batch']),
    dataset('library', ['student_id', 'name', 'membership_status']),
  ];
  assert.deepEqual(collectCanonicalAttributes(datasets, ['student_id']), [
    'batch',
    'membership_status',
    'name',
  ]);
});

test('exact matches are suggested; synonyms require confirmation; unmapped stay absent', () => {
  const ds = dataset('library', ['student_id', 'name', 'full_name', 'membership_status']);
  const mappings = suggestMappingsForFile(ds, [
    'student_name',
    'membership_status',
    'room_number',
  ]);
  assert.deepEqual(mappings.student_name, { column: 'full_name', state: 'needs_confirmation' });
  assert.deepEqual(mappings.membership_status, {
    column: 'membership_status',
    state: 'suggested',
  });
  assert.equal(mappings.room_number, undefined);
});

test('computeComparedAttributes compares only attributes mapped in every source', () => {
  const academic = dataset('academic', ['student_id', 'name', 'batch'], true);
  const hostel = dataset('hostel', ['student_id', 'name']);
  const library = dataset('library', ['student_id', 'name']);
  const mappings: Record<string, FileColumnMappings> = buildAllSuggestions(
    [academic, hostel, library],
    ['student_id'],
    {},
  );
  // Suggest 'batch' only for the primary (as if the user mapped it manually).
  mappings.academic.batch = { column: 'batch', state: 'suggested' };
  assert.deepEqual(
    computeComparedAttributes([academic, hostel, library], mappings, ['student_id']),
    ['name'],
  );
});

test('computeComparedAttributesMultiPrimary includes attributes carried by at least two sources', () => {
  const academic = dataset('academic', ['student_id', 'name', 'batch'], true);
  const hostel = dataset('hostel', ['student_id', 'name', 'batch', 'hostel_name'], true);
  const library = dataset('library', ['student_id', 'name']);
  const mappings: Record<string, FileColumnMappings> = buildAllSuggestions(
    [academic, hostel, library],
    ['student_id'],
    {},
  );
  assert.deepEqual(
    computeComparedAttributesMultiPrimary(
      [academic, hostel, library],
      mappings,
      ['student_id'],
    ),
    ['batch', 'name'],
  );
});

test('usedColumnsForFile never reports the attribute being edited', () => {
  const mappings: FileColumnMappings = {
    name: { column: 'full_name', state: 'confirmed' },
    batch: { column: 'batch_year', state: 'suggested' },
  };
  assert.deepEqual([...usedColumnsForFile('academic', { academic: mappings })], [
    'full_name',
    'batch_year',
  ]);
  assert.deepEqual(
    [...usedColumnsForFile('academic', { academic: mappings }, 'name')],
    ['batch_year'],
  );
});

test('buildAllSuggestions fills only files that have no mapping state yet', () => {
  const academic = dataset('academic', ['student_id', 'name'], true);
  const library = dataset('library', ['student_id', 'name']);
  const existing: Record<string, FileColumnMappings> = {
    academic: { name: { column: 'name', state: 'confirmed' } },
  };
  const result = buildAllSuggestions([academic, library], ['student_id'], existing);
  assert.equal(result.academic, existing.academic);
  assert.deepEqual(result.library.name, { column: 'name', state: 'suggested' });
});

test('buildFieldOwnershipPayload resolves primary carrying sources for all compared attributes', () => {
  const academic = dataset('file-academic', ['student_id', 'gpa', 'degree'], true);
  const hostel = dataset('file-hostel', ['student_id', 'room_no', 'block'], true);
  const idcard = dataset('file-idcard', ['student_id', 'gpa', 'room_no'], false);

  const mappings: Record<string, FileColumnMappings> = {
    'file-academic': {
      gpa: { column: 'gpa', state: 'suggested' },
      degree: { column: 'degree', state: 'suggested' },
    },
    'file-hostel': {
      room_no: { column: 'room_no', state: 'suggested' },
      block: { column: 'block', state: 'suggested' },
    },
    'file-idcard': {
      gpa: { column: 'gpa', state: 'suggested' },
      room_no: { column: 'room_no', state: 'suggested' },
    },
  };

  // User did not manually set fieldOwners in UI state: empty dict
  const fieldOwners: Record<string, string> = {};
  const aliasFor = (id: string) => id.replace('file-', '');

  const payload = buildFieldOwnershipPayload(
    [academic, hostel, idcard],
    mappings,
    fieldOwners,
    ['student_id'],
    aliasFor,
  );

  assert.ok(payload);
  // Academic carries gpa and is primary -> owner of gpa
  assert.equal(payload.gpa, 'academic');
  // Hostel carries room_no and is primary -> owner of room_no
  assert.equal(payload.room_no, 'hostel');
});

test('COLUMN_SYNONYMS supports bidirectional college attributes', () => {
  assert.ok(COLUMN_SYNONYMS.date_of_birth.includes('dob'));
  assert.ok(COLUMN_SYNONYMS.dob.includes('date_of_birth'));
  assert.ok(COLUMN_SYNONYMS.department.includes('course'));
  assert.ok(COLUMN_SYNONYMS.course.includes('department'));
  assert.ok(COLUMN_SYNONYMS.blood_group.includes('blood_type'));
});
