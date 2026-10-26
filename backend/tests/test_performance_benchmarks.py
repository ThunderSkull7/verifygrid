"""Performance Benchmarking & Throughput Verification Suite.

Benchmarks end-to-end reconciliation throughput and latency under memory constraints
using synthetic datasets of representative scale (1,000 rows, 5,000 rows, and 10,000 rows)
with mixed realistic financial conditions:
  - Exact matches (60%)
  - Monetary amount variances (15%)
  - Date settlement lags (10%)
  - Fuzzy string variations (5%)
  - Missing in target (5%)
  - Missing in source (5%)

Measures latencies across:
  1. File Ingestion & Schema Inference
  2. Data Profiling & Quarantine Anomaly Scanning
  3. Multi-source Join, Rule Evaluation & Reconciliation Execution
  4. Financial Materiality & Exception Clustering
  5. Multi-sheet Excel Workbook Export Generation
"""

from __future__ import annotations

import csv
import io
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple
import pytest
from sqlalchemy.orm import Session

from app.models.verification_run import VerificationDiscrepancy, VerificationRun
from app.schemas.multisource import SourceDefinition
from app.schemas.preprocessing import PreprocessingConfig
from app.schemas.result import MatchStatus
from app.schemas.rule import DateWindowRule, VersionedRuleConfig
from app.services.clustering_service import cluster_discrepancies_in_memory
from app.services.export_service import generate_audit_workbook_xlsx
from app.services.materiality_engine import (
    compute_summary_materiality,
)
from app.services.profiling_service import profile_dataset_records
from app.services.verification_engine import (
    extract_dataset_records,
    verify_multisource_datasets,
)


def generate_synthetic_benchmark_datasets(
    row_count: int,
) -> Tuple[bytes, bytes, List[Tuple[int, Dict[str, Any]]], List[Tuple[int, Dict[str, Any]]]]:
    """
    Generate synthetic reconciliation datasets with representative scale and matching conditions.
    Returns:
        (source_csv_bytes, target_csv_bytes, source_records, target_records)
    """
    base_date = datetime(2026, 1, 15, 10, 0, 0)
    
    src_rows: List[Dict[str, Any]] = []
    tgt_rows: List[Dict[str, Any]] = []

    src_records: List[Tuple[int, Dict[str, Any]]] = []
    tgt_records: List[Tuple[int, Dict[str, Any]]] = []

    for i in range(1, row_count + 1):
        txn_id = f"TXN_{i:07d}"
        acct_no = f"ACC_{100000 + (i % 500)}"
        base_amount = 100.0 + round((i * 7) % 5000, 2)
        txn_date_str = (base_date + timedelta(minutes=i % 1440)).strftime("%Y-%m-%d")

        # Mixed condition distribution
        mod = i % 100
        if mod < 60:
            # 60%: Exact Match
            name = f"Merchant Partner {i % 200}"
            src_row = {
                "txn_id": txn_id,
                "account_no": acct_no,
                "merchant_name": name,
                "amount": str(base_amount),
                "txn_date": txn_date_str,
                "status": "SETTLED",
            }
            tgt_row = dict(src_row)
        elif mod < 75:
            # 15%: Amount Variance
            variance = 5.25 if (i % 2 == 0) else -12.50
            src_row = {
                "txn_id": txn_id,
                "account_no": acct_no,
                "merchant_name": f"Vendor {i % 150}",
                "amount": str(base_amount),
                "txn_date": txn_date_str,
                "status": "SETTLED",
            }
            tgt_row = {
                "txn_id": txn_id,
                "account_no": acct_no,
                "merchant_name": f"Vendor {i % 150}",
                "amount": str(round(base_amount + variance, 2)),
                "txn_date": txn_date_str,
                "status": "SETTLED",
            }
        elif mod < 85:
            # 10%: Date Lag (2-4 days later)
            src_row = {
                "txn_id": txn_id,
                "account_no": acct_no,
                "merchant_name": f"Corporate Client {i % 80}",
                "amount": str(base_amount),
                "txn_date": txn_date_str,
                "status": "CLEARED",
            }
            lag_date = (base_date + timedelta(days=3, minutes=i % 1440)).strftime("%Y-%m-%d")
            tgt_row = {
                "txn_id": txn_id,
                "account_no": acct_no,
                "merchant_name": f"Corporate Client {i % 80}",
                "amount": str(base_amount),
                "txn_date": lag_date,
                "status": "CLEARED",
            }
        elif mod < 90:
            # 5%: Fuzzy Name Variation
            src_row = {
                "txn_id": txn_id,
                "account_no": acct_no,
                "merchant_name": f"Global Logistics LLC {i % 40}",
                "amount": str(base_amount),
                "txn_date": txn_date_str,
                "status": "COMPLETED",
            }
            tgt_row = {
                "txn_id": txn_id,
                "account_no": acct_no,
                "merchant_name": f"Global Logistics {i % 40}",
                "amount": str(base_amount),
                "txn_date": txn_date_str,
                "status": "COMPLETED",
            }
        elif mod < 95:
            # 5%: Missing in Target (Source only)
            src_row = {
                "txn_id": txn_id,
                "account_no": acct_no,
                "merchant_name": f"Orphan Source {i % 30}",
                "amount": str(base_amount),
                "txn_date": txn_date_str,
                "status": "PENDING",
            }
            tgt_row = None
        else:
            # 5%: Missing in Source (Target only)
            src_row = None
            tgt_row = {
                "txn_id": txn_id,
                "account_no": acct_no,
                "merchant_name": f"Unmatched Target {i % 30}",
                "amount": str(base_amount),
                "txn_date": txn_date_str,
                "status": "PENDING",
            }

        if src_row is not None:
            src_rows.append(src_row)
            src_records.append((len(src_rows), src_row))
        if tgt_row is not None:
            tgt_rows.append(tgt_row)
            tgt_records.append((len(tgt_rows), tgt_row))

    # Serialize CSV buffers
    fieldnames = ["txn_id", "account_no", "merchant_name", "amount", "txn_date", "status"]
    
    src_buf = io.StringIO()
    src_writer = csv.DictWriter(src_buf, fieldnames=fieldnames)
    src_writer.writeheader()
    src_writer.writerows(src_rows)
    src_csv_bytes = src_buf.getvalue().encode("utf-8")

    tgt_buf = io.StringIO()
    tgt_writer = csv.DictWriter(tgt_buf, fieldnames=fieldnames)
    tgt_writer.writeheader()
    tgt_writer.writerows(tgt_rows)
    tgt_csv_bytes = tgt_buf.getvalue().encode("utf-8")

    return src_csv_bytes, tgt_csv_bytes, src_records, tgt_records


def _run_scale_benchmark(
    row_count: int,
    db: Session,
    max_duration_seconds: float = 20.0,
) -> Dict[str, float]:
    """
    Executes a complete 5-phase benchmarking cycle on synthetic datasets of given scale.
    Records duration for each phase and enforces bounded execution.
    """
    print(f"\n========================================================")
    print(f"  BENCHMARK: Scale = {row_count:,} rows")
    print(f"========================================================")

    total_start = time.perf_counter()

    # 1. Dataset Generation
    gen_start = time.perf_counter()
    src_bytes, tgt_bytes, src_recs, tgt_recs = generate_synthetic_benchmark_datasets(row_count)
    gen_duration = time.perf_counter() - gen_start

    # 2. Phase 1: Ingestion & CSV Parsing
    p1_start = time.perf_counter()
    reader = csv.DictReader(io.StringIO(src_bytes.decode("utf-8")))
    parsed_rows = list(reader)
    assert len(parsed_rows) > 0
    p1_duration = time.perf_counter() - p1_start

    # 3. Phase 2: Data Profiling & Quarantine Scanning
    p2_start = time.perf_counter()
    summary_prof, quarantined = profile_dataset_records(
        file_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        filename="benchmark_source.csv",
        file_type="csv",
        records=src_recs,
        raw_headers=["txn_id", "account_no", "merchant_name", "amount", "txn_date", "status"],
        column_mapping={c: c for c in ["txn_id", "account_no", "merchant_name", "amount", "txn_date", "status"]},
        null_set={"none", "null", "nil", "nan", "n/a", "na", "#n/a", ""},
    )
    p2_duration = time.perf_counter() - p2_start
    assert summary_prof.total_rows == len(src_recs)

    # 4. Phase 3: Multi-Source Join, Rule Evaluation & Reconciliation Execution
    sources = [
        SourceDefinition(file_id=uuid.uuid4(), alias="erp", is_primary=True, key_columns=["txn_id"]),
        SourceDefinition(file_id=uuid.uuid4(), alias="bank", is_primary=False, key_columns=["txn_id"]),
    ]
    sources_records = {
        "erp": src_recs,
        "bank": tgt_recs,
    }
    date_rule = DateWindowRule(source_date_field="txn_date", target_date_field="txn_date", max_lag_days_after=3)
    rule_config = VersionedRuleConfig(date_window_rules=[date_rule])

    p3_start = time.perf_counter()
    rec_summary, results, discrepancies, records_by_src, missing_by_src = verify_multisource_datasets(
        sources=sources,
        sources_records=sources_records,
        unified_keys=["txn_id"],
        compare_attributes=["amount", "status"],
        ignore_attributes=[],
        numeric_tolerance=0.01,
        ignore_whitespace=True,
        ignore_case=True,
        rule_config=rule_config,
        include_identical=True,
    )
    p3_duration = time.perf_counter() - p3_start

    # 5. Phase 4: Financial Materiality & Exception Clustering
    p4_start = time.perf_counter()
    rec_summary = compute_summary_materiality(results, discrepancies, rec_summary)
    clusters = cluster_discrepancies_in_memory(discrepancies)
    p4_duration = time.perf_counter() - p4_start

    # 6. Phase 5: Multi-Sheet Excel Workbook Export Generation
    p5_start = time.perf_counter()
    fake_run = VerificationRun(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        status="completed",
        key_columns=["txn_id"],
        column_mapping={"amount": "amount", "status": "status"},
        summary=rec_summary.model_dump(),
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        sources=[{"alias": "erp"}, {"alias": "bank"}],
    )
    # Convert discrepancy items to VerificationDiscrepancy instances for openpyxl export
    model_discrepancies: List[VerificationDiscrepancy] = []
    for d in discrepancies[:1000]:  # Up to 1K exception rows in export tab
        model_discrepancies.append(
            VerificationDiscrepancy(
                id=uuid.uuid4(),
                run_id=fake_run.id,
                source_row_number=d.source_row_number,
                target_row_number=d.target_row_number,
                match_status=d.match_status.value if hasattr(d.match_status, "value") else str(d.match_status),
                discrepancy_category=d.discrepancy_category.value if hasattr(d.discrepancy_category, "value") else str(d.discrepancy_category),
                key_values=d.key_values,
                exposure_amount=d.exposure_amount,
                variance_amount=d.variance_amount,
                source_amount=d.source_amount,
                target_amount=d.target_amount,
                field_differences=[fd.model_dump() for fd in (d.field_differences or [])],
                source_record=d.source_record,
                target_record=d.target_record,
                message=d.message,
                created_at=datetime.now(timezone.utc),
            )
        )

    workbook_bytes = generate_audit_workbook_xlsx(db, fake_run, model_discrepancies)
    p5_duration = time.perf_counter() - p5_start
    assert len(workbook_bytes) > 0

    total_duration = time.perf_counter() - total_start

    # Metrics reporting
    throughput = round(row_count / p3_duration, 1) if p3_duration > 0 else 0
    metrics = {
        "dataset_rows": float(row_count),
        "gen_ms": round(gen_duration * 1000, 2),
        "p1_ingest_ms": round(p1_duration * 1000, 2),
        "p2_profiling_ms": round(p2_duration * 1000, 2),
        "p3_reconciliation_ms": round(p3_duration * 1000, 2),
        "p4_materiality_clustering_ms": round(p4_duration * 1000, 2),
        "p5_export_xlsx_ms": round(p5_duration * 1000, 2),
        "total_ms": round(total_duration * 1000, 2),
        "throughput_rows_per_sec": throughput,
    }

    print(f"  Throughput: {throughput:,.1f} rows/sec")
    print(f"  Phase 1 (Ingestion):       {metrics['p1_ingest_ms']:>8.2f} ms")
    print(f"  Phase 2 (Profiling):       {metrics['p2_profiling_ms']:>8.2f} ms")
    print(f"  Phase 3 (Reconciliation):  {metrics['p3_reconciliation_ms']:>8.2f} ms")
    print(f"  Phase 4 (Clustering):      {metrics['p4_materiality_clustering_ms']:>8.2f} ms")
    print(f"  Phase 5 (Workbook Export): {metrics['p5_export_xlsx_ms']:>8.2f} ms")
    print(f"  Total Cycle:               {metrics['total_ms']:>8.2f} ms ({total_duration:.2f} s)")
    print(f"========================================================\n")

    # Bounded execution assertion
    assert total_duration <= max_duration_seconds, (
        f"Benchmark of {row_count} rows took {total_duration:.2f}s, exceeding maximum allowed {max_duration_seconds}s limit."
    )

    return metrics


def test_performance_benchmark_1k_rows(db_session: Session):
    """Benchmark 1,000 rows with mixed matching conditions."""
    metrics = _run_scale_benchmark(row_count=1_000, db=db_session, max_duration_seconds=5.0)
    assert metrics["dataset_rows"] == 1000
    assert metrics["p3_reconciliation_ms"] < 2500.0


def test_performance_benchmark_5k_rows(db_session: Session):
    """Benchmark 5,000 rows with mixed matching conditions."""
    metrics = _run_scale_benchmark(row_count=5_000, db=db_session, max_duration_seconds=12.0)
    assert metrics["dataset_rows"] == 5000
    assert metrics["p3_reconciliation_ms"] < 8000.0


def test_performance_benchmark_10k_rows_bounded_execution(db_session: Session):
    """Benchmark 10,000 rows with mixed matching conditions, enforcing bounded execution."""
    metrics = _run_scale_benchmark(row_count=10_000, db=db_session, max_duration_seconds=25.0)
    assert metrics["dataset_rows"] == 10000
    assert metrics["throughput_rows_per_sec"] > 500.0  # Must process at least 500 rows/sec
