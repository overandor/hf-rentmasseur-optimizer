# Skill: chrome-extension-iframe-skill

> **Reusable machinery for Chrome extension iframe communication.**

## Capabilities

- Inject content into Chrome extension iframes
- Read DOM state from extension pages
- Bridge between agent system and Chrome extension
- Capture extension page screenshots

## Interface

```python
class ChromeExtensionIframeSkill:
    def inject(self, extension_id: str, path: str, content: str) -> bool:
        """Inject content into extension page via iframe."""

    def read_dom(self, extension_id: str, selector: str) -> str:
        """Read DOM element text from extension page."""

    def screenshot(self, extension_id: str) -> str:
        """Capture screenshot of extension page. Returns file path."""

    def bridge_message(self, extension_id: str, message: dict) -> dict:
        """Send message to extension, wait for response."""
```

## Dependencies

- Chrome with remote debugging enabled (`--remote-debugging-port=9222`)
- `chrome-remote-interface` Python package (or WebSocket client)
- Extension installed with `externally_connectable` permissions

## Security

- Extension ID must be whitelisted in agent config
- Messages are validated against schema before sending
- No credentials passed through extension bridge
- All bridge messages logged with timestamp

## Used By

- Future: Chrome extension integration for web research
- Future: Browser automation for form filling
- Future: Extension-based screenshot capture
