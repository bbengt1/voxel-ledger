"""Storage path computation is UUID-prefixed: same filename → distinct paths."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.attachments.storage import (
    compute_storage_path,
    slugify_filename,
)


def test_two_uploads_same_name_yield_distinct_paths() -> None:
    p1 = compute_storage_path("report.pdf")
    p2 = compute_storage_path("report.pdf")
    assert p1 != p2
    # Both should end with the original slug.
    assert p1.endswith("report.pdf")
    assert p2.endswith("report.pdf")


def test_path_has_year_month_prefix() -> None:
    now = datetime(2026, 5, 14, tzinfo=UTC)
    p = compute_storage_path("foo.txt", now=now)
    assert p.startswith("2026/05/")


def test_slug_truncates_to_100_chars() -> None:
    long_name = "a" * 500 + ".txt"
    slug = slugify_filename(long_name)
    assert len(slug) <= 100
    # Extension preserved.
    assert slug.endswith(".txt")


def test_slug_strips_unsafe_chars() -> None:
    slug = slugify_filename("../../etc/passwd")
    # Just the basename, with unsafe chars collapsed.
    assert "/" not in slug
    assert ".." not in slug


def test_slug_empty_falls_back_to_file() -> None:
    assert slugify_filename("") == "file"
    assert slugify_filename("///") == "file"
