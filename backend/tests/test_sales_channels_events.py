"""Sales-channel event-type round-trip + audit projection wiring."""

from __future__ import annotations

import uuid

import pytest
from app.events.registry import (
    InvalidEventPayloadError,
    is_registered,
    validate_payload,
)
from app.events.types import sales as sales_events
from app.projections.audit.excerpts import compute_excerpt
from app.projections.audit.summaries import render_summary


def test_all_four_event_types_are_registered() -> None:
    for t in (
        sales_events.TYPE_SALES_CHANNEL_CREATED,
        sales_events.TYPE_SALES_CHANNEL_UPDATED,
        sales_events.TYPE_SALES_CHANNEL_ARCHIVED,
        sales_events.TYPE_SALES_CHANNEL_UNARCHIVED,
    ):
        assert is_registered(t), f"event type {t} should be registered"


def test_created_payload_round_trip() -> None:
    cid = uuid.uuid4()
    normalized = validate_payload(
        sales_events.TYPE_SALES_CHANNEL_CREATED,
        {
            "sales_channel_id": str(cid),
            "name": "Shopify",
            "slug": "shopify",
            "kind": "direct_web",
            "fee_model": "percent_plus_flat",
            "fee_percent": "0.0290",
            "fee_flat": "0.30",
            "default_revenue_account_id": None,
            "default_fee_account_id": None,
            "external_id_format_hint": "^SHOP-\\d{10}$",
        },
    )
    assert normalized["sales_channel_id"] == str(cid)
    assert normalized["fee_model"] == "percent_plus_flat"
    assert normalized["fee_percent"] == "0.0290"


def test_created_payload_rejects_extra_field() -> None:
    with pytest.raises(InvalidEventPayloadError):
        validate_payload(
            sales_events.TYPE_SALES_CHANNEL_CREATED,
            {
                "sales_channel_id": str(uuid.uuid4()),
                "name": "X",
                "slug": "x",
                "kind": "pos",
                "fee_model": "none",
                "unexpected": "field",
            },
        )


def test_updated_payload_round_trip() -> None:
    normalized = validate_payload(
        sales_events.TYPE_SALES_CHANNEL_UPDATED,
        {
            "sales_channel_id": str(uuid.uuid4()),
            "before": {"name": "Old"},
            "after": {"name": "New"},
        },
    )
    assert normalized["before"] == {"name": "Old"}


def test_archived_and_unarchived_payload_round_trip() -> None:
    cid = uuid.uuid4()
    for t in (
        sales_events.TYPE_SALES_CHANNEL_ARCHIVED,
        sales_events.TYPE_SALES_CHANNEL_UNARCHIVED,
    ):
        validate_payload(t, {"sales_channel_id": str(cid)})


def test_audit_summary_created_mentions_slug_and_kind() -> None:
    msg = render_summary(
        sales_events.TYPE_SALES_CHANNEL_CREATED,
        {
            "sales_channel_id": str(uuid.uuid4()),
            "name": "Shopify",
            "slug": "shopify",
            "kind": "direct_web",
            "fee_model": "percent_plus_flat",
        },
        actor_label="owner@example.com",
        aggregate_type="sales_channel",
        aggregate_id="00000000-0000-0000-0000-000000000000",
    )
    assert "owner@example.com" in msg
    assert "shopify" in msg
    assert "direct_web" in msg


def test_audit_summary_updated_mentions_diff() -> None:
    msg = render_summary(
        sales_events.TYPE_SALES_CHANNEL_UPDATED,
        {
            "sales_channel_id": str(uuid.uuid4()),
            "before": {"fee_percent": "0.029"},
            "after": {"fee_percent": "0.034"},
        },
        actor_label="owner@example.com",
        aggregate_type="sales_channel",
        aggregate_id="00000000-0000-0000-0000-000000000000",
    )
    assert "fee_percent" in msg
    assert "0.029" in msg and "0.034" in msg


def test_audit_summary_archive_unarchive() -> None:
    cid = str(uuid.uuid4())
    for t, verb in (
        (sales_events.TYPE_SALES_CHANNEL_ARCHIVED, "archived"),
        (sales_events.TYPE_SALES_CHANNEL_UNARCHIVED, "unarchived"),
    ):
        msg = render_summary(
            t,
            {"sales_channel_id": cid},
            actor_label="owner@example.com",
            aggregate_type="sales_channel",
            aggregate_id=cid,
        )
        assert verb in msg
        assert cid in msg


def test_audit_excerpt_created_whitelisted_fields() -> None:
    payload = {
        "sales_channel_id": str(uuid.uuid4()),
        "name": "Shopify",
        "slug": "shopify",
        "kind": "direct_web",
        "fee_model": "percent_plus_flat",
        "fee_percent": "0.0290",
        "fee_flat": "0.30",
        "default_revenue_account_id": None,
        "default_fee_account_id": None,
        "external_id_format_hint": "^SHOP-\\d{10}$",
    }
    excerpt = compute_excerpt(sales_events.TYPE_SALES_CHANNEL_CREATED, payload)
    assert excerpt is not None
    assert excerpt["name"] == "Shopify"
    assert excerpt["slug"] == "shopify"
    assert excerpt["kind"] == "direct_web"
    assert excerpt["fee_model"] == "percent_plus_flat"
    assert excerpt["fee_percent"] == "0.0290"
    assert excerpt["fee_flat"] == "0.30"
    assert excerpt["external_id_format_hint"] == "^SHOP-\\d{10}$"
    # ``sales_channel_id`` is the aggregate id; not whitelisted into excerpt.
    assert "sales_channel_id" not in excerpt


def test_audit_excerpt_updated_carries_before_after() -> None:
    excerpt = compute_excerpt(
        sales_events.TYPE_SALES_CHANNEL_UPDATED,
        {
            "sales_channel_id": str(uuid.uuid4()),
            "before": {"fee_percent": "0.029"},
            "after": {"fee_percent": "0.034"},
        },
    )
    assert excerpt is not None
    assert excerpt["before"] == {"fee_percent": "0.029"}
    assert excerpt["after"] == {"fee_percent": "0.034"}


def test_audit_excerpt_archive_unarchive_have_none_excerpt() -> None:
    """Archive / unarchive carry only ``sales_channel_id`` — no excerpt
    is registered so ``compute_excerpt`` returns ``None``."""
    for t in (
        sales_events.TYPE_SALES_CHANNEL_ARCHIVED,
        sales_events.TYPE_SALES_CHANNEL_UNARCHIVED,
    ):
        assert (
            compute_excerpt(t, {"sales_channel_id": str(uuid.uuid4())}) is None
        ), f"{t} should not produce an excerpt"
