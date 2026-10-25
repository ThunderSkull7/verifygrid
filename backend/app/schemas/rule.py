"""Pydantic schemas for the Versioned Rule Engine and Aggregation System (Batch 4)."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.multisource import SourceDefinition


class RuleSeverity(str, Enum):
    """Severity classification for rule evaluation violations."""

    BLOCKING = "BLOCKING"
    WARNING = "WARNING"
    INFO = "INFO"


class PredicateOperator(str, Enum):
    """Supported predicate operators for structured where_conditions."""

    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    IN = "in"
    NOT_IN = "not_in"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    BETWEEN = "between"
    REGEX = "regex"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class ToleranceMode(str, Enum):
    """Modes for numeric tolerance evaluation."""

    ABSOLUTE = "absolute"
    PERCENTAGE = "percentage"
    BOTH_OR = "both_or"    # Passes if either absolute OR percentage is satisfied
    BOTH_AND = "both_and"  # Passes only if BOTH absolute AND percentage are satisfied


class RuleConjunction(str, Enum):
    """Boolean conjunction for compound predicates."""

    AND = "AND"
    OR = "OR"


class WhereCondition(BaseModel):
    """Structured predicate condition for row-level filtering and assertions."""

    field: str = Field(description="Column name or attribute to evaluate (e.g. 'currency', 'status')")
    operator: PredicateOperator = Field(description="Comparison operator")
    value: Optional[Any] = Field(default=None, description="Target value, or [min, max] list for 'between'")
    target_field: Optional[str] = Field(
        default=None,
        description="Optional field name in target dataset when comparing two dynamic fields"
    )
    source_alias: Optional[str] = Field(
        default=None,
        description="Optional source alias scope (e.g. 'erp', 'bank'). If None, evaluates across active source."
    )
    severity: RuleSeverity = Field(
        default=RuleSeverity.WARNING,
        description="Severity when condition is treated as an assertion requirement"
    )
    description: Optional[str] = Field(default=None, description="Human-readable rule explanation")

    model_config = ConfigDict(extra="ignore")


class DateWindowRule(BaseModel):
    """Settlement and transaction lag verification rule."""

    source_date_field: str = Field(description="Date column name in baseline source dataset")
    target_date_field: str = Field(description="Date column name in comparison dataset")
    source_alias: Optional[str] = Field(default=None, description="Optional baseline source alias")
    target_alias: Optional[str] = Field(default=None, description="Optional comparison source alias")
    lag_days_before: int = Field(
        default=0,
        ge=0,
        description="Allowed lag in days before source date (target_date >= source_date - lag_days_before)"
    )
    lag_days_after: int = Field(
        default=0,
        ge=0,
        description="Allowed lag in days after source date (target_date <= source_date + lag_days_after)"
    )
    date_format: Optional[str] = Field(
        default=None,
        description="Optional explicit strftime date format (e.g. '%Y-%m-%d')"
    )
    severity: RuleSeverity = Field(
        default=RuleSeverity.WARNING,
        description="Violation severity"
    )
    description: Optional[str] = Field(
        default="Target date must fall within configured settlement date window",
        description="Rule explanation"
    )

    model_config = ConfigDict(extra="ignore")


class NumericToleranceRule(BaseModel):
    """Flexible numeric currency/amount comparison rule."""

    source_amount_field: str = Field(description="Amount column name in baseline source dataset")
    target_amount_field: str = Field(description="Amount column name in comparison dataset")
    source_alias: Optional[str] = Field(default=None, description="Baseline source alias")
    target_alias: Optional[str] = Field(default=None, description="Comparison source alias")
    absolute_tolerance: float = Field(
        default=0.0,
        ge=0.0,
        description="Acceptable absolute difference: abs(src - tgt) <= absolute_tolerance"
    )
    percentage_tolerance: float = Field(
        default=0.0,
        ge=0.0,
        description="Acceptable relative percentage difference (0-100%): abs(src - tgt)/src * 100 <= pct"
    )
    tolerance_mode: ToleranceMode = Field(
        default=ToleranceMode.ABSOLUTE,
        description="Evaluation mode: 'absolute', 'percentage', 'both_or', or 'both_and'"
    )
    severity: RuleSeverity = Field(
        default=RuleSeverity.BLOCKING,
        description="Violation severity"
    )
    description: Optional[str] = Field(default=None, description="Rule description")

    model_config = ConfigDict(extra="ignore")


class StatusTransitionRule(BaseModel):
    """Whitelist of valid state transitions across sources."""

    source_field: str = Field(default="status", description="Status column name in source dataset")
    target_field: str = Field(default="status", description="Status column name in target dataset")
    source_alias: Optional[str] = Field(default=None, description="Baseline source alias")
    target_alias: Optional[str] = Field(default=None, description="Target source alias")
    allowed_transitions: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Mapping of primary status -> list of permitted equivalent secondary statuses"
    )
    case_sensitive: bool = Field(default=False, description="Whether status comparison is case-sensitive")
    severity: RuleSeverity = Field(default=RuleSeverity.BLOCKING, description="Violation severity")
    description: Optional[str] = Field(
        default="Cross-source status transition must be permitted by whitelist",
        description="Rule description"
    )

    model_config = ConfigDict(extra="ignore")


class CompoundRule(BaseModel):
    """Custom rule joining multiple conditions with conjunction."""

    id: Optional[str] = None
    name: str = Field(description="Rule name")
    description: Optional[str] = None
    severity: RuleSeverity = Field(default=RuleSeverity.WARNING)
    conjunction: RuleConjunction = Field(default=RuleConjunction.AND)
    conditions: List[WhereCondition] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class AggregationConfig(BaseModel):
    """Configuration for one-to-many (1:N) and many-to-one (N:1) split-payment reconciliation."""

    enabled: bool = Field(default=False, description="Enable split-payment aggregation engine")
    parent_source_alias: str = Field(
        default="source_a",
        description="Alias of the dataset containing parent orders/invoices (the 1 in 1:N)"
    )
    child_source_alias: str = Field(
        default="source_b",
        description="Alias of the dataset containing child installments/payments (the N in 1:N)"
    )
    parent_key: str = Field(
        default="id",
        description="Unique identifier column in parent dataset (e.g. 'invoice_id')"
    )
    child_grouping_key: str = Field(
        default="parent_id",
        description="Foreign key column in child dataset linking to parent key"
    )
    parent_amount_field: str = Field(
        default="amount",
        description="Total expected amount column in parent dataset"
    )
    child_amount_field: str = Field(
        default="amount",
        description="Installment amount column in child dataset"
    )
    child_receipt_id_field: Optional[str] = Field(
        default=None,
        description="Optional unique installment receipt/transaction ID for duplicate receipt detection"
    )
    child_date_field: Optional[str] = Field(
        default=None,
        description="Optional date column on child installments for settlement date window verification"
    )
    parent_date_field: Optional[str] = Field(
        default=None,
        description="Optional date column on parent order for date window lag comparison"
    )
    numeric_tolerance: float = Field(
        default=0.0,
        ge=0.0,
        description="Absolute tolerance when comparing parent amount to sum of child installments"
    )
    percentage_tolerance: float = Field(
        default=0.0,
        ge=0.0,
        description="Percentage tolerance when comparing parent amount to sum of child installments"
    )
    allow_partial_payment: bool = Field(
        default=False,
        description="Treat sum(child) < parent as a non-fatal warning instead of discrepancy"
    )
    allow_overpayment: bool = Field(
        default=False,
        description="Treat sum(child) > parent as a non-fatal warning instead of discrepancy"
    )

    model_config = ConfigDict(extra="ignore")


class VersionedRuleConfig(BaseModel):
    """Versioned JSON rule specification snapshot stored with verification runs."""

    version: str = Field(default="1.0.0", description="Semantic rule schema version")
    name: Optional[str] = Field(default="Default Rule Configuration", description="Rule set name")
    description: Optional[str] = Field(default=None, description="Rule set description")
    where_conditions: List[WhereCondition] = Field(
        default_factory=list,
        description="Structured predicates for row-level filtering and assertions"
    )
    date_window_rules: List[DateWindowRule] = Field(
        default_factory=list,
        description="Settlement and transaction lag verification rules"
    )
    numeric_tolerance_rules: List[NumericToleranceRule] = Field(
        default_factory=list,
        description="Numeric currency absolute and percentage tolerance rules"
    )
    status_transition_rules: List[StatusTransitionRule] = Field(
        default_factory=list,
        description="Explicit state mapping whitelists across sources"
    )
    custom_rules: List[CompoundRule] = Field(
        default_factory=list,
        description="Compound custom rules joined with AND/OR logic"
    )
    aggregation_config: Optional[AggregationConfig] = Field(
        default=None,
        description="Optional 1:N split payment aggregation configuration"
    )

    model_config = ConfigDict(extra="ignore")


class RuleValidateRequest(BaseModel):
    """Payload to validate rule syntax and verify field existence against datasets."""

    rules: VersionedRuleConfig
    file_ids: Optional[List[uuid.UUID]] = Field(
        default_factory=list,
        description="Optional file IDs to check column existence against"
    )
    sources: Optional[List[SourceDefinition]] = Field(
        default_factory=list,
        description="Optional source definitions to resolve column presence by alias"
    )


class RuleValidateResponse(BaseModel):
    """Response containing rule syntax and field existence verification."""

    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    total_rules_checked: int = 0
    field_resolutions: Dict[str, bool] = Field(
        default_factory=dict,
        description="Map of field_name -> exists_on_datasets"
    )


class RulePreviewRequest(BaseModel):
    """Payload to dry-run and preview rule impact on uploaded files."""

    rules: VersionedRuleConfig
    sources: List[SourceDefinition] = Field(
        ...,
        min_length=2,
        description="Participating source datasets"
    )
    unified_keys: Optional[List[str]] = Field(
        default=None,
        description="Matching keys if running full reconciliation preview"
    )
    sample_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Number of rows per dataset to sample for dry-run"
    )


class RulePreviewResponse(BaseModel):
    """Impact summary of a dry-run rule preview."""

    total_evaluated: int
    passed_count: int
    exception_count: int
    exceptions_by_rule: Dict[str, int] = Field(default_factory=dict)
    exceptions_by_severity: Dict[str, int] = Field(default_factory=dict)
    sample_discrepancies: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Sample of exceptions triggered by rules"
    )
