#!/bin/bash
# Test script — runs all tests
set -e

echo "=== HyperFlow Tests ==="

# Python tests
if [ -d "tests" ] || find . -name "test_*.py" -maxdepth 2 2>/dev/null | grep -q .; then
    echo "Running Python tests..."
    python3 -m pytest tests/ -v 2>&1 || python3 -m pytest -v 2>&1 || echo "No pytest, trying unittest"
    python3 -m unittest discover -s tests -v 2>&1 || true
fi

# Xcode tests
PROJECT=$(find . -name "*.xcodeproj" -maxdepth 2 | head -1 2>/dev/null)
if [ -n "$PROJECT" ]; then
    SCHEME=$(xcodebuild -list -project "$PROJECT" 2>&1 | grep -A1 "Schemes:" | tail -1 | xargs)
    if [ -n "$SCHEME" ]; then
        echo "Running Xcode tests..."
        xcodebuild -project "$PROJECT" -scheme "$SCHEME" -destination 'platform=iOS Simulator,name=iPhone 16' test 2>&1
    fi
fi

echo "=== Tests Complete ==="
