"""Pieces-math property test (Phase 5.2, #78).

Pieces produced for a job equals ``min(parts_per_set * runs_completed)``
across plates, with these edge cases:
  - no plates → 0
  - any plate with ``runs_completed == 0`` → 0
"""

from __future__ import annotations

import random
import uuid
from types import SimpleNamespace

import pytest
from app.services.jobs import pieces_produced


def _mk_job(plates: list[tuple[int, int]]):
    """Build a fake Job-shaped object for the pure pieces_produced helper."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        plates=[SimpleNamespace(parts_per_set=p, runs_completed=r) for p, r in plates],
    )


def test_no_plates_zero_pieces() -> None:
    assert pieces_produced(_mk_job([])) == 0


def test_any_zero_runs_produces_zero() -> None:
    assert pieces_produced(_mk_job([(2, 5), (3, 0)])) == 0
    assert pieces_produced(_mk_job([(1, 0)])) == 0


def test_single_plate_simple() -> None:
    assert pieces_produced(_mk_job([(4, 3)])) == 12


def test_min_across_plates() -> None:
    # plate A: 2 * 5 = 10
    # plate B: 3 * 4 = 12
    # plate C: 5 * 1 = 5  <- min
    assert pieces_produced(_mk_job([(2, 5), (3, 4), (5, 1)])) == 5


@pytest.mark.parametrize("seed", list(range(50)))
def test_property_min_holds_for_random_inputs(seed: int) -> None:
    rng = random.Random(seed)
    n_plates = rng.randint(1, 8)
    plates = [(rng.randint(1, 12), rng.randint(0, 10)) for _ in range(n_plates)]
    expected = min(p * r for p, r in plates)
    assert pieces_produced(_mk_job(plates)) == expected
