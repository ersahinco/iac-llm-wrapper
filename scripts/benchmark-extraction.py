#!/usr/bin/env python3
"""LLM extraction quality benchmark: runs compile against all fixtures, reports extraction metrics.

Usage:
    ./scripts/benchmark-extraction.py [--model qwen2.5:7b] [--provider ollama]

Exits non-zero if any fixture falls below quality threshold.
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

FIXTURES = [
    {
        "name": "valid-payments.md",
        "path": "fixtures/valid-payments.md",
        "pattern": "baseline",
        "expect": {"accounts": 5, "ous": 3, "workloads": 1},
    },
    {
        "name": "enterprise-full.md",
        "path": "fixtures/enterprise-full.md",
        "pattern": "hybrid-enterprise",
        "expect": {"accounts": 8, "ous": 5, "workloads": 4},
    },
    {
        "name": "enterprise-partial.md",
        "path": "fixtures/enterprise-partial.md",
        "pattern": "baseline",
        "expect": {"accounts": 6, "ous": 0, "workloads": 1},
    },
    {
        "name": "invalid-design.md",
        "path": "fixtures/invalid-design.md",
        "pattern": "baseline",
        "expect": {"accounts": 1, "ous": 0, "workloads": 1},
        "expect_failure": True,
    },
    {
        "name": "kubernetes-enterprise.md",
        "path": "fixtures/kubernetes-enterprise.md",
        "pattern": "kubernetes-cluster",
        "expect": {"accounts": 0, "ous": 0, "workloads": 0},
    },
    {
        "name": "blank-template.md",
        "path": "fixtures/blank-template.md",
        "pattern": "baseline",
        "expect": {"accounts": 0, "ous": 0, "workloads": 0},
    },
]


def parse_llm_json(raw_response: str) -> dict | None:
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 2:
            cleaned = "\n".join(lines[1:-1])
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def evidence_response_text(evidence_path: Path) -> str | None:
    try:
        import ruamel.yaml

        yaml = ruamel.yaml.YAML(typ="safe")
        with open(evidence_path) as f:
            data = yaml.load(f)
        if not data or "calls" not in data or not data["calls"]:
            return None
        return data["calls"][0].get("response", "")
    except Exception:
        return None


def count_extracted(text: str, key: str) -> int:
    data = parse_llm_json(text)
    if data is None:
        return -1
    items = data.get(key, [])
    if isinstance(items, list):
        return len(items)
    return -1


def run_one(fixture: dict, model: str, provider: str) -> dict:
    fixture_path = REPO_ROOT / fixture["path"]
    result = {
        "fixture": fixture["name"],
        "pattern": fixture["pattern"],
        "status": "OK",
        "compile": "ok",
        "violations": "",
        "latency_s": 0.0,
        "parse_err": "",
        **{f"{k}_got": -1 for k in ("accounts", "ous", "workloads")},
        **{f"{k}_exp": fixture["expect"].get(k, -1) for k in ("accounts", "ous", "workloads")},
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_path = Path(tmpdir) / "evidence.yaml"
        start = time.perf_counter()
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "intent_engine",
                "compile",
                "--input",
                str(fixture_path),
                "--output",
                tmpdir,
                "--pattern",
                fixture["pattern"],
                "--provider",
                provider,
                "--model",
                model,
                "--dry-run",
                "--evidence-output",
                str(evidence_path),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        latency = time.perf_counter() - start
        result["latency_s"] = round(latency, 1)

        stderr = proc.stderr or ""

        if fixture.get("expect_failure"):
            if proc.returncode != 0:
                result["compile"] = "expected-fail"
                result["violations"] = "CompileError (expected)"
            else:
                result["compile"] = "should-fail-but-passed"
                result["status"] = "FAIL"
        else:
            if proc.returncode != 0:
                result["compile"] = "failed"
                result["status"] = "FAIL"
                for line in stderr.splitlines():
                    if "[" in line and "]" in line:
                        result["violations"] += line.strip() + "; "

        if evidence_path.exists():
            raw = evidence_response_text(evidence_path)
            if raw:
                for key in ("accounts", "ous", "workloads"):
                    result[f"{key}_got"] = count_extracted(raw, key)
                data = parse_llm_json(raw)
                if data is None:
                    result["parse_err"] = "JSON parse failed"
                    if result["status"] == "OK":
                        result["status"] = "WARN"
                else:
                    errs = []
                    for key in ("accounts", "ous", "workloads"):
                        got = result[f"{key}_got"]
                        exp = result[f"{key}_exp"]
                        if exp > 0 and got < exp:
                            errs.append(f"{key}: got {got}, exp {exp}")
                    if errs:
                        result["parse_err"] = "; ".join(errs)
                        result["status"] = "WARN"

    return result


def fmt(v):
    if isinstance(v, int) and v < 0:
        return "N/A"
    return str(v)


def main():
    parser = argparse.ArgumentParser(description="LLM extraction quality benchmark")
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--provider", default="ollama")
    parser.add_argument("--fixture", help="Run a single fixture (filename)")
    args = parser.parse_args()

    fixtures = FIXTURES
    if args.fixture:
        fixtures = [f for f in FIXTURES if f["name"] == args.fixture]
        if not fixtures:
            print(f"No fixture named '{args.fixture}'")
            sys.exit(1)

    sep = "-" * 140
    header = (
        f"{'Fixture':30s} {'Pattern':20s} {'Cmp':14s} "
        f"{'Accts':10s} {'OUs':8s} {'Wrklds':8s} "
        f"{'Lat(s)':8s} {'ParseErr':30s}"
    )
    print(sep)
    print(header)
    print(sep)

    passed = 0
    warned = 0
    failed = 0

    for fix in fixtures:
        r = run_one(fix, args.model, args.provider)
        got_accts = fmt(r["accounts_got"])
        exp_accts = fmt(r["accounts_exp"])
        got_ous = fmt(r["ous_got"])
        exp_ous = fmt(r["ous_exp"])
        got_wl = fmt(r["workloads_got"])
        exp_wl = fmt(r["workloads_exp"])

        accts_str = f"{got_accts}/{exp_accts}" if exp_accts != "-1" else got_accts
        ous_str = f"{got_ous}/{exp_ous}" if exp_ous != "-1" else got_ous
        wl_str = f"{got_wl}/{exp_wl}" if exp_wl != "-1" else got_wl

        parse_str = (
            r["parse_err"]
            if r["parse_err"]
            else (r["violations"] if r.get("violations") else "none")
        )
        if len(parse_str) > 29:
            parse_str = parse_str[:26] + "..."

        status_mark = ""
        if r["status"] == "FAIL":
            status_mark = " FAIL"
            failed += 1
        elif r["status"] == "WARN":
            status_mark = " WARN"
            warned += 1
        else:
            passed += 1

        print(
            f"{fix['name']:30s} {fix['pattern']:20s} {r['compile']:14s}"
            f" {accts_str:10s} {ous_str:8s} {wl_str:8s}"
            f" {str(r['latency_s']):8s} {parse_str:30s}{status_mark}"
        )

    print(sep)
    total = passed + warned + failed
    print(f"Results: {passed} passed, {warned} warnings, {failed} failed (of {total} fixtures)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
