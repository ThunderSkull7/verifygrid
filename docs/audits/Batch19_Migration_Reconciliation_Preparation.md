# VerifyGrid Batch 19 — Migration Reconciliation Preparation

**Date:** 2026-10-29
**Batch type:** Documentation and repository audit only
**Branch:** `feature/batch-4-rule-engine-aggregation`
**HEAD:** `c91e9b37074483eeb7469dc943e1735fd5f5be02`
**Remote database:** Not contacted. No Neon, production, staging, or other remote database was inspected.
**Execution status:** Preparation only. No migration strategy is selected or authorized by this report.

## Evidence legend

- **[Confirmed from current repository evidence]** — directly observable in the current working tree, files, Git object database, or read-only command output.
- **[Reported by earlier batch]** — asserted by an earlier batch or repository document, but not independently re-established in Batch 19.
- **[Not independently verified]** — depends on a database, environment, backup system, or external source that was not inspected.
- **[Inference requiring further evidence]** — a reasoned consequence of current facts that depends on an unverified target, runtime behavior, or future decision.

A document containing a claim is current evidence that the claim was made. The truth of the claim is classified separately.

---

## 1. Executive summary

### 1.1 What this batch establishes

1. **[Confirmed from current repository evidence]** The repository still contains a single, linear Alembic chain:
   `0001_initial_tables` → `0002_verification_runs` → `0003_user_password` → `0004_verification_templates` → `0005_verification_lineage`.
   The filenames and revision identifiers agree, every parent resolves, there are no duplicate revision IDs, and `0005_verification_lineage` is the sole head.

2. **[Confirmed from current repository evidence]** `0001`–`0003` are tracked. `0004_verification_templates.py` and `0005_verification_lineage.py` remain untracked. `backend/migrations/env.py` remains modified with a 16-line addition and 2-line deletion relative to HEAD. `backend/migrations/script.py.mako` is 0 bytes.

3. **[Confirmed from current repository evidence]** The Batch 18 report exists at `docs/audits/Batch18_Migration_History_Divergence_Audit.md` and is untracked. The Batch 19 starting status list is identical to the end-of-Batch-18 status list. No unexpected content change appeared between the two batches.

4. **[Confirmed from current repository evidence]** No migration file, tracked revision, test, configuration, script, or inspected Git object contains `0004_enterprise_governance`. The identifier appears only as a prose claim in the untracked `0004_verification_templates.py` docstring and in untracked documentation.

5. **[Confirmed from current repository evidence]** The six columns added by `0005_verification_lineage` match the current ORM in type, nullability, and absence of defaults, indexes, and foreign keys:
   `verification_runs.sources`, `verification_discrepancies.source_row_indices`, `source_records`, `child_records`, `aggregated_amount`, and `expected_amount`.

6. **[Confirmed from current repository evidence]** Three server-default mismatches remain: `users.hashed_password`, `source_files.status`, and `verification_runs.status`. The migration-parity test explicitly does not compare server defaults, so a passing parity result would not close this gap.

7. **[Reported by earlier batch]** Batch 16 reported migration-parity `2 passed`, migration-built application `4 passed`, model-created PostgreSQL `12 passed`, and target-guard `11 passed` on an isolated loopback cluster. **[Not independently verified]** Those results were not rerun in Batch 19 and are not proof of the current working tree.

8. **[Not independently verified]** The actual Neon branch identity, schema, data, full `alembic_version` contents, backup status, and restore capability remain unknown. No remote connection was attempted.

### 1.2 What this batch does not establish

- It does not prove that `0004_enterprise_governance` ever existed.
- It does not prove that it did not exist elsewhere.
- It does not prove that Neon is divergent, reconciled, backed up, or safe to migrate.
- It does not select additive migration, merge revision, or rebuild as the final strategy.
- It does not authorize any migration, stamp, history edit, schema change, or production access.
- It does not make the prior Batch 16 test results current.

### 1.3 Confidence

| Area | Confidence | Basis |
| --- | --- | --- |
| Current working-tree identity and preservation | **High** | Git status, branch/HEAD, all-ref tree inspection, file hashes. |
| Repository migration graph integrity | **High** | Direct reading of all five migration files. |
| Absence of governance revision from this repository and inspected Git objects | **High** | Working-tree search, all-ref tree inspection, commit search, object search. |
| Six-column ORM/migration correspondence | **High (static)** | Direct source comparison; runtime parity not rerun. |
| Server-default discrepancies | **High (static)** | Direct source comparison; runtime/security impact unknown. |
| Prior Batch 16 test results | **None for current state** | Reported historically; not rerun in Batch 19. |
| Neon identity, history, schema, backup, and safety | **None** | No connection or authorized inventory. |
| Final reconciliation strategy | **Not selected** | Requires the inventory and owner review described below. |

### 1.4 Verdict preview

**PASS — preparation scope only.** The required reconciliation package is complete. The migration itself remains blocked, and Neon remains unverified. See section 13 for the formal verdict and qualifications.

---

## 2. Current working-tree baseline

### 2.1 Repository identity

**[Confirmed from current repository evidence]**

| Item | Current value |
| --- | --- |
| Branch | `feature/batch-4-rule-engine-aggregation` |
| HEAD | `c91e9b37074483eeb7469dc943e1735fd5f5be02` |
| HEAD subject | `feat: implement Batch 4 advanced rule engine, aggregation and split-payment reconciliation` |
| Status entries at Batch 19 start | 64 (`git status --porcelain=v1 --untracked-files=all`) |
| Modified status entries | 28 |
| Entries with textual diffs | 27 |
| Untracked status entries | 36 |
| Batch 18 report | Present, untracked, 58,088 bytes at the start of Batch 19 |

The working tree is intentionally dirty with substantial pre-existing work. No reset, clean, stash, checkout, branch switch, commit, or other state-changing Git operation was performed.

### 2.2 Difference from the Batch 18 wording

**[Confirmed from current repository evidence]** Batch 18 described 27 modified tracked files. The current `git status` has 28 `M` entries, but only 27 files appear in `git diff --stat` and `git diff --name-only`.

The extra entry is `backend/tests/test_multisource_wizard.py`:

- `git status` reports it as modified.
- `git diff -- backend/tests/test_multisource_wizard.py` is empty.
- `git diff --numstat` is empty.
- `git hash-object --path=backend/tests/test_multisource_wizard.py` equals the HEAD blob hash `670cfcfee5a2a655041c178ae044014c1ea277c1`.
- `git diff-files --raw` still reports an `M` entry because the index stat information is stale.

**[Inference requiring further evidence]** This is most consistent with a stat-only/line-ending metadata artifact, not a content change. The working-tree content is identical to HEAD for that file. Batch 18's count referred to textual diffs; Batch 19 reports the raw status count separately to avoid ambiguity. This is not a new change and was not "fixed," because refreshing the index would modify repository metadata and is outside this batch's scope.

### 2.3 Pre-existing migration-related changes

**[Confirmed from current repository evidence]**

| Path | State | Current evidence |
| --- | --- | --- |
| `backend/migrations/versions/0001_initial_tables.py` | Tracked, unmodified | Present; source read in this batch. |
| `backend/migrations/versions/0002_verification_runs.py` | Tracked, unmodified | Present; source read in this batch. |
| `backend/migrations/versions/0003_user_password.py` | Tracked, unmodified | Present; source read in this batch. |
| `backend/migrations/versions/0004_verification_templates.py` | **Untracked** | Present; source read in this batch. |
| `backend/migrations/versions/0005_verification_lineage.py` | **Untracked** | Present; source read in this batch. |
| `backend/migrations/env.py` | Modified, unstaged | 16 insertions, 2 deletions versus HEAD. |
| `backend/migrations/script.py.mako` | Tracked, unmodified | 0 bytes. |
| `backend/alembic.ini` | Tracked, unmodified | Present; not reproduced here and no URL/credential values were read into this report. |

**[Confirmed from current repository evidence]** Every inspected ref—five local branches, `origin/HEAD`, `origin/main`, and `origin/improvement/project-load-recovery`—tracks only `0001`–`0003` under `backend/migrations/versions`. None tracks `0004` or `0005`.

### 2.4 Batch 18 report and continuity

**[Confirmed from current repository evidence]**

- `docs/audits/Batch18_Migration_History_Divergence_Audit.md` exists.
- Its SHA-256 at the start of Batch 19 was `1434845A691EB60C9FD34B8C7EACBA5079A7CE667E8DDCB80D4B2578AE037655`.
- The Batch 19 starting `git status --porcelain=v1 --untracked-files=all` list is identical to the end-of-Batch-18 list saved during that audit. `Compare-Object` reported no difference.
- No unexpected new file, deletion, rename, or content change was identified between the two batches.

**[Reported by earlier batch]** Batch 18 concluded that the repository chain was internally consistent, that the governance revision was absent from the inspected repository and Git history, that the six columns matched the ORM, and that Neon remained unverified. Those conclusions are re-checked where relevant below.

### 2.5 Preservation confirmation

**[Confirmed from current repository evidence]**

- No application code, ORM model, migration, configuration, dependency, secret, or existing documentation was edited.
- No `.env` file was read.
- No database connection was attempted.
- No Alembic command was executed.
- No test suite was run.
- No Git operation changed repository state.
- The only new file is this report, `docs/audits/Batch19_Migration_Reconciliation_Preparation.md`.
- All pre-existing tracked modifications and untracked files remain present.

The only allowed new file was created after the baseline was captured. Section 12 records the final status comparison.

---

## 3. Migration evidence matrix

### 3.1 Summary matrix

All source facts below are **[Confirmed from current repository evidence]**. Test evidence is separated because none of it was rerun in Batch 19.

| Revision | File | `down_revision` | Tables affected | Objects introduced or removed | Defaults | Tracked? | Prior isolated PostgreSQL evidence | Reconfirmed here? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `0001_initial_tables` | `0001_initial_tables.py` | `None` | Creates `users`, `projects`, `source_files` | Three PKs; FKs `projects.owner_id → users.id` (`SET NULL`), `source_files.project_id → projects.id` (`CASCADE`); unique index on `users.email`; indexes on `projects.owner_id` and `source_files.project_id` | `users.created_at`/`updated_at` and `projects.created_at`/`updated_at` = `now()`; `source_files.created_at` = `now()`; `source_files.status` = `uploaded` | Yes | **[Reported by earlier batch]** Batch 16 reported the full graph built on isolated PostgreSQL; revision-specific results not independently confirmed | **No** |
| `0002_verification_runs` | `0002_verification_runs.py` | `0001_initial_tables` | Creates `verification_runs`, `verification_discrepancies` | Two PKs; FKs to projects/source_files (`CASCADE`/`SET NULL`); discrepancy FK to runs (`CASCADE`); indexes on run project/source/target/status and discrepancy run/match/category | `verification_runs.status` = `pending`; `created_at`/`updated_at` = `now()`; `verification_discrepancies.created_at` = `now()` | Yes | Same prior full-graph report; not reconfirmed | **No** |
| `0003_user_password` | `0003_user_password.py` | `0002_verification_runs` | Alters `users` | Adds `hashed_password` `String(255)`, non-null; downgrade drops it | `server_default=""` on `hashed_password` | Yes | Same prior full-graph report; not reconfirmed | **No** |
| `0004_verification_templates` | `0004_verification_templates.py` | `0003_user_password` | Creates `verification_templates` | PK; nullable `owner_id` FK to `users.id` (`SET NULL`); unique constraint `uq_verification_templates_owner_name`; index `ix_verification_templates_owner_id`; drop index/table on downgrade | `visibility` = `personal`; `config_version` = `1`; `created_at`/`updated_at` = `now()` | **No — untracked** | **[Reported by earlier batch]** Full-graph Batch 16 evidence; Batch 12 docstring also claims local application | **No** |
| `0005_verification_lineage` | `0005_verification_lineage.py` | `0004_verification_templates` | Alters `verification_runs`, `verification_discrepancies` | Adds six nullable columns; no indexes, FKs, defaults, or backfill; downgrade drops the six columns | None on the new columns | **No — untracked** | **[Reported by earlier batch]** Batch 16 reported parity and migration-built application tests; not reconfirmed | **No** |

### 3.2 Detailed operations

#### 0001 — Initial tables

**[Confirmed from current repository evidence]**

`users`:

- `id` UUID primary key, not null.
- `email` `String(255)`, not null, unique index `ix_users_email`.
- `full_name` `String(255)`, nullable.
- `created_at`, `updated_at` `DateTime(timezone=True)`, not null, `server_default=now()`.

`projects`:

- `id` UUID primary key.
- `name` `String(255)`, not null; `description` Text, nullable.
- `owner_id` UUID, nullable, FK to `users.id` with `ON DELETE SET NULL`; index `ix_projects_owner_id`.
- `created_at`, `updated_at` timestamptz, not null, `now()` default.

`source_files`:

- `id` UUID primary key.
- `project_id` UUID, not null, FK to `projects.id` with `ON DELETE CASCADE`; index.
- `original_filename` `String(255)`, `storage_path` `String(1024)`, `file_type` `String(50)`, `file_size` BigInteger, all not null.
- `status` `String(50)`, not null, `server_default="uploaded"`.
- `created_at` timestamptz, not null, `now()` default.

Downgrade drops indexes and tables in reverse dependency order. No branch or merge revision exists.

#### 0002 — Verification runs and discrepancies

**[Confirmed from current repository evidence]**

`verification_runs`:

- `id` UUID PK; `project_id` UUID not null FK `projects.id` `CASCADE`, indexed.
- `source_file_id` and `target_file_id` UUID nullable FKs to `source_files.id` `SET NULL`, indexed.
- `status` `String(50)`, not null, `server_default="pending"`, indexed.
- `key_columns` JSON not null; `column_mapping`, `configuration`, `summary` JSON nullable.
- `error_message` Text nullable; `started_at`, `completed_at` timestamptz nullable.
- `created_at`, `updated_at` timestamptz not null, `now()` default.

`verification_discrepancies`:

- `id` UUID PK; `run_id` UUID not null FK `verification_runs.id` `CASCADE`, indexed.
- `match_status` and `discrepancy_category` `String(50)`, not null, indexed.
- `key_values` JSON not null.
- `source_row_number`, `target_row_number` Integer nullable.
- `source_row_numbers`, `target_row_numbers`, `source_record`, `target_record`, `field_differences` JSON nullable.
- `message` Text nullable; `created_at` timestamptz not null, `now()` default.

Downgrade drops the discrepancy table/indexes, then the run table/indexes.

#### 0003 — Password column

**[Confirmed from current repository evidence]**

- Upgrade: `op.add_column("users", sa.Column("hashed_password", sa.String(length=255), nullable=False, server_default=""))`.
- Downgrade: `op.drop_column("users", "hashed_password")`.
- The server default is a database default, not merely a Python-side default. Its mismatch with the ORM is reviewed in section 7.

#### 0004 — Verification templates

**[Confirmed from current repository evidence]**

- Creates `verification_templates` with:
  - `id` UUID PK.
  - `owner_id` UUID nullable, FK to `users.id` `SET NULL`, indexed.
  - `name` `String(255)` not null; `description` Text nullable.
  - `mode` `String(50)` not null.
  - `visibility` `String(20)` not null, `server_default="personal"`.
  - `config_version` Integer not null, `server_default="1"`.
  - `configuration` JSON not null.
  - `created_at`, `updated_at` timestamptz not null, `now()` default.
  - Unique constraint on `(owner_id, name)` named `uq_verification_templates_owner_name`.
  - Index `ix_verification_templates_owner_id`.
- Downgrade drops the index and table.
- The file's lines 6–10 also contain the only migration-source claim about `0004_enterprise_governance`; that claim is addressed in section 5 and is not a migration operation in this repository.

#### 0005 — Lineage columns

**[Confirmed from current repository evidence]**

Upgrade adds, in order:

1. `verification_runs.sources` JSON, nullable.
2. `verification_discrepancies.source_row_indices` JSON, nullable.
3. `verification_discrepancies.source_records` JSON, nullable.
4. `verification_discrepancies.child_records` JSON, nullable.
5. `verification_discrepancies.aggregated_amount` Float, nullable.
6. `verification_discrepancies.expected_amount` Float, nullable.

No defaults, indexes, foreign keys, data updates, or backfills are added. Downgrade drops the six columns in reverse order. The migration docstring says NULL means "not recorded for this row," not missing data that can be reconstructed.

### 3.3 Graph integrity findings

**[Confirmed from current repository evidence]**

- Filenames and declared revision IDs match for all five files.
- `down_revision` values form one continuous chain with no missing parent.
- No duplicate revision identifiers exist.
- No branch labels or `depends_on` values create a second graph.
- `0005_verification_lineage` is the only head in the working tree.
- `0004_verification_templates` is the parent of `0005`; the reported governance revision is not in this chain.
- The chain is hand-written; no autogenerated migration is present.

**[Inference requiring further evidence]** A structurally valid local graph does not prove that any database's history can accept it. The graph is a set of files; the target's `alembic_version` and schema are separate facts that must be inventoried.

---

## 4. Exact read-only Neon inventory checklist

### 4.1 Purpose and boundary

This checklist is for a future authorized inspection of the intended remote database, referred to in prior documents as Neon. It must be performed on an isolated branch or other approved read-only replica—not by pointing the application or the migration CLI at the production target. No item in this checklist authorizes a write, migration, stamp, or history change.

**[Not independently verified]** The existence of a suitable Neon branch, read-only role, backup, point-in-time recovery, or restore capability is not established. Each capability must be evidenced, not assumed.

### 4.2 Authorization and database identity

Collect and record, without credentials or connection strings:

- [ ] Written authorization: named database owner, migration owner, environment owner, purpose, time window, and scope.
- [ ] Neon project identity: project name and/or approved project identifier, recorded from the Neon console/API or an owner-provided metadata record. Do not assume a SQL function exposes this.
- [ ] Exact branch identity: branch name and/or approved branch identifier; whether it is the primary branch, a child branch, or an isolated restore branch.
- [ ] Exact database name and role used for the inventory.
- [ ] Environment classification: production, staging, development, or unknown. Classification must come from the owner and deployment records, not from hostname guessing.
- [ ] Confirmation that this is the intended target. Record how the target was mapped to the application environment without reproducing credentials.
- [ ] Whether the target is the live application database, a replica, or a snapshot/branch. If unknown, stop before schema queries.
- [ ] Change freeze and incident status: confirm no deployment, migration, or schema change is in progress.

Read-only identity queries, after authorization:

```sql
SELECT current_database(),
       current_user,
       session_user,
       inet_server_addr(),
       inet_server_port(),
       version();

SHOW search_path;
```

Record the results as metadata. Do not record a connection URL or password. If the project/branch identity cannot be tied to the approved target, stop.

### 4.3 Migration history inventory

The inventory must capture **every row**, not just the latest revision.

- [ ] Locate every `alembic_version` table, including non-`public` schemas.
- [ ] Capture its schema, owner, columns, constraints, and row count.
- [ ] Capture every `version_num` value, including duplicates.
- [ ] Capture nulls, empty strings, over-length values, and formatting anomalies.
- [ ] Determine whether the table has one row (normal linear head) or multiple rows (multiple heads/branches).
- [ ] Record the exact revision identifiers verbatim in a non-secret evidence file.
- [ ] Compare every identifier with the trusted repository graph.
- [ ] Check specifically for `0004_enterprise_governance` and for any other unknown identifier.
- [ ] Determine whether every recorded revision is declared by a trusted migration file.
- [ ] Determine whether every needed parent/ancestor is present in the trusted graph.
- [ ] Determine whether the recorded history can be explained by one linear path from a trusted base to a trusted head.
- [ ] Record any history that cannot be explained, without guessing or rewriting it.

Discovery query:

```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name = 'alembic_version'
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name;
```

For each discovered schema, substitute the quoted schema name below:

```sql
SELECT version_num
FROM "<version_schema>".alembic_version
ORDER BY version_num;
```

```sql
SELECT version_num, count(*) AS occurrences
FROM "<version_schema>".alembic_version
GROUP BY version_num
ORDER BY version_num;
```

```sql
SELECT column_name, data_type, character_maximum_length,
       is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = '<version_schema>'
  AND table_name = 'alembic_version'
ORDER BY ordinal_position;
```

Compatibility criteria:

- A history is **compatible with the repository's linear chain** only if every recorded revision is declared by a trusted file, every required ancestor is present, and exactly one head resolves.
- A history is **not compatible** if it contains an unknown revision, a missing parent, multiple heads without a trusted merge, duplicate/inconsistent rows, or a revision whose file cannot be produced.
- The presence of `0004_enterprise_governance` is a finding to record, not a conclusion to assume. Its absence removes one hypothesis but does not prove the rest of the schema matches the repository.

### 4.4 Schema inventory

Capture all application-relevant objects, not only the tables named in the repository.

#### Tables and columns

- [ ] All schemas outside `pg_catalog` and `information_schema`.
- [ ] Tables, views, materialized views, foreign tables, and sequences.
- [ ] For each table: schema, name, type, owner, persistence, row-count estimate, comment.
- [ ] For each column: ordinal position, name, data type, `udt_schema`, `udt_name`, length, precision, scale, datetime precision, nullability, default, identity/generated status, generation expression, collation, comment.
- [ ] Hidden dropped columns (`pg_attribute.attisdropped`) that may reveal prior schema history.
- [ ] Column order, especially for the six lineage columns and the columns added by `0003`.

#### Constraints and indexes

- [ ] Primary keys.
- [ ] Foreign keys, including referenced schema/table/columns, `ON DELETE`/`ON UPDATE` actions, deferrability, and validation status.
- [ ] Unique constraints and unique indexes.
- [ ] Check constraints and exclusion constraints.
- [ ] Index definitions, including uniqueness, included columns, partial predicates, operator classes, and tablespace.
- [ ] Constraint and index ownership and names.
- [ ] Triggers and trigger functions.
- [ ] Row-level security policies and enabled/forced status.

#### Other schema elements

- [ ] Extensions and versions.
- [ ] Enum, domain, composite, and range types.
- [ ] Functions, procedures, aggregates, and their ownership/privileges.
- [ ] Sequences and ownership links.
- [ ] Views and materialized views.
- [ ] Comments and security labels.
- [ ] Publications/subscriptions or other replication objects, if present.
- [ ] Any object not represented by the repository migration chain.

#### Expected repository tables

The repository chain creates these application tables:

- `users`
- `projects`
- `source_files`
- `verification_runs`
- `verification_discrepancies`
- `verification_templates`

plus Alembic's `alembic_version`. Any other table or schema object must be recorded as an addition and assessed, not ignored.

Catalog query templates:

```sql
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name;
```

```sql
SELECT table_schema, table_name, ordinal_position, column_name,
       data_type, udt_schema, udt_name,
       character_maximum_length, numeric_precision, numeric_scale,
       datetime_precision, is_nullable, column_default,
       is_identity, is_generated, generation_expression
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
```

```sql
SELECT n.nspname AS schema_name,
       c.relname AS table_name,
       con.conname AS constraint_name,
       con.contype AS constraint_type,
       pg_get_constraintdef(con.oid, true) AS definition
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, con.conname;
```

```sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
```

```sql
SELECT extname, extversion, n.nspname AS extension_schema
FROM pg_extension e
JOIN pg_namespace n ON n.oid = e.extnamespace
ORDER BY extname;
```

```sql
SELECT n.nspname AS schema_name,
       c.relname AS relation_name,
       c.relkind,
       pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname;
```

For views, materialized views, functions, triggers, policies, domains, and enum labels, capture the corresponding catalog definitions or `information_schema` rows. Store definitions, not row contents. If a definition contains sensitive literals, redact those literals before sharing the evidence file.

#### Six lineage columns

Check each expected column individually:

```sql
SELECT table_name, column_name, data_type, udt_name,
       is_nullable, column_default, ordinal_position
FROM information_schema.columns
WHERE (table_name = 'verification_runs'
       AND column_name = 'sources')
   OR (table_name = 'verification_discrepancies'
       AND column_name IN ('source_row_indices',
                           'source_records',
                           'child_records',
                           'aggregated_amount',
                           'expected_amount'))
ORDER BY table_name, ordinal_position;
```

Also check for hidden dropped columns and constraints/indexes that mention those names. A column existing under a different type, a `jsonb` column where the ORM expects `json`, or a column with an unexpected default is a conflict, not a match.

#### Row counts and data safety

- [ ] Record row-count estimates only for tables whose data could affect a backfill or validation.
- [ ] Do not export row contents as part of the migration inventory.
- [ ] If a later reconciliation requires data validation, define a separate owner-approved, privacy-reviewed query.
- [ ] Record whether the six lineage columns contain any non-null data; a non-null value must never be dropped or overwritten as part of an unplanned migration.

Optional estimate query:

```sql
SELECT schemaname, relname, n_live_tup
FROM pg_stat_user_tables
ORDER BY schemaname, relname;
```

### 4.5 Operational safety inventory

#### Role and privileges

- [ ] Current role, session role, and role memberships.
- [ ] Superuser, create-role, create-database, login, replication, and bypass-RLS attributes.
- [ ] Schema ownership and `USAGE`/`CREATE` privileges.
- [ ] Table, sequence, function, and type ownership and privileges.
- [ ] Default privileges and role memberships that could grant DDL.
- [ ] Whether the inventory role is genuinely read-only; record any DDL/DML capability even if unused.
- [ ] Whether the application role differs from the inventory role and from the migration role.

```sql
SELECT current_database(), current_user, session_user,
       inet_server_addr(), inet_server_port();

SELECT rolname, rolsuper, rolcreaterole, rolcreatedb,
       rolcanlogin, rolreplication, rolbypassrls
FROM pg_roles
WHERE rolname IN (current_user, session_user);
```

```sql
SELECT n.nspname,
       pg_get_userbyid(n.nspowner) AS schema_owner,
       has_schema_privilege(current_user, n.oid, 'USAGE') AS can_use,
       has_schema_privilege(current_user, n.oid, 'CREATE') AS can_create
FROM pg_namespace n
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname;
```

```sql
SELECT schemaname, tablename,
       has_table_privilege(current_user,
                           format('%I.%I', schemaname, tablename),
                           'SELECT') AS can_select,
       has_table_privilege(current_user,
                           format('%I.%I', schemaname, tablename),
                           'INSERT') AS can_insert,
       has_table_privilege(current_user,
                           format('%I.%I', schemaname, tablename),
                           'UPDATE') AS can_update,
       has_table_privilege(current_user,
                           format('%I.%I', schemaname, tablename),
                           'DELETE') AS can_delete
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename;
```

#### Backup and restore evidence

Do not assume any backup, point-in-time recovery, branch, or clone feature exists. Require the database owner to provide:

- [ ] The backup/recovery mechanism and retention window.
- [ ] The timestamp and identity of the most recent verified recovery point.
- [ ] A restore test to a separate branch or isolated environment, with the restore timestamp and operator.
- [ ] Verification that the restore is usable: it connects, has the expected schema, and has plausible table counts.
- [ ] The exact restore-target identity, kept separate from the live target.
- [ ] Evidence that restoring or creating a rehearsal environment will not modify the live target.
- [ ] A named owner for the restore and a rollback/abort decision.

A statement that "the provider has backups" is not sufficient. Without a successful restore test, backup status is **not independently verified** and migration work remains blocked.

#### Rehearsal capability

- [ ] Can an isolated branch or disposable database be created from the target's current state?
- [ ] Is that environment network-isolated from production?
- [ ] Can the migration run there without touching the live target?
- [ ] Can the schema and representative data be verified there?
- [ ] Can the environment be destroyed after rehearsal?
- [ ] Who authorizes creation, migration, verification, and destruction?

If the answer to any of these is unknown, the inventory is incomplete and no migration should be planned for execution.

### 4.6 Evidence record and exit criteria

The inventory record must include:

- [ ] Date, time zone, operator, reviewer, and authorization reference.
- [ ] Project/branch/database/role identity, with no credentials.
- [ ] Exact query text used for catalog inspection.
- [ ] Raw output or an unambiguous summary, with sensitive literals redacted.
- [ ] Repository commit and working-tree state used for comparison.
- [ ] File hashes for the trusted migration files and ORM sources.
- [ ] A difference report against the repository's migration-built schema and ORM.
- [ ] A list of unknowns, contradictions, and follow-up questions.

**Exit criterion:** a written inventory that is internally consistent and reviewed by both the migration author and the database owner. If any item is missing or contradictory, the plan stops at this gate. No migration strategy is selected before this criterion is met.

---

## 5. Reconciliation decision matrix

### 5.1 Summary

No final strategy is selected. The following table summarizes the decision logic; the subsections define the evidence, risks, permitted actions, prohibitions, and authorization for each scenario.

| Scenario | Decisive evidence | Potential path after evidence | Primary blocker | Execution authorization |
| --- | --- | --- | --- | --- |
| 1. Governance file recovered | Trusted file, provenance, graph position, operations, target applicability | Merge revision or new additive revision, or rebuild if needed | File may be unverified, tampered, or inapplicable | Migration author + DB owner + technical lead; production change approval |
| 2. Revision exists remotely, file unavailable | Full history/schema, logs, artifacts, backups, owner knowledge | Recover original; otherwise controlled rebuild or newly authored reviewed migration | Cannot know semantics from revision ID/name | DB owner + migration owner + release manager; security/data owner review |
| 3. Revision absent from intended DB | Identity confirmation, full history, schema comparison | Possibly additive path if history/schema match; otherwise continue investigation | Absence does not prove overall compatibility | DB owner + migration author; standard change approval |
| 4. Multiple/inconsistent revisions | All version rows, graph analysis, schema-vs-history comparison, artifacts | Merge, additive, rebuild, or further investigation | Unknown ancestry and multiple heads | DB owner + migration author + release manager; incident/change process |
| 5. Identity/backup unestablished | Owner attestation, target identity, verified restore | None yet; remain blocked | Cannot prove target or rollback | Infra/DB owner; no execution authorization |

### 5.2 Scenario 1 — The governance migration is recovered

**Hypothesis:** A trustworthy original file is recovered from a verified source.

**Evidence required:**

- The complete file, not a snippet or a filename.
- Revision ID, `down_revision`, `branch_labels`, and `depends_on` values.
- Full upgrade and downgrade operations, including DML, backfills, triggers, and data transformations.
- Column types, nullability, defaults, constraint/index names, and dependency order.
- Provenance: source system, repository/commit or artifact identifier, author, date, checksum, review history, and chain of custody.
- Proof that this exact file was the one applied to the intended database/branch, not merely a file that existed in another environment.
- Comparison with `0003_user_password`, `0004_verification_templates`, and `0005_verification_lineage`.
- Confirmation of whether the file is an ancestor, a sibling branch, or a replacement history.
- A static review of idempotency, transaction behavior, lock impact, and downgrade safety.

**Risks:**

- The file may be tampered with, incomplete, or from a different project.
- It may contain destructive DML or a backfill that is unsafe on current data.
- It may create objects that overlap with `0004` or `0005`.
- Its revision ID may collide with a different revision or its parent may be missing.
- Applying it on the wrong branch can produce a false history even if the SQL succeeds.

**Permitted read-only actions:**

- Read and parse the file.
- Compute and compare hashes.
- Inspect its provenance and related commits/artifacts.
- Build a static graph and compare it with the repository graph and the inventory.
- Ask the owner to confirm whether it was applied to the target.

**Prohibited actions:**

- Executing the recovered file against Neon, production, staging, or any unapproved database.
- Editing an already-applied historical revision.
- Copying the file into the repository without review.
- Using it to justify `alembic stamp` or a manual `alembic_version` edit.
- Applying `0005` on top of an unresolved graph.

**Decision owner / authorization:** The migration author and database owner must approve the file and its graph position; a technical lead or release manager must approve the path. Any production execution requires normal change-management approval and a verified restore point. If the file includes data changes, a data owner and security reviewer must also approve.

### 5.3 Scenario 2 — The revision exists remotely but the original file is unavailable

**Hypothesis:** The target's history contains `0004_enterprise_governance`, but no trustworthy file survives.

**Why it cannot be reconstructed from the name or revision ID:**

- A revision identifier is an opaque label. It does not specify SQL, column types, constraints, indexes, data transformations, transaction boundaries, or ordering.
- The name `enterprise_governance` describes a domain concept, not a schema contract. It could mean tables, columns, permissions, audits, data migrations, or nothing matching the name.
- A schema diff can reveal the current state but not the historical sequence, intent, idempotency, or downgrade behavior.
- A fabricated file with the same revision ID would make the history look complete while asserting operations that were never reviewed. That is effectively history fabrication, not recovery.
- Even if the current schema appears to contain the expected effects, the target may also contain partial changes, manual edits, or objects from another source.

**Evidence required:**

- Full `alembic_version` contents and all revision identifiers.
- Complete schema inventory, including objects that may have come from the missing revision.
- Deployment logs, CI artifacts, migration run logs, release records, and change tickets.
- Source history from all available clones, developer machines, backups, package artifacts, and branch/restore history.
- Neon branch/restore metadata if the owner can provide it; do not assume the feature exists.
- Owner and operator interviews about what was applied and when.
- A comparison against the repository's `0003`/`0004` schema and the six-column contract.
- A decision record explaining why reconstruction is or is not possible.

**Potential recovery strategies, only after evidence:**

- Recover the original file from a verified backup or artifact and follow Scenario 1.
- If the original cannot be recovered, perform a controlled rebuild on an isolated branch from the trusted graph and migrate data through a separately reviewed export/import process.
- Author a new, reviewed migration or merge revision based on the inventoried schema, explicitly documenting that it is a reconstruction rather than the original. It must not claim unverified provenance.

**Risks:**

- Unknown DML or data transformations may have changed rows.
- A rebuild may lose data or require downtime.
- A newly authored revision may conflict with objects that already exist.
- A merge may create a false ancestry if the remote history is not fully understood.
- The six columns may already exist under the missing revision.

**Permitted read-only actions:**

- Read-only inventory and catalog comparison.
- Static analysis of all available artifacts.
- Hash/signature checks and provenance review.
- Comparison with repository ORM and migrations.
- Owner interviews and evidence collection.

**Prohibited actions:**

- Creating `0004_enterprise_governance.py` with guessed operations.
- Applying `0005` to the target to "see what happens."
- Stamping the target to the repository head.
- Deleting or editing `alembic_version` rows.
- Treating a schema diff as proof of the original migration's semantics.

**Decision owner / authorization:** Database owner, migration author, and release manager; security/data owner review if the missing revision touched user, credential, or financial data. A controlled rebuild or reconstruction requires a separate approved change, a verified restore point, and an isolated rehearsal.

### 5.4 Scenario 3 — The reported governance revision does not exist in the intended database

**Hypothesis:** The earlier report was mistaken, stale, or described a different branch/environment.

**What changes:** One hypothesis is removed, but the target is still not automatically safe. The complete history and schema must still be compared with the repository. The target could follow the repository chain, contain a different divergence, or be the wrong database entirely.

**Evidence required:**

- Confirmation of the exact project/branch/database and environment classification.
- Full `alembic_version` contents and every revision identifier.
- Complete schema inventory.
- Comparison of the six columns and all repository tables.
- A check for extra tables, columns, constraints, indexes, extensions, or manual changes.
- Provenance of the earlier claim: when it was made, which target it referenced, and whether that target still exists.
- Evidence that the current target is the one the application actually uses.

**Risks:**

- The claim may have been true for a different branch; the current target may still be divergent.
- The claim may be stale; the target may have changed since it was made.
- The absence of one revision may hide a different unknown revision or manual schema change.
- Concluding "the report was wrong, so `0005` is safe" would repeat the original error at a different layer.

**Permitted read-only actions:**

- Full read-only inventory.
- Static comparison with the repository graph and ORM.
- Provenance review of the earlier claim.
- Owner confirmation of target identity.

**Prohibited actions:**

- Applying `0005` solely because the governance identifier is absent.
- Stamping or deleting history rows.
- Assuming the repository chain is authoritative for the target without schema evidence.

**Decision owner / authorization:** Database owner and migration author for the comparison; standard change approval for any later migration. If target identity is uncertain, Scenario 5 applies and all migration work remains blocked.

### 5.5 Scenario 4 — Multiple revisions or otherwise inconsistent history

**Hypothesis:** `alembic_version` has multiple rows, multiple heads, unknown revisions, gaps, duplicates, or a state inconsistent with the actual schema.

**Additional investigation required:**

- Enumerate every version row and every occurrence.
- Build the complete directed graph from all trusted migration files.
- Identify all heads, all roots, all missing parents, and all unknown identifiers.
- Determine whether the histories share a trusted base revision.
- Check whether the actual schema contains objects from each claimed revision, or only some of them.
- Look for evidence of manual stamps, failed migrations, partially applied DDL, restored backups, or branch merges.
- Check object ownership, extensions, and schemas that might indicate a different application history.
- Check whether `alembic_version` itself is in the expected schema and has the expected shape.
- Determine whether a merge revision is structurally possible; a merge requires both parent revisions and their files.
- Determine whether an additive revision can resolve the state; it cannot by itself collapse multiple heads.
- Determine whether a controlled rebuild is the only reproducible option.

**Risks:**

- A merge of an unknown history creates a false claim of common ancestry.
- An additive migration on top of multiple heads leaves the version state ambiguous.
- A rebuild can lose data or require downtime.
- A partially applied migration may have left locks, invalid indexes, or orphaned objects.
- A manual stamp may have hidden missing DDL.

**Permitted read-only actions:**

- Full version-table and schema inventory.
- Static graph construction and comparison.
- Backup/restore verification.
- Isolated branch rehearsal only after written approval.
- Owner/operator interviews.

**Prohibited actions:**

- Editing, deleting, or inserting `alembic_version` rows.
- Running `alembic stamp` or `alembic upgrade` against the target.
- Merging histories without both parent files and a reviewed graph.
- Applying `0005` as a diagnostic step.
- Assuming a multi-row table is safe to "clean up."

**Decision owner / authorization:** Database owner, migration author, and release manager; an incident or change-manager if the inconsistency is production-affecting. Any merge/rebuild requires a separate design review, a verified restore point, and an isolated rehearsal.

### 5.6 Scenario 5 — Target identity or backup status cannot be established

**Hypothesis:** The team cannot prove which Neon project/branch/database is the intended target, or cannot prove a usable backup/restore exists.

**Decision:** Migration work remains **blocked**. No additive, merge, rebuild, stamp, or history operation is authorized.

**Evidence required:**

- Named owner and written target attestation.
- Project/branch/database identity from an authoritative source.
- Environment classification and mapping to the application.
- Verified backup or point-in-time recovery, including a successful restore test to a separate environment.
- A named restore owner and a documented restore procedure.
- Confirmation that a rehearsal can occur without modifying the live target.

**Risks:**

- Migrating the wrong branch could corrupt an unrelated environment.
- Migrating without a verified restore point removes the recovery option.
- An unverified "backup" may be incomplete or untested.
- A wrong environment classification could expose production data or cause an outage.

**Permitted read-only actions:**

- Stop the migration process.
- Collect identity metadata only through an approved console/API or owner-provided record.
- Ask the owner to provide backup/restore evidence.
- Document the blocker and escalate.

**Prohibited actions:**

- Any database migration or schema change.
- Any `alembic` command that connects to a database.
- Any attempt to infer the target from a hostname, `.env` value, or prior report.
- Any "temporary" stamp or history edit.

**Decision owner / authorization:** Infrastructure/database owner and release manager. No execution authorization can be issued until identity and restore capability are independently established.

### 5.7 Strategy mapping and non-selection

**[Reported by earlier batch]** The existing reconciliation plan defines additive migration (Option A), merge revision (Option B), fresh rebuild with data copy (Option C), and stamping (Option D, rejected). Those are strategy categories, not decisions that can be made before the inventory.

**[Inference requiring further evidence]** The appropriate path depends on facts not yet known:

- If the target is exactly `0004_verification_templates` and the six columns are absent, a reviewed additive migration may be possible.
- If a trustworthy governance history is a sibling of the repository's `0004`, a merge revision may be possible only after both files are reviewed.
- If the history is unknown or irreconcilable, a controlled rebuild may be the only reproducible option.
- Stamping remains prohibited because it asserts unproven state.

No final strategy is selected in Batch 19.

---

## 6. Six-column lineage verification

### 6.1 Direct source comparison

**[Confirmed from current repository evidence]**

| Column | ORM declaration | Migration operation | Nullable | Default | Index/FK | Downgrade |
| --- | --- | --- | --- | --- | --- | --- |
| `verification_runs.sources` | `JSON`, `Mapped[Optional[List[Dict[str, Any]]]]` | `op.add_column(... sa.Column("sources", sa.JSON(), nullable=True))` | Yes | None | None | `drop_column` |
| `verification_discrepancies.source_row_indices` | `JSON`, `Mapped[Optional[Dict[str, Any]]]` | Adds `sa.JSON()`, nullable | Yes | None | None | `drop_column` |
| `verification_discrepancies.source_records` | `JSON`, `Mapped[Optional[Dict[str, Any]]]` | Adds `sa.JSON()`, nullable | Yes | None | None | `drop_column` |
| `verification_discrepancies.child_records` | `JSON`, `Mapped[Optional[List[Dict[str, Any]]]]` | Adds `sa.JSON()`, nullable | Yes | None | None | `drop_column` |
| `verification_discrepancies.aggregated_amount` | `Float`, `Mapped[Optional[float]]` | Adds `sa.Float()`, nullable | Yes | None | None | `drop_column` |
| `verification_discrepancies.expected_amount` | `Float`, `Mapped[Optional[float]]` | Adds `sa.Float()`, nullable | Yes | None | None | `drop_column` |

**[Confirmed from current repository evidence]** The ORM declares no `server_default`, index, foreign key, or unique constraint on these six fields. The migration adds none. The migration docstring states that NULL means "not recorded for this row," and that no backfill is appropriate.

### 6.2 Migration behavior

**[Confirmed from current repository evidence]**

- `0005` performs six separate `op.add_column` calls.
- The columns are appended to existing tables, so their physical column order will differ from the ORM declaration order. This is normal for `add_column` and is not semantic drift.
- No `UPDATE`, `INSERT`, or backfill runs.
- No index, foreign key, check constraint, or unique constraint is attached.
- Downgrade drops all six columns in reverse order. Base run and discrepancy rows remain, but lineage stored in the six columns is intentionally lost on downgrade.
- The migration's parent is `0004_verification_templates`; it is not a child of the reported governance revision.

### 6.3 Inventory results that establish column status

For each column, the inventory must establish:

- [ ] The table exists.
- [ ] The exact column name exists.
- [ ] PostgreSQL type is `json` (not `jsonb`) for the five JSON fields.
- [ ] PostgreSQL type is `double precision` (`float8`) for the two amount fields.
- [ ] `is_nullable` is `YES`.
- [ ] `column_default` is null/absent.
- [ ] No unexpected index, foreign key, unique constraint, or check constraint references the column.
- [ ] No hidden dropped column with the same name exists in `pg_attribute`.
- [ ] Any existing data is recorded without exporting row contents.

### 6.4 Decision implications

**[Inference requiring further evidence]**

| Inventory result | Implication |
| --- | --- |
| All six columns absent; base tables match `0004`; history can accept `0005` as a child | `0005` is a structural candidate for an additive path, subject to history review, isolated tests, and approval. This is not authorization. |
| Some columns present with compatible definitions | `0005` cannot be applied as-is; a new reviewed migration or merge strategy is needed. |
| Any column present with an incompatible type, nullability, default, or constraint | Conflict; stop and re-plan. Do not drop or alter it without a data and dependency review. |
| Base tables missing or materially different | `0005` alone cannot establish the ORM contract; broader reconciliation is required. |
| Columns contain non-null lineage data | Preserve the data; do not drop or overwrite it during migration or rollback. |
| History names a revision absent from trusted files | History is unverified; `0005` is not safe to apply merely because columns are missing. |
| History has multiple heads | A merge/additive/rebuild decision is required; `0005` alone does not resolve multiple heads. |

**[Inference requiring further evidence]** The fact that the six columns are missing does not prove that `0005` is safe. The base revision, existing objects, history, and target identity must all agree first.

---

## 7. Server-default discrepancy review

### 7.1 Findings

**[Confirmed from current repository evidence]**

| Column | ORM declaration | Migration declaration | Current known discrepancy | Runtime behavior unknown | Security flag |
| --- | --- | --- | --- | --- | --- |
| `users.hashed_password` | `String(255)`, `nullable=False`; no `server_default` | `String(255)`, `nullable=False`, `server_default=""` | Database default is empty string; ORM metadata does not declare it | Whether raw/legacy inserts omit the column; whether an empty hash can authenticate or is rejected; whether any admin/import path relies on the database default | **Yes — dedicated security review required** |
| `source_files.status` | `String(50)`, `nullable=False`, Python-side `default="uploaded"`; no `server_default` | `String(50)`, `nullable=False`, `server_default="uploaded"` | Database default is `uploaded`; ORM metadata expresses only a Python default | Whether any raw SQL insert omits the column; whether existing data relies on the database default; whether the two defaults are intended to stay aligned | Review required |
| `verification_runs.status` | `String(50)`, `nullable=False`, Python-side `default="pending"`; no `server_default` | `String(50)`, `nullable=False`, `server_default="pending"` | Database default is `pending`; ORM metadata expresses only a Python default | Same as above for raw inserts and existing data | Review required |

### 7.2 Why the parity test does not close this gap

**[Confirmed from current repository evidence]** `backend/tests/test_alembic_migration_parity.py:299-301` states:

> `compare_metadata` detects type, column, index, and foreign-key drift. It does not compare server defaults unless explicitly configured; the six new columns are checked for the absence of defaults above.

The test checks the six new columns for no default, but it does not assert server-default parity for existing columns. Its schema comparison checks column sets, nullability, primary keys, foreign keys, unique constraints, indexes, and type/column/index/FK drift. A passing result therefore does not prove that `users.hashed_password`, `source_files.status`, or `verification_runs.status` have matching database and ORM defaults.

### 7.3 What remains unknown

**[Confirmed from current repository evidence]** The source declarations are known; the runtime and data consequences are not.

**[Inference requiring further evidence]** For each discrepancy, the following need evidence:

- Every insertion path: ORM, raw SQL, migration scripts, imports, admin tools, and tests.
- Whether any path omits the column and relies on the database default.
- Whether existing rows contain values produced by the default.
- The authentication behavior for an empty `hashed_password` string, including whether login rejects it, whether any fallback or error path accepts it, and whether an empty value can be created through an API or import.
- Whether the defaults are intentional compatibility safeguards or accidental drift.
- Whether changing a default would affect locks, existing rows, or application behavior.

### 7.4 Security review for `users.hashed_password`

**Flag:** This discrepancy requires a dedicated security review before any schema change or migration reconciliation assumes it is harmless.

The review should answer:

- Can a user row be created without an explicit password hash?
- Does the login verification function reject `''`, raise an error, or treat it as a valid hash under any algorithm?
- Can a legacy row with `''` be activated, reset, or impersonated?
- Are there import, seed, admin, or migration paths that create users directly?
- Does the empty-string default interact with password reset, token issuance, or account lockout?
- Should the database default be removed, retained, or replaced with an explicit sentinel? **No change is recommended until the evidence is reviewed.**

Do not change the default or add a migration as part of this batch.

### 7.5 Status-column review

For `source_files.status` and `verification_runs.status`, the review should:

- Enumerate all creation and update paths.
- Check for raw SQL that omits `status`.
- Check whether existing rows have unexpected values.
- Determine whether database defaults are part of the intended contract.
- Decide whether ORM and database defaults should be aligned in a separate, reviewed change.

No schema modification is recommended without that evidence.

---

## 8. Isolated PostgreSQL test revalidation plan

### 8.1 Status

**Batch 19 did not run any tests.** The plan below is for a future, explicitly authorized batch. It must not be executed against Neon or any remote database.

**[Reported by earlier batch]** Batch 16 documented the following results on a disposable loopback cluster:

- Migration parity: `2 passed`.
- Migration-built application: `4 passed`.
- Model-created PostgreSQL: `12 passed`.
- Target guard: `11 passed`.

**[Not independently verified]** These results are historical. They must not be described as current until the procedure below succeeds on the current working tree.

### 8.2 Required conditions

1. **Explicitly designated disposable PostgreSQL test database.**
   - Local loopback or an isolated test server.
   - Dedicated database name clearly containing `test`.
   - Dedicated test login role clearly containing `test`.
   - No production, staging, Neon, or application database.
   - No shared production credentials.
   - Disposable after the run.

2. **Positive confirmation of isolation.**
   - The host resolves only to loopback addresses.
   - The connected server is verified with `current_database()`, `current_user`, and `inet_server_addr()`.
   - The target is compared with the application database endpoint and rejected if identical.
   - Redirect-capable query parameters are rejected.
   - The test environment has no route or credential path to Neon/production.
   - An owner records the isolation decision before the run.

3. **Explicit test-only connection.**
   - Use the supported test-only mechanism: `VERIFYGRID_TEST_DATABASE_URL` plus `VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS`.
   - Alembic must receive the already-validated connection through `config.attributes["connection"]`.
   - Do not use the application's normal startup path to run migrations.
   - Do not store the target URL in the repository, logs, or this report.

4. **No fallback to production.**
   - Inspect the test code and the `env.py` explicit-connection path before running.
   - Confirm the migration path does not call `settings.database_url` when a provided connection is present.
   - Run the connection-free target-guard tests, including negative cases.
   - If the explicit-connection change is absent, stop.
   - If the guard does not reject non-loopback or application targets, stop.

5. **Clean test record.**
   - Record date, time zone, operator, branch, HEAD, and a hash of the working tree.
   - Record hashes of the five migration files, `env.py`, and `script.py.mako`.
   - Record the test database identity and role, without credentials.
   - Record the exact test selection and results.
   - Preserve logs, including failure output, with secrets redacted.
   - Record whether each schema was dropped and whether the test database was disposed.

6. **No production changes.**
   - The test database is not the live target.
   - The tests create unique schemas and drop them; they must never use `public` for test tables.
   - A failed test must not trigger fallback to another database.

7. **No premature currency claim.**
   - Until the rerun passes, describe Batch 16 results as historical only.
   - If any test fails, treat the current migration chain as unconfirmed.
   - Do not "fix" failures by changing production or by stamping a database.

### 8.3 Suggested run sequence for a future authorized batch

Do not execute these commands in Batch 19.

1. **Freeze and record.** Confirm no deployment or production migration is in progress. Record HEAD and critical-file hashes. Confirm the test database is disposable and empty.
2. **Guard tests.** Run the connection-free guard suite, including negative cases. Expected historical count: `11 passed`, but treat the count as prior evidence until observed.
3. **Migration parity.** Run the parity suite. Expected historical count: `2 passed`. It should upgrade the full graph, verify the head, verify the six columns, compare the schema/ORM contract, insert legacy rows, upgrade only `0005`, verify preservation, downgrade to `0004`, and re-upgrade.
4. **Migration-built application.** Run the four application tests against the Alembic-built schema:
   - multi-source run persistence and lineage retrieval;
   - split-payment aggregation persistence;
   - template lifecycle and uniqueness;
   - transaction rollback and uniqueness.
   Expected historical count: `4 passed`.
5. **Model-created PostgreSQL (separate evidence).** If desired, rerun the 12-test model-created suite only to compare behavior. It must not be presented as migration evidence.
6. **Teardown.** Drop the unique schemas and dispose the test database/cluster. Confirm no connection remains and no production target was touched.
7. **Record and review.** Attach results to the batch report; have the migration author and reviewer sign off. Only then may the team say the current working tree's migration chain is locally revalidated.

### 8.4 Command shape

Use an isolated shell. Set the opt-in variable and supply the target through an out-of-band value; do not echo or record the value.

```powershell
$env:VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS = "1"
$env:VERIFYGRID_TEST_DATABASE_URL = "<supply-out-of-band-do-not-record>"

# Run from backend/ with the project virtual environment.
python -m pytest tests/test_postgres_target_guard.py -q
python -m pytest tests/test_alembic_migration_parity.py -q -rs
python -m pytest tests/test_postgres_migration_application.py -q -rs

Remove-Item Env:\VERIFYGRID_TEST_DATABASE_URL
Remove-Item Env:\VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS
```

Do not substitute the application database URL. Do not run the migration suites with the opt-in variable unset and then treat skips as passes.

### 8.5 Acceptance criteria

**[Inference requiring further evidence]** The revalidation is successful only when:

- The target guard proves loopback/test isolation and rejects the application target.
- The explicit-connection path is present and used.
- The full migration graph upgrades to `0005`.
- The six columns and their types/nullability/defaults match the ORM.
- Legacy rows survive upgrade; downgrade/re-upgrade behaves as documented.
- The migration-built application tests pass.
- No production/Neon database is contacted.
- The results, environment, and file hashes are recorded without secrets.

A pass would establish current local repository parity only. It would still not authorize a Neon migration or prove that the remote history can accept `0005`.

---

## 9. Migration-template and Git-preservation concerns

### 9.1 Empty revision template

**[Confirmed from current repository evidence]** `backend/migrations/script.py.mako` is 0 bytes (SHA-256 `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855`).

**[Inference requiring further evidence]** Alembic uses this template when generating a new revision. An empty template may cause `alembic revision` or `alembic revision --autogenerate` to fail or produce an invalid/empty migration. The exact behavior was not tested. Future revision generation must not be attempted until the template is reviewed and restored from an approved Alembic/project template.

**Do not fix it in Batch 19.** Restoring the template is a separate, authorized development-workflow change. It must be reviewed for the project's intended header, revision format, imports, and type annotations.

### 9.2 Untracked migration files

**[Confirmed from current repository evidence]**

- `backend/migrations/versions/0004_verification_templates.py` is untracked. SHA-256: `CBE7E536573D06D49E4EB2F8EFB7BD26A0D3CCA786F01EA80AE7C8E7CA74E227`.
- `backend/migrations/versions/0005_verification_lineage.py` is untracked. SHA-256: `645BE701DFF05FDF6D263AF678CB17E77D818CE64C00A8B9F3AF96E46E585713`.

These files are the repository's only copies of the two newest revisions, including the sole head. They are not recoverable from any current commit or branch. A filesystem loss, a clean, a reset, or a failed machine migration would destroy the current migration chain's head.

**Do not stage, commit, or copy them in Batch 19.** A future commit requires:

- Review of both files against the ORM and migration graph.
- Confirmation that line endings and Git filters are correct.
- A decision on whether `0004` and `0005` belong in the same commit as `env.py`.
- Explicit user authorization.

### 9.3 Modified `env.py`

**[Confirmed from current repository evidence]** `backend/migrations/env.py` has 16 insertions and 2 deletions versus HEAD, implementing the explicit-connection path used by the migration tests. SHA-256: `F1A56CC8A201936615DE14F7730E32265C3132AF1372EF382F485207E67F056B`.

If that modification is lost or reverted, the tests' Alembic calls may fall back to the normal settings-based engine target. The test guard still validates the supplied test URL, but the migration execution path would no longer be pinned to the validated connection. This is a test-isolation and preservation risk.

**Do not edit or stage it in Batch 19.** Review the diff and include it in an explicitly authorized commit after the migration files are reviewed.

### 9.4 Pre-existing Batches 1–18 work

**[Confirmed from current repository evidence]** The working tree contains 27 textual tracked-file diffs and a large untracked set, including application, frontend, tests, docs, migrations, and configuration changes. The Batch 18 report and this Batch 19 report are untracked.

**Do not clean, reset, stash, switch branches, or commit.** Preserve every existing change. Any future commit must be scoped by the user and reviewed for unintended files; this report does not authorize one.

### 9.5 Preservation record

Critical file hashes at Batch 19 inspection time:

| File | SHA-256 |
| --- | --- |
| `0004_verification_templates.py` | `CBE7E536573D06D49E4EB2F8EFB7BD26A0D3CCA786F01EA80AE7C8E7CA74E227` |
| `0005_verification_lineage.py` | `645BE701DFF05FDF6D263AF678CB17E77D818CE64C00A8B9F3AF96E46E585713` |
| `backend/migrations/env.py` | `F1A56CC8A201936615DE14F7730E32265C3132AF1372EF382F485207E67F056B` |
| `backend/migrations/script.py.mako` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |
| `docs/audits/Batch18_Migration_History_Divergence_Audit.md` | `1434845A691EB60C9FD34B8C7EACBA5079A7CE667E8DDCB80D4B2578AE037655` |

Hashes are evidence of the inspected content, not authorization to change or publish the files.

---

## 10. Explicit blockers and authorization gates

### 10.1 Blockers

1. **[Not independently verified]** The intended Neon project/branch/database identity, environment classification, and ownership are unknown.
2. **[Not independently verified]** The full `alembic_version` contents and whether the target contains `0004_enterprise_governance` are unknown.
3. **[Not independently verified]** The complete target schema, including extra objects and the six lineage columns, is unknown.
4. **[Not independently verified]** A verified backup or restore point, and the ability to rehearse on an isolated branch, are unknown.
5. **[Confirmed from current repository evidence]** No trustworthy governance migration file exists in this repository or inspected Git objects. Its recovery from an external source is unverified.
6. **[Confirmed from current repository evidence]** The two newest migration files are untracked; the sole head is not protected by Git history.
7. **[Confirmed from current repository evidence]** The explicit-connection safety path in `env.py` is uncommitted.
8. **[Confirmed from current repository evidence]** The three server-default discrepancies are unresolved; the `hashed_password` default requires security review.
9. **[Confirmed from current repository evidence]** `script.py.mako` is empty, so future revision generation is not currently reliable.
10. **[Reported by earlier batch]** Batch 16 test results are historical; current revalidation has not been performed.

### 10.2 Authorization gates

No migration execution may proceed until all applicable gates are passed:

| Gate | Required evidence | Authorizer |
| --- | --- | --- |
| 0. Scope and freeze | Named owner, approved target, change freeze, no deployment in progress | Database owner / release manager |
| 1. Read-only inventory | Complete section 4 checklist, internally consistent, reviewed | Database owner + migration author |
| 2. Strategy decision | Written choice of additive/merge/rebuild with rationale; no stamping | Migration author + DB owner + technical lead |
| 3. Migration review | Reviewed file(s), graph, preconditions, down/restore path, security/data review where applicable | Migration author + reviewer + security/data owner as needed |
| 4. Isolated rehearsal | Successful run on a disposable isolated target; evidence recorded | Migration author + DB owner |
| 5. Restore readiness | Verified backup/restore point and named restore owner | Database owner / infrastructure owner |
| 6. Production change | Change ticket, deployment window, rollback plan, final approval | Release manager / production owner |

A gate cannot be skipped because the migration is "only additive." The six columns are nullable, but that does not establish history compatibility or target identity.

### 10.3 Prohibited shortcuts

The following remain prohibited:

- Running `alembic upgrade head` against any unverified target.
- Running `alembic stamp` or editing `alembic_version`.
- Deleting history rows.
- Creating a governance migration from its name or revision ID.
- Applying `0005` as a test or "because the columns are missing."
- Treating a successful local test as cloud authorization.
- Treating a backup claim without a restore test as verified recovery.
- Committing or staging the untracked migrations in this batch.

---

## 11. Recommended next actions in order

1. **Preserve the current tree.** Do not clean, reset, stash, switch branches, stage, or commit. Keep the hashes in section 9 as the preservation baseline.
2. **Recover the governance migration from trustworthy external sources.** Search verified clones, backups, CI artifacts, release records, migration logs, and owner-held files. Record provenance. Do not reconstruct from the name.
3. **Establish target identity.** Obtain written owner confirmation of the Neon project, branch, database, role, and environment classification without exposing credentials. If identity is uncertain, stop at Scenario 5.
4. **Collect the read-only inventory.** Use section 4 on an isolated/read-approved branch or replica. Capture every `alembic_version` row, the full schema, the six columns, extra objects, privileges, and backup/restore evidence.
5. **Compare and document.** Build a difference report against the repository migration-built schema and ORM. Explicitly record unknown revisions, extra objects, server-default differences, and any data-bearing lineage columns.
6. **Select a strategy.** Choose additive, merge, rebuild, or further investigation with written rationale. Do not choose stamping or history deletion. If the inventory contradicts the repository, stop and re-plan.
7. **Author or recover the migration.** If adding/merging, review the exact file, graph position, preconditions, downgrade/restore path, and any data changes. Do not edit applied history.
8. **Revalidate locally.** Run the isolated PostgreSQL plan in section 8 against the current working tree and record results. Do not claim Batch 16 results are current until this succeeds.
9. **Rehearse on an isolated target.** Apply the chosen migration to a disposable branch/restored environment, verify schema, data safety, application behavior, and rollback/restore.
10. **Obtain production authorization.** Only after gates 0–5, with a verified restore point and change approval, may a production migration be scheduled.
11. **Post-migration verification (future).** Verify the version table, six columns, application health, and data integrity. This is outside Batch 19.

---

## 12. Commands and files inspected

### 12.1 Commands run

All commands were read-only. None opened a database connection, invoked Alembic, read `.env`, or changed repository state.

| Command group | Purpose | Outcome |
| --- | --- | --- |
| `git status --porcelain=v1 --untracked-files=all` (before and after writing the report) | Capture baseline and verify the only new file. | 64 entries before; 65 after; the sole difference is this report. |
| `git branch --show-current`, `git rev-parse HEAD`, `git log -1 --oneline` | Record branch, commit, and subject. | Branch and HEAD recorded in section 2. |
| `git diff --stat`, `git diff --name-only`, `git diff --shortstat`, `git diff --numstat -- backend/migrations/env.py` | Measure textual changes and the `env.py` diff. | 27 textual files, 4,813 insertions, 651 deletions; `env.py` 16/2. |
| `git status --porcelain=v1 --untracked-files=all -- backend/migrations backend/alembic.ini backend/migrations/env.py` | Isolate migration-related state. | `env.py` modified; `0004`/`0005` untracked. |
| `git status --porcelain=v1 -- backend/tests/test_multisource_wizard.py`; `git diff`, `git diff-files --raw`, `git hash-object`, `git rev-parse HEAD:...` | Explain the 28th `M` entry. | Content hash equals HEAD; empty textual diff; stat-only index artifact. |
| `git ls-files backend/migrations/versions`; `git ls-tree -r --name-only HEAD -- backend/migrations/versions`; `git ls-tree` across every local/remote ref | Confirm tracked migration set. | Only `0001`–`0003` are tracked on every inspected ref. |
| `git log --all --oneline -S'enterprise_governance'`; `git log --all --oneline -- backend/migrations/versions` | Search history for the governance revision and migration additions. | No governance commit; only commits adding `0001`–`0003`. |
| `Get-ChildItem docs`, `Get-ChildItem docs/audits`, `Get-ChildItem backend/migrations/versions` | Inventory report and migration files. | Batch 18 report present; five migrations present. |
| `Get-FileHash` on `0004`, `0005`, `env.py`, `script.py.mako`, Batch 18 report | Record preservation hashes. | Hashes in section 9. |
| `Get-Item backend/migrations/script.py.mako` | Confirm template size. | 0 bytes. |
| `Compare-Object` of the Batch 18 final status file and the Batch 19 baseline | Detect changes between batches. | No differences. |
| File reads of all five migrations, `env.py`, `app/models/{__init__,user,source_file,verification_run,verification_template}.py`, `tests/{conftest,pg_test_target,test_alembic_migration_parity,test_postgres_migration_application}.py`, and relevant `docs/` sections | Verify current source and prior claims. | Findings documented above. |

The shell environment did not have `rg` available; searches used PowerShell `Select-String` and the harness `grep` tool. This did not affect the findings.

### 12.2 Files inspected

**Migrations and configuration:**

- `backend/migrations/versions/0001_initial_tables.py`
- `backend/migrations/versions/0002_verification_runs.py`
- `backend/migrations/versions/0003_user_password.py`
- `backend/migrations/versions/0004_verification_templates.py`
- `backend/migrations/versions/0005_verification_lineage.py`
- `backend/migrations/env.py`
- `backend/migrations/script.py.mako`
- `backend/migrations/README`

**ORM models:**

- `backend/app/models/__init__.py`
- `backend/app/models/user.py`
- `backend/app/models/source_file.py`
- `backend/app/models/verification_run.py`
- `backend/app/models/verification_template.py`

**Tests:**

- `backend/tests/conftest.py`
- `backend/tests/pg_test_target.py`
- `backend/tests/test_alembic_migration_parity.py`
- `backend/tests/test_postgres_migration_application.py`

**Documentation:**

- `docs/audits/Batch18_Migration_History_Divergence_Audit.md`
- `docs/NEON_MIGRATION_RECONCILIATION_PLAN.md`
- `docs/POSTGRES_INTEGRATION_TESTING.md`
- `docs/REUSABLE_VERIFICATION_TEMPLATES_DESIGN.md`
- `docs/PERSISTED_LINEAGE_ANALYSIS.md` (inventory presence only; not relied on for a conclusion in this report)

### 12.3 Tests, database commands, and secret handling

**[Confirmed from current repository evidence]**

- Tests executed: **none**.
- Alembic commands executed: **none**.
- Database connections attempted: **none**.
- `.env` files read: **none**.
- Database URLs, credentials, tokens, or private keys printed: **none**.
- Schema/data changes: **none**.
- Application, model, migration, configuration, dependency, or existing documentation edits: **none**.

Why no tests were run: the PostgreSQL suites require an explicitly supplied isolated target, which Batch 19 does not authorize; the default SQLite suite uses `Base.metadata.create_all` and would not provide migration-chain evidence. No test was run merely to produce a green result.

### 12.4 Final working-tree verification

**[Confirmed from current repository evidence]**

- Baseline status: 64 entries.
- Final status after adding this report: 65 entries.
- `Compare-Object` shows exactly one new path: `docs/audits/Batch19_Migration_Reconciliation_Preparation.md`.
- No pre-existing file was modified, deleted, renamed, staged, or committed.
- The 27 textual tracked-file diffs and all 36 pre-existing untracked entries remain.

---

## 13. Final verdict

### 13.1 Verdict

**PASS — preparation scope only.**

The Batch 19 package is complete:

- Current repository state and preservation were verified.
- The migration evidence matrix was produced from current source.
- The read-only Neon inventory checklist is exact and evidence-oriented.
- The five reconciliation scenarios define evidence, risks, permitted read-only actions, prohibitions, and authorization.
- The six lineage columns were verified against the ORM and migration source.
- The server-default audit was separated, with the password default flagged for security review.
- The isolated PostgreSQL revalidation plan is defined but not executed.
- Template and Git-preservation concerns are documented.
- Blockers, authorization gates, and ordered next actions are explicit.

### 13.2 Verdict qualifications

- **Not a PASS for Neon reconciliation.** Neon was not inspected.
- **Not a PASS for migration readiness.** No strategy is selected and no target inventory exists.
- **Not a PASS for revalidation.** Batch 16 results remain historical.
- **Not a PASS for server-default parity.** The discrepancies are unresolved.
- **Not an authorization to commit.** The untracked migrations and modified `env.py` remain untracked/uncommitted by design.

If "PASS" were interpreted as permission to migrate, the verdict would be **FAIL**. It is not. The passing verdict applies strictly to the documentation and preparation deliverable required by Batch 19.

### 13.3 Recommended next step

**Recover the governance migration from a trustworthy source and collect the complete read-only Neon inventory in section 4, under written owner authorization.** Until the inventory is reviewed and a strategy is approved, migration work remains blocked and unverified. Do not stamp, delete history, fabricate a migration, or apply `0005` to the target.
