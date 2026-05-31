#!/usr/bin/env python3
"""Compare model-benchmark.yaml artifacts in a simple table."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import ruamel.yaml


def _yaml_load(path: Path) -> dict[str, Any]:
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping")
    return data


def _nested(data: dict[str, Any], section: str, key: str, default: Any = "") -> Any:
    value = data.get(section)
    if not isinstance(value, dict):
        return default
    return value.get(key, default)


def _row(path: Path) -> dict[str, str]:
    data = _yaml_load(path)
    return {
        "path": str(path),
        "mode": str(_nested(data, "run", "mode", "unknown")),
        "provider": str(_nested(data, "run", "provider", "unknown")),
        "model": str(_nested(data, "run", "model", "unknown")),
        "readiness": str(_nested(data, "readiness", "status", "unknown")),
        "latencyMs": str(_nested(data, "latency", "totalMs", 0)),
        "tokens": str(_nested(data, "tokens", "totalTokens", 0)),
        "accepted": str(_nested(data, "quality", "acceptedDecisionCount", 0)),
        "blockers": str(_nested(data, "readiness", "blockerCount", 0)),
        "parseErrors": str(_nested(data, "quality", "parseErrorCount", 0)),
    }


def _print_table(rows: list[dict[str, str]]) -> None:
    columns = [
        "mode",
        "provider",
        "model",
        "readiness",
        "latencyMs",
        "tokens",
        "accepted",
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
