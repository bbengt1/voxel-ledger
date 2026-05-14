"""Lightweight grep guardrail: ``COUNT(`` must never appear as executable
code in the reference number service.

v1 incident #243 was caused by COUNT-based numbering. The intentional
mentions of ``COUNT(`` in the module docstring and the warning-banner
comment are the *reason* this guardrail exists, so we strip docstrings
and comments before scanning — and look for actual SQL/Python usage."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

SERVICE_PATH = Path(__file__).resolve().parent.parent / "app" / "services" / "reference_number.py"


def _strip_comments_and_docstrings(src: str) -> str:
    """Return ``src`` with all ``#`` comments and string/docstring
    literals replaced by single spaces, preserving line numbers."""
    # Drop comments via tokenize.
    out_tokens: list[str] = []
    g = tokenize.generate_tokens(io.StringIO(src).readline)
    for tok_type, tok_str, *_ in g:
        if tok_type == tokenize.COMMENT:
            continue
        out_tokens.append(tok_str if tok_type != tokenize.STRING else '""')
    no_comments = " ".join(out_tokens)
    # Belt-and-suspenders: drop anything that looks like a triple-quoted
    # block in case tokenize missed something exotic.
    no_comments = re.sub(r'""".*?"""', '""', no_comments, flags=re.DOTALL)
    return no_comments


def test_no_count_in_reference_number_service() -> None:
    src = SERVICE_PATH.read_text(encoding="utf-8")

    # Sanity: file must parse — otherwise the guardrail is meaningless.
    ast.parse(src)

    scrubbed = _strip_comments_and_docstrings(src)
    # Case-insensitive so neither ``count(`` nor ``COUNT(`` slips by.
    assert "count(" not in scrubbed.lower(), (
        "COUNT( appears in executable code of reference_number.py — " "see v1 issue #243"
    )
