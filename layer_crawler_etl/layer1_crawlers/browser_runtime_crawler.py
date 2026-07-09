"""
Layer 1: Browser Runtime Crawler
Crawls web applications using Puppeteer for runtime verification.
"""

import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from layer_crawler_etl.layer1_crawlers.base_crawler import BaseCrawler, CrawlResult
from layer_crawler_etl.layer0_source_registry.source_registry import Source


@dataclass
class RuntimeMetrics:
    """Runtime metrics from browser crawl."""
    console_errors: List[str] = field(default_factory=list)
    console_warnings: List[str] = field(default_factory=list)
    failed_requests: List[Dict] = field(default_factory=list)
    page_load_time_ms: float = 0.0
    first_contentful_paint_ms: float = 0.0
    largest_contentful_paint_ms: float = 0.0
    network_requests_count: int = 0
    js_errors_count: int = 0
    memory_usage_mb: float = 0.0
    screenshot_path: Optional[str] = None


class BrowserRuntimeCrawler(BaseCrawler):
    """Crawls web applications using browser automation for runtime verification."""
    
    crawler_type = "browser_runtime"
    
    def validate_source(self, source: Source) -> bool:
        """Validate that source is a web-accessible URL."""
        valid_types = ["website", "runtime_url", "huggingface", "api_endpoint"]
        return any(t in source.source_type.value.lower() for t in valid_types)
    
    async def crawl(self, source: Source) -> CrawlResult:
        """Crawl web application for runtime verification."""
        result = CrawlResult(source_id=source.source_id)
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Note: In production, this would use actual Puppeteer/Playwright
            # For now, we'll create a mock implementation
            metrics = await self._crawl_with_browser(source)
            
            data = {
                "source_url": source.url,
                "runtime_verified": True,
                "console_errors": metrics.console_errors,
                "console_warnings": metrics.console_warnings,
                "failed_requests": metrics.failed_requests,
                "page_load_time_ms": metrics.page_load_time_ms,
                "first_contentful_paint_ms": metrics.first_contentful_paint_ms,
                "largest_contentful_paint_ms": metrics.largest_contentful_paint_ms,
                "network_requests_count": metrics.network_requests_count,
                "js_errors_count": metrics.js_errors_count,
                "memory_usage_mb": metrics.memory_usage_mb,
                "screenshot": metrics.screenshot_path,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            result.data = data
            
            # Flag errors
            if metrics.console_errors:
                result.add_error(f"Found {len(metrics.console_errors)} console errors")
            
            if metrics.failed_requests:
                result.add_warning(f"Found {len(metrics.failed_requests)} failed requests")
            
            if metrics.screenshot_path:
                result.add_artifact(metrics.screenshot_path)
            
            artifact_path = self.save_raw_data(source.source_id, data, "runtime.json")
            result.add_artifact(artifact_path)
            
        except Exception as e:
            result.add_error(f"Browser runtime crawl failed: {str(e)}")
            result.data = {"runtime_verified": False, "error": str(e)}
        
        result.crawl_duration_seconds = asyncio.get_event_loop().time() - start_time
        return result
    
    async def _crawl_with_browser(self, source: Source) -> RuntimeMetrics:
        """
        Crawl URL with browser automation using Playwright.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError("Playwright not installed. Install with: pip install playwright && playwright install")
        
        metrics = RuntimeMetrics()
        screenshot_path = self.get_storage_path(source.source_id) / "screenshot.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Capture console logs
            console_logs = []
            page.on("console", lambda msg: console_logs.append({"type": msg.type, "text": msg.text}))
            
            # Capture failed requests
            failed_requests = []
            def handle_request_failed(request):
                failed_requests.append({
                    "url": request.url,
                    "failure": request.failure
                })
            page.on("requestfailed", handle_request_failed)
            
            # Track network requests
            network_requests = []
            page.on("request", lambda request: network_requests.append(request.url))
            
            # Navigate to URL
            start_time = asyncio.get_event_loop().time()
            try:
                await page.goto(source.url, wait_until="networkidle", timeout=30000)
                load_time = (asyncio.get_event_loop().time() - start_time) * 1000
                metrics.page_load_time_ms = load_time
            except Exception as e:
                metrics.console_errors.append(str(e))

            # Performance metrics
            try:
                perf_metrics = await page.evaluate("""() => {
                    const timing = performance.timing;
                    return {
                        loadTime: timing.loadEventEnd - timing.navigationStart,
                        domContentLoaded: timing.domContentLoadedEventEnd - timing.navigationStart,
                        firstPaint: performance.getEntriesByType('paint')[0]?.startTime || 0
                    };
                }""")
                metrics.first_contentful_paint_ms = perf_metrics.get("firstPaint", 0) * 1000
                metrics.largest_contentful_paint_ms = perf_metrics.get("loadTime", 0)
            except:
                pass
            
            # Count errors
            metrics.console_errors = [log["text"] for log in console_logs if log["type"] == "error"]
            metrics.console_warnings = [log["text"] for log in console_logs if log["type"] == "warning"]
            metrics.failed_requests = failed_requests
            metrics.network_requests_count = len(network_requests)
            metrics.js_errors_count = len(metrics.console_errors)

            # Get memory usage (Chrome-specific)
            try:
                memory_metrics = await page.evaluate("""
                    () => {
                        if (performance.memory) {
                            return {
                                usedJSHeapSize: performance.memory.usedJSHeapSize / 1024 / 1024,
                                totalJSHeapSize: performance.memory.totalJSHeapSize / 1024 / 1024
                            };
                        }
                        return null;
                    }
                """)
                if memory_metrics:
                    metrics.memory_usage_mb = memory_metrics.get("usedJSHeapSize", 0)
            except:
                pass

            # Take screenshot
            try:
                screenshot_path = self.output_dir / f"{source.source_id}_screenshot.png"
                await page.screenshot(path=str(screenshot_path), full_page=False)
                metrics.screenshot_path = str(screenshot_path)
            except Exception as e:
                metrics.console_warnings.append(f"Screenshot failed: {str(e)}")

            await browser.close()

        return metrics
    
    async def _launch_puppeteer_script(self, url: str, output_path: Path) -> Dict:
        """
        Launch Puppeteer script for browser automation.
        
        This would create a Node.js script that:
        1. Launches Puppeteer
        2. Navigates to URL
        3. Collects metrics
        4. Saves screenshot
        5. Outputs JSON results
        """
        # This is a placeholder for the production implementation
        script = f"""
const puppeteer = require('puppeteer');
const fs = require('fs');

(async () => {{
  const browser = await puppeteer.launch({{headless: 'new'}});
  const page = await browser.newPage();
  
  const consoleLogs = [];
  page.on('console', msg => {{
    consoleLogs.push({{type: msg.type(), text: msg.text()}});
  }});
  
  const failedRequests = [];
  page.on('requestfailed', request => {{
    failedRequests.push({{url: request.url(), failure: request.failure()}});
  }});
  
  await page.goto('{url}', {{waitUntil: 'networkidle2'}});
  
  const metrics = await page.metrics();
  const performanceTiming = JSON.parse(
    await page.evaluate(() => JSON.stringify(window.performance.timing))
  );
  
  await page.screenshot({{path: '{output_path}/screenshot.png'}});
  
  const result = {{
    consoleLogs,
    failedRequests,
    metrics,
    performanceTiming
  }};
  
  fs.writeFileSync('{output_path}/browser-results.json', JSON.stringify(result, null, 2));
  
  await browser.close();
}})();
"""
        return {"script": script}
