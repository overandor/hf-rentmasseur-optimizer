"""
Browser Runtime Crawler using Playwright
Verifies runtime behavior, console errors, and failed requests
"""
import asyncio
import json
from pathlib import Path
from typing import List, Dict, Any
from .core import BaseCrawler, Source, SubjectType, EvidenceType

class BrowserRuntimeCrawler(BaseCrawler):
    """Crawls web applications for runtime verification"""
    
    def __init__(self, headless: bool = True):
        super().__init__("browser_runtime_crawler")
        self.headless = headless
        self.console_errors = []
        self.failed_requests = []
    
    async def crawl(self, source: Source) -> List:
        signals = []
        url = source.location
        
        if not url.startswith(("http://", "https://")):
            return signals
        
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.add_signal(SubjectType.BROWSER_RUNTIME, EvidenceType.RUNTIME_VERIFIED, False, source.location)
            signals.extend(self.signals)
            return signals
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context()
            page = await context.new_page()
            
            # Track console errors
            page.on("console", lambda msg: self._handle_console(msg))
            
            # Track failed requests
            page.on("response", lambda response: self._handle_response(response))
            
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                
                # Take screenshot
                screenshot_path = Path("receipts") / f"runtime-{Path(url).name}.png"
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(screenshot_path))
                
                # Check for critical elements
                has_content = len(await page.content()) > 1000
                has_title = await page.title() != ""
                
                self.add_signal(SubjectType.BROWSER_RUNTIME, EvidenceType.RUNTIME_VERIFIED, has_content, source.location)
                self.add_signal(SubjectType.BROWSER_RUNTIME, EvidenceType.CONSOLE_ERRORS, len(self.console_errors), source.location)
                self.add_signal(SubjectType.BROWSER_RUNTIME, EvidenceType.FAILED_REQUESTS, len(self.failed_requests), source.location)
                
            except Exception as e:
                self.add_signal(SubjectType.BROWSER_RUNTIME, EvidenceType.RUNTIME_VERIFIED, False, source.location)
                self.add_signal(SubjectType.BROWSER_RUNTIME, EvidenceType.CONSOLE_ERRORS, 1, source.location)
            
            await browser.close()
        
        signals.extend(self.signals)
        return signals
    
    def _handle_console(self, msg):
        if msg.type == "error":
            self.console_errors.append(msg.text)
    
    def _handle_response(self, response):
        if response.status >= 400:
            self.failed_requests.append({
                "url": response.url,
                "status": response.status
            })
