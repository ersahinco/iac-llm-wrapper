"""Tests for the interview engine: save/resume, transcript, input validation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from intent_engine.core.interview import InterviewEngine
from intent_engine.core.requirements import Requirement, RequirementGraph, RequirementStatus


def _make_graph() -> RequirementGraph:
    g = RequirementGraph()
    g.add(
        Requirement(
            key="primary_region",
            label="Primary Region",
            question="Which region?",
            default="eu-central-1",
            category="org",
        )
    )
    g.add(
        Requirement(
            key="topology",
            label="Topology",
            question="Network topology?",
            options=["hub-spoke", "single-vpc"],
            default="single-vpc",
            category="network",
        )
    )
    g.add(
        Requirement(
            key="network_cidr",
            label="CIDR",
            question="CIDR block?",
            default="10.0.0.0/16",
            category="network",
        )
    )
    return g


class TestSaveResume:
    def test_save_and_load_state(self):
        g = _make_graph()
        e1 = InterviewEngine(g)
        e1.run_from_decisions({"primary_region": "us-west-2", "topology": "hub-spoke"})

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
            e1.save_state(path)

        e2 = InterviewEngine.load_state(path, graph=_make_graph())
        assert e2.graph.get("primary_region") == "us-west-2"
        assert e2.graph.get("topology") == "hub-spoke"
        assert e2.graph.status("primary_region") == RequirementStatus.DECIDED
        assert e2.graph.status("topology") == RequirementStatus.DECIDED
        Path(path).unlink()

    def test_save_and_load_with_skip(self):
        g = _make_graph()
        e1 = InterviewEngine(g)
        e1.run_from_decisions({"primary_region": "eu-west-1"})
        e1.skip("topology")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
            e1.save_state(path)

        e2 = InterviewEngine.load_state(path, graph=_make_graph())
        assert e2.graph.get("primary_region") == "eu-west-1"
        assert e2.graph.status("topology") == RequirementStatus.SKIPPED
        Path(path).unlink()

    def test_save_preserves_audit_trail(self):
        e1 = InterviewEngine(_make_graph())
        e1.run_from_decisions({"primary_region": "eu-west-1", "topology": "single-vpc"})

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
            e1.save_state(path)

        state = json.loads(Path(path).read_text())
        assert len(state["audit"]) == 2
        assert state["audit"][0]["key"] == "primary_region"
        assert state["audit"][1]["key"] == "topology"
        Path(path).unlink()

    def test_save_preserves_pattern(self):
        e1 = InterviewEngine(_make_graph(), pattern="test-pattern")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
            e1.save_state(path)

        state = json.loads(Path(path).read_text())
        assert state["pattern"] == "test-pattern"
        Path(path).unlink()


class TestTranscript:
    def test_to_markdown_with_decisions(self):
        engine = InterviewEngine(_make_graph())
        engine.run_from_decisions({"primary_region": "us-west-2", "topology": "hub-spoke"})

        md = engine.to_markdown()
        assert "# Design Document" in md
        assert "us-west-2" in md
        assert "hub-spoke" in md

    def test_to_markdown_includes_unanswered(self):
        engine = InterviewEngine(_make_graph())
        engine.run_from_decisions({"primary_region": "eu-west-1"})

        md = engine.to_markdown()
        assert "<fill in>" in md

    def test_to_markdown_groups_by_category(self):
        engine = InterviewEngine(_make_graph())
        engine.run_from_decisions(
            {
                "primary_region": "us-east-1",
                "topology": "single-vpc",
                "network_cidr": "10.0.0.0/16",
            }
        )

        md = engine.to_markdown()
        assert "Org" in md or "org" in md
        assert "Network" in md or "network" in md


class TestInputValidation:
    def test_validate_answer_rejects_invalid_option(self):
        engine = InterviewEngine(_make_graph())
        # Move past primary_region (free text) to topology (has options)
        engine.answer("primary_region", "eu-west-1")
        q = engine.next_question()
        assert q is not None
        assert q.key == "topology"
        err = engine._validate_answer(q, "invalid-topology")
        assert err is not None
        assert "Invalid choice" in err

    def test_validate_answer_accepts_valid_option(self):
        engine = InterviewEngine(_make_graph())
        q = engine.next_question()
        assert q is not None
        err = engine._validate_answer(q, "eu-west-1")
        assert err is None

    def test_validate_int_answer(self):
        g = RequirementGraph()
        g.add(Requirement(key="days", label="Days", question="How many?", target_type="int"))
        engine = InterviewEngine(g)
        q = engine.next_question()
        assert q is not None
        assert engine._validate_answer(q, "abc") is not None
        assert engine._validate_answer(q, "42") is None

    def test_validate_bool_answer(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="flag",
                label="Flag",
                question="Enable?",
                options=["true", "false"],
                target_type="bool",
            )
        )
        engine = InterviewEngine(g)
        q = engine.next_question()
        assert q is not None
        assert engine._validate_answer(q, "nope") is not None
        assert engine._validate_answer(q, "true") is None
        assert engine._validate_answer(q, "yes") is not None  # not in options


class TestBacktracking:
    def test_back_command_revisits_previous_question(self):
        g = _make_graph()
        engine = InterviewEngine(g)

        answers: dict[str, str] = {
            "primary_region": "us-east-1",
            "topology": "\\back",
        }
        call_order: list[str] = []

        def fake_input(prompt: str) -> str:
            q = engine.next_question()
            if q is None:
                return ""
            call_order.append(q.key)
            if q.key == "primary_region":
                return "eu-west-1"
            if q.key == "topology":
                return "hub-spoke"
            return answers.get(q.key, "")

        outputs: list[str] = []

        def fake_output(msg: str) -> None:
            outputs.append(msg)

        engine.run_interactive(input_fn=fake_input, output_fn=fake_output)
        assert engine.graph.get("primary_region") == "eu-west-1"
        assert engine.graph.get("topology") == "hub-spoke"

    def test_back_on_first_question_warns(self):
        g = _make_graph()
        engine = InterviewEngine(g)

        call_order: list[str] = []

        def fake_input(prompt: str) -> str:
            q = engine.next_question()
            if q is None:
                return ""
            call_order.append(q.key)
            if q.key == "primary_region" and len(call_order) == 1:
                return "\\back"
            return "eu-west-1" if q.key == "primary_region" else "single-vpc"

        outputs: list[str] = []

        def fake_output(msg: str) -> None:
            outputs.append(msg)

        engine.run_interactive(input_fn=fake_input, output_fn=fake_output)
        assert "Cannot go back" in " ".join(outputs)
        assert engine.graph.get("primary_region") == "eu-west-1"


class TestInterviewSaveResume:
    def test_save_command_writes_state_and_exits(self, tmp_path: Path):
        g = _make_graph()
        engine = InterviewEngine(g)

        answers = {
            "primary_region": "\\save /tmp/test-state.json",
        }

        def fake_input(prompt: str) -> str:
            q = engine.next_question()
            if q is None:
                return ""
            return answers.get(q.key, "")

        outputs: list[str] = []

        def fake_output(msg: str) -> None:
            outputs.append(msg)

        engine.run_interactive(input_fn=fake_input, output_fn=fake_output)
        assert "saved to" in " ".join(outputs)
        assert Path("/tmp/test-state.json").exists()
        Path("/tmp/test-state.json").unlink()

    def test_save_command_without_path_warns(self):
        g = _make_graph()
        engine = InterviewEngine(g)
        # Use a closure that returns \save first, then answers properly
        call_count = {"primary_region": 0}

        def fake_input(prompt: str) -> str:
            q = engine.next_question()
            if q is None:
                return ""
            if q.key == "primary_region":
                call_count["primary_region"] += 1
                if call_count["primary_region"] == 1:
                    return "\\save "
                return "eu-west-1"
            return "single-vpc" if q.key == "topology" else ""

        outputs: list[str] = []

        def fake_output(msg: str) -> None:
            outputs.append(msg)

        engine.run_interactive(input_fn=fake_input, output_fn=fake_output)
        assert "save" in " ".join(outputs).lower()
        assert engine.graph.get("primary_region") == "eu-west-1"

    def test_save_and_resume_roundtrip(self, tmp_path: Path):
        g = _make_graph()
        engine = InterviewEngine(g)
        state_path = tmp_path / "state.json"

        # Simulate answering first question then saving
        answers = {
            "primary_region": "eu-west-1",
            "topology": f"\\save {state_path}",
        }

        def fake_input(prompt: str) -> str:
            q = engine.next_question()
            if q is None:
                return ""
            return answers.get(q.key, "")

        def fake_output(msg: str) -> None:
            pass

        engine.run_interactive(input_fn=fake_input, output_fn=fake_output)
        assert state_path.exists()

        # Resume and verify state
        e2 = InterviewEngine.load_state(str(state_path), graph=_make_graph())
        assert e2.graph.get("primary_region") == "eu-west-1"
