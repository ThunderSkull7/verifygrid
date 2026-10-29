# VerifyGrid Batch 20 — Governance Migration Recovery Audit

**Date:** 2026-10-29 (PKT, UTC+05:30)  
**Batch type:** Read-only repository and source audit  
**Branch:** `feature/batch-4-rule-engine-aggregation`  
**HEAD:** `c91e9b37074483eeb7469dc943e1735fd5f5be02`  
**Recovered source commit:** `58a0e5c243978480c4ca817c537c700ed6b20516`  
**Remote database:** Not contacted. No Neon, production, staging, or other remote database was inspected.  
**Execution status:** Audit only. No migration strategy is selected, authorized, or executed by this report.

## Evidence legend

- **[Confirmed from current repository evidence]** — directly observable in the current working tree, current files, or read-only local Git output.
- **[Confirmed from pinned remote source]** — directly observable in the exact GitHub commit, file, tree, or API response identified by the pinned SHA.
- **[Confirmed from historical source context]** — observable in the repository tree at the pinned SHA, but not part of the current local branch. This is historical context, not current application state.
- **[Reported by earlier batch]** — asserted by an earlier batch or repository document, but not independently re-established in Batch 20.
- **[Not independently verified]** — depends on a database, deployment, backup, or other external state that was not inspected.
- **[Inference requiring further evidence]** — a reasoned consequence of current facts that depends on an unverified target, runtime behavior, historical deployment, or future decision.

A document containing a claim is evidence that the claim was made. The truth of the claim is classified separately. A GitHub commit is evidence that a file was committed to that repository; it is not evidence that any database executed it.

---

## 1. Executive summary

### 1.1 Principal findings

1. **[Confirmed from pinned remote source]** The exact requested file was retrieved from the specified commit, not from a branch name or a similarly named local file. The file is `backend/migrations/versions/0004_enterprise_governance_and_materiality.py`, 156 lines, 10,032 bytes, with Git blob SHA `5f66fa2ca8faab62fdfe27e3369a3416f2d03276`. The downloaded content has SHA-256 `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB`. The Git blob SHA computed locally matches the blob SHA returned by the GitHub API for that commit.

2. **[Confirmed from pinned remote source]** The file declares revision `0004_enterprise_governance`, parent `0003_user_password`, no branch labels, and no `depends_on`. The commit `58a0e5c243978480c4ca817c537c700ed6b20516` adds exactly this file (156 additions, 0 deletions). Its parent is `777a41aeee08c70334da358d2c03534338800185`. The commit is unsigned; content integrity is strong because the SHA and blob identity match, but the commit does not provide a cryptographic author attestation beyond GitHub hosting.

3. **[Confirmed from pinned remote source]** At that commit, `backend/migrations/versions/` contained only `0001_initial_tables.py`, `0002_verification_runs.py`, `0003_user_password.py`, and the recovered `0004_enterprise_governance_and_materiality.py`. It did not contain `0004_verification_templates.py` or `0005_verification_lineage.py`. The local blobs for `0001`–`0003` are identical to the remote blobs at that commit, so the two histories share content-identical ancestry through `0003_user_password` and diverge immediately afterward.

4. **[Confirmed from current repository evidence]** The current local chain remains:
   `0001_initial_tables` → `0002_verification_runs` → `0003_user_password` → `0004_verification_templates` → `0005_verification_lineage`.
   It has one head, `0005_verification_lineage`. The recovered revision and `0004_verification_templates` are both declared children of `0003_user_password`.

5. **[Confirmed from current repository evidence]** The recovered migration and `0005_verification_lineage.py` add the same six columns:
   `verification_runs.sources`; and on `verification_discrepancies`, `source_row_indices`, `source_records`, `child_records`, `aggregated_amount`, and `expected_amount`.
   The SQLAlchemy declarations are identical: JSON for the four JSON fields on discrepancies plus the run `sources` field, Float for the two amount fields, all nullable, with no defaults, indexes, or foreign keys. The two migrations also contain matching downgrade drops for all six columns.

6. **[Confirmed from current repository evidence]** The recovered migration contains governance and materiality objects that the current ORM does not declare:
   - `users.role`;
   - nine `verification_runs.sign_off_*` columns, plus two foreign keys and one index;
   - seventeen materiality/clustering/review columns on `verification_discrepancies`, plus six indexes;
   - the `audit_events` table, with fourteen columns, three foreign keys, and six indexes.

   The current ORM has no `AuditEvent` model, no `users.role`, no sign-off fields, and no materiality/clustering/review fields. The current `audit_log.py` is a 0-byte, unimported placeholder. The current ORM does declare `VerificationTemplate`, which the recovered migration does not create.

7. **[Confirmed from current repository evidence]** `verification_discrepancies.reason_code` and `confidence_score` are read-only Python properties in the current ORM, computed from `field_differences` and `match_status`. They are not mapped database columns. The recovered migration would create physical columns with those names. Current code would not map or read them, and the current properties have no setters. This is a semantic conflict, not merely an extra column.

8. **[Confirmed from historical source context]** The historical ORM at the same pinned commit is materially different. It contains a role-aware `User`, the nine sign-off fields, the materiality fields, an `AuditEvent` model mapped to `audit_events`, and mapped `_reason_code`/`_confidence_score` columns using the database names `reason_code`/`confidence_score`. The recovered migration is largely consistent with that historical ORM. However, the historical ORM also declares `DiscrepancyReviewDecision` on table `discrepancy_review_decisions`, and no migration file in the pinned commit's migration tree creates that table. The recovered lineage therefore has an unresolved historical schema gap of its own.

9. **[Inference requiring further evidence]** The current migration chain cannot incorporate the recovered revision *unmodified* while preserving both the current ancestry and the current operation set. Adding the file as-is creates a second head; any database that applies both branches reaches duplicate `add_column` operations for the six shared columns. Linearizing the graph requires changing at least one `down_revision` and/or changing/removing the duplicate operations. A merge revision does not deduplicate parent operations: Alembic still has to traverse and apply both branches. The current ORM would also remain incompatible with the governance extras.

10. **[Confirmed from pinned remote source and current repository evidence]** The recovered file is historical repository evidence: it is a committed migration on the remote repository's `main` history, and its `0001`–`0003` ancestry matches the local files. It is not evidence that Neon, or any other database, applied it. No deployment log, database history, schema inventory, CI artifact, or restore record was inspected.

### 1.2 What this batch establishes and does not establish

**Establishes:**

- The exact recovered source, its revision metadata, its complete upgrade/downgrade operation list, and its checksums.
- The historical migration tree at the pinned commit and its relationship to the current local chain.
- The exact duplicate-operation set with `0005_verification_lineage.py`.
- The current-ORM compatibility gap and the separate historical-ORM context.
- Why no unmodified incorporation is available and what any future strategy must resolve.
- That Neon remains unverified.

**Does not establish:**

- That Neon contains `0004_enterprise_governance` in `alembic_version`.
- That the recovered migration was ever applied to Neon, staging, production, or any other database.
- That the recovered migration is complete or correct for its own historical application; the missing historical review table is a counterexample to completeness.
- That the current or historical schema matches either migration chain.
- That any migration strategy is safe or selected.
- That Batch 16 test results apply to the current tree or to the recovered lineage.
- That the untracked local migrations are protected by Git history.

### 1.3 Investigation answers

| Investigation question | Answer | Evidence |
| --- | --- | --- |
| 1. Verify revision, parent, provenance, and complete operations | Exact file retrieved from pinned SHA; revision and parent match the task statement; all 33 `add_column` calls, one table, five foreign keys, thirteen indexes, and the full downgrade were read. | Sections 3–4 |
| 2. Compare with current 0004 and 0005 | Recovered is a sibling of `0004_verification_templates`; it duplicates six columns with `0005_verification_lineage`; it does not create `verification_templates`. | Section 5 |
| 3. Identify every duplicate operation | Six duplicate `add_column` operations and six matching duplicate `drop_column` operations; no duplicate table, index, or foreign-key name. | Section 6 |
| 4. Focus on the six lineage columns | All six are exact duplicates in name, type, nullability, default absence, and downgrade behavior. | Section 6.1 |
| 5. Compare with current ORM | Current ORM lacks role, sign-off, materiality, audit table, and review table; it has templates and the six lineage columns. `reason_code`/`confidence_score` collide with computed properties. | Section 7 |
| 6. Can the current chain incorporate it without ancestry changes or duplicates? | No, not unmodified. Branch-only presence creates two heads and duplicate DDL on any database applying both; linearization changes ancestry and/or operations. | Sections 5.5 and 8 |
| 7. Historical repository evidence versus Neon application | It is committed historical repository evidence; it does not prove Neon applied it. | Sections 3.3 and 9 |
| 8. Safe options, prerequisites, risks, unresolved questions | Four candidate path families and one rejected path are documented; none is selected. | Section 8 |

### 1.4 Verdict preview

**PASS — audit scope only.** The required investigation and report are complete. This is not a PASS for reconciliation, migration readiness, ORM compatibility, or Neon verification. See section 12.

---

## 2. Working-tree baseline and preservation

### 2.1 Repository identity

**[Confirmed from current repository evidence]**

| Item | Value |
| --- | --- |
| Branch | `feature/batch-4-rule-engine-aggregation` |
| HEAD | `c91e9b37074483eeb7469dc943e1735fd5f5be02` |
| HEAD subject | `feat: implement Batch 4 advanced rule engine, aggregation and split-payment reconciliation` |
| Status entries at Batch 20 start | 65 (`git status --porcelain=v1 --untracked-files=all`) |
| Modified status entries | 28 |
| Files with textual diffs | 27 |
| Untracked status entries | 37 |
| Local `main` / `origin/main` | `ccd7e604ac1d262fca9d108e0e62875bec47d1c6` |
| Current local migration files | `0001`–`0005` in the working tree |
| Tracked migration files | `0001`–`0003` only |
| Batch 18 report | Present, untracked |
| Batch 19 report | Present, untracked |
| Batch 20 report before this batch | Absent |

### 2.2 Continuity with Batch 19

**[Confirmed from current repository evidence]**

- The Batch 19 final status list contained 65 entries.
- The Batch 20 starting status list contained 65 entries.
- `Compare-Object` reported them as identical: no file was added, removed, renamed, or content-changed between the end of Batch 19 and the start of Batch 20.
- The 28 modified status entries still include the previously documented stat-only false positive on `backend/tests/test_multisource_wizard.py`; its content matches HEAD and its textual diff is empty. It is not a Batch 20 change.
- The two newest local migrations, `0004_verification_templates.py` and `0005_verification_lineage.py`, remain untracked.
- `backend/migrations/env.py` remains modified.
- `backend/migrations/script.py.mako` remains 0 bytes.
- No reset, clean, stash, checkout, branch switch, fetch, commit, or other state-changing Git operation was performed.

### 2.3 Critical pre-report hashes

**[Confirmed from current repository evidence]**

| File | SHA-256 before this report |
| --- | --- |
| `backend/migrations/versions/0001_initial_tables.py` | `F3E045B29E52A132947E6ED156BA57995FD45B75EAA2C7D6289901C5AFD569A0` |
| `backend/migrations/versions/0002_verification_runs.py` | `44A9CD93E9A1260C7C61E3029FD6F884B5B27523FDCE25D966C986748AD78B2E` |
| `backend/migrations/versions/0003_user_password.py` | `6F256919E0E2537468335FF0A6C253E80BC513E3DFB6D414F9564C10083902E6` |
| `backend/migrations/versions/0004_verification_templates.py` | `CBE7E536573D06D49E4EB2F8EFB7BD26A0D3CCA786F01EA80AE7C8E7CA74E227` |
| `backend/migrations/versions/0005_verification_lineage.py` | `645BE701DFF05FDF6D263AF678CB17E77D818CE64C00A8B9F3AF96E46E585713` |
| `backend/migrations/env.py` | `F1A56CC8A201936615DE14F7730E32265C3132AF1372EF382F485207E67F056B` |
| `backend/migrations/script.py.mako` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |
| `docs/audits/Batch18_Migration_History_Divergence_Audit.md` | `1434845A691EB60C9FD34B8C7EACBA5079A7CE667E8DDCB80D4B2578AE037655` |
| `docs/audits/Batch19_Migration_Reconciliation_Preparation.md` | `DDA7AB82B5D799D9BC1EF1A12D23E392F507DCE801275BF4A89B8D637DCE856F` |

### 2.4 Preservation statement

**[Confirmed from current repository evidence]**

- No application code, ORM model, migration, configuration, dependency, or existing report was edited.
- No `.env` file was read.
- No database connection was attempted.
- No Alembic command was executed.
- No test suite was executed.
- No schema, data, or migration history was changed.
- The recovered migration was downloaded only to the approved temporary area outside the working tree; it was not copied into the repository.
- The only new working-tree file is this report.

Final verification is recorded in section 10.

---

## 3. Source provenance

### 3.1 Local availability check

**[Confirmed from current repository evidence]**

The specified commit is not present in the local clone:

| Check | Result |
| --- | --- |
| `git cat-file -e 58a0e5c…^{commit}` | Failed; exit code 128; object not found |
| `git branch -a --contains 58a0e5c…` | Failed; no such commit |
| Local file `backend/migrations/versions/0004_enterprise_governance_and_materiality.py` | Absent |
| Any local file with `enterprise_governance` in its name | None found |
| Local refs containing the recovered migration | None; every inspected local/remote-tracking ref tracked only `0001`–`0003` under `backend/migrations/versions` |
| Local `main` and `origin/main` | `ccd7e604ac1d262fca9d108e0e62875bec47d1c6` |
| Current audit branch | `feature/batch-4-rule-engine-aggregation` at `c91e9b3` |

The local absence is not evidence that the commit never existed. It means this clone's refs do not contain it. The remote repository was inspected through its public API and raw content endpoint.

### 3.2 Exact retrieval and commit metadata

**[Confirmed from pinned remote source]**

The file was retrieved from the exact commit-pinned URL:

`https://raw.githubusercontent.com/ThunderSkull7/verifygrid/58a0e5c243978480c4ca817c537c700ed6b20516/backend/migrations/versions/0004_enterprise_governance_and_materiality.py`

It was saved only to the approved temporary directory, not to the working tree.

| Property | Value |
| --- | --- |
| Repository | `ThunderSkull7/verifygrid` (public) |
| Commit SHA | `58a0e5c243978480c4ca817c537c700ed6b20516` |
| Parent SHA | `777a41aeee08c70334da358d2c03534338800185` |
| Commit author / committer display name | `ThunderSkull7` |
| Authored / committed time | `2026-10-26T10:49:20Z` |
| Commit message | `chore(migrations): add alembic migration for enterprise governance, materiality, and audit tables` |
| GitHub commit verification | `verified: false`; reason `unsigned` |
| File path | `backend/migrations/versions/0004_enterprise_governance_and_materiality.py` |
| File status in commit | Added |
| Additions / deletions / changes | 156 / 0 / 156 |
| File size | 10,032 bytes |
| File line count | 156 |
| Git blob SHA from GitHub API | `5f66fa2ca8faab62fdfe27e3369a3416f2d03276` |
| Git blob SHA computed from downloaded content | `5f66fa2ca8faab62fdfe27e3369a3416f2d03276` |
| Local SHA-256 of downloaded content | `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` |
| Declared revision | `0004_enterprise_governance` |
| Declared `down_revision` | `0003_user_password` |
| Declared `branch_labels` | `None` |
| Declared `depends_on` | `None` |

At retrieval time, the GitHub repository's default branch was `main`, and `main` pointed at the recovered commit. A compare request from local `main` (`ccd7e60`) to the recovered commit reported the remote branch `12` commits ahead and `0` behind, including governance-related commits. This is remote repository history, not local ref state. The local clone has not fetched it, and no fetch was performed in this batch.

### 3.3 Historical migration tree and shared ancestry

**[Confirmed from pinned remote source]**

At the recovered commit, the migration directory contained:

- `0001_initial_tables.py` (3,345 bytes; blob `b596655605d327bb346d4bdbc76d3b175d5bd5c3`)
- `0002_verification_runs.py` (4,968 bytes; blob `0f38544f2baaada0a97c63e4eb55ba0b4121b6c9`)
- `0003_user_password.py` (712 bytes; blob `5e92119597f879e55f81a7d8198a78ebd1444459`)
- `0004_enterprise_governance_and_materiality.py` (10,032 bytes; blob `5f66fa2ca8faab62fdfe27e3369a3416f2d03276`)

The parent commit's migration directory contained only `0001`–`0003`.

**[Confirmed from current repository evidence and pinned remote source]** The local `0001`, `0002`, and `0003` files have the same Git blob SHA-1 values as the remote files at the recovered commit:

| File | Local `git hash-object` | Remote blob at recovered commit | Match |
| --- | --- | --- | --- |
| `0001_initial_tables.py` | `b596655605d327bb346d4bdbc76d3b175d5bd5c3` | `b596655605d327bb346d4bdbc76d3b175d5bd5c3` | Yes |
| `0002_verification_runs.py` | `0f38544f2baaada0a97c63e4eb55ba0b4121b6c9` | `0f38544f2baaada0a97c63e4eb55ba0b4121b6c9` | Yes |
| `0003_user_password.py` | `5e92119597f879e55f81a7d8198a78ebd1444459` | `5e92119597f879e55f81a7d8198a78ebd1444459` | Yes |

The divergence therefore begins after a content-identical `0003_user_password`.

### 3.4 Provenance assessment

**[Confirmed from pinned remote source]**

- The recovered file is a real committed file in the repository history identified by the specified SHA.
- Its content matches the GitHub blob identity; it is not a similarly named substitute.
- It is part of a historical `main` line that also contains governance application models and tests at the same commit.
- The commit is unsigned, so the evidence establishes repository content and commit metadata, not a separately verified human identity or review approval.

**[Not independently verified]**

- Whether the commit was reviewed, merged under a particular policy, deployed, or applied to any database.
- Whether the historical `main` line was ever the application version used by any environment.
- Whether Neon or any other target contains the revision.
- Whether the recovered migration was later superseded, reverted, or replaced outside the inspected commit.

**Key distinction:** The recovered file is evidence of a historical repository migration. A migration file in Git is an instruction, not proof of execution. Nothing in the inspected evidence proves that Neon applied it; nothing proves that Neon did not.

---

## 4. Recovered migration summary

### 4.1 Revision metadata

**[Confirmed from pinned remote source]**

| Field | Value |
| --- | --- |
| File | `0004_enterprise_governance_and_materiality.py` |
| Revision | `0004_enterprise_governance` |
| Parent | `0003_user_password` |
| Branch labels | None |
| `depends_on` | None |
| Upgrade function | Lines 21–119 |
| Downgrade function | Lines 122–156 |
| Imports | `typing.Sequence`, `typing.Union`, `alembic.op`, `sqlalchemy as sa` |

### 4.2 Operation tally

**[Confirmed from pinned remote source]**

| Area | Upgrade operations | Downgrade operations |
| --- | --- | --- |
| `users` | 1 `add_column` (`role`) | 1 `drop_column` |
| `verification_runs` | 10 `add_column` (`sources` + 9 sign-off fields), 2 `create_foreign_key`, 1 `create_index` | 10 `drop_column` |
| `verification_discrepancies` | 22 `add_column`, 6 `create_index` | 22 `drop_column` |
| `audit_events` | 1 `create_table` with 14 columns and 3 inline foreign keys, 6 `create_index` | 1 `drop_table` |
| `verification_templates` | None | None |
| **Total** | **33 added columns; 1 new table; 5 foreign keys; 13 indexes** | **33 dropped columns; 1 dropped table** |

There are no `op.alter_column`, `op.execute`, `INSERT`, `UPDATE`, backfill, trigger, or data-transformation operations in the recovered migration. The only data-destructive behavior is the downgrade, which drops the table and columns.

### 4.3 Upgrade operations in detail

#### 4.3.1 `users`

| Column | Type | Nullable | Server default | Notes |
| --- | --- | --- | --- | --- |
| `role` | `String(50)` | No | `'MAKER'` | Added to the existing `users` table. Absent from current ORM. |

#### 4.3.2 `verification_runs`

| Column | Type | Nullable | Server default | Notes |
| --- | --- | --- | --- | --- |
| `sources` | `JSON` | Yes | None | **Duplicate of `0005_verification_lineage`.** Present in current ORM. |
| `sign_off_status` | `String(50)` | No | `'DRAFT'` | Indexed by `ix_verification_runs_sign_off_status`. Absent from current ORM. |
| `sign_off_proposed_by` | `Uuid` | Yes | None | FK `fk_runs_sign_off_proposed_by_users` → `users.id`, `ON DELETE SET NULL`. |
| `sign_off_proposed_by_name` | `String(255)` | Yes | None | Absent from current ORM. |
| `sign_off_proposal_note` | `Text` | Yes | None | Absent from current ORM. |
| `sign_off_proposed_at` | `DateTime(timezone=True)` | Yes | None | Absent from current ORM. |
| `sign_off_approved_by` | `Uuid` | Yes | None | FK `fk_runs_sign_off_approved_by_users` → `users.id`, `ON DELETE SET NULL`. |
| `sign_off_approved_by_name` | `String(255)` | Yes | None | Absent from current ORM. |
| `sign_off_decision_note` | `Text` | Yes | None | Absent from current ORM. |
| `sign_off_decided_at` | `DateTime(timezone=True)` | Yes | None | Absent from current ORM. |

The two sign-off foreign keys are created after the columns. The index is non-unique.

#### 4.3.3 `verification_discrepancies`

| Column | Type | Nullable | Server default | Duplicate? |
| --- | --- | --- | --- | --- |
| `source_row_indices` | `JSON` | Yes | None | **Yes — `0005`** |
| `source_records` | `JSON` | Yes | None | **Yes — `0005`** |
| `child_records` | `JSON` | Yes | None | **Yes — `0005`** |
| `aggregated_amount` | `Float` | Yes | None | **Yes — `0005`** |
| `expected_amount` | `Float` | Yes | None | **Yes — `0005`** |
| `source_amount` | `Float` | Yes | None | No |
| `target_amount` | `Float` | Yes | None | No |
| `variance_amount` | `Float` | Yes | None | No |
| `exposure_amount` | `Float` | Yes | None | No; indexed |
| `currency` | `String(10)` | Yes | `'USD'` | No |
| `severity` | `String(20)` | Yes | `'medium'` | No; indexed |
| `resolution_status` | `String(30)` | Yes | `'unresolved'` | No; indexed |
| `resolution_note` | `Text` | Yes | None | No |
| `resolved_by` | `String(100)` | Yes | None | No |
| `resolved_at` | `DateTime(timezone=True)` | Yes | None | No |
| `cluster_id` | `String(64)` | Yes | None | No; indexed |
| `cluster_name` | `String(255)` | Yes | None | No |
| `assigned_to` | `String(100)` | Yes | None | No; indexed |
| `assigned_at` | `DateTime(timezone=True)` | Yes | None | No |
| `side_by_side` | `JSON` | Yes | None | No |
| `reason_code` | `String(100)` | Yes | None | No; indexed; conflicts with current ORM property |
| `confidence_score` | `Float` | Yes | None | No; conflicts with current ORM property |

Indexes created on `verification_discrepancies`:

- `ix_verification_discrepancies_exposure_amount`
- `ix_verification_discrepancies_severity`
- `ix_verification_discrepancies_resolution_status`
- `ix_verification_discrepancies_cluster_id`
- `ix_verification_discrepancies_assigned_to`
- `ix_verification_discrepancies_reason_code`

All six are non-unique.

#### 4.3.4 `audit_events`

The recovered migration creates this table:

| Column | Type | Nullable | Default / constraint |
| --- | --- | --- | --- |
| `id` | `Uuid` | No | Primary key |
| `event_id` | `String(64)` | No | Indexed; not unique |
| `sequence_number` | `Integer` | No | Server default `'1'`; indexed; not unique |
| `run_id` | `Uuid` | Yes | FK → `verification_runs.id`, `ON DELETE CASCADE`; indexed |
| `project_id` | `Uuid` | No | FK → `projects.id`, `ON DELETE CASCADE`; indexed |
| `user_id` | `Uuid` | Yes | FK → `users.id`, `ON DELETE SET NULL`; no index |
| `user_email` | `String(255)` | Yes | None |
| `user_role` | `String(50)` | No | Server default `'MAKER'` |
| `event_type` | `String(100)` | No | Indexed |
| `timestamp_utc` | `DateTime(timezone=True)` | No | Server default `now()` |
| `timestamp_str` | `String(64)` | No | None |
| `event_payload` | `JSON` | No | None |
| `previous_event_hash` | `String(64)` | No | None |
| `current_event_hash` | `String(64)` | No | Indexed |

Indexes:

- `ix_audit_events_event_id`
- `ix_audit_events_sequence_number`
- `ix_audit_events_run_id`
- `ix_audit_events_project_id`
- `ix_audit_events_event_type`
- `ix_audit_events_current_event_hash`

All are non-unique. The table has no unique constraint on `event_id`, `sequence_number`, or any hash column, and no database trigger enforcing append-only behavior or hash chaining. Those properties, if intended, are application-level responsibilities rather than schema-enforced guarantees.

### 4.4 Downgrade behavior

**[Confirmed from pinned remote source]**

The downgrade performs, in order:

1. `drop_table("audit_events")` — removes the table and all rows, plus its indexes and inline FKs.
2. Drops the 22 `verification_discrepancies` columns in reverse order, including the five shared lineage columns and the physical `reason_code`/`confidence_score` columns.
3. Drops the 10 `verification_runs` columns in reverse order, including `sources` and all nine sign-off columns.
4. Drops `users.role`.

There are 33 `drop_column` calls and one `drop_table` call. The downgrade does not explicitly drop the two sign-off foreign keys or the three named indexes before dropping their columns; PostgreSQL normally removes objects that depend on a dropped column, but this was not executed or verified. The audit table downgrade destroys all audit events and their hash chain.

### 4.5 Static observations and risks

**[Confirmed from pinned remote source unless marked otherwise]**

- The migration alters three existing tables and creates one table. It does not create `verification_templates` or `discrepancy_review_decisions`.
- `role`, `sign_off_status`, `currency`, `severity`, and `resolution_status` have server defaults. The current ORM does not declare any of these columns.
- `users.role` and `user_role` both default to `'MAKER'`; the user role is denormalized into the audit table with no database-level consistency constraint.
- The audit table's `event_id`, `sequence_number`, and hash fields have no uniqueness or invariant constraints. The migration alone cannot guarantee tamper evidence.
- The recovered migration has no conditional DDL (`IF NOT EXISTS`) and no introspection. It assumes every object it adds is absent.
- The downgrade is destructive to governance data and to the six lineage columns; it must not be treated as a reversible data-preserving operation.
- **[Inference requiring further evidence]** The behavior of adding `NOT NULL` columns with server defaults to populated tables depends on the PostgreSQL version and locking behavior. It was not tested.

---

## 5. Current versus recovered migration chain

### 5.1 Current local chain

**[Confirmed from current repository evidence]**

| Revision | File | Parent | Principal objects |
| --- | --- | --- | --- |
| `0001_initial_tables` | `0001_initial_tables.py` | None | `users`, `projects`, `source_files` |
| `0002_verification_runs` | `0002_verification_runs.py` | `0001_initial_tables` | `verification_runs`, `verification_discrepancies` |
| `0003_user_password` | `0003_user_password.py` | `0002_verification_runs` | `users.hashed_password` |
| `0004_verification_templates` | `0004_verification_templates.py` | `0003_user_password` | `verification_templates` |
| `0005_verification_lineage` | `0005_verification_lineage.py` | `0004_verification_templates` | Six lineage columns |

Current head: `0005_verification_lineage`.

`0004_verification_templates` creates the `verification_templates` table with its owner foreign key, unique constraint, index, and defaults. `0005_verification_lineage` adds the six nullable lineage columns and nothing else.

### 5.2 Recovered historical chain

**[Confirmed from pinned remote source]**

| Revision | File | Parent | Principal objects |
| --- | --- | --- | --- |
| `0001_initial_tables` | `0001_initial_tables.py` | None | Same as local; content-identical blob |
| `0002_verification_runs` | `0002_verification_runs.py` | `0001_initial_tables` | Same as local; content-identical blob |
| `0003_user_password` | `0003_user_password.py` | `0002_verification_runs` | Same as local; content-identical blob |
| `0004_enterprise_governance` | `0004_enterprise_governance_and_materiality.py` | `0003_user_password` | Users role, run sign-off, discrepancy materiality, `audit_events` |

At the pinned commit, the only head was `0004_enterprise_governance`.

### 5.3 Graph relationship

```text
CURRENT LOCAL:
0001_initial_tables
  -> 0002_verification_runs
    -> 0003_user_password
      -> 0004_verification_templates
        -> 0005_verification_lineage   (sole current head)

RECOVERED AT PINNED COMMIT:
0001_initial_tables
  -> 0002_verification_runs
    -> 0003_user_password
      -> 0004_enterprise_governance     (head at that commit)

COMBINED WITHOUT EDITS:
0003_user_password
  -> 0004_verification_templates -> 0005_verification_lineage
  -> 0004_enterprise_governance        (second head)
```

The shared `0001`–`0003` ancestry is content-identical. The divergence starts at the two distinct `0004` revisions. The numeric prefix `0004` is a filename convention, not an Alembic ordering key. Alembic uses the full revision identifier, so `0004_enterprise_governance` and `0004_verification_templates` are distinct revisions, not a duplicate ID.

### 5.4 Direct comparison of the two `0004` revisions

| Aspect | Current `0004_verification_templates` | Recovered `0004_enterprise_governance` |
| --- | --- | --- |
| Declared parent | `0003_user_password` | `0003_user_password` |
| Creates new table | `verification_templates` | `audit_events` |
| Alters existing tables | None | `users`, `verification_runs`, `verification_discrepancies` |
| Adds template contract | Yes | No |
| Adds users role | No | Yes |
| Adds run sign-off contract | No | Yes (nine fields, two FKs, one index) |
| Adds discrepancy materiality contract | No | Yes (seventeen new fields, six indexes) |
| Adds lineage columns | No | Yes (five discrepancy fields plus run `sources`) |
| Overlapping objects with the other `0004` | None | None |
| Shared ancestry | `0003_user_password` | `0003_user_password` |
| Conflict with `0005` | None | Six duplicate columns and six duplicate downgrade drops |

The two `0004` files do not directly duplicate each other. Their conflict is structural: they are siblings, and the recovered revision duplicates six columns that the later current revision also adds.

### 5.5 Can the current chain incorporate the recovered revision without changing ancestry or duplicating operations?

**No, not unmodified.**

The precise situation is:

1. **Adding the file as-is** does not edit any existing `down_revision`, but it creates a second head. The current chain is no longer linear. `alembic upgrade head` is ambiguous; `get_current_head()` cannot return one head; the current parity test expects exactly `0005_verification_lineage`. A database that applies both branches will execute both `0004` upgrades and then hit duplicate `add_column` calls for the six shared columns. The order does not matter: one branch will add the six columns, and the other will try to add them again.

2. **Linearizing without editing the recovered file** requires changing a current `down_revision` or adding a merge. Changing a current parent modifies the current ancestry. A merge adds a new revision but does not remove the duplicate operations: Alembic must still apply both parent branches before the merge. A merge is not a deduplication mechanism.

3. **Reparenting the recovered file** to `0004_verification_templates` or `0005_verification_lineage` changes its declared ancestry. If it becomes a child of `0005`, the duplicate six columns already exist and its upgrade still fails. If it becomes a child of `0004_verification_templates` and `0005` remains its child, `0005` still duplicates the six columns.

4. **Removing or conditionally skipping the duplicates** changes the recovered file, the current `0005` file, or both. That is an operation change, not an unmodified incorporation. It also changes the downgrade semantics: the two revisions currently both claim ownership of the same six columns.

5. **Even a structurally successful unification** would leave the current ORM incompatible with the governance objects. The current ORM has no role, sign-off, materiality, or audit model, and the recovered migration does not create the current `verification_templates` table. A migration-only change cannot make the current application use the recovered schema.

Therefore, the recovered revision can be *present in the directory* as an unapplied sibling without editing existing files, but it cannot be *incorporated into the current chain as an applicable revision* while preserving both the current ancestry and the current operation set. A future strategy must explicitly choose how to resolve the sibling history, the six duplicate columns, the missing template table, and the ORM/application contract. This audit does not make that choice.

### 5.6 Consequence of each plausible ordering

| Ordering | Change required | Upgrade consequence | History / ORM consequence |
| --- | --- | --- | --- |
| Current chain only | None | Current `0004`/`0005` apply; no governance objects. | Current ORM contract remains as today; recovered features absent. |
| Recovered branch only, from `0003` | None to the recovered file | Governance objects apply; six lineage columns exist via the governance revision rather than `0005`. | `verification_templates` is missing; current ORM parity fails; `0005` is not applied; audit governance extras exist. |
| Both `0004` revisions as siblings | None; just add the file | Two heads; `upgrade head` is ambiguous; applying both branches duplicates six columns and fails. | Current single-head tests fail; no unified history. |
| Recovered after `0005` | Reparent recovered to `0005` | First duplicate column (`sources`) fails immediately. | Recovered ancestry changes; downgrade overlap remains. |
| Recovered before `0004_verification_templates` | Reparent current `0004` or recovered | If current `0005` remains, it duplicates all six columns and fails. | Current ancestry changes; templates and governance could coexist only after further operation changes. |
| Recovered between `0004_verification_templates` and `0005` | Reparent recovered to current `0004` | Current `0005` still duplicates the six columns and fails. | Current ancestry changes; `0005` must be edited or replaced. |
| Merge revision with two parents | Add a merge revision | Both parent branches are traversed; duplicate DDL still fails. | Merge does not deduplicate operations or reconcile the ORM. |
| Edit/conditionalize duplicate operations | Modify recovered and/or `0005` | Could avoid duplicate DDL, but only as a new reviewed migration design. | Not an unmodified incorporation; downgrade and history semantics must be redesigned. |
| Stamp or skip one revision | Edit `alembic_version` or stamp | Avoids executing one branch but asserts a state that may not match the schema. | Prohibited as history manipulation; hides missing objects. |

**[Inference requiring further evidence]** A database currently at `0004_enterprise_governance` has no ancestry path to `0005_verification_lineage`. Alembic will not automatically apply `0004_verification_templates` and `0005` as a normal upgrade. Even if a merge is added, traversing the current branch applies `0005`, which duplicates the six governance columns. The target's actual schema and history would determine whether any conditional or alternative path is even possible.

---

## 6. Duplicate-operation matrix

### 6.1 Duplicate columns

**[Confirmed from current repository evidence and pinned remote source]**

| Column | Definition in recovered migration | Definition in `0005_verification_lineage` | Match | Consequence if both branches execute |
| --- | --- | --- | --- | --- |
| `verification_runs.sources` | `sa.JSON()`, nullable, no default; lines 29, 155 | `sa.JSON()`, nullable, no default; lines 43–46, 83 | Exact | Second `add_column` fails; second `drop_column` fails on downgrade |
| `verification_discrepancies.source_row_indices` | `sa.JSON()`, nullable, no default; lines 62, 145 | `sa.JSON()`, nullable, no default; lines 50–53, 82 | Exact | Same |
| `verification_discrepancies.source_records` | `sa.JSON()`, nullable, no default; lines 63, 144 | `sa.JSON()`, nullable, no default; lines 54–57, 81 | Exact | Same |
| `verification_discrepancies.child_records` | `sa.JSON()`, nullable, no default; lines 64, 143 | `sa.JSON()`, nullable, no default; lines 61–64, 80 | Exact | Same |
| `verification_discrepancies.aggregated_amount` | `sa.Float()`, nullable, no default; lines 65, 142 | `sa.Float()`, nullable, no default; lines 65–68, 79 | Exact | Same |
| `verification_discrepancies.expected_amount` | `sa.Float()`, nullable, no default; lines 66, 141 | `sa.Float()`, nullable, no default; lines 69–72, 78 | Exact | Same |

No duplicate operation exists for any other column, index, foreign key, unique constraint, or table name between the recovered migration and the current `0004`/`0005` revisions.

### 6.2 Duplicate downgrade operations

The same six columns are dropped by both downgrades:

| Column | Recovered downgrade | Current `0005` downgrade |
| --- | --- | --- |
| `verification_discrepancies.expected_amount` | Line 141 | Line 78 |
| `verification_discrepancies.aggregated_amount` | Line 142 | Line 79 |
| `verification_discrepancies.child_records` | Line 143 | Line 80 |
| `verification_discrepancies.source_records` | Line 144 | Line 81 |
| `verification_discrepancies.source_row_indices` | Line 145 | Line 82 |
| `verification_runs.sources` | Line 155 | Line 83 |

If a database somehow had both revisions applied, downgrading both would attempt to drop the same six columns twice. The second downgrade would fail because the columns no longer exist. The first downgrade would already have destroyed the lineage data. The recovered migration additionally drops all governance and audit data.

### 6.3 Non-duplicate overlap

| Object | Recovered | Current chain | Duplicate? |
| --- | --- | --- | --- |
| `verification_runs` | Alters with governance columns | Alters with `sources` only | Table overlap; only `sources` duplicates |
| `verification_discrepancies` | Alters with 22 columns | Alters with five lineage columns | Table overlap; five columns duplicate |
| `users.role` | Adds | Not present | No |
| Nine run sign-off columns | Adds | Not present | No |
| Seventeen materiality/clustering/review columns | Adds | Not present | No |
| `audit_events` | Creates | Not present | No |
| `verification_templates` | Does not create | Creates | No migration duplicate; schema gap in recovered-only path |
| Run sign-off FKs/index | Creates | Not present | No |
| Six discrepancy indexes | Creates | Not present | No |
| Six audit indexes | Creates | Not present | No |
| `discrepancy_review_decisions` | Does not create | Not present | Historical ORM expects it; unresolved historical gap |

### 6.4 Execution consequences

**[Confirmed from source; runtime not executed]**

- **Multiple heads:** With both files present and unmodified, the revision graph has two heads. A command targeting `head` cannot choose one. The current parity test's `_expected_head()` calls `ScriptDirectory.get_current_head()` and expects a single value; multiple heads are a test-contract conflict before any database work.
- **Duplicate upgrade:** On a database that traverses both branches, the first branch adds the six columns. The second branch's first duplicate is `verification_runs.sources`, followed by the five discrepancy columns. PostgreSQL rejects the duplicate column; Alembic does not silently skip it because `op.add_column` has no `IF NOT EXISTS` or introspection check here.
- **Partial transaction / version state:** The exact transaction and version-table outcome depends on Alembic and PostgreSQL transaction behavior, which was not executed. Even a rolled-back attempt can prompt unsafe manual repair if operators assume some operations succeeded. No such repair is authorized.
- **No path from governance to current head:** A database at `0004_enterprise_governance` is not on the current chain. A normal `upgrade` to `0005_verification_lineage` has no direct ancestry path. A merge still traverses both branches and hits duplicate DDL.
- **Duplicate downgrade:** Downgrading both revisions is impossible without data loss and a failure on the second ownership claim of the six columns. The recovered downgrade also drops audit history.
- **Schema-only success is not application success:** A database could have both template and governance tables only if the graph and operations were deliberately restructured. The current ORM would still not map the governance extras, and a historical ORM would not have the current template table.

### 6.5 Duplicate conclusion

The only exact duplication is the six-column set. That is sufficient to make unmodified co-application impossible. The absence of duplicated table/index names does not make the revisions compatible, because the duplicate-column DDL fails before the rest of the schema can be evaluated.

---

## 7. ORM compatibility findings

### 7.1 Current model inventory

**[Confirmed from current repository evidence]**

`backend/app/models/__init__.py` registers:

- `User` (`users`)
- `Project` (`projects`)
- `SourceFile` (`source_files`)
- `VerificationRun` (`verification_runs`)
- `VerificationDiscrepancy` (`verification_discrepancies`)
- `VerificationTemplate` (`verification_templates`)

It does not register an audit model. `backend/app/models/audit_log.py` exists but is 0 bytes and is not imported. `backend/app/models/review.py` is also 0 bytes; there is no current `DiscrepancyReviewDecision` model.

### 7.2 Current ORM versus recovered operations

#### `User`

| Recovered column | Current ORM | Finding |
| --- | --- | --- |
| `role` | Absent from `backend/app/models/user.py` | Extra database column if recovered migration is applied; no current authorization role contract; no current code references `user.role`. |

#### `VerificationRun`

| Recovered object | Current ORM | Finding |
| --- | --- | --- |
| `sources` | Declared as `JSON`, nullable | Already covered by current `0005`; duplicate DDL. |
| `sign_off_status` | Absent | Extra column, NOT NULL default `DRAFT`, plus index. Current ORM does not select or expose it. |
| `sign_off_proposed_by`, `sign_off_approved_by` | Absent | Extra UUID FKs to `users.id`; no current relationships. |
| Seven remaining sign-off fields | Absent | Extra nullable columns; no current application contract. |
| `ix_verification_runs_sign_off_status` | Not declared | Extra index; parity test compares indexes exactly. |

#### `VerificationDiscrepancy`

| Recovered object | Current ORM | Finding |
| --- | --- | --- |
| `source_row_indices`, `source_records`, `child_records` | Declared as JSON, nullable | Already covered by current `0005`; duplicate DDL. |
| `aggregated_amount`, `expected_amount` | Declared as Float, nullable | Already covered by current `0005`; duplicate DDL. |
| `source_amount`, `target_amount`, `variance_amount`, `exposure_amount` | Absent | Extra Float columns; `exposure_amount` indexed. |
| `currency`, `severity`, `resolution_status` | Absent | Extra nullable columns with server defaults `USD`, `medium`, `unresolved`. |
| `resolution_note`, `resolved_by`, `resolved_at` | Absent | Extra columns; no current workflow. |
| `cluster_id`, `cluster_name`, `assigned_to`, `assigned_at` | Absent | Extra columns; `cluster_id` and `assigned_to` indexed. |
| `side_by_side` | Absent | Extra JSON column. |
| `reason_code` | Current **read-only property**, computed from `field_differences` and `match_status`; not a mapped column | Physical column would be ignored by current ORM. The current property has no setter, so current code cannot persist a value to it. |
| `confidence_score` | Current **read-only property**, computed from `field_differences`/`match_status`; not a mapped column | Same conflict; physical column would be ignored by current ORM. |
| Six discrepancy indexes | Not declared | Extra indexes; parity test compares indexes exactly. |

#### `AuditEvent` / `audit_events`

| Recovered object | Current ORM | Finding |
| --- | --- | --- |
| `audit_events` table | No model; `audit_log.py` is 0 bytes and unimported | Extra table; current ORM's expected table set does not include it. Any audit feature would be absent from current code. |
| 14 audit columns, 3 FKs, 6 indexes | Not declared | Complete schema/ORM drift. |

#### `VerificationTemplate`

| Current object | Recovered migration | Finding |
| --- | --- | --- |
| `verification_templates` table, owner FK, unique constraint, index, defaults | Does not create it | A database built only from the recovered branch lacks the current ORM's template table. Template queries would have no table. |

#### `DiscrepancyReviewDecision` / `discrepancy_review_decisions`

| Historical source context | Current ORM | Recovered migration |
| --- | --- | --- |
| Historical `verification_run.py` defines `DiscrepancyReviewDecision` mapped to `discrepancy_review_decisions` with FKs to discrepancies/runs and indexes. | No model. | Does not create the table. |

No migration file at the pinned commit creates this historical table. This is a separate historical-ORM/migration gap, not a current-ORM requirement.

### 7.3 Current ORM compatibility summary

- The current ORM is consistent with the current chain's six lineage columns and the template table.
- The recovered migration is **not compatible** with the current ORM as a complete schema:
  - it adds an unmapped `users.role`;
  - it adds unmapped sign-off columns, FKs, and an index;
  - it adds unmapped materiality/clustering/review columns and indexes;
  - it adds a whole unmapped `audit_events` table;
  - its physical `reason_code` and `confidence_score` columns collide semantically with current computed properties;
  - it does not create the current `verification_templates` table.
- SQLAlchemy can often ignore extra database columns when reading mapped entities, so some current application paths might still run against a schema with extras. That is not compatibility. The current parity test asserts exact table, column, foreign-key, unique-constraint, and index sets; the extras would fail those assertions. Missing tables or columns would fail application queries.
- **[Inference requiring further evidence]** If the deployed application is the historical governance-era code rather than the current local code, the current ORM comparison is not representative. The deployment commit, environment, and database must be identified before deciding which ORM contract matters.

### 7.4 Historical ORM context at the pinned commit

**[Confirmed from historical source context]**

At `58a0e5c…`, `backend/app/models` contained:

- `user.py` with `role: Mapped[str]` (`String(50)`, Python default `MAKER`, non-null);
- `verification_run.py` with the nine sign-off fields, the six lineage fields, the seventeen materiality fields, and mapped `_reason_code`/`_confidence_score` columns using the database names `reason_code`/`confidence_score`;
- `audit_log.py` with an `AuditEvent` model mapped to `audit_events`, matching the migration's table shape;
- `__init__.py` importing `AuditEvent`;
- `review.py` (0 bytes) and a `DiscrepancyReviewDecision` class inside `verification_run.py` mapped to `discrepancy_review_decisions`;
- no `verification_template.py` and no `VerificationTemplate` registration.

This explains the recovered migration's shape: it belongs to a different application lineage that implemented maker-checker governance, materiality, clustering, and audit hashing. Its presence is not accidental, but it is also not the current local contract.

The historical ORM/migration comparison also shows that the recovered migration is not a complete historical schema by itself: `DiscrepancyReviewDecision` expects `discrepancy_review_decisions`, and no migration at that commit creates it. Any claim that the recovered migration fully represents the historical schema would be unsupported.

### 7.5 Test-contract impact

**[Confirmed from current repository evidence; tests not run]**

`backend/tests/test_alembic_migration_parity.py` currently:

- Sets `EXPECTED_HEAD = "0005_verification_lineage"` and `PREVIOUS_HEAD = "0004_verification_templates"` (lines 66–67).
- Calls `ScriptDirectory.get_current_head()` for `_expected_head()` (lines 175–178).
- Asserts the actual table set equals the ORM table set plus `alembic_version` (lines 223–227).
- Asserts exact column sets, nullability, primary keys, foreign keys, unique constraints, and indexes per table (lines 229–297).
- Uses `compare_metadata` for additional drift (lines 299–312).

Adding the recovered file as an unmodified sibling would introduce a second head, so `_expected_head()` would no longer return the single expected head. Applying the governance schema would additionally introduce an extra table, extra columns, extra FKs, and extra indexes relative to the current ORM. The parity suite would therefore not pass as currently written. No test was executed; this is a static contract analysis.

The parity test explicitly does not compare server defaults (lines 299–301), so the recovered `role`, `sign_off_status`, `currency`, `severity`, and `resolution_status` defaults would not be the first failure; the extra objects would be. If the ORM were later updated to include governance fields, a new default audit would still be required.

### 7.6 ORM conclusion

The recovered migration and the current ORM describe different applications. The current chain is the better match for the current ORM, but it does not implement the governance features. The recovered lineage is the better match for the historical governance-era ORM, but it omits at least one historical table and is not the current application. Neither fact authorizes a schema change.

---

## 8. Potential reconciliation paths and risks

**No path is selected, ranked, or authorized by this report.** The following are candidate families for a future decision after the Batch 19 read-only inventory and an explicit application-version decision. None can be evaluated safely without the target database's actual history and schema.

### 8.1 Candidate path matrix

| Path | What it would preserve | Prerequisites | Principal risks | Status |
| --- | --- | --- | --- | --- |
| **A. Archive the recovered file as evidence; keep the current chain unchanged** | Current chain, current ORM, current local migrations | Owner confirms no target is at `0004_enterprise_governance`; inventory confirms no governance objects/data are required; separate decision that governance features are out of scope | If a target is at governance, current app lacks templates and the six columns may have different ownership; divergence remains; future migration still blocked | Safe as a *documentation* position only; not a reconciliation |
| **B. New reviewed additive migration on the current head for selected governance objects** | Current chain and ancestry; current template table; adds only chosen governance features | Full target inventory; owner decides which governance features are wanted; ORM/API/schema work; verified no overlapping objects; backup/restore; isolated rehearsal; new tests | Does not repair a target whose history is already governance; could duplicate objects if target has some; creates a superset schema; `reason_code`/`confidence_score` property conflict; downgrade design; current parity tests require ORM changes | Candidate only; not selected |
| **C. History-aware unification with a target already at governance** | Historical governance data and revision lineage; adds only missing current objects (notably templates) without re-adding the six columns | Complete inventory; schema/data comparison; confirmation that governance revision was actually applied; owner decision on canonical lineage; new reviewed migration/merge that does not replay duplicate DDL; backup/rehearsal; application-version decision | False merge ancestry; duplicate DDL if current `0005` is traversed unchanged; inability to downgrade cleanly; loss of audit hash-chain meaning; hidden historical gaps such as `discrepancy_review_decisions`; current ORM vs historical ORM mismatch | Candidate only; not selected |
| **D. Controlled rebuild on the current chain with data migration** | A reproducible current graph and current ORM contract | Verified backup/restore; isolated rehearsal; complete data mapping; explicit handling of governance/audit data; downtime plan; owner authorization; post-migration verification | Data loss; downtime; loss of governance/audit history; broken external references; new schema may not satisfy historical app consumers | Candidate only; not selected |
| **E. Branch-specific coexistence** | Historical governance branch for historical environments; current chain for current environments | Explicit environment-to-branch mapping; separate application versions; no cross-environment use; migration discipline for both branches | Two divergent truths; future merges harder; production/test mismatch; unclear which code owns which database; no single head | Candidate only; not selected |
| **F. Stamp or edit `alembic_version`** | Nothing verifiable | Not acceptable | Asserts unapplied or unknown state; hides missing objects; breaks reproducibility; can mask duplicate or missing DDL; violates migration-history integrity | **Rejected / prohibited; not a safe option** |

### 8.2 Preconditions common to every non-rejected path

1. **Target identity and environment:** Written owner confirmation of the Neon project, branch, database, role, and environment classification, without credentials.
2. **Complete migration history:** Every `alembic_version` row, exact revision strings, duplicate rows, unknown revisions, and whether `0004_enterprise_governance` is present.
3. **Complete schema inventory:** Tables, columns, types, nullability, defaults, constraints, indexes, FKs, triggers, extensions, ownership, and extra objects. Specifically: the six lineage columns, governance fields, `audit_events`, `verification_templates`, and `discrepancy_review_decisions`.
4. **Data inventory:** Non-null counts and ownership of lineage, governance, and audit data; do not export row contents without a separate privacy review.
5. **Application-version decision:** Which code lineage is the intended application: the current local ORM, the historical governance-era ORM, or another commit. The current ORM comparison is not representative of a historical deployment.
6. **Backup and restore evidence:** A verified recovery point and a successful restore test to a separate branch or isolated environment. A provider feature claim without a restore test is insufficient.
7. **Rehearsal:** A disposable isolated target where the chosen migration can run without touching the live target, followed by schema, data, application, and rollback verification.
8. **Authorization:** Migration author, database owner, technical/release owner, and security/data owners as applicable.

### 8.3 Path-specific risks and prohibitions

**Path A — archive only**

- Permitted read-only actions: retain the recovered source hash and provenance; inspect the target read-only; document that governance features are out of scope.
- Prohibited: claiming the target is safe because the file was not applied; applying `0005` to a governance target; deleting the historical revision from a target.
- Risk: a real target may already be on the governance branch, making “keep current chain unchanged” insufficient for that environment.

**Path B — additive migration on current head**

- Permitted read-only actions: compare target schema/ORM; design a migration offline; review operations statically.
- Prohibited: adding the recovered file unmodified; assuming “additive” means safe; ignoring the six-column duplicate ownership; changing production defaults without evidence.
- Risks: superset drift, ORM/property conflicts, duplicate objects if the target contains governance fields, and a false sense that the historical revision has been reconciled.

**Path C — history-aware unification**

- Permitted read-only actions: exact history/schema comparison; provenance review; static graph design; owner interviews.
- Prohibited: creating a merge that silently assumes common ancestry; replaying `0005` on a schema that already has the six columns; editing an already-applied historical revision; deleting `alembic_version` rows; inventing missing operations.
- Risks: a merge is not a deduplication tool; both histories must be fully understood; the six-column ownership must be resolved; the missing historical `discrepancy_review_decisions` table may indicate further gaps; audit hash-chain integrity may depend on not rewriting history.

**Path D — controlled rebuild**

- Permitted read-only actions: inventory, backup verification, rehearsal planning, data-mapping review.
- Prohibited: rebuilding before a verified restore; copying production data to an unapproved environment; dropping governance/audit data without explicit owner approval.
- Risks: data loss, downtime, loss of audit evidence, external references, and a new schema that is reproducible but not the historical application's schema.

**Path E — branch coexistence**

- Permitted read-only actions: document environment mapping; keep branch histories separate; verify each environment independently.
- Prohibited: pointing one application version at the other branch's database; assuming a future merge is trivial; syncing version tables manually.
- Risks: long-term divergence, two migration truths, and a harder reconciliation later.

**Path F — stamping/history editing**

- Prohibited in all cases until a future authorized change explicitly justifies it and every object is proven present. Stamping a revision does not create its schema and can hide missing DDL.
- This report does not authorize stamping, deleting rows, or manual `alembic_version` edits.

### 8.4 Unresolved questions

1. Which Neon project, branch, database, role, and environment are the intended target?
2. What are the exact contents of `alembic_version`? Does any row contain `0004_enterprise_governance`? Are there multiple heads or unknown revisions?
3. Does the target schema contain any governance fields, `audit_events`, `verification_templates`, or `discrepancy_review_decisions`? What are their exact types, defaults, constraints, and indexes?
4. Do the six lineage columns exist? Are they populated? If both the governance and lineage revisions could claim them, which one actually created them?
5. Was `0004_enterprise_governance` ever applied to the target, or was it only committed? What deployment/log/CI evidence exists?
6. Which application commit is deployed against each environment: current local ORM, historical governance-era ORM, or another?
7. Are governance features still required? Is there real sign-off, materiality, clustering, or audit data that must be preserved?
8. Is the audit hash chain intact, and would any migration or rebuild invalidate its sequence or hashes?
9. Is `discrepancy_review_decisions` present in the target, and how was it created if the recovered migration does not create it?
10. Is there a verified backup/restore point and an isolated rehearsal capability?
11. Who owns the decision to unify, branch, or rebuild, and what change authorization is required?
12. Should the untracked local `0004`/`0005` and modified `env.py` be committed separately to protect the current chain? That is a Git-preservation decision, not part of this audit.

**No strategy can be selected until questions 1–5 and 11 are answered; questions 6–10 determine whether any candidate path is viable.**

---

## 9. Neon and remote-database status

**Neon remains unverified.**

**[Confirmed from current repository evidence and the safety constraints of this batch]**

- No connection to Neon, production, staging, or any other remote database was attempted.
- No `.env` file was read.
- No database URL, credential, token, or secret was printed or recorded.
- No Alembic upgrade, downgrade, stamp, revision, history, or database-inspection command was executed.
- No schema, data, or migration-history change was made.
- No test suite was executed.

**[Not independently verified]**

- Neon project/branch/database identity and environment classification.
- Full `alembic_version` contents, including whether `0004_enterprise_governance` exists.
- Current schema, the six lineage columns, governance objects, extra objects, and data.
- Backup, restore, point-in-time recovery, and isolated rehearsal capability.
- Whether any environment ever ran the recovered migration.

The GitHub commit proves that the migration file was committed to the repository. It does not prove that Neon applied it. Conversely, this audit found no evidence that Neon did not apply it. The correct status is **unknown**, not “applied” and not “absent.”

The read-only inventory and authorization gates in Batch 19 remain prerequisites. In particular, the inventory must capture every `alembic_version` row and the exact schema before any strategy is selected.

---

## 10. Safety, preservation, and final verification

### 10.1 Actions not taken

**[Confirmed from current repository evidence]**

- No application code, ORM model, migration, configuration, dependency, or existing report was edited.
- No migration was copied into the working tree.
- No database connection was attempted.
- No `.env` file was read.
- No Alembic command was executed.
- No test suite was run.
- No schema, data, or migration history was changed.
- No commit, push, merge, rebase, branch switch, fetch, stash, reset, clean, or deploy was performed.
- The recovered file and historical ORM files were written only to the approved temporary area outside the repository.

### 10.2 Final working-tree verification

**[Confirmed from current repository evidence]**

- Baseline before this report: 65 status entries.
- Final status after adding this report: 66 entries.
- `Compare-Object` between the Batch 20 baseline and final status lists shows exactly one new path:
  `docs/audits/Batch20_Governance_Migration_Recovery_Audit.md`.
- No pre-existing file was modified, deleted, renamed, staged, or committed.
- The 27 textual tracked-file diffs and all 37 pre-existing untracked entries remain.
- The recovered migration does not exist in the working tree.

### 10.3 Critical post-report hashes

**[Confirmed from current repository evidence]**

| File | SHA-256 after this report | Unchanged from baseline? |
| --- | --- | --- |
| `backend/migrations/versions/0001_initial_tables.py` | `F3E045B29E52A132947E6ED156BA57995FD45B75EAA2C7D6289901C5AFD569A0` | Yes |
| `backend/migrations/versions/0002_verification_runs.py` | `44A9CD93E9A1260C7C61E3029FD6F884B5B27523FDCE25D966C986748AD78B2E` | Yes |
| `backend/migrations/versions/0003_user_password.py` | `6F256919E0E2537468335FF0A6C253E80BC513E3DFB6D414F9564C10083902E6` | Yes |
| `backend/migrations/versions/0004_verification_templates.py` | `CBE7E536573D06D49E4EB2F8EFB7BD26A0D3CCA786F01EA80AE7C8E7CA74E227` | Yes |
| `backend/migrations/versions/0005_verification_lineage.py` | `645BE701DFF05FDF6D263AF678CB17E77D818CE64C00A8B9F3AF96E46E585713` | Yes |
| `backend/migrations/env.py` | `F1A56CC8A201936615DE14F7730E32265C3132AF1372EF382F485207E67F056B` | Yes |
| `backend/migrations/script.py.mako` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | Yes |
| `docs/audits/Batch18_Migration_History_Divergence_Audit.md` | `1434845A691EB60C9FD34B8C7EACBA5079A7CE667E8DDCB80D4B2578AE037655` | Yes |
| `docs/audits/Batch19_Migration_Reconciliation_Preparation.md` | `DDA7AB82B5D799D9BC1EF1A12D23E392F507DCE801275BF4A89B8D637DCE856F` | Yes |

### 10.4 Report status

This report is untracked. It is not staged or committed. It is the only new working-tree change from Batch 20.

---

## 11. Files inspected and commands executed

### 11.1 Files inspected

**Current local migrations and configuration:**

- `backend/migrations/versions/0001_initial_tables.py`
- `backend/migrations/versions/0002_verification_runs.py`
- `backend/migrations/versions/0003_user_password.py`
- `backend/migrations/versions/0004_verification_templates.py`
- `backend/migrations/versions/0005_verification_lineage.py`
- `backend/migrations/env.py` (presence/status only; no URL values recorded)
- `backend/migrations/script.py.mako` (size/hash only)

**Current ORM:**

- `backend/app/models/__init__.py`
- `backend/app/models/user.py`
- `backend/app/models/project.py`
- `backend/app/models/source_file.py`
- `backend/app/models/verification_run.py`
- `backend/app/models/verification_template.py`
- Presence/size of `backend/app/models/audit_log.py` and `backend/app/models/review.py` (both 0 bytes)

**Current tests and prior reports (read-only reference):**

- `backend/tests/test_alembic_migration_parity.py` (head, table-set, column, index, and metadata assertions)
- `docs/audits/Batch18_Migration_History_Divergence_Audit.md` (existence and prior findings; not re-audited in full)
- `docs/audits/Batch19_Migration_Reconciliation_Preparation.md` (existence and prior baseline)
- `docs/NEON_MIGRATION_RECONCILIATION_PLAN.md` (prior reconciliation gates, searched/consulted)
- Repository documentation and source searches for the governance terms listed below

**Pinned remote source:**

- `backend/migrations/versions/0004_enterprise_governance_and_materiality.py` at `58a0e5c…`
- Historical `backend/app/models/user.py`
- Historical `backend/app/models/verification_run.py`
- Historical `backend/app/models/audit_log.py`
- Historical `backend/app/models/__init__.py`
- Historical `backend/app/models/project.py` and `source_file.py` (for context)
- Migration-directory listings at the recovered commit and its parent
- Repository commit metadata, tree, branch, and compare API responses for the pinned SHA

The historical files were read only to distinguish the recovered lineage from the current ORM. They were not copied into the working tree and are not proposed as current code.

### 11.2 Commands and read-only checks

All commands were read-only. No command opened a database connection, invoked Alembic against a database, read `.env`, or changed repository state.

| Command / check | Purpose | Outcome |
| --- | --- | --- |
| `git status --porcelain=v1 --untracked-files=all` (before and after) | Baseline and final preservation | 65 before; 66 after; only this report added |
| `git branch --show-current`, `git rev-parse HEAD`, `git log -1 --oneline` | Record branch and HEAD | Recorded in section 2 |
| `git status --porcelain=v1 --untracked-files=all -- backend/migrations docs/audits` | Isolate migration/report state | `env.py` modified; `0004`/`0005` and Batch 18/19 reports untracked |
| `git diff --name-only`, `git diff --stat` | Count textual changes | 27 files with textual diffs; 28 raw status entries |
| `git cat-file -e 58a0e5c…^{commit}`; `git branch -a --contains 58a0e5c…` | Check local availability of the pinned commit | Absent locally; exit 128 / no such commit |
| `git hash-object` on current `0001`–`0003` | Compare local blobs to remote commit tree | Exact matches with remote blobs |
| `Invoke-WebRequest` on the commit-pinned raw GitHub URL | Retrieve exact source | Downloaded only to temp; SHA-256 and Git blob recorded |
| GitHub API `repos/.../commits/58a0e5c…` | Commit metadata, parent, file list, verification | Parent `777a41a…`; one added file; 156 additions; unsigned |
| GitHub API `contents/backend/migrations/versions?ref=58a0e5c…` and parent | Historical migration tree | Only `0001`–`0004` at commit; only `0001`–`0003` at parent |
| GitHub API `contents/backend/app/models?ref=58a0e5c…` and raw historical model files | Historical ORM context | Role, sign-off, materiality, AuditEvent, and review model documented |
| GitHub API repository/branches and compare `ccd7e60...58a0e5c…` | Remote main/default-branch context | Remote `main` at recovered commit at retrieval time; local `main` 12 commits behind |
| `Get-FileHash` on critical local files and downloaded source | Preservation and source identity | Hashes in sections 2 and 10; recovered SHA-256 in section 3 |
| Python `ast.parse` (static only) on `0004`, `0005`, and recovered file | Enumerate `op.*` calls and counts | 33 `add_column`, 1 `create_table`, 5 FKs, 13 indexes; matching downgrade drops |
| PowerShell `Select-String` / harness `grep` over `backend/app`, `backend/tests`, `docs`, `frontend/src` | Find governance terms and current usage | No current `sign_off`, `audit_events`, `AuditEvent`, `cluster_id`, `resolution_status`, `exposure_amount`, or `variance_amount` usage; `role` hits are source-role concepts, not `users.role`; `source_amount` hits are rule-config field names |
| `Test-Path` on the recovered path and Batch 20 report | Confirm no local copy/report existed | Both absent before writing |
| `Compare-Object` between Batch 19 final and Batch 20 baseline, and between Batch 20 baseline and final | Continuity and sole-change verification | Batch 19/20 baseline identical; final differs only by this report |

### 11.3 Tests, migrations, and secrets

**[Confirmed from current repository evidence]**

- Tests executed: **none**.
- Alembic commands executed: **none**.
- Database connections attempted: **none**.
- `.env` files read: **none**.
- Database URLs, credentials, tokens, or private keys recorded: **none**.
- Application, ORM, migration, configuration, dependency, or existing-documentation edits: **none**.
- Git state changes: **none**.

No test was run because the PostgreSQL suites require an explicitly supplied isolated target and Batch 20 does not authorize one. No Alembic command was run because the batch explicitly prohibits migration commands and no database target was authorized.

---

## 12. Final verdict

### 12.1 Verdict

**PASS — audit scope only.**

The Batch 20 investigation is complete:

- The exact recovered migration was retrieved from the specified commit and verified by SHA-256 and Git blob identity.
- The revision ID, parent, provenance, complete upgrade/downgrade operations, and historical migration tree were verified.
- The recovered revision was compared with `0004_verification_templates.py` and `0005_verification_lineage.py`.
- Six duplicate columns and six duplicate downgrade drops were identified, with exact definitions.
- The current ORM compatibility gaps were documented, including the `reason_code`/`confidence_score` property conflict and the missing template/audit/review contracts.
- The historical ORM context was separated from current state.
- The ancestry/ordering consequences were analyzed; no unmodified incorporation path exists.
- Safe path families, prerequisites, risks, and unresolved questions were documented without selecting a strategy.
- Neon remains unverified; no database or migration was touched.
- The report is the only new working-tree change, and all prior work remains intact.

### 12.2 Verdict qualifications

- **Not a PASS for reconciliation.** The recovered revision is not incorporated, merged, applied, or reconciled.
- **Not a PASS for migration readiness.** No target inventory, strategy, backup verification, or rehearsal exists.
- **Not a PASS for Neon.** Neon was not inspected.
- **Not a PASS for ORM compatibility.** The recovered migration is incompatible with the current ORM as a complete schema.
- **Not a PASS for historical completeness.** The recovered migration omits at least the historical `discrepancy_review_decisions` table.
- **Not a PASS for revalidation.** No test was run, and Batch 16 results remain historical.
- **Not an authorization to commit.** The untracked local migrations, modified `env.py`, and this report remain untracked/uncommitted by design.

If “PASS” were interpreted as permission to migrate, copy the recovered file, or stamp a database, the verdict would be **FAIL**. It is not. The passing verdict applies strictly to the read-only audit deliverable required by Batch 20.

### 12.3 Recommended next step

Preserve the current working tree and obtain, under written owner authorization, the read-only Neon inventory and deployment lineage required by Batch 19. In particular, determine whether any target's `alembic_version` contains `0004_enterprise_governance`, which application commit that target runs, and whether the six lineage columns, governance objects, and audit data already exist. Do not copy the recovered migration into the working tree, do not apply either branch, do not stamp, and do not delete migration history until that evidence is reviewed and a strategy is explicitly authorized.
