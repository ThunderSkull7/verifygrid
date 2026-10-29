# Neon Migration Reconciliation Plan

**Batch:** 15, updated in Batch 16
**Status:** Planning and local evidence only. Repository migration drift was
repaired locally in Batch 16; no cloud reconciliation was executed.
**Neon connection:** Not made. No read, write, probe, migration, or history query was executed against Neon.
**Execution script:** None. This document intentionally contains no runnable reconciliation script.

## 1. Purpose

Define a safe, reviewable path to reconcile the repository's Alembic history and
ORM model contract with the Neon-hosted database, without repeating the schema
drift discovered locally and without risking existing cloud data.

This plan exists because Batch 15 established two independent facts:

1. The repository migrations did not build the schema the current ORM models
   expect.
2. The repository already records that the cloud database has a divergent
   migration history.

Batch 16 repaired fact 1 locally by adding revision
`0005_verification_lineage` and proving it on isolated PostgreSQL. Fact 2 is
unchanged: the actual Neon schema and migration history remain unverified.
Neither fact can be resolved safely by connecting to Neon and letting Alembic
choose a path automatically.

## 2. Scope and non-goals

**In scope**

- Documenting the current migration graph and observed model drift.
- Defining evidence required before any Neon change.
- Defining a branch-first rehearsal and approval process.
- Defining verification and rollback criteria.
- Assigning explicit decision ownership.

**Out of scope**

- Connecting to Neon in Batches 15–16.
- Running `alembic upgrade`, `stamp`, `downgrade`, or autogenerate against Neon.
- Deleting, truncating, resetting, or rebuilding the cloud database.
- Editing historical migrations that may already be applied elsewhere.
- Writing or shipping an executable reconciliation script.
- Making a production deployment decision.

## 3. Safety rules and non-negotiables

1. **No automatic reconciliation.** Alembic must never be allowed to infer or
   rewrite history on a database whose actual graph is unknown.
2. **No direct production-first work.** Any rehearsal happens on a dedicated
   Neon branch or a restored copy, never on the primary branch.
3. **Read-only inventory first.** Schema inspection must use catalog metadata
   only. Row data is not needed for migration planning.
4. **No credentials in tickets, documents, logs, or chat.** Use a secret manager
   or environment injection. Do not paste connection strings.
5. **Forward-only by default.** Prefer additive, reviewed migrations. Rewriting
   or stamping history requires a separate, explicit decision.
6. **One change set, one purpose.** Do not combine schema repair, data backfill,
   and unrelated feature work in the same migration.
7. **Backup/restore point before mutation.** A verified restore mechanism must
   exist before the production window opens.
8. **Two-person review.** The migration author and the database owner must both
   approve the inventory, migration, verification queries, and rollback plan.
9. **Fail closed.** If the inventory is incomplete, ambiguous, or contradicts
   the repository, stop. Do not "try it and see".
10. **Application compatibility before cutover.** Deploy code only when the
    target schema satisfies the runtime ORM contract.

## 4. Local evidence collected in Batches 15–16

All evidence below comes from a temporary local PostgreSQL 18 cluster on
loopback, plus read-only catalog inspection of the local development database.
Neither Neon nor the ordinary development database was used for tests or
modified.

### 4.1 Migration-built schema (Batch 15 observation)

Applying the committed graph `0001_initial_tables` → `0002_verification_runs` →
`0003_user_password` → `0004_verification_templates` to a throwaway database
created the expected tables, foreign keys, and indexes, but omitted six columns
required by the current models:

| Table | Missing column |
| --- | --- |
| `verification_runs` | `sources` |
| `verification_discrepancies` | `source_row_indices` |
| `verification_discrepancies` | `source_records` |
| `verification_discrepancies` | `child_records` |
| `verification_discrepancies` | `aggregated_amount` |
| `verification_discrepancies` | `expected_amount` |

`alembic_version` was the only extra table. No table, foreign-key, or index
mismatch was found beyond the missing columns. This was the pre-repair state;
Batch 16 adds those columns in revision `0005_verification_lineage`.

### 4.2 Local development database

Read-only catalog inspection showed the local `verifygrid` database at revision
`0004_verification_templates` with the same six columns missing. It was not
changed and was not used as a test database.

### 4.3 Application impact

- Templates can be created against the migrated tables.
- Multi-source run persistence writes `verification_runs.sources`, so it fails
  on a schema without that column.
- Retrieving discrepancies selects the missing lineage columns, so persisted
  result reads also fail.
- Tests that pass against a model-created schema do **not** prove migration
  compatibility. Batch 15 reports them separately.

### 4.4 Repository-recorded cloud divergence

The header of `0004_verification_templates.py` records that the cloud database
had a divergent history identified as `0004_enterprise_governance` and was not
touched. This is repository evidence, not a Batch 15 observation. The actual
Neon schema and history remain unverified.

### 4.5 Batch 16 local repair and evidence

Revision `0005_verification_lineage` is a child of
`0004_verification_templates`. It adds only the six columns below. Every column
is nullable, has no server default, and requires no backfill:

| Column | PostgreSQL type | Nullable | Default | Backfill |
| --- | --- | --- | --- | --- |
| `verification_runs.sources` | `json` | yes | none | none |
| `verification_discrepancies.source_row_indices` | `json` | yes | none | none |
| `verification_discrepancies.source_records` | `json` | yes | none | none |
| `verification_discrepancies.child_records` | `json` | yes | none | none |
| `verification_discrepancies.aggregated_amount` | `double precision` | yes | none | none |
| `verification_discrepancies.expected_amount` | `double precision` | yes | none | none |

Definitions come from the current ORM (`sa.JSON` and `sa.Float`), not from the
column names. `NULL` means "this row predates the field or the field does not
apply", so no legacy value can be reconstructed. No index or foreign key is
added; the application never joins or filters on these lineage snapshots.

The revision identifier is 25 characters, within
`alembic_version.version_num VARCHAR(32)`. The downgrade drops only the six
columns and preserves base run/discrepancy rows; lineage stored in the six
columns is intentionally not recoverable after a downgrade.

Local evidence on the isolated loopback cluster:

- Migration parity: `2 passed`. The full graph upgrades from base to head,
  produces every application table, matches the six column types/nullability/
  defaults, matches primary keys, foreign keys, indexes, and unique
  constraints, reports no `compare_metadata` drift, preserves representative
  pre-existing rows, and survives downgrade plus re-upgrade.
- Migration-built application tests: `4 passed`. Three-source run persistence
  and lineage retrieval, partial split-payment aggregation persistence,
  template lifecycle and duplicate-name uniqueness, and transaction rollback
  all ran against the Alembic-built schema.
- Target guard: `11 passed`. The model-created PostgreSQL suite remains
  `12 passed` and is reported separately.

The tests create uniquely named schemas and drop them afterwards. The `public`
schema, the development database, and Neon were not touched. This evidence
establishes local repository parity only; it does not establish that the cloud
database accepts revision `0005` or that its actual history matches this graph.

## 5. Current repository migration graph

```text
0001_initial_tables
  └── 0002_verification_runs
        └── 0003_user_password
              └── 0004_verification_templates
                    └── 0005_verification_lineage  (repository head)
```

Characteristics:

- Linear, hand-written revisions.
- PostgreSQL-specific target (`postgresql+psycopg`).
- `migrations/env.py` overrides the Alembic URL from application settings
  during normal CLI use. Migration tests pass an explicitly validated
  connection instead, so they never connect to or fall back to the application
  URL.
- `0005_verification_lineage` adds the six model columns listed in section 4.5.
- No migration encodes the cloud-only `0004_enterprise_governance` revision.
- Revision `0005` has never been applied to the local development database or
  to Neon.

The repository graph now satisfies the ORM contract at its local head. It is
still **not authoritative for the cloud schema**. Treating it as authoritative
is the core failure mode this plan prevents.

## 6. Current ORM model contract

The runtime is driven by SQLAlchemy models, not by migrations. The models
expect:

- `verification_runs.sources` for the per-run source snapshot.
- Per-discrepancy `source_row_indices` and `source_records` for multi-source
  lineage.
- `child_records`, `aggregated_amount`, and `expected_amount` for split-payment
  aggregation lineage.
- `verification_templates` for reusable templates.

Any target schema must satisfy the model contract before the corresponding
features can be considered deployable. A migration that merely matches an old
migration file is not sufficient. The repository graph satisfies this contract
locally at `0005_verification_lineage`; the cloud schema still has to be
inventoried and compared.

## 7. Observed drift and deployment impact

| Area | Repository migration | Current model | Deployment impact |
| --- | --- | --- | --- |
| Template table | Created in `0004` | Matches | Template CRUD can work if the rest of the schema is sound. |
| Run source snapshot | Added in `0005` | `sources` required | Migration-built local persistence succeeds; cloud state is unverified. |
| Multi-source lineage | Added in `0005` | `source_row_indices`, `source_records` required | Migration-built local reads succeed; cloud state is unverified. |
| Aggregation lineage | Added in `0005` | Three columns required | Migration-built local aggregation persistence succeeds; cloud state is unverified. |
| Cloud history | Unknown / divergent | Model-driven runtime | Cannot be planned without a read-only inventory. |

**Classification:** the local repository migration defect is resolved and
verified on isolated PostgreSQL. Neon remains a deployment blocker: its actual
schema, history, and response to revision `0005` are unknown. Do not claim
persistent multi-source or aggregation readiness on Neon until the inventory
and branch rehearsal in this plan are complete.

## 8. Why automatic reconciliation is prohibited

1. Alembic cannot know whether a missing column was never created, intentionally
   removed, renamed, or created under a different history.
2. `alembic stamp` would make the version table claim a state the schema may not
   have. That converts a visible failure into silent corruption.
3. Autogenerate compares models to a live database; without a reviewed baseline
   it can propose destructive drops for objects it does not recognize.
4. The cloud history reportedly contains revisions absent from this repository.
   A local head calculation cannot reason about them.
5. A failed migration on a pooled production database can leave a partially
   applied state and block application startup.
6. The correct artifact is a reviewed, additive migration with a known
   preconditions check — not an improvisation during a deployment window.

## 9. Neon-specific unknowns and required inventory

Before any change, the database owner must collect the following on a **Neon
branch**, using catalog metadata only:

1. Current database, role, and branch identity (no credentials in the record).
2. Full `alembic_version` contents.
3. Complete table, column, type, nullability, default, foreign-key, index, and
   constraint inventory for the `public` schema.
4. Whether the six model columns exist, and if so with what types and defaults.
   Revision `0005` is a candidate only when the inventory confirms the
   expected base tables and a history that can accept this child revision. If
   any column already exists with an incompatible definition, stop and re-plan
   instead of applying it blindly.
5. Whether any cloud-only tables or columns overlap with application tables.
6. Whether `0004_enterprise_governance` (or any other revision) has a
   corresponding migration file anywhere outside this repository.
7. Row-count estimates only for tables that would be backfilled; no row contents.
8. Extension dependencies, ownership, and role privileges relevant to DDL.
9. Neon branch/restore capabilities and the chosen restore point.

**Exit criterion:** a written inventory that is internally consistent and
reviewed by both the migration author and the database owner. If any item is
missing, the plan stops at this gate.

## 10. Reconciliation strategy options

### Option A — Additive forward migration from the repository graph (recommended)

Author a new revision after `0004_verification_templates` that adds only the
columns the models require, with explicit types, nullability, defaults, and
backfill behavior. Rehearse on a Neon branch whose inventory matches the target.

Batch 16 implemented this option locally as `0005_verification_lineage` and
verified it on isolated PostgreSQL. That does not authorize applying it to Neon;
the branch rehearsal and approvals below are still required.

**Pros:** preserves history, reviewable, reversible with a prepared down
migration or restore point.
**Cons:** requires the cloud history to accept a new child revision; may need a
merge revision if the cloud branch is genuinely divergent.
**Use when:** inventory confirms the existing tables and only the known columns
are missing.

### Option B — Merge revision for two histories

If the cloud contains `0004_enterprise_governance` and both histories must be
preserved, author a merge revision with two parents after both graphs are
understood.

**Pros:** preserves both histories without stamping.
**Cons:** requires the missing cloud revision file(s); otherwise the graph
cannot be reproduced locally.
**Use when:** the cloud revision file is recovered and reviewed.

### Option C — Fresh branch rebuild and data copy

Create a new Neon branch/database from the canonical migration graph, verify it,
then migrate data through a reviewed export/import process.

**Pros:** produces a clean, reproducible schema.
**Cons:** highest operational risk; requires downtime or dual-write planning;
data copy is outside this plan.
**Use when:** the existing history cannot be reconstructed or is irreparably
divergent.

### Option D — Stamp the cloud database to repository head

**Rejected.** It asserts a schema state that has not been proven and hides drift.
It must not be used as a shortcut.

**Recommendation:** start with Option A. Escalate to Option B only if the
inventory proves two legitimate histories. Consider Option C only if the cloud
history cannot be reconstructed. Do not use Option D.

## 11. Manual rehearsal and rollout runbook

This is a sequence of review gates, not an executable procedure. Any concrete
commands or SQL must be authored separately, reviewed, and run by the database
owner.

### Gate 0 — Freeze and identify

- Freeze unrelated schema changes.
- Identify the Neon branch, restore point, and accountable owner.
- Confirm no application deployment will occur during the rehearsal.

### Gate 1 — Read-only inventory

- Collect the inventory in section 9 on a branch.
- Compare it with the local migration-built schema and the ORM metadata.
- Record every difference, including extras, not only missing columns.

### Gate 2 — Choose the strategy

- Select Option A, B, or C with written rationale.
- If Option B, recover and review the missing revision file(s) first.
- If the inventory contradicts the repository, stop and re-plan.

### Gate 3 — Author the migration

- Add one forward revision with a single purpose.
- Include explicit preconditions and a documented down path or restore strategy.
- Do not edit applied historical revisions.
- Add automated model-vs-migration parity coverage in CI where feasible.
- Revision `0005_verification_lineage` is the local candidate. If the cloud
  inventory requires a merge or a different parent, author that revision
  separately and do not force this one onto an incompatible history.

### Gate 4 — Rehearse on a branch

- Apply the migration to the branch.
- Run the PostgreSQL integration suite against the branch schema, not a
  model-created schema.
- Run the migration-parity and migration-built application suites against the
  branch schema.
- Run template CRUD, multi-source persistence, result retrieval, and aggregation
  smoke tests.
- Confirm the application starts and health checks pass.

### Gate 5 — Review and approve

- Two-person review of migration, inventory diff, rehearsal output, and rollback.
- Record explicit go/no-go. A missing approval is a no-go.

### Gate 6 — Production window

- Confirm restore point.
- Apply only the reviewed revision.
- Verify `alembic_version`, the six columns, and application health.
- Stop on the first unexpected result; do not layer corrective migrations in the
  same window.

### Gate 7 — Post-change verification

- Re-run the persistence and retrieval smoke tests.
- Confirm no unexpected table/column loss.
- Record the final schema and revision in the deployment log.

## 12. Verification, rollback, ownership, and exit criteria

### Verification checklist

- [ ] `alembic_version` matches the approved target (`0005_verification_lineage`
      or an approved cloud-specific revision).
- [ ] `verification_runs.sources` exists with the approved type/nullability.
- [ ] All five discrepancy lineage columns exist with approved types.
- [ ] Foreign keys and indexes match the model contract.
- [ ] Template CRUD works.
- [ ] Multi-source run creation persists and returns `completed`.
- [ ] Persisted result retrieval returns lineage fields without database errors.
- [ ] Aggregation persistence works when that feature is enabled.
- [ ] Application startup and health checks pass.
- [ ] No unrelated schema objects were dropped or altered.

### Rollback

- Preferred: restore the Neon branch/restore point to the pre-change state.
- If a down migration is used, it must be rehearsed and must not drop data that
  cannot be recreated.
- Application rollback alone is insufficient if the schema changed incompatibly.
- Record the rollback decision and the exact restored point.

### Ownership

| Responsibility | Owner |
| --- | --- |
| Migration authoring and application compatibility | Backend maintainer |
| Neon inventory, branch, restore point, DDL execution | Database owner |
| Go/no-go and risk acceptance | Engineering lead |
| Post-change verification | On-call engineer plus reviewer |

### Exit criteria

The plan is complete only when:

1. The inventory is reviewed and consistent.
2. A strategy is chosen and recorded.
3. The migration is rehearsed on a branch against a migration-built schema.
4. PostgreSQL integration tests pass against that schema.
5. Rollback is rehearsed or a restore point is proven.
6. Two-person approval is recorded.
7. The production change and verification are logged.

Until then, Neon remains **Blocked / Not verified** for this release. No Batch
15 or Batch 16 work authorizes a Neon connection. Local migration parity does
not establish Neon compatibility, and the cloud's divergent history has not
been inspected.
