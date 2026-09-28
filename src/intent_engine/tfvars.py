"""Export values for a documented module interface. Never run Terraform."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import Unresolvable

from .emit import EmitBlocked, Resolution
from .models import Review
from .output import write_bundle


def emit_tfvars(
    resolution: Resolution, review: Review, contract: Path, out_dir: Path
) -> list[Path]:
    try:
        content = contract.read_bytes()
        schema = json.loads(content)
        Draft202012Validator.check_schema(schema)
        values = _map_values(schema, resolution)
        # An empty registry forbids runtime retrieval of remote schema references.
        validator = Draft202012Validator(schema, registry=Registry())
        errors = sorted(error.message for error in validator.iter_errors(values))
    except (OSError, ValueError, SchemaError, Unresolvable) as exc:
        raise EmitBlocked(f"invalid module input contract: {exc}") from exc
    if errors:
        raise EmitBlocked("module input validation failed: " + "; ".join(errors))
    outputs = [out_dir / "terraform.tfvars.json", out_dir / "decision-trace.json"]
    sources = {contract.resolve(), Path(review.document).resolve()}
    if review.organisation:
        sources.update(Path(r.path).resolve() for r in review.organisation.references)
    if any(path.resolve() in sources for path in outputs):
        raise EmitBlocked("keep source documents and contracts separate from generated files")
    trace = {
        "sourceDocument": review.document,
        "sourceSha256": review.sha256,
        "module": schema["x-module"],
        "contractSha256": hashlib.sha256(content).hexdigest(),
        "validation": "input-contract-only",
        "organisation": review.organisation.model_dump(
            exclude={"references": {"__all__": {"content"}}}
        )
        if review.organisation
        else None,
        "policyAssessments": [a.model_dump() for a in resolution.assessments],
        "variables": {
            name: next(
                entry for entry in resolution.trace if entry["decision"] == spec["x-decision"]
            )
            for name, spec in schema["properties"].items()
            if name in values
        },
    }
    return write_bundle(
        out_dir,
        {
            path.name: json.dumps(payload, indent=2) + "\n"
            for path, payload in zip(outputs, (values, trace), strict=True)
        },
    )


def _map_values(schema: Any, resolution: Resolution) -> dict[str, Any]:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise EmitBlocked("module contract must describe an object")
    module = schema.get("x-module")
    if not isinstance(module, dict) or not all(
        isinstance(module.get(key), str) and module[key].strip() for key in ("source", "version")
    ):
        raise EmitBlocked("module contract needs x-module source and version")
    properties = schema.get("properties")
    if (
        not isinstance(properties, dict)
        or not properties
        or schema.get("additionalProperties") is not False
    ):
        raise EmitBlocked("module contract needs properties and additionalProperties: false")
    values = {}
    for name, spec in properties.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("x-decision"), str):
            raise EmitBlocked(f"{name}: an explicit x-decision mapping is required")
        key = spec["x-decision"]
        if key not in resolution.values:
            raise EmitBlocked(f"{name}: mapped decision '{key}' has no resolved value")
        values[name] = resolution.values[key]
    return values
