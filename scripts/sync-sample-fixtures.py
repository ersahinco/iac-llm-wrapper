#!/usr/bin/env python3
"""Sync versioned sample fixture bundles from registered sample decisions."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

from intent_engine.core.compiler import compile_from_interview
from intent_engine.core.sample_config import GLOBAL_SAMPLE_REGISTRY, SampleConfig
from intent_engine.patterns import load_builtin_patterns

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = REPO_ROOT / "fixtures"
KEEP_FILES = {"README.md"}


def _selected_samples(names: list[str]) -> list[SampleConfig]:
    if not names:
        return [
            sample
            for sample in (
                GLOBAL_SAMPLE_REGISTRY.get(name) for name in GLOBAL_SAMPLE_REGISTRY.list()
            )
            if sample.fixture_dir or (FIXTURES_ROOT / sample.fixture_name).exists()
        ]
    return [GLOBAL_SAMPLE_REGISTRY.get(name) for name in names]


def _fixture_dir(sample: SampleConfig) -> Path:
    return FIXTURES_ROOT / sample.fixture_name


def _generated_files(path: Path) -> dict[str, str]:
    return {
        item.name: _normalized_artifact_text(item.name, item.read_text())
        for item in sorted(path.iterdir())
        if item.is_file()
    }


def _normalized_artifact_text(file_name: str, text: str) -> str:
    if file_name != "decision-audit.yaml":
        return text
    return re.sub(
        r"(^\s*-?\s*timestamp:\s*).+$",
        r"\1<TIMESTAMP>",
        text,
        flags=re.MULTILINE,
    )


def _drift_messages(sample: SampleConfig, generated_dir: Path, fixture_dir: Path) -> list[str]:
    expected = _generated_files(generated_dir)
    actual = {
        item.name: _normalized_artifact_text(item.name, item.read_text())
        for item in sorted(fixture_dir.iterdir())
        if item.is_file() and item.name not in KEEP_FILES
    }
    messages: list[str] = []
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(name for name in expected if name in actual and actual[name] != expected[name])
    if missing:
        messages.append(f"{sample.name}: missing {', '.join(missing)}")
    if extra:
        messages.append(f"{sample.name}: stale {', '.join(extra)}")
    if changed:
        messages.append(f"{sample.name}: changed {', '.join(changed)}")
    return messages


def _sync_sample(sample: SampleConfig, check: bool) -> list[str]:
    fixture_dir = _fixture_dir(sample)
    if not fixture_dir.exists():
        return [f"{sample.name}: fixture dir missing at {fixture_dir.name}"]

    with tempfile.TemporaryDirectory(prefix="intent-engine-fixture-") as temp_dir:
        generated_dir = Path(temp_dir) / sample.fixture_name
        compile_from_interview(sample.decisions, generated_dir, pattern=sample.pattern)
        drift = _drift_messages(sample, generated_dir, fixture_dir)
        if check or not drift:
            return drift

        expected_names = set(_generated_files(generated_dir))
        for item in list(fixture_dir.iterdir()):
            if item.is_file() and item.name not in KEEP_FILES and item.name not in expected_names:
                item.unlink()
        for item in generated_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, fixture_dir / item.name)
        return drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="append", default=[], help="Sample config name to sync")
    parser.add_argument("--check", action="store_true", help="Fail when fixture drift exists")
    args = parser.parse_args()

    load_builtin_patterns()
    drifts: list[str] = []
    for sample in _selected_samples(args.sample):
        drifts.extend(_sync_sample(sample, check=args.check))

    for drift in drifts:
        print(drift)

    if args.check and drifts:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
