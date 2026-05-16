"""Customer-credit-balance projection (Phase 7.4, #112).

Consumes ``ar.CustomerCreditAccrued`` / ``ar.CustomerCreditApplied``
events and rebuilds the ``customer_credit_balance`` row. Replay-safe:
INSERT ... ON CONFLICT DO UPDATE with a signed delta is associative.
"""

from app.projections.customer_credit import handlers  # noqa: F401
