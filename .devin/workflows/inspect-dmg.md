# Workflow: inspect-dmg

> **Mount and inspect a DMG's contents safely.**

## Prerequisites

- DMG file exists at given path
- `hdiutil` available (macOS built-in)

## Steps

1. **Verify DMG exists**
   - `test -f <dmg_path>` — abort if not found
   - Record file size: `ls -la <dmg_path>`

2. **Mount DMG read-only**
   - `hdiutil attach -readonly -nobrowse <dmg_path>`
   - Parse output for mount point path
   - Save mount point as variable

3. **List contents**
   - `ls -laR <mount_point>`
   - Save output as artifact: `/tmp/dmg_inspect_{timestamp}.log`

4. **Checksum verification**
   - `shasum -a 256 <dmg_path>`
   - Record hash in receipt

5. **Check code signature (if .app inside)**
   - `codesign -dv --verbose=4 <mount_point>/*.app`
   - `spctl -a -t exec -vv <mount_point>/*.app`
   - Save output as artifact

6. **Unmount DMG**
   - `hdiutil detach <mount_point>`
   - Verify unmount succeeded

7. **Write receipt**
   - Artifact: inspection log + checksum
   - Use `/create-receipt` workflow

## Error Handling

- Mount failure → abort, write failure receipt
- Unmount failure → log warning, continue
- No .app found → skip code signature step
