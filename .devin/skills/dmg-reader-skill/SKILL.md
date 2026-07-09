# Skill: dmg-reader-skill

> **Reusable machinery for reading and inspecting DMG files.**

## Capabilities

- Mount DMG read-only
- List contents recursively
- Extract specific files from DMG
- Verify code signatures
- Compute checksums

## Interface

```python
class DmgReaderSkill:
    def mount(self, dmg_path: str) -> str:
        """Mount DMG read-only, return mount point path."""

    def list_contents(self, mount_point: str) -> list:
        """List all files in mounted DMG recursively."""

    def extract_file(self, mount_point: str, file_path: str, dest: str) -> str:
        """Extract a single file from DMG to destination."""

    def verify_signature(self, app_path: str) -> dict:
        """Check code signature of .app bundle. Returns {valid, authority, team_id}."""

    def checksum(self, dmg_path: str) -> str:
        """Compute SHA-256 of DMG file."""

    def unmount(self, mount_point: str) -> bool:
        """Unmount DMG. Returns True on success."""
```

## Dependencies

- `hdiutil` (macOS built-in)
- `codesign` (macOS built-in)
- `shasum` (macOS built-in)

## Used By

- `inspect-dmg` workflow
- `extract-dmg-hf` workflow
- `build-dmg` workflow (verification step)
