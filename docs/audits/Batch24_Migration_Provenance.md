# Batch 24 Migration Provenance Record

**Date:** 2026-10-29  
**Repository:** `C:\Users\shaha\verifygrid`  
**Branch:** `feature/batch-4-rule-engine-aggregation`  
**HEAD at Batch 25 start:** `c91e9b37074483eeb7469dc943e1735fd5f5be02`

This note records the provenance of the recovered governance migration and the
retired local migration revisions. It is a Batch 25 artifact referenced by
`docs/audits/Batch24_Architecture_Decision_Memo.md` section 10.2. It does not
modify any Batch 18-23 report.

## 1. Recovered governance revision

| Property | Value |
| --- | --- |
| Revision ID | `0004_enterprise_governance` |
| Source commit | `58a0e5c243978480c4ca817c537c700ed6b20516` (not present in local Git) |
| Source tree | `C:\Users\shaha\AppData\Local\Temp\verifygrid_batch21_deployed\verifygrid-58a0e5c243978480c4ca817c537c700ed6b20516` |
| Source path | `backend\migrations\versions\0004_enterprise_governance_and_materiality.py` |
| Source SHA-256 | `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` |
| Source bytes | 10,032 |
| Destination path | `backend\migrations\versions\0004_enterprise_governance_and_materiality.py` |
| Destination SHA-256 | `44D31AE949469608BD253C3EC3BD356E0252C2E50F84AF026566C2361A5A7AEB` |
| Parent | `0003_user_password` |

The destination file is a byte-identical copy. It was not reformatted, edited,
renamed, or regenerated. The source commit object is absent locally; the
preserved source tree is the only local authority for the governance DDL.

## 2. Retired local revisions

Both local revisions were untracked and are now outside the active Alembic
graph. They are preserved byte-identically under `backend/migrations/retired/`,
which Alembic does not scan.

| Original path | Archived path | SHA-256 | Bytes | Disposition |
| --- | --- | --- | ---: | --- |
| `backend\migrations\versions\0004_verification_templates.py` | `backend\migrations\retired\0004_verification_templates.py` | `CBE7E536573D06D49E4EB2F8EFB7BD26A0D3CCA786F01EA80AE7C8E7CA74E227` | 2,936 | Retired. Its table DDL is intended to be reissued as `0005_verification_templates` in a later authorized batch. |
| `backend\migrations\versions\0005_verification_lineage.py` | `backend\migrations\retired\0005_verification_lineage.py` | `645BE701DFF05FDF6D263AF678CB17E77D818CE64C00A8B9F3AF96E46E585713` | 3,144 | Retired. Never replayed. Its six lineage columns are owned by `0004_enterprise_governance`. |

The original files were removed from `backend/migrations/versions/` only after
the archived copies were verified by SHA-256.

## 3. Retirement decision

- The canonical graph after Batch 25 is `0001_initial_tables ->
  0002_verification_runs -> 0003_user_password -> 0004_enterprise_governance`.
- `0005_verification_lineage` is not in the graph and cannot be replayed.
  Attempting to upgrade to it fails with `Can't locate revision identified by
  '0005_verification_lineage'`.
- `0004_verification_templates` is not in the graph. Its DDL is not replayed
  against production or local databases.
- No database was stamped, rebuilt, upgraded, or otherwise modified in Batch
  25. The local development database disposition remains deferred to the
  authorized Batch 26 execution (Batch 24 decision D7; the Batch 25
  instruction prohibits destructive local-database operations).
- No production, Neon, Render, Cloudflare, staging, or remote database was
  contacted.
- `0005_verification_templates` and `0006_discrepancy_review_decisions` were
  **not** created in Batch 25. The Batch 25 instruction explicitly excludes
  the two future application revisions; they remain the next migration-graph
  work item after this batch. The Batch 24 memo's full manifest therefore
  remains partially open. See the Batch 25 report for the exact deviation.

## 4. Verification commands

The hashes above were produced with `Get-FileHash -Algorithm SHA256` in
PowerShell. The active graph was inspected with `alembic heads` and
`alembic history`; both ran without a database target. The recovered file hash
and the archived hashes were re-verified after the copies.

## 5. Preservation statement

No Batch 18-23 report was edited. No application model, schema, service,
endpoint, frontend file, or environment file was changed by Batch 25. The only
application-adjacent changes are the Alembic tooling, migration graph,
migration tests, and this provenance record.
