# Workflow: notarize-release

> **Notarize a DMG or app bundle with Apple's notarization service.**

## Prerequisites

- Apple Developer account with App-specific password
- `xcrun notarytool` available (Xcode Command Line Tools)
- Artifact is signed with Developer ID Application certificate

## Steps

1. **Verify signing**
   - `codesign -dv --verbose=4 <artifact_path>`
   - Must show "Authority=Developer ID Application: ..."
   - If not signed → abort: "Artifact must be signed before notarization"

2. **Submit for notarization**
   - `xcrun notarytool submit <artifact_path> --apple-id <apple_id> --password <app_password> --team-id <team_id>`
   - Parse submission ID from output
   - Save submission ID

3. **Wait for result**
   - `xcrun notarytool wait <submission_id> --apple-id <apple_id> --password <app_password> --team-id <team_id>`
   - Timeout: 15 minutes
   - Expected status: "Accepted"

4. **Staple ticket**
   - `xcrun stapler staple <artifact_path>`
   - Verify: `xcrun stapler validate <artifact_path>`

5. **Final verification**
   - `spctl -a -t exec -vv <artifact_path>`
   - Must return "accepted"

6. **Write receipt**
   - Artifacts: notarization log, staple output, spctl output
   - Use `/create-receipt` workflow

## Credential Handling

- Apple ID, app password, and team ID are read from environment variables:
  - `APPLE_ID`, `APPLE_APP_PASSWORD`, `APPLE_TEAM_ID`
- These are NEVER logged, NEVER included in receipts.
- Receipt records only: "notarized via notarytool" + submission ID + result.

## Error Handling

- Submission failure → abort, write failure receipt
- Timeout → abort, write failure receipt with "notarization timed out"
- Rejection → abort, write failure receipt with rejection reason from notarytool log
