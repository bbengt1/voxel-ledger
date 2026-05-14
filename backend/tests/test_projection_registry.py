"""Unit tests for the projection handler registry."""

from __future__ import annotations

import pytest
from app.events import registry as event_registry
from app.events.types import _test_event  # noqa: F401  (ensures TestEvent is registered)
from app.projections import registry as projection_registry


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Each test starts with a clean projection registry."""
    snapshot_by_event = {k: list(v) for k, v in projection_registry._BY_EVENT_TYPE.items()}
    snapshot_by_name = dict(projection_registry._BY_NAME)
    projection_registry._reset_for_tests()
    yield
    projection_registry._BY_EVENT_TYPE.clear()
    projection_registry._BY_NAME.clear()
    projection_registry._BY_EVENT_TYPE.update(snapshot_by_event)
    projection_registry._BY_NAME.update(snapshot_by_name)


async def _noop(event, session):  # pragma: no cover - never invoked here
    return None


def test_register_and_lookup_by_event_type() -> None:
    @projection_registry.projection(
        event_type="test.TestEvent",
        name="p1",
        read_model_tables=("projection_test_event",),
    )
    async def h(event, session):  # pragma: no cover
        return None

    handlers = projection_registry.handlers_for("test.TestEvent")
    assert [x.name for x in handlers] == ["p1"]
    assert handlers[0].read_model_tables == ("projection_test_event",)


def test_register_unknown_event_type_fails_loudly() -> None:
    assert not event_registry.is_registered("not.a.real.Event")
    with pytest.raises(projection_registry.ProjectionRegistryError) as exc:

        @projection_registry.projection(
            event_type="not.a.real.Event",
            name="bad",
            read_model_tables=("t",),
        )
        async def h(event, session):  # pragma: no cover
            return None

    assert "unregistered event type" in str(exc.value)


def test_wildcard_subscription_always_allowed() -> None:
    @projection_registry.projection(event_type="*", name="audit", read_model_tables=("audit",))
    async def h(event, session):  # pragma: no cover
        return None

    handlers = projection_registry.handlers_for("test.TestEvent")
    assert "audit" in [h.name for h in handlers]


def test_handler_name_collision_rejected() -> None:
    @projection_registry.projection(
        event_type="test.TestEvent",
        name="dupe",
        read_model_tables=("projection_test_event",),
    )
    async def h(event, session):  # pragma: no cover
        return None

    with pytest.raises(projection_registry.ProjectionRegistryError) as exc:

        @projection_registry.projection(
            event_type="test.TestEvent",
            name="dupe",
            read_model_tables=("projection_test_event",),
        )
        async def h2(event, session):  # pragma: no cover
            return None

    assert "collision" in str(exc.value)


def test_dispatch_order_is_deterministic_by_name() -> None:
    @projection_registry.projection(event_type="test.TestEvent", name="b", read_model_tables=("t",))
    async def hb(event, session):  # pragma: no cover
        return None

    @projection_registry.projection(event_type="test.TestEvent", name="a", read_model_tables=("t",))
    async def ha(event, session):  # pragma: no cover
        return None

    @projection_registry.projection(event_type="*", name="c", read_model_tables=("t",))
    async def hc(event, session):  # pragma: no cover
        return None

    names = [h.name for h in projection_registry.handlers_for("test.TestEvent")]
    assert names == ["a", "b", "c"]


def test_empty_read_model_tables_rejected() -> None:
    with pytest.raises(projection_registry.ProjectionRegistryError):

        @projection_registry.projection(event_type="test.TestEvent", name="x", read_model_tables=())
        async def h(event, session):  # pragma: no cover
            return None


def test_get_handler_unknown_name_raises() -> None:
    with pytest.raises(projection_registry.ProjectionRegistryError):
        projection_registry.get_handler("nope")
