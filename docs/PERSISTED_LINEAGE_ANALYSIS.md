# Persisted Lineage and `missing_by_source` Semantics

**Status:** Batch 15 analysis only. No matching or persistence behavior was changed.
**Scope:** local repository code and an in-memory SQLite observation. No Neon connection was made.

## 1. Contract in the preview (stateless) path

`MultiSourceVerificationResponse` exposes both aggregate maps at the top level:

| Field | Source | Meaning |
| --- | --- | --- |
| `records_by_source` | `verification_engine.py` | Number of eligible records read from each source after quarantine exclusions. |
| `missing_by_source` | `verification_engine.py` | Number of result rows whose `missing_in_sources` list contains that source alias. |

The exact construction is:

```python
records_by_source = {s.alias: len(filtered_records[s.alias]) for s in sources}
missing_by_source = {
    s.alias: sum(1 for item in results if s.alias in (item.missing_in_sources or []))
    for s in sources
}
```

Consequences of that definition:

1. `missing_by_source` counts **result rows**, not raw input rows. One unmatched key contributes one count for each source in which it is absent.
2. A record present in every source never contributes, because `missing_in_sources` is empty.
3. Duplicate-key result rows can contribute when the engine marks a source as missing for that row; the count should be read as "result rows missing this source", not "unique input records absent".
4. The maps are independent: `records_by_source` describes eligibility; `missing_by_source` describes outcome-level absence.
5. `total_source_records` is the primary source only; `total_target_records` is the sum of non-primary sources. Neither replaces `missing_by_source`.

Per-result lineage in the preview includes:

- `source_row_indices` (alias → row number or `null`)
- `source_records` (alias → record or `null`)
- `missing_in_sources` (list of absent aliases)
- `source_presence` (alias → boolean)
- `lineage` (matching method, fallback key/values, ownership mode)
- `unverified_fields` (attributes intentionally not checked for that record)

## 2. What is persisted

`create_and_execute_multisource_run` stores:

- the run's `sources` and full effective `configuration`;
- `summary`, augmented with `records_by_source` and `missing_by_source`;
- one `VerificationDiscrepancy` row per **discrepancy** result (identical matches are not persisted).

`VerificationDiscrepancy` currently persists:

- `key_values`
- `source_row_number` / `target_row_number` and plural variants
- `source_row_indices`
- `source_records`
- legacy `source_record` / `target_record`
- `field_differences`, `child_records`, amounts, message

It does **not** have columns for:

- `missing_in_sources`
- `source_presence`
- `lineage`
- `unverified_fields`

`reason_code` and `confidence_score` are computed properties on the ORM model,
not stored columns.

## 3. Observed persisted API behavior

A local in-memory SQLite observation used three cases: one field mismatch, one
record missing in the secondary source, and one record missing in the primary
source. It printed only field presence and non-sensitive key metadata.

Observed run summary:

- `summary.records_by_source = {"primary": 3, "secondary": 3}`
- `summary.missing_by_source = {"primary": 1, "secondary": 1}`
- `missing_by_source` is **not** a top-level field on the persisted run response.

Observed persisted result items:

| Status | `source_row_indices` | `source_records` | `missing_in_sources` | `source_presence` | `lineage` | `unverified_fields` |
| --- | --- | --- | --- | --- | --- | --- |
| `field_mismatch` | present | present | `null` | `null` | absent | absent |
| `missing_in_target` | present (`secondary: null`) | present | `null` | `null` | absent | absent |
| `missing_in_source` | present (`primary: null`) | present | `null` | `null` | absent | absent |

The API schema declares `missing_in_sources` and `source_presence`, but the ORM
object has no such attributes. Pydantic therefore serializes them as `null`.
`lineage` and `unverified_fields` are not part of the persisted discrepancy
response schema at all.

## 4. Impact

- **Missing-source counts survive** inside `run.summary.missing_by_source`.
- **Per-record absence attribution is lost** in the persisted result API. A
  client can still infer absence from `null` entries in `source_row_indices`
  because the run stores the participating source aliases, but it receives no
  explicit `missing_in_sources` or `source_presence` contract.
- **Matching provenance is lost.** Persisted results cannot show whether a row
  matched by primary key or fallback key, which fallback values were used, or
  which ownership mode applied.
- **Not-checked versus verified is lost.** `unverified_fields` is available in
  the preview but absent from persisted results, weakening audit evidence.
- **On a migration-built database the loss is worse than field omission.** The
  committed migrations do not create `source_row_indices`, `source_records`,
  `child_records`, `aggregated_amount`, `expected_amount`, or
  `verification_runs.sources`. Persistence or retrieval against such a schema
  fails at the database layer before these semantics can be evaluated.

## 5. Is `missing_by_source` itself defective?

No reproducible defect was established in the calculation. It matches its
documented implementation and the observed counts. The open questions are:

1. Should duplicate-key rows contribute to `missing_by_source`? The current
   contract counts result rows, not unique input records.
2. Should `missing_by_source` be promoted to a top-level persisted field rather
   than existing only inside the opaque `summary` JSON?
3. Should per-result `missing_in_sources` and `source_presence` be persisted as
   explicit lineage columns or reconstructed from `source_row_indices`?
4. Should persisted results expose `lineage` and `unverified_fields` for audit
   parity with the preview?

Changing any of these would alter a public contract. Batch 15 therefore records
the questions and does **not** change matching, counting, or persistence.

## 6. Recommended next contract (not implemented)

Before implementing, the team should agree on:

- the definition of `missing_by_source` (result rows vs unique keys);
- whether duplicate/invalid-key rows are included;
- the persisted-result schema additions and their migration;
- backward-compatibility behavior for existing runs whose lineage was never
  stored.

Only after that contract is accepted should a migration and API change be
authored and tested against an isolated PostgreSQL target.
