#!/bin/bash
# Build script — runs the project build
set -e

echo "=== HyperFlow Build ==="

# Python projects
if [ -f "requirements.txt" ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt 2>&1
fi

if [ -f "setup.py" ] || [ -f "pyproject.toml" ]; then
    echo "Building Python package..."
    python3 -m build 2>&1 || echo "No build tool available, skipping"
fi

# Xcode projects
if [ -d "*.xcodeproj" ] || find . -name "*.xcodeproj" -maxdepth 2 2>/dev/null | grep -q .; then
    echo "Building Xcode project..."
    PROJECT=$(find . -name "*.xcodeproj" -maxdepth 2 | head -1)
    SCHEME=$(xcodebuild -list -project "$PROJECT" 2>&1 | grep -A1 "Schemes:" | tail -1 | xargs)
    if [ -n "$SCHEME" ]; then
        xcodebuild -project "$PROJECT" -scheme "$SCHEME" -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1
    fi
fi

echo "=== Build Complete ==="
