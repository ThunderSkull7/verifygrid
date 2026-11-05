/**
 * Batch 3 terminology contracts.
 *
 * Verifies that simplified, user-friendly labels and copy are properly wired
 * across shared frontend components and status definitions.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const readSrc = (file: string) =>
  readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8');

test('StatusBadge uses simplified, non-technical copy', () => {
  const code = readSrc('components/StatusBadge.tsx');
  assert.match(code, /running:\s*\{\s*label:\s*'Checking…'/);
  assert.match(code, /preprocessed:\s*\{\s*label:\s*'Checked'/);
  assert.match(code, /none:\s*\{\s*label:\s*'Match'/);
  assert.match(code, /identical:\s*\{\s*label:\s*'Match'/);
  assert.match(code, /field_mismatch:\s*\{\s*label:\s*'Difference'/);
  assert.match(code, /missing_in_target:\s*\{\s*label:\s*'Missing in comparison file'/);
  assert.match(code, /missing_in_source:\s*\{\s*label:\s*'Missing in main file'/);
});

test('Navigation and tab metadata use simplified labels', () => {
  const sidebar = readSrc('components/Sidebar.tsx');
  assert.match(sidebar, /<span>Organization Records<\/span>/);
  assert.match(sidebar, /currentTab === 'financial' \? 'Financial Auditing' : 'Compare Records'/);

  const app = readSrc('App.tsx');
  assert.match(app, /verify:\s*\{\s*title:\s*'Organization Records',\s*crumb:\s*'Compare records'\s*\}/);
  assert.match(app, /financial:\s*\{\s*title:\s*'Financial Auditing',\s*crumb:\s*'Compare financial records'\s*\}/);
});

test('FileUploadSection uses trusted file and file to check roles', () => {
  const upload = readSrc('components/FileUploadSection.tsx');
  assert.match(upload, /Main file to trust/);
  assert.match(upload, /File to check/);
  assert.match(upload, /Check Data/);
  assert.match(upload, /Upload spreadsheets & check data/);
});

test('RecordInspectorDrawer presents plain-language diff and metrics', () => {
  const drawer = readSrc('components/RecordInspectorDrawer.tsx');
  assert.match(drawer, /RECORD DETAILS/);
  assert.match(drawer, /Total Difference Amount/);
  assert.match(drawer, /Net Difference/);
  assert.match(drawer, /Side-by-Side Column Comparison/);
  assert.match(drawer, />Main File \(Original\)<\/th>/);
  assert.match(drawer, />Comparison File \(Original\)<\/th>/);
});

test('ProjectsView guides non-technical users in spreadsheet comparison', () => {
  const projects = readSrc('components/ProjectsView.tsx');
  assert.match(projects, /Organize your spreadsheets and record comparisons/);
  assert.match(projects, /Create your first project to upload spreadsheets and compare records\./);
});

test('CryptographicAuditViewer uses Tamper-Evident and avoids overstating security', () => {
  const viewer = readSrc('components/CryptographicAuditViewer.tsx');
  assert.match(viewer, /Tamper-Evident Audit Trail/);
  assert.doesNotMatch(viewer, /tamper-proof/i);
});


