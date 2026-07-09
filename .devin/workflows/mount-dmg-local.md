# Workflow: mount-dmg-local

> **Mount a DMG locally for manual inspection.**

## Prerequisites

- DMG file exists at given path

## Steps

1. **Verify DMG exists**
   - `test -f <dmg_path>`

2. **Attach DMG**
   - `hdiutil attach <dmg_path>`
   - Parse output for mount point

3. **Open in Finder**
   - `open <mount_point>`

4. **Log mount**
   - Record: timestamp, dmg_path, mount_point
   - Write receipt

## Cleanup

- User manually ejects via Finder, OR
- `hdiutil detach <mount_point>` when done
