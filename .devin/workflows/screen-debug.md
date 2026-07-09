# Workflow: screen-debug

> **Capture and analyze screen state for debugging agent behavior.**

## Prerequisites

- `screencapture` available (macOS built-in)
- `WindowManager` class available in `agent_controller.py`

## Steps

1. **Declare capture**
   - Log: `[ScreenDebug] Capturing screen for debugging at {timestamp}`
   - Purpose: "debug"
   - This satisfies Rule 00: No stealth capture

2. **Capture all windows**
   - For each window index 0-3:
     - `WindowManager.capture_window_screenshot(window_index)`
     - Save path to list

3. **Capture full screen**
   - `screencapture -x /tmp/screen_debug_{timestamp}.png`

4. **OCR each window**
   - Run `_ocr_screenshot()` on each capture
   - Log OCR quality score and first 200 chars

5. **Run vision model (if OCR quality < 30)**
   - Use `ollama.vision()` as fallback
   - Log vision model response

6. **Analyze agent state**
   - Log: which agents are alive (`thread.is_alive()`)
   - Log: last output timestamp for each agent
   - Log: message bus recent messages

7. **Write report**
   - Save analysis to `/tmp/screen_debug_{timestamp}.md`
   - Include: screenshot paths, OCR text, agent states, bus messages

8. **Write receipt**
   - Artifact: debug report
   - Use `/create-receipt` workflow
