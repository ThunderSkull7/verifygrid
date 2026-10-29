# Batch 24 - Migration Reconciliation and Application Architecture Decision Memo

**Date:** 2026-10-29  
**Repository:** `C:\Users\shaha\verifygrid`  
**Branch:** `feature/batch-4-rule-engine-aggregation`  
**HEAD:** `c91e9b37074483eeb7469dc943e1735fd5f5be02`  
**Status:** PASS - decision-documentation scope only. Batch 25 (offline migration/tooling implementation) is conditionally GO **after this memo is approved and owners are named**. Batch 26 (application merge and P0 remediation) is NO-GO until Batch 25 exits. All production migration and deployment remain NO-GO.  
**Supersedes:** None of the Batch 18-23 reports wholesale. It resolves the application-version, P0-security, migration-ownership, tooling, test-isolation, local-database, retention, and gate decisions those reports left open. Where this memo conflicts with a proposal in Batch 22 or Batch 23, this memo controls for future work, and the conflict is stated explicitly.

---

## Evidence legend

| Label | Meaning |
| --- | --- |
| **[Repository]** | Confirmed by direct read-only inspection of the current working tree in Batch 24. |
| **[Preserved deployed source]** | Confirmed by read-only inspection of the preserved tree for commit `58a0e5c243978480c4ca817c537c700ed6b20516` at `C:\Users\shaha\AppData\Local\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516`. |
| **[Prior audit]** | Established by Batch 18, 19, 20, 21, 22, or 23 and not independently re-executed here. |
| **[Production brief]** | Supplied by the task/production context and recorded in Batch 21 and Batch 22. Not re-inspected in Batch 24. |
| **[Decision]** | A direction selected by this memo for future authorized work. It is not an executed change. |
| **[Inference]** | A conclusion derived from static evidence that requires confirmation at a later gate. |
| **[Not verified]** | No Batch 24 evidence exists; the item remains a blocker. |

All Batch 24 work was read-only with respect to the repository except for creating this memo. No database, Neon, Render, Cloudflare, Alembic command, test suite, `.env` file, deployment setting, or Git state was touched.

---

## 1. Executive decision summary

### 1.1 The decision in one paragraph

**[Decision]** The application strategy is **Option B: merge the deployed governance/audit/review/materiality/clustering capabilities into the current branch**, with **Option D (start from the deployed tree and port current Batch 4/template work) as the contingency** if the Batch 26 file-level merge proves irreconcilable. **Option A (schema-only, keep deployed `58a0e5c`) is rejected as stated** because it leaves the two deployed P0 authorization vulnerabilities live in the only running application, does not deliver templates, and does not reconcile the current branch. **Option C (deploy the current branch alone) remains rejected** because it silently disables governance and audit. A separately re-scoped **Option A' (keep `58a0e5c` and backport only the P0 security fixes plus `0006`)** is an emergency alternative, not the recommendation, and would require its own memo, diff, tests, and deployment authorization.

### 1.2 Decisions made by this memo

| ID | Decision | Primary consequence |
| --- | --- | --- |
| **D1** | Adopt **Option B**; retain **D** as contingency; reject **C**; reject **A as stated**; treat **A'** as a separate emergency re-scope. | One application codebase becomes the target. Batch 26 performs a file-by-file merge, not a wholesale copy. |
| **D2** | Adopt the canonical single-head graph `0001_initial_tables -> 0002_verification_runs -> 0003_user_password -> 0004_enterprise_governance -> 0005_verification_templates -> 0006_discrepancy_review_decisions`. | The local `0005_verification_lineage` branch is retired, never replayed. Local `0004_verification_templates` is reissued as `0005_verification_templates`. |
| **D3** | Fix both P0 authorization defects in the application that will run: public registration must never accept a privileged role, and governance must derive authority from `users.role`, never from `X-User-Role`. | The deployed G1/G2 code cannot be ported. Batch 26 adds regression tests that fail if either behavior returns. |
| **D4** | Make migration execution explicitly targeted and fail-closed: no `settings.database_url` fallback, no ambient `.env` target, explicit connection for tests, and a production-only acknowledgement path. | `backend/migrations/env.py` and `backend/alembic.ini` are hardened in Batch 25. A developer cannot accidentally migrate the cloud database. |
| **D5** | Repair the revision template before generating any revision. | `backend/migrations/script.py.mako` is restored from the Alembic 1.20.0 generic template, verified by generation in a temporary directory. |
| **D6** | Run migration tests only on an explicitly validated, disposable loopback PostgreSQL target, using the Alembic-built schema, never `Base.metadata.create_all`. | T1-T14 become executable in Batch 25/26. A skipped test is not a pass. |
| **D7** | Local development database disposition defaults to **L1 - disposable rebuild**. **L2 - export/rebuild/reload** is allowed only with a written owner attestation that the data must be preserved. **L3 - stamp is rejected.** | The local database is rebuilt from the canonical graph. It is never stamped or upgraded through the retired branch. |
| **D8** | `discrepancy_review_decisions` foreign keys use **`ON DELETE RESTRICT`**, not `CASCADE`; audit-event deletion is guarded at the application level because the recovered `0004` already deployed `audit_events` with `CASCADE`. | Review and audit rows survive as evidence. Hard deletion of a project, run, or discrepancy with retained evidence is rejected with a conflict, not silently cascaded. User deletion preserves review/audit identity through `SET NULL`/text fields. This supersedes the Batch 23 `0006` CASCADE reconstruction if approved. |
| **D9** | Sequence the work as **Batch 25 = offline migration/tooling only**, **Batch 26 = Option B/D application merge and P0 remediation**, **Batch 27 = production evidence and rehearsal**, **Batch 28 = production execution**, **Batch 29 = post-deployment verification/hypercare**. | No stage may skip its entry gate. Production remains NO-GO until Batch 27 exits and Batch 28 is separately authorized. |
| **D10** | Enforce two-person accountability for migration execution and production deployment, with named role owners recorded in the approval block. | No single person may both execute and approve a production migration or deployment. |

### 1.3 Why Option B and not Option A

**[Repository + Preserved deployed source + Prior audit]** The deployed application at `58a0e5c` is the only application that currently maintains governance, audit, and review behavior. It also contains two P0 authorization flaws:

1. public registration accepts an optional unbounded `role` and persists it (`schemas/auth.py:20`, `endpoints/auth.py:41` in the preserved deployed tree); and
2. governance endpoints accept a client-supplied `X-User-Role` header and the service honors it when it is one of the four valid role strings (`endpoints/governance.py:41,67,94,121`; `services/governance_service.py:24-32`).

**[Decision]** Option A keeps that application running and changes only the schema. That leaves both vulnerabilities exploitable for the entire duration of the migration program, leaves the current branch unreconciled, and leaves `verification_templates` as a dormant table with no deployed consumer. Option A therefore fails the security and product-completeness tests even though it has the lowest immediate migration risk. Option B is larger, but it is the only option that fixes the code that actually runs, delivers templates, and ends the two-codebase divergence.

### 1.4 Why Option B and not Option D

**[Repository + Preserved deployed source]** The deployed commit is not present in local Git (`git cat-file -e 58a0e5c...` exits 1), and only a preserved source tree is available. The current branch is larger and newer in the verification engine, multi-source schemas, preprocessing, and profiling; the deployed tree is larger in export, result schemas, the verification endpoint, the run model, and the router. Neither tree is a superset.

**[Decision]** B uses the current branch as the system of record and ports the governance-era files into it. D would start from the preserved deployed tree and re-port the current Batch 4/template work, which is harder to source and would put the current branch's tests and newer engine at risk. D remains the contingency if B's file-by-file merge cannot preserve both behavior sets without an unacceptable regression.

### 1.5 What this memo does not authorize

This memo authorizes **no** production migration, no Neon connection, no Render deployment, no Cloudflare change, no database change, no `.env` edit, no application-code edit, no migration edit, and no test execution. It authorizes only the planning decision and, after written approval, the Batch 25 offline-scope entry described in section 10. All production actions remain behind the gates in section 9.

---

## 2. Scope, constraints, and baseline

### 2.1 Scope

**[Decision]** This memo decides:

- the application strategy (A, B, C, D, or a re-scoped A');
- the P0 authorization remediation and its acceptance tests;
- migration ownership, canonical graph, and safe retirement of the local branch;
- the `0006` retention/FK contract and the audit-deletion guard;
- revision-template and migration-environment tooling;
- isolated PostgreSQL test isolation;
- local development database disposition; and
- the stage gates, accountability, and first implementation batch.

### 2.2 Hard constraints observed in Batch 24

- No application, migration, test, configuration, environment, or existing-report edit.
- No connection to Neon, Render, Cloudflare, or any database.
- No Alembic command, test run, or deployment command.
- No read of `backend/.env` or any secret value.
- No Git write, commit, branch, tag, or ref change.
- No claim of runtime verification for static inspection.

### 2.3 Working-tree baseline

**[Repository]** Captured before and after this memo:

| Item | Value |
| --- | --- |
| Branch | `feature/batch-4-rule-engine-aggregation` |
| HEAD | `c91e9b37074483eeb7469dc943e1735fd5f5be02` |
| Working-tree entries before Batch 24 | 69 |
| Working-tree entries after this memo | 70 (the memo is the only addition) |
| Git ref inventory | 11 lines including `HEAD` (10 `git for-each-ref` entries) |
| Deployed commit in local Git | **Absent**; `git cat-file -e 58a0e5c243978480c4ca817c537c700ed6b20516` exits 1 |
| Batch 23 report | 1,461 lines, 124,963 bytes, SHA-256 `D28023EB600B28A3FFE794C3F244696D7ABB9F1E5247B6C1157A2394BF762EA0` |
| Batch 22 report | SHA-256 `70A7D43DD8418E12C7C2999379F8EA5A11ADBC5E77D73F0AD0B94AE3F65D8EA1` |

### 2.4 Critical file hashes before Batch 24

**[Repository]** SHA-256 values saved to the Batch 24 temporary baseline:

| File | SHA-256 | Bytes |
| --- | --- | --- |
| `backend/migrations/versions/0001_initial_tables.py` | `F3E045B29E52A132947E6ED156BA57995FD45B75EAA2C7D6289901C5AFD569A0` | 3,345 |
| `backend/migrations/versions/0002_verification_runs.py` | `44A9CD93E9A1260C7C61E3029FD6F884B5B27523FDCE25D966C986748AD78B2E` | 4,968 |
| `backend/migrations/versions/0003_user_password.py` | `6F256919E0E2537468335FF0A6C253E80BC513E3DFB6D414F9564C10083902E6` | 712 |
| `backend/migrations/versions/0004_verification_templates.py` | `CBE7E536573D06D49E4EB2F8EFB7BD26A0D3CCA786F01EA80AE7C8E7CA74E227` | 2,936 |
| `backend/migrations/versions/0005_verification_lineage.py` | `645BE701DFF05FDF6D263AF678CB17E77D818CE64C00A8B9F3AF96E46E585713` | 3,144 |
| `backend/migrations/env.py` | `F1A56CC8A201936615DE14F7730E32265C3132AF1372EF382F485207E67F056B` | 2,696 |
| `backend/migrations/script.py.mako` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 |
| `backend/app/schemas/auth.py` | `027DE78A82E1FA20FAD2E132557A32FE4A94488D0F5D1A19189B28C7E2D0797E` | 1,375 |
| `backend/app/api/v1/endpoints/auth.py` | `98C7CCB5850FD3D762AED530E20F3EBCBC19F1CB0E82203983CF2EF7E70470F4` | 3,085 |
| `backend/app/models/verification_run.py` | `B59FA3BF64072F81ED51ED8AA8BAE49150818E58890E409A02792A38D16E02BC` | 7,574 |

The recovered governance migration has SHA-256 `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` and must be copied byte-identically in Batch 25.

---

## 3. Current versus deployed application

### 3.1 Application divergence

**[Repository + Preserved deployed source]** The two trees are not versions of the same application with a small patch. They are divergent implementations.

| File | Current bytes | Deployed bytes | Interpretation |
| --- | ---: | ---: | --- |
| `backend/app/services/verification_engine.py` | 127,961 | 112,673 | Current is larger; Batch 4 behavior is newer. |
| `backend/app/schemas/multisource.py` | 14,503 | 5,869 | Current multi-source contract is substantially expanded. |
| `backend/app/schemas/result.py` | 21,449 | 27,657 | Deployed has materiality/side-by-side result fields. |
| `backend/app/services/preprocessing.py` | 25,763 | 22,461 | Current preprocessing is larger. |
| `backend/app/services/export_service.py` | 14,112 | 49,077 | Deployed export has materiality/recipe features. |
| `backend/app/services/profiling_service.py` | 40,745 | 33,303 | Current profiling is larger. |
| `backend/app/api/v1/endpoints/verification.py` | 8,006 | 10,035 | Deployed endpoint exposes governance fields. |
| `backend/app/models/verification_run.py` | 7,574 | 13,162 | Deployed has sign-off, governance, and review models. |
| `backend/app/models/user.py` | 1,218 | 1,445 | Deployed has `role`. |
| `backend/app/api/v1/router.py` | 2,678 | 3,094 | Deployed registers governance, audit, review, and recipe routes. |

**[Inference]** A wholesale copy in either direction would regress one tree. Batch 26 must merge file by file and run both the current Batch 2-14 tests and the ported governance/review/audit tests.

### 3.2 ORM table inventory

**[Repository + Preserved deployed source]** Counts were obtained by importing `app.models` and enumerating `Base.metadata`; no database connection was opened.

| Table | Current ORM | Deployed ORM | Canonical target | Migration owner |
| --- | ---: | ---: | ---: | --- |
| `users` | 6 | 7 (`role`) | 7 | `0004_enterprise_governance` adds `role`. |
| `projects` | 6 | 6 | 6 | `0001_initial_tables`. |
| `source_files` | 8 | 8 | 8 | `0001_initial_tables`. |
| `verification_runs` | 15 | 24 | 24 | `0002` base; `0004` adds 10. |
| `verification_discrepancies` | 19 | 36 | 36 | `0002` base; `0004` adds 22. |
| `verification_templates` | 10 | absent | 10 | `0005_verification_templates`. |
| `audit_events` | absent | 14 | 14 | `0004_enterprise_governance`. |
| `discrepancy_review_decisions` | absent | 12 | 12 | `0006_discrepancy_review_decisions`. |

### 3.3 Current branch strengths and gaps

**[Repository]** Current branch:

- Has a newer verification engine, multi-source schema, preprocessing, profiling, template model/service/schema/endpoints, and the Batch 2-14 tests.
- Has **no** `users.role` mapping, sign-off fields, materiality/clustering fields, `AuditEvent`, `DiscrepancyReviewDecision`, governance service, review service, audit service, or governance/audit/review/recipe routes.
- Maps `reason_code` and `confidence_score` as read-only Python properties and does not write the physical columns.
- Has empty placeholders at `backend/app/models/audit_log.py`, `backend/app/models/review.py`, `backend/app/services/audit_service.py`, `backend/app/services/review_service.py`, `backend/app/schemas/review.py`, and `backend/app/api/v1/endpoints/audit.py`.
- Has no public `role` field in `backend/app/schemas/auth.py` and no `X-User-Role` reference anywhere in `backend/app`.

### 3.4 Deployed application strengths and P0 defects

**[Preserved deployed source]** Deployed application:

- Has `users.role` (7 columns), 24 run columns, 36 discrepancy columns, `audit_events` (14 columns), `DiscrepancyReviewDecision` (12 columns), governance/materiality/clustering services, and governance/audit/review/recipe routes.
- Has **no** `verification_templates` model, service, or route.
- Accepts a public registration `role` and persists it (`backend/app/schemas/auth.py:20`; `backend/app/api/v1/endpoints/auth.py:41`).
- Accepts `X-User-Role` on four governance endpoints (`backend/app/api/v1/endpoints/governance.py:41,67,94,121`) and honors any of the four valid role strings (`backend/app/services/governance_service.py:24-32`).
- Has review routes that insert into `discrepancy_review_decisions` (`backend/app/services/review_service.py:104,256`), but no migration in either tree creates that table. Production is reported to lack it. Those routes fail at runtime today.
- Uses SQLite `create_all` for its governance/review tests, so it never detected the missing review table or the PostgreSQL-specific authorization/retention issues.

### 3.5 Migration graph divergence

**[Repository + Prior audit]**

```text
Current local graph:
0001_initial_tables
  -> 0002_verification_runs
       -> 0003_user_password
            -> 0004_verification_templates
                 -> 0005_verification_lineage          (local head)

Production graph:
0001_initial_tables
  -> 0002_verification_runs
       -> 0003_user_password
            -> 0004_enterprise_governance               (production head)
```

The six lineage columns are owned by the production `0004`. Replaying local `0005_verification_lineage` would issue six duplicate `ADD COLUMN` operations. Combining the histories unmodified creates two heads. A merge revision does not solve this because both parents are still traversed.

### 3.6 Production facts carried forward

**[Production brief + Prior audit]** Production is reported to be at `0004_enterprise_governance`, with 33 verification runs and 25,654 discrepancies, and without `verification_templates` or `discrepancy_review_decisions`. These are **not** re-verified in Batch 24. They are gate inputs, not facts established here.

---

## 4. Option analysis and decision register

### 4.1 The four options

**[Prior audit + Decision]** The options use the Batch 23 definitions:

| Option | What is deployed | Governance | Templates | Relative effort | Verdict |
| --- | --- | --- | --- | --- | --- |
| **A - Schema-only, keep `58a0e5c`** | Apply `0005` and/or `0006`; do not deploy current code. | Preserved, but G1/G2 remain exploitable. | No; `0005` is dormant. | Lowest. | **Rejected as stated.** |
| **B - Merge governance into current** | Current branch plus deployed governance/audit/review/materiality/clustering code. | Preserved if the port is complete and tested. | Yes. | Highest. | **Recommended.** |
| **C - Deploy current alone** | Current branch over the canonical schema. | Lost: no role enforcement, sign-off, materiality, clustering, review, or audit writes. | Yes. | Medium. | **Rejected.** |
| **D - Start from deployed, add current work** | Deployed tree plus current Batch 4/template work. | Preserved. | Yes. | Highest. | **Contingency only.** |

### 4.2 Option A is rejected as stated

**[Decision]** Option A fails on three independent grounds:

1. **Security.** The deployed application is the only application running in production. Its public registration accepts `role` and persists it, and its governance endpoints trust `X-User-Role`. A schema-only change leaves both P0 paths live. The migration program could take weeks; the vulnerability would remain exploitable for that entire period. A decision to defer a known P0 authorization bypass requires a separate, explicit risk acceptance by the security owner and engineering lead; it is not a migration-planning default.
2. **Product completeness.** `0005_verification_templates` would create a table that the deployed application does not use. The current branch's template feature would remain undeployed. The migration would therefore add schema without delivering the capability that motivated it.
3. **Reconciliation.** Option A explicitly does not reconcile the current branch. The two application trees and the two migration histories would remain divergent after the migration. The next feature batch would face the same decision with more production data and more drift.

**[Decision]** Option A is not authorized by this memo. If production risk must be reduced before Batch 26 is complete, the correct emergency path is A' in section 4.3, not A.

### 4.3 Option A' - emergency security backport (separate re-scope)

**[Decision]** A' means: keep `58a0e5c` as the deployed application, backport only the G1/G2 fixes (and the G5 length bounds if review routes are used), add `0005` and/or `0006`, and deploy the patched governance application. It is functionally A plus a security patch.

A' is **not recommended** because:

- The deployed commit is not in local Git, so the backport must be reconstructed from the preserved tree and re-tested as a separate branch.
- It still does not deliver templates and still leaves the current branch unreconciled.
- It creates a third code state (deployed + backport) that must be maintained until B/D lands.

A' is permitted only as a separately authorized emergency change with its own memo, diff, security review, tests, and deployment gate. It cannot be used to bypass D1 or the Batch 26 merge.

### 4.4 Option B is recommended

**[Decision]** Option B is selected because it is the only option that satisfies all four requirements at once:

1. **Fix the code that runs.** The merged application is the application that will be deployed. G1/G2 are fixed in that code, not deferred to an unmerged branch.
2. **Preserve governance and audit continuity.** The deployed sign-off, materiality, clustering, review, and audit behavior is ported, not dropped. Existing production data remains meaningful.
3. **Deliver templates.** The current template model/service/schema/endpoints are retained and become usable once `0005` is applied.
4. **End the divergence.** The current branch becomes the system of record. The preserved deployed tree becomes a reference artifact, not a second production codebase.

**Principal risk:** the merge is file-level and neither tree is a superset. The engine, result schema, export service, and run model differ materially. A careless merge could regress Batch 4 behavior or governance behavior.

**Mitigations:** Batch 26 must merge file by file; preserve both test suites; add contract tests for physical `reason_code`/`confidence_score`; run the current Batch 2-14 tests and the ported governance/review/audit tests; and require an application smoke test against the canonical schema before production authorization.

### 4.5 Option D is the contingency

**[Decision]** D is selected only if one of the following is true during Batch 26:

- The current branch's engine/result/export contracts cannot be merged with the deployed governance contracts without an unacceptable regression to either behavior set.
- The current branch fails its own baseline tests after the merge and the failures cannot be resolved within the Batch 26 scope.
- A governance-first production deadline forces deployment before the current branch merge is complete, and the engineering lead explicitly chooses to port current features forward instead.

D's risks are higher than B's because the deployed commit is absent from local Git, the preserved tree is the only source, and the current branch's newer engine/export/profiling/multisource work must be re-ported. D must use the same canonical graph, P0 fixes, retention decision, test gates, and two-person authorization. D is not a shortcut around any gate.

### 4.6 Option C remains rejected

**[Decision]** C is rejected. Deploying the current branch over the canonical schema preserves historical governance data but stops maintaining it: no role enforcement, no sign-off, no materiality, no clustering, no review writes, and no audit writes. The audit chain would be truncated at the deployment boundary. A green current test suite would not detect the loss because the current suite has no governance/review/audit tests.

### 4.7 Decision register with consequences

| ID | Decision | Alternatives rejected | Consequences | Reversal / change control |
| --- | --- | --- | --- | --- |
| **D1** | Option B; D contingency; A rejected as stated; C rejected; A' separate emergency re-scope. | A, C, D as primary. | Batch 26 is a file-level merge with the highest effort. One codebase becomes the target. Templates and governance both ship. | Changing to D requires a written Batch 26 decision with the trigger evidence. Changing to A/A' requires a new memo and security risk acceptance. |
| **D2** | Canonical graph `0001 -> 0002 -> 0003 -> 0004_enterprise_governance -> 0005_verification_templates -> 0006_discrepancy_review_decisions`. | Local graph retained; merge revision; stamp. | Local `0005_verification_lineage` is retired. Local `0004_verification_templates` is reissued as `0005`. One head only. | Reverting after production applies would require a new forward migration, not a downgrade. |
| **D3** | Public registration never accepts a privileged role; governance authority comes only from `users.role`. | Port deployed G1/G2; admin header override in production. | The deployed auth/governance code cannot be copied as-is. Batch 26 must rewrite the relevant schemas, dependencies, services, and tests. | Removing the guard requires a new security review and a new memo. |
| **D4** | Migration execution requires an explicit target; no `settings.database_url` fallback; no ambient `.env`; test mode requires an explicit connection; production requires an acknowledgement and two-person approval. | Keep current `env.py`; rely on operator discipline. | `env.py` and `alembic.ini` change in Batch 25. Some existing developer workflows that relied on `.env` will need an explicit URL. | A future relaxation requires a security review and a new guard test. |
| **D5** | Restore `script.py.mako` from the Alembic 1.20.0 generic template or a reviewed equivalent before generating any revision. | Leave empty; write revisions by hand. | `alembic revision` becomes usable. Generated revisions must still be reviewed. | Template changes are versioned and tested by throwaway generation. |
| **D6** | Migration tests run only on an explicitly validated loopback PostgreSQL target, against the Alembic-built schema, never `create_all`. | SQLite `create_all`; shared development database; production rehearsal as the first test. | T1-T14 require a disposable local PostgreSQL instance and explicit environment variables. Tests that skip are not passes. | Any change to the guard requires a security/test review. |
| **D7** | Local DB defaults to L1 disposable rebuild; L2 only with written owner attestation; L3 stamp rejected. | Stamp; upgrade through the retired branch; silent data deletion. | Local data may be lost under L1. L2 requires export/reload rehearsal. The local revision remains unverified until an authorized read-only query. | The owner may choose L2 before Batch 25 exit; the choice is recorded in the approval block. |
| **D8** | `0006` review FKs use `RESTRICT`; audit deletion is guarded in the application because `0004`'s `audit_events` already uses `CASCADE`. | `CASCADE` for review; schema change to `0004`; archive-before-delete only. | Deleting a discrepancy/run with review rows is rejected. Deleting a project/run with audit rows is rejected by the application. Retention becomes enforceable. | If the retention policy later requires database-level audit `RESTRICT`, add a separate forward migration after production inventory; do not edit `0004`. |
| **D9** | Batch 25 offline migration/tooling; Batch 26 application merge/P0; Batch 27 evidence/rehearsal; Batch 28 production; Batch 29 hypercare. | One large batch; production-first; parallel app and schema changes. | Each stage has its own entry/exit gate. No production action in Batch 25 or 26. | Stage scope changes require a written amendment to this memo. |
| **D10** | Two-person accountability for migration execution and deployment; named role owners in the approval block. | Single-operator migration; informal review. | Production execution requires an executor and an independent reviewer present. Approvals are recorded. | Break-glass requires post-hoc review and a new gate record. |

---

## 5. P0 security remediation and P1 blockers

### 5.1 P0-1 - Public registration must not assign a privileged role

**Finding [Preserved deployed source]:** `backend/app/schemas/auth.py:20` accepts an optional unbounded `role`; `backend/app/api/v1/endpoints/auth.py:41` uppercases the value and persists it. There is no enum, allow-list, admin check, or separation between public registration and administrative provisioning. An unauthenticated caller can register as `ADMIN` and then use governance routes. Maker-checker separation is defeated.

**Decision [D3]:**

- `UserRegisterRequest` must contain only `email`, `password`, and `full_name`. It must not contain `role`.
- The registration service must set `role = "MAKER"` server-side. It must not read a role from the request body, query string, header, cookie, or token.
- Role elevation must be a separate authenticated endpoint, for example `PATCH /api/v1/users/{user_id}/role`, available only to an authenticated `ADMIN`.
- The elevation endpoint must validate the target role against exactly `{MAKER, CHECKER, ADMIN, VIEWER}`. It must reject unknown strings, case variants that are not normalized, `NULL`, and empty values with 422.
- The API response may expose `role` read-only. `UserResponse` must include it for the UI and for tests, but the field must not be writable through registration or profile update.
- The database default `MAKER` from `0004` is a defense-in-depth default, not the authorization decision. The application must set the value explicitly.

**Required files in Batch 26:**

- `backend/app/schemas/auth.py` - remove `role` from `UserRegisterRequest`; add `role` to `UserResponse` as read-only.
- `backend/app/api/v1/endpoints/auth.py` - set `role="MAKER"` on registration; add the admin-only elevation endpoint or a separate users endpoint.
- `backend/app/models/user.py` - map `role` with the server/client default.
- `backend/app/api/deps.py` - add `require_roles(...)` / `require_admin` dependencies.
- `backend/app/core/security.py` - define the role constants and normalization/validation helpers.
- New tests, for example `backend/tests/test_auth_role_security.py`.

**Acceptance tests:**

1. `POST /api/v1/auth/register` with `{"role": "ADMIN"}` is rejected with 422 (unknown field) or the field is ignored; in either case the created user's stored role is `MAKER`.
2. Registration with `role: "admin"`, `role: "ADMIN "`, `role: null`, or a 10,000-character role string cannot create a privileged user.
3. A `MAKER`, `CHECKER`, or `VIEWER` cannot call the elevation endpoint; it returns 403.
4. An `ADMIN` can elevate a user to `CHECKER`; the change is persisted and audited.
5. An invalid target role returns 422, not 500.

### 5.2 P0-2 - Governance must not trust `X-User-Role`

**Finding [Preserved deployed source]:** `backend/app/api/v1/endpoints/governance.py:41,67,94,121` accept `X-User-Role`; `backend/app/services/governance_service.py:24-32` returns the override if it is one of the four role strings. Any authenticated user can claim `CHECKER` or `ADMIN` and approve or reject sign-offs. The audit event records the claimed role, so the audit trail is also poisoned.

**Decision [D3]:**

- Remove `X-User-Role` from all governance endpoint signatures and from all service resolution paths.
- Resolve the role only from the authenticated principal's `users.role` value, loaded by `get_current_user` and enforced by a server-side dependency. Do not accept a role from a header, query parameter, request body, JWT claim that the server does not control, or environment override.
- If a test override is absolutely required, it must be compiled only in a test configuration, require an authenticated `ADMIN`, require a non-production environment flag, and be covered by a test proving it is disabled in production. The default and recommended design is **no override at all**.
- The audit event's `user_role` must be the authoritative role used for the decision. If the principal has a missing, `NULL`, or unrecognized role, the request fails closed with 403; it must not fall back to `MAKER` or `ADMIN`.
- Maker-checker rules must be enforced on the server: a `MAKER` cannot approve their own proposal; a `CHECKER` cannot approve a run they proposed; an `ADMIN` override, if any, must be explicit, audited, and tested.

**Required files in Batch 26:**

- `backend/app/api/v1/endpoints/governance.py` - remove the header parameter from all four endpoints.
- `backend/app/services/governance_service.py` - delete the header-override branch; accept the authoritative role from the caller/dependency.
- `backend/app/api/deps.py` - role dependency and current-user role loading.
- `backend/app/models/user.py` - `role` mapping.
- Ported `backend/tests/test_governance_audit.py` plus new regression tests, for example `backend/tests/test_governance_role_security.py`.

**Acceptance tests:**

1. A `MAKER` sends `X-User-Role: CHECKER` and attempts to approve a sign-off; the request returns 403 and the sign-off remains unchanged.
2. A `MAKER` sends `X-User-Role: ADMIN`; the header is ignored and the audit event records `MAKER`, not `ADMIN`.
3. A `CHECKER` can approve a run proposed by a different `MAKER`; the audit event records `CHECKER`.
4. A user with `role = NULL` or an unknown role is denied governance actions.
5. A search of the merged `backend/app` finds no `X-User-Role`, `x_user_role`, or equivalent client-role authority path.

### 5.3 P0-3 - Migration execution must be explicitly targeted

**Finding [Repository]:** `backend/migrations/env.py:25` sets `sqlalchemy.url` from `settings.database_url`; lines 68-75 build the engine from that URL when no explicit connection is supplied. `settings` loads `backend/.env`, and `backend/alembic.ini` has a local URL that `env.py` overwrites. There is no CLI target guard. A developer or release job running `alembic upgrade head` can migrate the `.env`-configured cloud database.

**Decision [D4]:**

- `env.py` must not use `settings.database_url` as a migration target. Remove the `settings` import and the unconditional `config.set_main_option` fallback.
- The migration target must come from one of exactly two explicit sources:
  1. a validated SQLAlchemy connection supplied in `config.attributes["connection"]` (the test/programmatic path); or
  2. an explicit URL supplied for this process, for example `-x db_url=...` or `VERIFYGRID_MIGRATION_DATABASE_URL`, never from `.env`.
- `backend/alembic.ini` must contain no usable target URL. Remove the URL value or set it to an empty placeholder that fails closed.
- Before any DDL, query and assert `current_database()`, `current_user`, and `inet_server_addr()`. Refuse to proceed if the connected database/user does not match the validated target.
- The default allow-list is loopback only. A non-loopback target requires `VERIFYGRID_ALLOW_PRODUCTION_MIGRATION=1`, an explicit change-ticket acknowledgement (`VERIFYGRID_PRODUCTION_MIGRATION_ACK`), and the two-person execution gate. The acknowledgement is a guard, not a substitute for human authorization.
- In test mode (`VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS=1`), if no validated connection is supplied, `env.py` must raise before opening any connection. It must never fall back to the application database.
- Offline mode (`--sql`) must also require an explicit URL and must not read `.env`.

**Required files in Batch 25:**

- `backend/migrations/env.py` - remove the settings fallback; add the explicit-target resolver, identity check, and test-mode guard.
- `backend/alembic.ini` - remove the usable URL.
- `backend/tests/test_migration_env_guard.py` (new) - unit tests for missing target, `.env`-only target, mismatched identity, test-mode fallback, and explicit loopback target.

**Acceptance tests:**

1. With no explicit target and no connection, `env.py` raises a clear error before connecting.
2. With `VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS=1` and no connection, `env.py` raises, even if `DATABASE_URL` or `.env` points at a database.
3. With an explicit validated loopback connection, migrations proceed.
4. With a connection whose `current_database()`/`current_user` differs from the validated target, migrations abort.
5. No code path constructs an engine from `settings.database_url`.

### 5.4 P0-4 - The test path must not depend on an uncommitted `env.py`

**Finding [Repository + Prior audit]:** `env.py` is modified (16 additions, 2 deletions) to honor `config.attributes["connection"]`; the change is uncommitted. If it is reverted or lost, `alembic.command.upgrade()` in tests falls back to `settings.database_url` while the test still validates only `VERIFYGRID_TEST_DATABASE_URL`. A test run could migrate the application database while the guard reports success.

**Decision [D4/D6]:** Commit the explicit-connection path as part of Batch 25, together with the hard fail-closed guard in section 5.3. A test that enables integration mode without an explicit connection must fail, not skip. The connection identity must be asserted inside the migration path, not only in the test fixture.

**Required files:** `backend/migrations/env.py`, `backend/tests/test_migration_env_guard.py`, `backend/tests/conftest.py` or the relevant fixture, and the migration tests.

### 5.5 P0-5 - Production evidence is a prerequisite, not a postscript

**Decision:** The following remain P0 blockers to production authorization, even though they are not code defects:

- read-only production inventory confirming the revision, table absence, governance shape, row counts, and audit-chain status;
- a verified backup/PITR restore to a separate branch or database;
- a Render dashboard review confirming build/start/pre-deploy commands and auto-deploy behavior;
- a Neon-branch or isolated-restore rehearsal;
- named database owner, migration executor, independent reviewer, security owner, and release manager;
- two-person written authorization for the production window.

None of these can be satisfied by static inspection. They are Batch 27 gates.

### 5.6 P1 blocker register

The following P1 items must be closed before production authorization. Most are Batch 26 application work; two are Batch 25 tooling work.

| ID | P1 finding | Decision and required work | Target batch | Acceptance evidence |
| --- | --- | --- | --- | --- |
| **G5** | Review/assignment fields can exceed `varchar(100)`/`varchar(255)`. | Add `max_length` to `ReviewDecisionRequest.reviewer_id`/`.reviewer_email`, `BulkReviewRequest`, and `AssignmentRequest.reviewer_id`. Decide whether `resolved_by`/`assigned_to` store a user id or an email; if email, bound to 255 and change the column only through a forward migration, not by editing `0004`. Normal paths must return 422, not 500. | Batch 26 | Tests with 101/256/10,000-character values; no `DataError`; assignment works for a 254-character email only if the column is widened by an approved migration, otherwise the API rejects it cleanly. |
| **G6** | Audit sequence allocation is unsynchronized. | Serialize chain allocation with a transaction-scoped PostgreSQL advisory lock keyed by the chain (`project_id` plus `run_id`), or an equivalent row lock that all writers use. Keep the read-max-plus-one logic inside the lock. Document that direct SQL writers are prohibited. Add a concurrency test with two sessions. A unique constraint is defense-in-depth and is **not** added in `0006`; if required later, it is a separate forward migration after production inventory. | Batch 26 | Two concurrent writers produce distinct sequence numbers and a verifiable chain; no duplicate sequence in 100 concurrent appends; test uses the migration-built schema. |
| **G7** | Cascade FKs destroy audit/review evidence. | `0006` uses `ON DELETE RESTRICT` for both review FKs. Because `0004` already deployed `audit_events.project_id`/`.run_id` as `CASCADE` and must remain byte-identical, the application must reject hard deletion of a project/run/discrepancy when audit or review rows exist, with 409 and an explanatory error. Add a retention/archival path before any future hard delete. | Batch 25 (`0006` DDL) and Batch 26 (guards) | `DELETE` of a discrepancy/run with review rows fails at the database with FK violation; API returns 409; audit rows survive an attempted project/run delete; tests prove no silent cascade. |
| **G8** | `cluster_name` has no 255-character guard. | Truncate deterministically to 255 with an ellipsis or short hash suffix; do not widen the column without production evidence. Add a long-field-name test. | Batch 26 | A discrepancy with many/long field names persists a `cluster_name` of at most 255 characters; no `DataError`. |
| **G9** | `reason_code`/`confidence_score` semantics differ. | Map `_reason_code`/`_confidence_score` to the physical columns with setters. Write the physical values on every discrepancy path in the engine. Preserve the current computed fallback, including the `NULL_KEY` branch for blank-key `needs_review`. Do not copy the deployed property that omits `NULL_KEY`. | Batch 26 | Round-trip tests: current-created rows expose the physical value; NULL physical values fall back correctly; blank-key rows produce `NULL_KEY`; deployed filters see current-created rows. |
| **G10** | Default JWT secret is insecure if `SECRET_KEY` is missing. | Refuse to start in production when `secret_key` is the default. Add a startup/config test. Document rotation. This is a deployment gate, not a migration. | Batch 26 | Production-like config with the default secret fails startup; explicit secret starts; test does not print the secret. |
| **G11** | `script.py.mako` is empty. | Restore the Alembic 1.20.0 generic template (20 lines, SHA-256 `D38920781B4D31AE1C0A71BC09F41C2ADE8FEAB9E5A087E3F30CB4BBF0C1C9D3`) or a reviewed equivalent. Verify by generating a throwaway revision in a temp directory, not in the repository graph. | Batch 25 | `alembic revision` in a temp copy produces a syntactically valid file with `revision`, `down_revision`, `upgrade()`, and `downgrade()`; no repository revision is created. |
| **G12** | Tests do not cover governance, review, or audit; head constants are stale. | Repoint `PREVIOUS_HEAD`/`EXPECTED_HEAD` to the canonical graph; add T1-T14; port deployed governance/audit, clustering, materiality, and recipe tests; convert them from SQLite `create_all` to migration-built PostgreSQL where they assert schema behavior. Treat skips as not-run. | Batch 25 (migration tests) and Batch 26 (application tests) | `test_alembic_migration_parity.py` and `test_postgres_migration_application.py` use `0006`; new `test_postgres_reconciliation_design.py` covers T1-T14; ported tests pass on the canonical schema; no integration test silently skips. |

### 5.7 P2 residual register

These are documented, not production blockers for the first migration, but they must not be lost:

| ID | P2 item | Treatment |
| --- | --- | --- |
| **G13** | Server defaults are not compared by the parity test. | Add explicit `information_schema.columns.column_default` assertions in Batch 25/26; do not enable `compare_server_default` blindly because the ORM declarations are incomplete. |
| **G14** | `0003_user_password.hashed_password` has an empty-string server default. | Document. Login fails closed for an empty hash. Remove only in a future forward migration after confirming no rows rely on it; never edit `0003`. |
| **G15** | `is_bulk_action` default is ambiguous. | Canonical `0006` uses `server_default=sa.false()` and the reconciled ORM declares the same server default. Test raw insert and ORM insert. |
| **G16** | Review `run_id` can be inconsistent with the discrepancy's run. | Application-enforced invariant; service loads the discrepancy by `run_id` before insert. Document; consider a composite FK only as a separate contract change. |
| **G17** | Template uniqueness with `NULL` owners. | Unique `(owner_id, name)` treats `NULL` owners as distinct. Document; reads are owner-scoped. No partial unique index in this reconciliation. |
| **G18** | New tables have no production history. | Treat as new schema; test with synthetic production-scale data; inventory production before deploy to confirm both tables are still absent. |

### 5.8 P0/P1 closure gates

| Gate | Must be closed before | Evidence required |
| --- | --- | --- |
| G1 registration role | Batch 26 exit | Regression tests in section 5.1 pass; code search finds no role field in public registration. |
| G2 header authority | Batch 26 exit | Regression tests in section 5.2 pass; code search finds no `X-User-Role`. |
| G3 explicit migration target | Batch 25 exit | `env.py` guard tests pass; no `settings.database_url` path; `alembic.ini` has no usable URL. |
| G4 committed test path | Batch 25 exit | `env.py` explicit-connection path committed; fail-closed test passes. |
| G5-G12 P1 | Batch 26 exit (G11 at Batch 25) | Section 5.6 acceptance evidence. |
| Production evidence (P0-5) | Batch 28 entry | Batch 27 exit package. |

---

## 6. Migration ownership, canonical graph, and safe retirement

### 6.1 Canonical graph

**[Decision D2]** The only authorized migration graph is:

```text
0001_initial_tables
  -> 0002_verification_runs
       -> 0003_user_password
            -> 0004_enterprise_governance
                 -> 0005_verification_templates
                      -> 0006_discrepancy_review_decisions   (sole head)
```

Rules:

- Every revision has exactly one parent and one child until `0006`.
- `0005_verification_lineage` is not in the graph and is never replayed.
- `0004_verification_templates` is not in the graph. Its DDL is reissued as `0005_verification_templates`.
- No merge revision, no branch label, no `depends_on`, no stamp.
- The six lineage columns are owned by `0004_enterprise_governance` and must appear exactly once in the whole graph.

### 6.2 Revision ownership matrix

| Revision / file | Owner | Contract authority | Change rule |
| --- | --- | --- | --- |
| `0001_initial_tables` / `0001_initial_tables.py` | Migration owner | Repository history | Immutable. No edit. |
| `0002_verification_runs` / `0002_verification_runs.py` | Migration owner | Repository history | Immutable. No edit. |
| `0003_user_password` / `0003_user_password.py` | Migration owner | Repository history | Immutable. No edit. |
| `0004_enterprise_governance` / `0004_enterprise_governance_and_materiality.py` | Migration owner plus release manager | Preserved deployed file; SHA-256 `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` | Copy byte-identically. Do not edit operations, defaults, indexes, or FK actions. |
| `0005_verification_templates` / `0005_verification_templates.py` | Template feature owner plus migration owner | Current `0004_verification_templates.py` DDL and `models/verification_template.py` | New revision; 10-column contract; no changes to the table shape. |
| `0006_discrepancy_review_decisions` / `0006_discrepancy_review_decisions.py` | Governance/review owner plus migration owner | Deployed ORM `DiscrepancyReviewDecision`, deployed `review_service.py`, and this memo's D8 retention decision | New revision; 12-column contract; review FKs `RESTRICT`; `is_bulk_action` server default `false`; four indexes. |
| `script.py.mako` | Tooling owner | Alembic 1.20.0 generic template | Restore and test by throwaway generation. |
| `env.py` | Platform/test owner | This memo's D4 | Harden and commit with guard tests. |
| `alembic.ini` | Platform owner | This memo's D4 | Remove usable URL. |
| Migration tests | QA/test owner | This memo's D6 and T1-T14 | Repoint to `0006`; migration-built PostgreSQL only. |
| Application merge / P0 | Application owner plus security owner | This memo's D1/D3 and Batch 23 section 7 | File-by-file merge; no wholesale copy. |

### 6.3 Recovered `0004_enterprise_governance` handling

**[Prior audit + Preserved deployed source]**

| Property | Required treatment |
| --- | --- |
| Source path | `C:\Users\shaha\AppData\Local\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516\backend\migrations\versions\0004_enterprise_governance_and_materiality.py` |
| Destination path | `backend/migrations/versions/0004_enterprise_governance_and_materiality.py` |
| Revision | `0004_enterprise_governance` |
| Parent | `0003_user_password` |
| SHA-256 | `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` |
| Git object | Absent locally; the deployed commit is not an ancestor of `HEAD` or `origin/main`. |
| Rule | Copy byte-identically. Verify the hash after copy and before commit. Do not reformat, rename the revision, or edit the operations. |

The file adds 33 columns, 5 foreign-key definitions, 13 indexes, and `audit_events`. Its `audit_events.project_id` and `.run_id` foreign keys are `ON DELETE CASCADE`; that deployed contract is retained because editing the recovered file would destroy provenance and because production already has it. D8 addresses the retention consequence at the application layer.

### 6.4 Local revision retirement mechanics

**[Decision D2/D7]** The two local revisions are untracked. Deleting them without an archive would lose their content. The retirement sequence in Batch 25 is:

1. Create `backend/migrations/retired/` (outside `backend/migrations/versions/`, so Alembic does not scan it).
2. Copy `backend/migrations/versions/0004_verification_templates.py` to `backend/migrations/retired/0004_verification_templates.py`.
3. Copy `backend/migrations/versions/0005_verification_lineage.py` to `backend/migrations/retired/0005_verification_lineage.py`.
4. Record both archived SHA-256 values in `docs/audits/Batch24_Migration_Provenance.md`.
5. Remove the originals from `backend/migrations/versions/`.
6. Add the recovered `0004_enterprise_governance_and_materiality.py` byte-identically and verify `44D31AE9...`.
7. Add `0005_verification_templates.py` and `0006_discrepancy_review_decisions.py`.
8. Run a static graph check: exactly one head, linear parents, no duplicate revision IDs, no `0005_verification_lineage`.
9. Commit the graph, the archive, the provenance note, `script.py.mako`, `env.py`, `alembic.ini`, and the migration tests in one reviewed change.
10. Only after the commit, run the isolated tests and the local rebuild.

The local revision files must not be renamed into the canonical graph. Renaming `0004_verification_templates.py` to `0005_verification_templates.py` would leave its `down_revision` pointing at `0003` and create a second head or a wrong parent. The file is reissued with new metadata, not renamed.

### 6.5 Why stamping is prohibited

**[Prior audit + Decision D7]** Alembic's `alembic_version` records what DDL was executed. It is not a repair tool.

| Local state | `alembic upgrade head` with the canonical graph | Stamp shortcut | Result |
| --- | --- | --- | --- |
| At `0004_verification_templates` | Fails: the revision is not in the canonical ancestry; if removed, Alembic cannot locate the current revision. | Stamp to `0004_enterprise_governance` claims 33 columns and `audit_events` exist when they do not. | False history; `0005` collides with the existing template table; governance queries fail. |
| At `0005_verification_lineage` | Fails for the same reason; the revision is retired. | Stamp to `0006` skips all canonical DDL. | Severe false history; no governance; template table exists; review table absent. |
| Any state | Canonical `0005` attempts `CREATE TABLE verification_templates` against an existing table. | Any stamp is a lie about executed DDL. | Unusable. |

The local database must be rebuilt, or exported, rebuilt, and reloaded. Section 8 defines the disposition.

### 6.6 `0006_discrepancy_review_decisions` contract and retention decision

**[Decision D8]** The table contract is the Batch 23 reconstruction with one deliberate change: both foreign keys use `ON DELETE RESTRICT` instead of `CASCADE`.

**Revision metadata:**

| Property | Value |
| --- | --- |
| Revision | `0006_discrepancy_review_decisions` |
| Parent | `0005_verification_templates` |
| DDL source | Deployed ORM `DiscrepancyReviewDecision` and `review_service.py`; no historical migration exists. |
| Nature | Reconstruction, not recovered DDL. Constraint names are project-chosen and must be stable. |

**Columns (12):**

| Column | Type | Nullable | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | No | application `uuid4` | Primary key. |
| `discrepancy_id` | `uuid` | No | none | FK `verification_discrepancies.id` `ON DELETE RESTRICT`; indexed. |
| `run_id` | `uuid` | No | none | FK `verification_runs.id` `ON DELETE RESTRICT`; indexed. |
| `decision` | `varchar(50)` | No | none | `APPROVE`, `REJECT`, `FORCE_MATCH`, `ESCALATE`, `REOPEN`. |
| `justification` | `text` | No | none | Non-blank. |
| `reviewer_id` | `varchar(100)` | Yes | none | Denormalized identity; bounded at the API. |
| `reviewer_email` | `varchar(255)` | Yes | none | Denormalized identity; bounded at the API. |
| `previous_status` | `varchar(50)` | Yes | none | Snapshot before the decision. |
| `new_status` | `varchar(50)` | No | none | Mapped from `DECISION_TO_STATUS`. |
| `is_bulk_action` | `boolean` | No | server `false`; ORM `server_default=sa.false()` | Set explicitly by the service. |
| `cluster_id` | `varchar(64)` | Yes | none | Snapshot; not an FK. |
| `created_at` | `timestamptz` | No | `now()` | Service also passes UTC. |

**Objects:** primary key `(id)`; FKs `discrepancy_id` and `run_id` with `RESTRICT`; indexes on `cluster_id`, `discrepancy_id`, `reviewer_id`, `run_id`. No unique constraint (multiple decisions per discrepancy are valid). No `updated_at`, no soft-delete column, no metadata JSON.

**Consequences of `RESTRICT`:**

- Deleting a discrepancy or run with review rows fails with a foreign-key violation. The API must pre-check and return 409 with a clear message, or use an approved soft-delete/archival path.
- Review rows survive project/run/discrepancy deletion attempts, preserving the evidence of record.
- Existing production has no review table, so there is no production data migration conflict at creation time.
- The deployed ORM declares `CASCADE`. Batch 26 must change the ORM foreign keys to `RESTRICT`; otherwise the ORM metadata and the migration disagree. This is an intentional contract change, not drift.
- The deployed review service's delete/cleanup behavior must be audited and changed if it relies on cascade.
- **Transition window:** between applying `0006` and deploying the Batch 26 build, the old deployed application may encounter a foreign-key conflict on a delete path that previously cascaded. The migration window must be coordinated so this interval is as short as possible; delete smoke tests are part of the Stage 4 verification. If the old application has an active delete workflow, apply `0006` immediately before the Batch 26 deploy and keep the rollback plan ready.

**Audit-event deletion guard:**

- `audit_events.project_id` and `.run_id` remain `CASCADE` because `0004` is byte-identical and already deployed. The application must guard deletion of projects and runs when audit rows exist. The guard checks `audit_events` and `discrepancy_review_decisions` before any hard delete and returns 409.
- A future retention policy that requires database-level `RESTRICT` on `audit_events` requires a separate forward migration after production inventory. It is not part of `0006`, and `0004` must not be edited.
- Tests must prove that an attempted delete does not remove audit rows and does not silently cascade review rows.

### 6.7 `0005_verification_templates` contract

**[Decision D2]** Reissue the current local `0004_verification_templates.py` DDL with new revision metadata:

| Property | Value |
| --- | --- |
| Revision | `0005_verification_templates` |
| Parent | `0004_enterprise_governance` |
| Columns | 10: `id`, `owner_id`, `name`, `description`, `mode`, `visibility`, `config_version`, `configuration`, `created_at`, `updated_at`. |
| Owner FK | `owner_id -> users.id` `ON DELETE SET NULL`. |
| Unique | `uq_verification_templates_owner_name` on `(owner_id, name)`. |
| Index | `ix_verification_templates_owner_id`. |
| Defaults | `visibility='personal'`, `config_version=1`, `created_at=now()`, `updated_at=now()`. |

The table contract is exact and must not be widened or "fixed" during reconciliation. `NULL` owners can duplicate names because PostgreSQL treats `NULL` values as distinct; this is documented as a dormant-data edge case, not changed with a partial index in this batch.

### 6.8 Migration ownership and separation of duties

| Role | Responsibility | Cannot do alone |
| --- | --- | --- |
| **Engineering lead / decision owner** | Approves D1-D10, stage transitions, and production authorization. | Execute the production migration. |
| **Migration owner** | Owns the graph, `0004` provenance, `0005`/`0006` DDL, `script.py.mako`, and the migration test plan. | Approve their own production execution. |
| **Migration reviewer (second person)** | Independently reviews the graph, offline SQL, test evidence, and production runbook; present at execution. | Be the same person as the executor. |
| **Security owner** | Approves G1/G2/G5/G8/G10 remediation and the role model. | Waive a P0 without a written risk acceptance. |
| **QA/test owner** | Owns T1-T14, the isolated target, and the evidence package. | Declare a skipped test a pass. |
| **Database owner** | Owns production inventory, backup/PITR restore, target identity, and DB authorization. | Approve the application merge. |
| **Release manager** | Owns Render configuration, deploy window, auto-deploy control, and rollback coordination. | Approve schema DDL. |
| **Local data owner** | Attests L1 versus L2 and accepts local data loss. | Authorize production work. |
| **Audit/retention owner** | Approves D8 and the retention/archival policy. | Change the migration contract unilaterally. |

---

## 7. Tooling and isolated PostgreSQL test strategy

### 7.1 Revision template (`script.py.mako`)

**[Repository]** `backend/migrations/script.py.mako` is 0 bytes (SHA-256 `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855`). The installed Alembic 1.20.0 generic template is 20 lines (SHA-256 `D38920781B4D31AE1C0A71BC09F41C2ADE8FEAB9E5A087E3F30CB4BBF0C1C9D3`). An empty template makes `alembic revision` produce an unusable file, which is a direct risk for future migrations.

**[Decision D5]** Replace the 0-byte file with the Alembic 1.20.0 generic template or a reviewed project-specific equivalent. The template must contain:

- the `"""${message}"""` docstring;
- `revision: str = ${repr(up_revision)}`;
- `down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}`;
- `branch_labels` and `depends_on`;
- `def upgrade() -> None:` with `pass`;
- `def downgrade() -> None:` with `pass`.

**Acceptance:**

1. In a temporary copy of the migrations directory, run a revision-generation command that does not touch the repository graph.
2. Confirm the generated file imports, compiles, has both functions, and contains the expected revision variables.
3. Confirm no file was created under `backend/migrations/versions/` during the test.
4. Record the template hash in the Batch 25 evidence.

Do not "test" the template by generating a real migration into the repository and deleting it later; that leaves graph state and untracked artifacts.

### 7.2 Safe `env.py` design

**[Repository]** Current `env.py`:

- imports `settings` at line 13;
- sets `sqlalchemy.url` from `settings.database_url` at line 25;
- builds the engine from `settings.database_url` when no explicit connection is supplied at lines 68-75;
- sets `compare_type=True` but not `compare_server_default`;
- relies on an uncommitted `config.attributes["connection"]` path for tests.

**[Decision D4]** The Batch 25 `env.py` must implement this behavior:

1. **No application settings target.** Remove `from app.core.config import settings` and every use of `settings.database_url`. Importing application models for metadata is allowed; importing a settings object that reads `.env` for a target is not.
2. **Explicit connection first.** If `config.attributes.get("connection")` is present, use it. This is the only programmatic/test path. Validate its identity before DDL.
3. **Test mode fails closed.** If `VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS=1` and no connection is present, raise `RuntimeError` before creating an engine. Do not fall back to any URL.
4. **Explicit CLI URL.** Otherwise require `-x db_url=...` or `VERIFYGRID_MIGRATION_DATABASE_URL`. If neither is present, raise a clear error listing the accepted forms.
5. **Identity assertion.** Before DDL, execute:

   ```sql
   SELECT current_database(), current_user, inet_server_addr();
   ```

   Compare the result to the validated target. Abort on any mismatch, including a loopback hostname that resolves to a non-loopback address.
6. **Target policy.** Allow loopback only by default. A non-loopback target requires both:
   - `VERIFYGRID_ALLOW_PRODUCTION_MIGRATION=1`; and
   - `VERIFYGRID_PRODUCTION_MIGRATION_ACK=<change-ticket-id>`.

   These variables are guardrails, not authorization. The two-person production gate in section 9 is still required.
7. **Offline mode.** `--sql` must also require an explicit URL and must not read `.env`.
8. **No implicit engine.** Do not call `engine_from_config` with a URL that came from `alembic.ini`. If `alembic.ini` has no URL, the only engine is the explicit one.
9. **No startup hook.** `backend/app/main.py` and `backend/app/db/session.py` remain unchanged. Migrations are never run at application startup.
10. **Non-connecting commands stay offline.** `alembic heads`, `alembic history`, and `alembic revision` must not require a database target. Target resolution occurs only when a connection or DDL is requested. Graph inspection and revision generation must work with no `.env`, no URL, and no database.

**Illustrative shape (not executed):**

```python
def _explicit_connection():
    connection = config.attributes.get("connection")
    if connection is not None:
        _assert_target_identity(connection)
        return connection

    if os.getenv("VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS") == "1":
        raise RuntimeError("integration mode requires config.attributes['connection']")

    url = context.get_x_argument(as_dictionary=True).get("db_url") \
        or os.getenv("VERIFYGRID_MIGRATION_DATABASE_URL")
    if not url:
        raise RuntimeError("explicit migration target required; .env is not a target source")

    _assert_allowed_target(url)
    engine = create_engine(url, poolclass=pool.NullPool)
    connection = engine.connect()
    _assert_target_identity(connection)
    return connection
```

**Acceptance tests (`backend/tests/test_migration_env_guard.py`):**

- missing target raises before any connection;
- `.env`/`DATABASE_URL` alone raises;
- test mode without a connection raises;
- explicit loopback connection succeeds;
- identity mismatch aborts;
- non-loopback target without both production variables aborts;
- non-loopback target with both variables is allowed by the guard but still requires the human gate;
- `heads`, `history`, and `revision` work without a target or `.env`;
- no `settings.database_url` reference remains in `env.py`.

### 7.3 Isolated PostgreSQL test contract

**[Decision D6]** The only authorized migration test target is a disposable PostgreSQL database on loopback, dedicated to testing.

Required environment:

```powershell
$env:VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS = "1"
$env:VERIFYGRID_TEST_DATABASE_URL = "postgresql+psycopg://verifygrid_test:<local-password>@127.0.0.1:5432/verifygrid_test"
$env:DATABASE_URL = "postgresql+psycopg://verifygrid_app:placeholder@127.0.0.1:5432/verifygrid"
```

Rules:

- `VERIFYGRID_TEST_DATABASE_URL` is mandatory and must pass `backend/tests/pg_test_target.validate_test_database_url`.
- The guard rejects the application database name, `postgres`, `template0`, `template1`, `neondb`, remote hosts, non-loopback resolved addresses, redirect query parameters, and roles not named for testing.
- Alembic receives an already-validated SQLAlchemy connection through `config.attributes["connection"]`.
- Each test creates a unique schema named `verifygrid_it_<hex>`, sets `search_path` to it, and drops it in `finally`.
- No test uses `Base.metadata.create_all` to build the schema under test.
- No test contacts Neon, Render, Cloudflare, or production.
- No test reads a production secret. `DATABASE_URL` is a loopback placeholder used only for the guard's comparison.
- A skipped integration test is **not run**, not passed. CI must fail if an expected integration test is skipped in the integration job.

### 7.4 T1-T14 acceptance matrix

| ID | Scenario | Target batch | Acceptance evidence |
| --- | --- | --- | --- |
| **T1** | Fresh database migration to one head | 25 | Programmatic upgrade to head through the explicit validated connection on an empty isolated schema; one head `0006`; all eight tables; exact columns, nullability, defaults, PKs, FKs, unique constraints, indexes. |
| **T2** | Production-equivalent `0001 -> 0004` then `0005 -> 0006` | 25 | Build to `0004_enterprise_governance`; seed governance/audit data; apply `0005`, then `0006`; all assertions pass. |
| **T3** | Production-scale data preservation | 25 | Synthetic 33-run / 25,654-discrepancy seed; per-table fingerprints before/after; no row loss. |
| **T4** | No duplicate lineage DDL | 25 | Offline SQL from `0004` to `0006` contains two `CREATE TABLE`s, no `ADD COLUMN` for the six lineage columns, no `DROP`. |
| **T5** | Template lifecycle on canonical schema | 26 | CRUD, apply, uniqueness, owner-deletion `SET NULL`, cross-user 404 on the migration-built schema. |
| **T6** | Review single/bulk on canonical schema | 26 | Single and bulk decisions persist; multiple decisions per discrepancy; `RESTRICT` deletion behavior; every column correct. |
| **T7** | Governance sign-off on canonical schema | 26 | Propose/approve/reject; maker-checker separation; header spoofing denied; self-approval denied. |
| **T8** | Audit chain append/verify/tamper | 26 | Append, verify, tamper detection; concurrent sequence test; no duplicate sequence. |
| **T9** | ORM queries and physical fields | 26 | Round-trip all eight tables; `_reason_code`/`_confidence_score`; `NULL_KEY` fallback; relationships. |
| **T10** | Raw-insert defaults | 25/26 | Raw SQL inserts omitting defaults; `role='MAKER'`, `sign_off_status='DRAFT'`, `currency='USD'`, `severity='medium'`, `resolution_status='unresolved'`, `is_bulk_action=false`. |
| **T11** | Empty-table downgrade/upgrade round trip | 25 | Canonical `0006 -> 0004` on empty tables, then upgrade; schema returns to `0006`; `0005`/`0006` do not drop lineage columns; non-empty rollback policy is T12. |
| **T12** | Non-empty rollback policy | 26 | Documented and tested policy: export/forward-fix, not downgrade; non-empty review/audit rows are never dropped. |
| **T13** | Local canonical rebuild | 25 | Throwaway local schema `0001 -> 0006`; compare to the migration-built test schema; no stamp; exact eight tables. |
| **T14** | Render-like startup compatibility | 26 | Selected app starts against the canonical schema; `/health`, `/health/db`, and selected feature routes pass. |

### 7.5 Test layers and CI behavior

| Layer | Runs when | Must never do |
| --- | --- | --- |
| Pure unit tests | Every `pytest` run | Open a database connection. |
| Target-guard tests | Every `pytest` run | Open a database connection. |
| Migration integration tests (T1-T4, T10, T11, T13) | Only with `VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS=1` and a validated loopback target | Fall back to `DATABASE_URL`/`.env`; use `create_all`; contact production. |
| Application integration tests (T5-T9, T12, T14) | Only in the isolated integration job | Use SQLite to assert PostgreSQL schema behavior. |
| Production rehearsal | Batch 27 only | Substitute for isolated tests; run before authorization. |

### 7.6 Abort conditions for any test run

Stop immediately if:

- the guard rejects the test URL, role, or host;
- the connected database/user differs from the validated target;
- `inet_server_addr()` is not loopback;
- the test database contains an unexpected schema or `alembic_version`;
- a test attempts to use `settings.database_url` for DDL;
- a production hostname, Neon endpoint, Render hostname, or non-loopback address appears in any URL;
- a migration emits `ADD COLUMN` for any of the six lineage columns or a `DROP`;
- a test expects a skipped result to count as success.

### 7.7 What the tests cannot prove

A green isolated suite cannot prove:

- that production data values, permissions, or extensions match the synthetic seed;
- that Render has no hidden pre-deploy command or auto-deploy race;
- that the selected application version is the right product decision;
- that the production audit chain is currently valid;
- that concurrent production writes will not contend with DDL locks;
- that the reconstructed `0006` matches a lost historical artifact;
- that production has no unknown object that collides with `0005` or `0006`.

Those remain Batch 27 production gates.

---

## 8. Local development database disposition

### 8.1 Current state - bounded, not verified

**[Repository + Inference + Not verified]** The local development database was **not** queried in Batch 24. Its exact `alembic_version` is unknown. The evidence bounds it:

- `0004_verification_templates.py` records that Batch 12 applied it to the local `verifygrid` database from `0003_user_password`.
- `0005_verification_lineage.py` exists in the working tree and may have been applied afterward.
- The local graph therefore ends at either `0004_verification_templates` or `0005_verification_lineage`.
- Both states lack `0004_enterprise_governance`; both contain `verification_templates`; the `0005` state also has the six lineage columns.
- Neither state can be upgraded through the canonical graph. Canonical `0005` would collide with the existing `verification_templates` table.

The exact revision must be read in a future authorized batch with a read-only `SELECT version_num FROM alembic_version;`. Batch 24 does not connect.

### 8.2 Disposition options

| Option | When to use | Procedure | Risks |
| --- | --- | --- | --- |
| **L1 - Disposable rebuild** | Local data has no lasting value; it is development/test data. | Stop the backend; record row counts for reference; drop and recreate the local database; run the canonical graph to `0006`; recreate the development user; smoke test. | Local data loss. Must be an explicit owner decision. No production impact. |
| **L2 - Export, rebuild, reload** | Local templates, projects, or verification history must be preserved. | Read-only export of application tables; rebuild from the canonical graph; reload in FK order; verify counts and fingerprints; smoke test. | Export/reload bugs, timezone/JSON fidelity, missed columns. Requires a dry run on a throwaway database. |
| **L3 - Stamp** | Never. | None. | False history and schema/data mismatch. **Rejected.** |

### 8.3 Decision

**[Decision D7]** The default disposition is **L1 - disposable rebuild**. The local data owner must attest in writing that the local data is disposable before L1 is executed. If the owner cannot attest, the disposition is **L2**, not L1 and not a stamp.

The default is a decision, not an assumption. The memo does not assert that the local data is worthless; it asserts that the project will not preserve it silently. The owner's choice and attestation are recorded in the approval block (section 14) and in the Batch 25 evidence.

### 8.4 L1 procedure

1. Confirm the target is the local development database and not a cloud endpoint. Record `current_database()`, `current_user`, and `inet_server_addr()` from a local read-only session.
2. Stop the backend and any process holding a connection.
3. Record row counts for `users`, `projects`, `source_files`, `verification_runs`, `verification_discrepancies`, and `verification_templates` for the record. This is not a backup; it is evidence of what was discarded.
4. Drop and recreate the local database with an explicit local administrator command.
5. Run the canonical graph from an empty database to `0006_discrepancy_review_decisions`, using the hardened `env.py` and an explicit local URL.
6. Recreate the development user through the application registration path. The user receives `MAKER`; do not insert a privileged role manually.
7. Run `/health` (non-database) and `/health/db`; run a read-only project/template smoke test.
8. Verify exactly one `alembic_version` row at `0006` and exactly the eight expected tables.
9. Record the commands, counts discarded, final counts, and revision in the Batch 25 evidence.

### 8.5 L2 procedure and constraints

L2 is allowed only with a written owner attestation that specific local data must be preserved. It must be rehearsed on a throwaway database before the real local rebuild.

**Export:**

- Export only application tables: `users`, `projects`, `source_files`, `verification_runs`, `verification_discrepancies`, `verification_templates`.
- Do **not** export `alembic_version`.
- Do not export schema DDL; the canonical graph creates the schema.
- Preserve UUID primary keys and JSON values exactly.
- Export timestamps in UTC; target columns are `timestamptz`.
- Record per-table row counts and a deterministic fingerprint, for example `md5(string_agg(row_to_json(t)::text, '' ORDER BY id))`.
- Hash the export files and store the hashes with the evidence.

**Rebuild:**

- Create an empty local database.
- Run the canonical graph to `0006` with an explicit local URL.
- Do not use `Base.metadata.create_all`.

**Reload:**

- Reload in dependency order: `users` -> `projects` -> `source_files` -> `verification_runs` -> `verification_discrepancies` -> `verification_templates`.
- `verification_templates.owner_id` depends on `users`.
- Do not invent non-null governance values for columns added by `0004`. New `users.role` values must be explicit; if the export has no role, assign `MAKER` only after confirming the user is not intended to be an admin. New sign-off, materiality, clustering, and review fields must be `NULL` or their documented defaults, not fabricated.
- If the local database is at `0005_verification_lineage`, preserve the six lineage JSON values exactly. If it is at `0004_verification_templates`, those columns do not exist locally; the canonical `0004` adds them as `NULL`. Do not fabricate lineage values.

**Verify:**

- Compare per-table row counts and fingerprints to the export.
- Verify exactly one `alembic_version` row at `0006`.
- Verify the eight tables and the exact `0005`/`0006` object inventory.
- Run `/health`, `/health/db`, and a read-only template/project smoke test.
- Record any intentional normalization or rejected row.

### 8.6 Local verification queries

After either L1 or L2, run these read-only checks through the authorized local session:

```sql
SELECT version_num FROM alembic_version;
-- expected exactly one row: 0006_discrepancy_review_decisions

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'users','projects','source_files','verification_runs',
    'verification_discrepancies','verification_templates',
    'audit_events','discrepancy_review_decisions'
  )
ORDER BY table_name;
-- expected eight rows
```

Then run the application's non-database health check and a read-only template/project smoke test. Do not create review decisions or sign-offs in a local smoke test unless the database is disposable.

### 8.7 What is explicitly prohibited

- `alembic stamp` on the local database.
- `alembic upgrade head` against the retired local graph.
- Editing `alembic_version` by hand.
- Copying a production dump into the local database.
- Dropping the local database without the owner attestation.
- Treating the local rebuild as a production rehearsal.

---

## 9. Stage gates, execution sequence, and accountability

### 9.1 Stage model

| Stage | Batch | Scope | Authorized by | Exit artifact |
| --- | --- | --- | --- | --- |
| **0** | Batch 24 | Decision memo and owner nomination. | Engineering lead, security owner, database owner, migration owner/reviewer. | Signed approval block; named owners; local data disposition. |
| **1** | Batch 25 | Offline migration/tooling implementation only: canonical graph, recovered `0004`, `0005`, `0006`, retirement archive, `script.py.mako`, `env.py`, `alembic.ini`, migration-only tests. | Stage 0 approval. | Single-head graph; offline SQL evidence; template-generation evidence; guard tests; T1-T4/T10/T11/T13 pass; no app code changed. |
| **2** | Batch 26 | Option B/D application merge, P0 remediation, ORM reconciliation, ported tests, T5-T9/T12/T14. | Stage 1 exit. | Merged app; P0 tests pass; full isolated suite passes; app smoke on canonical schema; no production touched. |
| **3** | Batch 27 | Production read-only inventory, backup/PITR restore proof, Render review, Neon-branch/isolated rehearsal, rollback rehearsal. | Stage 2 exit. | Production authorization package; two-person approval; rehearsal evidence. |
| **4** | Batch 28 | Production `0005`, then `0006`, then deploy the merged app. | Stage 3 exit and a separate written production authorization. | Production revision `0006`; preserved counts; smoke pass; deployment record. |
| **5** | Batch 29 | Post-deployment verification and hypercare. | Stage 4 completion. | 24-72 hour verification report; audit-chain status; final counts; unfreeze record. |

### 9.2 Stage 0 - Decision approval gate

**Entry:** This memo is complete and reviewed.

**Required approvals:**

- Engineering lead accepts D1-D10 and the Batch 25 scope.
- Security owner accepts the P0 remediation design in section 5 and the D8 retention decision.
- Database owner accepts the production evidence and backup/recovery gates in Stage 3.
- Migration owner and independent migration reviewer accept the canonical graph and retirement mechanics.
- Local data owner records L1 or L2 in the approval block.

**Exit criteria:**

- All approval lines in section 14 are signed with a date.
- The local DB disposition is recorded as L1 or L2.
- The Batch 25 executor and reviewer are named.
- No unresolved P0 design objection remains.

**No-go:** Any missing signature; any request to skip the security fixes or the canonical graph; any request to authorize production in this stage.

### 9.3 Stage 1 - Batch 25 offline migration/tooling gate

**Entry criteria:**

- Stage 0 exit.
- The Batch 25 change set is limited to the files in section 10.
- The operator confirms no production credential is present in the shell.
- The isolated PostgreSQL target is disposable and loopback-only.

**Exit criteria (all required):**

1. Recovered `0004_enterprise_governance_and_materiality.py` is in the repository, byte-identical, SHA-256 `44D31AE9...` verified.
2. `0005_verification_templates.py` and `0006_discrepancy_review_decisions.py` exist with the contracts in section 6.
3. `0004_verification_templates.py` and `0005_verification_lineage.py` are removed from `backend/migrations/versions/` and archived under `backend/migrations/retired/` with hashes recorded.
4. `alembic heads` reports exactly one head: `0006_discrepancy_review_decisions`.
5. Offline SQL from `0004` to `0006` contains two `CREATE TABLE`s, no lineage `ADD COLUMN`, and no `DROP`.
6. `script.py.mako` is restored and a throwaway generation succeeds without creating a repository revision.
7. `env.py` has no `settings.database_url` path; `alembic.ini` has no usable URL; the guard tests pass.
8. T1-T4, T10, T11, and T13 pass on the isolated target against the Alembic-built schema.
9. No application model/schema/service/endpoint file changed.
10. No untracked migration artifact remains.
11. The local database is rebuilt under L1 or L2 and verified at `0006`, if the owner authorized the local action in this batch. If not, the local action is explicitly deferred to Batch 26 with the disposition recorded.
12. The Batch 25 evidence package records commands, hashes, test output, and the single-head proof.

**No-go:**

- Any duplicate revision ID, second head, or non-linear parent.
- Any edit to the recovered `0004` operations.
- Any `ADD COLUMN`/`DROP` for the six lineage columns in offline SQL.
- Any test that silently skips or falls back to an application URL.
- Any app-code change smuggled into Batch 25.
- Any use of `create_all` for the schema under test.
- Any local stamp.

### 9.4 Stage 2 - Batch 26 application merge and P0 gate

**Entry criteria:**

- Stage 1 exit.
- A written Batch 26 file-level merge plan exists, naming every file from section 10.2 and the owner of each merge conflict.
- The current branch's pre-merge tests are recorded as a baseline.
- The security owner has reviewed the G1/G2 target design.

**Exit criteria (all required):**

1. Option B merged application exists; if B is abandoned, a written D-trigger decision exists and D follows the same gates.
2. G1 and G2 regression tests pass; no public role field and no `X-User-Role` authority path remains.
3. G5-G10 and G12 P1 items are closed with the evidence in section 5.6.
4. The reconciled ORM includes all eight tables, `users.role`, the nine sign-off fields, the 17 materiality/clustering/review fields, physical `_reason_code`/`_confidence_score` mappings, `AuditEvent`, and `DiscrepancyReviewDecision` with `RESTRICT` FKs.
5. The parity test uses `EXPECTED_HEAD = 0006_discrepancy_review_decisions` and the selected ORM; `compare_metadata` does not report unexplained drift.
6. T5-T9, T12, and T14 pass on the canonical schema.
7. The current Batch 2-14 tests still pass; ported governance/review/audit/materiality/clustering/export tests pass.
8. The application starts against the canonical schema; `/health`, `/health/db`, and the selected feature routes pass.
9. No production, Neon, Render, or Cloudflare action occurred.
10. The Batch 26 evidence package records the merged file list, test output, and any accepted residual risk.

**No-go:**

- Any P0 regression test failing.
- Any governance route still trusting a client role.
- Any wholesale copy that regresses current Batch 4 behavior or deployed governance behavior.
- Any missing review table or missing template table in the selected app's smoke path.
- Any `compare_metadata` drift dismissed without a written contract decision.
- Any attempt to deploy from Batch 26.

### 9.5 Stage 3 - Batch 27 production evidence and rehearsal gate

**Entry criteria:**

- Stage 2 exit.
- Written production change ticket and proposed window.
- Named database owner, migration executor, independent reviewer, security owner, and release manager.
- Render auto-deploy control plan.

**Required evidence:**

1. **Read-only inventory:** exactly one `alembic_version` row at `0004_enterprise_governance`; 33 runs; 25,654 discrepancies; both new tables absent; governance columns and audit table present; exact types/defaults/indexes checked against the approved contract; audit-chain verification result recorded (valid, or pre-existing failure documented with cause).
2. **Backup/PITR:** a backup exists; a restore to a separate branch/database has been performed and smoke-queried; the restore timestamp and RPO/RTO are recorded; the restore is not merely "PITR is enabled."
3. **Render review:** build command, start command, pre-deploy command (or none), health check, auto-deploy setting, and environment-variable names (values not reproduced) are recorded. Auto-deploy is disabled or coordinated for the window.
4. **Neon-branch or isolated-restore rehearsal:** apply `0005`, verify; apply `0006`, verify; start the Batch 26 build; run `/health`, `/health/db`, template smoke, review smoke, governance smoke, and audit-chain verification. Row counts and fingerprints match the preflight.
5. **Rollback rehearsal:** the restore-to-separate-branch procedure is timed and documented; the decision tree in section 9.8 is walked through.
6. **Two-person review:** executor and reviewer sign the SQL, inventory diff, test output, and rollback plan.

**Exit criteria:**

- A production authorization package contains all six evidence items, the exact migration commands, the exact app image/commit, the window, the abort conditions, and the rollback decision tree.
- The engineering lead and database owner sign the production authorization separately from this memo.
- No P0 or P1 item is open.

**No-go:**

- Revision/count/object mismatch.
- No verified restore.
- Audit chain broken with unknown cause.
- Render auto-deploy cannot be controlled.
- Rehearsal failure.
- Missing two-person approval.
- Production target identity cannot be proven.

### 9.6 Stage 4 - Batch 28 production execution gate

**Pre-flight (all required):**

1. Confirm the production target identity with `current_database()`, `current_user`, and `inet_server_addr()`. The operator reads the values aloud/records them; they must match the authorized target.
2. Confirm exactly one `alembic_version` row at `0004_enterprise_governance`.
3. Confirm `verification_templates` and `discrepancy_review_decisions` are still absent.
4. Confirm the pre-migration backup/restore point and the tested restore path.
5. Disable or coordinate Render auto-deploy.
6. Set `PGOPTIONS="-c lock_timeout=5000"` for the migration session.
7. Confirm no long-running transaction or conflicting deploy.
8. Confirm the executor and reviewer are both present.

**Execution:**

| Step | Action | Verification | Abort condition |
| --- | --- | --- | --- |
| 1 | Apply `0005_verification_templates` from an explicit one-off job. | `alembic current` is `0005`; table, unique constraint, FK, and index exist; row counts unchanged. | Lock timeout, object mismatch, count change. |
| 2 | Apply `0006_discrepancy_review_decisions`. | `alembic current` is `0006`; table, two `RESTRICT` FKs, and four indexes exist; row counts unchanged. | Same. |
| 3 | Deploy the Batch 26 build. | App starts; `/health`, `/health/db`, template smoke, review smoke, governance smoke, audit chain pass. | Startup or smoke failure. |
| 4 | Post-deploy verification and unfreeze. | Section 9.7 checks; final revision and counts recorded. | Any unexpected result. |

**Command shape (only after Stage 3 exit and with the secret supplied for this process only):**

```powershell
# The migration target is explicit and is NOT read from .env or DATABASE_URL.
$env:VERIFYGRID_MIGRATION_DATABASE_URL = "<explicit-production-connection-string>"
$env:VERIFYGRID_ALLOW_PRODUCTION_MIGRATION = "1"
$env:VERIFYGRID_PRODUCTION_MIGRATION_ACK = "<approved-change-ticket-id>"
$env:PGOPTIONS = "-c lock_timeout=5000"
cd backend

alembic current
alembic upgrade 0005_verification_templates
alembic current
alembic upgrade 0006_discrepancy_review_decisions
alembic current
```

Do not use `alembic upgrade head` on production. Do not paste credentials into this memo, logs, or chat.

### 9.7 Stage 5 - Batch 29 post-deployment verification and hypercare

**Required checks:**

- `alembic_version` remains exactly one row at `0006`.
- Row counts for the pre-existing tables match the preflight within the approved transaction/write window; new tables have expected counts.
- Audit chain verifies; any new event sequence is monotonic.
- Template create/read/update/delete/apply works for an authorized user; cross-user access returns 404.
- Review single and bulk decisions work; deletion attempts with review rows return 409.
- Governance propose/approve/reject works; a `MAKER` cannot approve; `X-User-Role` has no effect.
- No unexplained 500s or `DataError`s in logs.
- Render deployment is stable; no restart loop.
- The change ticket is closed with final revision, counts, timestamps, and approvers.

**Hypercare window:** at least 24 hours, ideally 72 hours, with a named on-call owner.

**No-go for unfreeze:** any `alembic_version` mismatch, audit-chain failure, unexplained data loss, P0 security finding, repeated 500/`DataError`, or Render restart loop. Keep the change ticket open, preserve evidence, and escalate to the rollback/restore decision tree in section 9.8.

### 9.8 Rollback and recovery rules

- **Application failure before any schema change:** roll back the application; no schema action.
- **`0005` failure:** PostgreSQL DDL is transactional; investigate and retry only after the cause is known. Do not stamp.
- **`0005` success, `0006` failure:** keep `0005`; it is additive and the old app ignores it. Fix forward.
- **`0006` success, application failure:** roll back the application; keep both new tables. Do not drop non-empty tables.
- **Template table empty and an approved undo is required:** targeted drop only after verifying zero rows and a fresh backup.
- **Review table non-empty:** treat as audit evidence; forward-fix or restore, never drop.
- **Governance data damaged:** restore to a separate branch; never downgrade `0004` on production.
- **Audit chain failure:** stop writes, preserve the chain, restore to a separate branch, and investigate before any further DDL.
- Do not use `Base.metadata.drop_all`/`create_all` against production; do not delete `alembic_version` rows.

### 9.9 Accountability and the two-person rule

| Gate | Accountable | Consulted | Informed |
| --- | --- | --- | --- |
| D1/D9 strategy and stage transitions | Engineering lead | Security owner, migration owner, product owner | Release manager |
| D2/D8 graph and retention | Migration owner | Audit/retention owner, database owner | Engineering lead |
| D3 P0 security | Security owner | Application owner, migration reviewer | Engineering lead |
| D4/D5/D6 tooling and tests | Platform/test owner | Migration owner, security owner | Release manager |
| D7 local disposition | Local data owner | Migration owner | Engineering lead |
| Production inventory/backup | Database owner | Migration owner, release manager | Engineering lead |
| Production execution | Migration executor | Independent reviewer, database owner | Release manager, security owner |
| Deployment/rollback | Release manager | Database owner, migration executor | Engineering lead |

**Two-person rule:** the production migration executor and the independent reviewer must be different people. Both must be present for the DDL and the deployment. The database owner and engineering lead must both sign the production authorization. No shared credentials; no single-person break-glass without a post-hoc review.

### 9.10 Global no-go triggers

Stop immediately if any of the following is true:

- `alembic_version` is not exactly one row at `0004_enterprise_governance` at preflight.
- `verification_templates` or `discrepancy_review_decisions` already exists in production.
- Any governance object, six-lineage column, type, default, index, or FK differs from the approved contract.
- The canonical graph still has two heads or contains `0005_verification_lineage`.
- Offline SQL shows duplicate `ADD COLUMN`/`DROP` for the six lineage columns.
- The recovered governance file hash differs from `44D31AE9...`.
- The application decision is unresolved or the selected build is not the approved Batch 26 build.
- The selected application lacks the governance port and is intended to replace `58a0e5c`.
- Backup/PITR is unavailable or untested.
- Render auto-deploy cannot be controlled.
- The review-table contract is ambiguous or conflicts with new evidence.
- The audit chain is broken and the cause is unknown.
- Any isolated or rehearsal test fails.
- Two-person approval is missing.
- The production target identity cannot be verified.
- A P0 security regression test fails.

### 9.11 What this memo authorizes

This memo authorizes **only** the decision record and, after Stage 0 signatures, entry into the Batch 25 offline scope. It authorizes **no** production migration, no production deployment, no Neon/Render/Cloudflare change, no database connection, and no application deployment. Stage 4 requires a **separate written production authorization** after Stage 3.

---

## 10. First implementation batch - Batch 25 scope and acceptance

### 10.1 Objective

**[Decision D9]** Batch 25 implements the **offline migration graph and migration tooling only**. It does not merge the application, does not fix application P0 code, and does not touch production.

### 10.2 Exact Batch 25 file manifest

**Add:**

| File | Requirement |
| --- | --- |
| `backend/migrations/versions/0004_enterprise_governance_and_materiality.py` | Byte-identical copy of the preserved deployed file; revision `0004_enterprise_governance`; parent `0003_user_password`; SHA-256 `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB`. |
| `backend/migrations/versions/0005_verification_templates.py` | Revision `0005_verification_templates`; parent `0004_enterprise_governance`; 10-column contract; owner FK `SET NULL`; unique `(owner_id, name)`; owner index. |
| `backend/migrations/versions/0006_discrepancy_review_decisions.py` | Revision `0006_discrepancy_review_decisions`; parent `0005_verification_templates`; 12-column contract; two `RESTRICT` FKs; four indexes; `is_bulk_action` server default `false`. |
| `backend/migrations/retired/0004_verification_templates.py` | Archived copy of the retired local revision; hash recorded. |
| `backend/migrations/retired/0005_verification_lineage.py` | Archived copy of the retired local revision; hash recorded. |
| `docs/audits/Batch24_Migration_Provenance.md` | Provenance note: source commit, source path, recovered `0004` SHA-256, archived local revision hashes, retrieval date, and the retirement decision. Does not edit Batches 18-23. |
| `backend/tests/test_migration_env_guard.py` | Unit tests for the explicit-target and fail-closed behavior in section 7.2. |
| `backend/tests/test_postgres_reconciliation_design.py` | Migration-only tests: graph shape, exact `0005`/`0006` inventory, offline SQL, T1-T4, T10, T11, T13. Application tests are added in Batch 26. |

**Edit:**

| File | Requirement |
| --- | --- |
| `backend/migrations/script.py.mako` | Replace 0 bytes with the Alembic 1.20.0 generic template or reviewed equivalent; 20 lines; hash `D3892078...` if generic. |
| `backend/migrations/env.py` | Remove `settings.database_url`; add explicit connection/URL resolver, test-mode fail-closed guard, identity assertion, and production acknowledgement. |
| `backend/alembic.ini` | Remove the usable `sqlalchemy.url`; no credential or production URL. |
| `backend/tests/test_alembic_migration_parity.py` | Set `PREVIOUS_HEAD = "0004_enterprise_governance"` for the production-equivalent path and `EXPECTED_HEAD = "0006_discrepancy_review_decisions"`; update the ORM contract only to the extent Batch 25 can do so without app code (migration introspection, not the merged ORM). |
| `backend/tests/test_postgres_migration_application.py` | Set `EXPECTED_HEAD = "0006_discrepancy_review_decisions"`; update only the constant in Batch 25. The application assertions remain Batch 26 work and are explicitly excluded from the Batch 25 gate; they are not claimed green against the unmerged ORM. |

**Delete from the active graph (after archiving):**

| File | Requirement |
| --- | --- |
| `backend/migrations/versions/0004_verification_templates.py` | Remove from `versions/`; the archived copy remains. |
| `backend/migrations/versions/0005_verification_lineage.py` | Remove from `versions/`; the archived copy remains. |

**No other file may change in Batch 25.**

### 10.3 Task order

1. Create `backend/migrations/retired/` and archive the two local revisions; record hashes.
2. Remove the two originals from `backend/migrations/versions/`.
3. Copy the recovered `0004_enterprise_governance_and_materiality.py` byte-identically; verify the hash.
4. Create `0005_verification_templates.py` from the current template DDL, changing only revision metadata and docstring.
5. Create `0006_discrepancy_review_decisions.py` from the approved 12-column contract, with `RESTRICT` FKs and `is_bulk_action` server default `false`.
6. Repair `script.py.mako`; verify by throwaway generation in a temp directory.
7. Harden `env.py` and `alembic.ini`; add `test_migration_env_guard.py`.
8. Update the parity/application test head constants; add the migration-only reconciliation tests.
9. Run static graph checks and offline SQL generation (no database connection).
10. Run the isolated PostgreSQL tests T1-T4, T10, T11, T13 on the disposable loopback target.
11. If the local data owner authorized it, rebuild the local database under L1 or L2 and verify `0006`. Otherwise record the deferral.
12. Commit the change set and produce the Batch 25 evidence package.

### 10.4 Batch 25 acceptance criteria

Batch 25 is **GO** only when all of the following are true:

- [ ] The active versions directory contains exactly `0001`, `0002`, `0003`, the recovered `0004`, `0005_verification_templates`, and `0006_discrepancy_review_decisions`.
- [ ] `alembic heads` returns exactly one head: `0006_discrepancy_review_decisions`.
- [ ] No file in the active graph declares `revision = "0005_verification_lineage"` or `down_revision = "0004_verification_templates"`.
- [ ] Recovered `0004` SHA-256 is `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB`.
- [ ] Offline SQL from `0004` to `0006` contains exactly two `CREATE TABLE` statements and no `ADD COLUMN`/`DROP` for the six lineage columns.
- [ ] `0005` has exactly 10 columns, the owner FK `SET NULL`, the unique `(owner_id, name)`, and the owner index.
- [ ] `0006` has exactly 12 columns, two `RESTRICT` FKs, four indexes, and `is_bulk_action` server default `false`.
- [ ] `script.py.mako` generation in a temp directory produces a valid revision; no repository revision was created.
- [ ] `env.py` contains no `settings.database_url`; a missing target fails before connecting; test mode without a connection fails; an identity mismatch aborts.
- [ ] `alembic.ini` contains no usable URL.
- [ ] T1-T4, T10, T11, and T13 pass on the isolated target; no test skipped silently.
- [ ] No application model/schema/service/endpoint file changed.
- [ ] No untracked migration artifact remains.
- [ ] The local DB is rebuilt and at `0006`, or the deferral and owner disposition are recorded.
- [ ] The evidence package contains commands, hashes, test output, graph proof, and offline SQL.

Batch 25's automated gate is limited to the migration-only modules. `test_postgres_migration_application.py` is updated but its application assertions are Batch 26 work; a green application suite is not a Batch 25 criterion and must not be claimed.

### 10.5 Illustrative Batch 25 verification commands (not executed)

These are the shapes to run in the future authorized batch. They are not executed here.

```powershell
cd C:\Users\shaha\verifygrid\backend

# 1. Static graph and offline SQL. No database connection.
alembic heads
alembic history --verbose
alembic -x db_url="<explicit-local-url>" upgrade 0004_enterprise_governance:0006_discrepancy_review_decisions --sql > ..\batch25_offline.sql

# 2. Guard unit tests. No database connection.
python -m pytest tests/test_migration_env_guard.py -q

# 3. Isolated PostgreSQL migration tests. Explicit loopback target only.
python -m pytest tests/test_alembic_migration_parity.py -q
python -m pytest tests/test_postgres_reconciliation_design.py -q
```

The offline SQL must be inspected, not merely generated. The test run must use the target-guard variables from section 7.3. Do not run `alembic upgrade` against a real database outside the isolated test fixture.

### 10.6 Batch 25 stop conditions

- The recovered file hash differs.
- A second head appears.
- The static graph contains the retired revision.
- Offline SQL emits duplicate lineage DDL.
- A test falls back to `settings.database_url` or `.env`.
- The local database is stamped.
- An application file changes.
- The isolated target is not loopback.
- A test skips and the runner treats it as pass.

### 10.7 Explicitly out of scope for Batch 25

- Application model/schema/service/endpoint changes.
- P0 G1/G2 code fixes.
- Porting governance/review/audit/materiality/clustering/recipe code.
- Production inventory, backup, Render, Neon, Cloudflare, or deployment.
- Production migration.
- Changes to `backend/app/main.py` or `backend/app/db/session.py`.

---

## 11. Batch 26 application merge and P0 file manifest

### 11.1 Exact application files

**Models:**

| File | Change |
| --- | --- |
| `backend/app/models/user.py` | Add `role` (`String(50)`, non-null, server/client default `MAKER`). |
| `backend/app/models/verification_run.py` | Add 9 sign-off fields and 2 user FKs; add 17 materiality/clustering/review fields; map `_reason_code`/`_confidence_score` with setters; add `DiscrepancyReviewDecision` with `RESTRICT` FKs and the review relationship; preserve current `source_row_index`/`target_row_index` and the `NULL_KEY` fallback. |
| `backend/app/models/audit_log.py` | Replace 0 bytes with `AuditEvent` (14 columns). |
| `backend/app/models/review.py` | Remove the 0-byte placeholder or make it a re-export of `DiscrepancyReviewDecision`; do not leave two model definitions. |
| `backend/app/models/__init__.py` | Export `AuditEvent`, `DiscrepancyReviewDecision`, and `VerificationTemplate`; keep the existing exports. |

**Schemas:**

| File | Change |
| --- | --- |
| `backend/app/schemas/auth.py` | Remove `role` from `UserRegisterRequest`; add read-only `role` to `UserResponse`. |
| `backend/app/schemas/review.py` | Replace 0 bytes with review schemas; add `max_length` bounds; normalize decision/justification. |
| `backend/app/schemas/audit.py` | Add audit schemas. |
| `backend/app/schemas/governance.py` | Add governance schemas. |
| `backend/app/schemas/result.py` | Merge materiality/side-by-side fields without dropping current Batch 4 fields. |
| `backend/app/schemas/recipe.py` | Add if recipes are in scope; see section 11.4. |

**Services:**

| File | Change |
| --- | --- |
| `backend/app/services/review_service.py` | Replace 0 bytes with the deployed implementation; add length validation; enforce `RESTRICT`-aware deletion behavior; audit the decision. |
| `backend/app/services/audit_service.py` | Replace 0 bytes with the deployed hash-chain implementation; add transaction-scoped serialization for sequence allocation; retain tamper verification. |
| `backend/app/services/clustering_service.py` | Add; truncate `cluster_name` to 255 deterministically. |
| `backend/app/services/materiality_engine.py` | Add. |
| `backend/app/services/governance_service.py` | Add; remove `X-User-Role`; accept only the authoritative role; enforce maker-checker. |
| `backend/app/services/recipe_service.py` | Add if recipes are in scope. |
| `backend/app/services/verification_engine.py` | Merge, do not overwrite: add governance/materiality/clustering writes and physical reason/confidence writes while retaining Batch 4 behavior. |
| `backend/app/services/project_service.py` | Preserve role-aware behavior; add delete guards for audit/review evidence. |
| `backend/app/services/export_service.py` | Merge deployed materiality/recipe export behavior if in scope; retain current Batch 4 export behavior. |
| `backend/app/services/profiling_service.py` | Merge only if the file-level diff shows deployed-only behavior; retain current profiling. |
| `backend/app/services/preprocessing.py` | Merge only if the file-level diff shows deployed-only behavior; retain current preprocessing. |

**API:**

| File | Change |
| --- | --- |
| `backend/app/api/deps.py` | Add `require_roles(...)` / `require_admin`; load `current_user.role`; fail closed on missing/unknown role. |
| `backend/app/core/security.py` | Add role constants, normalization, and validation helpers. |
| `backend/app/core/config.py` | Refuse to start in production with the default JWT secret. |
| `backend/app/api/v1/endpoints/audit.py` | Replace 0 bytes with audit routes. |
| `backend/app/api/v1/endpoints/review.py` | Add the deployed review routes under the singular module name; retire the empty `reviews.py` or keep one consistent module. |
| `backend/app/api/v1/endpoints/governance.py` | Add governance routes; remove `X-User-Role` from every signature. |
| `backend/app/api/v1/endpoints/recipes.py` | Add if recipes are in scope. |
| `backend/app/api/v1/endpoints/auth.py` | Set `role="MAKER"` on registration; add admin-only elevation; return role read-only. |
| `backend/app/api/v1/endpoints/verification.py` | Merge governance/materiality response behavior; retain Batch 4 behavior. |
| `backend/app/api/v1/endpoints/exports.py` | Merge materiality/recipe export behavior if in scope. |
| `backend/app/api/v1/endpoints/projects.py` | Add delete guards for projects/runs with audit/review evidence. |
| `backend/app/api/v1/router.py` | Register audit, review, governance, and recipe routers; do not leave a dead `reviews.py` import. |

**Tests:**

| File | Change |
| --- | --- |
| `backend/tests/test_alembic_migration_parity.py` | Canonical head and reconciled ORM; `compare_metadata` clean or documented. |
| `backend/tests/test_postgres_migration_application.py` | Canonical head; template/review/governance assertions on the migration-built schema. |
| `backend/tests/test_postgres_reconciliation_design.py` | Extend with T5-T9, T12, T14 application coverage. |
| `backend/tests/test_auth_role_security.py` | G1 regressions. |
| `backend/tests/test_governance_role_security.py` | G2 regressions and maker-checker. |
| `backend/tests/test_review_retention.py` | `RESTRICT` FKs; 409 delete guards; audit retention. |
| `backend/tests/test_audit_concurrency.py` | Sequence serialization and chain verification. |
| `backend/tests/test_review_lengths.py` | G5 bounds; 422 not 500. |
| `backend/tests/test_governance_audit.py` | Ported deployed governance/audit tests, adapted to the merged app and migration-built schema. |
| `backend/tests/test_exception_clustering.py` | Ported deployed clustering/review tests. |
| `backend/tests/test_results_materiality.py` | Ported deployed materiality tests. |
| `backend/tests/test_exports_recipes.py` | Ported deployed export/recipe tests if recipes are in scope. |

### 11.2 P0-specific files

The P0 changes are concentrated in:

- `backend/app/schemas/auth.py`
- `backend/app/api/v1/endpoints/auth.py`
- `backend/app/api/v1/endpoints/governance.py`
- `backend/app/services/governance_service.py`
- `backend/app/api/deps.py`
- `backend/app/core/security.py`
- `backend/app/core/config.py`
- `backend/app/models/user.py`
- `backend/tests/test_auth_role_security.py`
- `backend/tests/test_governance_role_security.py`

No P0 fix is deferred to a later batch. If any of these files cannot be merged in Batch 26, Batch 26 does not exit.

### 11.3 Merge order and conflict rules

1. **Models and metadata first.** Add `role`, sign-off, materiality/clustering/review fields, `AuditEvent`, and `DiscrepancyReviewDecision`. Do not change existing column semantics.
2. **Schemas second.** Add role read-only, review bounds, governance/audit schemas, and materiality result fields.
3. **Services third.** Port governance/review/audit/materiality/clustering; harden the audit sequence; remove header authority; add delete guards.
4. **API fourth.** Add routes and dependencies; register routers; update auth.
5. **Tests fifth.** Port and adapt; add P0 regressions; run both suites.
6. **Engine/export merge last.** These are the highest-conflict files. Merge against tests, not by copy.

Conflict rules:

- Current Batch 4 behavior wins for current-only features unless the deployed behavior is a deliberate governance requirement.
- Deployed governance behavior wins for governance/audit/sign-off/review, subject to D3 and D8.
- Shared functions require tests for both behaviors before the conflict is resolved.
- No wholesale file copy. Every conflict is recorded in the Batch 26 evidence.
- If a conflict cannot be resolved without regressing either side, invoke the D contingency in section 4.5.

### 11.4 Review and recipe scope

**[Decision]** Review is **in scope** for Batch 26. The deployed application exposes review routes, the deployed service inserts into `discrepancy_review_decisions`, and production is reported to lack the table. `0006` fixes a production defect; leaving review out would preserve a broken deployed feature and leave the new table unused.

Recipes are **in scope only if the product owner confirms they are a supported deployed feature**. The deployed router and export service reference recipes, so dropping them silently would be a regression. If the product owner explicitly excludes recipes, Batch 26 must remove the recipe router/service/schema from the merged build in a written scope decision and adjust the ported tests; it must not leave dead routes or imports. The default is to include recipes because they are part of the deployed feature set.

### 11.5 Explicitly unchanged in Batch 26

- `backend/app/main.py` - no startup migration hook.
- `backend/app/db/session.py` - no `create_all`, no migration execution.
- `backend/alembic.ini` - already hardened in Batch 25; no production URL.
- No `backend/.env` edit, Render/Cloudflare configuration edit, or production secret.
- No existing Batch 18-23 report edit.
- No production migration or deployment.

---

## 12. Risks, residual risk, and mitigations

| Risk | Likelihood | Impact | Mitigation | Gate |
| --- | --- | --- | --- | --- |
| Option B merge regresses Batch 4 or governance behavior. | High | High | File-by-file merge; preserve both test suites; contract tests for engine/result/export; D contingency if irreconcilable. | Batch 26 exit |
| P0 authorization flaw is reintroduced during the port. | Medium | Critical | G1/G2 regression tests; code search for role fields/header; security owner sign-off. | Batch 26 exit |
| Recovered `0004` is edited or tampered with. | Low | Critical | Byte-identical copy; SHA-256 before/after; no reformat; provenance note. | Batch 25 exit |
| Local data is lost under L1 without a real owner decision. | Medium | Medium | Written L1 attestation; L2 option; row-count record; no silent drop. | Stage 0 / Batch 25 |
| Audit sequence collides under concurrency. | Medium | High | Advisory-lock serialization; concurrency test; direct writers prohibited; unique constraint considered later. | Batch 26 exit |
| Review/audit evidence is deleted by cascade. | Medium | High | `0006` `RESTRICT`; application delete guards for `audit_events`; 409 responses; retention tests. | Batch 26/28 |
| A developer or job migrates the cloud database from `.env`. | Medium | Critical | D4 explicit target, no settings fallback, no usable `alembic.ini` URL, identity assertion, test-mode fail-closed. | Batch 25 exit |
| Tests run against the wrong database or use `create_all`. | Medium | Critical | `pg_test_target` guard; explicit connection; unique schema; target identity; no `create_all`; skip-is-not-pass. | Batch 25/26 |
| Render auto-deploy deploys during the migration window. | Medium | High | Disable/coordinate auto-deploy; record build/start/pre-deploy; release manager gate. | Batch 27 exit |
| Production data/objects differ from the brief. | Medium | High | Read-only inventory; object/type/default/index comparison; abort on mismatch. | Batch 27 entry |
| Reconstructed `0006` is wrong because no historical migration exists. | Medium | High | Contract from deployed ORM/service; review; isolated tests; production absence confirmed; forward-fix rather than downgrade. | Batch 25/27 |
| Server-default drift causes raw-insert failures or silent divergence. | Medium | Medium | Explicit default assertions; align ORM; T10; document intentional drift. | Batch 25/26 |
| Two-codebase drift continues if B stalls. | Medium | High | D contingency trigger; no partial deployment; one branch target; time-boxed merge. | Batch 26 |
| Review/recipe scope expands without control. | Medium | Medium | Review in scope; recipes only with product-owner confirmation; written scope decision. | Stage 0 / Batch 26 |
| Production rollback is mistaken for a downgrade. | Low | Critical | Restore-to-separate-branch policy; no `0004` downgrade; rollback rehearsal; forward-fix rules. | Batch 27/28 |
| Approval is informal or single-person. | Medium | High | Named roles; two-person rule; signed approval block; change ticket. | All stages |

**Residual risk accepted by this memo:** the deployment remains NO-GO until the gates are met. This memo does not accept any production security, data-loss, or availability risk. The only accepted planning risk is that Batch 25 may reveal a graph/tooling issue that delays Batch 26; that is a schedule risk, not a production risk.

---

## 13. Commands executed, files changed, and verification evidence

### 13.1 Commands executed in Batch 24

All commands were read-only with respect to the repository, databases, and infrastructure. No database connection, Alembic command, test run, `.env` read, deployment command, or Git write occurred.

| Command group | Purpose | Outcome |
| --- | --- | --- |
| `git status --porcelain=v1 --untracked-files=all` (before and after) | Capture the working-tree baseline and confirm the only addition. | 69 entries before; 70 after; the only difference is this memo. |
| `git branch --show-current`, `git rev-parse HEAD`, `git log -1 --oneline` | Record branch, HEAD, and subject. | `feature/batch-4-rule-engine-aggregation`; `c91e9b37074483eeb7469dc943e1735fd5f5be02`. |
| `git for-each-ref` / ref count | Record refs before and after. | 11 lines including `HEAD` (10 `git for-each-ref` entries), unchanged. |
| `Get-FileHash -Algorithm SHA256` on the ten critical files | Capture pre-existing content hashes. | Saved to `C:\Users\shaha\AppData\Local\Temp\opencode\batch24_hashes_before.txt`; values in section 2.4. |
| `Get-Item` on current and preserved deployed files | Compare application/migration sizes. | Section 3.1 table; neither tree is a superset. |
| `Get-Content` / `Select-String` on `backend/migrations/env.py`, `script.py.mako`, `tests/pg_test_target.py`, `core/config.py`, `db/base.py`, `db/session.py`, `models/__init__.py`, migration tests | Inspect tooling, test isolation, and current contracts. | Findings in sections 5-7. |
| `Get-Content` / `Select-String` on current `schemas/auth.py`, `endpoints/auth.py`, and all `backend/app` files for `X-User-Role`/`x_user_role` | Confirm current branch lacks the deployed P0 behavior. | No public `role` field, no header authority path in current `backend/app`; deployed paths confirmed in the preserved tree. |
| `Get-Content` / `Select-String` on preserved deployed `schemas/auth.py:20`, `endpoints/auth.py:41`, `endpoints/governance.py:41,67,94,121`, `services/governance_service.py:24-32` | Re-confirm the P0 evidence. | Exact lines recorded in section 5. |
| `git cat-file -e 58a0e5c243978480c4ca817c537c700ed6b20516` | Check whether the deployed commit exists locally. | Exit 1; absent. The preserved tree is the only local source. |
| `Get-Content` / heading scans of Batch 18-23 reports | Establish the prior decisions, gates, T1-T14, and contracts. | Read-only; no report edited. |
| `Get-FileHash` on Batch 22 and Batch 23 reports | Confirm the prior report hashes. | Batch 22 `70A7D43D...`; Batch 23 `D28023EB...`; unchanged. |

### 13.2 Files changed

| File | Change |
| --- | --- |
| `docs/audits/Batch24_Architecture_Decision_Memo.md` | **Created.** This is the only file added by Batch 24. |

No application, migration, test, configuration, environment, or existing report was edited. No file was deleted. No Git ref or commit changed.

### 13.3 Post-write verification evidence

The following were rechecked after this memo was written:

| Check | Expected | Result |
| --- | --- | --- |
| Working-tree entries | 69 before; 70 after; only the memo added | **Pass** |
| HEAD | `c91e9b37074483eeb7469dc943e1735fd5f5be02` | **Unchanged** |
| Ref inventory | 11 lines including `HEAD` (10 `git for-each-ref` entries) | **Unchanged** |
| Critical file hashes | Match section 2.4 | **Match** |
| Recovered `0004` hash | `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` | **Verified in preserved tree; not copied in Batch 24** |
| Memo byte size | Recorded in the Batch 24 completion record | **Computed after the final write** |
| Memo SHA-256 | Recorded in the Batch 24 completion record | **Computed after the final write** |

The memo's own byte size and SHA-256 are not embedded in the memo because writing the value would change the hash. They are recorded in the Batch 24 completion message and in the temporary verification record.

### 13.4 Verification limitations

- **No runtime verification was performed.** All findings are static inspection or prior-audit evidence.
- **No database was contacted.** The local and production revisions, row counts, object inventory, and audit-chain status remain unverified.
- **No Alembic command was run.** The canonical graph is a design, not an executed migration.
- **No test was run.** T1-T14 are planned acceptance criteria, not results.
- **No deployment or infrastructure action was performed.**
- **The production brief is not independently re-verified.** The 33-run/25,654-discrepancy figures are gate inputs from the prior record.
- **The preserved deployed tree is not a Git commit.** It is a read-only source copy; the deployed commit object is absent locally.

### 13.5 Evidence preservation

| Artifact | Location |
| --- | --- |
| Working-tree status before | `C:\Users\shaha\AppData\Local\Temp\opencode\batch24_status_before.txt` |
| Refs before | `C:\Users\shaha\AppData\Local\Temp\opencode\batch24_refs_before.txt` |
| Critical hashes before | `C:\Users\shaha\AppData\Local\Temp\opencode\batch24_hashes_before.txt` |
| Preserved deployed source | `C:\Users\shaha\AppData\Local\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516` |
| Batch 24 memo | `docs/audits/Batch24_Architecture_Decision_Memo.md` |

---

## 14. Final verdict and approval

### 14.1 Verdict

**PASS - decision-documentation scope only.**

This memo completes the application-strategy decision, the P0 security remediation design, the migration ownership and canonical graph, the local-history retirement decision, the `0006` retention decision, the revision-template and migration-environment tooling decisions, the isolated PostgreSQL test strategy, the local database disposition, and the stage gates with accountability.

**Conditional GO for Batch 25** after the Stage 0 approval block is signed. Batch 25 is limited to the offline migration/tooling scope in section 10.

**NO-GO for Batch 26** until Batch 25 exits with all acceptance criteria in section 10.4.

**NO-GO for production migration and deployment.** Production requires the Batch 25 and Batch 26 exits, the Batch 27 evidence and rehearsal package, and a separate written Batch 28 production authorization. This memo alone authorizes no production migration, no production deployment, no Neon/Render/Cloudflare change, no database connection, and no application deployment.

### 14.2 What is authorized now

- The decision record in this memo.
- Stage 0 review and signature collection.
- After Stage 0 signatures: entry into Batch 25, limited to the files and tasks in section 10.
- No application-code change, migration execution, database connection, test run, or deployment is authorized by this memo itself.

### 14.3 Approval block

Complete at Stage 0. A blank line is not approval. Names must be individuals, not team aliases.

| Role | Name | Decision (Approve / Approve with conditions / Reject) | Conditions | Signature | Date |
| --- | --- | --- | --- | --- | --- |
| Engineering lead / decision owner |  |  |  |  |  |
| Security owner |  |  |  |  |  |
| Database owner |  |  |  |  |  |
| Migration owner |  |  |  |  |  |
| Independent migration reviewer |  |  |  |  |  |
| QA/test owner |  |  |  |  |  |
| Release manager |  |  |  |  |  |
| Local data owner |  |  |  |  |  |
| Audit/retention owner |  |  |  |  |  |

### 14.4 Required attestations

**Security owner:**

> I have reviewed D3 and the G1/G2 remediation design. I confirm that no P0 security finding is waived by this memo, that public registration will not accept a privileged role, and that governance authority will come only from the server-side user role. I approve the Batch 26 security acceptance tests.

**Local data owner (select one):**

> **L1:** I attest that the local development data is disposable and may be discarded under the L1 procedure in section 8.4. I understand that this is a local-only action with no production impact.

> **L2:** I attest that specific local data must be preserved. I authorize the export/rebuild/reload procedure in section 8.5, including a rehearsed dry run and fingerprint verification, and I accept the residual export/reload risk.

**Database owner:**

> I accept the Stage 3 production evidence requirements: read-only inventory, verified backup/PITR restore, Neon-branch or isolated-restore rehearsal, rollback rehearsal, target identity verification, and two-person authorization. No production DDL will be authorized until those are satisfied.

**Engineering lead:**

> I approve D1-D10 and the Batch 25 conditional entry. I understand that Batch 26 and all production work remain NO-GO until their gates are met, and that this memo does not authorize a production migration or deployment.

### 14.5 Change control

Any change to D1-D10, the canonical graph, the `0006` retention contract, the P0 design, the local disposition, or the stage gates requires a written amendment to this memo approved by the engineering lead and the affected owner. A change to the production plan after Stage 3 requires a new production authorization. Verbal approvals are not sufficient.

### 14.6 Closing statement

The safest path is not the smallest schema change. It is the path that fixes the authorization flaws in the code that runs, preserves governance and audit evidence, delivers the template capability, retires the divergent local history without stamping, and proves the result on an isolated production-equivalent target before anyone touches production.

That path is **Option B**, executed through the gates in this memo. Option D remains the contingency if the merge cannot preserve both behavior sets. Option A as stated is rejected because it leaves known P0 vulnerabilities live and does not deliver the capability the migration is meant to enable. Option C remains rejected because it silently disables governance.

**This memo authorizes no production migration and no production deployment.**

---

*End of Batch 24 Architecture Decision Memo.*

