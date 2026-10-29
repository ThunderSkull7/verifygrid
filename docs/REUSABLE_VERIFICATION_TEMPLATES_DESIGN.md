# Reusable Verification Templates — Technical Design (Batch 10)

> **Status: IMPLEMENTED (Batch 11) — migration applied locally (Batch 12).**
> The template model, API, service, and frontend panel exist (personal-only launch).
> The migration `0004_verification_templates` was applied in Batch 12 to the local
> development database (`verifygrid` @ localhost, from `0003_user_password` → head).
> The `.env`-configured cloud database has a divergent, unrelated migration history
> (`0004_enterprise_governance`) and was intentionally NOT touched — see Batch 12
> report. §7.2's "NOT APPLIED" note is historical (Batch 10 proposal state).

A reusable verification template lets a college save a validated verification configuration
(sources/roles, worksheet selections, column mappings, identity keys, fallback keys, ownership)
and re-apply it to future batches of uploaded files, without rebuilding the configuration and
without bypassing ingestion validation.

---

## 1. Existing architecture findings (verified in the current working tree)

| Area | Finding | Path |
|---|---|---|
| Tenancy | **There is no Organization entity.** Tenancy is per-user: `Project.owner_id` (nullable, FK `users.id`, `SET NULL`), and `get_project_by_id` filters `owner_id == current_user.id` when a user is present. | `backend/app/models/project.py`, `backend/app/models/user.py`, `backend/app/services/project_service.py` |
| Auth | `get_current_user` dependency (JWT); project-scoped ownership checks are done in services, not middleware. | `backend/app/api/deps.py` |
| Runs | `VerificationRun` stores per-execution data: `key_columns`, `column_mapping`, `sources` (list of `SourceDefinition` dicts incl. `file_id`), full `request.model_dump()` in `configuration`, plus `summary`/results. It mixes reusable config with per-upload state — not a suitable template store. | `backend/app/models/verification_run.py` |
| Request contract | `MultiSourceVerificationRequest` / `SourceDefinition` (alias, `file_id`, `is_primary`, `label`, `key_columns`, `field_mapping`, `excluded_row_indices`, `sheet_name`) with server-side invariants (unique aliases, one primary or multi-primary, no ambiguous mappings, fallback ≠ primary, ownership rules, multi-primary rejects fallback). | `backend/app/schemas/multisource.py` |
| Two-source (Financial) | `POST /projects/{id}/verify` with `VerificationRequest` (source/target file, `key_columns`, `column_mapping`, tolerance, status rules, rules/aggregation). | `backend/app/api/v1/endpoints/verification.py`, engine `verify_datasets` |
| Preprocessing | `PreprocessingConfig.selected_worksheet` (Batch 7 exact-name selection; unknown name → `worksheet_not_found` error; no silent fallback). | `backend/app/schemas/preprocessing.py`, `backend/app/services/preprocessing.py` |
| Identity safety | `key_tuple_is_valid` (Batch 8): blank/null/whitespace components are invalid keys → `needs_review`, never matched. | `backend/app/services/verification_engine.py` |
| Sidecars | Quarantine/profile sidecars are worksheet-scoped (Batch 9): `?worksheet=` on profiling endpoints; `get_excluded_row_indices_for_file(path, worksheet)` only applies matching-worksheet resolutions. | `backend/app/services/profiling_service.py` |
| Migrations | Hand-written Alembic revisions `0001_initial_tables` → `0002_verification_runs` → `0003_user_password`; PostgreSQL target (`postgresql+psycopg`). | `backend/migrations/versions/`, `backend/alembic.ini` |
| Tests | In-memory SQLite + `Base.metadata.create_all` — **migrations are not exercised by tests**. | `backend/tests/conftest.py` |
| Router | `api_router` includes auth/projects/uploads/preprocessing/verification/exports/profiling/rules. `blueprints.py` exists but is an **empty, unused stub** (not wired). | `backend/app/api/v1/router.py` |
| Docs | Only `README.md` exists; this document establishes the `docs/` convention. | repo root |
| Existing template code | None. `blueprints.py` is empty and unreferenced; no template models/schemas/endpoints. | verified |

**Mode separation today:** Organization Verification = multi-source wizard (`/verify/multi-source`,
2+ sources, unified keys, fallback, multi-primary). Financial Auditing = two-source path
(`/verify`) plus split-payment aggregation rules. They are distinct endpoints and request schemas;
templates must carry an explicit `mode` and must never be applied across modes.

---

## 2. Recommended template model and ownership semantics

### 2.1 Dedicated table (recommended) vs extending `VerificationRun`

**Recommendation: dedicated `verification_templates` table.**

| Option | Trade-offs |
|---|---|
| **Dedicated table (chosen)** | Clean lifecycle (templates outlive projects/files), org-level reuse independent of any project, no risk of leaking run results or per-upload state, simple RBAC surface, cheap indexing. Cost: one new table + migration. |
| Extend `VerificationRun` (e.g. `is_template` flag) | No migration of concept, but mixes mutable templates with immutable audit records, couples template queries to a large results-bearing table, forces runs to reference non-existent files, and complicates cross-project reuse (runs are project-scoped). Rejected. |
| Reference mutable "config records" (normalized tables for mappings/keys) | Stronger integrity, but heavy joins, migration churn on every schema evolution, and the request schemas already define the canonical JSON shape. Rejected in favor of a **versioned, validated JSON snapshot** (see §3.3). |

### 2.2 Ownership and visibility (using the ACTUAL tenancy model)

Because the repository has no Organization table yet, templates are **user-owned** today, with a
visibility flag designed so organization sharing can be added without a data migration of shape:

- `owner_id` — FK `users.id`, `ON DELETE SET NULL` (same convention as `Project.owner_id`).
- `visibility` — `String(20)`, values `personal` (default) | `organization_shared`.
  - **Current effective semantics:** with only per-user tenancy, `organization_shared` is treated
    as *owner-visible* plus (when an Organization feature lands) org-visible. Listing for a user
    returns: templates they own (any visibility) ∪ `organization_shared` templates owned by users
    of the same organization (once organizations exist). Until then, `organization_shared` rows
    behave exactly like `personal` for everyone except the owner — **deny by default**.
- `project_id` — **not** stored: templates are reusable across projects. (A future
  `organization_id` nullable FK can be added in a small migration when organizations exist.)

### 2.3 Uniqueness

`UniqueConstraint("owner_id", "name")` — names unique per owner. Renames re-validate. Case
sensitivity follows the database collation; no case-insensitive index is introduced (documented
limitation; users can distinguish by name casing).

### 2.4 Authorization matrix (backend-enforced, never UI-only)

| Action | Rule |
|---|---|
| List | `owner_id == current_user.id` ∪ visible shared scope (deny-by-default per §2.2). |
| Get / Update / Delete | Template must resolve via a query that filters `id` **and** the same visibility predicate; otherwise 404 (not 403 — do not confirm existence across tenants). Update/Delete additionally require **write access**: owner-only today. |
| Apply | Same read predicate; the target project must belong to the caller (existing `get_project_by_id` check); file IDs used at apply-time must belong to that project (existing `SourceFile` project filter). |

Every endpoint takes `current_user = Depends(get_current_user)`; unauthenticated requests fail at
the dependency (401). Cross-tenant access yields **404**, consistent with existing project
behavior (ownership filter in the query, not a post-fetch check).

---

## 3. Configuration schema and versioning

### 3.1 Snapshot contents (source of truth: actual request schemas)

A template stores a **complete, self-contained configuration snapshot** (`configuration` JSON)
derived from `MultiSourceVerificationRequest` with per-upload state removed:

```jsonc
{
  "version": 1,
  "mode": "organization",            // 'organization' | 'financial'
  "sources": [                        // template slots, in configured order
    {
      "alias": "sis",                 // required, unique within template
      "label": "Academic Records",    // optional display label (reused)
      "is_primary": true,
      "key_columns": ["student_id"],
      "field_mapping": {"student_id": "student_id", "full_name": "full_name", "gpa": "gpa"},
      "sheet_name": "Detailed Data"   // worksheet selection: reusable config (validated per new file)
    }
  ],
  "unified_keys": ["student_id"],
  "compare_attributes": ["full_name", "gpa"],
  "ignore_attributes": [],
  "numeric_tolerance": 0.0,
  "ignore_whitespace": true,
  "ignore_case": false,
  "include_identical": true,
  "fallback_keys": [["phone"]],       // ordered; Batch 4 semantics
  "multi_primary": false,
  "field_ownership": {"gpa": "registrar"}  // Batch 5 (only with multi_primary)
}
```

**Explicitly excluded (per-upload state, never stored):**
- `file_id` — replaced at apply-time by the user's new uploads.
- `excluded_row_indices` — Batch 9 quarantine exclusions are worksheet-scoped per-upload sidecar
  state; re-deriving them per upload is exactly what Batch 9 guarantees.
- Row indices, quarantine resolutions, student records, discrepancy data — these live in runs,
  not templates.
- `preprocessing_config` — **not** stored wholesale; only `selected_worksheet` per source slot is
  retained (a template should not pin global null-token lists or max rows for future batches).
- Any secrets/credentials — the snapshot contains column names and settings only.

**Financial mode snapshots** use the two-source shape instead: `source_file`/`target_file` slots
are replaced by two *slots* (alias + optional `sheet_name`), plus `key_columns`, `column_mapping`,
`compare_columns`, `ignore_columns`, tolerance/normalization flags, and `status_rules`.
`rule_config`/aggregation is **out of scope for v1 templates** (documented limitation) because
aggregation references concrete child/parent file relationships; a future version may add it.

### 3.2 Mode discipline

`mode` is a required column and snapshot field. Saving and applying both re-validate that the
snapshot's shape matches its mode: `organization` snapshots validate as
`TemplateOrganizationConfig` (multisource-shaped), `financial` as `TemplateFinancialConfig`.
The apply endpoint routes to the matching existing verification path; an organization template can
never be executed through the financial path and vice versa. The Financial wizard UI never sees
organization template endpoints (frontend separation mirrors the existing wizard split).

### 3.3 Validation & versioning strategy

- `config_version` (integer column, default 1) is mirrored inside the snapshot as `"version"`;
  they must agree.
- **On save:** the payload is parsed through a dedicated Pydantic schema
  (`TemplateConfigurationV1`, reuse of the validators in `MultiSourceVerificationRequest` — alias
  uniqueness, single-primary or multi-primary invariants, ambiguous-mapping rejection, fallback ≠
  primary, ownership rules, multi-primary rejects fallback). Invalid input → `422` with the
  validator's messages. Nothing is silently discarded: unknown fields are rejected (`extra="forbid"`),
  not ignored.
- **On load/apply:** the stored JSON is re-validated against the schema registered for
  `config_version`. A mismatch between the column and the embedded `"version"` → `422`.
- **Future schema changes:** add `TemplateConfigurationV2` and a registered migration function
  (`V1 → V2` upgrader). Read path upgrades transparently on apply (the template row is only
  rewritten if the user saves); list/get return the stored version with an optional
  `schema_upgrade_available` flag.
- **Unsupported versions** (e.g. `config_version = 99` on an older deployment after a rollback):
  loading for apply returns `422 Unsupported template configuration version` with the supported
  set — never a silent partial load, never silent field dropping.
- **Snapshot vs references:** a complete snapshot is chosen because (a) the request schemas are
  already the canonical JSON contract, (b) templates must survive deletion/re-mapping of the
  project they were created in, and (c) normalized storage would require referential machinery
  (per-source rows, per-mapping rows) that adds migration churn without adding integrity the
  Pydantic validators don't already enforce at the boundary.

---

## 4. API contract (proposed; NOT implemented)

All routes under the existing `/api/v1` router, registered as
`templates_router` (`/templates`, tags `["Templates"]`). All require authentication.

### 4.1 `GET /api/v1/templates`
- Query: `mode` (optional filter), `visibility` (optional), paging `skip`/`limit` (≤ 200).
- Response `200`: `{ "templates": [TemplateSummary], "total": int }` where `TemplateSummary` =
  `{ id, name, description, mode, visibility, config_version, source_count, created_at, updated_at }`
  (no configuration payload — keep listings light).
- Auth: visibility predicate from §2.4. Cross-tenant rows are simply absent.

### 4.2 `POST /api/v1/templates`
- Body: `{ name, description?, mode, visibility?, configuration }`.
- Validation: name non-empty (≤ 255); `visibility ∈ {personal, organization_shared}`;
  configuration validated per §3.3 (422 on failure, incl. unique-name violation → `409`).
- Response `201`: full `Template` object.
- Errors: `401`, `409` (duplicate name), `422` (validation).

### 4.3 `GET /api/v1/templates/{template_id}`
- Response `200`: full `Template` (including configuration).
- Errors: `401`; **`404`** when the template does not exist *or* is not visible to the caller.

### 4.4 `PUT /api/v1/templates/{template_id}`
- Body: partial `{ name?, description?, visibility?, configuration? }`. Owner-only (write access).
- Configuration changes are re-validated in full (no partial config merge — a snapshot is replaced
  atomically). Response `200` with the updated template; `404` / `409` / `422` as above.

### 4.5 `DELETE /api/v1/templates/{template_id}`
- Owner-only. Response `204`. Idempotent 404 semantics: deleting a non-visible/non-existent
  template → `404`.

### 4.6 `POST /api/v1/templates/{template_id}/apply` *(the safety-critical endpoint)*
- Body: `{ project_id, sources: [{ slot: <alias from template>, file_id } ...] }` — the caller
  binds each template slot to an uploaded file in that project. For financial templates:
  `{ project_id, source_file_id, target_file_id }`.
- Steps (all before any verification executes):
  1. Template read-permission check (§2.4) → `404` if denied.
  2. Project ownership check via existing `get_project_by_id` → `404`.
  3. Every bound `file_id` must belong to `project_id` → `404`/`422`.
  4. Every template slot must be bound exactly once (missing/extra bindings → `422`).
  5. **Worksheet validation:** for each xlsx slot with `sheet_name`, verify it exists in the new
     workbook (`list_worksheet_names`); missing → `422` with per-slot detail. CSV slots with a
     `sheet_name` → `422` (Batch 7 rule).
  6. **Column-mapping validation:** parse each file's headers (preprocessing read) and check every
     `key_columns` entry and every mapped source column exists; report missing/renamed columns
     per slot. Response carries a structured `validation_report`.
  7. **Setting validation:** re-run the request-schema invariants (§3.3) plus Batch 8/4/5 rules
     (identity keys non-empty, fallback ≠ primary, ownership targets exist).
- Response `200` (validation passes): the **effective `MultiSourceVerificationRequest`** /
  `VerificationRequest` (file IDs substituted) + `validation_report` — the frontend then submits
  it to the *existing* verify endpoints. **The apply endpoint never executes verification itself**;
  correctness-critical gaps (missing key columns, unknown worksheet, ambiguous mappings) return
  `422` and block execution.
- Errors: `401`, `404` (template/project/file not visible or not found), `422` (any blocking
  validation failure, with `validation_report`).

The two-step design (apply → existing verify endpoint) guarantees legacy requests without
templates are untouched and all existing per-request invariants still run at execution time.

---

## 5. Frontend workflow (proposed; smallest effective integration)

All within the existing Organization Verification wizard (`frontend/src/components/
ReconciliationWizard.tsx`, 5-step wizard) and its file step (`FileUploadSection.tsx`);
**Financial Auditing stays separate and gains nothing** in v1.

1. **Step 1 (setup):** optional "Start from a saved template" picker (`api.getTemplates({mode:'organization'})`).
   Choosing a template loads slot metadata (aliases/labels/roles) and the rest of the config into
   wizard state; the user can still configure manually as today (template path is optional).
2. **Upload:** as today. If a template is active, each uploaded file is bound to a slot
   (auto-suggest by label/role, user-confirmed).
3. **Validation:** on binding, the frontend calls `POST /templates/{id}/apply` with the bindings
   and renders `validation_report` inline: worksheet mismatches, missing/renamed columns, key
   and ownership problems — each mapped to the wizard step where it can be fixed.
4. **Review:** the wizard's existing review step shows the effective configuration (from the apply
   response). Execution is gated on `validation_report.blocking == false`; the "Run verification"
   button submits the effective request to the existing verify endpoint.
5. **Save as template:** an optional action at the review step (`POST /templates` or
   `PUT /templates/{id}` for owned templates) using the *validated effective configuration*
   (file IDs and row exclusions stripped).

No new routes/pages; two new service functions in `frontend/src/services/api.ts` were the extent
of the planned plumbing.

---

## 6. Validation and safety rules (summary)

- Backend authorization on every template operation (§2.4); cross-tenant access → `404`.
- `extra="forbid"` on template configuration schemas — no silent field dropping.
- Per-upload state (`file_id`, `excluded_row_indices`, row indices, quarantine resolutions,
  records) is structurally excluded from the template schema — a v1 schema simply has no such
  fields, so leakage is impossible by construction rather than by convention.
- Apply-time validations that **block execution**: unknown worksheet; missing key/mapped columns;
  unbound or extra-bound slots; files from another project; mode mismatch; unsupported
  config version; invalid fallback/ownership settings.
- Apply-time validations that **warn only** (non-blocking): renamed-but-mappable columns where the
  mapping can be auto-suggested (user must confirm), optional label drift.
- Batch 8 identity safety and Batch 9 worksheet-scoped sidecars are untouched: templates carry
  *no* exclusions; every run re-derives them from the current upload's own sidecars.
- No secrets/credentials ever enter the snapshot (schema has no credential fields).

---

## 7. Migration design and rollback plan

### 7.1 Proposed table `verification_templates`

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | PK, default `uuid4` (matches `projects.id` convention) |
| `owner_id` | `UUID` | FK `users.id` `ON DELETE SET NULL`, nullable, indexed (mirrors `projects.owner_id`) |
| `name` | `String(255)` | NOT NULL |
| `description` | `Text` | nullable |
| `mode` | `String(50)` | NOT NULL, values `organization` / `financial` (app-level enum) |
| `visibility` | `String(20)` | NOT NULL, server default `'personal'` |
| `config_version` | `Integer` | NOT NULL, server default `1` |
| `configuration` | `JSON` | NOT NULL |
| `created_at` / `updated_at` | `DateTime(timezone=True)` | NOT NULL, `now()` server defaults, `updated_at` onupdate |

- **PK/FKs:** `id` PK; `owner_id → users.id`.
- **Tenant deletion behavior:** `SET NULL` on owner deletion (template survives, becomes
  ownerless/orphaned and is treated as personal-invisible except to admins in a future org model —
  same as existing project behavior).
- **Indexes:** index on `owner_id`; **unique constraint** `(owner_id, name)`.
- **JSON vs normalized:** JSON (consistent with `verification_runs.configuration`) — the request
  schemas are the canonical shape, validated at every boundary (§3.3).
- **Defaults/nullability:** `visibility`/`config_version` have server defaults so inserts are
  simple; `configuration` NOT NULL (a template without config is meaningless).
- **Rollback:** `downgrade()` drops the table. No existing table is touched, so rollback is
  complete and lossless for pre-existing data.
- **Existing data migration:** none required — brand-new table, no backfill.
- **PostgreSQL compatibility:** plain `UUID`/`JSON`/`String`/`DateTime(timezone=True)` types, the
  same as revisions 0001–0002. `sa.Uuid` is used in newer revisions' model forms; the proposed
  migration follows 0002's explicit `sa.Uuid()` style.
- **SQLite tests:** tests build schema via `Base.metadata.create_all`, not Alembic, so the new
  model works under SQLite (generic `Uuid` and `JSON` are portable). The Alembic migration itself
  is only exercised against PostgreSQL/locally — never in CI test runs. A test that wants to
  assert migration presence can parse the file, but upgrade/downgrade execution is intentionally
  out of scope (not applied anywhere in this batch).

### 7.2 Migration file (APPLIED locally in Batch 12)

- **Path:** `backend/migrations/versions/0004_verification_templates.py`
- **Revision:** `0004_verification_templates` · **Revises:** `0003_user_password`
- `upgrade()` creates the table, `downgrade()` drops it. No unrelated changes are included.
- **Batch 12 status:** applied to the local development database (`verifygrid` @ localhost,
  `0003_user_password` → head) after read-only verification that its history matches this
  repository's graph; schema, constraints, defaults, and data preservation were verified.
  Downgrade was verified via offline `--sql` generation only (drops index → table → updates
  `alembic_version`); no destructive downgrade was run against the data-bearing dev DB.
  The `.env`-configured cloud database (divergent `0004_enterprise_governance` history)
  was NOT touched — reconciliation requires a project-owner decision.

---

## 8. Test plan (for the implementation batch)

Configuration validation
- V1 snapshot round-trips (save → get → apply-response) without mutation.
- Unknown fields rejected (`extra="forbid"`); embedded `version` ≠ `config_version` → 422.
- Unsupported `config_version` on load/apply → 422 with supported set.

CRUD & authorization
- Create (201), duplicate name (409), invalid config (422).
- List returns owned only; second user's list excludes them (cross-tenant read denial → 404 on
  get/update/delete/apply for the other user's template).
- Update owner-only; delete → 204 then 404.

Apply-time safety
- Matching columns → effective request correct (file IDs substituted; no `excluded_row_indices`).
- Missing/renamed key or mapped columns → 422 with per-slot report.
- Invalid worksheet on xlsx slot → 422 (message lists available sheets); `sheet_name` on CSV → 422.
- Files bound from another project → 404.
- Invalid fallback (== primary, or with multi_primary) and invalid ownership → 422.
- Multi-primary template with fallback config rejected at save *and* apply.

Mode separation
- Organization template cannot be applied via financial path and vice versa; financial snapshot
  shape is the two-source shape.

Compatibility & leakage
- Legacy requests without templates behave identically (existing suite green).
- Saved template contains no `file_id`, `excluded_row_indices`, row indices, resolutions, or
  record data (schema-level assertion on the JSON payload).
- Template survives owner deletion (`owner_id` NULL) without cascading errors.

---

## 9. Implementation sequence (next batch)

1. `TemplateConfigurationV1` Pydantic schemas (org + financial) with `extra="forbid"` + unit tests.
2. `VerificationTemplate` SQLAlchemy model + register in `app/models/__init__.py`.
3. Review/applied migration `0004` (only after design sign-off), run locally against PostgreSQL.
4. `template_service.py`: CRUD + visibility predicate + apply/validation logic (reusing
   `list_worksheet_names`, preprocessing header reads, `MultiSourceVerificationRequest` validation).
5. `templates.py` endpoint + router registration + response schemas.
6. Frontend: `api.ts` service functions; wizard template picker, slot binding, validation report
   rendering, save-as-template action.
7. Full test suite + gates.

---

## 10. Open decisions and trade-offs

1. **Organizations do not exist yet.** `visibility='organization_shared'` is stored but behaves
   as personal until an Organization entity lands. Alternative: omit the column now and add it
   later — rejected because a nullable-string column is cheaper than a second migration and
   clarifies intent. *(Decision needed before implementation only if org sharing must be live at
   launch.)*
2. **`rule_config`/aggregation excluded from v1 financial templates.** Aggregation binds concrete
   child/parent files; a safe slot-binding design needs more thought. Limitation documented.
3. **Case-insensitive name uniqueness** not provided (DB collation dependent). Acceptable for v1.
4. **Apply response re-submits to existing verify endpoints** rather than embedding
   `template_id` in the verification request. Alternative (`template_id` on the request) was
   rejected for this batch to avoid touching `VerificationRun`/request schemas; it can be added
   later for provenance without breaking anything.
5. **Owner deletion leaves orphaned templates** (mirroring `projects.owner_id` semantics).
   An admin/curator story is deferred to the Organization feature.

---

## 11. Quality-gate results (actual runs, Batch 10)

Because this batch added only a design document and an unapplied migration proposal — no code
imported by the application (the migration file is standalone and never executed by tests) —
application behavior is unchanged by construction. Gates were still run:

| Gate | Command | Result |
|---|---|---|
| Backend suite | `pytest tests -q` (in `backend/`) | **232 passed**, 1 warning |
| Type check | `npx tsc --noEmit` (in `frontend/`) | exit 0 |
| Lint | `npx oxlint` (in `frontend/`) | exit 0 |
| Build | `npx vite build` (in `frontend/`) | exit 0, ✓ built |

## 12. Files changed in Batch 10

- `docs/REUSABLE_VERIFICATION_TEMPLATES_DESIGN.md` (new — this document)
- `backend/migrations/versions/0004_verification_templates.py` (new — **proposed, NOT applied**)

No other files were modified; Batches 1–9 remain intact; nothing was committed, pushed, merged,
deployed, or migrated; no production data or secrets were accessed.

---

## Recommendation

**Ready for implementation**, contingent on resolving open decision §10.1 (whether
organization-shared visibility must be live at launch, or stored-but-dormant as designed here).
The proposed migration `0004_verification_templates` should be reviewed and applied locally
(`alembic upgrade head` on a local PostgreSQL) at the start of the implementation batch — it was
deliberately not applied in Batch 10.
