/**
 * Batch 4 Guided Comparison Workflow contracts.
 *
 * Verifies that the organization comparison journey is simplified into a clear,
 * task-first workflow for college administrators:
 * 1. Upload guidance with clear next-action prompts
 * 2. File role clarity (Main file to trust vs Files to check)
 * 3. Intelligent matching column preference (student_id detection & quick selector)
 * 4. Step 3 Pre-Comparison Review Summary card before execution
 * 5. Progressive disclosure for advanced settings & backup matching keys
 * 6. Navigation and state preservation
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const readSrc = (file: string) =>
  readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8');

test('CSS contains guided summary card and progressive disclosure classes', () => {
  const css = readSrc('index.css');
  assert.match(css, /\.guided-summary-card\s*\{[^}]*background-color:\s*var\(--bg-card\);/s);
  assert.match(css, /\.progressive-details\s*\{[^}]*background-color:\s*var\(--bg-subtle\);/s);
  assert.match(css, /\.progressive-details\[open\]\s*\{[^}]*background-color:\s*var\(--bg-card\);/s);
  assert.match(css, /\.progressive-details\s*>\s*summary\s*\{[^}]*cursor:\s*pointer;/s);
});

test('ReconciliationWizard guides upload with progressive step prompts', () => {
  const code = readSrc('components/ReconciliationWizard.tsx');
  // Upload prompts for 0, 1, and 2+ files
  assert.match(code, /No files added yet\. Drop 2 or more files above to begin\./);
  assert.match(code, /1 file uploaded\..*?Add at least 1 more file to compare against/s);
  assert.match(code, /Continue to file setup/);
});

test('ReconciliationWizard prefers student_id as matching column when available and validated', () => {
  const code = readSrc('components/ReconciliationWizard.tsx');
  // Safe student_id validation heuristic across all required files + recommendation score
  assert.match(code, /studentIdInAllFiles\s*=\s*uploadedDatasets\.length >= 2/);
  assert.match(code, /uploadedDatasets\.every/);
  assert.match(code, /studentRec\.overall_score >= 0.7/);
  // Recommended tag in matching column picker
  assert.match(code, /Recommended for Student Rosters/);
  assert.match(code, /student_id detected/);
});

test('ReconciliationWizard separates Step 2 into clear logical stages', () => {
  const code = readSrc('components/ReconciliationWizard.tsx');
  assert.match(code, /1\.\s*Identify File Roles/);
  assert.match(code, /2\.\s*Select Matching Column/);
  assert.match(code, /3\.\s*Match Column Names/);
  // Preserves exact test anchor
  assert.match(code, /Step 2: Name Your Files &amp; Matching Keys/);
});

test('ReconciliationWizard progressively discloses advanced matching options in Step 2', () => {
  const code = readSrc('components/ReconciliationWizard.tsx');
  // Multi-primary field ownership in collapsible details
  assert.match(code, /<details className="progressive-details">[\s\S]*?Advanced:\s*Multiple authoritative sources/);
  // Backup matching columns in collapsible details
  assert.match(code, /<details className="progressive-details"[\s\S]*?Backup matching columns \(optional\)/);
});

test('ReconciliationWizard provides Pre-Comparison Review Summary in Step 3', () => {
  const code = readSrc('components/ReconciliationWizard.tsx');
  assert.match(code, /Pre-Comparison Review Summary/);
  assert.match(code, /Main Trusted File/);
  assert.match(code, /Files to Check/);
  assert.match(code, /Columns Being Compared/);
});

test('ReconciliationWizard progressively discloses advanced comparison rules in Step 3', () => {
  const code = readSrc('components/ReconciliationWizard.tsx');
  // Essential rules are visible
  assert.match(code, /Text &amp; Spacing Cleanup/);
  assert.match(code, /Number & Amount Differences/);
  // Advanced rules are collapsed
  assert.match(code, /<details className="progressive-details"[\s\S]*?Advanced comparison settings/);
  assert.match(code, /Payment \/ Transaction Date Range/);
  assert.match(code, /Equivalent Status Terms/);
  assert.match(code, /Filter Records Before Comparing/);
});
