# LLM Setup Guide

## Overview

`iac-llm-wrapper` uses LLMs to help extract architect intent for registered
target configuration handoff. Local models via Ollama are the primary
development path. No API key or cloud service required. A 3B parameter model
running locally is sufficient for many structured design docs; use a 7B model
when customer-style notes are the quality bar and your workstation can handle
the latency.

Compilation is deterministic by default. LLM use is opt-in and requires both an
explicit provider and model so results stay attributable and repeatable.

**Important**: LLM testing is a local developer responsibility. CI does not run LLM tests (no API keys in GitHub Actions, no Ollama in CI). Every developer validates extraction quality with their own local models before submitting PRs.

## Quick Start with Ollama

### 1. Install Ollama

```bash
# macOS
curl -fsSL https://ollama.com/install.sh | sh

# Or download from https://ollama.com/download
```

### 2. Pull a Small Model

For infrastructure extraction, small models (3B parameters) work well. On a
modern MacBook Pro, prefer `qwen2.5:7b` for customer-style evals when the extra
latency is acceptable:

```bash
# Recommended customer-fixture model when local hardware can handle it
ollama pull qwen2.5:7b

# Recommended: Qwen 2.5 3B - fast, good instruction following
ollama pull qwen2.5:3b

# Alternative: Llama 3.2 3B - good general performance
ollama pull llama3.2:3b
```

### 3. Start Ollama

```bash
ollama serve
```

### 4. Verify Model is Running

```bash
curl http://localhost:11434/api/tags
```

### 5. Run the Tool

```bash
# Compile with local LLM
iac-llm-wrapper compile -i design.md -o out/ --pattern aws-lza --provider ollama --model qwen2.5:3b

# Or set environment variable
export INTENT_ENGINE_PROVIDER=ollama
export INTENT_ENGINE_MODEL=qwen2.5:3b
iac-llm-wrapper compile -i design.md -o out/ --pattern aws-lza
```

## Model Recommendations

| Model | Size | Speed | Quality | Best For |
|-------|------|-------|---------|----------|
| `qwen2.5:7b` | 7B | Medium | Better | Customer-style fixtures, richer notes |
| `qwen2.5:3b` | 3B | Fast | Good | General extraction, structured output |
| `llama3.2:3b` | 3B | Fast | Good | General extraction, longer contexts |
| `phi4:14b` | 14B | Medium | Better | Complex multi-region designs |
| `deepseek-r1:7b` | 7B | Medium | Better | Reasoning-intensive discovery |

## Real Packet Defaults

For a first customer packet run, prefer a model path that your team can repeat:

```bash
# Local workstation path for customer-style notes
iac-llm-wrapper discover -i customer-packet.md --pattern aws-lza \
  --provider ollama --model qwen2.5:7b
iac-llm-wrapper compile -i customer-packet.md -o out/customer-packet \
  --pattern aws-lza --provider ollama --model qwen2.5:7b --no-raw-evidence

# Direct Bedrock path through the local AWS CLI session
aws sts get-caller-identity
iac-llm-wrapper compile -i customer-packet.md -o out/customer-packet \
  --pattern aws-lza --provider bedrock \
  --model eu.amazon.nova-2-lite-v1:0 --no-raw-evidence

# Human review page for either path
iac-llm-wrapper review html --input out/customer-packet \
  --output out/customer-packet/handoff-review.html
```

Use `--no-raw-evidence` for service-style packet runs. Keep raw prompt/response
evidence only for local extraction debugging, preferably outside the repo with
`--evidence-output` or the eval script `--evidence-dir` option.

### Hardware Requirements

- **3B models**: ~2GB RAM, runs on most laptops
- **7B models**: ~4GB RAM, modern laptop or desktop
- **14B models**: ~8GB RAM, dedicated GPU recommended

## Testing Local LLM Extraction

Run deterministic and LLM-backed eval loops:

```bash
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-extraction.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/evaluate-extraction.py --llm --provider ollama --model qwen2.5:7b --evidence-dir /tmp/iac-llm-evidence
uv run python scripts/evaluate-golden-journey.py --scenario ready
uv run python scripts/evaluate-golden-journey.py --scenario blocked
uv run python scripts/evaluate-golden-journey.py --scenario all --output tests/results/golden-journey.yaml
uv run python scripts/evaluate-golden-journey.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/evaluate-golden-journey.py --llm --provider ollama --model qwen2.5:7b --require-conformant
uv run python scripts/evaluate-golden-journey.py --llm --provider ollama --model qwen2.5:7b --keep-output tests/results/golden-qwen2.5-7b --benchmark-output tests/results/golden-qwen2.5-7b.yaml
uv run python scripts/evaluate-golden-journey.py --scenario all --llm --provider bedrock --model eu.amazon.nova-2-lite-v1:0 --keep-output tests/results/golden-bedrock-nova-2-lite --output tests/results/golden-journey-bedrock-nova-2-lite.yaml
uv run python scripts/evaluate-usability.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/battle-test.py --fixture aws-lza-complex-enterprise-handoff --llm --provider ollama --model qwen2.5:7b
```

These compile checked-in role/eval fixtures, including customer-style board
notes and BYOM module notes, compare handoff artifacts against expected
outcomes, verify ready and blocked static review-page stakeholder signals, and
verify LLM evidence when `--llm` is enabled. Use
`evaluate-golden-journey.py` as the fastest product-confidence check.
`--scenario ready` runs the customer-style AWS LZA fixture through service-style
compile (`--no-raw-evidence`), static review generation, readiness checks,
contract and manual-gate checks, target artifact checks, trace/benchmark checks,
and model conformance visibility. `--scenario blocked` proves a messy blocked
input fails closed while still producing safe assessment/review artifacts,
blocker ownership/questions, trace/benchmark checks, and no deployable or target
handoff artifacts. Add `--require-conformant` when the run should fail unless
the model has `conformance=pass`; add `--benchmark-output` when you want a
compact YAML summary of readiness, model, raw coverage, raw missing decisions,
and conformance. Add `--output` to write a ready/blocked result artifact for
CI archives or model-run comparison.

Every compile writes `model-benchmark.yaml` next to the handoff artifacts. Use it
to compare provider/model behavior, latency, token reporting, readiness, raw LLM
coverage of accepted decisions, and decision/gap counts without adding a UI or
observability service to this repo. `battle-test.py` keeps full local review
bundles under ignored `tests/results/`. Each bundle includes
`battle-summary.yaml` with a verdict, confidence categories, findings, and
improvement items so model weaknesses become actionable.
Compare multiple runs with:

```bash
uv run python scripts/compare-model-benchmarks.py tests/results/*/model-benchmark.yaml
uv run python scripts/compare-model-benchmarks.py --require-conformant tests/results/*/model-benchmark.yaml
```

Treat `readiness=ready` as necessary but not sufficient when comparing models.
Prefer models that also show high `rawCoverage` and low `rawMissing`; a ready
handoff can still be carried by structured Markdown while the model misses
accepted decisions. `conformance=pass` means the LLM run was ready, had no parse
errors, and had full raw coverage for accepted decisions. `conformance=review`
means the handoff may be usable but model extraction still needs human review.
`conformance=fail` means the model run should not be accepted as a model-quality
baseline.

## Raw Evidence Hygiene

LLM-backed `compile` writes raw prompt/response evidence to
`<output>/raw-evidence.yaml` for local developer runs unless you pass
`--evidence-output` to choose a different path or `--no-raw-evidence` to skip
raw prompt/response storage. Keep raw evidence only when debugging extraction or
tuning a model: it is the clearest way to inspect what the model saw, what it
returned, and why graph acceptance behaved the way it did.

Treat raw evidence like temporary customer design material. It may contain
account names, network topology, control requirements, document excerpts, and
model responses. It is a development/debug artifact, not a required service
artifact. A service deployment can use `context-manifest.yaml`,
`llm-trace-summary.yaml`, `model-benchmark.yaml`, and `handoff-review.html` to
show which code-owned context and LLM interpretation shaped the bundle without
storing raw prompts and responses. Use a
restricted output directory, avoid secrets in design docs, provide API keys
through environment variables or `--api-key`, and redact evidence before sharing
outside the project team. The repo ignores common raw-evidence file names to
reduce accidental commits.

Do not place secret values in design docs, eval fixtures, prompts, raw evidence,
or emitted handoff artifacts. Capture secret-store references plus expected
parameter names instead, for example `aws-secretsmanager://team/app/db#password`,
`aws-ssm-parameter://team/app/api-key`, or an approved enterprise vault URI. The
downstream provisioning toolchain resolves the value; this wrapper should only
carry the reference, owner, expected parameter name, and validation notes.

## LLM vs Deterministic Fallback

### With LLM (Model-Assisted Path)
- Extracts free-form values from prose (accounts, OUs, CIDRs)
- Detects signals from unstructured text
- Fills gaps with guided interview
- Handles implicit requirements
- **This is the intended extraction path for narrative docs**

### Without LLM (Bootstrap / CI Only)
- Uses graph defaults
- Requires explicit `--decisions` JSON for custom values
- Signal detection still works via keyword matching
- The AWS LZA pattern can recover named accounts and OUs from structured sections
- **Not sufficient for real design documents**

The deterministic fallback exists for:
- Unit tests (fast, no external dependencies)
- CI bootstrapping (when no API key is available)
- Developer workflow without LLM setup

It cannot interpret arbitrary free-form prose. If you feed a 20-page narrative design document
into the tool without an LLM, you get defaults plus any explicitly structured entities — not the
full architect intent.

### When to Use Each

| Scenario | Recommendation |
|----------|---------------|
| Local development | Ollama with 3B model; use `qwen2.5:7b` for customer-fixture hardening |
| CI with API key | Cloud LLM through the OpenAI-compatible backend |
| CI without API key | Deterministic fallback (limited) |
| Complex enterprise docs | 7B+ local model or approved cloud model |
| Quick validation / unit tests | Deterministic fallback |

## Troubleshooting

### Model Times Out
- 3B models should respond in 10-30 seconds
- Try a faster model (qwen2.5:3b is generally fastest)

### Extraction Quality is Poor
- Ensure the document follows the expected structure (see `fixtures/`)
- Try a larger model (7B+)
- Use `--decisions` JSON for critical values
- Check the LLM evidence output: `--evidence-output evidence.yaml`
- Check `model-benchmark.yaml` for latency, parse errors, and decision/gap counts

### Ollama Is Unavailable
- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- Check the model is pulled: `ollama list`
- Try specifying base URL: `--base-url http://localhost:11434/v1`

## Cloud LLM Options

If local models are insufficient:

```bash
# OpenAI
export OPENAI_API_KEY=sk-...
iac-llm-wrapper compile -i design.md -o out/ --provider openai --model gpt-4o-mini

# Amazon Bedrock through local AWS CLI credentials/session
aws sts get-caller-identity
aws bedrock-runtime converse \
  --region eu-central-1 \
  --model-id eu.amazon.nova-2-lite-v1:0 \
  --messages '[{"role":"user","content":[{"text":"Return only OK"}]}]' \
  --inference-config '{"maxTokens":16,"temperature":0.1}'

iac-llm-wrapper compile -i design.md -o out/ \
  --provider bedrock \
  --model eu.amazon.nova-2-lite-v1:0

# Amazon Bedrock through an approved OpenAI-compatible gateway or proxy,
# when teams require gateway mediation instead of direct AWS CLI invocation.
export OPENAI_API_KEY=bedrock-gateway-token
iac-llm-wrapper compile -i design.md -o out/ \
  --provider openai \
  --base-url https://bedrock-gateway.example.com/v1 \
  --model eu.amazon.nova-2-lite-v1:0
```

For Bedrock, keep the repo data model provider-neutral: choose the cheapest
approved model that passes `evaluate-extraction.py --llm` on customer-style
fixtures, record the run in `model-benchmark.yaml`, and compare latency, token
reporting, raw LLM coverage, parse errors, and readiness before changing prompts.
Do not add provider-specific benchmark pricing tables unless repeated customer
runs need that decision inside this repo.

## Performance Benchmarks

On Apple M3 Pro (18GB RAM):

| Model | Compile Time | Quality |
|-------|-------------|---------|
| qwen2.5:3b | 8-15s | Good |
| llama3.2:3b | 10-20s | Good |
| phi4:14b | 30-60s | Better |

On Intel i7-12700H + RTX 3060:

| Model | Compile Time | Quality |
|-------|-------------|---------|
| qwen2.5:3b | 5-10s | Good |
| llama3.2:3b | 6-12s | Good |
| phi4:14b | 15-30s | Better |
