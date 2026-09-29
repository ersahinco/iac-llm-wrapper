"""Parse the complete client document into sourced statements and explicit answers."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .models import Decision, Document, Fact, Statement

_LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_HEADING = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*#*$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_DECORATION = re.compile(r"[`*_]")


class IngestError(Exception):
    """The document could not be read. Not an extraction result."""


def normalize_key(text: str) -> str:
    cleaned = _DECORATION.sub("", text).strip().lower()
    cleaned = re.sub(r"[\s/-]+", "_", cleaned)
    return re.sub(r"[^a-z0-9_]", "", cleaned)


def read_document(path: Path) -> Document:
    if not path.is_file():
        raise IngestError(f"{path}: document not found")
    try:
        text = path.read_text("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise IngestError(f"{path}: document could not be read: {exc}") from exc
    if not text.strip():
        raise IngestError(f"{path}: document is empty")

    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Document(path=str(path), sha256=sha256, statements=_statements(text))


def _statements(text: str) -> list[Statement]:
    statements: list[Statement] = []
    section = "(document root)"
    in_fence = False

    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip()
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or not line.strip():
            continue
        heading = _HEADING.match(line)
        if heading:
            section = heading.group("title").strip()
            continue
        statements.append(
            Statement(id=f"s{number}", text=line.strip(), section=section, line=number)
        )
    return statements


def extract_facts(document: Document, catalog: dict[str, Decision]) -> list[Fact]:
    """Recover `decision: value` answers. Unmatched prose stays prose."""
    index: dict[str, str] = {}
    for decision in catalog.values():
        index[normalize_key(decision.key)] = decision.key
        index.setdefault(normalize_key(decision.label), decision.key)
    facts: list[Fact] = []
    for statement in document.statements:
        left, _, raw = _LIST_MARKER.sub("", statement.text, count=1).partition(":")
        value = raw.strip()
        decision_key = index.get(normalize_key(left))
        if not left.strip() or not value or decision_key is None:
            continue
        facts.append(
            Fact(
                decision_key=decision_key,
                value=value,
                section=statement.section,
                line=statement.line,
                origin="document",
                statement_id=statement.id,
            )
        )
    return facts
