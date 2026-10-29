# VerifyGrid Batch 18 — Migration-History Divergence Audit

**Date:** 2026-10-29
**Audit type:** Read-only repository and Git-working-tree investigation
**Branch:** `feature/batch-4-rule-engine-aggregation`
**HEAD:** `c91e9b37074483eeb7469dc943e1735fd5f5be02`
**Scope:** Repository-side migration history, ORM/migration parity, Alembic configuration, and the reported `0004_enterprise_governance` divergence.
**Remote database:** Not contacted. The remote/cloud state, including any Neon branch, schema, data, and `alembic_version` contents, remains unverified.

## Evidence legend

Every conclusion in this report is labelled with one of the following categories:

- **[Confirmed from repository evidence]** — directly observable in the checked-out files, the Git object database, or read-only command output.
- **[Reported previously but not independently verified]** — asserted in repository documentation, comments, or prior batch narratives, but not proven by this audit.
- **[Inference requiring further evidence]** — a reasoned consequence of confirmed facts that depends on unverified external state or runtime behavior.

A statement that a document *contains a claim* is confirmed. The *truth of that claim* is separately classified. This distinction is central to the audit.

---

## 1. Executive summary and confidence level

### 1.1 Summary

1. **[Confirmed from repository evidence]** The checked-out repository contains a single, linear, internally consistent Alembic chain:
   `0001_initial_tables` → `0002_verification_runs` → `0003_user_password` → `0004_verification_templates` → `0005_verification_lineage`.
   The filenames and declared revision identifiers agree, every parent resolves, there are no duplicate revision identifiers, and `0005_verification_lineage` is the only head.

2. **[Confirmed from repository evidence]** No migration file, test, configuration, script, tracked commit, reachable object, or unreachable/dangling Git tree inspected in this repository contains a revision named `0004_enterprise_governance` or any of its upgrade/downgrade operations. The identifier appears only as a claim in the docstring of the untracked `0004_verification_templates.py` and in untracked documentation.

3. **[Confirmed from repository evidence]** Revision `0005_verification_lineage` adds exactly six nullable columns that the current ORM declares: `verification_runs.sources`, and on `verification_discrepancies`, `source_row_indices`, `source_records`, `child_records`, `aggregated_amount`, and `expected_amount`. No index, foreign key, default, or backfill is added by `0005`.

4. **[Confirmed from repository evidence]** Static comparison found no application table or non-default column in the current ORM metadata that is absent from the repository migration chain at head `0005`. However, three server-default mismatches remain between migrations and ORM declarations. The migration-parity test explicitly does not compare server defaults, so its green result would not detect them.

5. **[Reported previously but not independently verified]** A prior batch reported that the cloud database has a divergent history identified as `0004_enterprise_governance`, that `0004_verification_templates` was applied to a local development database, and that `0005_verification_lineage` has not been applied to the local development database or the cloud database. This audit did not inspect any database.

6. **[Inference requiring further evidence]** Because the cloud history is unknown, applying `0005_verification_lineage` to the cloud database is unsafe. If the cloud head is a revision absent from the repository graph, Alembic cannot establish a valid path from that head to `0005`; the current revision would likely be unresolvable, and any forced or manually altered history could leave the version table and schema inconsistent. The additive, nullable nature of `0005` reduces direct data-loss risk on a matching base schema, but it does not solve the history problem.

7. **[Confirmed from repository evidence]** Normal CLI Alembic use targets `settings.database_url` from `backend/migrations/env.py`, not the hardcoded URL in `backend/alembic.ini`. The test-only explicit-connection path is present but is an uncommitted modification. There is no application-startup migration or `create_all` path.

8. **[Confirmed from repository evidence]** The audit made no database connection, ran no Alembic command, ran no test, and changed no application, model, migration, configuration, secret, or dependency file. The only new file is this report.

### 1.2 Confidence

| Area | Confidence | Basis |
| --- | --- | --- |
| Repository migration graph integrity | **High** | Direct file inspection; all revisions and parents checked. |
| Absence of the governance revision from this repository and reachable Git history | **High** | Working-tree search, all-ref tree inspection, commit search, object search, unreachable-tree inspection. |
| Absence from every possible external source | **None** | Other clones, backups, CI artifacts, deleted files, and remote databases were not accessible. |
| ORM-to-migration column coverage | **High (static)** | Models and migration operations read directly; runtime parity not rerun. |
| Server-default drift | **High (static)** | Definitions compared in `0003`, `0001`, `0002`, and the ORM. Runtime impact not tested. |
| Actual local/cloud database state | **None** | No database was contacted; prior claims were not independently checked. |
| Safety of applying `0005` to the cloud | **Blocked** | Depends on the unknown remote `alembic_version` and schema. |
| Reconciliation strategy | **Low / conditional** | Only evidence-gathering paths can be stated; strategy cannot be chosen without inventory. |

### 1.3 Verdict

**PASS — for the audit scope only.**

The investigation tasks were completed with read-only repository evidence, the required report was produced, and every safety constraint was observed. This verdict does **not** mean the migration histories are reconciled, that Neon is verified, or that any migration is safe to apply. Cloud reconciliation remains **blocked and unverified**.

---

## 2. Working-tree baseline and preservation confirmation

### 2.1 Repository identity

**[Confirmed from repository evidence]**

- Current branch: `feature/batch-4-rule-engine-aggregation`.
- HEAD commit: `c91e9b37074483eeb7469dc943e1735fd5f5be02` (`feat: implement Batch 4 advanced rule engine, aggregation and split-payment reconciliation`).
- Local branches observed: `main`, `feature/batch-1-matching-correctness`, `feature/batch-2-profiling-quarantine`, `feature/batch-3-multisource-wizard`, and the current branch.
- Remote refs observed: `origin/main` and `origin/improvement/project-load-recovery`.
- No tags were present.

### 2.2 Pre-existing working-tree state

**[Confirmed from repository evidence]** The working tree was already dirty at the start of Batch 18. The baseline contained 27 modified tracked files and a large untracked set. The modified tracked files were:

- Backend application: `backend/app/api/v1/endpoints/profiling.py`, `backend/app/api/v1/router.py`, `backend/app/models/__init__.py`, `backend/app/models/verification_run.py`, `backend/app/schemas/multisource.py`, `backend/app/schemas/preprocessing.py`, `backend/app/schemas/result.py`, `backend/app/services/preprocessing.py`, `backend/app/services/profiling_service.py`, `backend/app/services/verification_engine.py`.
- Migration configuration: `backend/migrations/env.py`.
- Backend tests: `backend/tests/test_multisource_wizard.py`, `backend/tests/test_postgres_integration.py`, `backend/tests/test_verification_engine.py`.
- Frontend: `frontend/index.html`, `frontend/package-lock.json`, `frontend/package.json`, `frontend/src/App.tsx`, `frontend/src/components/AppearanceControl.tsx`, `frontend/src/components/FileUploadSection.tsx`, `frontend/src/components/ProfilingQuarantineDrawer.tsx`, `frontend/src/components/ReconciliationWizard.tsx`, `frontend/src/components/Sidebar.tsx`, `frontend/src/context/ThemeContext.tsx`, `frontend/src/context/themeContextDef.ts`, `frontend/src/index.css`, `frontend/src/services/api.ts`, `frontend/src/types/index.ts`.

The untracked set included, among others:

- Batch 11–16 application and test work: `backend/app/api/v1/endpoints/templates.py`, `backend/app/models/verification_template.py`, `backend/app/schemas/template.py`, `backend/app/services/template_service.py`, the Batch 2–14 test files, `backend/tests/test_postgres_target_guard.py`, and `backend/tests/test_postgres_migration_application.py`.
- Migration files: `backend/migrations/versions/0004_verification_templates.py` and `backend/migrations/versions/0005_verification_lineage.py`.
- Migration-parity infrastructure: `backend/tests/pg_test_target.py` and `backend/tests/test_alembic_migration_parity.py`.
- The entire `docs/` directory, including the prior reconciliation plan, template design, lineage analysis, and PostgreSQL testing document.
- Frontend Batch 11/17 work: `frontend/src/components/TemplatePanel.tsx`, `frontend/src/services/columnMapping.ts`, `frontend/tests/`, and `frontend/vitest.config.ts`.

**[Inference requiring further evidence]** The paths are consistent with the Batches 1–17 work described in the task context, and no unrelated infrastructure, secret, CI, or deployment path appeared in the baseline. Per-file batch attribution was taken from the task context and file contents; this audit did not independently reconstruct the provenance of every change.

### 2.3 Unexpected changes

**[Confirmed from repository evidence]** No file path outside the areas associated with Batches 1–17 appeared in the baseline. No new modification was observed during the audit.

**[Inference requiring further evidence]** Because the working tree is broad and uncommitted, it is not possible to prove from Git alone that every line belongs to the intended batch. The absence of an unexpected path is not a line-by-line review of all 27 modified files.

### 2.4 Preservation confirmation

**[Confirmed from repository evidence]**

- No `git clean`, `git reset`, `git stash`, `git checkout`, `git switch`, branch creation, commit, push, merge, rebase, or deployment was performed.
- No application, ORM model, migration, configuration, secret, or dependency file was edited.
- The only permitted new file is this report: `docs/audits/Batch18_Migration_History_Divergence_Audit.md`.
- The pre-existing modified and untracked files remain present. In particular, `0004_verification_templates.py` and `0005_verification_lineage.py` were not moved, renamed, regenerated, or overwritten.
- Baseline status with `--untracked-files=all` contained 63 entries. After this report was added, the status contained the same entries plus this report. The comparison is recorded in section 9.

**[Inference requiring further evidence]** The most important preservation risk is not this audit but the pre-existing state: `0004_verification_templates.py` and `0005_verification_lineage.py` exist only as untracked files. They are not recoverable from any current commit or branch. A filesystem loss, aggressive clean, or failed machine migration would destroy the repository's only copies of the two newest revisions. Version-controlling them requires an explicit user-authorized commit, which this batch did not perform.

---

## 3. Migration-chain inventory

### 3.1 Graph

**[Confirmed from repository evidence]**

```text
0001_initial_tables
  └── 0002_verification_runs
        └── 0003_user_password
              └── 0004_verification_templates
                    └── 0005_verification_lineage  (sole repository head)
```

The chain is linear. No branching revision, merge revision, or second head exists in the working tree.

### 3.2 Per-migration inventory

| # | File | Revision ID | `down_revision` | Declared purpose | Upgrade operations | Downgrade operations | Git tracking |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0001 | `backend/migrations/versions/0001_initial_tables.py` | `0001_initial_tables` | `None` | Initial tables for users, projects, and source_files | Creates `users`, `projects`, `source_files`; adds unique index on `users.email`, index on `projects.owner_id`, index on `source_files.project_id`; FKs from projects to users and source_files to projects. | Drops the three indexes and three tables in reverse order. | Tracked |
| 0002 | `backend/migrations/versions/0002_verification_runs.py` | `0002_verification_runs` | `0001_initial_tables` | Verification runs and discrepancies tables | Creates `verification_runs` and `verification_discrepancies`; adds FKs to projects/source_files and run; adds indexes on run project/source/target/status and discrepancy run/match status/category. | Drops discrepancy indexes and table, then run indexes and table. | Tracked |
| 0003 | `backend/migrations/versions/0003_user_password.py` | `0003_user_password` | `0002_verification_runs` | Add hashed_password to users table | Adds `users.hashed_password` as `String(255)`, non-null, `server_default=""`. | Drops `users.hashed_password`. | Tracked |
| 0004 | `backend/migrations/versions/0004_verification_templates.py` | `0004_verification_templates` | `0003_user_password` | Create verification_templates table (reusable template feature) | Creates `verification_templates` with UUID primary key, nullable owner FK to `users.id` (`ON DELETE SET NULL`), name, description, mode, visibility (`server_default="personal"`), config_version (`server_default="1"`), configuration JSON, timestamps; unique constraint `uq_verification_templates_owner_name`; index `ix_verification_templates_owner_id`. | Drops the owner index and the table. | **Untracked** |
| 0005 | `backend/migrations/versions/0005_verification_lineage.py` | `0005_verification_lineage` | `0004_verification_templates` | Add multi-source and aggregation lineage columns | Adds six nullable columns: `verification_runs.sources` JSON; `verification_discrepancies.source_row_indices` JSON, `source_records` JSON, `child_records` JSON, `aggregated_amount` Float, `expected_amount` Float. No indexes, FKs, defaults, or backfill. | Drops the six columns in reverse order. | **Untracked** |

### 3.3 Integrity checks

**[Confirmed from repository evidence]**

- The filenames match their declared revision identifiers for all five files.
- `down_revision` values form one continuous chain with no missing parent.
- There are no duplicate revision identifiers.
- There is exactly one repository head: `0005_verification_lineage`.
- `0005`'s parent is `0004_verification_templates`, not the reported `0004_enterprise_governance`.
- `0001` and `0002` create the base tables; `0003` alters `users`; `0004` creates the template table; `0005` alters the two run/discrepancy tables.
- The downgrade order in `0005` is the reverse of its upgrade order; the other downgrades drop objects in dependency-safe order.

**[Confirmed from repository evidence]** `backend/migrations/versions/` contains exactly these five Python migration files. No additional migration file is present in the working tree.

**[Confirmed from repository evidence]** `backend/migrations/script.py.mako` is 0 bytes. **[Inference requiring further evidence]** Alembic's revision-generation command normally renders that template; an empty template may cause `alembic revision` to fail or produce an unusable file. This audit did not invoke the command, so the practical impact is unverified. It does not affect the validity of the existing five hand-written migrations.

---

## 4. Evidence for and against the reported governance revision

### 4.1 The claim as recorded

**[Confirmed from repository evidence]** The following sources contain the claim. Their existence is confirmed; their factual assertion about the cloud database is not.

| Source | What it says | Classification |
| --- | --- | --- |
| `backend/migrations/versions/0004_verification_templates.py:6-10` | Batch 12 applied `0004_verification_templates` to the local development database after a read-only review. The `.env`-configured cloud database has a divergent, unrelated migration history identified as `0004_enterprise_governance` and was not touched. | **Claim confirmed; cloud state reported but not independently verified.** |
| `docs/REUSABLE_VERIFICATION_TEMPLATES_DESIGN.md:5-9` | Repeats that the migration was applied locally and that the cloud database has a divergent history identified as `0004_enterprise_governance` and was intentionally not touched. | **Claim confirmed; cloud state reported but not independently verified.** |
| `docs/REUSABLE_VERIFICATION_TEMPLATES_DESIGN.md:329` | Repeats the divergent cloud-history statement. | **Claim confirmed; cloud state reported but not independently verified.** |
| `docs/NEON_MIGRATION_RECONCILIATION_PLAN.md:113-118` | Describes the `0004` docstring as repository-recorded cloud divergence and explicitly says the actual Neon schema and history remain unverified. | **Claim confirmed; the document itself acknowledges the remote state is unverified.** |
| `docs/NEON_MIGRATION_RECONCILIATION_PLAN.md:183` | States that no migration encodes the cloud-only `0004_enterprise_governance` revision. | **Confirmed by this audit's repository search.** |
| `docs/NEON_MIGRATION_RECONCILIATION_PLAN.md:240-263` | Lists the required Neon inventory: branch identity, full `alembic_version`, complete schema inventory, six-column status, overlapping objects, external revision file, row estimates, privileges, and restore capability. | **Confirmed as a documented prerequisite; the inventory was not collected.** |

**[Confirmed from repository evidence]** The design document refers to a Batch 12 report, but no standalone Batch 12 report file exists under `docs/`. At the start of the audit, the `docs/` directory contained only the four untracked Markdown files listed in section 2.2; this report is now the fifth. The claim's provenance therefore rests on the migration docstring and untracked design/planning documents, not on a separately archived Batch 12 audit.

**[Confirmed from repository evidence]** The entire `docs/` directory is untracked. These documents are not part of Git history and could be lost or altered without a Git record.

### 4.2 Evidence against the revision existing in this repository

**[Confirmed from repository evidence]**

1. **Working tree:** `backend/migrations/versions/` contains only `0001`, `0002`, `0003`, `0004_verification_templates`, and `0005_verification_lineage`. There is no `0004_enterprise_governance.py` and no other file whose content defines that revision.

2. **Tracked Git history:** All reachable tracked migration history stops at `0003_user_password`:
   - `9d1da36` added `0001_initial_tables.py`.
   - `2ab1060` added `0002_verification_runs.py`.
   - `f90d37f` added `0003_user_password.py`.
   No commit adds `0004_verification_templates.py`, `0005_verification_lineage.py`, or any governance revision.

3. **All branches and remotes:** `git ls-tree -r --name-only` on `main`, `origin/main`, `feature/batch-4-rule-engine-aggregation`, and `feature/batch-3-multisource-wizard` returned only `0001`–`0003` under `backend/migrations`. No branch or remote ref tracks `0004` or `0005`.

4. **String search:** `git log --all -S'enterprise_governance'`, `git log --all -S'0004_enterprise_governance'`, and full-history path searches for `*enterprise_governance*` returned no commits. The identifier is not present in any commit diff reachable from the inspected refs.

5. **Object search:** `git rev-list --all --objects` contained no path matching `enterprise_governance`. The unreachable/dangling tree objects reported by `git fsck --unreachable --no-reflogs` and `git fsck --dangling --no-reflogs` were inspected; each contained only the `0001`–`0003` migration set (or no migration paths at all). No unreachable file for the governance revision was found.

6. **Deletion search:** `git log --all --diff-filter=D -- backend/migrations/versions` returned no commits, so no tracked migration was deleted in reachable history. `git log --all --stat -- backend/migrations/versions` showed only the three additions above.

7. **Other repository locations:** Searches of application code, tests, configuration, scripts, documentation, and root files found `enterprise_governance` only in the `0004` docstring and the untracked docs. No test imports or asserts on it; no configuration references it; no script inspects or manipulates `alembic_version` for the cloud database.

8. **No recoverable operations:** Even if the name is genuine, the repository contains no revision ID declaration, parent, table/column operations, constraint changes, or checksum for it. A name alone is not enough to reconstruct a migration.

### 4.3 What the evidence does and does not establish

**[Confirmed from repository evidence]** The repository's own migration graph has no governance revision, and no inspected Git object contains one. The only repository record of it is a prose claim.

**[Reported previously but not independently verified]** The cloud database—referred to as Neon in prior documents—has a divergent `alembic_version` containing `0004_enterprise_governance`, and the repository's `0004_verification_templates` was applied only to a local database. No database was contacted in this audit, so none of this was confirmed.

**[Inference requiring further evidence]** Absence from this repository does not prove that the revision never existed. It could have existed in:
- another clone or developer machine that was never committed;
- a deleted untracked file;
- a CI artifact, backup, or database migration log;
- a different branch/project database with its own history;
- a Neon branch whose history was created outside this checkout.

Conversely, the prior claim does not prove that the current cloud database still has that history. The branch may have been reset, recreated, restored, or replaced since Batch 12. The identifier could also refer to a different database or a different environment than the one now configured.

**[Confirmed from repository evidence]** No repository script performs migration stamping or manual `alembic_version` manipulation. `docs/NEON_MIGRATION_RECONCILIATION_PLAN.md:225-238` explicitly rejects stamping and automatic reconciliation. This audit likewise does not recommend deleting history rows, stamping, or fabricating a migration.

---

## 5. ORM-versus-migration findings

### 5.1 The six columns added by `0005`

**[Confirmed from repository evidence]** The migration and the ORM agree on the following contract:

| Table.column | Migration definition (`0005`) | ORM definition | Nullable | Default | Index/FK |
| --- | --- | --- | --- | --- | --- |
| `verification_runs.sources` | `sa.JSON()` | `JSON` (`Mapped[Optional[List[Dict[str, Any]]]]`) | Yes | None | None |
| `verification_discrepancies.source_row_indices` | `sa.JSON()` | `JSON` (`Mapped[Optional[Dict[str, Any]]]`) | Yes | None | None |
| `verification_discrepancies.source_records` | `sa.JSON()` | `JSON` (`Mapped[Optional[Dict[str, Any]]]`) | Yes | None | None |
| `verification_discrepancies.child_records` | `sa.JSON()` | `JSON` (`Mapped[Optional[List[Dict[str, Any]]]]`) | Yes | None | None |
| `verification_discrepancies.aggregated_amount` | `sa.Float()` | `Float` (`Mapped[Optional[float]]`) | Yes | None | None |
| `verification_discrepancies.expected_amount` | `sa.Float()` | `Float` (`Mapped[Optional[float]]`) | Yes | None | None |

**[Confirmed from repository evidence]** `0005` adds no indexes or foreign keys, and the ORM declares none for these fields. The migration docstring states that NULL means "not recorded for this row," not missing data that can be reconstructed, and that no backfill is appropriate. The ORM types are nullable and match that intent.

### 5.2 Table and column coverage

**[Confirmed from repository evidence]** The ORM metadata registered by `backend/app/models/__init__.py` contains six tables: `users`, `projects`, `source_files`, `verification_runs`, `verification_discrepancies`, and `verification_templates`. The repository migration chain creates all six:

- `0001`: `users`, `projects`, `source_files`.
- `0002`: `verification_runs`, `verification_discrepancies`.
- `0003`: adds `users.hashed_password`.
- `0004`: adds `verification_templates`.
- `0005`: adds the six lineage columns.

**[Confirmed from repository evidence]** `VerificationTemplate` matches `0004` on the primary key, nullable owner FK with `ON DELETE SET NULL`, name/description/mode/configuration columns, `visibility` and `config_version` defaults, timestamps, the unique constraint `uq_verification_templates_owner_name`, and the `owner_id` index.

**[Inference requiring further evidence]** Static inspection found no additional ORM table or non-default column missing from the chain. This is not a runtime proof. The parity suite that would prove it was not rerun in Batch 18, and its own server-default blind spot is documented below.

### 5.3 Server-default drift

**[Confirmed from repository evidence]** Three migration-defined server defaults do not match the current ORM declarations:

| Column | Migration behavior | ORM behavior | Consequence |
| --- | --- | --- | --- |
| `users.hashed_password` | `0003` adds it as non-null with `server_default=""`. | `backend/app/models/user.py` declares `String(255), nullable=False` with no `server_default`. | A database built by migrations retains an empty-string default; the ORM does not declare it. Direct SQL inserts that omit the column receive `''`; ORM inserts must supply a value. |
| `source_files.status` | `0001` creates it as non-null with `server_default="uploaded"`. | `backend/app/models/source_file.py` declares `default="uploaded"` only (Python-side). | The database default exists but is not represented in ORM metadata. ORM inserts normally supply the value; raw SQL inserts may rely on the database default. |
| `verification_runs.status` | `0002` creates it as non-null with `server_default="pending"`. | `backend/app/models/verification_run.py` declares `default="pending"` only (Python-side). | Same pattern: database default not represented in ORM metadata. |

**[Confirmed from repository evidence]** The migration-parity test's own comment at `backend/tests/test_alembic_migration_parity.py:299-301` states that `compare_metadata` "does not compare server defaults unless explicitly configured"; the test checks only that the six new columns have no default. The broader schema comparison checks column sets, nullability, primary keys, foreign keys, unique constraints, and indexes, and uses `compare_metadata` with `compare_type=True` for type/column/index/FK drift. It does not assert server-default parity for existing columns.

**[Inference requiring further evidence]** A green parity result therefore does **not** prove full metadata parity. The three defaults above could be intentional database safeguards or accidental drift; the repository does not state which. Their runtime impact depends on whether any code path inserts through raw SQL or relies on database defaults, and on how authentication handles an empty password hash. That impact was not tested.

**[Inference requiring further evidence]** The `hashed_password` default is the most security-sensitive of the three. If a user row can be created outside the ORM without an explicit hash, it will contain `''` rather than NULL. Whether that value can authenticate depends on the password-verification implementation; it should not be assumed safe or unsafe without a targeted security review. This audit did not modify or test it.

### 5.4 Other model/migration notes

**[Confirmed from repository evidence]** The ORM uses `onupdate=func.now()` for several `updated_at` columns; this is client-side SQLAlchemy behavior, not a database trigger, and the migrations do not create triggers. This is not a schema mismatch, but it means database-level updates do not automatically refresh `updated_at`.

**[Confirmed from repository evidence]** `backend/app/models/audit_log.py`, `review.py`, and `rule.py` are 0-byte files and are not imported by `backend/app/models/__init__.py`; they define no metadata. No migration is expected for them in the current application.

**[Reported previously but not independently verified]** Batch 16 reported migration-parity `2 passed`, migration-built application `4 passed`, model-created PostgreSQL `12 passed`, and target-guard `11 passed` on an isolated loopback cluster. These results are prior evidence only. Batch 18 did not rerun them, did not inspect that cluster, and does not treat them as proof of the current working tree or of any cloud state.

---

## 6. Alembic configuration and test-isolation findings

### 6.1 Single head and URL resolution

**[Confirmed from repository evidence]**

- The working-tree graph has one head, `0005_verification_lineage`.
- `backend/migrations/env.py:24-25` unconditionally sets the Alembic `sqlalchemy.url` option from `settings.database_url`.
- `backend/migrations/env.py:68-75` builds the normal online engine from the configuration section, with the URL overwritten from `settings.database_url`.
- `backend/alembic.ini` contains a hardcoded loopback PostgreSQL URL with a placeholder local password. That value is overridden by `env.py` during normal CLI use; it is not reproduced in this report.
- `backend/app/core/config.py:11-17` defines `database_url` as a configurable setting. A `.env` file exists in `backend/`; its contents were not read in this audit.

**[Inference requiring further evidence]** Normal `alembic upgrade`, `downgrade`, `stamp`, or `revision --autogenerate` CLI use therefore follows whatever `settings.database_url` resolves to, including a cloud URL if `.env` is configured that way. There is no CLI-level loopback/test-target guard comparable to the test guard. An operator can direct Alembic at the wrong database simply by running the command in the configured environment. This is a governance and operational risk, not evidence that a wrong target has ever been used.

### 6.2 Explicit test connection path

**[Confirmed from repository evidence]**

- `backend/migrations/env.py:49-66` supports a connection supplied via `config.attributes["connection"]`. When present, Alembic configures that connection and runs migrations without constructing an engine from `settings.database_url`.
- The migration tests construct the Alembic `Config` and set `config.attributes["connection"]` explicitly (`backend/tests/test_alembic_migration_parity.py:148-172`).
- The tests create a unique schema, pin `search_path` to it, verify the actual connected database/user/server address, and drop the schema afterward (`test_alembic_migration_parity.py:112-145`).
- The tests are opt-in: `pytest.mark.skipif` unless `VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS` is enabled, and `VERIFYGRID_TEST_DATABASE_URL` is required (`test_alembic_migration_parity.py:7-16, 52-60`; `test_postgres_migration_application.py:15-22, 64-72`).

**[Confirmed from repository evidence]** The safety change in `env.py` is **uncommitted** (it is one of the 27 modified tracked files). If that change were reverted or lost, the explicit-connection path would disappear and the test modules' Alembic calls would fall back to the normal settings-based engine target. The test guard would still validate the test URL before creating an engine, but the migration execution path itself would no longer be pinned to the validated connection. This makes preservation of the `env.py` modification important.

### 6.3 Target guard behavior

**[Confirmed from repository evidence]** `backend/tests/pg_test_target.py` implements a fail-closed guard that does not open a connection during validation. It rejects:

- missing or malformed URLs;
- drivers other than `postgresql+psycopg`;
- a missing host, non-loopback hosts, or hosts resolving to any non-loopback address;
- database names in `{postgres, template0, template1, verifygrid, neondb}`;
- database names that do not contain `test` (case-insensitive);
- usernames that do not contain `test`;
- redirect-capable query keys such as `host`, `hostaddr`, `port`, `dbname`, `database`, `user`, `service`, and `servicefile`;
- a target identical to the application database endpoint, or a database name matching the application database name.

The test fixture additionally verifies the actual `current_database()`, `current_user`, and `inet_server_addr()` after connecting.

**[Inference requiring further evidence]** This is strong isolation for the opt-in PostgreSQL suites, but it protects only those suites. It does not protect a human running the Alembic CLI. It also assumes the operator supplies a genuinely dedicated test database and role; the guard validates names and network location, not the absence of sensitive data in that database. The audit did not supply such a target and did not run the suites.

### 6.4 Default test harness and application startup

**[Confirmed from repository evidence]**

- `backend/tests/conftest.py:14-37` configures an in-memory SQLite database (`sqlite:///:memory:`) with `StaticPool` and creates the schema with `Base.metadata.create_all`.
- The default test suite therefore exercises a model-created SQLite schema, not the Alembic chain.
- No application code under `backend/app/` calls `create_all`, `command.upgrade`, `command.downgrade`, or `run_migrations`. `backend/app/main.py` only creates the FastAPI app, adds CORS, and includes the API router.
- No startup hook applies migrations automatically.

**[Inference requiring further evidence]** Migrations are an explicit operational step, not an application-startup behavior. A deployment that does not run them will start against an unmigrated schema and fail when code touches missing tables/columns. Conversely, because startup does not run Alembic, the application cannot accidentally auto-migrate a cloud database on boot. The actual deployment process was not inspected.

### 6.5 Empty revision template

**[Confirmed from repository evidence]** `backend/migrations/script.py.mako` is 0 bytes. No existing migration depends on it at runtime. **[Inference requiring further evidence]** Future `alembic revision` or `alembic revision --autogenerate` use may fail or emit an empty/invalid file until the template is restored from the Alembic distribution or the project's chosen template. This audit did not run either command.

---

## 7. Potential reconciliation paths and prerequisites

### 7.1 How to read this section

The task defines four diagnostic scenarios (A–D). They are **not** the same as the four strategy options in `docs/NEON_MIGRATION_RECONCILIATION_PLAN.md:265-313` (additive migration, merge revision, fresh rebuild, stamp). This section addresses the task's scenarios first, then maps them to the existing strategy vocabulary.

None of these paths was executed. None authorizes a database change. In particular, this audit does **not** recommend deleting an `alembic_version` row, stamping a revision, fabricating a migration from a name, or running `upgrade head` against the configured cloud database.

### 7.2 Scenario A — The governance migration is recoverable from a trustworthy source

**Hypothesis:** A file, commit, backup, CI artifact, or reviewed external source contains the actual `0004_enterprise_governance` revision.

**Evidence required before proceeding:**

- The original file or an authoritative copy, with its complete revision identifier, `down_revision`, upgrade, and downgrade operations.
- Proof of provenance: which commit/clone/backup produced it, when, and by whom.
- Confirmation that it was the revision actually applied to the specific cloud database/branch in question, not merely a file that existed somewhere.
- A reviewed comparison between its operations and the repository's `0004_verification_templates` operations.
- A graph plan: if governance is a separate child of `0003`, a merge revision with two parents may be needed; if it replaces the repository's `0004`, the relationship must be resolved without rewriting applied history.
- Local rehearsal on an isolated PostgreSQL target and a Neon branch rehearsal with a restore point.

**Risk of blindly applying `0005`:** **[Inference requiring further evidence]** If the cloud `alembic_version` is `0004_enterprise_governance`, that revision is not present in the repository graph. Alembic normally cannot resolve the current revision to a path ending at `0005`; an upgrade would likely fail before DDL. If a multi-head or manually altered version state allows DDL to proceed, the additive columns could be applied while the version history remains wrong, or fail if some of the six columns already exist. The result could be a schema that partially matches the ORM but a history that no tool can reproduce.

### 7.3 Scenario B — The governance changes were applied remotely but the migration file was lost

**Hypothesis:** The cloud schema contains changes from a real governance migration, but no copy of the revision file survives.

**Evidence required before proceeding:**

- Read-only cloud `alembic_version` contents and complete schema inventory, including tables, columns, types, nullability, defaults, constraints, indexes, and ownership.
- Evidence that the governance changes are actually present, not merely that the version row names them.
- Migration/deployment logs, backup artifacts, or Neon branch/PITR history that might contain the file or its SQL.
- A reconstructed, reviewed description of the governance changes derived from schema evidence, not from the name.
- A decision to author a new, reviewed merge or additive revision, or to rebuild on a fresh branch with a data-copy plan.

**Risk of blindly applying `0005`:** **[Inference requiring further evidence]** The same unresolved-parent problem applies. In addition, if the cloud already contains some or all of the six lineage columns under the governance history, `ADD COLUMN` will fail on the existing columns. PostgreSQL transactional DDL reduces the chance of a partially applied six-column batch, but it does not fix an unknown history, and a failed migration can still block deployment and require investigation under pressure. Reconstructing a migration from schema diffs is not equivalent to recovering the original; it needs review and tests.

### 7.4 Scenario C — The reported revision is incorrect or belongs to a different database history

**Hypothesis:** The Batch 12 claim was mistaken, stale, or referred to a different database, branch, or environment. The current cloud database may follow the repository chain or a different history entirely.

**Evidence required before proceeding:**

- Identification of the exact database/branch/project that `.env` targeted at Batch 12 and the exact target used now. The audit did not read `.env`, so even the current target identity is unknown.
- The current target's full `alembic_version` contents.
- A schema inventory compared with both the repository migration-built schema and the ORM.
- Any audit log, deployment record, or Neon branch history that explains how the claim originated.
- Confirmation that the six columns are either absent or already present with compatible definitions.

**Risk of blindly applying `0005`:** **[Inference requiring further evidence]** If the claim was wrong but the current database still differs from the repository base schema, `0005` can fail or create a misleading version state. If the current database matches `0004_verification_templates` and lacks only the six columns, `0005` is structurally the right shape—but that must be proven, not assumed from the claim's falsity. A report error does not itself make the target safe.

### 7.5 Scenario D — The remote history cannot yet be established

**Hypothesis:** None of the above can be resolved with the currently available evidence. This is the state of this audit.

**Evidence required before proceeding:**

- The full inventory listed in `docs/NEON_MIGRATION_RECONCILIATION_PLAN.md:240-263`, collected on a Neon branch by the database owner using catalog metadata only.
- A written, reviewed comparison against the repository chain and ORM.
- A restore point and an approved rehearsal plan.

**Risk of blindly applying `0005`:** **[Inference requiring further evidence]** The target's current revision, schema, and data are unknown. Any DDL could conflict with existing objects; any history operation could misstate the schema; and there is no basis for choosing between additive, merge, and rebuild strategies. The correct action is to stop at the inventory gate. This is the conservative reading of the current evidence and the one this audit adopts.

### 7.6 Mapping to the existing plan's strategy options

| Existing plan option | Meaning | Applicability here |
| --- | --- | --- |
| Option A — additive forward migration (`docs/NEON_MIGRATION_RECONCILIATION_PLAN.md:267-282`) | Add the missing columns after the repository's `0004_verification_templates`. | Only if inventory proves the cloud history can accept `0005` as a child and the six columns are absent/incompatible. `0005` is the local candidate; it is not authorized for the cloud. |
| Option B — merge revision (`:284-293`) | Preserve two histories with a merge revision after both graphs are understood. | Only if the governance revision is recovered/reconstructed and both histories are legitimate. Requires the missing revision file(s) or a reviewed reconstruction. |
| Option C — fresh branch rebuild and data copy (`:295-304`) | Rebuild from the canonical graph and migrate data through a reviewed process. | Only if the existing history cannot be reconstructed. Highest operational risk; data copy is outside this audit. |
| Option D — stamp to repository head (`:306-313`) | Assert a state without proving it. | **Rejected.** This audit does not recommend it. It converts visible drift into silent inconsistency. |

### 7.7 Common prerequisites and why `0005` is not automatically safe

**[Confirmed from repository evidence]** `0005` is additive, all six columns are nullable, and it adds no defaults, indexes, or foreign keys. On a database whose schema is exactly `0004_verification_templates` and whose `alembic_version` is exactly that revision, the DDL is low-risk for existing rows.

**[Inference requiring further evidence]** That precondition is precisely what is unverified. The history risk is independent of the DDL's additive shape:

- If the cloud version table names a revision absent from the repository, Alembic cannot compute the path to `0005`.
- If the cloud schema already has some of the six columns, the DDL conflicts even though it is "additive."
- If the cloud history has multiple heads or a version row inconsistent with the schema, Alembic's behavior depends on state that has not been inventoried.
- If a failed attempt leaves the version table and schema out of sync, later recovery is harder than starting from a known branch/restore point.

**[Confirmed from repository evidence]** The existing plan already requires a read-only inventory and a branch rehearsal before any change (`docs/NEON_MIGRATION_RECONCILIATION_PLAN.md:240-263, 321-359`). This audit adds no shortcut around those gates.

---

## 8. Explicit blockers and next safe steps

### 8.1 Blockers

1. **[Confirmed from repository evidence]** No remote database was contacted, by design. The cloud `alembic_version`, schema, data, branch identity, and restore points are unknown.
2. **[Confirmed from repository evidence]** No file defining `0004_enterprise_governance` exists in the working tree or in any inspected Git object. The revision cannot be recovered from this repository.
3. **[Confirmed from repository evidence]** The two newest migrations, including the only repository head, are untracked. They are preserved in the working tree but not protected by Git history.
4. **[Confirmed from repository evidence]** The explicit-connection safety path in `backend/migrations/env.py` is an uncommitted modification.
5. **[Confirmed from repository evidence]** The normal Alembic CLI has no loopback/test-target guard and follows `settings.database_url`, which may be configured for a remote database.
6. **[Confirmed from repository evidence]** Three server-default mismatches exist between migrations and ORM metadata, and the parity test does not compare server defaults.
7. **[Confirmed from repository evidence]** `backend/migrations/script.py.mako` is empty, which may impair future revision generation.
8. **[Reported previously but not independently verified]** The cloud database may have a divergent history. If true, it blocks any straightforward application of the repository's `0005`.

### 8.2 Ordered next safe steps

1. **Preserve the working tree.** Do not clean, reset, stash, or switch branches. Treat `0004_verification_templates.py`, `0005_verification_lineage.py`, and the modified `env.py` as critical uncommitted artifacts. When the user authorizes it, version-control them in a reviewed commit; this audit does not authorize that commit.
2. **Recover the governance migration from trustworthy sources.** Search other clones, developer machines, backups, CI artifacts, pull requests, database migration logs, and Neon branch/PITR history. Do not reconstruct it from the name alone. If no copy exists, record that fact and move to scenario B or D.
3. **Establish the target identity without connecting.** Identify the exact Neon project, branch, and environment that the current `.env` points to, without reading or printing credentials. Confirm whether Batch 12's claim referred to the same target.
4. **Collect the read-only inventory on a Neon branch.** Use catalog metadata only: current database/role/branch, full `alembic_version`, all tables/columns/types/nullability/defaults/constraints/indexes, whether the six columns exist and with what definitions, extra objects, ownership/privileges, and restore capability. The existing plan's section 9 is the checklist.
5. **Compare, then choose.** Compare the inventory with the repository migration-built schema and ORM. Choose additive (`0005` or a new revision), merge, or rebuild with a written rationale. If any inventory item is missing or contradictory, stop.
6. **Rehearse on a branch.** Apply the chosen revision to a Neon branch with a restore point; run migration-parity, migration-built application, template CRUD, multi-source persistence, aggregation, and health checks. Do not apply to the primary branch first.
7. **Handle server-default drift separately.** Decide whether the three database defaults are intentional. If they are not, author a reviewed follow-up migration and/or align the ORM declarations; do not bundle this into the cloud-history reconciliation without explicit review. Test authentication behavior for the empty `hashed_password` default.
8. **Restore the revision template.** Replace the empty `script.py.mako` with the project's intended Alembic template, or document that migrations are hand-written and the command is unsupported. This is a development-workflow fix, not a cloud migration.
9. **Consider a CLI safety guard.** Before future migration work, add an explicit target confirmation or a guard for normal CLI use, so `settings.database_url` cannot silently point Alembic at a remote database. Design it in a separate reviewed batch.
10. **Do not deploy a migration until the inventory gate is passed.** No stamping, no history-row deletion, no fabricated revision.

### 8.3 What not to do

**[Inference requiring further evidence]** The following would be unsafe under the current evidence:

- Running `alembic upgrade head` with the current `.env` configuration.
- Running `alembic stamp` to make the cloud version table match the repository.
- Deleting or editing rows in `alembic_version` by hand.
- Creating a file named `0004_enterprise_governance.py` with guessed operations.
- Applying `0005` because it is "only additive" without proving the base revision and column absence.
- Treating the prior Batch 16 local test results as proof of cloud compatibility.
- Treating the absence of the governance file from Git as proof that the cloud history claim is false.

---

## 9. Commands run and their outcomes

### 9.1 Nature of the commands

**[Confirmed from repository evidence]** All commands were read-only inspections. No command opened a database connection, invoked Alembic, ran a test, read `.env` values, or changed repository state. The hardcoded local URL in `backend/alembic.ini` was inspected but is not reproduced in this report; no credentials, tokens, or private keys are included.

### 9.2 Working-tree and Git inspection

| Command (or command group) | Purpose | Outcome |
| --- | --- | --- |
| `git status --porcelain=v1`, `git branch --show-current`, `git rev-parse HEAD`, `git log -1 --oneline` | Capture baseline identity and dirty state. | Branch `feature/batch-4-rule-engine-aggregation`; HEAD `c91e9b3`; 27 modified tracked files; large untracked set. |
| `git status --porcelain=v1 --untracked-files=all` (before report) | Expand untracked files for an exact baseline. | 63 entries; saved to a temporary file outside the repository for post-audit comparison. |
| `git diff --stat`; `git diff -- backend/migrations/env.py backend/alembic.ini backend/app/core/config.py`; `git status -- backend/migrations backend/alembic.ini` | Identify migration/config changes and confirm `env.py` modification. | 27 files changed, 4,813 insertions, 651 deletions; `env.py` has 16 added/2 removed lines implementing the explicit-connection path; `0004` and `0005` are untracked. |
| `git branch -a`, `git tag`, `git remote -v`, `git log --all --oneline --decorate -10` | Enumerate refs and reachable history. | Five local branches, two remote refs, no tags; reachable commits include Batches 1–4. |
| `git ls-tree -r --name-only <ref> -- backend/migrations` for `main`, `origin/main`, and the Batch 3/4 branches | Check every ref for tracked migration files. | Only `0001`–`0003` appear; no `0004`/`0005` and no governance file. |
| `git log --all --oneline -S'enterprise_governance' -- .`; `git log --all --oneline -S'0004_enterprise_governance'`; `git log --all --full-history --name-status -- '*enterprise_governance*'` | Search history for the governance string/path. | No matching commits or paths. |
| `git log --all --oneline -- backend/migrations`; `git log --all --oneline -- backend/migrations/versions`; `git log --all --stat -- backend/migrations/versions` | Inventory tracked migration history. | Only commits adding `0001`, `0002`, and `0003`. |
| `git log --all --diff-filter=D -- backend/migrations/versions` | Check for deleted tracked migrations. | No deletions. |
| `git rev-list --all --objects \| Select-String 'enterprise_governance'` | Search every reachable object path. | No matches. |
| `git fsck --unreachable --no-reflogs`; `git fsck --dangling --no-reflogs` | Inspect unreachable/dangling objects that `rev-list --all` cannot see. | Five unreachable trees and one dangling tree; no unreachable commits/blobs reported. |
| `git ls-tree -r --name-only <each unreachable tree>` filtered for migration/alembic/enterprise/governance paths | Check unreachable trees for a lost migration. | Only `0001`–`0003` (or no migration paths); no governance file. |
| `git reflog --all --date=iso` | Check recent ref operations for a lost commit/branch. | No governance-related entry. |
| `git status --porcelain=v1 --untracked-files=all` (after report) | Verify the only addition is this report. | 64 entries; the difference from the baseline is exactly `docs/audits/Batch18_Migration_History_Divergence_Audit.md`. |

### 9.3 File and content inspection

| Inspection | Purpose | Outcome |
| --- | --- | --- |
| Read `0001_initial_tables.py`, `0002_verification_runs.py`, `0003_user_password.py`, `0004_verification_templates.py`, `0005_verification_lineage.py` | Build the migration inventory and compare operations. | Linear chain; operations and downgrades as documented in section 3. |
| Read `backend/migrations/env.py` | Determine URL resolution and explicit-connection behavior. | Settings URL override at lines 24–25; explicit connection path at lines 57–66; normal engine at lines 68–85. |
| Read `backend/alembic.ini` and `backend/migrations/README` | Check configuration and migration conventions. | Hardcoded loopback URL (not reproduced); generic Alembic configuration; no extra safety guard. |
| Read `backend/migrations/script.py.mako` | Check revision template. | 0 bytes. |
| Read `backend/app/models/__init__.py`, `user.py`, `project.py`, `source_file.py`, `verification_run.py`, `verification_template.py` | Compare ORM metadata with migrations. | Six tables; six lineage columns match `0005`; three server-default mismatches. |
| Read `backend/tests/pg_test_target.py` | Evaluate test-target isolation. | Fail-closed loopback/test-name/app-DB/redirect guard; no connection during validation. |
| Read `backend/tests/test_alembic_migration_parity.py`, `test_postgres_migration_application.py`, `conftest.py` | Evaluate migration test setup and default harness. | Opt-in PostgreSQL suites with explicit connection; default in-memory SQLite with `create_all`. |
| Read `docs/NEON_MIGRATION_RECONCILIATION_PLAN.md`, `docs/REUSABLE_VERIFICATION_TEMPLATES_DESIGN.md`, `docs/POSTGRES_INTEGRATION_TESTING.md` | Distinguish prior claims from evidence. | Plan and design repeat the governance claim; plan explicitly treats remote state as unverified. |
| `Get-ChildItem` over `docs/`, `backend/migrations/`, `backend/app/models/`, `backend/tests/`, and repository root | Inventory files and check for additional migration/report artifacts. | Five migrations; four pre-existing docs files; no standalone Batch 12 report; many untracked tests. |
| PowerShell `Select-String` and the harness `grep` tool across application, migration, test, docs, and config paths for `enterprise_governance`, `0004_verification_templates`, `0005_verification_lineage`, `alembic_version`, `stamp`, `create_all`, `command.upgrade`, and `run_migrations` | Locate all references and startup behavior. | Governance string only in the `0004` docstring and untracked docs; `alembic_version` only in test helpers; no startup migration or `create_all` in application code. |
| `Get-Content backend/app/main.py` | Check for startup migration hooks. | No Alembic or `create_all`; only app creation, CORS, and router inclusion. |

The shell reported that `rg` (ripgrep) was unavailable in PATH; the equivalent searches were performed with PowerShell `Select-String` and the harness `grep` tool. This did not affect the conclusions.

### 9.4 Tests and database commands

**[Confirmed from repository evidence]**

- **Tests executed: none.**
- **Alembic commands executed: none.** No `upgrade`, `downgrade`, `stamp`, `revision`, `current`, `history`, or `heads` command was run.
- **Database connections opened: none.**
- **`.env` values read: none.** Only the existence and location of `backend/.env` were observed from a directory listing.
- **Schema or data changes: none.**

**Why no tests were run:** The PostgreSQL migration-parity and migration-built application suites are opt-in and require an explicitly supplied `VERIFYGRID_TEST_DATABASE_URL`. No such isolated target was provided, and this audit's constraints do not authorize obtaining one. The default SQLite suite is isolated by its in-memory configuration, but it builds the schema with `Base.metadata.create_all`; it would not provide evidence about the Alembic chain, the working-tree migrations, the server-default drift, or the reported cloud history. Running it could misleadingly suggest migration verification. The audit therefore relied on static, read-only evidence and did not execute tests. Prior Batch 16 results remain reported but not independently verified.

---

## 10. Final verdict

### 10.1 Verdict

**PASS — audit scope only.**

The Batch 18 investigation is complete. The repository-side facts are established, the prior cloud claim is correctly separated from verified evidence, the ORM/migration drift is documented, the Alembic/test isolation behavior is assessed, and the required report has been produced. All mandatory safety constraints were observed.

### 10.2 Verdict qualifications

- **Not a PASS for cloud reconciliation.** Neon was not contacted, and its schema, data, branch identity, and `alembic_version` contents remain unknown.
- **Not a PASS for applying `0005` to the cloud.** The repository head is valid for the repository graph, but the cloud history is unverified and the missing governance revision is unresolved.
- **Not a PASS for full ORM/migration parity.** Static coverage is complete at the table/column level, but three server-default mismatches remain and the parity test does not compare them.
- **Not a replacement for the existing reconciliation plan.** `docs/NEON_MIGRATION_RECONCILIATION_PLAN.md` remains the governing plan; this audit supplies repository evidence and confirms its inventory gate is still unmet.

### 10.3 Recommended next action

**Do not apply any migration to the cloud.** First recover the governance migration from a trustworthy source and collect the read-only Neon branch inventory described in the existing plan (branch identity, full `alembic_version`, complete schema inventory, six-column status, extra objects, privileges, and restore capability). Until that inventory is reviewed, the only safe status is **blocked and unverified**.

The highest-priority repository-side action is to preserve and version-control the untracked `0004_verification_templates.py`, `0005_verification_lineage.py`, and the modified `env.py` once the user authorizes a commit. Losing them would destroy the only copies of the repository's current migration head and its explicit-connection test safety path.
