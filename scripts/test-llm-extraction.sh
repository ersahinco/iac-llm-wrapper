#!/usr/bin/env bash
# Test script for LLM extraction with local Ollama models
# Usage: ./scripts/test-llm-extraction.sh [model_name]

set -euo pipefail

MODEL="${1:-qwen2.5:3b}"
FIXTURES_DIR="fixtures"
OUTPUT_DIR="/tmp/iac-llm-test-$(date +%s)"

echo "========================================="
echo "Testing LLM extraction with model: $MODEL"
echo "========================================="

# Check Ollama availability
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "ERROR: Ollama is not running. Start it with: ollama serve"
    exit 1
fi

echo "✓ Ollama is running"

# Check model availability
if ! curl -s http://localhost:11434/api/tags | grep -q "$MODEL"; then
    echo "ERROR: Model '$MODEL' not found. Pull it with: ollama pull $MODEL"
    exit 1
fi

echo "✓ Model '$MODEL' is available"
echo ""

# Test fixtures
FIXTURES=(
    "valid-payments.md:baseline"
    "enterprise-full.md:hybrid-enterprise"
    "enterprise-partial.md:baseline"
    "kubernetes-enterprise.md:kubernetes-cluster"
)

PASSED=0
FAILED=0

for fixture_pattern in "${FIXTURES[@]}"; do
    IFS=':' read -r fixture pattern <<< "$fixture_pattern"
    fixture_path="$FIXTURES_DIR/$fixture"
    test_output="$OUTPUT_DIR/$fixture"

    echo "Testing: $fixture (pattern: $pattern)"

    if uv run iac-llm-wrapper compile \
        -i "$fixture_path" \
        -o "$test_output" \
        --pattern "$pattern" \
        --provider ollama \
        --model "$MODEL" \
        > "$test_output.log" 2>&1; then
        echo "  ✓ Compilation successful"

        # Check key outputs exist
        if [ -f "$test_output/decision-report.yaml" ]; then
            echo "  ✓ decision-report.yaml generated"
        fi

        if [ -f "$test_output/module-inputs.yaml" ]; then
            echo "  ✓ module-inputs.yaml generated"
        fi

        if [ -f "$test_output/sample-recommendations.yaml" ]; then
            echo "  ✓ sample-recommendations.yaml generated"
        fi

        PASSED=$((PASSED + 1))
    else
        echo "  ✗ Compilation failed (see $test_output.log)"
        FAILED=$((FAILED + 1))
    fi
    echo ""
done

echo "========================================="
echo "Results: $PASSED passed, $FAILED failed"
echo "Output directory: $OUTPUT_DIR"
echo "========================================="

if [ $FAILED -gt 0 ]; then
    exit 1
fi
