"""Live cost-calc endpoint (Phase 5.3, #79).

``POST /api/v1/jobs/calculate``: returns a full cost breakdown for either
an existing job (by ``job_id``) or a proposed shape (by ``inputs``). The
endpoint is read-only computation — every authenticated role can call it
because every operational role consumes cost data (sales for quotes,
production for plan-feasibility, bookkeepers for review, viewers for
dashboards).

The router mounts at ``/jobs/calculate`` so it shares the ``/jobs``
prefix and tag with the rest of the production module. Because FastAPI
routes are matched in registration order, this router is included
**before** the jobs router so ``/jobs/calculate`` doesn't get captured
by the more permissive ``/jobs/{job_id}`` matcher.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.cost_calc import (
    CalcRequest,
    CalcResultResponse,
    PerPlateCostResponse,
)
from app.services.cost_engine.calculator import (
    CalcInputs,
    CalcResult,
    PlateInput,
)
from app.services.cost_engine.service import (
    CostEngineService,
    MissingRateConfigError,
)
from app.services.jobs import JobNotFoundError

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _result_to_response(result: CalcResult) -> CalcResultResponse:
    return CalcResultResponse(
        pieces_per_set=result.pieces_per_set,
        sets_required=result.sets_required,
        material_cost=result.material_cost,
        supply_cost=result.supply_cost,
        labor_cost=result.labor_cost,
        machine_cost=result.machine_cost,
        overhead_cost=result.overhead_cost,
        total_cost=result.total_cost,
        cost_per_piece=result.cost_per_piece,
        suggested_unit_price=result.suggested_unit_price,
        per_plate=[
            PerPlateCostResponse(
                plate_index=row.plate_index,
                parts_per_set=row.parts_per_set,
                runs=row.runs,
                material_cost=row.material_cost,
                labor_cost=row.labor_cost,
                machine_cost=row.machine_cost,
            )
            for row in result.per_plate
        ],
    )


@router.post(
    "/calculate",
    response_model=CalcResultResponse,
    status_code=status.HTTP_200_OK,
)
async def calculate_cost(
    payload: CalcRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[
        User,
        Depends(require_role("owner", "production", "sales", "bookkeeper", "viewer")),
    ],
) -> CalcResultResponse:
    try:
        if payload.job_id is not None:
            result = await CostEngineService.calculate_for_job(payload.job_id, session=session)
        else:
            assert payload.inputs is not None  # guaranteed by CalcRequest validator
            inputs = CalcInputs(
                plates=[
                    PlateInput(
                        parts_per_set=p.parts_per_set,
                        print_minutes=p.print_minutes,
                        print_grams_by_material=p.print_grams_by_material,
                        setup_minutes=p.setup_minutes,
                        assigned_printer_ids=p.assigned_printer_ids,
                    )
                    for p in payload.inputs.plates
                ],
                quantity_ordered=payload.inputs.quantity_ordered,
            )
            result = await CostEngineService.calculate_for_inputs(inputs, session=session)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except MissingRateConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    return _result_to_response(result)
