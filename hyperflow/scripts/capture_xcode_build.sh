#!/bin/bash
# Capture Xcode build output for HyperFlow receipt
# Usage: bash capture_xcode_build.sh <project_path> <scheme> [output_file]

PROJECT="${1:?Usage: capture_xcode_build.sh <project_path> <scheme> [output_file]}"
SCHEME="${2:?Usage: capture_xcode_build.sh <project_path> <scheme> [output_file]}"
OUTPUT="${3:-hyperflow/build_logs/xcode_build_$(date +%Y%m%d_%H%M%S).txt}"

mkdir -p "$(dirname "$OUTPUT")"

echo "=== Xcode Build Capture ===" > "$OUTPUT"
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT"
echo "Project: $PROJECT" >> "$OUTPUT"
echo "Scheme: $SCHEME" >> "$OUTPUT"
echo "Destination: iPhone 16 Simulator" >> "$OUTPUT"
echo "" >> "$OUTPUT"

# Clean build
echo "=== Clean Build ===" >> "$OUTPUT"
xcodebuild clean -project "$PROJECT" -scheme "$SCHEME" >> "$OUTPUT" 2>&1

# Build
echo "" >> "$OUTPUT"
echo "=== Build ===" >> "$OUTPUT"
xcodebuild build \
    -project "$PROJECT" \
    -scheme "$SCHEME" \
    -destination 'platform=iOS Simulator,name=iPhone 16' \
    >> "$OUTPUT" 2>&1

BUILD_RESULT=$?

echo "" >> "$OUTPUT"
echo "=== Build Result ===" >> "$OUTPUT"
if [ $BUILD_RESULT -eq 0 ]; then
    echo "BUILD: PASS" >> "$OUTPUT"
else
    echo "BUILD: FAIL (exit code $BUILD_RESULT)" >> "$OUTPUT"
    # Count errors and warnings
    ERRORS=$(grep -c "error:" "$OUTPUT" 2>/dev/null || echo "0")
    WARNINGS=$(grep -c "warning:" "$OUTPUT" 2>/dev/null || echo "0")
    echo "Errors: $ERRORS" >> "$OUTPUT"
    echo "Warnings: $WARNINGS" >> "$OUTPUT"
fi

echo "Build log saved to $OUTPUT"
echo "Build result: $([ $BUILD_RESULT -eq 0 ] && echo 'PASS' || echo 'FAIL')"
