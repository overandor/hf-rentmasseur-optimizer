# Skill: macos-notarization-skill

> **Reusable machinery for Apple notarization of DMGs and app bundles.**

## Capabilities

- Submit artifact for notarization
- Wait for notarization result
- Staple notarization ticket
- Verify notarization status

## Interface

```python
class MacosNotarizationSkill:
    def submit(self, artifact_path: str) -> str:
        """Submit to Apple notarytool. Returns submission ID."""

    def wait(self, submission_id: str, timeout: int = 900) -> str:
        """Wait for notarization to complete. Returns status: Accepted|Rejected|Invalid."""

    def staple(self, artifact_path: str) -> bool:
        """Staple notarization ticket. Returns True on success."""

    def verify(self, artifact_path: str) -> dict:
        """Full verification. Returns {notarized, stapled, spctl_accepted}."""

    def get_log(self, submission_id: str) -> str:
        """Fetch notarization log from Apple."""
```

## Dependencies

- `xcrun notarytool` (Xcode Command Line Tools)
- `xcrun stapler` (Xcode Command Line Tools)
- `spctl` (macOS built-in)
- Environment variables: `APPLE_ID`, `APPLE_APP_PASSWORD`, `APPLE_TEAM_ID`

## Credential Handling

- All credentials read from environment variables only
- NEVER logged, NEVER in receipts, NEVER as CLI arguments visible in `ps`
- Receipt records only: submission ID, status, timestamp

## Used By

- `notarize-release` workflow
- `build-dmg` workflow (step 4)
