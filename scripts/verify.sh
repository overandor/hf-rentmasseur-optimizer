#!/bin/bash
# Verify script — runs build, test, and lint, returns combined result
# Usage: bash verify.sh [output_file]

OUTPUT="${1:-LOGS/verify_$(date +%Y%m%d_%H%M%S).log}"
mkdir -p "$(dirname "$OUTPUT")"

echo "=== HyperFlow Verification ===" > "$OUTPUT"
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT"
echo "" >> "$OUTPUT"

ALL_PASS=true

# Build
echo "--- Build ---" >> "$OUTPUT"
if [ -f "scripts/build.sh" ]; then
    bash scripts/build.sh >> "$OUTPUT" 2>&1
    BUILD_RESULT=$?
    echo "Build: $([ $BUILD_RESULT -eq 0 ] && echo 'PASS' || echo 'FAIL')" >> "$OUTPUT"
    [ $BUILD_RESULT -ne 0 ] && ALL_PASS=false
else
    echo "Build: SKIP (no build.sh)" >> "$OUTPUT"
fi

echo "" >> "$OUTPUT"

# Test
echo "--- Tests ---" >> "$OUTPUT"
if [ -f "scripts/test.sh" ]; then
    bash scripts/test.sh >> "$OUTPUT" 2>&1
    TEST_RESULT=$?
    echo "Tests: $([ $TEST_RESULT -eq 0 ] && echo 'PASS' || echo 'FAIL')" >> "$OUTPUT"
    [ $TEST_RESULT -ne 0 ] && ALL_PASS=false
else
    echo "Tests: SKIP (no test.sh)" >> "$OUTPUT"
fi

echo "" >> "$OUTPUT"

# Lint
echo "--- Lint ---" >> "$OUTPUT"
if [ -f "scripts/lint.sh" ]; then
    bash scripts/lint.sh >> "$OUTPUT" 2>&1
    LINT_RESULT=$?
    echo "Lint: $([ $LINT_RESULT -eq 0 ] && echo 'PASS' || echo 'FAIL')" >> "$OUTPUT"
else
    echo "Lint: SKIP (no lint.sh)" >> "$OUTPUT"
fi

echo "" >> "$OUTPUT"
echo "=== Overall: $($ALL_PASS && echo 'PASS' || echo 'FAIL') ===" >> "$OUTPUT"

cat "$OUTPUT"
echo ""
echo "Log: $OUTPUT"
$ALL_PASS && exit 0 || exit 1
