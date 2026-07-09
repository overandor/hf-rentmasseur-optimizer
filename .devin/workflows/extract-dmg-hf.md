# Workflow: extract-dmg-hf

> **Extract a DMG from an HF Space and download it locally.**

## Prerequisites

- HF Space URL is live (run `/verify-space` first)
- `HF_TOKEN` environment variable is set
- `huggingface_hub` Python package installed

## Steps

1. **Verify HF Space is live**
   - Run `/verify-space` workflow
   - Abort if space is not running

2. **List Space files**
   - Use `huggingface_hub` API: `list_repo_files(repo_id=<space_id>, repo_type="space")`
   - Filter for `.dmg` files
   - If no DMG found → abort with "No DMG artifact in Space"

3. **Download DMG**
   - `huggingface_hub.hf_hub_download(repo_id=<space_id>, filename=<dmg_path>, repo_type="space")`
   - Record download path and file size

4. **Verify download**
   - `shasum -a 256 <downloaded_path>`
   - Compare with HF Space metadata hash if available

5. **Mount and inspect**
   - Run `/inspect-dmg` workflow on downloaded file

6. **Write receipt**
   - Artifacts: downloaded DMG, checksum, inspection log
   - Use `/create-receipt` workflow

## Error Handling

- Download failure → abort, write failure receipt
- Hash mismatch → log warning, continue with flag
- HF API error → abort with error details (no token in logs)
