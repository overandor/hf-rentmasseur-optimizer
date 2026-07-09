# Workflow: verify-space

> **Validate HF Space deployment is live and correct.**

## Prerequisites

- HF Space URL is known
- `curl` available

## Steps

1. **HTTP check**
   - `curl -s -o /dev/null -w "%{http_code}" -L <space_url>`
   - Expected: 200
   - If not 200 → space is not live

2. **API status check**
   - Use `huggingface_hub` API: `space_info(repo_id=<space_id>)`
   - Check `runtime.stage` == "RUNNING"
   - If not RUNNING → space is building or errored

3. **Screenshot capture**
   - `screencapture -x /tmp/space_verify_{timestamp}.png`
   - Or use `WindowManager.capture_window_screenshot()`
   - Save as artifact

4. **Content check (optional)**
   - `curl -s <space_url> | grep -i "<expected_content>"`
   - Verify expected text appears in response

5. **Write result**
   - All 3 checks pass → "VERIFIED" with artifacts
   - Any check fails → "NOT VERIFIED" with failure reason
   - Write receipt

## Sacred Rule

> No fake verification claims. Every claim must be backed by a command output or inspection result.
