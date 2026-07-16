#!/usr/bin/env python3
"""Compare model-benchmark.yaml artifacts in a simple table."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from intent_engine.core.yaml_utils import load_yaml_mapping


def _yaml_load(path: Path) -> dict[str, Any]:
    return load_yaml_mapping(path)


def _nested(data: dict[str, Any], section: str, key: str, default: Any = "") -> Any:
    value = data.get(section)
    if not isinstance(value, dict):
        return default
    return value.get(key, default)


def _row(path: Path) -> dict[str, str]:
    data = _yaml_load(path)
    quality = data.get("quality", {}) if isinstance(data.get("quality"), dict) else {}
    conformance = data.get("conformance", {}) if isinstance(data.get("conformance"), dict) else {}
    accepted = int(quality.get("acceptedDecisionCount", 0) or 0)
    raw_coverage = int(quality.get("rawLlmAcceptedCoverageCount", 0) or 0)
    missing = quality.get("rawLlmMissingAcceptedDecisions", [])
    missing_keys = ", ".join(str(item) for item in missing) if isinstance(missing, list) else ""
    return {
        "path": str(path),
        "mode": str(_nested(data, "run", "mode", "unknown")),
        "provider": str(_nested(data, "run", "provider", "unknown")),
        "model": str(_nested(data, "run", "model", "unknown")),
        "readiness": str(_nested(data, "readiness", "status", "unknown")),
        "latencyMs": str(_nested(data, "latency", "totalMs", 0)),
        "tokens": str(_nested(data, "tokens", "totalTokens", 0)),
        "accepted": str(accepted),
        "rawCoverage": f"{raw_coverage}/{accepted}" if accepted else "0/0",
        "rawMissing": str(_nested(data, "quality", "rawLlmMissingAcceptedDecisionCount", 0)),
        "missingKeys": missing_keys,
        "conformance": str(conformance.get("status", _infer_conformance(data))),
        "blockers": str(_nested(data, "readiness", "blockerCount", 0)),
        "parseErrors": str(_nested(data, "quality", "parseErrorCount", 0)),
    }


def _infer_conformance(data: dict[str, Any]) -> str:
    mode = str(_nested(data, "run", "mode", "unknown"))
    if mode != "llm":
        return "not-applicable"
    readiness = str(_nested(data, "readiness", "status", "unknown"))
    blockers = int(_nested(data, "readiness", "blockerCount", 0) or 0)
    parse_errors = int(_nested(data, "quality", "parseErrorCount", 0) or 0)
    raw_missing = int(_nested(data, "quality", "rawLlmMissingAcceptedDecisionCount", 0) or 0)
    if readiness != "ready" or blockers or parse_errors:
        return "fail"
    if raw_missing:
        return "review"
    return "pass"


def _print_table(rows: list[dict[str, str]]) -> None:
    columns = [
        "mode",
        "provider",
        "model",
        "readiness",
        "latencyMs",
        "tokens",
        "accepted",
        "rawCoverage",
        "rawMissing",
        "missingKeys",
        "conformance",
        "blockers",
        "parseErrors",
        "path",
    ]
    widths = {column: max(len(column), *(len(row[column]) for row in rows)) for column in columns}
    print("  ".join(column.ljust(widths[column]) for column in columns))
    print("  ".join("-" * widths[column] for column in columns))
    for row in rows:
        print("  ".join(row[column].ljust(widths[column]) for column in columns))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmarks", nargs="+", type=Path)
    parser.add_argument(
        "--require-conformant",
        action="store_true",
        help="Exit non-zero unless every LLM benchmark has conformance=pass.",
    )
    args = parser.parse_args()

    paths = [path for path in args.benchmarks if path.exists()]
    missing = [str(path) for path in args.benchmarks if not path.exists()]
    if missing:
        print(f"Missing benchmark file(s): {', '.join(missing)}", file=sys.stderr)
        return 1
    rows = [_row(path) for path in paths]
    if not rows:
        print("No benchmark files provided.", file=sys.stderr)
        return 1
    _print_table(rows)
    if args.require_conformant:
        failing = [row for row in rows if row["mode"] == "llm" and row["conformance"] != "pass"]
        if failing:
            failing_paths = ", ".join(row["path"] for row in failing)
            print(f"Non-conformant LLM benchmark(s): {failing_paths}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
