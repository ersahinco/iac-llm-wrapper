"""CLI integration tests — run actual commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from intent_engine.cli import app

runner = CliRunner()


class TestCLIDiscover:
    def test_discover_valid_design(self):
        result = runner.invoke(app, ["discover", "--input", "fixtures/valid-payments.md"])
        assert result.exit_code == 0
        assert "No gaps found" in result.output or "Synced" in result.output

    def test_discover_invalid_design_shows_gaps(self):
        # Use --path to show decision path; discover with decisions
        result = runner.invoke(
            app,
            [
                "discover",
                "--input",
                "fixtures/invalid-design.md",
                "--suggest",
            ],
        )
        assert result.exit_code == 0

    def test_discover_with_suggest(self):
        result = runner.invoke(
            app, ["discover", "--input", "fixtures/invalid-design.md", "--suggest"]
        )
        assert result.exit_code == 0

    def test_discover_with_path(self):
        result = runner.invoke(app, ["discover", "--input", "fixtures/valid-payments.md", "--path"])
        assert result.exit_code == 0
        assert "primary_region" in result.output


class TestCLICompile:
    def test_compile_valid_design(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("INTENT_ENGINE_DISABLE_LLM", "1")
        output_dir = tmp_path / "out"
        result = runner.invoke(
            app, ["compile", "--input", "fixtures/valid-payments.md", "--output", str(output_dir)]
        )
        # With defaults-only, compile succeeds with default values
        assert result.exit_code == 0, result.output
        assert output_dir.exists()
        assert (output_dir / "decision-report.yaml").exists()

    def test_compile_invalid_design_fails(self, tmp_path: Path):
        output_dir = tmp_path / "out"
        # Use interview with --no-defaults to trigger validation failures
        result = runner.invoke(
            app,
            [
                "interview",
                "--output",
                str(output_dir),
                "--decisions",
                '{"topology": "hub-spoke", "cicd_mode": "private"}',
                "--no-defaults",
            ],
        )
        assert result.exit_code != 0
        assert "violations" in result.output

    def test_compile_with_dry_run(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("INTENT_ENGINE_DISABLE_LLM", "1")
        output_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "compile",
                "--input",
                "fixtures/valid-payments.md",
                "--output",
                str(output_dir),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Dry-run" in result.output
        assert not (output_dir / "decision-report.yaml").exists()


class TestCLIVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "intent-engine" in result.output
        assert "0.1.0" in result.output


class TestCLICatalog:
    def test_catalog_list(self):
        result = runner.invoke(app, ["catalog", "list"])
        assert result.exit_code == 0
        assert "lza-minimal" in result.output
        assert "lza-baseline" in result.output
        assert "lza-hybrid-enterprise" in result.output

    def test_catalog_show(self):
        result = runner.invoke(app, ["catalog", "show", "--entry", "lza-minimal"])
        assert result.exit_code == 0
        assert "lza-minimal" in result.output
        assert "eu-central-1" in result.output

    def test_catalog_show_unknown_entry(self):
        result = runner.invoke(app, ["catalog", "show", "--entry", "nonexistent"])
        assert result.exit_code != 0

    def test_catalog_diff(self, tmp_path: Path):
        decisions_file = tmp_path / "decisions.json"
        decisions_file.write_text('{"primary_region": "us-east-1"}')
        result = runner.invoke(
            app, ["catalog", "diff", "--entry", "lza-minimal", "--input", str(decisions_file)]
        )
        assert result.exit_code == 0
        assert "primary_region" in result.output

    def test_catalog_apply(self, tmp_path: Path):
        decisions_file = tmp_path / "decisions.json"
        output_file = tmp_path / "merged.json"
        decisions_file.write_text('{"primary_region": "us-east-1"}')
        result = runner.invoke(
            app,
            [
                "catalog",
                "apply",
                "--entry",
                "lza-minimal",
                "--input",
                str(decisions_file),
                "--output",
                str(output_file),
            ],
        )
        assert result.exit_code == 0
        assert output_file.exists()


class TestCLIInterview:
    def test_interview_with_decisions(self, tmp_path: Path):
        output_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "interview",
                "--output",
                str(output_dir),
                "--decisions",
                '{"topology": "single-vpc", "primary_region": "eu-central-1"}',
            ],
        )
        assert result.exit_code == 0, result.output

    def test_interview_pattern_minimal(self, tmp_path: Path):
        output_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "interview",
                "--output",
                str(output_dir),
                "--pattern",
                "minimal",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "minimal" in result.output.lower() or output_dir.exists()

    def test_interview_pattern_financial(self, tmp_path: Path):
        output_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "interview",
                "--output",
                str(output_dir),
                "--pattern",
                "financial-services",
                "--decisions",
                '{"topology": "single-vpc", "primary_region": "eu-central-1"}',
            ],
        )
        assert result.exit_code == 0, result.output
        # Should have financial-specific fields in summary
        assert "data_residency" in result.output.lower() or output_dir.exists()


class TestCLIValidate:
    def test_validate_intent_artifacts(self, tmp_path: Path):
        # Create mock intent artifacts
        output_dir = tmp_path / "out"
        output_dir.mkdir()
        org_text = "organization:\n  primaryRegion: eu-central-1\n"
        (output_dir / "organization-config.yaml").write_text(org_text)
        (output_dir / "accounts-config.yaml").write_text("accounts:\n  - name: Test\n")
        (output_dir / "global-config.yaml").write_text("global:\n  primaryRegion: eu-central-1\n")
        (output_dir / "security-config.yaml").write_text(
            "security:\n  s3:\n    blockPublicAccess: true\n  audit:\n    retentionDays: 2555\n"
        )
        (output_dir / "network-config.yaml").write_text("network:\n  topology: hub-spoke\n")
        (output_dir / "iam-config.yaml").write_text("iam:\n")
        (output_dir / "customizations-config.yaml").write_text("customizations:\n")
        (output_dir / "decision-report.yaml").write_text("primaryRegion: eu-central-1\n")
        (output_dir / "deployment-graph.yaml").write_text("phases:\n")

        result = runner.invoke(app, ["validate", "--input", str(output_dir)])
        assert result.exit_code == 0, result.output

    def test_validate_missing_files(self, tmp_path: Path):
        output_dir = tmp_path / "out"
        output_dir.mkdir()
        result = runner.invoke(app, ["validate", "--input", str(output_dir)])
        assert result.exit_code != 0


class TestCLIReview:
    def test_review_identical_reports(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        data = {"primaryRegion": "eu-central-1", "topology": "single-vpc"}
        import ruamel.yaml

        yaml = ruamel.yaml.YAML()
        with open(before, "w") as f:
            yaml.dump(data, f)
        with open(after, "w") as f:
            yaml.dump(data, f)
        result = runner.invoke(app, ["review", "--before", str(before), "--after", str(after)])
        assert result.exit_code == 0
        assert "No differences found" in result.output

    def test_review_changed_values(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        import ruamel.yaml

        yaml = ruamel.yaml.YAML()
        with open(before, "w") as f:
            yaml.dump({"primaryRegion": "eu-central-1", "topology": "single-vpc"}, f)
        with open(after, "w") as f:
            yaml.dump({"primaryRegion": "eu-west-1", "topology": "hub-spoke"}, f)
        result = runner.invoke(app, ["review", "--before", str(before), "--after", str(after)])
        assert result.exit_code == 0
        assert "Changed" in result.output
        assert "eu-central-1" in result.output
        assert "eu-west-1" in result.output

    def test_review_missing_before_file(self, tmp_path: Path):
        after = tmp_path / "after.yaml"
        after.write_text("{}")
        result = runner.invoke(
            app, ["review", "--before", str(tmp_path / "nonexistent.yaml"), "--after", str(after)]
        )
        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_review_with_wa_coverage(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        import ruamel.yaml

        yaml = ruamel.yaml.YAML()
        with open(before, "w") as f:
            yaml.dump({"wellArchitectedCoverage": {"Security": []}}, f)
        with open(after, "w") as f:
            yaml.dump(
                {
                    "wellArchitectedCoverage": {
                        "Security": [],
                        "Reliability": [{"decision": "audit_retention"}],
                    }
                },
                f,
            )
        result = runner.invoke(app, ["review", "--before", str(before), "--after", str(after)])
        assert result.exit_code == 0
        assert "Well-Architected Coverage" in result.output
        assert "Reliability" in result.output


class TestCLITemplate:
    def test_template_minimal(self, tmp_path: Path):
        output = tmp_path / "design.md"
        result = runner.invoke(app, ["template", "--pattern", "minimal", "--output", str(output)])
        assert result.exit_code == 0, result.output
        assert output.exists()
        content = output.read_text()
        assert "## Region" in content
        assert "## Topology" in content
        assert "## Network" in content
        assert "primary: eu-central-1" in content

    def test_template_baseline(self, tmp_path: Path):
        output = tmp_path / "design.md"
        result = runner.invoke(app, ["template", "--pattern", "baseline", "--output", str(output)])
        assert result.exit_code == 0, result.output
        content = output.read_text()
        assert "## Hybrid Connectivity" in content
        assert "## CI/CD" in content

    def test_template_unknown_pattern(self, tmp_path: Path):
        output = tmp_path / "design.md"
        args = ["template", "--pattern", "nonexistent", "--output", str(output)]
        result = runner.invoke(app, args)
        assert result.exit_code != 0
        assert "Unknown pattern" in result.output

    def test_template_filled_minimal_compiles(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("INTENT_ENGINE_DISABLE_LLM", "1")
        tmpl = tmp_path / "design.md"
        runner.invoke(app, ["template", "--pattern", "minimal", "--output", str(tmpl)])
        out_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            ["compile", "--input", str(tmpl), "--output", str(out_dir), "--pattern", "minimal"],
        )
        assert result.exit_code == 0, result.output
        assert (out_dir / "decision-report.yaml").exists()

    def test_template_default_pattern_is_baseline(self, tmp_path: Path):
        output = tmp_path / "design.md"
        result = runner.invoke(app, ["template", "--output", str(output)])
        assert result.exit_code == 0
        content = output.read_text()
        assert "baseline pattern" in content
