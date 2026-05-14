"""Custom-fields service-layer validation tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.custom_field import CustomFieldType
from app.services import custom_fields as cf_service
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
async def _create_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_required_missing_raises(session: AsyncSession) -> None:
    await cf_service.create(
        session,
        entity_type="material",
        key="supplier_code",
        label="Supplier Code",
        field_type=CustomFieldType.STRING,
        options=None,
        required=True,
        default_value=None,
        display_order=0,
        actor_user_id=None,
    )
    await session.flush()

    with pytest.raises(cf_service.CustomFieldValidationError) as exc:
        await cf_service.validate_payload("material", {}, session=session)
    assert "supplier_code" in exc.value.errors


@pytest.mark.asyncio
async def test_string_type_check(session: AsyncSession) -> None:
    await cf_service.create(
        session,
        entity_type="material",
        key="supplier_code",
        label="Supplier Code",
        field_type=CustomFieldType.STRING,
        options=None,
        required=False,
        default_value=None,
        display_order=0,
        actor_user_id=None,
    )
    with pytest.raises(cf_service.CustomFieldValidationError):
        await cf_service.validate_payload("material", {"supplier_code": 42}, session=session)


@pytest.mark.asyncio
async def test_number_round_trip_normalization(session: AsyncSession) -> None:
    await cf_service.create(
        session,
        entity_type="material",
        key="weight_kg",
        label="Weight (kg)",
        field_type=CustomFieldType.NUMBER,
        options=None,
        required=False,
        default_value=None,
        display_order=0,
        actor_user_id=None,
    )
    result = await cf_service.validate_payload("material", {"weight_kg": "12.5"}, session=session)
    assert result["weight_kg"] == str(Decimal("12.5"))


@pytest.mark.asyncio
async def test_number_invalid_rejected(session: AsyncSession) -> None:
    await cf_service.create(
        session,
        entity_type="material",
        key="weight_kg",
        label="Weight (kg)",
        field_type=CustomFieldType.NUMBER,
        options=None,
        required=False,
        default_value=None,
        display_order=0,
        actor_user_id=None,
    )
    with pytest.raises(cf_service.CustomFieldValidationError):
        await cf_service.validate_payload(
            "material", {"weight_kg": "not-a-number"}, session=session
        )


@pytest.mark.asyncio
async def test_boolean_type_check(session: AsyncSession) -> None:
    await cf_service.create(
        session,
        entity_type="material",
        key="is_hazardous",
        label="Hazardous",
        field_type=CustomFieldType.BOOLEAN,
        options=None,
        required=False,
        default_value=None,
        display_order=0,
        actor_user_id=None,
    )
    out = await cf_service.validate_payload("material", {"is_hazardous": True}, session=session)
    assert out["is_hazardous"] is True
    with pytest.raises(cf_service.CustomFieldValidationError):
        await cf_service.validate_payload("material", {"is_hazardous": "yes"}, session=session)


@pytest.mark.asyncio
async def test_date_iso_parsing(session: AsyncSession) -> None:
    await cf_service.create(
        session,
        entity_type="material",
        key="received_on",
        label="Received On",
        field_type=CustomFieldType.DATE,
        options=None,
        required=False,
        default_value=None,
        display_order=0,
        actor_user_id=None,
    )
    out = await cf_service.validate_payload(
        "material", {"received_on": "2026-05-14"}, session=session
    )
    assert out["received_on"].startswith("2026-05-14")
    with pytest.raises(cf_service.CustomFieldValidationError):
        await cf_service.validate_payload(
            "material", {"received_on": "not-a-date"}, session=session
        )


@pytest.mark.asyncio
async def test_select_value_must_be_in_options(session: AsyncSession) -> None:
    await cf_service.create(
        session,
        entity_type="material",
        key="grade",
        label="Grade",
        field_type=CustomFieldType.SELECT,
        options=[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
        required=False,
        default_value=None,
        display_order=0,
        actor_user_id=None,
    )
    out = await cf_service.validate_payload("material", {"grade": "a"}, session=session)
    assert out["grade"] == "a"
    with pytest.raises(cf_service.CustomFieldValidationError):
        await cf_service.validate_payload("material", {"grade": "z"}, session=session)


@pytest.mark.asyncio
async def test_unknown_keys_tolerated(session: AsyncSession) -> None:
    # No fields defined; an unknown key should pass through.
    out = await cf_service.validate_payload("material", {"who_knows": "anything"}, session=session)
    assert out == {"who_knows": "anything"}
