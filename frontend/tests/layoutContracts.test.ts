/**
 * Batch 2 layout contracts.
 *
 * jsdom does not perform layout, so these checks guard the shared CSS
 * mechanisms that keep cards, tables and dialogs inside their containers:
 * shrinkable flex/grid children, table-local horizontal scrolling, wrapping
 * text, and viewport-bounded dialogs.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

test('Batch 1 header wrapping remains in place', () => {
  assert.match(css, /\.page-title\s*\{[^}]*min-width:\s*0;/s);
  assert.match(css, /\.page-subtitle\s*\{[^}]*min-width:\s*0;[^}]*overflow-wrap:\s*break-word;/s);
});

test('cards can shrink, wrap long copy and do not accumulate nested margins', () => {
  assert.match(css, /\.card,[\s\S]*?\.record-inspector-drawer\s*\{[^}]*min-width:\s*0;/);
  assert.match(css, /\.card-title,\s*\.card-description\s*\{[^}]*overflow-wrap:\s*anywhere;/);
  assert.match(css, /\.card \.card\s*\{[^}]*margin-bottom:\s*0;/);
});

test('wide tables scroll locally and long cell values wrap', () => {
  assert.match(css, /\.table-container\s*\{[^}]*overflow-x:\s*auto;/s);
  assert.match(css, /\.table-container\s*\{[^}]*max-width:\s*100%;/s);
  assert.match(css, /\.data-table td\s*\{[^}]*overflow-wrap:\s*anywhere;/);
});

test('exception cluster cards contain machine-generated identifiers', () => {
  assert.match(css, /\.cluster-card\s*\{[^}]*overflow-wrap:\s*anywhere;/s);
  assert.match(css, /\.cluster-card h4,[\s\S]*?\.cluster-card \.cluster-id\s*\{[^}]*overflow-wrap:\s*anywhere;/);
});

test('dialogs are viewport-bounded and their actions can wrap', () => {
  assert.match(css, /\.modal\s*\{[^}]*max-height:\s*calc\(100dvh - 40px\);/s);
  assert.match(css, /\.modal-header,\s*\.modal-footer\s*\{[^}]*flex-wrap:\s*wrap;/);
  assert.match(css, /\.modal-header > :first-child\s*\{[^}]*flex:\s*1 1 0;/s);
  assert.match(css, /\.drawer-panel\s*\{[^}]*max-height:\s*100dvh;/s);
});

test('dense drawer tables keep readable minimum widths', () => {
  assert.match(css, /\.drawer-body \.data-table\s*\{[^}]*min-width:\s*960px;/s);
  assert.match(css, /\.quarantine-table\s*\{[^}]*table-layout:\s*fixed;/s);
  assert.match(css, /\.inspector-diff-table\s*\{[^}]*min-width:\s*860px;/s);
});

test('drawer metrics and wizard steps adapt instead of clipping', () => {
  assert.match(css, /\.drawer-metrics\s*\{[^}]*repeat\(auto-fit, minmax\(108px, 1fr\)\)/s);
  assert.match(css, /\.drawer-tabs\s*\{[^}]*overflow-x:\s*auto;/s);
  assert.match(css, /@media \(max-width: 900px\)[\s\S]*?\.wizard-stepper-header\s*\{[^}]*overflow-x:\s*auto;/);
});
