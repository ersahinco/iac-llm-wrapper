"""One offline output contract: the unmodified schemas from a pinned LZA release."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft7Validator, FormatChecker

LZA_VERSION = "1.16.3"
LZA_COMMIT = "e6cab2077ed57d638f8d7b18e5bce8519aa7d26d"
CONFIG_FILES = tuple(
    f"{name}-config.yaml"
    for name in ("organization", "accounts", "global", "iam", "network", "security")
)


@lru_cache(maxsize=len(CONFIG_FILES))
def _validator(filename: str) -> Draft7Validator:
    path = resources.files("intent_engine").joinpath("schemas", filename.replace(".yaml", ".json"))
    schema = json.loads(path.read_text("utf-8"))
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema, format_checker=FormatChecker())


def validate_configs(documents: dict[str, Any]) -> list[str]:
    """Return file/path errors. This checks shape, not AWS state or deployment readiness."""
    errors: list[str] = []
    for filename in CONFIG_FILES:
        if filename not in documents:
            errors.append(f"{filename}: required configuration file is missing")
            continue
        for error in _validator(filename).iter_errors(documents[filename]):
            path = ".".join(str(part) for part in error.absolute_path) or "(root)"
            errors.append(f"{filename}:{path}: {error.message}")
    return sorted(errors)
