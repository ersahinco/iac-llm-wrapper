"""One selected organisation snapshot: references are never client answers."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML, YAMLError

from .catalog import _check_references
from .ingest import IngestError
from .models import (
    Assessment,
    Conflict,
    Decision,
    Evidence,
    Fact,
    Integration,
    Organisation,
    Policy,
    Reference,
)


def load_organisation(path: Path, catalog: dict[str, Decision]) -> Organisation:
    try:
        content = path.read_text("utf-8")
        org = Organisation.model_validate(YAML(typ="safe").load(content))
        for reference in org.references:
            source = (path.parent / reference.path).resolve()
            reference.content = source.read_text("utf-8")
            reference.sha256 = hashlib.sha256(reference.content.encode()).hexdigest()
            reference.path = str(source)
        if any(r.id == "organisation-manifest" for r in org.references):
            raise ValueError("organisation-manifest is a reserved reference ID")
        org.references.append(
            Reference(
                id="organisation-manifest",
                path=str(path.resolve()),
                kind="context",
                sha256=hashlib.sha256(content.encode()).hexdigest(),
                content=content,
            )
        )
        ids = [reference.id for reference in org.references]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate reference IDs")
        _validate_scope(org, catalog)
        configuration_data(org)
    except (OSError, UnicodeError, YAMLError, ValidationError, ValueError, TypeError) as exc:
        raise IngestError(f"{path}: invalid organisation references: {exc}") from exc
    return org


def _validate_scope(org: Organisation, catalog: dict[str, Decision]) -> None:
    for kind, group in (
        ("system", org.systems),
        ("integration", org.integrations),
        ("policy", org.policies),
    ):
        if len({item.id for item in group}) != len(group):
            raise ValueError(f"duplicate {kind} IDs")
        for item in group:
            evidence_text(org, item.evidence)  # Validate sources before graph replacement.
    decisions = organisation_catalog(catalog, org)
    system_ids = {system.id for system in org.systems}
    for integration in org.integrations:
        if integration.source not in system_ids or integration.target not in system_ids:
            raise ValueError(f"{integration.id}: unknown integration endpoint")
    scopes: list[Integration | Policy] = [*org.integrations, *org.policies]
    for scoped in scopes:
        if not set(scoped.decision_keys) <= decisions.keys():
            raise ValueError(f"{scoped.id}: unknown decision in scope")
    if org.policies and sum(r.kind == "policy" for r in org.references) != 1:
        raise ValueError("select exactly one OPA policy file for this example")


def organisation_catalog(
    catalog: dict[str, Decision], org: Organisation | None
) -> dict[str, Decision]:
    result = dict(catalog)
    for decision in org.questions if org else []:
        if decision.key in result:
            raise IngestError(f"organisation question duplicates catalog key: {decision.key}")
        if decision.default is not None:
            raise IngestError("organisation integration questions require explicit answers")
        result[decision.key] = decision
    _check_references(result, "organisation questions")
    return result


def evidence_text(org: Organisation, evidence: Evidence) -> str:
    reference = next((r for r in org.references if r.id == evidence.reference), None)
    if reference is None:
        raise ValueError(f"unknown evidence reference: {evidence.reference}")
    lines = reference.content.splitlines()
    if evidence.line > len(lines) or evidence.quote not in lines[evidence.line - 1]:
        raise ValueError(f"{reference.path}:{evidence.line}: quote is absent from source")
    return f"{reference.path}:{evidence.line} — {evidence.quote}"


def configuration_data(org: Organisation) -> dict[str, Any]:
    result = {
        r.id: YAML(typ="safe").load(r.content) for r in org.references if r.kind == "configuration"
    }
    json.dumps(result, allow_nan=False)  # Only JSON-compatible configuration reaches OPA.
    return result


def assess(org: Organisation | None, values: dict[str, Any]) -> list[Assessment]:
    if org is None or not org.policies:
        return []
    payload = json.dumps(
        {"decisions": values, "references": configuration_data(org)}, sort_keys=True
    )
    input_sha = hashlib.sha256(payload.encode()).hexdigest()
    try:
        if shutil.which("opa") is None:
            raise ValueError("OPA not installed; organisation policies were not assessed")
        policy = next(r for r in org.references if r.kind == "policy")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "organisation.rego"
            path.write_text(policy.content, encoding="utf-8")
            completed = subprocess.run(
                [
                    "opa",
                    "eval",
                    "--format=json",
                    "--strict",
                    "--stdin-input",
                    "--data",
                    str(path),
                    "data.organisation.assessments",
                ],
                input=payload,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
        if completed.returncode:
            raise ValueError(completed.stderr.strip() or completed.stdout.strip() or "OPA failed")
        raw = json.loads(completed.stdout)["result"][0]["expressions"][0]["value"]
        if not isinstance(raw, list):
            raise ValueError("OPA must return an assessment list")
        results = [Assessment.model_validate(row) for row in raw]
        expected = {p.id for p in org.policies}
        if len(results) != len(expected) or {r.policy_id for r in results} != expected:
            raise ValueError("OPA must assess every selected policy exactly once")
        for result in results:
            result.input_sha256 = input_sha
        return results
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError, TypeError) as exc:
        return [
            Assessment(
                policy_id=p.id, status="not-assessed", message=str(exc), input_sha256=input_sha
            )
            for p in org.policies
        ]


def policy_conflicts(
    org: Organisation | None, assessments: list[Assessment], facts: list[Fact], document: str
) -> list[Conflict]:
    if org is None:
        return []
    policies = {p.id: p for p in org.policies}
    return [
        Conflict(
            code="ORG_POLICY_CONFLICT"
            if result.status == "conflict"
            else "ORG_POLICY_NOT_ASSESSED",
            message=f"{result.policy_id}: {result.message}",
            decision_keys=policies[result.policy_id].decision_keys,
            evidence=[evidence_text(org, policies[result.policy_id].evidence)]
            + [
                f"{document}:{f.line} — {f.decision_key}: {f.value}"
                for f in facts
                if f.decision_key in policies[result.policy_id].decision_keys
            ]
            + [
                f"{r.path} (sha256 {r.sha256})" for r in org.references if r.kind == "configuration"
            ],
        )
        for result in assessments
        if result.status in {"conflict", "not-assessed"}
    ]
