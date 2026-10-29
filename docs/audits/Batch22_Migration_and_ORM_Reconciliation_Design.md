# VerifyGrid Batch 22 — Production Migration and ORM Reconciliation Design

**Batch:** 22
**Date:** 2026-10-29
**Repository:** `C:\Users\shaha\verifygrid`
**Branch:** `feature/batch-4-rule-engine-aggregation`
**HEAD:** `c91e9b37074483eeb7469dc943e1735fd5f5be02`
**Scope:** Design and audit only. No implementation, no database connection, no migration execution, no stamping, no test run, no application changes, and no Git state changes.
**Verdict:** **PASS — design scope only.**
**Production migration status:** **NO-GO** until the entry, implementation, and production gates in section 9 are satisfied.

---

## Evidence legend

| Label | Meaning |
| --- | --- |
| **[Repository]** | Directly inspected in the current working tree at the HEAD above. |
| **[Deployed source]** | Inspected in the recovered deployed tree for commit `58a0e5c` at `C:\Users\shaha\AppData\Local\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516`. |
| **[Prior audit]** | Recorded in Batch 18, 19, 20, or 21. |
| **[Production brief]** | Supplied as confirmed production state in the Batch 22 task. It was not independently re-inspected in this batch. |
| **[Inference]** | A conclusion reasoned from repository evidence but not directly observed in production. |
| **[Assumption]** | A condition that must be confirmed before implementation or deployment. |
| **[Proposal]** | A design recommendation. It is not implemented, authorized, or applied by this report. |

No production database, Neon branch, Render dashboard, or deployment log was contacted in this batch.

---

## 1. Executive summary

### 1.1 Principal findings

1. **[Production brief + Prior audit]** Production is governance-canonical at Alembic revision `0004_enterprise_governance` and contains the governance fields, `audit_events`, and all six lineage columns. The six lineage columns are therefore owned by the governance revision. The local `0005_verification_lineage` revision must not be replayed against production; doing so would attempt six duplicate `add_column` operations.

2. **[Repository + Prior audit]** The local graph is a different branch:

   ```text
   0001_initial_tables
     └── 0002_verification_runs
           └── 0003_user_password
                 └── 0004_verification_templates
                       └── 0005_verification_lineage   (local head)

   production:
   0001_initial_tables
     └── 0002_verification_runs
           └── 0003_user_password
                 └── 0004_enterprise_governance        (production head)
   ```

   Combining the two histories unmodified produces two heads and six duplicate column operations. A merge revision does not fix this: both parents are still traversed.

3. **[Production brief]** Production contains **33 verification runs** and **25,654 discrepancies**. It does **not** contain `verification_templates` or `discrepancy_review_decisions`.

4. **[Repository]** The only genuinely missing application tables are:

   - `verification_templates`, which the current ORM, API, and template service require; and
   - `discrepancy_review_decisions`, which the deployed review model, review service, and review routes require but which **no migration in either the current or deployed tree creates**.

5. **[Deployed source]** The missing review table is not a speculative feature. The deployed code inserts into it in two places:

   - `backend/app/services/review_service.py:104` for a single review; and
   - `backend/app/services/review_service.py:256` for each eligible record in a bulk review.

   The deployed routes are `POST /projects/{project_id}/runs/{run_id}/reviews/bulk` and `POST /projects/{project_id}/runs/{run_id}/reviews/{discrepancy_id}`. If production lacks the table, those paths fail at runtime.

6. **[Proposal]** The safe migration family is a **single governance-canonical linear graph**:

   ```text
   0001_initial_tables
     └── 0002_verification_runs
           └── 0003_user_password
                 └── 0004_enterprise_governance
                       └── 0005_verification_templates
                             └── 0006_discrepancy_review_decisions   (new sole head)
   ```

   `0005_verification_lineage` is retired, not conditionally skipped. `0004_verification_templates` is retired and reissued as `0005_verification_templates` on top of the governance revision. The review table is a **separate revision** from templates because its contract is reconstructed, its data is audit-like, and its deployment/rollback decision is independent.

7. **[Repository + Deployed source]** A schema bridge alone does **not** preserve governance functionality if the current application replaces the deployed application. The current application has:

   - no `AuditEvent` model and no audit service implementation;
   - no `DiscrepancyReviewDecision` model;
   - an empty review endpoint/service/schema and an empty audit endpoint;
   - no `users.role` mapping or role contract;
   - no sign-off, materiality, clustering, or assignment fields;
   - `reason_code` and `confidence_score` as read-only Python properties rather than mapped physical columns; and
   - a verification engine that writes only `field_differences`, leaving the physical `reason_code`/`confidence_score` columns NULL.

   Deploying that application over production would preserve the historical governance data but stop maintaining the governance workflow and audit chain. The target therefore requires either (a) keeping the deployed `58a0e5c` application, or (b) a combined application that ports the deployed governance code and adds templates. Option (b) is the recommended target; option (a) is the lowest-risk schema-only change but does not deliver templates.

8. **[Repository + Prior audit]** No repository-visible application startup path runs Alembic. `backend/app/main.py` and `backend/app/db/session.py` are byte-identical to the deployed versions and contain no migration hook. Render dashboard configuration remains unknown. The deployment plan must make migration execution explicit and must not assume a pre-deploy command.

9. **[Repository]** `backend/migrations/script.py.mako` is empty (0 bytes). Any `alembic revision` command would produce an unusable revision until the template is repaired. This is an implementation prerequisite, not a production change.

### 1.2 What this batch establishes

- The exact canonical graph and why it is forward-only.
- The exact minimum DDL for `verification_templates` and `discrepancy_review_decisions`.
- Why the review table requires a separate revision.
- The exact ORM/schema compatibility gaps, including `users.role`, sign-off fields, materiality/clustering fields, `reason_code`, `confidence_score`, `AuditEvent`, and review decisions.
- The local-history reconciliation options and why stamping is rejected.
- An isolated-database test matrix covering fresh migration, production-equivalent upgrade, data preservation, templates, governance/audit, ORM queries, and rollback.
- A Render deployment and migration sequence with rollback considerations.
- Explicit entry, implementation, and production go/no-go criteria.

### 1.3 What this batch does not establish

- That production's exact column types, defaults, constraints, and indexes match `0004_enterprise_governance` in every detail. The production brief confirms the objects, not a full catalog inventory.
- That the deployed review table ever existed or had a particular historical DDL. No migration creates it; its contract is reconstructed from the deployed ORM.
- That Render has no pre-deploy command. Dashboard configuration and logs were not inspected.
- That the current local database is disposable or that its data can be discarded.
- That any production migration, application deployment, or Neon change is authorized.
- That the governance review feature is actively used in production.
- That the existing audit hash chain currently verifies.
- That the current application can be deployed without a governance regression.

### 1.4 Verdict preview

**PASS — design scope only.** The required design and audit deliverable is complete. This is not a PASS for migration readiness, production compatibility, ORM compatibility, Render configuration, or Neon verification. Production migration remains **NO-GO** until section 9.

---

## 2. Scope, constraints, and working-tree baseline

### 2.1 Constraints observed

The batch was performed under these constraints:

- Do not implement changes.
- Do not connect to Neon.
- Do not run production migrations.
- Do not stamp revisions.
- Do not modify migration files.
- Do not change application code.
- Do not change Git state, environment variables, deployment settings, or remote infrastructure.
- Use read-only repository inspection and existing audit evidence.

### 2.2 Repository baseline

**[Repository]**

| Property | Value |
| --- | --- |
| Branch | `feature/batch-4-rule-engine-aggregation` |
| HEAD | `c91e9b37074483eeb7469dc943e1735fd5f5be02` |
| HEAD subject | `feat: implement Batch 4 advanced rule engine, aggregation and split-payment reconciliation` |
| Working-tree entries before this report | 67 |
| Batch 22 report before this batch | Absent |
| Local migration files | `0001`, `0002`, `0003`, `0004_verification_templates`, `0005_verification_lineage` |
| Local sole head | `0005_verification_lineage` |

Pre-existing working-tree entries include modified `backend/migrations/env.py` and untracked Batch 18–21 reports and the two local migration files. They were not created or modified by this batch.

### 2.3 Prior audit conclusions

**[Prior audit]**

| Batch | Deliverable | Verdict | Relevance to Batch 22 |
| --- | --- | --- | --- |
| 18 | `Batch18_Migration_History_Divergence_Audit.md` | PASS — audit scope only | Established the divergent histories and the missing governance revision. |
| 19 | `Batch19_Migration_Reconciliation_Preparation.md` | PASS — preparation scope only | Defined inventory, decision matrix, and isolated-test prerequisites. |
| 20 | `Batch20_Governance_Migration_Recovery_Audit.md` | PASS — audit scope only | Recovered the deployed governance migration and proved the duplicate-operation risk. |
| 21 | `Batch21_Production_Schema_Lineage_Audit.md` | PASS — audit scope only | Established the governance-canonical strategy family and the current ORM gap. |

Batch 21's qualifications still apply: it was not a PASS for reconciliation, migration readiness, Neon, Render configuration, ORM compatibility, historical completeness, or revalidation.

### 2.4 Actions not taken

**[Repository]**

- No application code or ORM model was edited.
- No migration file was created, edited, renamed, or deleted.
- No Alembic command was run: no `upgrade`, `downgrade`, `stamp`, `revision`, `history`, `current`, or `heads`.
- No database connection was attempted.
- No Neon or Render resource was contacted.
- No test suite was run.
- No `.env` file was read or resolved.
- No Git index, branch, commit, tag, or remote was changed.
- No environment variable or deployment setting was changed.

---

## 3. Verified facts versus assumptions

### 3.1 Verified facts

| # | Fact | Evidence | Confidence |
| --- | --- | --- | --- |
| F1 | Production Alembic revision is `0004_enterprise_governance`. | Production brief; Batch 21 §1.1, §4.2. | Confirmed by task context; not re-inspected here. |
| F2 | Live Render commit is `58a0e5c243978480c4ca817c537c700ed6b20516`. | Production brief; Batch 21 §4.1; recovered source tree. | Confirmed by task context; Render status not re-inspected here. |
| F3 | Production contains governance fields, `audit_events`, and all six lineage columns. | Production brief; Batch 21 §1.1, §4.2. | Confirmed by task context. |
| F4 | Production does not contain `verification_templates`. | Production brief. | Confirmed by task context. |
| F5 | Production does not contain `discrepancy_review_decisions`. | Production brief. | Confirmed by task context. |
| F6 | Production contains 33 verification runs and 25,654 discrepancies. | Production brief. | Confirmed by task context. |
| F7 | The local chain is `0001 → 0002 → 0003 → 0004_verification_templates → 0005_verification_lineage`. | Repository migration files; Batch 21 §3.1. | Confirmed. |
| F8 | The current local sole head is `0005_verification_lineage`. | `backend/migrations/versions/0005_verification_lineage.py:35-36`; parity test lines 66–67. | Confirmed. |
| F9 | The deployed governance revision is `0004_enterprise_governance`, child of `0003_user_password`. | Deployed `0004_enterprise_governance_and_materiality.py:15-16`. | Confirmed. |
| F10 | The governance revision adds the same six lineage columns as `0005_verification_lineage`. | Governance lines 29, 62–66; lineage lines 41–72. | Confirmed. |
| F11 | Applying both branches would attempt six duplicate `add_column` operations and six duplicate `drop_column` operations. | Batch 20 §6; Batch 21 §1.1, §8; direct file comparison. | Confirmed. |
| F12 | The governance revision adds 33 columns, one table (`audit_events`), five foreign keys, and thirteen indexes. | Governance migration; Batch 21 §4.2. | Confirmed. |
| F13 | The governance revision does not create templates or review decisions. | Governance migration; Batch 21 §4.2. | Confirmed. |
| F14 | No migration in either tree creates `discrepancy_review_decisions`. | Repository and deployed `migrations/versions`; recursive grep. | Confirmed. |
| F15 | The deployed ORM declares `DiscrepancyReviewDecision` mapped to `discrepancy_review_decisions`, with 12 columns and two cascade FKs. | Deployed `backend/app/models/verification_run.py:398-467`. | Confirmed. |
| F16 | Deployed review code inserts into `discrepancy_review_decisions` for single and bulk reviews. | Deployed `review_service.py:104-116, 256-268`; routes `review.py:103-168`. | Confirmed. |
| F17 | The current ORM declares `verification_templates` with 10 columns, a nullable owner FK, a unique `(owner_id, name)`, and an owner index. | `backend/app/models/verification_template.py:25-81`; `0004_verification_templates.py:30-70`. | Confirmed. |
| F18 | The current application actively registers and uses template routes. | `backend/app/api/v1/router.py:15, 68`; `templates.py`; `template_service.py`. | Confirmed. |
| F19 | The current ORM lacks `users.role`, the nine sign-off fields, the seventeen materiality/clustering/review fields, `AuditEvent`, and review decisions. | Current `user.py`, `verification_run.py`, `models/__init__.py`; Batch 21 §7.1–7.2. | Confirmed. |
| F20 | The current ORM maps `reason_code` and `confidence_score` as read-only properties, not physical columns. | Current `verification_run.py:218-259`. | Confirmed. |
| F21 | The deployed ORM maps physical `reason_code` and `confidence_score` through `_reason_code` and `_confidence_score` with setters. | Deployed `verification_run.py:309-319, 350-395`. | Confirmed. |
| F22 | The current verification engine writes `field_differences` only; it does not set `_reason_code` or `_confidence_score`. | Current `verification_engine.py:1751-1764, 2869-2887`; grep for `_reason_code=` found none. | Confirmed. |
| F23 | The deployed verification engine writes physical `_reason_code` and `_confidence_score`. | Deployed `verification_engine.py:1679-1680, 2617-2618`. | Confirmed. |
| F24 | The deployed verification engine filters on `VerificationDiscrepancy._reason_code`. | Deployed `verification_engine.py:1823, 1830`. | Confirmed. |
| F25 | Current review/audit/governance implementations are empty stubs or absent. | File sizes: `review_service.py`, `audit_service.py`, `schemas/review.py`, `endpoints/reviews.py`, `endpoints/audit.py`, `models/audit_log.py`, `models/review.py` are 0 bytes; governance/review/recipes endpoints, governance/recipe schemas, and clustering/materiality/governance services are absent. | Confirmed. |
| F26 | The deployed app registers review, governance, audit, and recipe routers. | Deployed `router.py:15-18, 71-74`. | Confirmed. |
| F27 | No application startup path runs Alembic. | Current and deployed `main.py`, `session.py`; Batch 21 §5. | Confirmed. |
| F28 | Deployed tests create the schema with `Base.metadata.create_all`, masking the missing review-table migration. | Deployed `tests/conftest.py:40-42`. | Confirmed. |
| F29 | The current test suite uses in-memory SQLite and `Base.metadata.create_all`, so it cannot prove migration compatibility. | Current `tests/conftest.py:14-37`. | Confirmed. |
| F30 | The migration-parity test expects `EXPECTED_HEAD = "0005_verification_lineage"` and exact current-ORM table sets. | `test_alembic_migration_parity.py:66-67, 221-312`. | Confirmed. |
| F31 | `backend/migrations/script.py.mako` is empty (0 bytes). | Direct file inspection. | Confirmed. |
| F32 | `backend/migrations/env.py` has an uncommitted explicit-connection test path. | `git status`; `env.py:49-66`. | Confirmed. |
| F33 | The repository contains no `render.yaml`, Dockerfile, Procfile, backend start/release script, or backend migration workflow. | Batch 21 §5.2; current recursive search. | Confirmed for repository; Render dashboard unknown. |

### 3.2 Assumptions that must be confirmed before implementation

| # | Assumption | Why it matters | Confirmation required |
| --- | --- | --- | --- |
| A1 | Production's governance columns, `audit_events`, and six lineage columns match `0004_enterprise_governance` in type, nullability, defaults, indexes, and constraints. | A mismatch means the canonical graph is not a truthful baseline. | Full read-only catalog inventory. |
| A2 | `alembic_version` contains exactly one row, `0004_enterprise_governance`. | Multiple or unknown rows invalidate the upgrade path. | Read-only version-table inventory. |
| A3 | Production has no manually created templates or review table. | The production brief says absent, but a stale brief would make `create_table` fail. | Re-check immediately before migration. |
| A4 | The deployed review table's contract is fully represented by the deployed ORM. | No migration exists; the ORM is the only repository evidence. | Code review plus isolated schema tests; document any inferred defaults. |
| A5 | The local development database is disposable, or its data can be exported and reloaded. | The retired local history cannot be upgraded in place without a rebuild. | Owner decision. |
| A6 | Render deployment is manually controlled or can be paused during the migration. | Auto-deploy on a migration commit could start the new app before the schema exists. | Render dashboard review. |
| A7 | A verified backup or point-in-time restore exists and has been restore-tested. | Additive DDL is low risk, but data loss or operator error still requires recovery. | Database owner evidence. |
| A8 | The application version to run in production is explicitly selected. | Schema-only and combined-app outcomes differ materially. | Written product/engineering decision. |
| A9 | The governance review feature is either required or explicitly out of scope. | Determines whether `0006` is mandatory in the first production window. | Product/owner decision. |
| A10 | The existing audit hash chain is valid before the change. | If it is already broken, post-migration verification cannot distinguish old from new damage. | Read-only audit-chain verification on a branch/restore. |
| A11 | No other unknown schema object depends on the new tables or conflicts with their names. | A hidden object could block `create_table` or indicate undocumented history. | Full inventory. |
| A12 | The production database role can create tables, indexes, and foreign keys in the target schema. | Insufficient privileges cause a partial-window failure. | Role/privilege inventory. |

### 3.3 Facts this batch deliberately does not assume

- It does not assume that the local `0004_verification_templates` was ever applied to production.
- It does not assume that `0005_verification_lineage` was ever applied to production.
- It does not assume that production's six lineage columns came from `0005`; the governance revision is the sufficient explanation.
- It does not assume that the review table had a historical migration that was lost; the evidence shows no such migration in either recovered tree.
- It does not assume that the current application is production-compatible.
- It does not assume that the current test suite proves migration behavior.

---

## 4. Proposed migration graph

### 4.1 Canonical graph

**[Proposal]**

```text
0001_initial_tables
  └── 0002_verification_runs
        └── 0003_user_password
              └── 0004_enterprise_governance
                    └── 0005_verification_templates
                          └── 0006_discrepancy_review_decisions   (sole head)
```

| Revision | Parent | Operation | Source of truth | Production action |
| --- | --- | --- | --- | --- |
| `0001_initial_tables` | — | Initial users/projects/source files | Existing local/deployed file | Already applied; do not touch. |
| `0002_verification_runs` | `0001` | Runs/discrepancies | Existing local/deployed file | Already applied; do not touch. |
| `0003_user_password` | `0002` | Password column | Existing local/deployed file | Already applied; do not touch. |
| `0004_enterprise_governance` | `0003` | 33 columns, `audit_events`, 5 FKs, 13 indexes | Recovered deployed file, byte-identical | Already applied; do not replay. |
| `0005_verification_templates` | `0004_enterprise_governance` | Create `verification_templates` | Current template ORM and current template migration DDL | New forward-only migration. |
| `0006_discrepancy_review_decisions` | `0005_verification_templates` | Create `discrepancy_review_decisions` | Deployed review ORM and review service insert contract | New forward-only migration. |

### 4.2 Retired revisions

**[Proposal]**

| File | Disposition | Reason |
| --- | --- | --- |
| `backend/migrations/versions/0004_verification_templates.py` | Retire/remove from the graph. Reissue its DDL as `0005_verification_templates` on the governance parent. | Its parent is `0003`, which puts it on a branch parallel to production governance. It is untracked and only applied locally. |
| `backend/migrations/versions/0005_verification_lineage.py` | Retire/remove from the graph. Do not replay, copy, merge, or conditionally skip it. | Its six columns are already added by `0004_enterprise_governance`. Keeping it creates duplicate ownership and duplicate DDL. |

The retirements are repository-history reconciliation, not production history changes. Production remains truthfully stamped at `0004_enterprise_governance`.

### 4.3 Why a merge revision is not the solution

**[Inference from repository evidence]**

A merge revision with parents `0004_enterprise_governance` and `0005_verification_lineage` would cause Alembic to traverse both branches when upgrading a production database at `0004_enterprise_governance`. Traversal would apply the local `0004_verification_templates` and then `0005_verification_lineage`, attempting to add the six lineage columns a second time. The merge would preserve both duplicate operation sets rather than eliminate them.

A merge with parents `0004_enterprise_governance` and `0004_verification_templates` avoids `0005_verification_lineage`, but leaves the local database at an unknown revision and still requires retiring or rewriting the lineage branch. It adds graph complexity without solving the duplicate-ownership problem.

The linear canonical graph is simpler and has one owner for every object.

### 4.4 Why the review table is a separate revision

**[Proposal]**

`discrepancy_review_decisions` is not part of the template feature and should not share its revision:

1. **Different evidence quality.** `verification_templates` has a complete current ORM plus a complete current migration that can be re-parented. `discrepancy_review_decisions` has no migration at all; its DDL must be reconstructed from the deployed ORM and insert paths.

2. **Different data semantics.** Templates are user configuration and can be deleted with the user's intent. Review decisions are audit-like evidence of human decisions and may need retention even if a feature is rolled back.

3. **Different application dependency.** Templates are required by the current application. Review decisions are required by the deployed `58a0e5c` application. The application-version decision may require one before the other.

4. **Different rollback policy.** A failed template migration can be reverted while the table is empty. A review table with rows must not be dropped merely to roll back a deployment.

5. **Independent review gate.** Mixing a known contract with an inferred contract makes it harder to approve or reject either one cleanly. Two small `create_table` revisions cost almost nothing and isolate the blast radius.

The recommended order is templates first (`0005`) and review second (`0006`). Both are additive and may be applied in the same authorized window. If the review feature is urgent, the two revision IDs may be reordered **before either is applied to any database**; once a revision is applied, do not rewrite its ancestry.

### 4.5 What the canonical graph does not contain

**[Proposal]**

- No `add_column` for any of the six lineage columns.
- No changes to `users`, `projects`, `source_files`, `verification_runs`, `verification_discrepancies`, or `audit_events`.
- No data backfill.
- No `create_all`.
- No blind `IF NOT EXISTS` table creation.
- No changes to governance constraints, indexes, or defaults.
- No stamping step.

### 4.6 Minimum safe migration

**[Proposal]**

- **To introduce `verification_templates` only:** `0005_verification_templates` is the minimum schema change. It creates one new table and its index/constraint. It does not touch existing tables or data.
- **To repair the deployed review feature:** `0006_discrepancy_review_decisions` is the minimum schema change. It creates one new table and its indexes/FKs. It does not touch existing tables or data.
- **Do not combine them into one revision.** They have separate contracts, tests, and rollback decisions.
- **Do not add any other object speculatively.** The only confirmed missing objects are these two tables. Any additional object requires inventory evidence and a separate design.

No other application table is missing based on the inspected models:

- `users`, `projects`, `source_files`, `verification_runs`, and `verification_discrepancies` are shared base/governance tables.
- `audit_events` is already created by `0004_enterprise_governance`.
- `models/rule.py` and `models/review.py` are empty; rules are stored in the run configuration/rule JSON, and clustering is computed from discrepancies.
- Recipes are exported/validated as `.verifygrid.json` payloads; no recipe table exists in the deployed code.

---

## 5. Revision specifications

### 5.1 `0005_verification_templates`

**[Proposal derived from Repository]**

Revision metadata:

- revision: `0005_verification_templates`
- down_revision: `0004_enterprise_governance`
- branch_labels: `None`
- depends_on: `None`

Table contract:

| Column | SQLAlchemy type | PostgreSQL type | Nullable | Default | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Uuid` | `uuid` | No | none (application UUID) | Primary key. |
| `owner_id` | `Uuid` | `uuid` | Yes | none | FK `users.id` `ON DELETE SET NULL`; indexed. |
| `name` | `String(255)` | `varchar(255)` | No | none | Unique with owner. |
| `description` | `Text` | `text` | Yes | none | |
| `mode` | `String(50)` | `varchar(50)` | No | none | Application-validated mode. |
| `visibility` | `String(20)` | `varchar(20)` | No | `'personal'` | Dormant sharing field. |
| `config_version` | `Integer` | `integer` | No | `1` | |
| `configuration` | `JSON` | `json` | No | none | Validated snapshot. |
| `created_at` | `DateTime(timezone=True)` | `timestamptz` | No | `now()` | |
| `updated_at` | `DateTime(timezone=True)` | `timestamptz` | No | `now()` | ORM `onupdate=now()`. |

Constraints and indexes:

- Primary key: `verification_templates_pkey` on `id`.
- Foreign key: `owner_id` → `users.id`, `ON DELETE SET NULL`.
- Unique constraint: `uq_verification_templates_owner_name` on `(owner_id, name)`.
- Index: `ix_verification_templates_owner_id` on `owner_id`.

Behavior:

- Existing rows: none; table is new.
- Existing tables: no `ALTER TABLE`. The only locks on existing tables are the brief locks PostgreSQL takes when creating the new foreign key to `users`.
- Row count after migration: 0.
- Downgrade: drop the index and table. This destroys templates if any exist; operational policy must prohibit downgrade once templates contain user data.

Compatibility note:

- The current template migration creates the same table on the local branch. The canonical revision reuses the exact DDL but changes the parent. It must not carry the old revision ID or parent.

### 5.2 `0006_discrepancy_review_decisions`

**[Proposal derived from Deployed source]**

Revision metadata:

- revision: `0006_discrepancy_review_decisions`
- down_revision: `0005_verification_templates`
- branch_labels: `None`
- depends_on: `None`

Table contract:

| Column | SQLAlchemy type | PostgreSQL type | Nullable | Default | Notes |
| --- | --- | --- | --- | --- | --- |
| `id` | `Uuid` | `uuid` | No | none (application UUID) | Primary key. |
| `discrepancy_id` | `Uuid` | `uuid` | No | none | FK `verification_discrepancies.id` `ON DELETE CASCADE`; indexed. |
| `run_id` | `Uuid` | `uuid` | No | none | FK `verification_runs.id` `ON DELETE CASCADE`; indexed. |
| `decision` | `String(50)` | `varchar(50)` | No | none | `APPROVE`, `REJECT`, `FORCE_MATCH`, `ESCALATE`, `REOPEN`. |
| `justification` | `Text` | `text` | No | none | Non-empty at application boundary. |
| `reviewer_id` | `String(100)` | `varchar(100)` | Yes | none | String, not a user FK; may hold UUID text, `system`, or `reviewer`. Indexed. |
| `reviewer_email` | `String(255)` | `varchar(255)` | Yes | none | |
| `previous_status` | `String(50)` | `varchar(50)` | Yes | none | |
| `new_status` | `String(50)` | `varchar(50)` | No | none | |
| `is_bulk_action` | `Boolean` | `boolean` | No | `false` | ORM client default `False`; migration should use `server_default=false` for raw-insert safety. |
| `cluster_id` | `String(64)` | `varchar(64)` | Yes | none | Indexed; no FK. |
| `created_at` | `DateTime(timezone=True)` | `timestamptz` | No | `now()` | |

Constraints and indexes:

- Primary key: `discrepancy_review_decisions_pkey` on `id`.
- Foreign key: `discrepancy_id` → `verification_discrepancies.id`, `ON DELETE CASCADE`.
- Foreign key: `run_id` → `verification_runs.id`, `ON DELETE CASCADE`.
- Index: `ix_discrepancy_review_decisions_discrepancy_id`.
- Index: `ix_discrepancy_review_decisions_run_id`.
- Index: `ix_discrepancy_review_decisions_reviewer_id`.
- Index: `ix_discrepancy_review_decisions_cluster_id`.
- No unique constraints.
- No check constraints.
- No `updated_at`.

Relationships:

- ORM `DiscrepancyReviewDecision.discrepancy` ↔ `VerificationDiscrepancy.review_decisions`, with `cascade="all, delete-orphan"` on the parent relationship. Database FK also cascades.
- ORM `DiscrepancyReviewDecision.run` → `VerificationRun`, no `back_populates`.
- No relationship to `User`; `reviewer_id` is deliberately a string for audit identity.

Behavior:

- Existing rows: none; table is new.
- Existing tables: no `ALTER TABLE`. Brief FK locks on `verification_discrepancies` and `verification_runs`.
- Row count after migration: 0.
- Downgrade: drop the table. This destroys review decisions if any exist; operational policy must prohibit downgrade once rows exist.

Contract uncertainty:

- No migration ever created this table. The deployed ORM is the strongest available contract, but the original DDL (if any ever existed outside the repository) is unknown.
- The `is_bulk_action` server default is a reconstruction choice. The deployed ORM uses a client-side `default=False`; every deployed insert sets the value explicitly. A server default of `false` is strictly safer for raw SQL and does not change deployed behavior. The ORM should be updated to declare the same `server_default` so metadata and migration agree.
- If a future read-only inventory or historical artifact shows a different contract, stop and revise the design before applying `0006`.

### 5.3 Operation and lock profile

**[Inference]**

Both revisions are `CREATE TABLE` plus indexes and constraints. They do not rewrite or scan existing application tables. PostgreSQL still takes brief locks on referenced tables when adding the new FKs. The expected impact is small, but production execution should still:

- run in a controlled window or low-traffic period;
- set a short `lock_timeout` (for example, 5 seconds) so a blocked DDL statement fails rather than waiting indefinitely;
- monitor application errors and database locks during the window;
- avoid running while a long transaction holds conflicting locks on `users`, `verification_runs`, or `verification_discrepancies`.

### 5.4 Fail-closed preflight, not conditional DDL

**[Proposal]**

Do not use blind `CREATE TABLE IF NOT EXISTS` or `ADD COLUMN IF NOT EXISTS` as a substitute for inventory. Conditional DDL can silently accept an existing table with the wrong shape and then mark the revision applied.

The safe sequence is:

1. Read-only preflight asserts the target revision and object absence.
2. The migration uses plain `create_table` and fails loudly if the object exists.
3. If the migration fails, stop, inspect, and re-plan. Do not stamp over the failure.

This preserves the truthfulness of `alembic_version`.

---

## 6. Local development history reconciliation

### 6.1 The problem

**[Repository]**

The local database, if it was upgraded along the current branch, records `0005_verification_lineage` and contains:

- `verification_templates` from the local `0004_verification_templates`;
- the six lineage columns from `0005_verification_lineage`;
- no governance columns, `users.role`, `audit_events`, sign-off fields, materiality fields, or review table.

The canonical graph expects a database at `0004_enterprise_governance` to already contain the governance superset. The local schema is not equal to that revision, even though it has some overlapping objects. It cannot be truthfully stamped to `0005_verification_templates` or `0006_discrepancy_review_decisions` without first creating the missing governance objects.

### 6.2 Options

**[Proposal]**

| Option | Action | Assessment |
| --- | --- | --- |
| L1 — Disposable rebuild (recommended) | Drop/recreate the local schema or database, then run the canonical graph from `0001` to `0006`. Re-seed or reload approved local data. | Clean, truthful, no duplicate DDL, no stamping. Requires local data to be disposable or exported first. |
| L2 — Export/rebuild/reload | Export base application data from the old schema, rebuild the canonical schema, reload the data into the new base tables, then verify counts and constraints. | Preserves local data without pretending the old schema was canonical. Needs a reviewed local-only data script. Governance columns receive defaults/NULL because the old local schema had none. |
| L3 — Local-only reconciliation migration | Author a local-only migration that adds the missing governance objects to the old branch, then stamps `0004_enterprise_governance`, then upgrades. | High complexity, duplicates production DDL outside the canonical graph, and risks false stamping. Not recommended. |
| L4 — Stamp the old database to the canonical head | Run `alembic stamp 0006_discrepancy_review_decisions` without DDL. | Rejected. The schema does not match; the stamp would be false. |
| L5 — Keep the old branch indefinitely | Keep the local branch as a separate labeled history and use explicit targets. | Rejected for the canonical graph because it leaves two heads and requires disciplined targeting forever. Batch 21 already identified this as more error-prone. |

### 6.3 Recommended local procedure

**[Proposal]**

1. Confirm with the owner whether local development data must be preserved.
2. If not, drop/recreate the local schema and run the canonical graph. This is the preferred path.
3. If yes:
   - export only base application data needed for development, with a reviewed local script;
   - rebuild the canonical schema from `0001` to `0006`;
   - reload users, projects, source files, runs, discrepancies, and templates in FK-safe order;
   - verify row counts, FK integrity, template uniqueness, and a sample of run/discrepancy payloads;
   - do not copy old governance state because none existed locally.
4. Never run `alembic stamp` against the old local schema as a shortcut.
5. Never run the local rebuild procedure against production.

### 6.4 Production history

**[Proposal]**

Production requires **no stamping**:

- It is already truthfully at `0004_enterprise_governance`.
- The canonical graph adds only `0005` and `0006`.
- `alembic upgrade 0005_verification_templates` and `alembic upgrade 0006_discrepancy_review_decisions` are forward-only.
- If production is not at `0004_enterprise_governance` at execution time, stop. Do not stamp to make the command proceed.

---

## 7. ORM and schema compatibility

### 7.1 Table inventory

**[Repository + Deployed source]**

| Table | Current ORM | Deployed ORM | Production brief | Canonical target |
| --- | --- | --- | --- | --- |
| `users` | 6 columns | 7 columns (`role` extra) | Governance fields present | 7 columns. |
| `projects` | 6 | 6 | Present | 6. |
| `source_files` | 8 | 8 | Present | 8. |
| `verification_runs` | 15 | 24 (9 sign-off extra, plus shared `sources`) | Governance fields and six lineage columns present | 24. |
| `verification_discrepancies` | 19 | 36 (17 governance extra, plus shared lineage) | Governance fields and six lineage columns present | 36. |
| `verification_templates` | 10 | absent | Absent | 10; added by `0005`. |
| `audit_events` | absent | 14 | Present | 14; governance-owned. |
| `discrepancy_review_decisions` | absent | 12 | Absent | 12; added by `0006`. |

### 7.2 Exact object-level mismatches

**[Repository + Deployed source]**

| Object group | Deployed/Production contract | Current ORM/application | Compatibility consequence | Required future action |
| --- | --- | --- | --- | --- |
| `users.role` | `String(50)`, not null, server default `MAKER`. | Not mapped; auth schema/reponse has no role. | Current inserts rely on the DB default; current code cannot enforce or display maker-checker roles. | Add `User.role`; extend auth schema/response and registration if roles are required. |
| Run sign-off | `sign_off_status` not null default `DRAFT`, indexed; `sign_off_proposed_by`/`approved_by` FKs to `users.id` `SET NULL`; seven name/note/time fields. | Not mapped. | Current inserts get `DRAFT`; current code cannot propose, approve, reject, or display sign-off. Existing sign-off data is invisible. | Add all nine fields and relationships; port governance service/routes. |
| Discrepancy materiality | `source_amount`, `target_amount`, `variance_amount`, `exposure_amount` (indexed), `currency` default `USD`, `severity` default `medium` (indexed), `resolution_status` default `unresolved` (indexed), `resolution_note`, `resolved_by`, `resolved_at`. | Not mapped. | Current inserts rely on nullable/default values; current code does not populate or expose materiality or resolution. Existing values are invisible. | Add fields; port materiality engine and result serialization. |
| Clustering/review | `cluster_id` (indexed), `cluster_name`, `assigned_to` (indexed), `assigned_at`, `side_by_side`. | Not mapped. | Current code cannot cluster, assign, or display side-by-side records. | Add fields; port clustering/review services and routes. |
| Physical `reason_code` | `String(100)`, indexed. | Read-only property computed from `field_differences` and `match_status`; not a column. | Current reads ignore stored values; current writes leave the column NULL. Deployed filters on `_reason_code` will not see current-created rows. | Map `_reason_code` to `reason_code` with a setter; write it in the engine; preserve fallback property behavior. |
| Physical `confidence_score` | `Float`. | Read-only property computed from `field_differences`/`match_status`; not a column. | Same as above; semantic drift and NULL writes. | Map `_confidence_score` to `confidence_score` with a setter; write it in the engine. |
| `audit_events` | 14 columns, 3 FKs, 6 indexes; append-only SHA-256 chain. | No model, no service, no route. | Current application activity is not audited; the deployed chain becomes incomplete if the current app replaces the deployed app. | Add `AuditEvent`, audit service, audit routes, and calls from run/review/governance paths. |
| `discrepancy_review_decisions` | 12 columns, 2 cascade FKs, 4 indexes; required by deployed review service. | No model, no service, no route; table absent. | Deployed review endpoints fail on the missing table; current app has no review feature at all. | Add table via `0006`; add model/service/routes if current app is to support review. |
| `verification_templates` | Absent in deployed ORM/production. | 10 columns; table absent in production. | Current template endpoints fail with missing relation. | Add table via `0005`; keep current ORM/API. |
| Server defaults | Governance revision uses DB defaults for role, sign-off status, currency, severity, resolution status, audit sequence, timestamps. | Current ORM often has client-side defaults only. | Inserts work through DB defaults, but ORM/migration parity tests that compare defaults may drift. | Add default assertions to the parity test; align ORM/migration declarations intentionally. |
| JSON types | Governance uses `sa.JSON` → PostgreSQL `json` for lineage and audit payloads. | Current uses `sa.JSON`. | A production `jsonb` column would be a mismatch, not a compatible variant, for exact parity. | Inventory exact types; do not "fix" without evidence. |

### 7.3 Behavioral consequences of deploying the current application over production

**[Inference from static code]**

| Area | Likely behavior | Severity |
| --- | --- | --- |
| Auth/projects/files/uploads/runs/basic results/exports | Likely to work because all shared base columns exist and governance extras are nullable or defaulted. | Low SQL risk; governance blind spots. |
| Template endpoints | Fail while `verification_templates` is absent; work after `0005`. | Blocking for the template feature. |
| Review endpoints | Current app has no review routes; review decisions table is irrelevant to current app. Deployed app's review routes fail until `0006`. | Feature loss / existing bug. |
| Role and sign-off | Ignored; no maker-checker enforcement or visibility. | Governance regression. |
| Materiality/clustering | Ignored; new discrepancies lack exposure/severity/cluster data. | Governance regression. |
| Physical reason/confidence | New rows leave columns NULL; current reads compute values from JSON. Deployed filters may not see new rows. | Semantic and reporting regression. |
| Audit trail | Current app writes no `audit_events`; chain stops reflecting new activity. | Governance/audit regression. |
| Existing governance data | Not deleted by the schema, but not used or maintained by the current app. | Data preserved, functionality lost. |

### 7.4 Application reconciliation options

**[Proposal]**

| Option | Description | Preserves governance functionality? | Delivers templates? | Assessment |
| --- | --- | --- | --- | --- |
| A — Schema-only, keep deployed app `58a0e5c` | Apply `0005` (dormant) and/or `0006` (repairs review). Do not deploy current app. | Yes, as long as `58a0e5c` remains the running application. | No. | Lowest-risk production schema change. Suitable if templates are not needed yet. |
| B — Combined application (recommended target) | Port deployed governance/audit/review code into the current branch, retain templates and rule engine, then deploy after `0005` and `0006`. | Yes, if the port is complete and tested. | Yes. | Highest engineering effort; the only option that delivers both. |
| C — Deploy current application alone | Apply schema, replace `58a0e5c` with current app. | No. | Yes. | Rejected for production: it silently stops governance, sign-off, materiality, clustering, and audit. |
| D — New combined build from `58a0e5c` | Start from deployed code and cherry-pick templates/rule-engine changes. | Yes. | Yes. | Functionally equivalent to B; may be cleaner if the deployed governance code is the stronger baseline. Choose B or D after a file-level diff. |

**Recommendation:** Target B or D. Do not authorize option C for production. Option A is acceptable only as a schema-only change with an explicit decision to defer templates.

### 7.5 Minimum ORM/application changes for the combined target

**[Proposal]**

The following list is the minimum known set. It is not a guarantee that a file-level diff against `58a0e5c` will not reveal additional changes.

**Models**

- `backend/app/models/user.py`: add `role` (`String(50)`, not null, default/server default `MAKER`).
- `backend/app/models/verification_run.py`:
  - add the nine sign-off fields and two user FKs;
  - add the seventeen materiality/clustering/review fields;
  - map `_reason_code` to `reason_code` and `_confidence_score` to `confidence_score`, with property getters/setters that preserve the existing computed fallback;
  - add `review_decisions` relationship and `DiscrepancyReviewDecision` class, or move the class only if all deployed imports are updated;
  - preserve `source_row_index`/`target_row_index` properties.
- `backend/app/models/audit_log.py`: replace the empty file with the `AuditEvent` model.
- `backend/app/models/review.py`: either remove the empty file or make it a re-export; the deployed service imports `DiscrepancyReviewDecision` from `verification_run`.
- `backend/app/models/__init__.py`: import and export `AuditEvent` and `DiscrepancyReviewDecision`.

**Schemas**

- `backend/app/schemas/review.py`: replace the empty file with the deployed review schemas.
- Add `backend/app/schemas/audit.py`.
- Add `backend/app/schemas/governance.py`.
- Add `backend/app/schemas/recipe.py` if recipes are in scope.
- `backend/app/schemas/auth.py`: add `role` to register/response if role management is required.

**Services**

- `backend/app/services/review_service.py`: replace the empty file with the deployed implementation.
- `backend/app/services/audit_service.py`: replace the empty file with the deployed hash-chain implementation.
- Add `backend/app/services/clustering_service.py`.
- Add `backend/app/services/materiality_engine.py`.
- Add `backend/app/services/governance_service.py`.
- Add `backend/app/services/recipe_service.py` if recipes are in scope.
- `backend/app/services/verification_engine.py`: write governance fields and physical `_reason_code`/`_confidence_score`; integrate materiality/clustering where required.
- `backend/app/services/project_service.py`: preserve deployed role-aware behavior if ADMIN semantics are required.

**API**

- Replace empty `backend/app/api/v1/endpoints/audit.py` with the deployed audit routes.
- Add `backend/app/api/v1/endpoints/review.py` (the deployed name) or rename/replace the empty `reviews.py` consistently.
- Add `backend/app/api/v1/endpoints/governance.py`.
- Add `backend/app/api/v1/endpoints/recipes.py` if recipes are in scope.
- `backend/app/api/v1/router.py`: register review, governance, audit, and recipe routers.
- `backend/app/api/v1/endpoints/auth.py`: persist/return role if role management is required.

**Tests**

- Port the deployed governance/audit, exception-clustering, materiality, and recipe tests.
- Adapt them to the current test fixtures, then add migration-built variants.
- Do not rely on the SQLite `create_all` fixture for schema compatibility.

**Explicitly unchanged**

- `backend/app/main.py`: do not add a startup migration hook.
- `backend/app/db/session.py`: do not add `create_all` or migration execution.
- No `render.yaml` is required for the migration itself; if one is added, it must be reviewed as deployment configuration, not as an application code change.

### 7.6 ORM/schema parity test consequences

**[Repository]**

The current parity test will fail against the canonical graph until it is updated:

- `EXPECTED_HEAD` must become `0006_discrepancy_review_decisions`.
- `PREVIOUS_HEAD` must be `0004_enterprise_governance`.
- The expected table set must include `verification_templates`, `audit_events`, and `discrepancy_review_decisions`.
- The expected column set must include governance fields only if the current ORM is also reconciled. If the current ORM remains a subset, the parity test must be redesigned around the canonical ORM target, not the current subset.
- The six-column-specific assertions should be retained as a regression check that the canonical graph adds them exactly once.
- `compare_metadata` must run against the ORM that the deployed application will actually use. A schema-only deployment with the old ORM cannot claim full parity.

### 7.7 Existing test blind spots

**[Repository + Deployed source]**

- Current `tests/conftest.py` uses in-memory SQLite and `Base.metadata.create_all`; it does not exercise Alembic.
- Deployed `tests/conftest.py` also used `Base.metadata.create_all`, which is why the missing review table was not caught by the deployed test suite.
- The current parity test is opt-in and only runs with `VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS=1` and a loopback test database.
- No test currently proves that upgrading from `0004_enterprise_governance` to the new head preserves 33 runs and 25,654 discrepancies.
- No test currently proves that the deployed review service works against a migration-built schema.

---

## 8. Compatibility risks and mitigations

| # | Risk | Impact | Likelihood | Mitigation | Gate |
| --- | --- | --- | --- | --- | --- |
| R1 | Duplicate six-column DDL from retaining `0005_verification_lineage`. | Migration fails or corrupts history; production blocked. | High if the file remains in the graph. | Retire the revision; offline-SQL test asserts no `ALTER TABLE ... ADD COLUMN` for the six columns after `0004`. | Entry + implementation. |
| R2 | Two heads from adding the governance revision beside the local branch. | `upgrade head` ambiguous; deployment script may choose the wrong branch. | High if the recovered file is added unmodified. | One linear canonical graph; `ScriptDirectory.get_current_head()` must return `0006`. | Implementation. |
| R3 | False stamping a local or production database. | Silent schema/history mismatch. | Medium if operators take shortcuts. | No stamping; rebuild local; production already truthfully at `0004`; abort on revision mismatch. | Production. |
| R4 | Deploying the current application without governance code. | Governance, sign-off, materiality, clustering, and audit functionality stop working. | High if option C is chosen. | Choose option A or B/D; make the application decision an explicit gate. | Entry. |
| R5 | Review table remains missing. | Deployed review endpoints fail; review history cannot be recorded. | Certain if `0006` is omitted while review is used. | Separate `0006`; smoke tests on isolated and rehearsal schemas. | Implementation + production. |
| R6 | Reconstructed review-table DDL differs from an unknown historical contract. | Schema drift, application errors, or hidden data incompatibility. | Medium because no migration exists. | Treat the ORM as the contract; fail-closed preflight; document inferred defaults; stop on conflicting evidence. | Implementation. |
| R7 | Production schema differs from the assumed `0004` shape. | Canonical migration may be unsafe or misleading. | Medium; only object-level production facts were supplied. | Full read-only inventory immediately before the change; compare with the recovered migration and ORM; abort on mismatch. | Production. |
| R8 | DDL locks block writes on `users`, `verification_runs`, or `verification_discrepancies`. | Brief application errors or lock timeouts. | Low; `CREATE TABLE` with new FKs is short. | Low-traffic window; `lock_timeout`; monitor locks and 5xx rates; retry only after the lock clears. | Production. |
| R9 | `is_bulk_action` default mismatch. | Raw inserts that omit the column fail if no server default exists. | Low for deployed ORM code, which sets the value; medium for future code/scripts. | Add `server_default=false` and align the ORM; test a raw insert that omits the column. | Implementation. |
| R10 | Audit chain concurrency or duplicate sequence numbers. | Chain verification may fail; governance evidence integrity at risk. | Unknown; existing behavior. | Do not change constraints in this migration; verify the existing chain; run a separate concurrency review. | Production. |
| R11 | Role header spoofing (`X-User-Role`). | A user could claim CHECKER/ADMIN authority if the deployed governance routes are ported unchanged. | Pre-existing deployed behavior; unknown production exposure. | Do not claim governance security is complete. Require a separate authorization review before enabling maker-checker in production. | Entry/security. |
| R12 | Local development data loss during rebuild. | Lost local test data. | Medium if the local DB is treated as disposable without confirmation. | Owner decision; export/reload path; no production impact. | Entry. |
| R13 | Render auto-deploy race. | New application starts before `0005`/`0006`, causing template/review failures. | Medium; dashboard behavior unknown. | Inspect Render settings; disable auto-deploy or use a controlled pre-deploy/manual sequence; verify revision before app start. | Production. |
| R14 | Alembic targets the wrong database. | Unintended production change. | Low if explicit, medium if `.env` is trusted. | Use an explicit connection/URL for the one-off job; verify database and role identity; never rely on ambient `.env`; two-person execution. | Production. |
| R15 | Rollback drops review/template data. | Permanent loss of user configuration or audit-like evidence. | Medium if downgrade is used reflexively. | App rollback first; keep additive tables; forward-fix; PITR restore to a separate branch; prohibit downgrade past `0004`; prohibit dropping non-empty review tables. | Production. |
| R16 | Server defaults and JSON types drift. | ORM/migration parity gaps; subtle insert/read differences. | Medium; current tests do not compare all defaults. | Add default/type assertions; inspect `json` vs `jsonb`; abort on mismatch. | Implementation. |
| R17 | Empty `script.py.mako`. | New revision files are empty or malformed. | Certain until fixed. | Repair the template before generating revisions; review generated files. | Implementation. |
| R18 | Untracked migration files remain outside version control. | Canonical graph is not reproducible; deployment may use stale files. | High if files stay untracked. | Commit the canonical graph and provenance record; remove retired files; verify `git status` before deployment. | Implementation. |
| R19 | Mixed application versions write and read the same tables differently. | Audit chain incomplete; reason/confidence NULLs; review data inconsistent. | Medium during rolling deploys. | Deploy one application version; avoid long dual-version windows; verify audit coverage after cutover. | Production. |
| R20 | Production review feature is not actually used, but the table is added anyway. | Low data risk; unnecessary schema surface. | Low. | Decide scope explicitly; adding an empty table is harmless but should be justified. | Entry. |

---

## 9. Isolated-database test plan

### 9.1 Safety contract

**[Proposal]**

All tests run on an isolated PostgreSQL target, never production:

- `VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS=1`
- `VERIFYGRID_TEST_DATABASE_URL` points to an explicitly validated loopback test database.
- The existing `tests/pg_test_target.py` fail-closed guard rejects production-like database names and non-loopback hosts.
- Each test creates a unique schema, runs Alembic through an explicitly validated connection, and drops the schema afterward.
- The application `DATABASE_URL` is never used as a fallback.
- No test reads `.env` or a production secret.
- No test uses `Base.metadata.create_all` to build the schema under test.

### 9.2 Test matrix

| ID | Scenario | Setup | Actions | Required assertions |
| --- | --- | --- | --- | --- |
| T1 | Fresh database migration | Empty isolated schema. | `alembic upgrade head`. | Sole head is `0006_discrepancy_review_decisions`; all eight tables exist; exact columns, nullability, PKs, FKs, unique constraints, indexes; `compare_metadata` reports no drift; template/review tables empty. |
| T2 | Production-equivalent upgrade | Build `0001 → 0004_enterprise_governance`; seed production-like data. | `alembic upgrade 0005_verification_templates`, then `0006_discrepancy_review_decisions`. | Revision advances; only the two new tables/indexes/FKs are created; no `ALTER TABLE` on existing tables; no duplicate lineage columns. |
| T3 | Data preservation | Same as T2; seed 33 runs, 25,654 discrepancies, audit events, sign-offs, roles, projects, files. | Capture per-table row fingerprints before upgrade; upgrade; capture again. | Existing row counts and fingerprints are identical; `alembic_version` changes only as expected; no governance/audit rows are updated or deleted; new tables have zero rows. |
| T4 | No duplicate DDL | Canonical graph scripts. | Generate offline SQL for `0004_enterprise_governance:0006_discrepancy_review_decisions`. | SQL contains `CREATE TABLE` for templates/review and their indexes; contains no `ALTER TABLE ... ADD COLUMN` for `sources`, `source_row_indices`, `source_records`, `child_records`, `aggregated_amount`, or `expected_amount`; contains no `DROP`. |
| T5 | Template lifecycle | Canonical schema; authenticated user. | Create/list/get/update/delete; duplicate name; cross-user access; apply to uploaded files; delete owner user. | CRUD works; defaults `visibility='personal'`, `config_version=1`; unique `(owner_id, name)` enforced; cross-user returns 404; apply validates bindings; `owner_id` becomes NULL on user delete. |
| T6 | Review decisions | Canonical schema; existing run/discrepancies. | Single review and bulk review through the deployed routes; direct ORM query; delete a discrepancy; delete a run. | One row per decision with correct `discrepancy_id`, `run_id`, `decision`, `justification`, `reviewer_id`, `previous_status`, `new_status`, `is_bulk_action`, `cluster_id`, `created_at`; cascade delete removes review rows; indexes exist; no unique constraint blocks multiple decisions. |
| T7 | Governance/sign-off | Canonical schema; users with MAKER/CHECKER/ADMIN/VIEWER roles. | Propose, approve, reject; unauthorized role attempts; sign-off details. | Maker-checker transitions work; unauthorized roles are rejected; sign-off fields and audit events are written; existing run data is not altered outside the expected fields. |
| T8 | Audit chain | Canonical schema; run with audit events. | Append events; verify chain; tamper with a payload/hash in a test transaction; verify again. | Chain verifies for untampered events; tampering is detected; `sequence_number` and `previous_event_hash` are consistent; audit trail pagination works. |
| T9 | ORM queries and physical fields | Canonical schema; reconciled ORM. | Query every model; insert/update discrepancies with `_reason_code`/`_confidence_score`; filter on `_reason_code`; insert a review row via ORM; query `AuditEvent`. | All mapped columns load; physical `reason_code`/`confidence_score` values persist and are returned; property fallback still works when values are NULL; relationships load; `compare_metadata` is clean. |
| T10 | Raw-insert defaults | Canonical schema. | Insert a review row omitting `is_bulk_action` via raw SQL; insert a user/run/discrepancy omitting governance defaults. | Server defaults apply: `is_bulk_action=false`, `users.role='MAKER'`, `sign_off_status='DRAFT'`, `currency='USD'`, `severity='medium'`, `resolution_status='unresolved'`. |
| T11 | Downgrade/empty-table policy | Canonical schema with no template/review rows. | Downgrade `0006 → 0004`; downgrade `0005 → 0004`; re-upgrade. | New tables are removed; base/governance tables and rows survive; re-upgrade restores the schema; no governance column is dropped. |
| T12 | Non-empty rollback policy | Canonical schema with template/review rows. | Attempt the documented downgrade path in a test. | The test documents that downgrade destroys rows; operational policy must require export or forward-fix instead. A production downgrade is not approved merely because the SQL succeeds. |
| T13 | Local canonical rebuild | Throwaway local schema. | Build `0001 → 0006` from scratch; compare with the migration-built test schema. | Same table/column/index/constraint set; no reliance on the retired branch; no stamp. |
| T14 | Render-like startup compatibility | Application built from the selected production version. | Start app against the canonical schema; run health and smoke endpoints. | App starts without migrations; `/health` and `/health/db` pass; template and/or governance/review routes behave as expected for the selected version. |

### 9.3 Production-like dataset

**[Proposal]**

Use synthetic data, not production row contents:

- 2–3 users with roles MAKER, CHECKER, ADMIN, VIEWER;
- 2 projects;
- 33 verification runs distributed across projects/statuses;
- 25,654 discrepancies across match statuses, including nested JSON `field_differences`, lineage fields, materiality fields, and cluster IDs;
- audit events for a subset of runs, with a valid hash chain;
- sign-off states DRAFT, PROPOSED, APPROVED, REJECTED;
- zero templates and zero review decisions before upgrade;
- representative nullable and non-null values.

Row fingerprints:

- Use a deterministic per-table digest, for example `md5(string_agg(row_to_json(t)::text, '' ORDER BY id))`, or a column-specific ordered hash for tables without `id`.
- Compare before and after migration.
- Do not export or log real production row contents.

### 9.4 Proposed commands

**[Proposal — not executed in this batch]**

```powershell
# Run from the repository root on an isolated local PostgreSQL target only.
$env:VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS = "1"
$env:VERIFYGRID_TEST_DATABASE_URL = "postgresql+psycopg://<local-user>:<local-password>@127.0.0.1:5432/<isolated-test-db>"

cd backend

# Migration parity against the canonical graph.
python -m pytest tests/test_alembic_migration_parity.py -q

# Application behavior on the Alembic-built schema.
python -m pytest tests/test_postgres_migration_application.py -q

# New reconciliation, data-preservation, review, governance, and audit tests.
python -m pytest tests/test_postgres_reconciliation_design.py -q
```

No command above may point at production. The test database URL must be supplied explicitly; do not read it from `.env`.

### 9.5 Acceptance criteria

- Single head and linear canonical graph.
- Fresh migration and production-equivalent upgrade both pass.
- Existing row counts and fingerprints are unchanged.
- 33 runs and 25,654 discrepancies survive the production-equivalent upgrade test.
- Template CRUD/apply/uniqueness/scoping pass.
- Review single/bulk persistence and cascade behavior pass.
- Governance sign-off and audit-chain tests pass.
- ORM queries against the canonical schema pass, including physical `reason_code`/`confidence_score`.
- No duplicate six-column DDL appears in offline SQL or the revision graph.
- No `compare_metadata` drift for the selected ORM target.
- Downgrade tests prove base data survives when the new tables are empty.
- No test contacts production, Neon, or Render.

### 9.6 What the tests cannot prove

- That production data values, permissions, or schema match the assumption set.
- That Render's dashboard has no hidden pre-deploy command.
- That the selected application version is the right product decision.
- That the audit chain is currently valid in production.
- That concurrent production writes will not contend with the DDL locks.
- That a future unknown object will not conflict.
- That the reconstructed review-table contract matches a lost historical artifact.

---

## 10. Render deployment and migration sequence

### 10.1 Preconditions

**[Proposal]**

Do not start the production sequence until:

1. A written application decision selects option A (keep `58a0e5c`) or option B/D (combined application).
2. The canonical graph is committed, single-headed, and reviewed.
3. The recovered `0004_enterprise_governance` file is preserved byte-identically, with its SHA-256 provenance recorded.
4. A read-only production inventory confirms:
   - `alembic_version` has exactly one row at `0004_enterprise_governance`;
   - `verification_templates` is absent;
   - `discrepancy_review_decisions` is absent;
   - the governance objects and six lineage columns match the recovered migration;
   - no unknown object conflicts.
5. A backup/PITR restore has been tested to a separate branch or database.
6. Render service configuration is known: build command, start command, pre-deploy command (if any), auto-deploy setting, and environment-variable names.
7. The change window, database owner, migration executor, reviewer, and rollback owner are named.
8. The isolated test plan has passed on a production-equivalent schema.

### 10.2 Render configuration findings

**[Repository]**

- The repository contains no `render.yaml`, Dockerfile, Procfile, backend start script, release script, or backend migration workflow.
- The deployed tree at `58a0e5c` has the same absence.
- The backend README documents a manual `alembic upgrade head` before `uvicorn`.
- No application startup path runs Alembic.
- Render dashboard behavior remains unverified.

**Consequence:** The plan must not assume that Render runs migrations. A migration command must be executed explicitly by an authorized operator or by a reviewed Render pre-deploy command. If a pre-deploy command already exists outside the repository, it must be inspected before any deploy that could trigger it.

### 10.3 Recommended sequence

**[Proposal]**

| Phase | Step | Action | Verification | Abort condition |
| --- | --- | --- | --- | --- |
| 0 | 0.1 | Freeze unrelated schema and application changes. | Change freeze recorded. | Any unrelated migration/deploy in flight. |
| 0 | 0.2 | Record production revision, live commit, row counts, and audit-chain status read-only. | `0004`, `58a0e5c`, 33 runs, 25,654 discrepancies, audit chain result. | Any mismatch with the production brief. |
| 0 | 0.3 | Confirm backup/PITR and restore test. | Restore point timestamp and successful test restore. | No verified restore. |
| 0 | 0.4 | Confirm Render settings and disable/coordinate auto-deploy. | Dashboard evidence; no deploy in progress. | Auto-deploy cannot be controlled. |
| 1 | 1.1 | Rehearse on a Neon branch or isolated restore matching production. | Apply `0005`; verify; apply `0006`; verify; deploy selected app; smoke. | Any schema/data/application failure. |
| 1 | 1.2 | Run the isolated test matrix against the rehearsal schema. | All acceptance criteria pass. | Any test failure. |
| 1 | 1.3 | Review migration SQL, inventory diff, test output, and rollback. | Two-person approval recorded. | Missing approval or unresolved risk. |
| 2 | 2.1 | Execute `0005_verification_templates` on production from an explicit one-off job. | `alembic_version` = `0005`; table/index/FK exist; row counts unchanged. | Lock timeout, revision mismatch, unexpected object, or count change. |
| 2 | 2.2 | Execute `0006_discrepancy_review_decisions`. | `alembic_version` = `0006`; table/indexes/FKs exist; row counts unchanged. | Same as above. |
| 2 | 2.3 | Deploy the selected application version. | App starts; health checks pass; selected feature smoke passes. | Startup failure or smoke failure. |
| 2 | 2.4 | Run post-deploy verification. | Section 10.5 checks pass. | Any unexpected result. |
| 2 | 2.5 | Unfreeze and record final state. | Deployment log updated. | — |

### 10.4 Command shape

**[Proposal — not executed in this batch]**

The migration must be run from `backend/` with the explicit target connection and a reviewed command. Do not rely on an ambient `.env` that might point elsewhere.

```powershell
# Authorized operator shell, from the repository root.
# Set the production connection explicitly for this process only.
$env:DATABASE_URL = "<production-connection-string-from-secret-manager>"
$env:PGOPTIONS = "-c lock_timeout=5000"

cd backend

# Apply only the reviewed revision. Do not use `head` until the graph is canonical.
alembic current
alembic upgrade 0005_verification_templates
alembic current
alembic upgrade 0006_discrepancy_review_decisions
alembic current
```

Notes:

- `DATABASE_URL` is a placeholder. Do not paste a real credential into this report, logs, chat, or tickets.
- Before executing, verify that the explicit process variable wins over `.env` and that `alembic current` reports the intended target. `backend/migrations/env.py` uses `settings.database_url` and has no CLI-level target guard. If target precedence cannot be proven, use a dedicated Alembic configuration or a one-off job with an explicit connection; do not execute against an ambiguous target.
- `alembic current` is read-only with respect to schema, but it opens a database connection. It is not run in this batch.
- The `lock_timeout` setting is an example; confirm the correct PostgreSQL client mechanism for the chosen execution environment.
- If the migration is executed through Render, the same revision targets and verification must be used, and the output must be retained.
- Do not run `alembic upgrade head` against production until the canonical graph is committed and the retired branch is gone.

### 10.5 Production verification

**[Proposal]**

Read-only schema checks:

```sql
-- Exactly one version row.
SELECT version_num FROM alembic_version;

-- New tables exist with expected columns.
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('verification_templates', 'discrepancy_review_decisions')
ORDER BY table_name, ordinal_position;

-- Constraints and indexes.
SELECT conname, contype, conrelid::regclass AS table_name
FROM pg_constraint
WHERE conrelid IN ('verification_templates'::regclass,
                   'discrepancy_review_decisions'::regclass)
ORDER BY table_name, conname;

SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('verification_templates', 'discrepancy_review_decisions')
ORDER BY tablename, indexname;

-- Row counts: unchanged production data, empty new tables.
SELECT count(*) AS runs FROM verification_runs;                    -- expected 33
SELECT count(*) AS discrepancies FROM verification_discrepancies; -- expected 25,654
SELECT count(*) AS audit_events FROM audit_events;                 -- unchanged from preflight
SELECT count(*) AS templates FROM verification_templates;          -- expected 0
SELECT count(*) AS review_decisions FROM discrepancy_review_decisions; -- expected 0
```

Read-only application checks:

- `GET /api/v1/health` → 200.
- `GET /api/v1/health/db` → 200.
- `GET /api/v1/projects` and an existing run/discrepancy read → no 500.
- Template list/read → 200 (empty before any template is created).
- Review route read/validation → expected behavior; do not create review decisions in production unless a designated test project/run and explicit approval exist.
- Audit trail and audit-chain verification for an existing run → expected result. If the chain was already broken before the migration, record it as a pre-existing finding; do not attribute it to the migration.
- Governance sign-off read for an existing run → expected data; do not propose/approve in production smoke tests.

Write checks:

- Creating and deleting a smoke template is a write. It should be explicitly approved and performed only if the product owner accepts the audit/cleanup implications.
- Review decisions and sign-off transitions are audit-relevant writes. Test them on the rehearsal, not in production, unless a dedicated test project/run is approved.

### 10.6 Rollback considerations

**[Proposal]**

| Failure point | Preferred action | Schema action | Data action |
| --- | --- | --- | --- |
| `0005` fails | Stop; inspect transaction and revision state. | PostgreSQL DDL is transactional; the failed revision should roll back. Do not stamp. | No data change expected. |
| `0005` succeeds, app fails before `0006` | Roll back app if needed; keep `0005`. | Keep `verification_templates`; it is additive and old app ignores it. | No data loss. |
| `0006` fails | Stop; inspect. | Failed revision should roll back; `0005` may remain. | No review data written yet. |
| `0006` succeeds, app fails | Roll back app to the previous version; keep the new tables. | Keep both tables. | No data loss. |
| Template migration must be undone and table is empty | Explicitly approved `alembic downgrade 0004_enterprise_governance` or a targeted drop. | Drop templates only. | Verify zero rows first. |
| Template table has user data | Do not drop. | Forward-fix. | Export/restore if necessary. |
| Review table has decisions | Do not drop. | Forward-fix. | Review decisions are audit-like; preserve or restore from PITR. |
| Governance data damaged | Restore to a separate branch; do not downgrade `0004`. | Never run `0004` downgrade on production. | PITR restore, verify, then repoint with approval. |

Hard prohibitions:

- Do not run `alembic downgrade` past `0004_enterprise_governance` on production.
- Do not drop `audit_events`, sign-off fields, materiality fields, or the six lineage columns.
- Do not stamp production to any revision.
- Do not delete `alembic_version` rows.
- Do not use `Base.metadata.drop_all` or `create_all` against production.
- Do not run a corrective migration in the same window without a new review.

### 10.7 Failure handling

**[Proposal]**

- If the migration command fails, capture the exact error, current revision, lock state, and PostgreSQL log context. Do not retry blindly.
- If the revision table is unchanged, the failed DDL transaction rolled back; investigate before retrying.
- If the revision table advanced but the table is missing, stop and treat it as a history/schema mismatch; do not stamp.
- If the application starts but template/review routes fail, check the actual schema before rolling back; the app may be pointed at the wrong database or the migration may not have run.
- If row counts change, stop and restore/compare before any further write.
- If the audit chain fails, determine whether it was already broken before the change; do not overwrite audit rows.

---

## 11. Explicit go/no-go criteria

### 11.1 Entry gates — before implementation

- [ ] Written decision: option A (keep `58a0e5c`) or option B/D (combined application).
- [ ] Canonical graph approved: `0004_enterprise_governance → 0005_verification_templates → 0006_discrepancy_review_decisions`.
- [ ] Recovered `0004_enterprise_governance` file preserved with SHA-256 provenance.
- [ ] Retired local revisions removed from the graph and from any deployment path.
- [ ] Production read-only inventory confirms revision, object absence, governance shape, and row counts.
- [ ] Backup/PITR restore tested.
- [ ] Local development data disposition decided.
- [ ] Render configuration and auto-deploy behavior known.
- [ ] Review-feature scope decided.
- [ ] Security review scheduled for role-header behavior if governance routes are ported.
- [ ] Two-person ownership assigned.

### 11.2 Implementation gates — before any production authorization

- [ ] `script.py.mako` repaired; generated revisions are valid.
- [ ] Canonical graph has one head and is linear.
- [ ] No duplicate six-column DDL in the graph or offline SQL.
- [ ] `0005` and `0006` reviewed as separate revisions.
- [ ] Template and review DDL match the approved contracts.
- [ ] ORM target updated or explicitly scoped; parity test matches the selected ORM.
- [ ] Isolated PostgreSQL tests T1–T14 pass.
- [ ] Production-equivalent upgrade preserves 33 runs and 25,654 discrepancies.
- [ ] Template CRUD/apply/uniqueness/scoping pass.
- [ ] Review single/bulk/cascade pass.
- [ ] Governance sign-off and audit-chain tests pass.
- [ ] No untracked migration artifacts remain.
- [ ] No application startup migration hook was added.

### 11.3 Production gates — before execution

- [ ] Rehearsal on a Neon branch or isolated restore passed.
- [ ] Rehearsal row counts/fingerprints match production preflight.
- [ ] Audit chain verifies on the rehearsal (or the pre-existing failure is documented).
- [ ] Template and review smoke tests pass on the rehearsal.
- [ ] Rollback/restore plan rehearsed.
- [ ] Production window approved; no conflicting deploy or long transaction.
- [ ] Explicit written authorization from the database owner and engineering lead.
- [ ] Migration executor and reviewer present.
- [ ] Production connection target identity verified.
- [ ] Render auto-deploy disabled or coordinated.

### 11.4 No-go triggers

Stop immediately if any of the following is true:

- `alembic_version` is not exactly one row at `0004_enterprise_governance`.
- `verification_templates` or `discrepancy_review_decisions` already exists.
- Any governance object, six-lineage column, type, default, index, or FK differs from the approved contract.
- The canonical graph still has two heads.
- Offline SQL shows duplicate `add_column`/`drop_column` operations for the six lineage columns.
- The recovered governance file hash differs from the approved provenance hash.
- The application decision is unresolved.
- The selected application lacks the governance port and is intended to replace `58a0e5c`.
- Backup/PITR is unavailable or untested.
- Render auto-deploy cannot be controlled.
- The review-table contract is ambiguous or conflicts with new evidence.
- Audit chain is already broken and the cause is unknown.
- Any isolated or rehearsal test fails.
- Two-person approval is missing.
- The production target identity cannot be verified.

### 11.5 Current decision

**NO-GO for production migration and deployment.**

The design is complete, but implementation and production authorization are not. The single safest next action is:

> Commit the canonical graph and the recovered governance provenance in a future authorized implementation batch, repair the revision template, update the ORM/tests for the selected application option, and prove the production-equivalent upgrade on an isolated PostgreSQL target and a Neon branch/restore. Do not connect to production or run any migration until the gates in this section are satisfied.

---

## 12. Exact files and schema objects requiring future changes

### 12.1 Migration/history files

**[Proposal]**

| File | Change | Notes |
| --- | --- | --- |
| `backend/migrations/versions/0004_enterprise_governance_and_materiality.py` | Add the recovered deployed file, byte-identical. | Revision `0004_enterprise_governance`, parent `0003_user_password`, SHA-256 `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB`. Do not edit its operations. |
| `backend/migrations/versions/0005_verification_templates.py` | Add new revision. | Revision `0005_verification_templates`, parent `0004_enterprise_governance`; DDL from the current template migration. |
| `backend/migrations/versions/0006_discrepancy_review_decisions.py` | Add new revision. | Revision `0006_discrepancy_review_decisions`, parent `0005_verification_templates`; reconstructed review-table DDL. |
| `backend/migrations/versions/0004_verification_templates.py` | Retire/remove from the graph. | Reissued as `0005_verification_templates`. |
| `backend/migrations/versions/0005_verification_lineage.py` | Retire/remove from the graph. | Do not replay; six columns are governance-owned. |
| `backend/migrations/script.py.mako` | Repair the empty template. | Currently 0 bytes; blocks safe revision generation. |
| `backend/migrations/env.py` | Keep/commit the explicit test-connection path. | Pre-existing modification; must be reviewed and committed as part of the implementation, not left untracked. |
| `docs/audits/` provenance record | Add a short provenance note for the recovered governance file. | Record source commit, path, SHA-256, and retrieval date; do not edit the recovered file. |

### 12.2 ORM/application files for the combined target

**[Proposal]**

| File | Change |
| --- | --- |
| `backend/app/models/user.py` | Add `role`. |
| `backend/app/models/verification_run.py` | Add sign-off, materiality, clustering fields; map `_reason_code`/`_confidence_score`; add review relationship/class. |
| `backend/app/models/audit_log.py` | Add `AuditEvent`. |
| `backend/app/models/review.py` | Remove empty file or re-export the review model. |
| `backend/app/models/__init__.py` | Register `AuditEvent` and `DiscrepancyReviewDecision`. |
| `backend/app/schemas/review.py` | Replace empty file with review schemas. |
| `backend/app/schemas/audit.py` | Add audit schemas. |
| `backend/app/schemas/governance.py` | Add governance schemas. |
| `backend/app/schemas/recipe.py` | Add recipe schemas if recipes are in scope. |
| `backend/app/schemas/auth.py` | Add role to register/response if role management is required. |
| `backend/app/services/review_service.py` | Replace empty file with deployed implementation. |
| `backend/app/services/audit_service.py` | Replace empty file with deployed hash-chain implementation. |
| `backend/app/services/clustering_service.py` | Add. |
| `backend/app/services/materiality_engine.py` | Add. |
| `backend/app/services/governance_service.py` | Add. |
| `backend/app/services/recipe_service.py` | Add if recipes are in scope. |
| `backend/app/services/verification_engine.py` | Write governance/physical fields; integrate materiality/clustering. |
| `backend/app/services/project_service.py` | Preserve role-aware behavior if ADMIN semantics are required. |
| `backend/app/api/v1/endpoints/audit.py` | Replace empty file with audit routes. |
| `backend/app/api/v1/endpoints/review.py` or `reviews.py` | Add review routes under one consistent module name. |
| `backend/app/api/v1/endpoints/governance.py` | Add governance routes. |
| `backend/app/api/v1/endpoints/recipes.py` | Add recipe routes if in scope. |
| `backend/app/api/v1/router.py` | Register review, governance, audit, recipe routers. |
| `backend/app/api/v1/endpoints/auth.py` | Persist/return role if role management is required. |
| `backend/tests/test_alembic_migration_parity.py` | Update expected head/parent and canonical ORM expectations. |
| `backend/tests/test_postgres_migration_application.py` | Update expected head; add template/review/governance assertions. |
| New PostgreSQL test module(s) | Add T2–T14 coverage. |
| Ported deployed tests | Governance/audit, exception clustering, materiality, recipes. |

### 12.3 Exact schema objects

**[Proposal]**

New objects:

- `verification_templates` table with 10 columns.
- `verification_templates_pkey`.
- `uq_verification_templates_owner_name`.
- `ix_verification_templates_owner_id`.
- FK `verification_templates.owner_id → users.id` `ON DELETE SET NULL`.
- `discrepancy_review_decisions` table with 12 columns.
- `discrepancy_review_decisions_pkey`.
- FK `discrepancy_review_decisions.discrepancy_id → verification_discrepancies.id` `ON DELETE CASCADE`.
- FK `discrepancy_review_decisions.run_id → verification_runs.id` `ON DELETE CASCADE`.
- `ix_discrepancy_review_decisions_discrepancy_id`.
- `ix_discrepancy_review_decisions_run_id`.
- `ix_discrepancy_review_decisions_reviewer_id`.
- `ix_discrepancy_review_decisions_cluster_id`.

No changes to:

- `users` columns (role already exists in production).
- `verification_runs` columns (sign-off and sources already exist).
- `verification_discrepancies` columns (materiality, clustering, reason/confidence, and lineage already exist).
- `audit_events`.
- The six lineage columns.
- Any governance index, FK, default, or constraint.

### 12.4 Files that must not change for the migration

- `backend/app/main.py` — no startup migration.
- `backend/app/db/session.py` — no `create_all` or migration execution.
- `backend/alembic.ini` — no target URL hard-coding.
- No production `.env`, Render environment variable, or secret.
- No remote infrastructure configuration.

---

## 13. Commands executed and preservation record

### 13.1 Commands executed

**[Repository — read-only]**

The following command shapes were used. No command wrote to a database, ran Alembic, ran tests, or changed Git state.

```powershell
# Baseline identity and preservation.
git status --porcelain=v1 --untracked-files=all
git branch --show-current
git rev-parse HEAD
git log -1 --oneline
Test-Path docs\audits\Batch22_Migration_and_ORM_Reconciliation_Design.md
Get-Item docs\audits\Batch21_Production_Schema_Lineage_Audit.md |
  Select-Object Name,Length,LastWriteTime
Get-FileHash -Algorithm SHA256 docs\audits\Batch21_Production_Schema_Lineage_Audit.md

# File-size and empty-file confirmation.
Get-Item backend\migrations\script.py.mako |
  Select-Object FullName,Length
Get-Content backend\migrations\script.py.mako -Raw
Measure-Object -Line

# Hash every inspected source/test/report file.
Get-FileHash -Algorithm SHA256 backend\migrations\versions\0004_verification_templates.py
Get-FileHash -Algorithm SHA256 backend\migrations\versions\0005_verification_lineage.py
Get-FileHash -Algorithm SHA256 backend\migrations\env.py
Get-FileHash -Algorithm SHA256 backend\app\models\verification_template.py
Get-FileHash -Algorithm SHA256 backend\app\models\verification_run.py
Get-FileHash -Algorithm SHA256 backend\app\models\user.py
Get-FileHash -Algorithm SHA256 backend\app\api\v1\router.py
Get-FileHash -Algorithm SHA256 backend\app\main.py
Get-FileHash -Algorithm SHA256 backend\app\db\session.py
Get-FileHash -Algorithm SHA256 backend\tests\test_alembic_migration_parity.py
Get-FileHash -Algorithm SHA256 backend\tests\test_postgres_migration_application.py
Get-FileHash -Algorithm SHA256 docs\audits\Batch18_Migration_History_Divergence_Audit.md
Get-FileHash -Algorithm SHA256 docs\audits\Batch19_Migration_Reconciliation_Preparation.md
Get-FileHash -Algorithm SHA256 docs\audits\Batch20_Governance_Migration_Recovery_Audit.md
Get-FileHash -Algorithm SHA256 docs\audits\Batch21_Production_Schema_Lineage_Audit.md

# Post-report verification: exactly one new entry, unchanged hashes.
git status --porcelain=v1 --untracked-files=all
Compare-Object $before $after
git show-ref --head
Get-ChildItem -Recurse -File -Filter '*.db'
```

Read-only inspection tools used:

- Directory globs for `backend/app/models`, `backend/app/schemas`, `backend/app/services`, `backend/app/api/v1/endpoints`, `backend/migrations/versions`, and `backend/tests`.
- Content reads for the migration files, ORM models, API routers/endpoints, services, tests, `env.py`, `script.py.mako`, and Batch 18–21 reports.
- Recursive greps for `discrepancy_review_decisions`, `verification_templates`, `audit_events`, `reason_code`, `confidence_score`, `create_all`, `alembic upgrade`, and governance/review symbols.

### 13.2 Commands deliberately not executed

- No `alembic upgrade`, `downgrade`, `stamp`, `revision`, `history`, `current`, or `heads`.
- No `pytest` or other test runner.
- No `psql`, `pg_dump`, `pg_restore`, or database client.
- No Neon, Render, GitHub, or cloud API call.
- No `git add`, `git commit`, `git checkout`, `git branch`, `git tag`, `git push`, or worktree change.
- No `.env` read or environment-variable change.
- No application code or migration file edit.

### 13.3 Critical file hashes before this report

**[Repository]**

| File | SHA-256 |
| --- | --- |
| `backend/migrations/versions/0004_verification_templates.py` | `CBE7E536573D06D49E4EB2F8EFB7BD26A0D3CCA786F01EA80AE7C8E7CA74E227` |
| `backend/migrations/versions/0005_verification_lineage.py` | `645BE701DFF05FDF6D263AF678CB17E77D818CE64C00A8B9F3AF96E46E585713` |
| `backend/migrations/env.py` | `F1A56CC8A201936615DE14F7730E32265C3132AF1372EF382F485207E67F056B` |
| `backend/migrations/script.py.mako` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` (empty) |
| `backend/app/models/verification_template.py` | `4C07D82DE767AB3F6F80EF7901371701A5B503B8AF25D2A147F0758C81AC1667` |
| `backend/app/models/verification_run.py` | `B59FA3BF64072F81ED51ED8AA8BAE49150818E58890E409A02792A38D16E02BC` |
| `backend/app/models/user.py` | `3D34B163C414A375688250D9FA4283FB616EC8DE3E5069611B138B0A8847AED0` |
| `backend/app/models/audit_log.py` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` (empty) |
| `backend/app/models/review.py` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` (empty) |
| `backend/app/models/__init__.py` | `FA8CCA54BC0994B48C9C7AB45AEB7277284DE1D44C96E411C70F5A4DBA76D41C` |
| `backend/app/api/v1/router.py` | `1FF4256E68BDDC624E0DCB0A5E5DACA821B8D6CA29487F90F1A3057A95017E25` |
| `backend/app/main.py` | `8A21322879D8766D9C3BE3C12684162A8857A621C9B2E96813B98AA12C6E68C5` |
| `backend/app/db/session.py` | `99C64CC6D81A371F8AE98B02386BE7A738A38A43FD5FF488145DCBB0F6153A3A` |
| `backend/tests/test_alembic_migration_parity.py` | `FDED1D66792FF3C1F24A0C6C942F162B01F2C3D8691BA40716AA4BB7199E4822` |
| `backend/tests/test_postgres_migration_application.py` | `B53F99448ACAD210C8282ED2B07B3DC2C3A5DAF9495513F703AC23819E46EACF` |
| `docs/audits/Batch18_Migration_History_Divergence_Audit.md` | `1434845A691EB60C9FD34B8C7EACBA5079A7CE667E8DDCB80D4B2578AE037655` |
| `docs/audits/Batch19_Migration_Reconciliation_Preparation.md` | `DDA7AB82B5D799D9BC1EF1A12D23E392F507DCE801275BF4A89B8D637DCE856F` |
| `docs/audits/Batch20_Governance_Migration_Recovery_Audit.md` | `0F4D4E58536CB342D34F4EA2D8C0229F970A2F7844C037F9A7230DF1069F3A3D` |
| `docs/audits/Batch21_Production_Schema_Lineage_Audit.md` | `DF6A89BCC980C029173F9C6A51F66AEFC96826B041C8215CD4956DAE74CA8E8B` |

Recovered deployed governance migration:

| File | SHA-256 |
| --- | --- |
| `...\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\migrations\versions\0004_enterprise_governance_and_materiality.py` | `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` |

### 13.4 Files changed by this batch

Only one file was created:

- `docs/audits/Batch22_Migration_and_ORM_Reconciliation_Design.md`

No application code, ORM model, migration file, test, configuration, environment file, or prior audit report was changed.

### 13.5 Preservation statement

- The 67 pre-existing working-tree entries were not modified.
- The Batch 22 report adds one untracked file. The post-report working-tree entry count is **68**.
- A `Compare-Object` of the before/after `git status` output shows exactly one new line: `?? docs/audits/Batch22_Migration_and_ORM_Reconciliation_Design.md`.
- The HEAD remains `c91e9b37074483eeb7469dc943e1735fd5f5be02`.
- The key file hashes after the report are identical to the pre-report hashes in section 13.3.
- No file was staged, committed, or pushed.
- No database, Alembic revision, test, environment, deployment, or remote resource was changed.
- The report is an untracked audit artifact, consistent with the prior Batch 18–21 reports.

### 13.6 Files inspected

**[Repository]**

Migrations and environment:

- `backend/migrations/versions/0001_initial_tables.py`
- `backend/migrations/versions/0002_verification_runs.py`
- `backend/migrations/versions/0003_user_password.py`
- `backend/migrations/versions/0004_verification_templates.py`
- `backend/migrations/versions/0005_verification_lineage.py`
- `backend/migrations/env.py`
- `backend/migrations/script.py.mako`

Models, schemas, services, and API:

- `backend/app/models/__init__.py`
- `backend/app/models/user.py`
- `backend/app/models/project.py`
- `backend/app/models/source_file.py`
- `backend/app/models/verification_run.py`
- `backend/app/models/verification_template.py`
- `backend/app/models/audit_log.py` (empty)
- `backend/app/models/review.py` (empty)
- `backend/app/schemas/auth.py`
- `backend/app/schemas/review.py` (empty)
- `backend/app/services/template_service.py`
- `backend/app/services/review_service.py` (empty)
- `backend/app/services/audit_service.py` (empty)
- `backend/app/services/verification_engine.py`
- `backend/app/api/v1/router.py`
- `backend/app/api/v1/endpoints/auth.py`
- `backend/app/api/v1/endpoints/templates.py`
- `backend/app/api/v1/endpoints/reviews.py` (empty)
- `backend/app/api/v1/endpoints/audit.py` (empty)
- `backend/app/main.py`
- `backend/app/db/session.py`

Tests and prior audits:

- `backend/tests/conftest.py`
- `backend/tests/test_alembic_migration_parity.py`
- `backend/tests/test_postgres_migration_application.py`
- `backend/tests/test_batch11_templates.py`
- `backend/tests/test_batch13_template_workflow.py`
- `backend/tests/test_batch14_college_pilot_audit.py`
- `docs/audits/Batch18_Migration_History_Divergence_Audit.md`
- `docs/audits/Batch19_Migration_Reconciliation_Preparation.md`
- `docs/audits/Batch20_Governance_Migration_Recovery_Audit.md`
- `docs/audits/Batch21_Production_Schema_Lineage_Audit.md`
- `docs/NEON_MIGRATION_RECONCILIATION_PLAN.md`
- `README.md`
- `backend/README.md`

Deployed source at `58a0e5c`:

- `backend/migrations/versions/0004_enterprise_governance_and_materiality.py`
- `backend/app/models/user.py`
- `backend/app/models/verification_run.py`
- `backend/app/models/audit_log.py`
- `backend/app/services/review_service.py`
- `backend/app/services/governance_service.py`
- `backend/app/services/audit_service.py`
- `backend/app/services/clustering_service.py`
- `backend/app/services/materiality_engine.py`
- `backend/app/api/v1/router.py`
- `backend/app/api/v1/endpoints/review.py`
- `backend/app/api/v1/endpoints/governance.py`
- `backend/app/api/v1/endpoints/audit.py`
- `backend/app/api/v1/endpoints/recipes.py`
- `backend/tests/conftest.py`
- `backend/tests/test_exception_clustering.py`
- `backend/tests/test_governance_audit.py`

---

## 14. Final verdict

### 14.1 Verdict

**PASS — design scope only.**

This report completes the required design, reconciliation plan, risk analysis, isolated test plan, deployment/rollback plan, and go/no-go gates. It does not implement, authorize, or execute any change.

### 14.2 Verdict qualifications

- **Not a PASS for reconciliation.** The canonical graph is proposed, not committed.
- **Not a PASS for migration readiness.** No implementation, isolated test run, Neon branch rehearsal, backup verification, or production authorization exists.
- **Not a PASS for ORM compatibility.** The current ORM is not a complete contract for the governance schema. A combined application port or an explicit schema-only decision is required.
- **Not a PASS for Neon.** Neon was not contacted.
- **Not a PASS for Render.** Render dashboard configuration and logs were not inspected.
- **Not a PASS for governance functionality.** A schema-only change preserves data and objects, but the current application does not maintain role, sign-off, materiality, clustering, review, or audit behavior.
- **Not a PASS for historical completeness.** The deployed review table has no migration; its contract is reconstructed from the ORM.
- **Not a PASS for revalidation.** No test was run in this batch.

### 14.3 Single safest next action

**Do not migrate production yet.** In a future authorized implementation batch:

1. Commit the recovered `0004_enterprise_governance` file with provenance.
2. Retire the local `0004_verification_templates` and `0005_verification_lineage` branch.
3. Add `0005_verification_templates` and `0006_discrepancy_review_decisions`.
4. Repair `script.py.mako`.
5. Reconcile the ORM/application for option B/D, or explicitly select option A and keep `58a0e5c`.
6. Prove the production-equivalent upgrade and all T1–T14 tests on isolated PostgreSQL.
7. Rehearse on a Neon branch or isolated restore.
8. Return for production authorization with the evidence required by section 11.

Until then, production remains **NO-GO** for migration and deployment.

---

*End of Batch 22 report.*
