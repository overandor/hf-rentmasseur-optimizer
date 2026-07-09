# Skill: hf-space-deploy-skill

> **Reusable machinery for deploying to and verifying Hugging Face Spaces.**

## Capabilities

- Deploy code to HF Space
- Check Space status (building, running, error)
- Download artifacts from Space
- Verify Space is live via HTTP
- Capture Space screenshot

## Interface

```python
class HfSpaceDeploySkill:
    def deploy(self, repo_id: str, source_dir: str) -> str:
        """Deploy source directory to HF Space. Returns space URL."""

    def status(self, repo_id: str) -> dict:
        """Check Space status. Returns {stage, hardware, url}."""

    def verify_live(self, space_url: str) -> dict:
        """Verify Space is live. Returns {http_code, response_time, screenshot_path}."""

    def download_artifact(self, repo_id: str, filename: str) -> str:
        """Download a file from Space repo. Returns local path."""

    def list_files(self, repo_id: str) -> list:
        """List all files in Space repo."""
```

## Dependencies

- `huggingface_hub` Python package
- `HF_TOKEN` environment variable
- `curl` for HTTP checks

## Credential Handling

- Token is read from `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN`
- Token is NEVER logged or included in receipts
- Token is NEVER passed as command-line argument (env var only)

## Used By

- `verify-space` workflow
- `extract-dmg-hf` workflow
