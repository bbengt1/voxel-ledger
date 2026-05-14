"""Smoke-test event type. The only purpose is to give the test suite (and
Phase 1.2 projection scaffolding) something real to register and append.

Do not use this for business logic. Real business events live under their
bounded context (accounting, inventory, sales, ...).
"""

from __future__ import annotations

from pydantic import BaseModel

from app.events.registry import register_event

TYPE = "test.TestEvent"


class TestEventPayload(BaseModel):
    # Tell pytest this is not a test class (the ``Test`` prefix would
    # otherwise trigger collection).
    __test__ = False

    value: str


register_event(TYPE, TestEventPayload)
