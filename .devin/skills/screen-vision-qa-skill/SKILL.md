# Skill: screen-vision-qa-skill

> **Reusable machinery for screen capture, OCR, and vision-based QA.**

## Capabilities

- Capture window screenshots
- OCR text extraction (macOS Vision framework)
- Vision model analysis (Ollama llava)
- Screenshot diff detection (skip unchanged screens)
- Code region cropping + upscaling
- Ensemble OCR (Vision + Tesseract + llava)

## Interface

```python
class ScreenVisionQaSkill:
    def capture(self, window_index: int = 0) -> str:
        """Capture screenshot of window. Returns file path."""

    def ocr(self, image_path: str) -> tuple:
        """OCR text extraction. Returns (text, quality_score)."""

    def vision_analyze(self, image_path: str, prompt: str) -> str:
        """Analyze image with llava. Returns text response."""

    def has_changed(self, image_path: str) -> bool:
        """Check if screenshot changed since last call. Uses 64x64 pixel hash."""

    def crop_to_code(self, image_path: str) -> str:
        """Crop to code editor region, upscale 2x. Returns new image path."""

    def ensemble_ocr(self, image_path: str) -> tuple:
        """Run Vision OCR + Tesseract + llava, merge by confidence.
        Returns (best_text, source, confidence)."""
```

## Dependencies

- `screencapture` (macOS built-in)
- `Vision` framework (PyObjC)
- `PIL` (Pillow) for cropping and diff
- `pytesseract` (optional, for ensemble OCR)
- Ollama with `llava:latest` model

## OCR Pipeline

```
capture → has_changed? → crop_to_code → ocr → quality >= 30?
                                              ↓ no
                                         vision_analyze (fallback)
```

## Used By

- `screen-debug` workflow
- `CodeReviewerAgent` (every step)
- `ChatHistoryReader` (history scanning)
