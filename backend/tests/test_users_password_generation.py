"""Password generator (Phase 1.6)."""

from __future__ import annotations

from app.services.users import (
    _PWD_DIGIT,
    _PWD_LOWER,
    _PWD_SYMBOL,
    _PWD_UPPER,
    GENERATED_PASSWORD_LENGTH,
    generate_password,
)


def test_password_length() -> None:
    pwd = generate_password()
    assert len(pwd) == GENERATED_PASSWORD_LENGTH == 20


def test_password_has_every_class() -> None:
    # Run several times — the loop only retries if a class is missing,
    # so this both proves the generator terminates and that all classes
    # appear.
    for _ in range(50):
        pwd = generate_password()
        assert any(c in _PWD_UPPER for c in pwd)
        assert any(c in _PWD_LOWER for c in pwd)
        assert any(c in _PWD_DIGIT for c in pwd)
        assert any(c in _PWD_SYMBOL for c in pwd)


def test_passwords_are_unique() -> None:
    seen = {generate_password() for _ in range(100)}
    # Birthday paradox is irrelevant at this size + 20-char alphabet — every
    # password should be unique.
    assert len(seen) == 100
