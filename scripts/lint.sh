#!/bin/bash
# Lint script — runs code linters
set -e

echo "=== HyperFlow Lint ==="

# Python lint
if [ -f ".flake8" ] || [ -f "setup.cfg" ]; then
    echo "Running flake8..."
    python3 -m flake8 . 2>&1 || true
fi

if [ -f "pyproject.toml" ]; then
    echo "Running ruff..."
    python3 -m ruff check . 2>&1 || true
fi

# Swift lint
if command -v swiftlint &>/dev/null; then
    echo "Running SwiftLint..."
    swiftlint 2>&1 || true
fi

echo "=== Lint Complete ==="
