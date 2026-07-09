#!/bin/bash
# Xcode verification — build, test, and capture results
# Usage: bash xcode_verify.sh <project> <scheme> [output_file]

PROJECT="${1:?Usage: xcode_verify.sh <project> <scheme> [output_file]}"
SCHEME="${2:?Usage: xcode_verify.sh <project> <scheme> [output_file]}"
OUTPUT="${3:-LOGS/xcode_verify_$(date +%Y%m%d_%H%M%S).log}"

mkdir -p "$(dirname "$OUTPUT")"

echo "=== Xcode Verification ===" > "$OUTPUT"
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT"
echo "Project: $PROJECT" >> "$OUTPUT"
echo "Scheme: $SCHEME" >> "$OUTPUT"
echo "" >> "$OUTPUT"

ALL_PASS=true

# Build
echo "--- Build ---" >> "$OUTPUT"
xcodebuild build \
    -project "$PROJECT" \
    -scheme "$SCHEME" \
    -destination 'platform=iOS Simulator,name=iPhone 16' \
    >> "$OUTPUT" 2>&1
BUILD_RESULT=$?
echo "Build: $([ $BUILD_RESULT -eq 0 ] && echo 'PASS' || echo 'FAIL')" >> "$OUTPUT"
[ $BUILD_RESULT -ne 0 ] && ALL_PASS=false

# Count errors and warnings
ERRORS=$(grep -c "error:" "$OUTPUT" 2>/dev/null || echo "0")
WARNINGS=$(grep -c "warning:" "$OUTPUT" 2>/dev/null || echo "0")
echo "Errors: $ERRORS" >> "$OUTPUT"
echo "Warnings: $WARNINGS" >> "$OUTPUT"

echo "" >> "$OUTPUT"

# Test
echo "--- Tests ---" >> "$OUTPUT"
xcodebuild test \
    -project "$PROJECT" \
    -scheme "$SCHEME" \
    -destination 'platform=iOS Simulator,name=iPhone 16' \
    >> "$OUTPUT" 2>&1
TEST_RESULT=$?
echo "Tests: $([ $TEST_RESULT -eq 0 ] && echo 'PASS' || echo 'FAIL')" >> "$OUTPUT"
[ $TEST_RESULT -ne 0 ] && ALL_PASS=false

echo "" >> "$OUTPUT"

# Signing check
echo "--- Signing ---" >> "$OUTPUT"
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -showBuildSettings 2>&1 | grep -E "CODE_SIGN_IDENTITY|DEVELOPMENT_TEAM|PROVISIONING_PROFILE" >> "$OUTPUT" 2>&1

echo "" >> "$OUTPUT"
echo "=== Overall: $($ALL_PASS && echo 'PASS' || echo 'FAIL') ===" >> "$OUTPUT"

cat "$OUTPUT"
echo ""
echo "Log: $OUTPUT"
$ALL_PASS && exit 0 || exit 1
