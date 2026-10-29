# Isolated PostgreSQL Integration Testing

**Batch:** 15, extended in Batch 16
**Purpose:** Run backend integration, Alembic migration-parity, and
migration-built application tests against a real PostgreSQL server without
touching the application development database or any remote database.

## Safety model

The suite is opt-in and fails closed:

- Importing the test module never opens a connection.
- A normal `pytest tests` run skips the PostgreSQL tests. Skips are not
  PostgreSQL verification.
- Opt-in requires both:
  - `VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS=1`
  - `VERIFYGRID_TEST_DATABASE_URL` set to an explicitly isolated test database
- There is **no fallback** to `settings.database_url`. The application
  `DATABASE_URL` is never used as a test target.
- `backend/tests/pg_test_target.py` rejects:
  - missing or malformed URLs;
  - drivers other than `postgresql+psycopg`;
  - non-loopback hosts, including hosts that resolve to any non-loopback
    address;
  - database or role names that do not clearly identify a test target;
  - the application database name;
  - an endpoint identical to the application endpoint;
  - query parameters that could redirect the connection (`host`, `port`,
    `dbname`, `user`, `service`, and similar).
- The actual connected server is checked with `current_database()`,
  `current_user`, and `inet_server_addr()` before any schema change.
- The sessions use unique schemas and drop them at the end:
  `verifygrid_it_<random>` for the model-created suite,
  `verifygrid_mig_<random>` for migration parity, and
  `verifygrid_migapp_<random>` for migration-built application tests. Table data
  is truncated between tests. The `public` schema is never used for test tables.
- Error messages and the `TargetCheck` representation never include the URL,
  password, or query string.

## Temporary cluster used in Batches 15–16

The tests used a **separate** PostgreSQL 18 cluster on loopback port `55432`.
The ordinary PostgreSQL service on port `5432` and its `verifygrid` development
database were not used.

- Data directory:
  `C:\Users\shaha\AppData\Local\Temp\opencode\verifygrid-pgtest`
- Log:
  `C:\Users\shaha\AppData\Local\Temp\opencode\verifygrid-pgtest.log`
- Host/port: `127.0.0.1:55432`
- Test database: `verifygrid_test`
- Least-privilege login role: `verifygrid_test_app`
  (non-superuser, no `CREATEDB`, no `CREATEROLE`)
- Cluster admin role: `verifygrid_test`

`--auth=trust` was used only because this cluster listens exclusively on
loopback and exists only for disposable tests. Do not use trust authentication
for a shared, networked, or persistent database.

### Setup outline

PostgreSQL 18 binaries were used from:

```text
C:\Program Files\PostgreSQL\18\bin
```

The cluster was initialized with a dedicated data directory and admin role:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\initdb.exe" `
  -D "C:\Users\shaha\AppData\Local\Temp\opencode\verifygrid-pgtest" `
  -U verifygrid_test --auth=trust --encoding=UTF8 --locale=C
```

It was started on loopback only:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" `
  -D "C:\Users\shaha\AppData\Local\Temp\opencode\verifygrid-pgtest" `
  -l "C:\Users\shaha\AppData\Local\Temp\opencode\verifygrid-pgtest.log" `
  -o '"-p 55432 -h 127.0.0.1"' -w start
```

The least-privilege role and test database were created with:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\createuser.exe" `
  -h 127.0.0.1 -p 55432 -U verifygrid_test verifygrid_test_app

& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" `
  -h 127.0.0.1 -p 55432 -U verifygrid_test `
  -O verifygrid_test_app verifygrid_test
```

No password is needed on this loopback-only throwaway cluster. For any other
environment, use a secret manager and never commit or print the URL.

## Running the suite

Construct the URL in the shell without echoing it. The command shape is:

```powershell
$env:VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS = "1"
$testRole = "verifygrid_test_app"
$testPort = "55432"
$testDb = "verifygrid_test"
$env:VERIFYGRID_TEST_DATABASE_URL = (
  "postgresql+psycopg://${testRole}@127.0.0.1:${testPort}/${testDb}"
)
& ".\.venv\Scripts\python.exe" -m pytest tests/test_postgres_integration.py -q -rs
Remove-Item Env:\VERIFYGRID_TEST_DATABASE_URL
Remove-Item Env:\VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS
```

Expected result for the model-created suite:

```text
12 passed
```

The target guard has its own connection-free test module:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest tests/test_postgres_target_guard.py -q
```

Expected result:

```text
11 passed
```

## Running the Alembic-built suites (Batch 16)

Both migration suites use the same opt-in variables and the same fail-closed
target guard. They must be run only against the dedicated loopback test
database:

```powershell
$env:VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS = "1"
$testRole = "verifygrid_test_app"
$testPort = "55432"
$testDb = "verifygrid_test"
$env:VERIFYGRID_TEST_DATABASE_URL = (
  "postgresql+psycopg://${testRole}@127.0.0.1:${testPort}/${testDb}"
)

# Migration parity: schema built only by Alembic, compared with ORM metadata.
& ".\.venv\Scripts\python.exe" -m pytest tests/test_alembic_migration_parity.py -q -rs

# Application operations on the Alembic-built schema.
& ".\.venv\Scripts\python.exe" -m pytest tests/test_postgres_migration_application.py -q -rs

Remove-Item Env:\VERIFYGRID_TEST_DATABASE_URL
Remove-Item Env:\VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS
```

Batch 16 results:

```text
tests/test_alembic_migration_parity.py          2 passed
tests/test_postgres_migration_application.py    4 passed
```

Alembic receives an already-validated connection through
`config.attributes["connection"]`; `migrations/env.py` never opens a connection
to `settings.database_url` on that path. The test fails if the connected
database, role, or server address differs from the validated target.

## Schema initialization and verification levels

There are now three verification levels:

| Evidence level | Schema source | Batch 16 result |
| --- | --- | --- |
| Application tests | `Base.metadata.create_all()` | 12 passed (Batch 15) |
| Migration parity | Alembic upgrade to `head` | 2 passed |
| Migration-built application tests | Alembic upgrade to `head` | 4 passed |

The model-created suite still verifies application behavior quickly. It is not
evidence that the committed migrations build a working schema.

The migration-parity suite upgrades the full graph
`0001_initial_tables → 0002_verification_runs → 0003_user_password →
0004_verification_templates → 0005_verification_lineage`, then checks:

- the final `alembic_version` is `0005_verification_lineage`;
- every application table exists;
- the six lineage columns exist with the expected PostgreSQL types and
  nullability, and with no defaults;
- primary keys, foreign keys, indexes, and unique constraints match the ORM;
- `alembic.autogenerate.compare_metadata` reports no remaining drift;
- representative pre-existing rows survive the upgrade;
- the downgrade drops only the six new columns, preserves base rows, and a
  re-upgrade works.

The migration-built application suite uses the same Alembic schema (never
`create_all`) and exercises real API paths:

1. Three-source run creation, persisted `sources`, and discrepancy lineage
   retrieval.
2. Partial split-payment aggregation with persisted `child_records`,
   `aggregated_amount`, and `expected_amount`.
3. Template create/read/list/delete and duplicate-name uniqueness.
4. Transaction rollback and database-level uniqueness enforcement.

Do not report a green model-created run as proof that Alembic can build a
working schema, or a green local migration run as proof that Neon is compatible.

## Coverage

The 12 PostgreSQL cases cover:

1. Template creation, retrieval, and listing.
2. Nested configuration JSON round-trip and replacement.
3. Template ownership and authorization.
4. Template apply validation without executing verification.
5. Multi-source preview and persisted-run consistency.
6. Blank and null identity keys.
7. Duplicate-key handling.
8. Worksheet-specific quarantine resolution.
9. Independent resolutions across multiple worksheets.
10. Persisted reason codes.
11. Summary counters versus persisted results.
12. Transaction rollback, uniqueness constraints, and per-test cleanup.

The suite asserts real PostgreSQL behavior. SQLite results are not substituted
for these cases. The two Batch 16 migration suites add the six-case evidence
described above; they run separately and are never counted as SQLite or
model-created results.

## Cleanup

Stop the temporary cluster when finished:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" `
  -D "C:\Users\shaha\AppData\Local\Temp\opencode\verifygrid-pgtest" -w stop
```

The data directory can then be removed if it is no longer needed. Never point
these commands at the production PostgreSQL data directory.

## What remains unverified

- Neon connectivity and schema.
- Alembic upgrade from the committed graph on Neon.
- Neon's actual migration history and any cloud-only revisions.
- Real-browser end-to-end behavior; the component tests use jsdom.
- Production load, concurrency, backup/restore, and monitoring.
