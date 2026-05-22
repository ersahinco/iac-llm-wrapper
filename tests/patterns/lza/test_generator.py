"""Tests for LZA-specific generator registry (builtin generators)."""

from __future__ import annotations

from pathlib import Path

import intent_engine.patterns.lza.generators  # noqa: F401 — triggers generator registration
from intent_engine.core.generator import GLOBAL_REGISTRY
from intent_engine.patterns.lza.models import RawIntent


class TestLZABuiltinGenerators:
    def test_builtin_generators_registered(self):
        names = GLOBAL_REGISTRY.list()
        assert "organization" in names
        assert "accounts" in names
        assert "security" in names
        assert "workload-skeletons" in names

    def test_generate_creates_files(self, tmp_path: Path):
        from intent_engine.core.generator import generate_all

        intent = RawIntent()
        intent.primary_region = "eu-central-1"
        intent.ous = []
        intent.accounts = []

        output_dir = tmp_path / "out"
        generate_all(intent, output_dir)

        assert (output_dir / "decision-report.yaml").exists()
        assert (output_dir / "organization-config.yaml").exists()
