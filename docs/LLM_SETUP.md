# LLM Setup Guide

## Overview

`iac-llm-wrapper` is an LLM-assisted intent-to-IaC orchestration framework. Local
models via Ollama are the primary development path. No API key or cloud service
required. A 3B parameter model running locally is sufficient for many structured
design docs.

**Important**: LLM testing is a local developer responsibility. CI does not run LLM tests (no API keys in GitHub Actions, no Ollama in CI). Every developer validates extraction quality with their own local models before submitting PRs.

## Quick Start with Ollama

### 1. Install Ollama

```bash
# macOS
curl -fsSL https://ollama.com/install.sh | sh

# Or download from https://ollama.com/download
```

### 2. Pull a Small Model

For infrastructure extraction, small models (3B parameters) work well:

```bash
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
| `qwen2.5:3b` | 3B | Fast | Good | General extraction, structured output |
| `llama3.2:3b` | 3B | Fast | Good | General extraction, longer contexts |
| `phi4:14b` | 14B | Medium | Better | Complex multi-region designs |
| `deepseek-r1:7b` | 7B | Medium | Better | Reasoning-intensive discovery |

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
uv run python scripts/evaluate-usability.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/battle-test.py --fixture aws-lza-complex-enterprise-handoff --llm --provider ollama --model qwen2.5:7b
```

These compile checked-in role/eval fixtures, compare handoff artifacts against
expected outcomes, and verify LLM evidence when `--llm` is enabled.

Every compile writes `model-benchmark.yaml` next to the handoff artifacts. Use it
to compare provider/model behavior, latency, token reporting, readiness, and
decision/gap counts without adding a UI or observability service to this repo.
`battle-test.py` keeps full local review bundles under ignored `tests/results/`.
Each bundle includes `battle-summary.yaml` with a verdict, confidence categories,
findings, and improvement items so model weaknesses become actionable.
Compare multiple runs with:

```bash
uv run python scripts/compare-model-benchmarks.py tests/results/*/model-benchmark.yaml
```

## LLM vs Deterministic Fallback

### With LLM (Model-Assisted Path)
- Extracts free-form values from prose (accounts, workloads, CIDRs)
- Detects signals from unstructured text
- Fills gaps with guided interview
- Handles implicit requirements
- **This is the intended extraction path for narrative docs**

### Without LLM (Bootstrap / CI Only)
- Uses graph defaults
- Requires explicit `--decisions` JSON for custom values
- Signal detection still works via keyword matching
- Structured Markdown sections can recover named accounts, OUs, and workloads
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
| Local development | Ollama with 3B model or API key |
| CI with API key | Cloud LLM (set `OPENAI_API_KEY`) |
| CI without API key | Deterministic fallback (limited) |
| Complex enterprise docs | 7B+ model or cloud LLM |
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

### Ollama Not Detected
- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- Check the model is pulled: `ollama list`
- Try specifying base URL: `--base-url http://localhost:11434/v1`

## Cloud LLM Options

If local models are insufficient:

```bash
# OpenAI
export OPENAI_API_KEY=sk-...
iac-llm-wrapper compile -i design.md -o out/ --provider openai --model gpt-4o-mini
```

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
