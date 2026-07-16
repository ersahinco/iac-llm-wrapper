"""Digest and verification helpers for plan-ready bundle replay."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .contracts import PLAN_READY_BUNDLE_CONTRACT, TargetContract
from .paths import BundleFileError, resolve_bundle_file
from .patterns import GLOBAL_REGISTRY
from .validator import Violation
from .yaml_utils import load_bundle_yaml_mapping

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 identity of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay_artifact_digest(path: Path) -> str:
    """Return the stable replay identity for a generated artifact."""
    if path.name != "decision-audit.yaml":
        return sha256_file(path)
    text = re.sub(
        r"(^\s*-?\s*timestamp:\s*).+$",
        r"\1<TIMESTAMP>",
        path.read_text(),
        flags=re.MULTILINE,
    )
    return hashlib.sha256(text.encode()).hexdigest()


def contract_digest(contract: TargetContract) -> str:
    """Return the stable identity of a target contract."""
    payload = contract.model_dump(by_alias=True)
    rendered = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(rendered.encode()).hexdigest()


def verify_replay_manifest(bundle: Path, pattern: str) -> list[Violation]:
    """Verify source, contract, and artifact identities before target execution."""
    try:
        manifest = load_bundle_yaml_mapping(bundle, "replay-manifest.yaml")
    except (BundleFileError, ValueError) as exc:
        return [_violation("REPLAY_MANIFEST_INVALID", str(exc))]

    violations: list[Violation] = []
    if manifest.get("schemaVersion") != "intent-engine/replay-manifest/v1":
        violations.append(_violation("REPLAY_SCHEMA_UNSUPPORTED", "Unsupported replay schema."))
    if manifest.get("pattern") != pattern:
        violations.append(
            _violation(
                "REPLAY_PATTERN_MISMATCH",
                f"Replay pattern must be '{pattern}', got {manifest.get('pattern')!r}.",
            )
        )
    violations.extend(_verify_source(manifest.get("source")))
    violations.extend(_verify_contracts(manifest.get("contracts"), pattern))
    artifacts = manifest.get("artifacts")
    files = artifacts.get("files") if isinstance(artifacts, dict) else None
    violations.extend(_verify_files(bundle, files))
    return violations


def _verify_source(value: Any) -> list[Violation]:
    if not isinstance(value, dict):
        return [_violation("REPLAY_SOURCE_INVALID", "Replay source must be a mapping.")]
    if not isinstance(value.get("mode"), str) or not value["mode"]:
        return [_violation("REPLAY_SOURCE_INVALID", "Replay source mode is missing.")]
    digest = value.get("sha256")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        return [_violation("REPLAY_SOURCE_INVALID", "Replay source SHA-256 is invalid.")]
    return []


def _verify_contracts(value: Any, pattern: str) -> list[Violation]:
    if not isinstance(value, list):
        return [_violation("REPLAY_CONTRACTS_INVALID", "Replay contracts must be a list.")]
    expected_contracts = [*GLOBAL_REGISTRY.get(pattern).contracts, PLAN_READY_BUNDLE_CONTRACT]
    expected = {contract.name: contract_digest(contract) for contract in expected_contracts}
    seen: set[str] = set()
    violations: list[Violation] = []
    for item in value:
        if not isinstance(item, dict):
            violations.append(
                _violation("REPLAY_CONTRACT_INVALID", "Replay contract entry must be a mapping.")
            )
            continue
        name = item.get("name")
        digest = item.get("sha256")
        if not isinstance(name, str) or name not in expected:
            violations.append(
                _violation("REPLAY_CONTRACT_UNKNOWN", f"Unexpected replay contract: {name!r}.")
            )
            continue
        if name in seen:
            violations.append(
                _violation("REPLAY_CONTRACT_DUPLICATE", f"Duplicate replay contract: {name}.")
            )
            continue
        seen.add(name)
        if digest != expected[name]:
            violations.append(
                _violation("REPLAY_CONTRACT_CHANGED", f"Replay contract changed: {name}.")
            )
    for name in sorted(expected.keys() - seen):
        violations.append(
            _violation("REPLAY_CONTRACT_MISSING", f"Replay contract is missing: {name}.")
        )
    return violations


def _verify_files(bundle: Path, value: Any) -> list[Violation]:
    if not isinstance(value, list) or not value:
        return [
            _violation("REPLAY_FILES_INVALID", "Replay artifact files must be a non-empty list.")
        ]
    seen: set[str] = set()
    violations: list[Violation] = []
    for item in value:
        if not isinstance(item, dict):
            violations.append(
                _violation("REPLAY_FILE_INVALID", "Replay artifact entry must be a mapping.")
            )
            continue
        name = item.get("name")
        digest = item.get("sha256")
        if not isinstance(name, str) or name == "replay-manifest.yaml":
            violations.append(
                _violation("REPLAY_FILE_INVALID", f"Invalid replay artifact name: {name!r}.")
            )
            continue
        if name in seen:
            violations.append(
                _violation("REPLAY_FILE_DUPLICATE", f"Duplicate replay artifact: {name}.")
            )
            continue
        seen.add(name)
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            violations.append(
                _violation("REPLAY_DIGEST_INVALID", f"Invalid SHA-256 for replay artifact: {name}.")
            )
            continue
        try:
            path = resolve_bundle_file(bundle, name)
        except BundleFileError as exc:
            code = "REPLAY_FILE_MISSING" if exc.reason == "missing" else "REPLAY_FILE_UNSAFE"
            violations.append(_violation(code, str(exc)))
            continue
        assert path is not None
        if replay_artifact_digest(path) != digest:
            violations.append(
                _violation("REPLAY_ARTIFACT_CHANGED", f"Replay artifact changed: {name}.")
            )
    return violations


def _violation(code: str, message: str) -> Violation:
    return Violation(code=code, message=message)
