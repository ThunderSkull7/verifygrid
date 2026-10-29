# Batch 23 — Implementation Readiness Audit

**Repository:** `C:\Users\shaha\verifygrid`
**Branch:** `feature/batch-4-rule-engine-aggregation`
**HEAD:** `c91e9b37074483eeb7469dc943e1735fd5f5be02`
**Audit date:** 2026-10-29
**Scope:** read-only validation of the Batch 22 canonical migration graph, the `0005` and `0006` DDL contracts, the recovered `0004_enterprise_governance` revision, ORM/application compatibility, local-history retirement, the Batch 22 T1–T14 test plan, and production gates.
**Deliverable status:** **PASS — audit scope only.**
**Implementation verdict:** **NO-GO for implementation as a whole.**
**Production/Neon:** not contacted. No Alembic command, migration, database operation, test suite, deployment action, environment-file read, or Git-state change was performed.
**Files changed by this batch:** one new file, `docs/audits/Batch23_Implementation_Readiness_Audit.md`.

---

## Evidence legend

| Tag | Meaning |
| --- | --- |
| **[Repository]** | Confirmed by reading files in the current working tree at `C:\Users\shaha\verifygrid`. |
| **[Deployed source]** | Confirmed by reading the preserved tree at `DEPLOYED_ROOT` (defined below), recovered from pinned commit `58a0e5c243978480c4ca817c537c700ed6b20516` in Batch 21. |
| **[Prior audit]** | Established by Batch 18–22 evidence and not re-contacted in this batch. |
| **[Static simulation]** | Produced by an AST/static inspection script that read files only and opened no database connection. |
| **[Inference]** | A conclusion drawn from static code or schema behavior, not observed at runtime. |
| **[Unverified]** | A claim that requires production, Render, Neon, Git-remote, or test evidence that this batch did not collect. |
| **[Proposal]** | A future action or design choice; not implemented or authorized by this report. |

`DEPLOYED_ROOT` is:

```text
C:\Users\shaha\AppData\Local\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516
```

The deployed commit object is **not present in the local Git repository**; `git cat-file -t 58a0e5c...` fails with “could not get object info.” The preserved tree is therefore the only local copy of the deployed source. This matters for the combined-application options in section 7.

---

## 1. Executive summary

### 1.1 Verdict

**PASS — audit scope only.** Batch 23 independently re-verified the canonical graph, the two proposed tables, the recovered governance revision, the current/deployed ORM contracts, the current test coverage, and the entry gates. It did not implement, migrate, test against a database, or authorize production.

**NO-GO for implementation as a whole.** Batch 22’s entry gates are not satisfied. The canonical graph is still a design, the working tree still contains two Alembic heads, the recovered `0004` is outside the repository, the local revisions are untracked and not retired, `script.py.mako` is empty, the test-isolation path in `env.py` is uncommitted, and no production inventory, backup/PITR proof, local-data decision, Render configuration review, role-security decision, or two-person authorization exists.

**The migration-graph design itself is implementable.** Static simulation of the intended chain produces exactly one head, and the `0005`/`0006` table contracts are internally consistent with the current template ORM and the deployed review ORM. That is a design finding, not an implementation authorization.

**A migration-only slice is not authorized now.** It would require an explicit written amendment to Batch 22’s entry gates, a written application-version decision, and a scope limited to the canonical graph plus tests. Without that amendment, even a schema-only implementation would violate the entry gates.

### 1.2 Decision matrix

| Scope | Verdict | Basis |
| --- | --- | --- |
| Batch 23 audit deliverable | **PASS** | Required evidence collected; one report added; no code/database/Git change. |
| Canonical graph design | **PASS — conditional** | Static chain is linear and single-headed; duplicate lineage DDL is identified; old branch must be retired. |
| `0005_verification_templates` contract | **PASS — verified** | Ten columns, defaults, FK, unique constraint, and index agree with the current ORM, schema, service, and endpoints. |
| `0006_discrepancy_review_decisions` contract | **PASS — inferred contract** | Twelve columns, two cascade FKs, four indexes agree with the deployed ORM and review service; no migration ever created the table. |
| Recovered `0004_enterprise_governance` | **PASS — provenance verified** | SHA-256 matches Batch 20/21; file is not in local Git; recovery is external to the repository. |
| ORM compatibility for the canonical target | **NO-GO for combined app** | Current ORM is a subset; option B/D requires a large port; option A is schema-only. |
| Implementation as a whole | **NO-GO** | Batch 22 entry gates remain open; multiple P0/P1 blockers in section 13. |
| Migration-only slice | **NO-GO now; eligible for amendment** | Requires written gate amendment and option A decision. |
| Production migration/deployment | **NO-GO** | No production inventory, backup/PITR proof, rehearsal, Render review, or authorization. |

### 1.3 Principal findings

1. **[Static simulation]** The canonical chain `0001_initial_tables → 0002_verification_runs → 0003_user_password → 0004_enterprise_governance → 0005_verification_templates → 0006_discrepancy_review_decisions` is linear and has one head, `0006_discrepancy_review_decisions`. The simulation injected the two proposed revisions because their files do not exist yet; it does not prove those files are correct or committed.

2. **[Repository + Deployed source]** The working tree plus the recovered `0004` currently has **two heads**: `0005_verification_lineage` and `0004_enterprise_governance`. `alembic upgrade head` would be ambiguous until the local branch is retired.

3. **[Repository + Deployed source]** The six lineage columns are already added by `0004_enterprise_governance`. The local `0005_verification_lineage` adds the same six definitions again. Retaining both would produce duplicate `ADD COLUMN` operations and a migration failure on a governance-built database.

4. **[Repository]** The `0005_verification_templates` contract is exact: ten columns, `owner_id → users.id ON DELETE SET NULL`, unique `(owner_id, name)`, and `ix_verification_templates_owner_id`. The current ORM and template service agree, apart from the expected `owner_id IS NULL` uniqueness behavior after user deletion.

5. **[Deployed source]** The `0006_discrepancy_review_decisions` contract is a reconstruction, not a recovered migration. It has twelve columns, two `ON DELETE CASCADE` FKs, four indexes, no unique or check constraints, no user FK, and no `updated_at`. The deployed ORM and review service agree on the column set. The table’s historical DDL, if any ever existed outside the repository, is unknown.

6. **[Repository + Deployed source]** The current ORM is a production **subset**: `users` 6 columns, `verification_runs` 15, `verification_discrepancies` 19, and no `audit_events` or `discrepancy_review_decisions`. The deployed ORM has `users` 7, `verification_runs` 24, `verification_discrepancies` 36, `audit_events` 14, and `discrepancy_review_decisions` 12. A combined build must port the missing models, services, schemas, and routes; a schema-only deployment preserves governance data but not governance functionality.

7. **[Repository]** The current verification engine writes lineage on the multi-source path but does **not** write physical `_reason_code`/`_confidence_score`, materiality, or clustering fields at `backend/app/services/verification_engine.py:1751` and `:2869`. The deployed engine writes them at `DEPLOYED_ROOT\backend\app\services\verification_engine.py:1679-1680` and `:2617-2618`.

8. **[Repository]** The current `reason_code` property includes a `NULL_KEY` special case for blank-key `needs_review` rows (`backend/app/models/verification_run.py:243-247`). The deployed property omits that branch. Simply porting the deployed property changes blank-key semantics unless every write persists `_reason_code` or the fallback is preserved.

9. **[Repository + Deployed source]** Several application-contract gaps are not fully covered by Batch 22: privileged role self-assignment at registration, trusted `X-User-Role` header overrides, database-length overflows for review/assignment fields, unsynchronized audit sequence allocation, cascade deletion of audit-like rows, `cluster_name` without a length guard, and server-default drift that the parity test deliberately does not compare.

10. **[Repository]** The existing migration tests are tied to the retired local head: `PREVIOUS_HEAD = "0004_verification_templates"` and `EXPECTED_HEAD = "0005_verification_lineage"` in `backend/tests/test_alembic_migration_parity.py`, and `EXPECTED_HEAD = "0005_verification_lineage"` in `backend/tests/test_postgres_migration_application.py`. They do not cover governance, review, audit, the canonical head, production-scale preservation, raw defaults, or the new graph.

11. **[Repository]** The test isolation path depends on an uncommitted `backend/migrations/env.py` modification that honors `config.attributes["connection"]`. If that path is lost or not committed, `alembic.command.upgrade()` in the tests falls back to `settings.database_url`, which can be a remote application database. The test modules also import `settings`, and `Settings` loads `.env` via `pydantic-settings`; Batch 22’s claim that “no test reads `.env`” is inaccurate.

12. **[Repository]** The local development database cannot be truthfully stamped or upgraded onto the canonical graph. It either has templates at `0004_verification_templates` or templates plus lineage at `0005_verification_lineage`; either way it lacks governance, and canonical `0005` would attempt to create an existing `verification_templates` table. The disposition must be a disposable rebuild or an export/rebuild/reload, never a stamp.

13. **[Repository]** Batch 22’s entry gates are all still open or only partially evidenced: no written option A/B/D decision, no committed canonical graph, no in-repository provenance, no production read-only inventory, no tested backup/PITR restore, no local-data decision, no Render dashboard review, no review-feature scope, no role-security review, and no two-person ownership.

14. **[Proposal]** The first authorized action is therefore **not code**. It is a written gate amendment and application-version decision, followed by an offline-only graph implementation slice. Section 13.4 defines the exact first step.

### 1.4 What Batch 23 adds beyond Batch 22

Batch 22 designed the reconciliation. Batch 23 adds independent verification and identifies issues that the design did not treat as gates:

- the deployed commit is absent from local Git, so a combined port cannot rely on local ancestry;
- the local `origin/main` ref is `ccd7e604...` (2026-10-21), not the deployed commit, and no fetch was performed;
- the parity test’s default-comparison blind spot is explicit in its own comment;
- the uncommitted `env.py` connection path is a **safety dependency**, not merely a convenience;
- registration can self-assign privileged roles, and governance trusts a client-supplied role header;
- review/assignment fields can exceed their DB columns and produce server errors;
- the audit chain has no database-level sequence uniqueness or locking;
- the audit/review cascade FKs conflict with any retention policy;
- `cluster_name` has no 255-character guard;
- `0003_user_password` has a `server_default=""` password hash that the ORM does not declare.

These are implementation-readiness findings. They do not invalidate the canonical graph, but they prevent a claim that the system is ready to implement without further decisions.

---

## 2. Scope, constraints, and baseline

### 2.1 In scope

- Validate the canonical revision chain and the proposed revision metadata.
- Verify every column, type, nullability, default, foreign key, unique constraint, and index of the two proposed tables against the application code.
- Re-verify the recovered `0004_enterprise_governance` object inventory and its six lineage columns.
- Compare the current ORM, the deployed ORM, and the canonical target.
- Audit Batch 22’s T1–T14 test plan against the tests that actually exist.
- Specify how to run migration tests only against an isolated, disposable PostgreSQL database.
- Define the local-history retirement mechanics and the production gates.
- Produce a GO/NO-GO, remaining blockers, expected files, and first authorized step.

### 2.2 Out of scope and prohibited actions

- No code, ORM, migration, configuration, environment, deployment, or existing-report edit.
- No Alembic `upgrade`, `downgrade`, `stamp`, `revision`, `history`, `current`, or `heads`.
- No PostgreSQL, Neon, Render, Cloudflare, or production database connection.
- No migration, schema, data, or `alembic_version` change.
- No test suite, pytest run, or database client invocation.
- No `.env` read, environment-variable change, secret exposure, or credential validation.
- No Git commit, push, fetch, checkout, branch, tag, stash, reset, clean, merge, rebase, or worktree change.
- No Render or Cloudflare configuration change.

### 2.3 Working-tree baseline

**[Repository]**

| Property | Value |
| --- | --- |
| Branch | `feature/batch-4-rule-engine-aggregation` |
| HEAD | `c91e9b37074483eeb7469dc943e1735fd5f5be02` |
| HEAD subject | `feat: implement Batch 4 advanced rule engine, aggregation and split-payment reconciliation` |
| HEAD commit time | `2026-10-25T23:17:40+05:30` |
| Working-tree entries, `--untracked-files=all` | **68 before this report** |
| Modified entries | 28 |
| Untracked entries | 40 |
| `refs/remotes/origin/main` | `ccd7e604ac1d262fca9d108e0e62875bec47d1c6` (2026-10-21) |
| Deployed commit in local Git | **absent**; `git cat-file` reports “could not get object info” |

The 68 entries include 28 modified files and 40 untracked files. The untracked set includes the two local migrations, the template feature files, the migration tests, the Batch 18–22 audit reports, and several frontend tests. No existing entry was modified by Batch 23.

### 2.4 Deployed-source baseline

**[Prior audit + Deployed source]**

Batch 21 established that remote `main` pointed at `58a0e5c243978480c4ca817c537c700ed6b20516` at its audit time, and preserved that tree under `DEPLOYED_ROOT`. Batch 23 did not re-contact GitHub or Render. The local repository does not contain that commit object, and local `origin/main` points at an older commit. Therefore:

- the deployed tree is evidence of the source at the pinned commit;
- it is **not** proof that Render is currently running that commit;
- it is **not** a local Git ancestor or merge base;
- any combined port must either use the preserved tree or perform an authorized read-only fetch in a future batch.

This is a deployment-identity blocker, not a reason to distrust the recovered file. The recovered `0004` file’s SHA-256 matches the Batch 20/21 provenance hash.

### 2.5 Method

- Read the current migration files, ORM models, schemas, services, endpoints, and tests.
- Read the recovered `0004` migration and deployed ORM/services from `DEPLOYED_ROOT`.
- Import the current and deployed ORM metadata in separate Python processes to enumerate tables, columns, defaults, indexes, and foreign keys. This opened no database connection.
- Parse the migration graph with an AST script outside the repository to list revisions, parents, duplicate IDs, and heads.
- Use `Get-FileHash` for every critical file.
- Use `Select-String` and targeted reads to map write paths and test coverage.
- Do not infer production state from local files.

---

## 3. Canonical graph validation

### 3.1 Revision inventory

**[Repository + Deployed source + Proposal]**

| File | Revision | `down_revision` | Present in current tree? | Role |
| --- | --- | --- | --- | --- |
| `0001_initial_tables.py` | `0001_initial_tables` | `None` | Yes | Base tables. |
| `0002_verification_runs.py` | `0002_verification_runs` | `0001_initial_tables` | Yes | Runs and discrepancies. |
| `0003_user_password.py` | `0003_user_password` | `0002_verification_runs` | Yes | Adds `users.hashed_password`. |
| `0004_verification_templates.py` | `0004_verification_templates` | `0003_user_password` | Yes, untracked | Local template branch; **retire**. |
| `0005_verification_lineage.py` | `0005_verification_lineage` | `0004_verification_templates` | Yes, untracked | Local lineage branch; **retire**. |
| `0004_enterprise_governance_and_materiality.py` | `0004_enterprise_governance` | `0003_user_password` | **No**; recovered at `DEPLOYED_ROOT` | Governance, materiality, audit, six lineage columns. |
| `0005_verification_templates.py` | `0005_verification_templates` | `0004_enterprise_governance` | **No**; proposed | Canonical template table. |
| `0006_discrepancy_review_decisions.py` | `0006_discrepancy_review_decisions` | `0005_verification_templates` | **No**; proposed | Canonical review table. |

All revision IDs and parents in the existing files were parsed successfully. There are no duplicate revision IDs among the existing files.

### 3.2 Current graph versus canonical graph

**[Static simulation]**

The AST script `C:\Users\shaha\AppData\Local\Temp\opencode\batch23_graph_check.py` read the five current migration files plus the recovered governance migration. Its output was:

```text
FILES:
  0001_initial_tables.py: revision='0001_initial_tables' down=None
  0002_verification_runs.py: revision='0002_verification_runs' down='0001_initial_tables'
  0003_user_password.py: revision='0003_user_password' down='0002_verification_runs'
  0004_verification_templates.py: revision='0004_verification_templates' down='0003_user_password'
  0005_verification_lineage.py: revision='0005_verification_lineage' down='0004_verification_templates'
  0004_enterprise_governance_and_materiality.py: revision='0004_enterprise_governance' down='0003_user_password'
DUPLICATE REVISIONS: []
HEADS (working tree + recovered): ['0005_verification_lineage', '0004_enterprise_governance']
CANONICAL HEADS: ['0006_discrepancy_review_decisions']
CANONICAL CHAIN: 0001_initial_tables -> 0002_verification_runs -> 0003_user_password -> 0004_enterprise_governance -> 0005_verification_templates -> 0006_discrepancy_review_decisions
```

The canonical simulation injected the proposed `0005_verification_templates` and `0006_discrepancy_review_decisions` revisions because their files do not exist. It proves the intended parent relationships are acyclic and single-headed; it does not prove the files’ DDL.

**Current graph shape:**

```text
0001_initial_tables
  └── 0002_verification_runs
        └── 0003_user_password
              ├── 0004_verification_templates
              │     └── 0005_verification_lineage        (head)
              └── 0004_enterprise_governance             (head)
```

**Canonical graph shape:**

```text
0001_initial_tables
  └── 0002_verification_runs
        └── 0003_user_password
              └── 0004_enterprise_governance
                    └── 0005_verification_templates
                          └── 0006_discrepancy_review_decisions   (sole head)
```

### 3.3 Duplicate lineage DDL

**[Repository + Deployed source]**

The recovered governance migration already adds all six columns that the local lineage migration adds:

| Column | `0004_enterprise_governance` | Local `0005_verification_lineage` | Duplicate? |
| --- | --- | --- | --- |
| `verification_runs.sources` | `sa.JSON()`, nullable, line 29 | `sa.JSON()`, nullable, line 45 | Yes, exact type/nullability. |
| `verification_discrepancies.source_row_indices` | `sa.JSON()`, nullable, line 62 | `sa.JSON()`, nullable, line 52 | Yes. |
| `verification_discrepancies.source_records` | `sa.JSON()`, nullable, line 63 | `sa.JSON()`, nullable, line 56 | Yes. |
| `verification_discrepancies.child_records` | `sa.JSON()`, nullable, line 64 | `sa.JSON()`, nullable, line 63 | Yes. |
| `verification_discrepancies.aggregated_amount` | `sa.Float()`, nullable, line 65 | `sa.Float()`, nullable, line 67 | Yes. |
| `verification_discrepancies.expected_amount` | `sa.Float()`, nullable, line 66 | `sa.Float()`, nullable, line 71 | Yes. |

The local `0005` downgrade also drops all six columns. If the canonical graph retained it after `0004_enterprise_governance`, the upgrade would fail on a database that already has the columns, and a downgrade would drop governance-owned lineage. The revision must be retired, not replayed.

### 3.4 Graph findings

**[Repository + Static simulation]**

1. **Two heads now.** The graph is not deployable with `head` until the local branch is removed. A deployment script that uses `head` would either fail or choose a head unpredictably.
2. **The recovered `0004` is not in the repository.** It exists only under `DEPLOYED_ROOT`. An implementation must copy it byte-identically and verify its hash; it must not retype or “clean up” its operations.
3. **The local migrations are untracked.** They are not protected by Git history. Retiring them by deletion would lose content unless they are archived outside `backend/migrations/versions/`.
4. **The numeric prefixes collide.** `0004_verification_templates` and `0004_enterprise_governance` are distinct revision IDs with the same filename prefix. Filename ordering is not Alembic ordering; only `revision`/`down_revision` matter.
5. **No branch labels or `depends_on` are used.** The graph relies on a single linear parent chain. That is acceptable only after the branch is removed.
6. **The canonical simulation is not a committed artifact.** A future test must assert the graph; a one-off temp script is evidence for this audit, not a repository safeguard.
7. **`alembic upgrade head` is unsafe until the graph is canonical.** Section 10 and section 12 prohibit it for production before the retirement is committed.

---

## 4. `0005_verification_templates` contract validation

### 4.1 Revision metadata

**[Proposal derived from Repository]**

| Property | Required value |
| --- | --- |
| File | `backend/migrations/versions/0005_verification_templates.py` |
| `revision` | `0005_verification_templates` |
| `down_revision` | `0004_enterprise_governance` |
| `branch_labels` | `None` |
| `depends_on` | `None` |
| DDL source | The `upgrade()` body of the current untracked `0004_verification_templates.py`, with only the revision metadata and docstring changed. |

The reissue changes the revision identifier, not the table contract. The old file’s `revision`/`down_revision` values and the application-status paragraph must not be copied into the canonical revision; the DDL and `downgrade()` operations should remain equivalent.

### 4.2 Table contract

**[Repository: `backend/migrations/versions/0004_verification_templates.py` + `backend/app/models/verification_template.py`]**

| Column | SQLAlchemy type | PostgreSQL type | Nullable | Default | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `sa.Uuid()` | `uuid` | No | none; application `uuid.uuid4` | Primary key. |
| `owner_id` | `sa.Uuid()` | `uuid` | Yes | none | FK `users.id` `ON DELETE SET NULL`; indexed. |
| `name` | `sa.String(255)` | `varchar(255)` | No | none | Unique with `owner_id`. |
| `description` | `sa.Text()` | `text` | Yes | none | |
| `mode` | `sa.String(50)` | `varchar(50)` | No | none | Application accepts only `organization`. |
| `visibility` | `sa.String(20)` | `varchar(20)` | No | `'personal'` (server and client) | Dormant sharing field; only `personal` accepted. |
| `config_version` | `sa.Integer()` | `integer` | No | `1` (server and client) | |
| `configuration` | `sa.JSON()` | `json` | No | none | Validated version-1 snapshot. |
| `created_at` | `sa.DateTime(timezone=True)` | `timestamptz` | No | `now()` | |
| `updated_at` | `sa.DateTime(timezone=True)` | `timestamptz` | No | `now()`; ORM `onupdate=func.now()` | |

The ten-column set, types, nullability, and defaults match the current ORM exactly. The migration uses `sa.text("now()")`, which is equivalent to the ORM’s `func.now()` server default.

### 4.3 Constraint and index inventory

**[Repository]**

| Object | Definition | Name | Notes |
| --- | --- | --- | --- |
| Primary key | `(id)` | PostgreSQL default `verification_templates_pkey` | No explicit name in the migration. |
| Foreign key | `owner_id → users.id ON DELETE SET NULL` | PostgreSQL default `verification_templates_owner_id_fkey` | Unnamed in the migration; the ORM also omits a name. |
| Unique | `(owner_id, name)` | `uq_verification_templates_owner_name` | Explicitly named in both migration and ORM. |
| Index | `(owner_id)` | `ix_verification_templates_owner_id` | Non-unique; explicitly named. |

There are no check constraints, no additional unique constraints, and no indexes on `name`, `mode`, `visibility`, or `created_at`.

### 4.4 Cross-check against application code

**[Repository]**

| Layer | Evidence | Result |
| --- | --- | --- |
| ORM | `backend/app/models/verification_template.py`: 10 columns; `owner_id` nullable FK with `index=True`; `visibility`/`config_version` server and client defaults; `updated_at` `onupdate=func.now()`. | **Match.** |
| Create schema | `backend/app/schemas/template.py`: `name` length 1–255; `description` unbounded; `mode` validated to `organization`; `visibility` validated to `personal`; `configuration` validated by `build_configuration`. | **Compatible.** All validated values fit the columns. |
| Update schema | `TemplateUpdate`: `name` length 1–255; `description` unbounded; `visibility` revalidated; `configuration` revalidated. | **Compatible.** |
| Service | `create_template` sets `owner_id`, stripped `name`, `description` or `NULL`, `visibility='personal'`, `config_version=1`; pre-checks duplicates and raises 409. `update_template` revalidates configuration and sets `config_version` from the payload. | **Compatible with a 10-character limit for `mode` and 8 for `visibility`.** |
| Endpoints | `backend/app/api/v1/endpoints/templates.py`: list/create/get/update/delete; cross-user lookups return 404; duplicate names return 409. | **Compatible.** |
| Unit tests | `backend/tests/test_batch11_templates.py`, `backend/tests/test_batch13_template_workflow.py`: ownership, duplicate rejection, config validation, apply workflow. | **Cover the application contract, not the migration DDL.** |
| Migration test | `backend/tests/test_postgres_migration_application.py::test_template_lifecycle_and_uniqueness_on_migrated_schema` exercises create/get/list/duplicate on a migration-built schema. | **Covers the template table on the retired local graph, not on the canonical graph.** |

### 4.5 Findings

1. **PASS — contract exact.** No column, type, nullability, default, foreign-key action, unique constraint, or index change is required. Reissuing the file as `0005` is sufficient for the table contract.

2. **Unique constraint and `NULL` owners.** PostgreSQL treats `NULL` values as distinct in a unique constraint. After a user deletion sets `owner_id` to `NULL`, multiple templates with the same name and `NULL` owner can coexist. The application never creates a `NULL`-owner template and always scopes reads to `owner_id = current_user.id`, so this is a dormant-data edge case, not a normal-path defect. It should be documented, not “fixed” with a partial unique index in this batch.

3. **Redundant owner index.** The unique constraint on `(owner_id, name)` already provides an index whose leading column is `owner_id`; `ix_verification_templates_owner_id` duplicates that prefix. Retaining it matches the current migration and ORM and is harmless at expected scale, but it is extra write cost. Do not remove it in this reconciliation; a future migration can consolidate.

4. **No database check constraints.** `mode` and `visibility` are enforced only by Pydantic and service code. A raw SQL writer can insert an unsupported mode or visibility. This is consistent with the rest of the schema and with the current ORM. Adding checks now would change the contract and is out of scope.

5. **`updated_at` has no database trigger.** The ORM’s `onupdate=func.now()` bumps the column for ORM updates, so `update_template` behaves correctly. Raw SQL updates will not bump it. This is normal for this codebase and not a migration defect.

6. **`configuration` is `json`, not `jsonb`.** The table has no containment or GIN index and the service persists/returns the whole snapshot. `json` is the current ORM type. Switching to `jsonb` would be a new design decision, not a reconciliation fix.

7. **`mode` filtering is not independently indexed.** `list_templates` filters `owner_id` and optionally `mode`, then orders by `created_at`. The owner index narrows the scan; per-user template counts are expected to be small. No index is required for this release.

8. **Local table collision.** The local development database was migrated to `0004_verification_templates`, so it already has `verification_templates`. Canonical `0005` would attempt `CREATE TABLE` against an existing table. This is direct evidence that the local database cannot be stamped or upgraded; section 10 defines retirement.

---

## 5. `0006_discrepancy_review_decisions` contract validation

### 5.1 Revision metadata

**[Proposal derived from Deployed source]**

| Property | Required value |
| --- | --- |
| File | `backend/migrations/versions/0006_discrepancy_review_decisions.py` |
| `revision` | `0006_discrepancy_review_decisions` |
| `down_revision` | `0005_verification_templates` |
| `branch_labels` | `None` |
| `depends_on` | `None` |
| DDL source | The deployed ORM `DiscrepancyReviewDecision` in `DEPLOYED_ROOT\backend\app\models\verification_run.py`, cross-checked against `DEPLOYED_ROOT\backend\app\services\review_service.py`. No migration in the repository or preserved tree creates this table. |

This is a **reconstruction**, not a recovered migration. Column names, types, nullability, foreign keys, and indexes are recoverable from the deployed ORM. Constraint names and the historical DDL are not.

### 5.2 Table contract

**[Deployed source]**

| Column | SQLAlchemy type | PostgreSQL type | Nullable | Default | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `sa.Uuid()` | `uuid` | No | none; ORM `uuid.uuid4` | Primary key. |
| `discrepancy_id` | `sa.Uuid()` | `uuid` | No | none | FK `verification_discrepancies.id` `ON DELETE CASCADE`; indexed. |
| `run_id` | `sa.Uuid()` | `uuid` | No | none | FK `verification_runs.id` `ON DELETE CASCADE`; indexed. |
| `decision` | `sa.String(50)` | `varchar(50)` | No | none | One of `APPROVE`, `REJECT`, `FORCE_MATCH`, `ESCALATE`, `REOPEN` after normalization. |
| `justification` | `sa.Text()` | `text` | No | none | Service rejects blank/whitespace-only. |
| `reviewer_id` | `sa.String(100)` | `varchar(100)` | Yes | none | Text identity; no user FK. |
| `reviewer_email` | `sa.String(255)` | `varchar(255)` | Yes | none | Text identity; no user FK. |
| `previous_status` | `sa.String(50)` | `varchar(50)` | Yes | none | Snapshot of `resolution_status` before the decision. |
| `new_status` | `sa.String(50)` | `varchar(50)` | No | none | Mapped from `DECISION_TO_STATUS`. |
| `is_bulk_action` | `sa.Boolean()` | `boolean` | No | none in deployed ORM; client default `False` | Service sets `False` for single review and `True` for bulk. |
| `cluster_id` | `sa.String(64)` | `varchar(64)` | Yes | none | Cluster at decision time; not an FK. |
| `created_at` | `sa.DateTime(timezone=True)` | `timestamptz` | No | `now()` | Service also passes an explicit UTC timestamp. |

There is no `updated_at`, no soft-delete column, and no free-form metadata JSON column.

### 5.3 Constraint and index inventory

**[Deployed source]**

| Object | Definition | Name in deployed metadata | Notes |
| --- | --- | --- | --- |
| Primary key | `(id)` | None (auto-generated) | |
| Foreign key | `discrepancy_id → verification_discrepancies.id ON DELETE CASCADE` | None (auto-generated) | Deletes review rows when a discrepancy is deleted. |
| Foreign key | `run_id → verification_runs.id ON DELETE CASCADE` | None (auto-generated) | Deletes review rows when a run is deleted. |
| Index | `(cluster_id)` | `ix_discrepancy_review_decisions_cluster_id` | Non-unique. |
| Index | `(discrepancy_id)` | `ix_discrepancy_review_decisions_discrepancy_id` | Non-unique. |
| Index | `(reviewer_id)` | `ix_discrepancy_review_decisions_reviewer_id` | Non-unique. |
| Index | `(run_id)` | `ix_discrepancy_review_decisions_run_id` | Non-unique. |

There is no unique constraint, no check constraint, and no index on `created_at`, `decision`, `reviewer_email`, or `(discrepancy_id, created_at)`.

### 5.4 Cross-check against application code

**[Deployed source]**

| Layer | Evidence | Result |
| --- | --- | --- |
| ORM | `DiscrepancyReviewDecision`: 12 columns; two `ON DELETE CASCADE` FKs; four indexes; `is_bulk_action` client default `False`; `created_at` server default `now()`. | **Column set matches the reconstruction.** |
| Review schema | `ReviewDecisionRequest`: `decision` unbounded, `justification` min length 1, `reviewer_id`/`reviewer_email` optional and unbounded. `BulkReviewRequest` likewise has unbounded decision/justification. `AssignmentRequest.reviewer_id` is required and unbounded. | **Lengths are not bounded to the database columns.** |
| Single-review service | `apply_single_review`: normalizes decision to uppercase; uses `DECISION_TO_STATUS`; falls back to `current_user.id`/`email` or `system`; requires non-blank justification; writes `previous_status`, `new_status`, `is_bulk_action=False`, `cluster_id`, explicit `created_at`; updates `resolution_status`, `resolution_note`, `resolved_by`, `resolved_at`; writes an audit event. | **Writes are compatible with the table, subject to the length findings below.** |
| Bulk-review service | `apply_bulk_review`: same decision validation; selects by `cluster_id` or explicit IDs; writes one review row per discrepancy with `is_bulk_action=True`; updates resolution state; writes a single bulk audit event. | **Compatible.** |
| Assignment service | `assign_discrepancies`: requires non-blank `reviewer_id`; sets `assigned_to = reviewer_email or reviewer_id.strip()` and `assigned_at` on every selected discrepancy. | **`assigned_to` is `varchar(100)` while `reviewer_email` is `varchar(255)`.** |
| Endpoints | `DEPLOYED_ROOT\backend\app\api\v1\endpoints\review.py`: cluster listing, cluster records, single review, bulk review, assignment. | **Routes exist but have no migration-created table in the preserved tree.** |
| Tests | Deployed `test_exception_clustering.py` covers bulk review execution, eligibility barriers, and API cluster/review/assignment endpoints. The current tree has no governance/review/audit tests. | **Review behavior is tested only against model-created SQLite, not against a migration-built table.** |
| Production brief | Batch 21 recorded `discrepancy_review_decisions` as absent in production. | **The deployed application’s review feature cannot work against the production schema until `0006` is applied.** |

### 5.5 Findings

1. **PASS — reconstructed contract is internally consistent.** Twelve columns, two cascade FKs, and four indexes match the deployed ORM and the review service’s write paths. No recovered migration exists, so this is the best available evidence.

2. **`is_bulk_action` default is an open contract detail.** The deployed ORM declares only a client-side `False`; Batch 22 specifies a server default of `false`. Either choice works because both service paths set the value explicitly. The canonical migration should either omit the server default and mirror the ORM exactly, or add `server_default=sa.false()` and add the same `server_default` to the ORM. Do not ship a migration default that the ORM does not declare without recording the drift.

3. **P1 — review and assignment lengths can exceed the database.** `ReviewDecisionRequest.reviewer_id`, `.reviewer_email`, `BulkReviewRequest`, and `AssignmentRequest.reviewer_id` have no `max_length`. `reviewer_id`/`assigned_to` are `varchar(100)`; `reviewer_email` is `varchar(255)` while `resolved_by` is `varchar(100)`. A long request value or a user email longer than 100 characters can produce a PostgreSQL `DataError` (500) or a failed assignment. The application must bound these fields or truncate/reject before persistence. This is an application-contract blocker, not a DDL change.

4. **No user foreign key is intentional but weakly enforced.** `reviewer_id`/`reviewer_email` are denormalized text so a decision survives user deletion. That supports audit retention, but it also means no referential integrity and no guarantee that the reviewer existed. This is acceptable only if the retention policy explicitly treats the text identity as the audit record of record.

5. **P2 — `run_id` is not constrained to the discrepancy’s run.** The service queries the discrepancy by `run_id` before writing, so normal paths are consistent. The database permits a review row whose `run_id` differs from `verification_discrepancies.run_id`. A composite FK would close this, but it would add an index/constraint not present in the deployed ORM. Record it as a known integrity limitation rather than silently changing the contract.

6. **P1 — cascade FKs conflict with evidence retention.** Deleting a run or discrepancy deletes its review decisions. The same pattern exists on `audit_events`. If review decisions and audit events are evidence of record, `ON DELETE CASCADE` is the wrong lifecycle for retention. This must be decided before `0006` is finalized. Options include `RESTRICT`, `SET NULL` on a nullable key, or an archival/export step before deletion. Changing the action changes the deployed ORM contract and needs an explicit decision.

7. **No unique constraint is correct.** A discrepancy can receive multiple decisions over time (reopen, re-review). The table is append-only by convention. The missing `updated_at` reinforces that.

8. **No `created_at` index.** Listing is scoped by discrepancy, run, cluster, or reviewer, all indexed. Ordering within a discrepancy uses the `discrepancy_id` index plus a sort. At expected volumes this is acceptable. A composite `(discrepancy_id, created_at)` index would be a future optimization, not a reconciliation requirement.

9. **Production absence is both an opportunity and a warning.** Because the table is absent in production, `0006` can create it without colliding with an existing review table. But the deployed application already exposes review routes that would fail against production today. The read-only production inventory must confirm the table is still absent before `0006` is deployed.

---

## 6. Recovered `0004_enterprise_governance` validation

### 6.1 Provenance

**[Prior audit + Deployed source]**

| Property | Value |
| --- | --- |
| Preserved path | `DEPLOYED_ROOT\backend\migrations\versions\0004_enterprise_governance_and_materiality.py` |
| Revision | `0004_enterprise_governance` |
| Parent | `0003_user_password` |
| SHA-256 | `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` |
| Local Git object | **Absent.** `git cat-file -t 58a0e5c...` fails; the commit is not an ancestor of local `HEAD` or `origin/main`. |
| Required treatment | Copy byte-identically into `backend/migrations/versions/0004_enterprise_governance.py`; verify the hash after copy; do not edit its operations. |

The hash matches the Batch 20/21 provenance record. The file is the only local authority for the governance DDL; the deployed commit object is not available locally.

### 6.2 Object inventory

**[Deployed source]**

| Table | Columns added | Foreign keys added | Indexes added | Other |
| --- | --- | --- | --- | --- |
| `users` | 1 (`role`) | 0 | 0 | |
| `verification_runs` | 10 (`sources` plus 9 sign-off fields) | 2 (`sign_off_proposed_by`, `sign_off_approved_by` → `users.id`, `SET NULL`) | 1 (`sign_off_status`) | |
| `verification_discrepancies` | 22 (lineage, materiality, clustering, review state, physical reason/confidence) | 0 | 6 | |
| `audit_events` | new table, 14 columns | 3 (`project_id`/`run_id` cascade; `user_id` set null) | 6 | Primary key only; no unique or check constraints. |
| **Total** | **33 columns** | **5 foreign-key definitions** (2 added to `verification_runs`, 3 inside `audit_events`) | **13** | **1 new table.** |

The 33-column count is `1 (users) + 10 (runs) + 22 (discrepancies)`. The 13-index count is `1 (runs) + 6 (discrepancies) + 6 (audit_events)`.

### 6.3 `users.role`

**[Deployed source]**

| Column | Type | Nullable | Default | Notes |
| --- | --- | --- | --- | --- |
| `role` | `varchar(50)` | No | server `'MAKER'`; ORM client `'MAKER'` | Application roles are `MAKER`, `CHECKER`, `ADMIN`, `VIEWER`. No check constraint. |

The deployed ORM has seven user columns. The current ORM has six and no `role` attribute. The deployed registration schema accepts an unbounded `role` string and the endpoint uppercases and persists it, which is the self-assignment finding in section 8.

### 6.4 `verification_runs` additions

**[Deployed source]**

| Column | Type | Nullable | Default | Notes |
| --- | --- | --- | --- | --- |
| `sources` | `json` | Yes | none | Multi-source snapshot; already written by the current engine. |
| `sign_off_status` | `varchar(50)` | No | server `'DRAFT'`; ORM client `'DRAFT'` | Governance state. |
| `sign_off_proposed_by` | `uuid` | Yes | none | FK `users.id` `ON DELETE SET NULL`. |
| `sign_off_proposed_by_name` | `varchar(255)` | Yes | none | Denormalized maker name. |
| `sign_off_proposal_note` | `text` | Yes | none | |
| `sign_off_proposed_at` | `timestamptz` | Yes | none | |
| `sign_off_approved_by` | `uuid` | Yes | none | FK `users.id` `ON DELETE SET NULL`. |
| `sign_off_approved_by_name` | `varchar(255)` | Yes | none | Denormalized checker name. |
| `sign_off_decision_note` | `text` | Yes | none | |
| `sign_off_decided_at` | `timestamptz` | Yes | none | |

Named foreign keys created by the migration:

- `fk_runs_sign_off_proposed_by_users` on `(sign_off_proposed_by)` → `users.id`, `ON DELETE SET NULL`.
- `fk_runs_sign_off_approved_by_users` on `(sign_off_approved_by)` → `users.id`, `ON DELETE SET NULL`.

Index: `ix_verification_runs_sign_off_status` on `(sign_off_status)`.

The deployed ORM has 24 run columns: 14 pre-governance columns plus `sources` and the nine sign-off columns. The current ORM already declares `sources` and 15 total columns, but the current local migration graph never adds `sources`; that is one of the lineage gaps that motivated the retired local `0005`.

### 6.5 `verification_discrepancies` additions

**[Deployed source]**

| Column | Type | Nullable | Default | Notes |
| --- | --- | --- | --- | --- |
| `source_row_indices` | `json` | Yes | none | Per-source row lineage. |
| `source_records` | `json` | Yes | none | Per-source record lineage. |
| `child_records` | `json` | Yes | none | Split-payment children. |
| `aggregated_amount` | `double precision` | Yes | none | |
| `expected_amount` | `double precision` | Yes | none | |
| `source_amount` | `double precision` | Yes | none | |
| `target_amount` | `double precision` | Yes | none | |
| `variance_amount` | `double precision` | Yes | none | |
| `exposure_amount` | `double precision` | Yes | none | Indexed. |
| `currency` | `varchar(10)` | Yes | server `'USD'`; ORM client `'USD'` | |
| `severity` | `varchar(20)` | Yes | server `'medium'`; ORM client `'medium'` | Indexed. |
| `resolution_status` | `varchar(30)` | Yes | server `'unresolved'`; ORM client `'unresolved'` | Indexed. |
| `resolution_note` | `text` | Yes | none | |
| `resolved_by` | `varchar(100)` | Yes | none | Service writes `reviewer_email or reviewer_id`; email can be up to 255. |
| `resolved_at` | `timestamptz` | Yes | none | |
| `cluster_id` | `varchar(64)` | Yes | none | Indexed. |
| `cluster_name` | `varchar(255)` | Yes | none | Generated names have no length guard. |
| `assigned_to` | `varchar(100)` | Yes | none | Service writes `reviewer_email or reviewer_id`; email can be up to 255. |
| `assigned_at` | `timestamptz` | Yes | none | |
| `side_by_side` | `json` | Yes | none | |
| `reason_code` | `varchar(100)` | Yes | none | Physical column; current ORM exposes a read-only property instead. |
| `confidence_score` | `double precision` | Yes | none | Physical column; current ORM exposes a read-only property instead. |

Indexes created by the migration:

- `ix_verification_discrepancies_exposure_amount`
- `ix_verification_discrepancies_severity`
- `ix_verification_discrepancies_resolution_status`
- `ix_verification_discrepancies_cluster_id`
- `ix_verification_discrepancies_assigned_to`
- `ix_verification_discrepancies_reason_code`

All 22 columns are nullable. Every one is added with either no default or a constant default, so PostgreSQL can add them without a table rewrite. The six lineage columns (`sources`, `source_row_indices`, `source_records`, `child_records`, `aggregated_amount`, `expected_amount`) are the same six that the local `0005_verification_lineage` adds.

### 6.6 `audit_events` table

**[Deployed source]**

| Column | Type | Nullable | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | No | none; ORM `uuid.uuid4` | Primary key. |
| `event_id` | `varchar(64)` | No | none | Indexed; **not unique**. |
| `sequence_number` | `integer` | No | server `1`; ORM client `1` | Indexed; **not unique**. |
| `run_id` | `uuid` | Yes | none | FK `verification_runs.id` `ON DELETE CASCADE`. |
| `project_id` | `uuid` | No | none | FK `projects.id` `ON DELETE CASCADE`. |
| `user_id` | `uuid` | Yes | none | FK `users.id` `ON DELETE SET NULL`. |
| `user_email` | `varchar(255)` | Yes | none | |
| `user_role` | `varchar(50)` | No | server `'MAKER'`; ORM client `'MAKER'` | |
| `event_type` | `varchar(100)` | No | none | Indexed. |
| `timestamp_utc` | `timestamptz` | No | `now()` | |
| `timestamp_str` | `varchar(64)` | No | none | Hash input. |
| `event_payload` | `json` | No | none | |
| `previous_event_hash` | `varchar(64)` | No | none | |
| `current_event_hash` | `varchar(64)` | No | none | Indexed. |

Indexes: `ix_audit_events_event_id`, `ix_audit_events_sequence_number`, `ix_audit_events_run_id`, `ix_audit_events_project_id`, `ix_audit_events_event_type`, `ix_audit_events_current_event_hash`.

The table has one primary key and three foreign keys. It has no unique constraint on `(project_id, run_id, sequence_number)`, `event_id`, or any hash column, and no check constraints.

### 6.7 Verification against the deployed ORM

**[Deployed source]**

| Table | Deployed ORM columns | Migration columns | Types/nullability | Defaults | FKs/indexes |
| --- | --- | --- | --- | --- | --- |
| `users` | 7 | 7 | Match. | Server default `MAKER`; ORM client default `MAKER`. | Match; no FK/index added for `role`. |
| `verification_runs` | 24 | 24 | Match. | `sign_off_status`: server `DRAFT`, ORM client `DRAFT`. | 5 FKs total after `0004`; 5 indexes total. |
| `verification_discrepancies` | 36 | 36 | Match. | `currency`, `severity`, `resolution_status`: server defaults exist, ORM has client defaults only. | 1 FK total; 9 indexes total. |
| `audit_events` | 14 | 14 | Match. | `sequence_number`, `user_role`: server defaults exist, ORM has client defaults only; `timestamp_utc` matches `now()`. | 3 FKs; 6 indexes; PK only. |

No deployed ORM column is missing from the migration, and no migration column is absent from the deployed ORM.

### 6.8 Findings

1. **PASS — provenance and inventory.** The SHA-256 matches the prior audit, and the 33-column/13-index/1-table inventory is exact. The file must be copied byte-identically.

2. **P1 — server-default drift is real but not migration-breaking.** Six columns have server defaults in the migration/DDL that the deployed ORM declares only as client defaults: `users.role`, `verification_runs.sign_off_status`, `verification_discrepancies.currency`, `.severity`, `.resolution_status`, `audit_events.user_role` (and `audit_events.sequence_number`). ORM inserts still get the intended values from client defaults. Raw SQL inserts get the server defaults. The parity test does not compare server defaults (`env.py` sets `compare_type=True` but leaves `compare_server_default` at its default `False`), so this drift is invisible to the existing test. The canonical ORM should either declare these server defaults or the contract should explicitly accept the drift. Do not remove the server defaults from the recovered migration.

3. **P1 — audit chain uniqueness is not enforced.** `audit_service.log_audit_event` reads the latest event for the chain (`ORDER BY sequence_number DESC, timestamp_utc DESC`), computes `sequence_number + 1`, and inserts with no row lock, advisory lock, or unique constraint. Two concurrent writers can allocate the same sequence number and build competing hashes. The validator will then see a duplicate or broken chain. The database cannot prevent this today. This is a concurrency-safety blocker for audit evidence, not a DDL parity issue.

4. **P1 — cascade FKs delete audit evidence.** `audit_events.project_id` and `.run_id` cascade; `.user_id` sets null. Deleting a project or run silently deletes its audit chain. This conflicts with any retention policy that treats audit events as evidence. The same issue applies to `discrepancy_review_decisions`. A retention decision is required before either table is treated as authoritative.

5. **Downgrade is destructive and only partially explicit.** `0004`’s `downgrade()` drops `audit_events` first (deleting all audit data), then drops the added columns. It does not explicitly drop the six discrepancy indexes or the two run foreign keys; PostgreSQL drops dependent indexes/constraints when their columns are dropped. This works on PostgreSQL but is not exercised by any test, and it cannot preserve audit history. Rollback must be treated as a restore-from-backup event, not a routine reverse migration.

6. **The current ORM is not the deployed ORM.** The current models omit `users.role`, all nine sign-off fields, `audit_events`, and `discrepancy_review_decisions`; they expose `reason_code`/`confidence_score` as read-only properties rather than mapped physical columns. Applying canonical `0004` and then running the current parity test would fail because the database would contain columns and tables the current metadata does not describe. This is the core option A versus B/D decision in section 7.

7. **No check constraints on role, sign-off status, resolution status, severity, or decision.** All are application-enforced strings. This is consistent with the deployed ORM and the rest of the schema. Adding checks would change the contract; do not add them during reconciliation.

8. **Lineage duplication is confirmed.** The six lineage columns added by `0004` are exactly the six added by local `0005_verification_lineage`. The local revision must be retired; it cannot follow `0004`.

---

## 7. ORM and application compatibility

### 7.1 Table inventory

**[Repository + Deployed source]**

| Table | Current ORM | Deployed ORM | Canonical target | Migration owner |
| --- | --- | --- | --- | --- |
| `users` | 6 columns | 7 (`role`) | 7 | `0004_enterprise_governance` adds `role`. |
| `projects` | 6 | 6 | 6 | `0001_initial_tables`. |
| `source_files` | 8 | 8 | 8 | `0001_initial_tables`. |
| `verification_runs` | 15 (`sources` already mapped) | 24 | 24 | `0002` base; `0004` adds 10. |
| `verification_discrepancies` | 19 (5 lineage columns already mapped) | 36 | 36 | `0002` base; `0004` adds 22. |
| `verification_templates` | 10 | absent | 10 | `0005_verification_templates` (new). |
| `audit_events` | absent | 14 | 14 | `0004_enterprise_governance` (new). |
| `discrepancy_review_decisions` | absent | 12 | 12 | `0006_discrepancy_review_decisions` (new). |

The current table counts were produced by importing `app.models` in a separate Python process and enumerating `Base.metadata`; no database connection was opened. The deployed counts were produced the same way against `DEPLOYED_ROOT`.

### 7.2 Exact mismatches

**[Repository + Deployed source]**

| # | Area | Deployed/canonical | Current | Consequence | Required action |
| --- | --- | --- | --- | --- | --- |
| M1 | `users.role` | `String(50)`, not null, default `MAKER`, no index; auth response includes role. | No `role` column or attribute; registration/login schemas have no role. | Current app cannot enforce or display maker-checker roles. The DB default would silently assign `MAKER` to current-created users. | Add the column mapping and decide role-management behavior. Do not port the deployed self-assignment bug. |
| M2 | Run sign-off | 9 fields: status, proposer id/name/note/time, approver id/name/note/time; 2 FKs to `users.id` `SET NULL`; status indexed. | None. | Current app cannot propose, approve, reject, or display sign-offs; existing sign-off data is invisible. | Add fields/relationships and port governance service/routes. |
| M3 | Discrepancy materiality | `source_amount`, `target_amount`, `variance_amount`, `exposure_amount` (indexed), `currency` (`USD`), `severity` (`medium`, indexed), `resolution_status` (`unresolved`, indexed), `resolution_note`, `resolved_by`, `resolved_at`. | None. | Current writes leave these NULL; existing values are invisible. | Add fields; port materiality engine and result serialization. |
| M4 | Clustering/review state | `cluster_id` (indexed), `cluster_name`, `assigned_to` (indexed), `assigned_at`, `side_by_side`. | None. | Current app cannot cluster, assign, or display side-by-side records. | Add fields; port clustering/review services and routes. |
| M5 | Physical `reason_code` | `String(100)`, indexed, mapped as `_reason_code` with a property getter/setter. | Read-only property computed from `field_differences` and `match_status`; not a column. | Current reads ignore stored values; current writes leave the column NULL; deployed filters on the physical column will not see current-created rows. | Map `_reason_code` to `reason_code`; write it in the engine; preserve the computed fallback. |
| M6 | Physical `confidence_score` | `Float`, mapped as `_confidence_score` with a property getter/setter. | Read-only property; not a column. | Same semantic drift as M5; current writes leave the column NULL. | Map the column; write it in the engine; preserve the fallback. |
| M7 | `audit_events` | 14 columns, 3 FKs, 6 indexes, SHA-256 hash chain. | No model, no service, no routes; `models/audit_log.py`, `services/audit_service.py`, `schemas/audit.py`, and `endpoints/audit.py` are 0-byte placeholders or absent. | Current activity is not audited; replacing the deployed app would truncate the chain. | Add model/service/routes and calls from run, review, and governance paths. |
| M8 | `discrepancy_review_decisions` | 12 columns, 2 cascade FKs, 4 indexes. | No model, no service, no routes; `models/review.py`, `services/review_service.py`, `schemas/review.py` are 0 bytes; `endpoints/reviews.py` is 0 bytes. | Deployed review endpoints fail because the table is missing; current app has no review feature. | Add `0006`; add model/service/routes if review is in scope. |
| M9 | `verification_templates` | Absent in deployed ORM and production. | 10 columns; model/service/schema/endpoints exist; migration is untracked and local DB has the table. | Current template endpoints fail in production until `0005`; deployed app does not use templates. | Add `0005`; keep current template code in a combined build. |
| M10 | Server defaults | Migration/DB has defaults for role, sign-off status, currency, severity, resolution status, audit role/sequence. | ORM often declares only client defaults; parity test does not compare server defaults. | Raw SQL inserts and ORM inserts can diverge; drift is invisible to tests. | Decide and declare defaults intentionally; add assertions. |
| M11 | Application divergence | Deployed engine is oriented to governance/materiality; deployed `verification_engine.py` is 112,673 bytes, `multisource.py` 5,869, `result.py` 27,657, `preprocessing.py` 22,461, `export_service.py` 49,077, `profiling_service.py` 33,303, `verification.py` 10,035. | Current engine is 127,961 bytes, `multisource.py` 14,503, `result.py` 21,449, `preprocessing.py` 25,763, `export_service.py` 14,112, `profiling_service.py` 40,745, `verification.py` 8,006. | Neither tree is a superset. Wholesale copying in either direction would regress the other branch’s functionality. | Perform a file-by-file merge, not a copy; test both Batch 4 and governance behavior. |
| M12 | Tests | Deployed has governance/audit, exception-clustering, materiality, and recipe tests; they use SQLite `create_all`. | Current has Batch 2–14 tests and migration tests tied to the retired local head; no governance/review/audit tests. | Missing governance tests would let option C pass a green suite while silently disabling governance. | Port and adapt tests; add migration-built coverage. |

### 7.3 Application options

**[Proposal + Repository + Deployed source]**

| Option | What is deployed | Governance functionality | Templates | Effort | Assessment |
| --- | --- | --- | --- | --- | --- |
| **A — Schema-only, keep `58a0e5c`** | Apply `0005` and/or `0006`; do not deploy current code. | Preserved, subject to the security gaps in section 8. | No; `0005` is dormant. | Lowest. | Acceptable only with a written decision to defer templates and an explicit statement that schema-only does not reconcile the current branch. |
| **B — Merge governance into current** | Current branch plus deployed governance/audit/review/materiality/clustering code. | Preserved if the port is complete and tested. | Yes. | Highest. | Recommended target for full functionality. Requires a file-level merge because current Batch 4 code is newer and larger. |
| **D — Start from deployed, add Batch 4/templates** | Deployed tree plus current Batch 4 and template work. | Preserved. | Yes. | Highest. | Functionally equivalent to B, but harder to source: the deployed commit is not in local Git and the template files are untracked. Choose B or D only after a file-level diff. |
| **C — Deploy current alone** | Current branch over the canonical schema. | **Lost**: no role enforcement, sign-off, materiality, clustering, review, or audit writes. | Yes. | Medium. | **Rejected.** It preserves data but silently disables governance. |

Batch 23 does not authorize B or D. The current branch and the preserved deployed tree are both divergent application states; the merged application does not exist yet.

### 7.4 Minimum B/D file manifest

**[Proposal derived from Repository + Deployed source]**

This expands Batch 22 §7.5 with the placeholders and divergences found in Batch 23.

**Models**

- `backend/app/models/user.py`: add `role`.
- `backend/app/models/verification_run.py`: add the 9 sign-off fields and 2 user FKs; add the 17 materiality/clustering/review fields; map `_reason_code`/`_confidence_score` with setters; add `DiscrepancyReviewDecision` and the `review_decisions` relationship; preserve `source_row_index`/`target_row_index` and the current `NULL_KEY` fallback.
- `backend/app/models/audit_log.py`: replace the 0-byte placeholder with `AuditEvent`.
- `backend/app/models/review.py`: remove the 0-byte placeholder or make it a re-export of `DiscrepancyReviewDecision`.
- `backend/app/models/__init__.py`: export `AuditEvent`, `DiscrepancyReviewDecision`, and keep `VerificationTemplate`.

**Schemas**

- `backend/app/schemas/review.py`: replace the 0-byte placeholder with the deployed schemas, with added length bounds.
- Add `backend/app/schemas/audit.py` and `backend/app/schemas/governance.py`.
- `backend/app/schemas/auth.py`: add `role` only with server-controlled assignment and validation; do not expose a privileged role in public registration.
- `backend/app/schemas/result.py`: merge materiality/side-by-side fields.
- Add `backend/app/schemas/recipe.py` if recipes are in scope.

**Services**

- `backend/app/services/review_service.py`: replace the 0-byte placeholder; add length validation before persistence.
- `backend/app/services/audit_service.py`: replace the 0-byte placeholder; add chain serialization.
- Add `clustering_service.py`, `materiality_engine.py`, and `governance_service.py`.
- Add `recipe_service.py` if recipes are in scope.
- `backend/app/services/verification_engine.py`: merge, do not overwrite. Add governance/materiality/clustering writes and physical reason/confidence writes while retaining Batch 4 behavior.
- `backend/app/services/project_service.py`: preserve role-aware behavior if ADMIN semantics are required.
- `backend/app/services/export_service.py`: merge deployed materiality/recipe export behavior if in scope.

**API**

- Replace `backend/app/api/v1/endpoints/audit.py` (0 bytes) with the audit routes.
- Add `review.py` (deployed name) or replace `reviews.py` consistently; do not leave both registered.
- Add `governance.py`.
- Add `recipes.py` if recipes are in scope.
- `backend/app/api/v1/router.py`: register the added routers.
- `backend/app/api/v1/endpoints/auth.py`: persist/return role only under the chosen role policy.
- `backend/app/api/v1/endpoints/verification.py` and `exports.py`: merge governance/materiality response behavior.

**Tests**

- Port deployed `test_governance_audit.py`, `test_exception_clustering.py`, `test_results_materiality.py`, and `test_exports_recipes.py`.
- Adapt fixtures; add migration-built variants.
- Add the T1–T14 tests in section 9.
- Add security regression tests for section 8.

**Explicitly unchanged**

- `backend/app/main.py`: no startup migration hook.
- `backend/app/db/session.py`: no `create_all` and no migration execution.
- No `render.yaml` or deployment configuration change as part of the application merge; if a Render manifest is added, it is a separate deployment change.

### 7.5 Parity-test consequences

**[Repository]**

The current parity test cannot simply be repointed at the canonical head:

- `EXPECTED_HEAD` must become `0006_discrepancy_review_decisions`.
- `PREVIOUS_HEAD` must become `0004_enterprise_governance` for the production-equivalent path, and `0005_verification_templates` for the review-table round trip.
- `Base.metadata` must be the ORM the selected application will actually use. Under option A, the current ORM is not that ORM, so `compare_metadata` against the current subset will report every governance column/table as drift.
- Under option B/D, the reconciled ORM must include all eight tables and physical reason/confidence mappings; otherwise `compare_metadata` will still fail.
- The six-column lineage assertions should be retained as a regression check: the canonical graph must add each lineage column exactly once, in `0004`.
- Server-default assertions must be added explicitly; `compare_server_default` is not enabled.

Under option A, the migration contract should be tested with an independent introspection test that asserts the canonical object inventory, not with `compare_metadata` against the current subset. Under option B/D, both the introspection test and `compare_metadata` should pass.

---

## 8. Additional application-contract gaps

These findings are outside the table-DDL parity question but block a claim that the application is ready to implement or deploy. Severity uses P0 (security or destructive risk), P1 (functional/data-integrity risk), P2 (contract/documentation risk).

### 8.1 Gap register

| ID | Severity | Finding | Evidence | Impact | Required decision/action |
| --- | --- | --- | --- | --- | --- |
| G1 | **P0** | Public registration can self-assign a privileged role. | `DEPLOYED_ROOT\backend\app\schemas\auth.py:20` accepts an optional unbounded `role`; `DEPLOYED_ROOT\backend\app\api\v1\endpoints\auth.py:41` uppercases and persists it; there is no enum, allow-list, or admin check. | An unauthenticated caller can register as `ADMIN`, then use governance routes. Maker-checker separation is defeated. | Do not port this behavior. Role assignment must be server-controlled (default `MAKER`, admin-only elevation) and validated to the four known roles. Add a regression test that `POST /register` with `role=ADMIN` does not create an admin, or is rejected. |
| G2 | **P0** | Governance trusts a client-supplied `X-User-Role` header. | `DEPLOYED_ROOT\backend\app\api\v1\endpoints\governance.py:41,67,94,121` accept `X-User-Role`; `DEPLOYED_ROOT\backend\app\services\governance_service.py:24-32` returns the override if it is one of the four role strings. | Any authenticated user can claim `CHECKER` or `ADMIN` and approve/reject sign-offs. The audit event records the claimed role. | Derive the role from `users.role` only. If an override is required for testing, restrict it to an authenticated admin, make it explicit, and never enable it in production. Add tests that a MAKER cannot approve by sending the header. |
| G3 | **P0** | Alembic CLI can target the ambient application database. | `backend/migrations/env.py:68-75` builds the engine from `settings.database_url` when no explicit connection is supplied; `settings` loads `backend/.env`; `alembic.ini`’s local URL is overwritten at line 25. There is no CLI target guard. | A developer or release job running `alembic upgrade head` can migrate the `.env`-configured cloud database. In a repository where `.env` has pointed at a divergent cloud database, this is a direct production-risk path. | Require an explicit target for any migration command (URL or connection), verify `current_database()`/`current_user()` before DDL, and fail closed when the target is not loopback unless a production flag plus two-person confirmation is present. Do not rely on `.env`. |
| G4 | **P0** | Migration tests depend on an uncommitted `env.py` path and can fall back to the application URL. | `backend/migrations/env.py` is modified (16 additions/2 deletions) to honor `config.attributes["connection"]`; the change is not committed. If it is reverted or lost, `alembic.command.upgrade()` in the tests falls back to `settings.database_url` while the test still validates only `VERIFYGRID_TEST_DATABASE_URL`. | A test run could migrate the application database instead of the isolated schema, with the guard reporting success. | Commit the explicit-connection path and add a hard guard: when `VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS` is enabled and no connection is supplied, raise before connecting. Add an assertion inside the migration path that the connected database/user match the validated test target. |
| G5 | **P1** | Review/assignment fields can exceed their database columns. | `ReviewDecisionRequest.reviewer_id`/`.reviewer_email`, `BulkReviewRequest`, and `AssignmentRequest.reviewer_id` have no `max_length` (`DEPLOYED_ROOT\backend\app\schemas\review.py:67-77,131-137`). `reviewer_id`/`assigned_to` are `varchar(100)`; `reviewer_email` is `varchar(255)`; `resolved_by` is `varchar(100)`. `assign_discrepancies` sets `assigned_to = reviewer_email or reviewer_id.strip()` and `resolved_by = reviewer_email or reviewer_id`. | A long email or request value produces a PostgreSQL `DataError` (500) or a failed assignment. A user email longer than 100 characters can break review writes. | Add `max_length` bounds to the schemas and validate before persistence; decide whether `resolved_by`/`assigned_to` should be 255 or should store a user id instead. Add 422-not-500 tests. |
| G6 | **P1** | Audit sequence allocation is unsynchronized. | `DEPLOYED_ROOT\backend\app\services\audit_service.py:74-89` reads the latest event by `sequence_number DESC, timestamp_utc DESC`, adds 1, and inserts; there is no `FOR UPDATE`, advisory lock, or unique constraint on `(project_id, run_id, sequence_number)` in `0004`. | Concurrent writers can allocate the same sequence and build competing hashes; chain verification then fails or reports a false tamper. | Serialize writes per chain (row/advisory lock) and add a unique constraint in a separate audit-hardening migration. Until then, document single-writer assumptions and do not claim the chain is concurrency-safe. |
| G7 | **P1** | Cascade FKs destroy audit-like evidence. | `0004` creates `audit_events.project_id`/`.run_id` `ON DELETE CASCADE`; `0006` will create `discrepancy_review_decisions.discrepancy_id`/`.run_id` `ON DELETE CASCADE`. | Deleting a project, run, or discrepancy silently deletes audit/review history. A retention policy that treats these rows as evidence cannot coexist with cascade. | Decide retention before finalizing `0006`: `RESTRICT`, `SET NULL` on a nullable key, or archive-before-delete. If the deployed contract must be preserved, record the cascade as an explicit accepted limitation and prohibit deletion in operations. |
| G8 | **P1** | `cluster_name` has no 255-character guard. | `DEPLOYED_ROOT\backend\app\services\clustering_service.py:169-223` builds names from `", ".join(f.replace("_", " ").title() for f in failed_fields)` plus alias/category text; `cluster_name` is `varchar(255)`. | A discrepancy with many or long field names produces a generated name longer than 255 and a `DataError` when clustering persists it. | Truncate deterministically to 255 with an ellipsis or hash suffix; add a test with long field names. Do not widen the column without evidence from production. |
| G9 | **P1** | `reason_code`/`confidence_score` semantics differ between current and deployed. | Current `backend/app/models/verification_run.py:218-247` computes `reason_code` and includes a `NULL_KEY` branch for blank-key `needs_review`; deployed `verification_run.py:309-319` maps physical columns and its property omits that branch. Current engine writes no physical fields; deployed engine writes them at `DEPLOYED_ROOT\backend\app\services\verification_engine.py:1679-1680,2617-2618`. | A naive port changes blank-key reason codes or leaves new rows NULL; deployed filters will not see current-created rows. | Map with setters, write physical values on every discrepancy path, and preserve the current `NULL_KEY` fallback when the physical value is NULL. Add round-trip tests. |
| G10 | **P1** | Default JWT secret is insecure if the environment variable is missing. | `backend/app/core/config.py:24` defaults `secret_key` to a fixed string. | If `SECRET_KEY` is unset in production, tokens are forgeable by anyone who knows the default. | Refuse to start in production with the default secret; document key rotation. This is a deployment configuration gate, not a migration change. |
| G11 | **P1** | `script.py.mako` is empty. | `backend/migrations/script.py.mako` is 0 bytes (SHA-256 `E3B0C442...`); the installed Alembic generic template is 20 lines (SHA-256 `D3892078...`). | `alembic revision` cannot generate a usable revision file; future migrations may be empty or malformed. | Restore the Alembic 1.20.0 generic template or an explicitly reviewed project template. Verify with a throwaway revision generation in a temp directory, not by editing the graph. |
| G12 | **P1** | The current test suite does not cover governance, review, or audit. | `backend/tests` has no `test_governance_audit.py`, `test_exception_clustering.py`, `test_results_materiality.py`, or `test_exports_recipes.py`; current `test_alembic_migration_parity.py:66-67` hardcodes `PREVIOUS_HEAD="0004_verification_templates"` and `EXPECTED_HEAD="0005_verification_lineage"`; `test_postgres_migration_application.py:77` hardcodes the retired head. | A green current suite says nothing about governance/review/audit; the deployed suite used SQLite `create_all` and missed the missing review table. | Port and adapt the deployed tests; repoint the head constants; add migration-built tests; treat skips as not-run. |
| G13 | **P2** | Server defaults are not compared by the parity test. | `backend/migrations/env.py:42,62,81` sets `compare_type=True` but not `compare_server_default`; the parity test comment at `backend/tests/test_alembic_migration_parity.py:299-301` acknowledges this. | Drift such as the six governance defaults and `is_bulk_action` is invisible. | Add explicit default assertions via `information_schema.columns.column_default`; decide the ORM declarations. |
| G14 | **P2** | `0003_user_password.hashed_password` has an empty-string server default. | `backend/migrations/versions/0003_user_password.py:27` uses `server_default=""`. | A user row inserted without a password has an empty hash; login fails closed (`verify_password` returns False for empty), so this is not an auth bypass. It is still misleading schema metadata and a data-hygiene trap. | Document it; if removed, do it in a forward migration after confirming no rows rely on the default. Do not edit `0003` retroactively. |
| G15 | **P2** | `is_bulk_action` default is ambiguous. | Deployed ORM: client default `False`, no server default. Batch 22 §5.2 proposes server default `false`. | Raw inserts omitting the column fail without a server default; a server default not declared in the ORM creates drift. | Choose one contract and test it (T10). Recommended: server default `false` plus ORM `server_default=sa.false()`, or no server default and every writer sets the value. |
| G16 | **P2** | Review table permits `run_id` inconsistent with the discrepancy’s run. | No composite FK; service checks the discrepancy by `run_id` before insert. | Direct writes or bugs can create a review row attached to the wrong run. | Document as an application-enforced invariant; consider a composite FK only with an explicit contract change. |
| G17 | **P2** | Template uniqueness with `NULL` owners. | Unique `(owner_id, name)`; `owner_id` is nullable because of `ON DELETE SET NULL`. | After user deletion, duplicate names with `NULL` owner can exist. | Document; reads are owner-scoped and never see them. No partial unique index in this batch. |
| G18 | **P2** | `verification_templates` and `discrepancy_review_decisions` are new tables with no production history. | Production brief: both absent. | The first deploy creates them; there is no production data to preserve in them, but there is also no production evidence that the contracts fit real usage. | Treat as new schema; test on production-equivalent synthetic data; inventory before deploy to confirm absence. |

### 8.2 Security decisions required before implementation

The following are **entry gates**, not implementation details:

1. **Role assignment policy.** Public registration must not accept a privileged role. Decide whether registration always creates `MAKER` and an admin promotes users, or whether registration is disabled and users are provisioned administratively.
2. **Governance authority source.** Remove `X-User-Role` as an authority source. Decide whether role comes only from `users.role` or from a verified token claim that the server controls.
3. **Audit retention and deletion policy.** Decide whether audit and review rows survive project/run/discrepancy deletion. This determines the `0006` FK action and whether `0004`’s cascade is accepted.
4. **Review feature scope.** Decide whether option A should add `0006` at all. If review is not used in production, adding the table is harmless but expands surface; if it is used, `0006` is required and the length/cascade issues must be fixed first.
5. **Migration execution authority.** Decide who may run migrations and how the target is proven. No ambient `.env` execution.

---

## 9. T1–T14 coverage and isolated-test runbook

### 9.1 Existing coverage versus Batch 22

**[Repository + Deployed source]**

| ID | Batch 22 scenario | Existing coverage | Status | Required work |
| --- | --- | --- | --- | --- |
| T1 | Fresh database migration to a single head | `test_alembic_migration_parity.py::test_alembic_head_matches_orm_contract` upgrades a fresh schema, but to `0005_verification_lineage` and against the current subset ORM. | **GAP** | Repoint to `0006`; assert single head; assert all eight tables and exact inventory; use the selected ORM. |
| T2 | Production-equivalent `0001 → 0004` upgrade | The parity test builds `PREVIOUS_HEAD = 0004_verification_templates`, not governance; it seeds only base rows. | **GAP** | Build to `0004_enterprise_governance`, seed governance/audit data, upgrade `0005` then `0006`. |
| T3 | Production-scale data preservation | The parity test preserves a handful of legacy rows and checks six columns; no 33-run/25,654-discrepancy fingerprint. | **PARTIAL** | Add synthetic production-scale seed and per-table fingerprints before/after. |
| T4 | No duplicate lineage DDL | No offline-SQL test. | **GAP** | Generate offline SQL from `0004:0006`; assert no `ADD COLUMN` for the six lineage columns and no `DROP`. |
| T5 | Template lifecycle on canonical schema | `test_batch11_templates.py`, `test_batch13_template_workflow.py`, and `test_postgres_migration_application.py::test_template_lifecycle_and_uniqueness_on_migrated_schema` cover CRUD/uniqueness on the local graph. | **PARTIAL** | Run the same lifecycle on canonical `0005`; add owner-deletion `SET NULL` and cross-user 404 assertions. |
| T6 | Review single/bulk on canonical schema | Deployed `test_exception_clustering.py` covers bulk/API on SQLite `create_all`; no current test; no migration-built test. | **GAP** | Add migration-built single/bulk/cascade tests; assert every column and multiple decisions. |
| T7 | Governance sign-off on canonical schema | Deployed `test_governance_audit.py` covers proposal, separation of duties, approval/rejection on SQLite; no current test. | **GAP** | Port to current fixtures; add migration-built test; add header-spoofing and self-assignment regressions. |
| T8 | Audit chain append/verify/tamper | Deployed `test_governance_audit.py` covers hash chaining and tamper detection on SQLite; no current test. | **GAP** | Port; add migration-built test; add concurrency/sequence test or document single-writer limitation. |
| T9 | ORM queries and physical fields | No current test; current ORM has no physical mappings. | **GAP** | Add model round-trip tests for all eight tables, `_reason_code`/`_confidence_score`, fallback behavior, and relationships. |
| T10 | Raw-insert defaults | No test; defaults are not compared. | **GAP** | Raw SQL inserts omitting defaults; assert `is_bulk_action=false`, `role='MAKER'`, `sign_off_status='DRAFT'`, `currency='USD'`, `severity='medium'`, `resolution_status='unresolved'`. |
| T11 | Empty-table downgrade/upgrade round trip | Parity test round-trips the local graph; no canonical `0006→0004` test. | **PARTIAL** | Add canonical empty-table round trip; assert base/governance rows survive and lineage columns are not dropped. |
| T12 | Non-empty rollback policy | No test. | **GAP** | Document destructive outcome; assert the operational policy is export/forward-fix, not downgrade. |
| T13 | Local canonical rebuild | No test; local DB is at the retired branch. | **GAP** | Build a throwaway local schema `0001→0006`; compare to the migration-built test schema; no stamp. |
| T14 | Render-like startup compatibility | No test; no Render manifest; app startup does not migrate. | **GAP** | Start the selected app version against the canonical schema; assert `/health`, `/health/db`, and the selected feature routes. |

### 9.2 Missing tests

At minimum, add a dedicated `backend/tests/test_postgres_reconciliation_design.py` covering:

- canonical revision graph: one head, linear parents, no duplicate revision IDs, no `0005_verification_lineage`;
- exact `0005`/`0006` object inventory: columns, types, nullability, defaults, PKs, FKs, unique constraints, indexes;
- production-equivalent upgrade and per-table fingerprints at 33 runs / 25,654 discrepancies;
- offline SQL from `0004` to `0006`: two `CREATE TABLE`s, no lineage `ADD COLUMN`, no `DROP`;
- template lifecycle on the canonical schema, including owner deletion and cross-user 404;
- review single/bulk on the canonical schema, including cascade behavior and multiple decisions;
- governance sign-off and audit-chain behavior on the canonical schema;
- physical reason/confidence writes and NULL fallback, including `NULL_KEY`;
- raw-insert defaults;
- empty-table and non-empty downgrade behavior;
- local rebuild comparison;
- application startup smoke test;
- security regressions for G1, G2, G5, and G8;
- a test that the migration path refuses to fall back to the application database when test mode is enabled.

Do not add these tests by extending the SQLite `create_all` fixture. They must run against the Alembic-built PostgreSQL schema.

### 9.3 Isolated-test safety contract

**[Proposal]**

The only authorized migration test target is a disposable PostgreSQL database on loopback, dedicated to testing:

- `VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS=1` is the explicit opt-in.
- `VERIFYGRID_TEST_DATABASE_URL` is mandatory and must pass `tests/pg_test_target.validate_test_database_url`.
- The guard must reject the application database name, a remote host, a non-loopback resolved address, and a role that is not named for testing.
- Alembic must receive an already-validated SQLAlchemy connection through `config.attributes["connection"]`; it must not fall back to `settings.database_url`.
- Each test creates a unique schema named `verifygrid_it_<hex>`, sets `search_path` to it, and drops it in `finally`.
- No test uses `Base.metadata.create_all` to build the schema under test.
- No test contacts Neon, Render, Cloudflare, or production.
- No test reads a production secret. `DATABASE_URL` is set explicitly to a loopback placeholder for the guard’s comparison; `.env` must not be the source of the target.

The current `pg_test_target` guard was statically validated in this audit: a loopback `verifygrid_test` database/role is accepted; the application database, a remote host, and a non-test role are rejected. That is a pure function check; no connection was opened.

### 9.4 Prerequisites before the runbook is executable

**[Proposal]**

1. The canonical graph is committed and single-headed; `0005_verification_lineage` and `0004_verification_templates` are retired from `backend/migrations/versions/` and archived outside it.
2. The recovered `0004` is in the repository with SHA-256 `44D31AE9...` verified.
3. `backend/migrations/env.py`’s explicit-connection path is committed, and the test-mode fallback guard exists.
4. `backend/migrations/script.py.mako` is restored if any revision generation is planned.
5. The parity/application tests are repointed to `0006` and the selected ORM.
6. The test database is a local disposable instance, not a shared development database.
7. The operator has confirmed no production URL or credential is present in the shell environment.

### 9.5 Runbook (future; not executed in Batch 23)

**[Proposal — illustrative commands only]**

Create a dedicated local role and database once, using a local PostgreSQL administrator account. The role and database names must contain `test` to satisfy the guard.

```powershell
# Local PostgreSQL only. Replace the password locally; never commit it.
$env:PGPASSWORD = "<local-admin-password>"
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "CREATE ROLE verifygrid_test LOGIN PASSWORD '<local-test-password>';"
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "CREATE DATABASE verifygrid_test OWNER verifygrid_test;"
```

Set an explicit, non-production comparison URL and the test target:

```powershell
# The application comparison URL is loopback and is NOT the test database.
$env:DATABASE_URL = "postgresql+psycopg://verifygrid_app:placeholder@127.0.0.1:5432/verifygrid"
$env:VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS = "1"
$env:VERIFYGRID_TEST_DATABASE_URL = "postgresql+psycopg://verifygrid_test:<local-test-password>@127.0.0.1:5432/verifygrid_test"
```

Run from the backend directory, in this order:

```powershell
cd C:\Users\shaha\verifygrid\backend

# 1. Guard behavior only; no database connection.
python -m pytest tests/test_postgres_target_guard.py -q

# 2. Canonical graph and ORM parity.
python -m pytest tests/test_alembic_migration_parity.py -q

# 3. Application behavior on the Alembic-built schema.
python -m pytest tests/test_postgres_migration_application.py -q

# 4. New reconciliation, preservation, review, governance, audit, and security tests.
python -m pytest tests/test_postgres_reconciliation_design.py -q
```

Do **not** run `alembic upgrade`, `alembic downgrade`, `alembic stamp`, or `alembic revision` as part of this runbook. The tests must invoke Alembic programmatically with the validated connection. If a test reports `skipped`, treat it as **not run**, not as passing.

Verify the target before and after:

```sql
-- Inside the test session, the fixture asserts these values.
SELECT current_database(), current_user, host(inet_server_addr());

-- After the suite, no test schema should remain.
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name LIKE 'verifygrid_it_%';
```

Optional teardown, only after every test has finished and the database is confirmed disposable:

```powershell
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "DROP DATABASE verifygrid_test WITH (FORCE);"
```

### 9.6 Abort conditions

Stop immediately if any of the following occurs:

- the guard rejects the test URL, the role, or the host;
- the connected database or user differs from the validated target;
- `inet_server_addr()` is not loopback;
- the test database already contains an unexpected schema or `alembic_version`;
- a test attempts to use `settings.database_url` for DDL;
- a production hostname, Neon endpoint, Render hostname, or non-loopback address appears in any URL;
- a migration emits `ADD COLUMN` for any of the six lineage columns, or a `DROP`;
- a test expects a skipped result to count as success.

### 9.7 What the tests cannot prove

Even a full green run cannot prove:

- that production data values and permissions match the synthetic seed;
- that Render’s dashboard has no hidden pre-deploy command or auto-deploy race;
- that the selected application version is the right product decision;
- that the audit chain is currently valid in production;
- that concurrent production writes will not contend with DDL locks;
- that the reconstructed `0006` matches a lost historical artifact;
- that the production database has no unknown object that collides with `0005` or `0006`.

Those remain production gates in section 12.

---

## 10. Local-history retirement

### 10.1 Current local state

**[Repository + Inference]**

The local development database is not queryable under this batch’s rules, so its exact revision is **[Unverified]**. The evidence bounds it:

- `0004_verification_templates.py`’s docstring records that Batch 12 applied it to the local development database (`verifygrid` @ localhost) from `0003_user_password` to head.
- `0005_verification_lineage.py` exists in the working tree and may have been applied afterward.
- The local graph therefore ends at either `0004_verification_templates` or `0005_verification_lineage`. Both states lack the governance revision.
- The local `verification_templates` table exists in either state, because `0004_verification_templates` created it.

The exact revision must be read in a future authorized batch with a read-only `SELECT version_num FROM alembic_version;`. This audit did not connect to the database.

### 10.2 Why the local database cannot be stamped or upgraded

**[Repository + Inference]**

| Local state | `alembic upgrade head` against canonical graph | `stamp` shortcut | Result |
| --- | --- | --- | --- |
| At `0004_verification_templates` | Fails: the revision is not in the canonical ancestry; if the file is removed, Alembic cannot locate the current revision. | Stamp to `0004_enterprise_governance` claims 33 columns and `audit_events` exist when they do not. | False history; later `0005` collides with the existing template table; governance queries fail. |
| At `0005_verification_lineage` | Fails for the same reason; the revision is retired. | Stamp to `0006` skips all canonical DDL. | Severe false history; schema remains without governance, templates are already present, and review is absent. |
| Any state | Applying canonical `0005` attempts `CREATE TABLE verification_templates`, which already exists. | Any stamp is a lie about executed DDL. | Unusable. |

Stamping is prohibited. Alembic’s version table records what was executed; it is not a repair tool. The local database must be **rebuilt** or **exported, rebuilt, and reloaded**.

### 10.3 Disposition options

**[Proposal]**

| Option | When to use | Procedure | Risks |
| --- | --- | --- | --- |
| **L1 — Disposable rebuild** | Local data has no lasting value; it is development/test data. | Stop the backend; record row counts for reference; drop and recreate the local database; run the canonical graph to `0006` in a future authorized batch; recreate the development user. | Local data loss. Must be an explicit owner decision. No production impact. |
| **L2 — Export, rebuild, reload** | Local templates, projects, or verification history must be preserved. | Read-only export of application tables (not `alembic_version`); rebuild the database from the canonical graph; reload in FK order; verify counts and fingerprints; run application smoke tests. | Export/reload bugs, timezone/JSON fidelity, missed columns. Requires a dry run on a throwaway database. |
| **L3 — Stamp** | Never. | — | False history and schema/DL data mismatch. **Rejected.** |

**Recommendation:** L1 if the owner confirms the local data is disposable; otherwise L2 with a rehearsed export on a throwaway schema. Do not choose L1 silently.

### 10.4 Export/reload constraints for L2

**[Proposal]**

- Export only application tables: `users`, `projects`, `source_files`, `verification_runs`, `verification_discrepancies`, `verification_templates`. The local database has no `audit_events` or `discrepancy_review_decisions`.
- Do **not** export `alembic_version`.
- Reload in dependency order: `users` → `projects` → `source_files` → `verification_runs` → `verification_discrepancies` → `verification_templates`. `verification_templates.owner_id` depends on `users`.
- Preserve UUID primary keys.
- Export timestamps in UTC; the target columns are `timestamptz`.
- The canonical schema adds `users.role` (default `MAKER`), nine sign-off fields (default `DRAFT`/NULL), and seventeen materiality/clustering/review fields (NULL/defaults). The reload must not invent non-null governance values.
- The six lineage columns already exist locally and match the canonical types; preserve their JSON values exactly.
- After reload, compare per-table row counts and a deterministic fingerprint (for example `md5(string_agg(row_to_json(t)::text, '' ORDER BY id))`) against the export.
- Run the template and verification smoke tests against the rebuilt local database.
- Never copy a production dump into the local database; this is a local-only operation.

### 10.5 Retirement mechanics

**[Proposal]**

1. Archive the two local revision files outside `backend/migrations/versions/` before removing them. They are untracked, so deletion without an archive loses their content. Record their SHA-256 values in the provenance note.
2. Remove `0004_verification_templates.py` and `0005_verification_lineage.py` from `backend/migrations/versions/`. Do not rename them into the canonical graph.
3. Add the recovered `0004_enterprise_governance_and_materiality.py` byte-identically; verify SHA-256 `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB`.
4. Add `0005_verification_templates.py` and `0006_discrepancy_review_decisions.py` with the contracts in sections 4 and 5.
5. Run a static graph check: exactly one head, linear parents, no duplicate revision IDs.
6. Commit the canonical graph, the archived files’ provenance record, and the retirement in one reviewed change. Do not leave migration files untracked.
7. Only after the commit, run the isolated tests and the local rebuild. Do not run `alembic upgrade head` against any database before the graph is committed.

### 10.6 Local verification after rebuild

**[Proposal]**

```sql
SELECT version_num FROM alembic_version;  -- expected exactly one row: 0006_discrepancy_review_decisions

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'users','projects','source_files','verification_runs',
    'verification_discrepancies','verification_templates',
    'audit_events','discrepancy_review_decisions'
  )
ORDER BY table_name;  -- expected eight rows
```

Then run the application’s non-database health check and a read-only template/project smoke test. Do not create review decisions or sign-offs in a local smoke test unless the database is disposable.

---

## 11. Expected file manifest

### 11.1 Migration and history files

**[Proposal]**

| File | Action | Exact requirement |
| --- | --- | --- |
| `backend/migrations/versions/0004_enterprise_governance_and_materiality.py` | **Add** | Byte-identical recovered file; revision `0004_enterprise_governance`; parent `0003_user_password`; SHA-256 `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB`. Do not edit operations. |
| `backend/migrations/versions/0005_verification_templates.py` | **Add** | Revision `0005_verification_templates`; parent `0004_enterprise_governance`; 10-column contract in section 4. |
| `backend/migrations/versions/0006_discrepancy_review_decisions.py` | **Add** | Revision `0006_discrepancy_review_decisions`; parent `0005_verification_templates`; 12-column reconstructed contract in section 5. |
| `backend/migrations/versions/0004_verification_templates.py` | **Retire/archive** | Remove from the active graph; preserve an archived copy and hash. |
| `backend/migrations/versions/0005_verification_lineage.py` | **Retire/archive** | Remove from the active graph; do not replay the six lineage columns. |
| `backend/migrations/script.py.mako` | **Repair** | Replace the 0-byte file with the Alembic 1.20.0 generic template or a reviewed equivalent. |
| `backend/migrations/env.py` | **Commit and harden** | Keep the explicit-connection path; add a fail-closed guard against the application-URL fallback in test mode. |
| `docs/audits/` provenance note | **Add** | Record source commit `58a0e5c...`, source path, SHA-256, retrieval date, and the archived local revision hashes. Do not edit Batch 18–22. |

### 11.2 Application files for option B/D

**[Proposal]**

| Group | Files |
| --- | --- |
| Models | `backend/app/models/user.py` (role); `backend/app/models/verification_run.py` (9 sign-off + 17 governance fields, physical reason/confidence, review class/relationship); `backend/app/models/audit_log.py` (replace 0 bytes); `backend/app/models/review.py` (remove or re-export); `backend/app/models/__init__.py` (exports). |
| Schemas | `backend/app/schemas/review.py` (replace 0 bytes, add length bounds); add `audit.py`, `governance.py`; `auth.py` (role policy); `result.py` (materiality/side-by-side); optional `recipe.py`. |
| Services | `backend/app/services/review_service.py` (replace 0 bytes); `backend/app/services/audit_service.py` (replace 0 bytes); add `clustering_service.py`, `materiality_engine.py`, `governance_service.py`; optional `recipe_service.py`; merge `verification_engine.py`, `project_service.py`, `export_service.py`. |
| API | `backend/app/api/v1/endpoints/audit.py` (replace 0 bytes); add `review.py` or replace `reviews.py`; add `governance.py`; optional `recipes.py`; `router.py`; `auth.py`; merge `verification.py`, `exports.py`. |
| Tests | Update `backend/tests/test_alembic_migration_parity.py`, `backend/tests/test_postgres_migration_application.py`; add `backend/tests/test_postgres_reconciliation_design.py`; port deployed `test_governance_audit.py`, `test_exception_clustering.py`, `test_results_materiality.py`, `test_exports_recipes.py`; add security and isolation regressions. |
| Configuration | No `render.yaml` required for the migration. Do not add a startup migration hook. The JWT secret and migration target are deployment gates, not files to hard-code. |

### 11.3 Explicitly unchanged

- `backend/app/main.py`: no startup migration.
- `backend/app/db/session.py`: no `create_all`, no migration execution.
- `backend/alembic.ini`: no production URL, no credential.
- No `backend/.env` edit, no Render/Cloudflare configuration edit, no production secret.
- No existing Batch 18–22 report edit.
- No application code, model, migration, or test change in Batch 23 itself.

---

## 12. Deployment gates and current status

### 12.1 Entry gates

**[Proposal + Repository]**

| # | Gate | Status | Evidence |
| --- | --- | --- | --- |
| E1 | Written application decision: option A vs B/D. | **OPEN** | No decision file or approval exists. |
| E2 | Canonical graph approved (`0004 → 0005 → 0006`). | **NOT MET** | Design only; the files do not exist; the working tree has two heads. |
| E3 | Recovered `0004_enterprise_governance` preserved with provenance. | **PARTIAL** | Hash verified in the preserved tree; not in the repository, not in local Git. |
| E4 | Retired local revisions removed from the graph and deployment path. | **NOT MET** | Both are still in `backend/migrations/versions/` and untracked. |
| E5 | Production read-only inventory. | **NOT MET** | Production/Neon not contacted. |
| E6 | Backup/PITR restore tested. | **NOT MET** | No backup evidence. |
| E7 | Local development data disposition decided. | **OPEN** | Owner decision; section 10. |
| E8 | Render configuration and auto-deploy known. | **NOT MET** | Dashboard not inspected; no manifest. |
| E9 | Review-feature scope decided. | **OPEN** | Whether `0006` is needed for option A depends on this. |
| E10 | Security review for role assignment/header authority. | **OPEN** | G1/G2 are unresolved. |
| E11 | Two-person ownership assigned. | **OPEN** | No named executor/reviewer. |

### 12.2 Implementation gates

| # | Gate | Status | Evidence |
| --- | --- | --- | --- |
| I1 | `script.py.mako` repaired; generated revisions valid. | **FAIL** | 0 bytes. |
| I2 | Canonical graph has one head and is linear. | **DESIGN ONLY** | Static simulation passes; the repository does not. |
| I3 | No duplicate six-column DDL in graph or offline SQL. | **DESIGN ONLY** | The duplicate is identified; no offline SQL test has run. |
| I4 | `0005` and `0006` reviewed as separate revisions. | **CONTRACT VERIFIED; FILES ABSENT** | Sections 4–5. |
| I5 | Template and review DDL match the approved contracts. | **PARTIAL** | `0005` exact; `0006` inferred from the ORM, not recovered. |
| I6 | ORM target updated or explicitly scoped; parity test matches it. | **OPEN** | Option A/B/D unresolved. |
| I7 | Isolated PostgreSQL T1–T14 pass. | **NOT RUN** | No test executed. |
| I8 | Production-equivalent upgrade preserves 33 runs / 25,654 discrepancies. | **NOT RUN** | No test executed. |
| I9 | Template CRUD/apply/uniqueness/scoping pass on canonical schema. | **PARTIAL** | Unit tests and local-graph migration test exist; canonical schema not built. |
| I10 | Review single/bulk/cascade pass on canonical schema. | **NOT RUN** | No current test; deployed SQLite test only. |
| I11 | Governance sign-off and audit chain pass on canonical schema. | **NOT RUN** | Deployed SQLite tests only. |
| I12 | No untracked migration artifacts remain. | **FAIL** | Old files untracked; canonical files absent. |
| I13 | No application startup migration hook. | **PASS** | No hook found. |
| I14 | Security regressions G1/G2/G5/G8 fixed. | **NOT DONE** | Findings only. |

### 12.3 Production gates

| # | Gate | Status |
| --- | --- | --- |
| P1 | Neon-branch or isolated-restore rehearsal passed. | **NOT MET** |
| P2 | Rehearsal row counts/fingerprints match production preflight. | **NOT MET** |
| P3 | Audit chain verifies on rehearsal, or pre-existing failure documented. | **NOT MET** |
| P4 | Template/review smoke tests pass on rehearsal. | **NOT MET** |
| P5 | Rollback/restore plan rehearsed. | **NOT MET** |
| P6 | Production window approved; no conflicting deploy. | **NOT MET** |
| P7 | Written authorization from database owner and engineering lead. | **NOT MET** |
| P8 | Executor and reviewer present. | **NOT MET** |
| P9 | Production target identity verified. | **NOT MET** |
| P10 | Render auto-deploy disabled or coordinated. | **NOT MET** |

### 12.4 Current no-go triggers

The following Batch 22 no-go triggers are true today:

- the canonical graph still has two heads;
- the recovered `0004` is not in the repository;
- the application decision is unresolved;
- the selected application (current branch) lacks governance and would replace the deployed governance app if option C were chosen;
- no backup/PITR, rehearsal, or production authorization exists;
- no isolated test has run;
- the security gaps G1/G2 are unresolved;
- the migration files are untracked.

**Verdict: NO-GO for production migration and deployment.**

### 12.5 Future deployment sequence

**[Proposal — not executed]**

Do not start this sequence until E1–E11 are satisfied.

| Phase | Step | Verification | Abort condition |
| --- | --- | --- | --- |
| 0 | Freeze schema/application changes; record the production revision, live commit, row counts, and audit-chain status read-only. | One `alembic_version` row at `0004_enterprise_governance`; 33 runs; 25,654 discrepancies. | Any mismatch. |
| 0 | Confirm backup/PITR restore to a separate branch/database. | Restore timestamp and smoke query. | No verified restore. |
| 0 | Confirm Render build/start/pre-deploy/auto-deploy settings. | Dashboard evidence; auto-deploy controlled. | Cannot control auto-deploy. |
| 1 | Rehearse on a Neon branch or isolated restore. Apply `0005`, verify, apply `0006`, verify, start the selected app, smoke. | All T1–T14 and section 12.3 checks. | Any failure. |
| 1 | Review SQL, inventory diff, test output, rollback, and security fixes. | Two-person approval. | Missing approval or unresolved P0. |
| 2 | Apply `0005_verification_templates` from an explicit one-off job. | Revision `0005`; table/index/FK exist; row counts unchanged. | Lock timeout, mismatch, unexpected object, count change. |
| 2 | Apply `0006_discrepancy_review_decisions`. | Revision `0006`; table/indexes/FKs exist; row counts unchanged. | Same. |
| 2 | Deploy option A (no app change) or the B/D build. | App starts; `/health` and `/health/db` pass; feature smoke passes. | Startup/smoke failure. |
| 2 | Post-deploy verification and unfreeze. | Section 10.5 of Batch 22; final revision and counts recorded. | Any unexpected result. |

Command shape, only after G3 is fixed and the target is explicitly verified:

```powershell
# Authorized operator shell. The URL must come from the secret manager for this process only.
$env:DATABASE_URL = "<explicit-production-connection-string>"
$env:PGOPTIONS = "-c lock_timeout=5000"
cd backend

alembic current
alembic upgrade 0005_verification_templates
alembic current
alembic upgrade 0006_discrepancy_review_decisions
alembic current
```

Do not use `alembic upgrade head` on production until the canonical graph is committed and the retired branch is gone. Do not paste credentials into this report or logs.

### 12.6 Rollback rules

- **Application failure before any schema change:** roll back the application; no schema action.
- **`0005` failure:** PostgreSQL DDL is transactional; investigate and retry only after the cause is known. Do not stamp.
- **`0005` success, `0006` failure:** keep `0005`; it is additive and the old app ignores it. Fix forward.
- **`0006` success, application failure:** roll back the application; keep both new tables. Do not drop non-empty tables.
- **Template table empty and an approved undo is required:** targeted drop only after verifying zero rows and a fresh backup.
- **Review table non-empty:** treat as audit evidence; forward-fix or restore, never drop.
- **Governance data damaged:** restore to a separate branch; never downgrade `0004` on production.
- Do not use `Base.metadata.drop_all`/`create_all` against production; do not delete `alembic_version` rows.

---

## 13. Final verdict and first authorized step

### 13.1 Verdict

**PASS — Batch 23 audit scope only.**

Batch 23 independently validated the canonical graph design, the `0005` and `0006` contracts, the recovered `0004` inventory, the current/deployed ORM gap, the local-history retirement requirement, the T1–T14 plan, and the deployment gates. It changed only this report.

**NO-GO for implementation as a whole.** Batch 22’s entry gates are not satisfied. The graph is a design, the repository still has two heads, the recovered governance revision is outside Git, the local revisions are untracked, the revision template is empty, the application decision is unwritten, the security issues are unresolved, and no production inventory, backup/PITR, rehearsal, Render review, or two-person authorization exists.

**The migration-graph design is implementable.** The intended chain is linear and single-headed; `0005` matches the current template ORM exactly; `0006` is consistent with the deployed review ORM; `0004`’s object inventory is exact and its hash is verified. Those are design findings, not authorization.

**A migration-only slice is not authorized now.** It requires an explicit written amendment to the entry gates, an application-version decision, and a scope limited to the canonical graph, tests, and local retirement. Without that amendment, implementing even the schema would violate Batch 22’s gates.

### 13.2 Remaining blockers

**P0 — must be resolved before implementation authorization**

1. **Written application decision (A vs B/D).** No option is approved; option C is rejected.
2. **Canonical graph not committed.** Two heads; `0004` outside the repository; local revisions untracked.
3. **Role security.** Public registration can self-assign `ADMIN` in the deployed code; governance trusts `X-User-Role`.
4. **Migration execution safety.** `env.py` can fall back to `settings.database_url`; tests depend on an uncommitted explicit-connection path; there is no CLI target guard.
5. **Production evidence absent.** No read-only inventory, backup/PITR restore, Neon-branch rehearsal, Render configuration review, or two-person authorization.

**P1 — must be resolved before production authorization**

6. `script.py.mako` is 0 bytes.
7. Local database disposition is undecided.
8. Review/audit retention conflicts with cascade FKs.
9. Review/assignment/role/cluster-name lengths can overflow.
10. Audit sequence allocation is unsynchronized.
11. Physical `reason_code`/`confidence_score` merge and `NULL_KEY` semantics are unresolved.
12. T1–T14 and canonical-schema tests have not run.
13. Review-feature scope is undecided.
14. Server defaults are not compared and are not aligned with the ORM.

### 13.3 First authorized step

**The first authorized step is a decision, not code.**

Write a short decision memo that:

1. selects **option A** (keep `58a0e5c`, schema-only, no templates) or **option B/D** (combined application);
2. explicitly amends Batch 22’s entry gates to authorize an **offline-only migration-graph implementation slice**;
3. names the security fixes required before any governance route is exposed (G1, G2);
4. chooses the local database disposition (L1 or L2);
5. names the migration executor and reviewer.

Only after that memo is approved should a future implementation batch:

1. copy the recovered `0004` byte-identically and verify its hash;
2. add `0005` and `0006`;
3. archive and remove the local `0004_verification_templates` and `0005_verification_lineage`;
4. repair `script.py.mako`;
5. commit `env.py` with a fail-closed test guard;
6. update the tests to the canonical head and selected ORM;
7. run T1–T14 on an isolated disposable PostgreSQL target.

No production or Neon connection is authorized by this report.

### 13.4 What would change the verdict

- **GO for implementation** requires: E1–E4, E7, E9, E10, and E11 resolved or explicitly amended; the canonical graph and tests planned; and the local disposition chosen. E5, E6, E8 and production gates can remain open until the production authorization phase, but the implementation slice must not touch production.
- **GO for production** requires all E1–E11, I1–I14, and P1–P10, plus a clean rehearsal and the security fixes. No partial green suite is sufficient.

---

## 14. Commands executed and preservation record

### 14.1 Commands executed

**[Repository — read-only]**

The following command shapes were executed. Repeated directory listings, file reads, and greps are grouped. Angle-bracket values such as `<file>` and ellipses such as `...` are placeholders for values enumerated elsewhere in this report; no shell command contained a literal placeholder. No command wrote to a database, ran Alembic, ran a test suite, changed Git state, or changed an environment file.

```powershell
# Identity and working-tree preservation.
git rev-parse HEAD
git branch --show-current
git status --porcelain=v1 --untracked-files=all
git status --porcelain=v1
git status --porcelain=v1 -- backend/app/services/audit_service.py backend/app/services/review_service.py backend/app/schemas/review.py backend/app/api/v1/endpoints/audit.py backend/app/api/v1/endpoints/reviews.py
git show-ref --head
git cat-file -t 58a0e5c243978480c4ca817c537c700ed6b20516
git rev-parse refs/remotes/origin/main
git log -1 --format='%H %cI %s' refs/remotes/origin/main
git log -1 --format='%H %cI %s'
git branch -a --contains 58a0e5c243978480c4ca817c537c700ed6b20516
Test-Path docs\audits\Batch23_Implementation_Readiness_Audit.md

# Working-tree baseline snapshot outside the repository.
git status --porcelain=v1 --untracked-files=all | Out-File -Encoding utf8 "$env:LOCALAPPDATA\Temp\opencode\batch23_status_before.txt"
git show-ref --head | Out-File -Encoding utf8 "$env:LOCALAPPDATA\Temp\opencode\batch23_refs_before.txt"

# Directory inventories and file sizes.
Get-ChildItem docs\audits -File | Select-Object Name,Length,LastWriteTime
Get-ChildItem backend\migrations\versions -File | Select-Object Name,Length,LastWriteTime
Get-ChildItem backend\app\services -File | Select-Object Name,Length
Get-ChildItem backend\app\schemas -File | Select-Object Name,Length
Get-ChildItem backend\app\models -File | Select-Object Name,Length
Get-ChildItem backend\app\api\v1\endpoints -File | Select-Object Name,Length
Get-ChildItem backend\tests -File -Filter '*.py' | Select-Object Name,Length
Get-Item docs\audits\Batch23_Implementation_Readiness_Audit.md

# Source, migration, schema, service, endpoint, and test inspection.
Get-Content backend\migrations\versions\0001_initial_tables.py
Get-Content backend\migrations\versions\0002_verification_runs.py
Get-Content backend\migrations\versions\0003_user_password.py
Get-Content backend\migrations\versions\0004_verification_templates.py
Get-Content backend\migrations\versions\0005_verification_lineage.py
Get-Content backend\migrations\env.py
Get-Content backend\migrations\script.py.mako
Get-Content backend\alembic.ini
Get-Content backend\app\models\__init__.py
Get-Content backend\app\models\user.py
Get-Content backend\app\models\verification_template.py
Get-Content backend\app\schemas\auth.py
Get-Content backend\app\schemas\template.py
Get-Content backend\app\services\template_service.py
Get-Content backend\app\core\config.py
Get-Content backend\app\core\security.py
Get-Content backend\tests\conftest.py
Get-Content backend\tests\pg_test_target.py
Get-Content backend\tests\test_alembic_migration_parity.py
Get-Content backend\tests\test_postgres_migration_application.py
Get-Content backend\app\api\v1\router.py

# Targeted symbol/line searches.
Select-String -Path backend\migrations\versions\0004_verification_templates.py,backend\migrations\versions\0005_verification_lineage.py -Pattern 'revision|down_revision|sa.Column\("(sources|source_row_indices|source_records|child_records|aggregated_amount|expected_amount)"'
Select-String -Path backend\migrations\env.py -Pattern 'compare_|context.configure|target_metadata|include_'
Select-String -Path backend\tests\test_alembic_migration_parity.py -Pattern 'PREVIOUS_HEAD|EXPECTED_HEAD|SIX_COLUMNS|compare_server_default|compare_metadata'
Select-String -Path backend\tests\test_postgres_migration_application.py -Pattern 'EXPECTED_HEAD|PREVIOUS_HEAD|compare_metadata|create_all'
Select-String -Path backend\app\services\verification_engine.py -Pattern 'sources\s*=|VerificationRun\(|reason_code|confidence_score'
Select-String -Path backend\app\api\v1\endpoints\templates.py -Pattern '@router|def |current_user|404|409|status_code'

# Current ORM metadata, no database connection.
python -c "import sys; sys.path.insert(0, r'C:\Users\shaha\verifygrid\backend'); import app.models; from app.db.base import Base; print('\n'.join(f'{t.name}: {len(t.columns)} cols, {len(t.indexes)} idx, {len(t.constraints)} constraints' for t in Base.metadata.sorted_tables))"
python -c "import sys; sys.path.insert(0, r'C:\Users\shaha\verifygrid\backend'); import app.models; from app.db.base import Base; t=Base.metadata.tables['verification_templates']; ..."

# Preserved deployed ORM metadata, no database connection.
$env:PYTHONPATH="$env:LOCALAPPDATA\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend"
python -c "import app.models; from app.db.base import Base; print('\n'.join(f'{t.name}: {len(t.columns)} cols, {len(t.indexes)} idx, {len(t.constraints)} constraints' for t in Base.metadata.sorted_tables))"
python -c "import app.models; from app.db.base import Base; t=Base.metadata.tables['discrepancy_review_decisions']; ..."
python -c "import app.models; from app.db.base import Base; t=Base.metadata.tables['audit_events']; ..."
python -c "import app.models; from app.db.base import Base; t=Base.metadata.tables['verification_runs']; ..."
python -c "import app.models; from app.db.base import Base; t=Base.metadata.tables['verification_discrepancies']; ..."

# Pure-function target-guard check (no connection, no settings import).
python -c "import sys; sys.path.insert(0, r'C:\Users\shaha\verifygrid\backend'); from tests.pg_test_target import validate_test_database_url; ..."

# Recovered governance migration and deployed source reads (via the read tool).
Get-Content "$env:LOCALAPPDATA\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\migrations\versions\0004_enterprise_governance_and_materiality.py"
Get-Content "$env:LOCALAPPDATA\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\app\models\verification_run.py"
Get-Content "$env:LOCALAPPDATA\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\app\models\audit_log.py"
Get-Content "$env:LOCALAPPDATA\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\app\services\review_service.py"
Get-Content "$env:LOCALAPPDATA\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\app\services\governance_service.py"
Get-Content "$env:LOCALAPPDATA\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\app\services\audit_service.py"
Get-Content "$env:LOCALAPPDATA\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\app\services\clustering_service.py"
Get-Content "$env:LOCALAPPDATA\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\app\schemas\review.py"
Get-Content "$env:LOCALAPPDATA\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\app\api\v1\endpoints\review.py"

# Hash verification (repeated for every file listed in section 14.3).
foreach ($f in $files) { Get-FileHash -Algorithm SHA256 $f }
Get-FileHash -Algorithm SHA256 "$env:LOCALAPPDATA\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\migrations\versions\0004_enterprise_governance_and_materiality.py"
$generic = "C:\Users\shaha\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\site-packages\alembic\templates\generic\script.py.mako"
Get-FileHash -Algorithm SHA256 $generic
(Get-Content $generic | Measure-Object -Line).Lines

# Python/tool versions.
python --version
python -c "import alembic, sqlalchemy, pydantic; print('alembic', alembic.__version__); print('sqlalchemy', sqlalchemy.__version__); print('pydantic', pydantic.__version__)"
```

The `python -c` metadata commands imported only ORM modules and `Base.metadata`; they opened no engine and read no `.env`. `PYTHONPATH` was set only inside the transient PowerShell process used to import the preserved deployed tree; it was not persisted.

### 14.2 Commands deliberately not executed

- No `alembic upgrade`, `downgrade`, `stamp`, `revision`, `history`, `current`, or `heads`.
- No `pytest`, `python -m pytest`, or other test runner.
- No `psql`, `pg_dump`, `pg_restore`, `createdb`, or database client.
- No Neon, Render, Cloudflare, GitHub, or cloud API call.
- No `git add`, `commit`, `push`, `fetch`, `checkout`, `branch`, `tag`, `stash`, `reset`, `clean`, `merge`, `rebase`, or worktree change.
- No `.env` read; no persistent environment-variable change; no `DATABASE_URL` set.
- No application code, ORM model, migration, test, configuration, environment file, or prior audit report edit.
- No production or local database connection.

### 14.3 Critical hashes after the report

**[Repository]**

These values were computed after the report content was written. For files also recorded in Batch 22 §13.3, the values are identical. No pre-existing file appears as modified in `git status`.

| File | SHA-256 |
| --- | --- |
| `docs/audits/Batch18_Migration_History_Divergence_Audit.md` | `1434845A691EB60C9FD34B8C7EACBA5079A7CE667E8DDCB80D4B2578AE037655` |
| `docs/audits/Batch19_Migration_Reconciliation_Preparation.md` | `DDA7AB82B5D799D9BC1EF1A12D23E392F507DCE801275BF4A89B8D637DCE856F` |
| `docs/audits/Batch20_Governance_Migration_Recovery_Audit.md` | `0F4D4E58536CB342D34F4EA2D8C0229F970A2F7844C037F9A7230DF1069F3A3D` |
| `docs/audits/Batch21_Production_Schema_Lineage_Audit.md` | `DF6A89BCC980C029173F9C6A51F66AEFC96826B041C8215CD4956DAE74CA8E8B` |
| `docs/audits/Batch22_Migration_and_ORM_Reconciliation_Design.md` | `70A7D43DD8418E12C7C2999379F8EA5A11ADBC5E77D73F0AD0B94AE3F65D8EA1` |
| `backend/migrations/versions/0001_initial_tables.py` | `F3E045B29E52A132947E6ED156BA57995FD45B75EAA2C7D6289901C5AFD569A0` |
| `backend/migrations/versions/0002_verification_runs.py` | `44A9CD93E9A1260C7C61E3029FD6F884B5B27523FDCE25D966C986748AD78B2E` |
| `backend/migrations/versions/0003_user_password.py` | `6F256919E0E2537468335FF0A6C253E80BC513E3DFB6D414F9564C10083902E6` |
| `backend/migrations/versions/0004_verification_templates.py` | `CBE7E536573D06D49E4EB2F8EFB7BD26A0D3CCA786F01EA80AE7C8E7CA74E227` |
| `backend/migrations/versions/0005_verification_lineage.py` | `645BE701DFF05FDF6D263AF678CB17E77D818CE64C00A8B9F3AF96E46E585713` |
| `backend/migrations/env.py` | `F1A56CC8A201936615DE14F7730E32265C3132AF1372EF382F485207E67F056B` |
| `backend/migrations/script.py.mako` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` (empty) |
| `backend/alembic.ini` | `BDD54D7DE18AC7121F7AF8DC7AB1EA79660143EAA36886BFBD9BC93DBDD2E203` |
| `backend/app/models/user.py` | `3D34B163C414A375688250D9FA4283FB616EC8DE3E5069611B138B0A8847AED0` |
| `backend/app/models/verification_run.py` | `B59FA3BF64072F81ED51ED8AA8BAE49150818E58890E409A02792A38D16E02BC` |
| `backend/app/models/verification_template.py` | `4C07D82DE767AB3F6F80EF7901371701A5B503B8AF25D2A147F0758C81AC1667` |
| `backend/app/models/audit_log.py` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` (empty) |
| `backend/app/models/review.py` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` (empty) |
| `backend/app/models/__init__.py` | `FA8CCA54BC0994B48C9C7AB45AEB7277284DE1D44C96E411C70F5A4DBA76D41C` |
| `backend/app/api/v1/router.py` | `1FF4256E68BDDC624E0DCB0A5E5DACA821B8D6CA29487F90F1A3057A95017E25` |
| `backend/app/api/v1/endpoints/auth.py` | `98C7CCB5850FD3D762AED530E20F3EBCBC19F1CB0E82203983CF2EF7E70470F4` |
| `backend/app/api/v1/endpoints/templates.py` | `7CB6F90B67A70F88C7905080236059DB54981121BEB83354F43561B7E45BE920` |
| `backend/app/services/verification_engine.py` | `084E4C53FB9F520A100D398B73204347FCF7B12B7ACF969996D61398DA20F629` |
| `backend/app/services/template_service.py` | `73260497C0F8CE42B58D10B75B550C99964A0D6E9D96C824854510DB02136A2D` |
| `backend/app/services/audit_service.py` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` (empty) |
| `backend/app/services/review_service.py` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` (empty) |
| `backend/app/schemas/auth.py` | `027DE78A82E1FA20FAD2E132557A32FE4A94488D0F5D1A19189B28C7E2D0797E` |
| `backend/app/schemas/review.py` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` (empty) |
| `backend/app/schemas/template.py` | `B80A76C407830E583A45EFAC1C62E816931059B527B36C50EE763A8E2826BCC3` |
| `backend/tests/test_alembic_migration_parity.py` | `FDED1D66792FF3C1F24A0C6C942F162B01F2C3D8691BA40716AA4BB7199E4822` |
| `backend/tests/test_postgres_migration_application.py` | `B53F99448ACAD210C8282ED2B07B3DC2C3A5DAF9495513F703AC23819E46EACF` |
| `backend/tests/pg_test_target.py` | `AEC58B947EE476314CF4CE28A9A5F354A7304B905A91EA7B352D2BD019380074` |

Recovered deployed governance migration:

| File | SHA-256 |
| --- | --- |
| `...\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\migrations\versions\0004_enterprise_governance_and_materiality.py` | `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` |

Installed Alembic generic revision template:

| File | SHA-256 | Lines |
| --- | --- | --- |
| `...\site-packages\alembic\templates\generic\script.py.mako` | `D38920781B4D31AE1C0A71BC09F41C2ADE8FEAB9E5A087E3F30CB4BBF0C1C9D3` | 20 |

### 14.4 Files changed by this batch

Exactly one file was created:

- `docs/audits/Batch23_Implementation_Readiness_Audit.md`

No application code, ORM model, migration, test, configuration, environment file, or existing audit report was changed. No file was staged, committed, or pushed.

### 14.5 Preservation verification

| Check | Result |
| --- | --- |
| Pre-report working-tree entries (`--untracked-files=all`) | **68** |
| Post-report working-tree entries (`--untracked-files=all`) | **69** |
| `Compare-Object` between before and after | Exactly one added line: `?? docs/audits/Batch23_Implementation_Readiness_Audit.md` |
| HEAD | `c91e9b37074483eeb7469dc943e1735fd5f5be02` (unchanged) |
| Branch | `feature/batch-4-rule-engine-aggregation` (unchanged) |
| `git show-ref --head` before/after diff | **0 lines** |
| Existing critical hashes | Unchanged; see section 14.3 |
| Staged or committed files | None |
| Database connections | None |
| Alembic commands | None |
| Test runs | None |
| `.env` reads or persistent environment changes | None |
| Deployment or remote changes | None |

### 14.6 Limitations

- The report’s own SHA-256 cannot be embedded without changing the file; it is reported in the delivery message after the final write.
- The local database revision was not queried because this batch prohibited database connections. Section 10 describes both possible states.
- Production schema, row counts, audit-chain validity, Render settings, and Neon branch behavior remain **[Unverified]**.
- The `discrepancy_review_decisions` contract is inferred from the deployed ORM and service; no historical migration exists.
- The current and deployed applications are divergent; the B/D merged application does not exist and was not built here.

### 14.7 Completion statement

Batch 23 is complete as an audit. It provides the canonical graph validation, exact `0005`/`0006` contracts, recovered `0004` inventory, ORM/application gap analysis, local-retirement mechanics, actionable T1–T14 coverage matrix, isolated-test runbook, file manifest, deployment gates, and a GO/NO-GO verdict.

**Audit scope: PASS. Implementation: NO-GO. Migration-graph design: implementable, subject to the written decision and gate amendment in section 13.**

*End of Batch 23 report.*
