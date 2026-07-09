# Workflow: build-dmg

> **Build a macOS DMG package from source.**

## Prerequisites

- Source directory contains `.app` bundle or build script
- `hdiutil` available (macOS built-in)
- Developer ID Application certificate (for signing)

## Steps

1. **Clean build**
   - Remove old build artifacts: `rm -rf build/ dist/`
   - // turbo
   - Run build script (e.g., `python3 build.py` or `xcodebuild`)
   - Verify `.app` exists in build output

2. **Create DMG**
   - `hdiutil create -volname "<App Name>" -srcfolder <app_path> -ov -format UDZO build/<App_Name>.dmg`
   - Verify DMG was created: `test -f build/<App_Name>.dmg`
   - Record DMG size

3. **Sign DMG**
   - `codesign --force --sign "Developer ID Application: <Name>" <dmg_path>`
   - Verify signature: `codesign -dv --verbose=4 <dmg_path>`

4. **Notarize** (run `/notarize-release` workflow)
   - Submit to Apple: `xcrun notarytool submit <dmg_path> --apple-id <id> --password <app_password> --team-id <team_id>`
   - Wait for status: `xcrun notarytool wait <submission_id>`
   - Staple: `xcrun stapler staple <dmg_path>`

5. **Verify**
   - `spctl -a -t exec -vv <dmg_path>` — must return "accepted"
   - If rejected → build failed, abort

6. **Write receipt**
   - Artifacts: DMG file, build log, notarization log, spctl output
   - Use `/create-receipt` workflow

## Error Handling

- Build failure → abort, write failure receipt
- Signing failure → abort, write failure receipt
- Notarization failure → abort, DMG is not distributable
- spctl rejection → abort, DMG is not distributable
