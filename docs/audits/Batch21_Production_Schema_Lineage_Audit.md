# VerifyGrid Batch 21 — Production Schema and Lineage Audit

**Date:** 2026-10-29 (PKT, UTC+05:30)  
**Batch type:** Read-only repository, deployment, and schema-lineage audit  
**Branch:** `feature/batch-4-rule-engine-aggregation`  
**HEAD:** `c91e9b37074483eeb7469dc943e1735fd5f5be02`  
**Deployed commit reported by context:** `58a0e5c243978480c4ca817c537c700ed6b20516`  
**Remote database:** Not contacted. No Neon, production, staging, or other database was inspected.  
**Execution status:** Audit only. No migration strategy is selected, authorized, or executed by this report.

## Evidence legend

- **[Confirmed from current repository evidence]** — directly observable in the current working tree or read-only local Git output.
- **[Confirmed from pinned remote source]** — directly observable in the exact GitHub commit or file identified by the pinned SHA.
- **[Reported by the user / earlier batch]** — asserted in the task context or prior audit, but not independently re-established here.
- **[Not independently verified]** — depends on a database, deployment dashboard, backup, or other external state that was not inspected.
- **[Inference requiring further evidence]** — a reasoned consequence of observed facts that depends on an unverified target, runtime behavior, or future decision.

A document containing a claim is evidence that the claim was made. A migration file is an instruction, not proof of execution. The production facts supplied in the task are context to audit, not database-verified findings of this batch.

---

## 1. Executive summary

### 1.1 Principal findings

1. **[Confirmed from pinned remote source]** Remote `main` currently points at `58a0e5c243978480c4ca817c537c700ed6b20516` (committed `2026-10-26T10:49:20Z`), the same commit the task says Render deploys. Its parent is `777a41aeee08c70334da358d2c03534338800185`. The commit message is `chore(migrations): add alembic migration for enterprise governance, materiality, and audit tables`.

2. **[Confirmed from pinned remote source]** At that commit, the only migration files were `0001_initial_tables.py`, `0002_verification_runs.py`, `0003_user_password.py`, and `0004_enterprise_governance_and_materiality.py`. There was no `0004_verification_templates.py` and no `0005_verification_lineage.py`. The deployed migration head was `0004_enterprise_governance`.

3. **[Confirmed from pinned remote source]** The deployed `0004_enterprise_governance` migration itself adds all six lineage columns that are commonly associated with `0005_verification_lineage`:
   - `verification_runs.sources` (line 29);
   - `verification_discrepancies.source_row_indices` (line 62);
   - `verification_discrepancies.source_records` (line 63);
   - `verification_discrepancies.child_records` (line 64);
   - `verification_discrepancies.aggregated_amount` (line 65);
   - `verification_discrepancies.expected_amount` (line 66).

   This is the primary repository explanation for how production could contain those columns while `alembic_version` records `0004_enterprise_governance`. They need not have come from `0005` at all.

4. **[Confirmed from current repository evidence]** The local chain is a different branch:
   `0001_initial_tables` → `0002_verification_runs` → `0003_user_password` → `0004_verification_templates` → `0005_verification_lineage`.
   Its sole head is `0005_verification_lineage`. `0004_verification_templates` and `0005_verification_lineage` are both untracked in Git.

5. **[Confirmed from current repository evidence and pinned remote source]** The two histories share a content-identical `0001`–`0003` ancestry and diverge at two different children of `0003_user_password`:
   - local `0004_verification_templates` → `0005_verification_lineage`;
   - production/deployed `0004_enterprise_governance`.

   Adding the recovered governance file to the current directory unmodified produces **two heads**. A merge revision does not remove duplicate operations: Alembic still traverses both parent branches.

6. **[Confirmed from current repository evidence and pinned remote source]** `0004_enterprise_governance` and `0005_verification_lineage` add the **same six columns** with the same SQLAlchemy types, nullability, absence of defaults, absence of indexes/foreign keys, and matching downgrade drops. Applying both branches to one database would attempt six duplicate `add_column` operations and, on downgrade, six duplicate `drop_column` operations.

7. **[Confirmed from pinned remote source]** The deployed application does **not** run Alembic at startup. Its `backend/app/main.py` only creates the FastAPI app, adds CORS, and includes the API router. Its `backend/app/db/session.py` creates a lazy SQLAlchemy engine and session factory without calling `create_all` or migrations. No deployed application file calls `command.upgrade`, `alembic upgrade`, or a subprocess. The deployed tree contains no `render.yaml`, Dockerfile, Procfile, start script, release script, or backend CI workflow; the only workflow is `.github/workflows/frontend-ci.yml`. The backend README documents a **manual** `alembic upgrade head` step before `uvicorn`.

8. **[Confirmed from current repository evidence]** The current startup files are identical to the deployed startup files:
   - `backend/app/main.py` SHA-256 `8A21322879D8766D9C3BE3C12684162A8857A621C9B2E96813B98AA12C6E68C5` locally and at `58a0e5c`;
   - `backend/app/db/session.py` SHA-256 `99C64CC6D81A371F8AE98B02386BE7A738A38A43FD5FF488145DCBB0F6153A3A` locally and at `58a0e5c`.

   The absence of automatic migration is therefore not a local-only condition; it is present in the deployed commit as well.

9. **[Confirmed from pinned remote source and current repository evidence]** The deployed ORM is governance-era, not the current local ORM. It declares `users.role`, nine run sign-off fields, seventeen discrepancy materiality/clustering/review fields, `audit_events`, and `discrepancy_review_decisions`. The current ORM declares none of those governance objects and instead declares `verification_templates`.

10. **[Confirmed from pinned remote source]** The deployed migration creates `audit_events` but does **not** create `discrepancy_review_decisions`, even though the deployed ORM declares that table and the deployed review service uses it. The deployed commit therefore has an internal schema gap of its own. Production may or may not contain that table; its provenance must be established before any conclusion about production's completeness.

11. **[Confirmed from current repository evidence]** The current ORM's `reason_code` and `confidence_score` are read-only Python properties computed from `field_differences` and `match_status`; they are not mapped columns. The deployed ORM maps physical `reason_code` and `confidence_score` columns through `_reason_code` and `_confidence_score`, with setters. Production, as described, has the physical columns. The current application would ignore them and compute different values in some cases. This is a semantic incompatibility, not just an extra-column difference.

12. **[Confirmed from current repository evidence]** The current ORM expects `verification_templates`, which the governance migration does not create. If production is governance-only and lacks that table, the current application's template endpoints will fail. The task context does not report whether `verification_templates` exists in production.

13. **[Confirmed from current repository evidence]** The current migration-parity test expects exactly one head (`0005_verification_lineage`) and exact table/column/index/foreign-key/unique-constraint sets for the current ORM. Against the governance schema, those assertions would fail on the governance extras, the missing template table, and any missing review table. A passing parity result on a local chain would not prove production compatibility.

### 1.2 What this batch establishes and does not establish

**Establishes:**

- The exact deployed commit, its migration tree, and its startup/deployment-file inventory.
- That no repository file or deployed application startup path automatically runs Alembic.
- That the deployed governance migration itself adds all six lineage columns.
- The exact local, deployed, and combined migration graphs, heads, and duplicate operations.
- The exact current-ORM versus deployed-ORM table/column/index/foreign-key differences.
- The most parsimonious repository-consistent explanation for the reported production state.
- Why `alembic upgrade head` is unsafe against production without a deliberate reconciliation design.
- A safe strategy family, prerequisites, and minimum additional evidence.

**Does not establish:**

- That Neon's `alembic_version` actually contains only `0004_enterprise_governance`.
- That production actually contains `audit_events`, sign-off fields, the six lineage columns, or any other specific object. Those remain user-reported.
- That the governance migration was ever executed against Neon, as opposed to being manually reconstructed or partially applied.
- Whether production contains `verification_templates`, `discrepancy_review_decisions`, or other unrecorded objects.
- That Render's dashboard has no pre-deploy command. Dashboard configuration and deploy logs were not inspected.
- That any migration strategy is safe or selected.

### 1.3 Investigation answers

| Investigation question | Answer | Evidence |
| --- | --- | --- |
| 1. Inspect current migrations, ORM, environment, startup, deployment, and history | Complete for repository-visible files; Render dashboard not inspected. | Sections 2–5 |
| 2. Does any startup/deployment process automatically run Alembic? | No repository/deployed application path does. Render dashboard configuration remains unverified. | Section 5 |
| 3. How could the six lineage columns reach production without `0005`? | The deployed `0004_enterprise_governance` adds exactly those six columns. This is the primary and sufficient repository explanation. | Section 6 |
| 4. Compare current ORM with production schema | Current ORM is a subset on the five shared tables, plus `verification_templates`; it lacks governance/audit/review objects and does not map physical `reason_code`/`confidence_score`. | Section 7 |
| 5. Exact migration graph, duplicate operations, `upgrade head` risk | Two sibling histories, two heads when combined, six duplicate add/drop operations, no safe blind `upgrade head`. | Section 8 |
| 6. Safe reconciliation strategy | Governance-canonical, forward-only superset bridge; do not replay `0005`. No concrete revision selected or authorized. | Section 9 |
| 7. Minimum additional evidence | Render/deploy evidence, full read-only production inventory, application-version decision, backup/rehearsal, ownership authorization. | Section 10 |
| 8. Verdict and safest next action | PASS — audit scope only; freeze and obtain authorized read-only inventory. | Section 12 |

### 1.4 Verdict preview

**PASS — audit scope only.** The required read-only investigation and report are complete. This is not a PASS for migration readiness, production compatibility, Render configuration, or Neon verification. See section 12.

---

## 2. Working-tree baseline and preservation

### 2.1 Repository identity

**[Confirmed from current repository evidence]**

| Item | Value |
| --- | --- |
| Branch | `feature/batch-4-rule-engine-aggregation` |
| HEAD | `c91e9b37074483eeb7469dc943e1735fd5f5be02` |
| HEAD subject | `feat: implement Batch 4 advanced rule engine, aggregation and split-payment reconciliation` |
| Local `main` / `origin/main` | `ccd7e604ac1d262fca9d108e0e62875bec47d1c6` |
| Commits from `origin/main` to HEAD | 3 |
| Commits from HEAD to `origin/main` | 0 |
| Status entries before this report | 66 (`git status --porcelain=v1 --untracked-files=all`) |
| Batch 18 report | Present, untracked |
| Batch 19 report | Present, untracked |
| Batch 20 report | Present, untracked |
| Batch 21 report before writing | Absent |
| Current migration files | `0001`–`0005` in the working tree |
| Tracked migration files at HEAD | `0001`–`0003` only |

The local branch is three commits ahead of the local/remote-tracking `origin/main` (`ccd7e60`), which is **not** the remote GitHub `main` inspected at `58a0e5c`. The local clone has not fetched the remote governance commits. This is a Git-reference observation, not a change to Git state.

### 2.2 Critical pre-report hashes

**[Confirmed from current repository evidence]**

| File | SHA-256 before this report |
| --- | --- |
| `backend/migrations/versions/0001_initial_tables.py` | `F3E045B29E52A132947E6ED156BA57995FD45B75EAA2C7D6289901C5AFD569A0` |
| `backend/migrations/versions/0002_verification_runs.py` | `44A9CD93E9A1260C7C61E3029FD6F884B5B27523FDCE25D966C986748AD78B2E` |
| `backend/migrations/versions/0003_user_password.py` | `6F256919E0E2537468335FF0A6C253E80BC513E3DFB6D414F9564C10083902E6` |
| `backend/migrations/versions/0004_verification_templates.py` | `CBE7E536573D06D49E4EB2F8EFB7BD26A0D3CCA786F01EA80AE7C8E7CA74E227` |
| `backend/migrations/versions/0005_verification_lineage.py` | `645BE701DFF05FDF6D263AF678CB17E77D818CE64C00A8B9F3AF96E46E585713` |
| `backend/migrations/env.py` | `F1A56CC8A201936615DE14F7730E32265C3132AF1372EF382F485207E67F056B` |
| `backend/app/main.py` | `8A21322879D8766D9C3BE3C12684162A8857A621C9B2E96813B98AA12C6E68C5` |
| `backend/app/db/session.py` | `99C64CC6D81A371F8AE98B02386BE7A738A38A43FD5FF488145DCBB0F6153A3A` |
| `backend/app/models/user.py` | `3D34B163C414A375688250D9FA4283FB616EC8DE3E5069611B138B0A8847AED0` |
| `backend/app/models/verification_run.py` | `B59FA3BF64072F81ED51ED8AA8BAE49150818E58890E409A02792A38D16E02BC` |
| `backend/app/models/__init__.py` | `FA8CCA54BC0994B48C9C7AB45AEB7277284DE1D44C96E411C70F5A4DBA76D41C` |
| `docs/audits/Batch18_Migration_History_Divergence_Audit.md` | `1434845A691EB60C9FD34B8C7EACBA5079A7CE667E8DDCB80D4B2578AE037655` |
| `docs/audits/Batch19_Migration_Reconciliation_Preparation.md` | `DDA7AB82B5D799D9BC1EF1A12D23E392F507DCE801275BF4A89B8D637DCE856F` |
| `docs/audits/Batch20_Governance_Migration_Recovery_Audit.md` | `0F4D4E58536CB342D34F4EA2D8C0229F970A2F7844C037F9A7230DF1069F3A3D` |

### 2.3 Preservation statement

**[Confirmed from current repository evidence]**

- No application code, ORM model, migration, configuration, dependency, or existing report was edited.
- No `.env` file was read.
- No database connection was attempted.
- No Alembic command was executed.
- No test suite was executed.
- No schema, data, or migration history was changed.
- No commit, push, merge, rebase, branch switch, fetch, stash, reset, clean, or deploy was performed.
- Remote source files were downloaded only to the approved temporary area outside the repository.
- The only new working-tree file is this report.

Final verification is in section 11.

---

## 3. Current repository migration state

### 3.1 Local chain

**[Confirmed from current repository evidence]**

| Revision | File | Parent | Principal objects |
| --- | --- | --- | --- |
| `0001_initial_tables` | `backend/migrations/versions/0001_initial_tables.py` | None | `users`, `projects`, `source_files` |
| `0002_verification_runs` | `backend/migrations/versions/0002_verification_runs.py` | `0001_initial_tables` | `verification_runs`, `verification_discrepancies` |
| `0003_user_password` | `backend/migrations/versions/0003_user_password.py` | `0002_verification_runs` | `users.hashed_password` |
| `0004_verification_templates` | `backend/migrations/versions/0004_verification_templates.py` | `0003_user_password` | `verification_templates`, owner FK, unique constraint, index |
| `0005_verification_lineage` | `backend/migrations/versions/0005_verification_lineage.py` | `0004_verification_templates` | Six nullable lineage columns |

Sole local head: `0005_verification_lineage`.

### 3.2 The local `0004` docstring is direct repository evidence

**[Confirmed from current repository evidence]**

`backend/migrations/versions/0004_verification_templates.py` lines 6–10 state:

> Application status (Batch 12): APPLIED to the local development database (`verifygrid` @ localhost, revision `0003_user_password` -> head) after a read-only review confirmed the target's history matches this repository's migration graph. The `.env`-configured cloud database has a divergent, unrelated migration history (`0004_enterprise_governance`) and was NOT touched.

This is a repository-recorded claim that:
- the current template migration was applied locally;
- the cloud target was already on a divergent `0004_enterprise_governance` history;
- the current chain was deliberately not applied to that cloud target.

It is evidence of intent and prior operator belief. It is not independent proof of Neon's current schema.

### 3.3 Current migration environment

**[Confirmed from current repository evidence]**

- `backend/migrations/env.py` sets the Alembic URL from `settings.database_url` (lines 13, 25, 68–69).
- Normal CLI use therefore follows the application's configured database URL. There is no CLI-level loopback or production-target guard.
- The uncommitted `env.py` change adds an explicit `config.attributes["connection"]` path (lines 57–66) for tests. The normal CLI path still uses `settings.database_url`.
- `backend/alembic.ini` contains a placeholder loopback URL; `env.py` overrides it in normal use. No credential values are reproduced here.
- `backend/migrations/script.py.mako` is 0 bytes. This does not affect applying existing revisions, but future `alembic revision` use would need a valid template.

### 3.4 Current ORM inventory

**[Confirmed from current repository evidence]**

`backend/app/models/__init__.py` registers:

- `User` (`users`)
- `Project` (`projects`)
- `SourceFile` (`source_files`)
- `VerificationRun` (`verification_runs`)
- `VerificationDiscrepancy` (`verification_discrepancies`)
- `VerificationTemplate` (`verification_templates`)

It does not register `AuditEvent` or `DiscrepancyReviewDecision`. `backend/app/models/audit_log.py` and `backend/app/models/review.py` are 0 bytes. The current `backend/app/api/v1/endpoints/audit.py` and `reviews.py` are also 0 bytes and are not included by `backend/app/api/v1/router.py`. The current app therefore has no active audit or review feature.

---

## 4. Deployed commit and production lineage

### 4.1 Commit identity

**[Confirmed from pinned remote source]**

| Property | Value |
| --- | --- |
| Repository | `ThunderSkull7/verifygrid` |
| Deployed commit | `58a0e5c243978480c4ca817c537c700ed6b20516` |
| Parent | `777a41aeee08c70334da358d2c03534338800185` |
| Commit time | `2026-10-26T10:49:20Z` |
| Message | `chore(migrations): add alembic migration for enterprise governance, materiality, and audit tables` |
| Remote `main` at audit time | `58a0e5c243978480c4ca817c537c700ed6b20516` |
| Migration files at commit | `0001`, `0002`, `0003`, `0004_enterprise_governance_and_materiality.py` |
| Migration head at commit | `0004_enterprise_governance` |

Remote `main` and the reported Render commit currently agree. That establishes repository/deployment reference alignment, not that Render actually built or is running that commit at this moment. Render deployment status and logs were not inspected.

### 4.2 Deployed migration

**[Confirmed from pinned remote source]**

`backend/migrations/versions/0004_enterprise_governance_and_materiality.py` at `58a0e5c`:

- revision: `0004_enterprise_governance`;
- `down_revision`: `0003_user_password`;
- no branch labels, no `depends_on`;
- 156 lines, SHA-256 `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB`;
- 33 `add_column` operations, one `create_table`, five foreign keys, thirteen indexes;
- matching downgrade with 33 `drop_column` operations and one `drop_table`;
- no data backfill, no `UPDATE`/`INSERT`, no conditional DDL.

The six columns shared with `0005_verification_lineage` are added at lines 29 and 62–66, quoted in section 1.1. The governance revision also adds:

- `users.role` (`String(50)`, not null, server default `MAKER`);
- nine `verification_runs.sign_off_*` columns, two user foreign keys, one index;
- seventeen `verification_discrepancies` materiality/clustering/review columns, six indexes;
- `audit_events` with fourteen columns, three inline foreign keys, six indexes.

The migration does **not** create `verification_templates` or `discrepancy_review_decisions`.

### 4.3 Deployed ORM

**[Confirmed from pinned remote source]**

At `58a0e5c`, `backend/app/models` contains:

- `User` with `role` (lines 36–40);
- `VerificationRun` with `sources` and nine sign-off fields (lines 66–142);
- `VerificationDiscrepancy` with the six lineage fields, seventeen governance/materiality fields, and mapped `_reason_code`/`_confidence_score` using database names `reason_code`/`confidence_score` (lines 209–319);
- `AuditEvent` mapped to `audit_events`;
- `DiscrepancyReviewDecision` mapped to `discrepancy_review_decisions` (lines 398–467);
- no `VerificationTemplate`.

The deployed app actively uses these objects:

- `backend/app/api/v1/router.py` includes review, governance, audit, and recipe routers (lines 71–74);
- `backend/app/services/review_service.py` imports `DiscrepancyReviewDecision` and creates rows (lines 15–16, 104, 256);
- `backend/app/services/governance_service.py` uses sign-off fields and audit logging;
- `backend/app/services/audit_service.py` queries and writes `AuditEvent` rows.

The deployed migration creates `audit_events`, so that dependency is covered. It does **not** create `discrepancy_review_decisions`, so the deployed review feature depends on a table that no migration at that commit creates.

---

## 5. Does startup or deployment run Alembic automatically?

### 5.1 Application startup

**[Confirmed from current repository evidence and pinned remote source]**

Both the current and deployed `backend/app/main.py` are byte-identical (SHA-256 `8A21322879D8766D9C3BE3C12684162A8857A621C9B2E96813B98AA12C6E68C5`). The file contains only:

- `FastAPI(...)` construction;
- CORS middleware;
- router inclusion;
- a root endpoint.

There is no `lifespan` handler, `@app.on_event("startup")`, migration call, `create_all`, or subprocess invocation.

Both `backend/app/db/session.py` files are also byte-identical (SHA-256 `99C64CC6D81A371F8AE98B02386BE7A738A38A43FD5FF488145DCBB0F6153A3A`). The engine is created lazily; no schema creation or migration occurs.

A search of current `backend/app` for `create_all`, `metadata.create_all`, `command.upgrade`, `alembic upgrade`, `subprocess`, or `os.system` found no application path. The only `create_all` calls in the repository are in test fixtures:
- `backend/tests/conftest.py:35`;
- `backend/tests/test_postgres_integration.py:133`.

### 5.2 Repository deployment configuration

**[Confirmed from current repository evidence]**

The current repository root contains no `render.yaml`, Dockerfile, Procfile, `start.sh`, `start.ps1`, release script, or deployment script. A recursive search for deployment-like filenames found none. The only GitHub workflow is `.github/workflows/frontend-ci.yml`; there is no backend migration workflow.

**[Confirmed from pinned remote source]**

The deployed tree at `58a0e5c` (189 paths, not truncated) contains the same absence: no `render.yaml`, Dockerfile, Procfile, start/release script, or deployment configuration. The only workflow is `.github/workflows/frontend-ci.yml`. The backend root contains only `.env.example`, `README.md`, `alembic.ini`, `app/`, `migrations/`, `pytest.ini`, `requirements.txt`, `storage/`, and `tests/`.

### 5.3 Documentation says migration is manual

**[Confirmed from current repository evidence and pinned remote source]**

`README.md` lines 43–47 and `backend/README.md` lines 235–245 both say:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The deployed `backend/README.md` at `58a0e5c` has the same instruction at lines 235–239. There is no documented automatic deployment hook.

### 5.4 Conclusion

**No repository-visible or application-startup path runs Alembic automatically.** The application cannot auto-migrate a cloud database on boot.

**Render dashboard behavior remains unverified.** Render can be configured with a start command and a pre-deploy command outside the repository. Such a command could run `alembic upgrade head`, but no repository evidence proves it. Deploy logs and the Render service configuration are required before concluding how the governance migration reached production.

The reported production state—`alembic_version = 0004_enterprise_governance` plus governance schema—is consistent with someone or something having run the deployed commit's migration against Neon. It is not proof of who ran it or when.

---

## 6. How the six lineage columns could reach production without `0005`

### 6.1 Primary explanation: the governance migration adds them

**[Confirmed from pinned remote source]**

The deployed `0004_enterprise_governance` adds exactly the six columns named in the task:

| Column | Governance migration line | Type | Nullable |
| --- | --- | --- | --- |
| `verification_runs.sources` | 29 | `JSON` | Yes |
| `verification_discrepancies.source_row_indices` | 62 | `JSON` | Yes |
| `verification_discrepancies.source_records` | 63 | `JSON` | Yes |
| `verification_discrepancies.child_records` | 64 | `JSON` | Yes |
| `verification_discrepancies.aggregated_amount` | 65 | `Float` | Yes |
| `verification_discrepancies.expected_amount` | 66 | `Float` | Yes |

These definitions match `0005_verification_lineage` in name, type, nullability, absence of defaults, and absence of indexes/foreign keys. If production's `alembic_version` is `0004_enterprise_governance`, and that migration was applied, the six columns are an expected part of that revision. They are not evidence that `0005` ran.

### 6.2 Corroborating evidence

**[Confirmed from pinned remote source]**

The deployed ORM at `58a0e5c` declares the same six fields as required model attributes:
- `VerificationRun.sources` (line 66);
- `VerificationDiscrepancy.source_row_indices`, `source_records`, `child_records`, `aggregated_amount`, `expected_amount` (lines 209–240).

The deployed application could not persist or read multi-source/aggregation lineage without them. The governance migration and deployed ORM therefore describe a single coherent application generation that already includes the lineage feature.

The reported presence of `audit_events`, `users.role`, and sign-off fields is also consistent with the governance migration having been applied. `0005` creates none of those objects.

### 6.3 Alternative explanations evaluated

| Hypothesis | Evidence for | Evidence against | Assessment |
| --- | --- | --- | --- |
| Governance migration `0004` applied | Version matches; governance schema reported; migration adds all six columns; deployed ORM requires them | No database connection, migration log, or execution record inspected | **Most parsimonious repository-consistent explanation.** Not independently proven. |
| `0005_verification_lineage` applied | Six columns exist | Production version is governance, not `0005`; `0005` has no ancestry path from governance; applying it would require history manipulation or a merge; it creates no governance objects | Unsupported by repository evidence. Could only occur after an unrecorded reparent/merge/stamp. |
| Manual `ALTER TABLE` / ad hoc DDL | Possible in any environment | No SQL script, startup hook, or documentation of manual column creation; governance migration already supplies the columns | Possible but unnecessary. Would be an unrecorded manual change. |
| `Base.metadata.create_all` against production | Would create model columns | No application path calls `create_all`; only test fixtures do; tests target isolated databases | No repository evidence. Would not explain governance-only objects cleanly. |
| Partial/failed migration followed by manual repair | Could explain mixed state | No logs or repair artifacts; version is a valid governance head; reported schema is coherent with full governance revision | Speculative. Needs migration logs. |
| Version table stamped to governance after other changes | Could explain columns without recorded revision | No evidence; stamping is explicitly prohibited and would hide history | Speculative and unsafe to assume. |

### 6.4 Conclusion

The six columns are **not a lineage mystery** once the deployed migration is read: `0004_enterprise_governance` owns the same six columns as `0005_verification_lineage`. The reported production state is exactly what a successful application of the deployed governance revision would produce, plus the governance objects. This is the primary explanation.

It remains a **repository-consistent inference**, not a database-verified fact. The missing evidence is execution provenance: migration logs, Render pre-deploy configuration, or an operator record showing that `alembic upgrade head` was run against Neon at `58a0e5c`.

---

## 7. Current ORM versus the reported production schema

### 7.1 Table inventory

**[Confirmed from current repository evidence and pinned remote source]**

A metadata-only comparison (no database connection) of the current ORM and the deployed governance-era ORM found:

| Table | Current ORM | Deployed ORM | Production status |
| --- | --- | --- | --- |
| `users` | 6 columns | 7 columns (`role` extra) | Reported governance schema present; `role` likely exists |
| `projects` | 6 columns | 6 columns | Shared base table; assumed compatible |
| `source_files` | 8 columns | 8 columns | Shared base table; assumed compatible |
| `verification_runs` | 15 columns | 24 columns (9 sign-off extra) | Reported sign-off fields present |
| `verification_discrepancies` | 19 columns | 36 columns (17 governance extra) | Reported governance schema present |
| `verification_templates` | 10 columns | absent | **Not reported.** May be missing in production |
| `audit_events` | absent | 14 columns | Reported present |
| `discrepancy_review_decisions` | absent | 12 columns | **Not reported.** No migration creates it |

The five shared tables have no current-only columns, indexes, foreign keys, or unique constraints relative to the deployed ORM at the metadata-name level. The deployed ORM is a superset on those tables. This means current code that only touches shared columns can often read and write without SQL errors, relying on governance server defaults for non-null extras.

### 7.2 Exact governance objects absent from the current ORM

**[Confirmed from current repository evidence and pinned remote source]**

| Area | Objects present in deployed ORM / migration | Current ORM | Compatibility consequence |
| --- | --- | --- | --- |
| `users.role` | `String(50)`, not null, server default `MAKER` | Not mapped | Current inserts rely on DB default; current code ignores roles and cannot enforce maker-checker permissions. |
| Run sign-off | `sign_off_status` (not null, default `DRAFT`, indexed), `sign_off_proposed_by`/`sign_off_approved_by` FKs to `users.id` (`SET NULL`), seven additional name/note/time fields | Not mapped | Current inserts get `DRAFT`; current code cannot propose, approve, reject, or display sign-off state. |
| Discrepancy materiality | `source_amount`, `target_amount`, `variance_amount`, `exposure_amount` (indexed), `currency` (default `USD`), `severity` (default `medium`, indexed), `resolution_status` (default `unresolved`, indexed), `resolution_note`, `resolved_by`, `resolved_at` | Not mapped | Current inserts rely on DB defaults for non-null fields; current code does not populate or expose materiality/resolution workflow. |
| Clustering/review | `cluster_id` (indexed), `cluster_name`, `assigned_to` (indexed), `assigned_at`, `side_by_side` | Not mapped | Current code cannot use clustering or assignment features. |
| Physical reason/confidence | `reason_code` `String(100)` indexed; `confidence_score` `Float` | Current **properties**, not mapped columns | Current code ignores stored values and computes from `field_differences`/`match_status`; writes leave physical columns NULL. Semantic drift. |
| `audit_events` | 14 columns, 3 FKs, 6 indexes | Not mapped; no model | Current code cannot append or verify audit events. Governance hash chain is not maintained by current code. |
| `discrepancy_review_decisions` | 12 columns, FKs to runs/discrepancies, indexes | Not mapped; no model | Deployed review service expects it, but no migration creates it. Production presence/provenance unknown. |

### 7.3 Exact current-only object

**[Confirmed from current repository evidence]**

`verification_templates` is declared by `backend/app/models/verification_template.py` and created by current `0004_verification_templates.py`. It is not created by `0004_enterprise_governance`.

The current API actively uses it:
- `backend/app/api/v1/router.py:68` includes the templates router;
- `backend/app/api/v1/endpoints/templates.py` defines list/create/get/update/delete operations;
- `backend/app/services/template_service.py` queries `VerificationTemplate` for all operations.

If production is governance-only and lacks `verification_templates`, those endpoints will fail with a missing-relation error. If production contains the table, its creation is not explained by the recorded governance revision and must be documented. The task context does not resolve this.

### 7.4 Six lineage columns

**[Confirmed from current repository evidence and pinned remote source]**

The six columns are compatible in name, SQLAlchemy type, nullability, and absence of defaults/indexes/FKs between:
- deployed `0004_enterprise_governance`;
- current `0005_verification_lineage`;
- current ORM.

PostgreSQL type expectations are `json` for the four JSON fields on discrepancies plus `verification_runs.sources`, and `double precision` for the two amount fields. Production must be checked for exact types; a `jsonb` column or a default would be a conflict, not a match.

### 7.5 Current application behavior against a governance schema

**[Inference requiring further evidence, based on static metadata]**

If the current application were pointed at a governance-only production schema:

- **Likely to work:** authentication, projects, source files, uploads, verification runs, discrepancy reads/writes, and exports, because all current shared-table columns exist and governance non-null defaults cover omitted fields.
- **Likely to fail:** template list/create/update/delete, because `verification_templates` may not exist.
- **Silently degraded:** role-based governance, sign-off workflow, materiality/clustering views, and audit trail, because current code does not map or use those objects.
- **Semantically different:** `reason_code` and `confidence_score` are computed properties in current code, not physical columns. Stored governance values may be ignored or overwritten by computed behavior.
- **No audit trail:** current run creation/update does not append `audit_events`, so the deployed tamper-evident chain would not reflect current application activity.
- **Deployed review endpoints:** the deployed app itself expects `discrepancy_review_decisions`, which no migration creates. If production lacks it, review actions fail; if it exists, its provenance is unexplained by the migration history.

These are static compatibility conclusions. No current code was executed against production.

### 7.6 Parity-test consequences

**[Confirmed from current repository evidence]**

`backend/tests/test_alembic_migration_parity.py`:

- expects `EXPECTED_HEAD = "0005_verification_lineage"` (line 67);
- expects `PREVIOUS_HEAD = "0004_verification_templates"` (line 66);
- asserts the actual table set equals `Base.metadata.tables | {"alembic_version"}` (lines 223–227);
- asserts exact column sets, nullability, primary keys, foreign keys, unique constraints, and indexes (lines 229–297);
- uses `compare_metadata` for additional drift (lines 299–312).

Against a governance schema, these assertions would fail because of:
- extra `audit_events` table;
- extra governance columns and indexes;
- possibly missing `verification_templates`;
- possibly missing `discrepancy_review_decisions` if the deployed ORM contract were used;
- different head revision.

A passing local parity test therefore cannot establish production compatibility. New tests and a new canonical graph are required before a dual-support schema can be claimed.

---

## 8. Exact migration graph and `upgrade head` risk

### 8.1 Graph

**[Confirmed from current repository evidence and pinned remote source]**

```text
CURRENT LOCAL
0001_initial_tables
  -> 0002_verification_runs
    -> 0003_user_password
      -> 0004_verification_templates
        -> 0005_verification_lineage        (sole local head)

DEPLOYED / PRODUCTION-REPORTED
0001_initial_tables
  -> 0002_verification_runs
    -> 0003_user_password
      -> 0004_enterprise_governance         (sole deployed head)

COMBINED WITHOUT EDITS
0003_user_password
  -> 0004_verification_templates -> 0005_verification_lineage   (head)
  -> 0004_enterprise_governance                                  (head)
```

The shared `0001`–`0003` files are content-identical between local and deployed histories (confirmed in Batch 20 by blob SHA). The divergence starts at the two distinct `0004` revisions. The numeric prefix is a filename convention, not Alembic ordering; the revision identifiers are distinct.

### 8.2 Duplicate operations

**[Confirmed from current repository evidence and pinned remote source]**

| Column | Governance operation | `0005` operation | Duplicate? |
| --- | --- | --- | --- |
| `verification_runs.sources` | `add_column` line 29; `drop_column` line 155 | `add_column` lines 43–46; `drop_column` line 83 | Exact |
| `verification_discrepancies.source_row_indices` | line 62; drop line 145 | lines 50–53; drop line 82 | Exact |
| `verification_discrepancies.source_records` | line 63; drop line 144 | lines 54–57; drop line 81 | Exact |
| `verification_discrepancies.child_records` | line 64; drop line 143 | lines 61–64; drop line 80 | Exact |
| `verification_discrepancies.aggregated_amount` | line 65; drop line 142 | lines 65–68; drop line 79 | Exact |
| `verification_discrepancies.expected_amount` | line 66; drop line 141 | lines 69–72; drop line 78 | Exact |

No other column, index, foreign key, unique constraint, or table name is duplicated between the two revisions. The six-column duplication alone is sufficient to make unmodified co-application fail.

### 8.3 `upgrade head` risk by scenario

| Scenario | What happens | Risk |
| --- | --- | --- |
| **A. Current tree as-is against production at governance** | Alembic cannot locate revision `0004_enterprise_governance` in the current script directory (it is absent). `upgrade head` fails before DDL. | Safe failure, but no reconciliation. The current graph cannot represent production. |
| **B. Deployed commit against production at governance** | Production is already at the sole head; `upgrade head` is a no-op. | Does not add templates or repair the missing review table. It also does not prove the schema matches the revision. |
| **C. Add recovered governance file unmodified to current tree** | Two heads (`0005_verification_lineage`, `0004_enterprise_governance`). `upgrade head` is ambiguous and fails before DDL. | No migration progress; current tests expecting one head fail. |
| **D. Create a merge revision with both parents** | Alembic traverses both branches. If production already has the six governance columns, `0005` tries to add them again. | Duplicate-column failure. PostgreSQL transactional DDL may roll back the attempt, but this was not executed and cannot be relied on. |
| **E. Reparent `0005` to governance** | `0005` still adds the six columns that governance already created. | First duplicate `add_column` fails. |
| **F. Reparent current `0004_verification_templates` to governance and keep `0005`** | Both `0004` branches are applied; `0005` then duplicates the six governance columns. | Failure unless `0005` is removed or rewritten. |
| **G. Edit/conditionalize duplicate operations** | A deliberate new migration design avoids duplicate DDL. | This is no longer the unmodified chain; downgrade ownership, version history, and ORM contract must be redesigned and reviewed. |
| **H. Stamp production to `0005`** | No DDL runs; version table claims a history and schema that may not exist, including templates. | Prohibited. Hides missing objects and destroys reproducibility. |
| **I. Apply `0005` directly to production** | No ancestry path from governance; duplicate six columns even if forced. | Unsafe and prohibited. |

### 8.4 Additional operational risk

**[Confirmed from current repository evidence; target not verified]**

`backend/migrations/env.py` uses `settings.database_url` for normal CLI use and has no local/production guard. An operator running `alembic upgrade head` from a shell whose environment points at production can target production. This audit did not read `.env`, did not resolve the configured URL, and has no evidence that this occurred. It is a governance risk, not a finding of past behavior.

### 8.5 Conclusion

There is **no safe blind `alembic upgrade head`** against production:

- with the current tree, production's revision is unknown to the script directory;
- with the governance file added unmodified, the graph has two heads;
- with a merge/reparent, duplicate column DDL is still traversed;
- with stamping, the version table lies.

Any viable path must explicitly resolve the sibling history and the six-column ownership before DDL is authored.

---

## 9. Recommended reconciliation strategy

**No concrete production migration is selected, authorized, or executed by this report.** The following is a strategy family and its gates. It preserves production data and supports both the governance schema and the lineage features.

### 9.1 Recommended family: governance-canonical, forward-only superset

The safest family is:

1. **Treat `0004_enterprise_governance` as the canonical production revision.**
2. **Treat the six lineage columns as governance-owned.** Do not apply `0005_verification_lineage` to production; it is a duplicate ownership claim for the same columns.
3. **Add only genuinely missing objects with a new forward-only revision on the governance lineage.** The likely candidates are:
   - `verification_templates`, because the current app requires it and governance does not create it;
   - `discrepancy_review_decisions`, only if production lacks it and the deployed review feature is required. No existing migration creates it, so its definition must come from the deployed ORM and be reviewed.
4. **Do not drop, rename, or rewrite any governance object or data.** Do not re-add the six columns. Do not replay `0005`.
5. **Use existence checks / conditional DDL** in the bridge revision so it is safe only after the inventory proves which objects are absent. A blind `create_table` would fail if production already has the object.
6. **Rehearse on a Neon branch or isolated restore**, never on the live production branch. Verify schema, data, application behavior, and rollback before any production approval.

This produces a superset schema: governance objects plus the current template table (and review table if needed), with one owner for the six lineage columns.

### 9.2 Repository graph cleanup

The current `0004_verification_templates` and `0005_verification_lineage` are untracked. Before committing a reconciliation, choose one of these designs:

- **Preferred: one linear canonical graph.**
  `0001 → 0002 → 0003 → 0004_enterprise_governance → new_templates_bridge`.
  Retire or rewrite `0005_verification_lineage`; its six columns are already in governance. Rebuild local development databases from the canonical graph. Production is untouched.
- **Alternative: explicit branch coexistence.**
  Keep the current local chain and the governance chain as separate labeled branches, with explicit revision targets. This avoids duplicate DDL but leaves two heads and requires disciplined deployment scripts. It is more error-prone than a single canonical graph.

A merge revision alone is **not** a solution: it preserves both parents and therefore both duplicate column operations unless one branch is rewritten or made conditional.

### 9.3 Application-version decision

Before schema work, decide which application production must run:

- **Governance-era `58a0e5c`:** no schema migration is required for the six lineage columns or governance objects; they are already part of that revision. The missing `discrepancy_review_decisions` table must still be explained or repaired if review features are used.
- **Current local application:** the schema needs `verification_templates` and the application needs a decision about governance features. Current code ignores role, sign-off, materiality, audit, and physical reason/confidence columns. A schema bridge alone will not make those features work.
- **A new combined application:** design the ORM/API contract first, then author one schema bridge that supports it. Do not infer the application contract from migration names.

### 9.4 Rejected approaches

| Approach | Why rejected |
| --- | --- |
| Run `alembic upgrade head` against production as-is | Current graph cannot resolve production's revision; adding governance creates two heads; merge/reparent duplicates six columns. |
| Apply `0005_verification_lineage` to production | No ancestry path; duplicate six columns; does not create governance objects and may not create templates. |
| Stamp production to `0005_verification_lineage` | Asserts a schema state that is not proven; hides missing template/review objects; prohibited. |
| Delete or edit `alembic_version` rows | History manipulation; hides the actual lineage; prohibited. |
| Downgrade governance to `0003` and rebuild | Destroys audit/governance data and risks production; not acceptable without a verified restore and explicit owner authorization. |
| Blind `create_all` against production | No application path supports it; would create model tables without migration history and could conflict with governance objects. |
| Add the recovered file unmodified to the current tree and deploy | Two heads; ambiguous `upgrade head`; duplicate DDL; current ORM still lacks governance mapping. |

### 9.5 What this recommendation is not

- It is not a selected revision ID.
- It is not an authorization to edit migrations, add the recovered file, or run DDL.
- It is not a claim that `verification_templates` or `discrepancy_review_decisions` is absent from production.
- It is not a claim that the current application should replace the governance application.

Those decisions require the evidence in section 10.

---

## 10. Minimum additional evidence before any migration strategy is approved

### 10.1 Deployment and execution provenance

- [ ] Render service configuration: build command, start command, pre-deploy command, auto-deploy setting, and environment-variable **names** (not values).
- [ ] Render deploy logs for the deployment of `58a0e5c`, including whether any migration command ran and its output.
- [ ] Confirmation that the live service still runs `58a0e5c`, or the exact commit it runs now.
- [ ] Any manual migration record: operator, timestamp, command, target, and output.
- [ ] Whether the governance migration was applied through Render, a shell, CI, or a developer machine.

### 10.2 Full read-only production inventory

Perform on an approved read-only role or isolated Neon branch/restore, never by pointing the application or Alembic at production:

- [ ] Every `alembic_version` table and every row, including duplicates, unknown revisions, and row count.
- [ ] All application tables, columns, types, nullability, defaults, identities, and comments.
- [ ] All primary keys, foreign keys (with delete/update actions), unique constraints, check constraints, indexes, triggers, and row-level security policies.
- [ ] Specifically:
  - [ ] `verification_templates` exists? If yes, exact definition and creation provenance.
  - [ ] `discrepancy_review_decisions` exists? If yes, exact definition and creation provenance; if no, deployed review endpoints are broken.
  - [ ] `audit_events` exact shape, row count, and hash-chain integrity.
  - [ ] `users.role` and all nine sign-off columns.
  - [ ] All seventeen materiality/clustering/review columns and six indexes.
  - [ ] Physical `reason_code` and `confidence_score` columns and non-null counts.
  - [ ] Six lineage columns: exact PostgreSQL types (`json` vs `jsonb`), nullability, defaults, indexes/FKs, and non-null data counts.
- [ ] Any object not represented by either migration graph, including manual tables, views, triggers, and extensions.

### 10.3 Data safety and recovery

- [ ] Row-count estimates and non-null counts for lineage, governance, audit, template, and review data. Do not export row contents without a separate privacy review.
- [ ] Whether audit hash-chain verification currently passes.
- [ ] Verified backup/point-in-time recovery point and a successful restore test to a separate branch or isolated environment.
- [ ] A disposable rehearsal target whose inventory matches production.
- [ ] Confirmation that rehearsal and inventory cannot modify the live branch.
- [ ] Retention/legal requirements for audit and sign-off data.

### 10.4 Application and ownership decisions

- [ ] Written decision: production runs the governance-era app, the current app, or a new combined build.
- [ ] Whether maker-checker roles, sign-off, materiality, clustering, and audit trail are required in production.
- [ ] Whether current template CRUD is required in production.
- [ ] Whether the deployed review feature is used; if so, how `discrepancy_review_decisions` is supposed to exist.
- [ ] Owner for the canonical migration lineage, schema, application version, and production change.
- [ ] Written authorization and change freeze for any future migration.

### 10.5 Repository and test prerequisites

- [ ] Preserve the recovered governance migration with provenance; decide whether it is committed as a historical revision or represented by a reviewed equivalent.
- [ ] Decide the canonical graph and retire/relabel the duplicate `0005` ownership.
- [ ] Add a parity test for the chosen canonical graph and a production-schema compatibility test that tolerates/validates governance supersets.
- [ ] Run the full test suite on an isolated PostgreSQL target, not production.
- [ ] Review the empty `script.py.mako` before generating any new revision.

**No strategy should be approved until sections 10.1–10.4 are complete and reviewed.**

---

## 11. Safety, preservation, and final verification

### 11.1 Actions not taken

**[Confirmed from current repository evidence]**

- No application code, ORM model, migration, configuration, dependency, or existing report was edited.
- No `.env` file was read.
- No database connection was attempted.
- No Alembic upgrade, downgrade, stamp, revision, history, or other migration command was executed.
- No test suite was run.
- No schema, data, or migration history was changed.
- No commit, push, merge, rebase, branch switch, fetch, stash, reset, clean, or deploy was performed.
- Remote source and deployed-tree files were written only to the approved temporary directory outside the repository.

### 11.2 Final working-tree verification

**[Confirmed from current repository evidence]**

- Baseline before this report: 66 status entries.
- Final status after adding this report: 67 entries.
- The only new path is `docs/audits/Batch21_Production_Schema_Lineage_Audit.md`.
- No pre-existing file was modified, deleted, renamed, staged, or committed.
- The untracked `0004_verification_templates.py`, `0005_verification_lineage.py`, and Batches 18–20 reports remain present.
- The modified `backend/migrations/env.py` remains modified.
- All critical-file hashes in section 2.2 remain unchanged.

### 11.3 Tests, migrations, and secrets

- Tests executed: **none**.
- Alembic commands executed: **none**.
- Database connections attempted: **none**.
- `.env` files read: **none**.
- Database URLs, credentials, tokens, or private keys recorded: **none**.
- Application, ORM, migration, configuration, dependency, or existing-documentation edits: **none** except this report.

No test was run because the PostgreSQL suites require an explicitly supplied isolated target and this batch does not authorize one. No Alembic command was run because the batch explicitly prohibits migration commands and no database target was authorized.

---

## 12. Final verdict

### 12.1 Verdict

**PASS — audit scope only.**

The Batch 21 investigation is complete:

- The current migration files, ORM models, migration environment, application startup, deployment-relevant repository files, and relevant Git/remote history were inspected.
- No repository-visible or application-startup path automatically runs Alembic. Render dashboard behavior remains unverified.
- The deployed `0004_enterprise_governance` was shown to add all six lineage columns, explaining the reported production state without `0005`.
- The exact local, deployed, and combined migration graphs, divergent heads, and six duplicate add/drop operations were documented.
- The current ORM was compared with the deployed governance-era ORM: current is a subset on shared tables, lacks governance/audit/review objects, maps `reason_code`/`confidence_score` differently, and alone declares `verification_templates`.
- The deployed app's unmigrated `discrepancy_review_decisions` dependency was identified.
- A governance-canonical, forward-only superset strategy was recommended without selecting or executing a migration.
- Minimum additional evidence and safety gates were documented.
- No database, migration, test, environment, or Git state was changed.
- This report is the only new working-tree change.

### 12.2 Verdict qualifications

- **Not a PASS for reconciliation.** Production remains on a divergent lineage; no migration was designed or approved.
- **Not a PASS for migration readiness.** No production inventory, backup verification, rehearsal, or authorization exists.
- **Not a PASS for Neon.** Neon was not inspected.
- **Not a PASS for Render configuration.** Dashboard settings and deploy logs were not inspected.
- **Not a PASS for ORM compatibility.** The current ORM is not a complete contract for the governance schema.
- **Not a PASS for historical completeness.** The deployed migration omits `discrepancy_review_decisions`.
- **Not a PASS for revalidation.** No test was run.

### 12.3 Single safest next action

**Freeze production schema changes and obtain an owner-authorized, read-only inventory of the production database—full `alembic_version`, `verification_templates`, `discrepancy_review_decisions`, the six lineage columns, governance/audit objects, and data counts—together with Render's pre-deploy configuration and deploy logs. Do not run `alembic upgrade head`, do not apply `0005`, do not stamp, and do not edit migration history until that evidence is reviewed and a concrete strategy is explicitly authorized.**
