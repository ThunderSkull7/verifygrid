# Batch 25 - Offline Migration and Tooling Report

**Date:** 2026-10-29  
**Repository:** `C:\Users\shaha\verifygrid`  
**Branch:** `feature/batch-4-rule-engine-aggregation`  
**HEAD:** `c91e9b37074483eeb7469dc943e1735fd5f5be02`  
**Verdict:** **PARTIAL - authorized offline tooling scope PASS; full Batch 24 section 10.4 acceptance not met because `0005`/`0006` and the local database rebuild were explicitly deferred.**

> This report records only the Batch 25 offline migration/tooling work. It does
> not authorize Batch 26, an application merge, a production migration, a
> deployment, a database stamp, or any remote database action.

---

## 1. Executive summary and verdict

### 1.1 Result

Batch 25 completed the authorized offline migration-graph and tooling work
against the recovered canonical `0004_enterprise_governance` baseline:

- The local `0004_verification_templates` and `0005_verification_lineage`
  revisions were archived byte-identically and removed from the active graph.
- The preserved deployed `0004_enterprise_governance_and_materiality.py` was
  restored as a byte-identical copy with SHA-256
  `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB`.
- The active graph is linear and has exactly one head:
  `0004_enterprise_governance`.
- `env.py` now requires an explicit target, fails closed in integration mode,
  rejects remote targets without both guard variables, and verifies the live
  database, role, and server address before DDL.
- `alembic.ini` contains no usable `sqlalchemy.url`.
- The empty `script.py.mako` was replaced with the Alembic 1.20.0 generic
  template; a throwaway generation test produced a syntactically valid revision
  without touching the repository graph.
- The guard test suite passed 29/29; the combined target-guard suite passed
  40/40; the canonical `0004` parity suite passed 3/3 on a disposable loopback
  PostgreSQL 18.6 cluster.
- Offline SQL from `0003_user_password` to `0004_enterprise_governance`
  generated 10,354 bytes with one `CREATE TABLE`, 33 `ADD COLUMN` statements,
  zero `DROP` statements, and each of the six retired lineage columns exactly
  once.

### 1.2 Why the verdict is PARTIAL rather than PASS

The Batch 24 memo's full manifest includes
`0005_verification_templates` and `0006_discrepancy_review_decisions`, and its
section 10.4 requires the single head to be
`0006_discrepancy_review_decisions`. The governing Batch 25 instruction
explicitly excluded those two application revisions and directed that the
canonical graph end at `0004_enterprise_governance`. Batch 25 followed the
newer instruction. Consequently:

- Every check within the narrower authorized scope passed.
- The Batch 24 section 10.4 acceptance criteria that depend on `0005`/`0006`
  remain open.
- The local development database rebuild remains deferred.
- The application/ORM assertions in
  `test_postgres_migration_application.py` remain Batch 26 work.

The batch is therefore not reported as PASS. No test was skipped and then
counted as passed; the unavailable application tests are marked **BLOCKED**.

### 1.3 Status by area

| Area | Status | Evidence |
| --- | --- | --- |
| Authorized Batch 25 offline tooling | **PASS** | Sections 3-7 |
| Canonical graph ending at recovered `0004` | **PASS** | Section 4 |
| Explicit-target / fail-closed guard | **PASS** | Section 5 |
| Guard unit and target tests | **PASS** | 29 passed; 40 passed combined |
| Canonical `0004` PostgreSQL parity tests | **PASS** | 3 passed on disposable loopback PG 18.6 |
| Offline SQL for `0003 -> 0004` | **PASS** | 10,354 bytes; 1 create, 33 adds, 0 drops |
| Full Batch 24 `0005`/`0006` acceptance | **DEFERRED** | Explicitly excluded by the Batch 25 instruction |
| Application/ORM migration tests | **BLOCKED** | Batch 26 merge required |
| Local development database rebuild | **DEFERRED** | No owner attestation; destructive action not authorized |
| Production migration / deployment | **NOT AUTHORIZED** | Outside Batch 25 |

---

## 2. Baseline and final Git state

### 2.1 Repository identity

| Item | Baseline | Final |
| --- | --- | --- |
| Branch | `feature/batch-4-rule-engine-aggregation` | Same |
| HEAD | `c91e9b37074483eeb7469dc943e1735fd5f5be02` | Same |
| Staged changes | None | None |
| Commit / push / merge / branch change | Not performed | Not performed |
| Working-tree entries (`git status --porcelain=v1 --untracked-files=all`) | 70 | 76, including this report |

The baseline working tree already contained 70 pre-existing entries from
earlier batches. Batch 25 did not alter, clean, stage, or commit those entries.
The batch-specific delta is limited to the paths listed in section 3.

### 2.2 Exact delta from the Batch 25 baseline

The baseline and final status files were compared with `Compare-Object`. The
only additions and removals were:

**Added or newly modified entries:**

```text
 M backend/alembic.ini
 M backend/migrations/script.py.mako
?? backend/migrations/retired/0004_verification_templates.py
?? backend/migrations/retired/0005_verification_lineage.py
?? backend/migrations/versions/0004_enterprise_governance_and_materiality.py
?? backend/tests/test_migration_env_guard.py
?? docs/audits/Batch24_Migration_Provenance.md
?? docs/audits/Batch25_Offline_Migration_and_Tooling_Report.md
```

**Removed from the active graph:**

```text
?? backend/migrations/versions/0004_verification_templates.py
?? backend/migrations/versions/0005_verification_lineage.py
```

`backend/migrations/env.py`,
`backend/tests/test_alembic_migration_parity.py`, and
`backend/tests/test_postgres_migration_application.py` were already present in
the baseline status with the same `M`/`??` classification; their contents were
changed in place, so they do not appear as new entries in the delta.

No entry under `backend/app/`, `frontend/`, `backend/app/api/`, or any
application route, model, schema, or service directory was added or removed.

### 2.3 Tracked diff summary

```text
 backend/alembic.ini               |   4 +-
 backend/migrations/env.py         | 406 +++++++++++++++++++++++++++++++----
 backend/migrations/script.py.mako |  28 +++
 3 files changed, 395 insertions(+), 43 deletions(-)
```

The Git line-ending warnings for these three files are expected on Windows and
do not represent content drift in the working tree.

---

## 3. Exact file changes and hashes

### 3.1 Changed files

| Path | Action | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `backend/migrations/versions/0004_enterprise_governance_and_materiality.py` | Added, byte-identical recovered baseline | 10,032 | `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` |
| `backend/migrations/retired/0004_verification_templates.py` | Archived from active graph | 2,936 | `CBE7E536573D06D49E4EB2F8EFB7BD26A0D3CCA786F01EA80AE7C8E7CA74E227` |
| `backend/migrations/retired/0005_verification_lineage.py` | Archived from active graph | 3,144 | `645BE701DFF05FDF6D263AF678CB17E77D818CE64C00A8B9F3AF96E46E585713` |
| `backend/migrations/versions/0004_verification_templates.py` | Deleted from active graph | 2,936 | Hash preserved in archive |
| `backend/migrations/versions/0005_verification_lineage.py` | Deleted from active graph | 3,144 | Hash preserved in archive |
| `backend/migrations/env.py` | Edited: explicit-target, fail-closed guard | 14,018 | `70942FF899381F687DDEC12C53E91EE509F9BF37D4D7EEAEA8D3042675E45A97` |
| `backend/alembic.ini` | Edited: removed usable URL | 795 | `E7461085260EC18A0A5B00C75E9D1A5924D0E7C574CC4F61CF6B8D0367FBC430` |
| `backend/migrations/script.py.mako` | Replaced empty file with Alembic 1.20.0 generic template | 704 | `D38920781B4D31AE1C0A71BC09F41C2ADE8FEAB9E5A087E3F30CB4BBF0C1C9D3` |
| `backend/tests/test_migration_env_guard.py` | Added: 29 guard/template/graph tests | 13,295 | `D8312E07D8495644B0159126681599A970122D7DF0743BBD998D4BB97A4480B7` |
| `backend/tests/test_alembic_migration_parity.py` | Rewritten for canonical `0004` migration introspection | 24,009 | `56942E378F12DFB926BE3083742D6CFA6566BA7740F315509CFD2D4133825C4A` |
| `backend/tests/test_postgres_migration_application.py` | Edited: `EXPECTED_HEAD` constant only; assertions deferred | 18,486 | `432824599A1FC01607ADE553B57BD9D1F7EAB5184B75D120730C533C0DA93BDC` |
| `docs/audits/Batch24_Migration_Provenance.md` | Added: provenance and retirement record | 4,388 | `492655477DC2DD643391ED038BED2AB4355BB9979286237FCD39C477F6F82156` |
| `docs/audits/Batch25_Offline_Migration_and_Tooling_Report.md` | Added: this report | See file metadata | See file metadata |

### 3.2 Files deliberately left unchanged

| Path | SHA-256 | Note |
| --- | --- | --- |
| `backend/tests/pg_test_target.py` | `AEC58B947EE476314CF4CE28A9A5F354A7304B905A91EA7B352D2BD019380074` | Existing fail-closed test-target guard reused unchanged |
| `backend/tests/test_postgres_target_guard.py` | `A157A7B009F77BB9DE8081FBEF62673F3F56CD0B75F8E5DFF67245E14F1E6E4C` | Existing target-guard tests reused unchanged |
| `docs/audits/Batch24_Architecture_Decision_Memo.md` | `86AB323B1D3B4738790DAE829519CB5E5226B26A1EE5D2EFD47BC713DE25D582` | 1,547 lines, 123,450 bytes; unchanged |
| `backend/migrations/versions/0001_initial_tables.py` | `F3E045B29E52A132947E6ED156BA57995FD45B75EAA2C7D6289901C5AFD569A0` | Unchanged |
| `backend/migrations/versions/0002_verification_runs.py` | `44A9CD93E9A1260C7C61E3029FD6F884B5B27523FDCE25D966C986748AD78B2E` | Unchanged |
| `backend/migrations/versions/0003_user_password.py` | `6F256919E0E2537468335FF0A6C253E80BC513E3DFB6D414F9564C10083902E6` | Unchanged |

### 3.3 `env.py` design summary

`backend/migrations/env.py` now performs the following before any migration
DDL:

1. Selects a target only from `config.attributes["connection"]`,
   `-x db_url=...`, or `VERIFYGRID_MIGRATION_DATABASE_URL`.
2. Rejects `DATABASE_URL`, `settings.database_url`, `.env`, and
   `alembic.ini` URLs as migration targets.
3. Requires the `postgresql+psycopg` driver, an explicit host, a non-system
   database name, and an explicit login role.
4. Rejects redirect-capable query parameters such as `host`, `hostaddr`,
   `port`, `dbname`, `service`, and `servicefile`.
5. Allows loopback targets by default and requires both
   `VERIFYGRID_ALLOW_PRODUCTION_MIGRATION=1` and a non-empty
   `VERIFYGRID_PRODUCTION_MIGRATION_ACK` for a non-loopback target.
6. In PostgreSQL integration mode, requires an explicitly validated
   connection and a dedicated loopback test database and role containing
   `test`.
7. Checks `current_database()`, `current_user`, and
   `inet_server_addr()` against the validated URL before configuring Alembic.
8. Fails closed when a test-mode run has no explicit connection.

The module no longer contains `settings.database_url`,
`from app.core.config import settings`, `engine_from_config`, or
`sqlalchemy.url`.

### 3.4 Alembic configuration and template

`backend/alembic.ini` retains the standard logging configuration and
`script_location`, but has no `sqlalchemy.url` line and no PostgreSQL URL. The
comment directs callers to supply a target explicitly.

`backend/migrations/script.py.mako` is the Alembic 1.20.0 generic template,
704 bytes, SHA-256
`D38920781B4D31AE1C0A71BC09F41C2ADE8FEAB9E5A087E3F30CB4BBF0C1C9D3`. The
Batch 24 memo describes the generic template as 20 lines; the actual 1.20.0
template is 28 lines. The hash matches the approved generic template, and the
throwaway generation test confirms that it produces a valid revision with the
correct parent.

---

## 4. Canonical migration graph evidence

### 4.1 Active graph

`python -m alembic -c alembic.ini heads` exited 0 and returned exactly:

```text
0004_enterprise_governance (head)
```

`python -m alembic -c alembic.ini history` exited 0 and returned:

```text
0003_user_password -> 0004_enterprise_governance (head), Add enterprise governance, materiality, clustering, and audit events
0002_verification_runs -> 0003_user_password, Add hashed_password to users table
0001_initial_tables -> 0002_verification_runs, Verification runs and discrepancies tables
<base> -> 0001_initial_tables, Initial tables for users, projects, and source_files
```

### 4.2 Revision metadata

| Revision | Parent | Status |
| --- | --- | --- |
| `0001_initial_tables` | `None` | Active |
| `0002_verification_runs` | `0001_initial_tables` | Active |
| `0003_user_password` | `0002_verification_runs` | Active |
| `0004_enterprise_governance` | `0003_user_password` | Active, single head |

The active `backend/migrations/versions/` directory contains exactly four
Python files, matching the four active revisions above.

### 4.3 Retired revisions

| Revision | Archived path | SHA-256 | Active graph |
| --- | --- | --- | --- |
| `0004_verification_templates` | `backend/migrations/retired/0004_verification_templates.py` | `CBE7E536573D06D49E4EB2F8EFB7BD26A0D3CCA786F01EA80AE7C8E7CA74E227` | No |
| `0005_verification_lineage` | `backend/migrations/retired/0005_verification_lineage.py` | `645BE701DFF05FDF6D263AF678CB17E77D818CE64C00A8B9F3AF96E46E585713` | No |

A search of the active versions directory for the strings
`0005_verification_lineage` and `0004_verification_templates` returned no
hits. Alembic regenerates the graph from active revision metadata, so the
retired files cannot be discovered from `retired/`.

### 4.4 Retired-replay negative control

Replaying the retired revision was attempted offline with an explicit loopback
URL:

```powershell
python -m alembic -c alembic.ini -x db_url="postgresql+psycopg://verifygrid_test_admin@127.0.0.1:55432/verifygrid_test" upgrade 0005_verification_lineage --sql
```

The command exited 1 with:

```text
FAILED: Can't locate revision identified by '0005_verification_lineage'
```

This is the expected negative result. It confirms that the retired revision
cannot be replayed accidentally. The six lineage columns that revision used to
add are owned by the recovered `0004_enterprise_governance` revision:

- `verification_runs.sources`
- `verification_discrepancies.source_row_indices`
- `verification_discrepancies.source_records`
- `verification_discrepancies.child_records`
- `verification_discrepancies.aggregated_amount`
- `verification_discrepancies.expected_amount`

### 4.5 Recovered `0004` provenance

| Property | Value |
| --- | --- |
| Revision ID | `0004_enterprise_governance` |
| Parent | `0003_user_password` |
| Recovered source | Preserved deployed tree for commit `58a0e5c243978480c4ca817c537c700ed6b20516` |
| Destination | `backend/migrations/versions/0004_enterprise_governance_and_materiality.py` |
| Source SHA-256 | `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` |
| Destination SHA-256 | `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` |
| Bytes | 10,032 |
| Byte-identical | Yes |

The full provenance record, including retrieval date and retirement decision,
is in `docs/audits/Batch24_Migration_Provenance.md`.

---

## 5. Migration environment guard design and results

### 5.1 Target sources

| Source | Accepted | Notes |
| --- | --- | --- |
| `config.attributes["connection"]` | Yes | Programmatic/test path; URL and live identity are validated |
| `-x db_url=...` | Yes | Explicit CLI/offline path |
| `VERIFYGRID_MIGRATION_DATABASE_URL` | Yes | Explicit environment path |
| `DATABASE_URL` | No | Deliberately ignored; tested |
| `settings.database_url` | No | Removed; tested statically |
| `backend/.env` | No | Never read as a target |
| `alembic.ini` `sqlalchemy.url` | No | Removed; tested statically |

`-x db_url` takes precedence over `VERIFYGRID_MIGRATION_DATABASE_URL`. Both are
validated with the same policy.

### 5.2 Validation policy

| Check | Behavior |
| --- | --- |
| Missing target | Fails before connecting |
| Invalid URL | Fails closed |
| Non-`postgresql+psycopg` driver | Rejected |
| Missing host, database, or role | Rejected |
| System database (`postgres`, `template0`, `template1`) | Rejected |
| Redirect query parameter | Rejected |
| Loopback host | Accepted after DNS resolution returns only loopback addresses |
| Non-loopback host without both guard variables | Rejected |
| Non-loopback host with both guard variables | Accepted, with a live non-loopback address check |
| Test mode without explicit connection | Fails closed |
| Test database name without `test` or on the disallowed list | Rejected |
| Test role without `test` | Rejected |
| Live database mismatch | Rejected before DDL |
| Live role mismatch | Rejected before DDL |
| Missing or non-loopback live address in test mode | Rejected |
| Ambiguous non-loopback target reaching a loopback server | Rejected |

The remote guard variables are guardrails, not production authorization. No
production migration is authorized by this report.

### 5.3 Static guard checks

The following tokens are absent from `backend/migrations/env.py`:

```text
settings.database_url
from app.core.config import settings
engine_from_config
sqlalchemy.url
```

`backend/alembic.ini` contains no `sqlalchemy.url` and no
`postgresql+psycopg://` URL.

### 5.4 Guard test results

`backend/tests/test_migration_env_guard.py` contains 29 tests covering:

- no application-settings or INI fallback;
- missing target, `DATABASE_URL` rejection, and `-x` precedence;
- driver, system-database, redirect, and remote-target rejection;
- both remote guard variables, including the requirement that both be present;
- loopback-only resolution;
- test database and test role naming;
- live database, role, address, and ambiguity checks;
- CLI missing-target and integration-mode failures before connecting;
- `heads` and `history` working without a target;
- linear graph and single-head assertions;
- retired-revision absence;
- recovered `0004` hash equality;
- throwaway template generation with correct parent and no repository change.

Executed result:

```text
29 passed, 1 warning in 2.94s
exit code 0
```

The warning is the pre-existing Starlette `httpx` deprecation warning from the
FastAPI test client import; it is unrelated to the migration guard.

The existing target-guard suite was also run together with the new suite:

```text
40 passed, 1 warning in 3.03s
exit code 0
```

---

## 6. Executed tests

### 6.1 Test environment

The PostgreSQL tests used a disposable cluster created for Batch 25:

| Item | Value |
| --- | --- |
| PostgreSQL | 18.6, x86_64-windows |
| Host / port | `127.0.0.1:55432` |
| Test role | `verifygrid_test_admin` |
| Test database | `verifygrid_test` |
| Cluster directory | `C:\Users\shaha\AppData\Local\Temp\opencode\batch25_pg2` |
| Authentication | `trust`, local only |
| `listen_addresses` | `127.0.0.1` only |

The test process received explicit variables:

```powershell
$env:VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS = "1"
$env:VERIFYGRID_TEST_DATABASE_URL = "postgresql+psycopg://verifygrid_test_admin@127.0.0.1:55432/verifygrid_test"
$env:DATABASE_URL = "postgresql+psycopg://verifygrid_app:placeholder@127.0.0.1:5432/verifygrid"
```

`DATABASE_URL` was set to a loopback placeholder specifically to prove that it
is not used as a migration target. `VERIFYGRID_MIGRATION_DATABASE_URL` was
removed for the parity run; Alembic received the already-validated connection
through `config.attributes["connection"]`.

The first disposable cluster (`batch25_pg`) suffered Windows child-process
failures (`0xC0000142` and shared-memory error 487) after initialization. It
was stopped immediately and not used for tests. The successful cluster
(`batch25_pg2`) was started by invoking `postgres.exe` directly in the
background. This was an environment workaround, not a product-code change.

### 6.2 Executed test commands

| Command | Scope | Result | Exit |
| --- | --- | --- | ---: |
| `python -m pytest tests\test_migration_env_guard.py -q` | Guard, template, graph; no DB | 29 passed | 0 |
| `python -m pytest tests\test_postgres_target_guard.py tests\test_migration_env_guard.py -q` | Existing + new guard suites; no DB | 40 passed | 0 |
| `python -m pytest tests\test_alembic_migration_parity.py -q` | Canonical `0004` on disposable loopback PG | 3 passed | 0 |
| `python -m py_compile migrations\env.py tests\test_migration_env_guard.py tests\test_alembic_migration_parity.py tests\test_postgres_migration_application.py` | Syntax compilation | Success | 0 |

### 6.3 Canonical `0004` parity tests

The three executed tests were:

1. `test_alembic_head_matches_canonical_baseline` - upgrades an empty schema to
   head, asserts revision `0004_enterprise_governance`, and asserts the exact
   migrated table/column/index/foreign-key inventory.
2. `test_upgrade_preserves_legacy_rows_and_applies_defaults` - upgrades to
   `0003_user_password`, inserts representative legacy rows, upgrades to
   `0004`, and asserts payload preservation plus governance defaults.
3. `test_empty_downgrade_and_reupgrade_round_trip` - upgrades to `0004`,
   downgrades to `0003`, verifies governance objects are absent, and upgrades
   again.

The tests assert the schema from migration introspection only. They do not use
`Base.metadata.create_all` and do not claim ORM parity. Verified facts include:

- Tables: `users`, `projects`, `source_files`, `verification_runs`,
  `verification_discrepancies`, `audit_events`, `alembic_version`.
- `users.role` is `character varying`, non-null, default containing `MAKER`.
- Ten governance columns on `verification_runs`, including
  `sign_off_status` default `DRAFT`.
- Twenty-two governance columns on `verification_discrepancies`, including
  `currency` default `USD`, `severity` default `medium`, and
  `resolution_status` default `unresolved`.
- Fourteen columns on `audit_events`, including `sequence_number` default `1`
  and `timestamp_utc` default `now()`.
- Expected indexes and foreign keys, including `audit_events` `CASCADE` to
  projects and runs and `SET NULL` to users.
- `verification_templates` and `discrepancy_review_decisions` are absent, as
  expected for the canonical `0004` graph.

`verification_templates` is absent because `0005_verification_templates` is
not part of Batch 25. `discrepancy_review_decisions` is absent because
`0006_discrepancy_review_decisions` is not part of Batch 25.

### 6.4 Online CLI smoke check on the disposable target

An explicit online upgrade was run only against the disposable loopback test
database to verify the CLI path:

```powershell
$env:VERIFYGRID_MIGRATION_DATABASE_URL = "postgresql+psycopg://verifygrid_test_admin@127.0.0.1:55432/verifygrid_test"
python -m alembic -c alembic.ini current
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini current
```

The commands exited 0. The database reached `0004_enterprise_governance` and
contained seven public tables including `alembic_version`. The `users.role`
column was `character varying`, non-null, with default
`'MAKER'::character varying`.

This check did not use the local development database on port 5432, did not
stamp the database, and did not connect to any remote target.

### 6.5 Negative controls

These non-zero results were intentional and are not test failures:

| Control | Exit | Observed message |
| --- | ---: | --- |
| `alembic current` with only `DATABASE_URL` set | 1 | `An explicit migration target is required.` |
| Integration mode without `config.attributes["connection"]` | 1 | `PostgreSQL integration mode requires an explicitly validated connection...` |
| Remote target without both guard variables | 1 | `Refusing a non-loopback migration target...` |
| Offline upgrade to retired `0005_verification_lineage` | 1 | `Can't locate revision identified by '0005_verification_lineage'` |

### 6.6 Test-cluster cleanup

After the tests:

1. The `verifygrid_test` database was dropped with `--force`.
2. It was recreated empty.
3. `SELECT count(*) FROM information_schema.tables WHERE table_schema='public'`
   returned `0`.
4. The cluster was stopped with `pg_ctl stop -m fast`; exit 0.
5. `pg_isready -h 127.0.0.1 -p 55432` returned `no response`; exit 2.
6. No listener remained on port 55432.

The pre-existing local PostgreSQL service on port 5432 was not contacted,
stopped, or modified.

---

## 7. Static checks and offline SQL

### 7.1 Graph checks

| Command | Result | Exit |
| --- | --- | ---: |
| `python -m alembic -c alembic.ini heads` | Exactly `0004_enterprise_governance (head)` | 0 |
| `python -m alembic -c alembic.ini history` | Linear `0001 -> 0002 -> 0003 -> 0004`; no retired revision | 0 |
| Active versions directory inspection | Exactly four `.py` files | 0 |
| Retired directory inspection | Exactly two archived `.py` files | 0 |
| Active-graph retired-ID search | No hits | 0 |

### 7.2 Offline SQL

Generated with:

```powershell
python -m alembic -c alembic.ini -x db_url="postgresql+psycopg://verifygrid_test_admin@127.0.0.1:55432/verifygrid_test" upgrade 0003_user_password:0004_enterprise_governance --sql
```

| Metric | Result |
| --- | ---: |
| Exit code | 0 |
| Output bytes | 10,354 |
| `CREATE TABLE` statements | 1 (`audit_events`) |
| `ALTER TABLE ... ADD COLUMN` statements | 33 |
| `DROP` statements | 0 |
| `users.role` additions | 1 |
| Six retired lineage columns | Each exactly once |
| Duplicate lineage DDL | None |

The 33 additions are the `users.role` column, ten `verification_runs`
governance columns, and twenty-two `verification_discrepancies` governance
columns. The six lineage columns formerly added by
`0005_verification_lineage` are present in the recovered `0004` DDL exactly
once and are not dropped.

The exact offline SQL is retained at
`C:\Users\shaha\AppData\Local\Temp\opencode\batch25\offline_final.sql`. It was
inspected, not merely generated.

### 7.3 Repository hygiene

| Check | Result |
| --- | --- |
| Staged changes | None |
| New application/frontend files | None |
| Stray migration files outside `versions/` and `retired/` | None |
| `env.py` forbidden fallback tokens | All absent |
| `alembic.ini` usable URL | Absent |
| Recovered `0004` hash | Matches provenance |
| Archived revision hashes | Match baseline |
| Python compilation of changed test/tooling files | Exit 0 |
| `alembic stamp` | Never invoked |

The only files in `backend/migrations/` outside `versions/` and `retired/` are
`env.py`, `script.py.mako`, `README`, and expected Python cache/package files.
The active `versions/` directory has exactly the four canonical revisions.

---

## 8. Blocked tests, deviations, and acceptance matrix

### 8.1 Deviation from the Batch 24 manifest

The Batch 24 memo's section 10.2 manifest includes:

- `backend/migrations/versions/0005_verification_templates.py`
- `backend/migrations/versions/0006_discrepancy_review_decisions.py`
- `backend/tests/test_postgres_reconciliation_design.py`
- A `0006` head and the full eight-table canonical schema

The Batch 25 instruction explicitly excluded the two `0005`/`0006` application
revisions and directed that the canonical graph end at
`0004_enterprise_governance`. Therefore:

| Manifest item | Actual Batch 25 disposition |
| --- | --- |
| `0005_verification_templates.py` | Not created; deferred |
| `0006_discrepancy_review_decisions.py` | Not created; deferred |
| `test_postgres_reconciliation_design.py` | Not created; its graph/`0005`/`0006` assertions depend on the deferred revisions |
| `PREVIOUS_HEAD = "0004_enterprise_governance"` | Implemented as `PREVIOUS_HEAD = "0003_user_password"` for the canonical `0003 -> 0004` path |
| `EXPECTED_HEAD = "0006_discrepancy_review_decisions"` | Set to `"0004_enterprise_governance"` in the application test constant only |
| Local DB rebuilt at `0006` | Deferred; no owner attestation and no destructive local action authorized |

This deviation is intentional, was directed by the newer Batch 25 instruction,
and is not a test failure. It does mean the Batch 24 section 10.4 criteria for
`0005`, `0006`, the `0006` head, and the full eight-table inventory remain
open. This report itself is the required deliverable and is not an application
change; it is the only documentation file added beyond the memo's manifest.

### 8.2 Blocked tests

| Test / requirement | Status | Exact blocker |
| --- | --- | --- |
| `backend/tests/test_postgres_migration_application.py` application assertions | **BLOCKED** | Import the unmerged ORM, which still expects the retired local schema (`verification_templates`) and lacks the canonical application merge. Batch 26 work. |
| T1 full eight-table fresh migration | **BLOCKED** | `0005_verification_templates` and `0006_discrepancy_review_decisions` are not implemented. |
| T2 full `0001 -> 0004 -> 0005 -> 0006` path | **BLOCKED** | `0005`/`0006` absent. The `0001 -> 0004` subset passed. |
| T3 production-scale 33-run / 25,654-discrepancy preservation | **BLOCKED** | Not implemented in Batch 25; no production-scale seed was authorized. |
| T4 exact `0004 -> 0006` offline SQL with two `CREATE TABLE`s | **BLOCKED** | `0005`/`0006` absent. The `0003 -> 0004` offline SQL passed with no duplicate lineage. |
| T10 `is_bulk_action=false` default | **BLOCKED** | Belongs to `0006`; the available `0004` defaults (`role`, `sign_off_status`, `currency`, `severity`, `resolution_status`) passed. |
| T11 `0006 -> 0004` round trip | **BLOCKED** | `0005`/`0006` absent. The `0004 -> 0003 -> 0004` round trip passed. |
| T13 local canonical rebuild at `0006` | **PARTIAL** | A fresh disposable loopback database was built `0001 -> 0004` by the CLI; no local development database was rebuilt and no `0006` comparison exists. |
| T5-T9, T12, T14 | **BLOCKED** | Application/ORM, review, audit, rollback-policy, and startup tests are Batch 26 work. |
| Local development database rebuild | **DEFERRED** | Batch 25 prohibits destructive local-database operations and no written owner attestation was provided. |

No application test was executed against the unmerged ORM. A failure there
would not have been evidence about the canonical schema, and a pass could not
have been claimed without the Batch 26 merge.

### 8.3 Batch 24 section 10.4 acceptance matrix

| Criterion | Status | Notes |
| --- | --- | --- |
| Active versions contain exactly `0001`, `0002`, `0003`, recovered `0004`, `0005`, `0006` | **NOT MET (deferred)** | Active graph intentionally ends at `0004` |
| `alembic heads` returns exactly one head at `0006` | **NOT MET (deferred)** | Single head is `0004_enterprise_governance` |
| No active revision declares the retired IDs | **MET** | No active-graph hits |
| Recovered `0004` hash matches | **MET** | `44D31AE9...A7AEB` |
| Offline `0004 -> 0006` SQL has two creates and no duplicate lineage DDL | **DEFERRED** | `0003 -> 0004` offline SQL has one create, 33 adds, no drops, no duplicate lineage |
| `0005` has 10 columns, `SET NULL`, unique `(owner_id, name)`, owner index | **DEFERRED** | Revision not created |
| `0006` has 12 columns, two `RESTRICT` FKs, four indexes, `is_bulk_action=false` | **DEFERRED** | Revision not created |
| Template generates a valid revision in a temp directory | **MET** | 29-test suite includes generation; repository graph unchanged |
| `env.py` has no settings fallback; missing target fails; test mode fails; identity mismatch aborts | **MET** | Guard suite passed |
| `alembic.ini` contains no usable URL | **MET** | Static check passed |
| T1-T4, T10, T11, T13 pass on the isolated target | **PARTIAL** | Canonical `0004` subset passed; full `0005`/`0006` matrix blocked |
| No application model/schema/service/endpoint changed | **MET** | Delta contains no `backend/app/` or frontend paths |
| No untracked migration artifact remains | **MET** | Only intentional new files; no stray artifacts |
| Local DB rebuilt at `0006`, or deferral recorded | **DEFERRED, RECORDED** | Deferral recorded in this report and the provenance note |
| Evidence package contains commands, hashes, test output, graph proof, offline SQL | **MET** | This report plus retained logs and SQL |

Overall Batch 24 section 10.4 status: **PARTIAL**. The authorized subset is
complete; the `0005`/`0006` and local-rebuild criteria are not met and are not
claimed.

### 8.4 Skipped tests are not passes

The PostgreSQL parity module is opt-in through a `skipif` guard. The guard was
satisfied explicitly, the three tests executed, and the runner reported
`3 passed`. No run reported `skipped` in place of a pass. The unavailable
application suite was not run at all and is marked **BLOCKED** above.

---

## 9. Safety evidence, remaining blockers, and handoff

### 9.1 No remote or production access

- Every database URL used in an executed command pointed to
  `127.0.0.1:55432`.
- The guard rejects non-loopback targets unless both production guard
  variables are present; no such variables were set for any executed
  migration.
- No Neon, Render, Cloudflare, staging, or production endpoint was contacted.
- The `db.example.com` URL in the guard unit tests is a non-routable
  negative-control literal and was never connected.
- No production inventory, backup, migration, or deployment command was run.
- No `alembic stamp` command was run.
- No application server was started against a migrated database.

### 9.2 Local database safety

- The pre-existing local PostgreSQL service on port 5432 was not contacted or
  modified.
- The disposable cluster on port 55432 was created solely for Batch 25 tests.
- Its test database was dropped and recreated empty at the end of the run.
- The cluster was stopped; port 55432 has no listener.
- No local development database was rebuilt, stamped, upgraded, or deleted.
- The local database disposition and any L1/L2 rebuild remain deferred to an
  authorized later batch with owner attestation.

### 9.3 Secrets and environment

- No `.env` file was edited.
- No secret, credential, or production URL was added to the repository.
- `alembic.ini` contains no URL.
- Process-scoped test variables were removed after the runs.
- The test role used `trust` authentication only inside the disposable
  loopback cluster.

### 9.4 Remaining blockers

| Blocker | Consequence | Required owner / batch |
| --- | --- | --- |
| `0005_verification_templates` not implemented | No template table, no template lifecycle schema, Batch 24 criteria open | Batch 26 or later authorized migration batch |
| `0006_discrepancy_review_decisions` not implemented | No review-decision table, no `RESTRICT` FKs, no `is_bulk_action`, Batch 24 criteria open | Batch 26 or later authorized migration batch |
| Application/ORM not merged | `test_postgres_migration_application.py` assertions blocked | Batch 26 |
| No production-scale T3 seed | Production-scale preservation unproven | Batch 26/27, explicitly authorized |
| Local database disposition unresolved | No local rebuild at `0006`; owner attestation absent | Data owner + later authorized batch |
| No production authorization | Production migration and deployment remain prohibited | Human two-person production gate |

### 9.5 Batch 26 entry conditions

Batch 26 must not begin from this report alone. Before any application merge or
migration work:

1. The owner must accept the `0005`/`0006` scope and the local database
   disposition.
2. The Batch 26 application file manifest must be frozen.
3. The unmerged ORM must be reconciled with the canonical `0004` schema and
   the future `0005`/`0006` revisions.
4. The application test suite must be run only after the merge, with skipped
   tests reported as skipped or blocked, never as passed.
5. Production access still requires the separate two-person authorization and
   must not reuse the Batch 25 test guard variables as authorization.

### 9.6 Final statement

Batch 25 delivered the authorized offline migration graph, recovered `0004`
baseline, explicit-target tooling, guard tests, canonical parity tests, offline
SQL evidence, and provenance record. All executed checks passed. The batch is
**PARTIAL**, not PASS, because the Batch 24 `0005`/`0006` acceptance criteria
and the local database rebuild were explicitly deferred by the governing
instruction. No production, remote, destructive, stamping, commit, push, or
Batch 26 action was performed.
