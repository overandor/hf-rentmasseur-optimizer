#!/bin/bash
# Capture git diff for HyperFlow receipt
# Usage: bash capture_git_diff.sh [output_file]

OUTPUT="${1:-hyperflow/build_logs/git_diff_$(date +%Y%m%d_%H%M%S).txt}"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"

echo "=== Git Diff Capture ===" > "$OUTPUT"
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT"
echo "Repo: $REPO_ROOT" >> "$OUTPUT"
echo "Branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')" >> "$OUTPUT"
echo "Commit: $(git rev-parse HEAD 2>/dev/null || echo 'none')" >> "$OUTPUT"
echo "" >> "$OUTPUT"
git diff >> "$OUTPUT" 2>&1
git diff --cached >> "$OUTPUT" 2>&1
echo "" >> "$OUTPUT"
echo "=== Changed files ===" >> "$OUTPUT"
git diff --name-only >> "$OUTPUT" 2>&1
git diff --cached --name-only >> "$OUTPUT" 2>&1

echo "Diff saved to $OUTPUT"
