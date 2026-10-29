"""Compatibility re-export for the discrepancy review decision model.

The canonical definition lives in ``app.models.verification_run`` beside the
discrepancy it references, matching the deployed ORM contract.
"""

from app.models.verification_run import DiscrepancyReviewDecision

__all__ = ["DiscrepancyReviewDecision"]
