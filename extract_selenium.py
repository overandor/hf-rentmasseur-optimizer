#!/usr/bin/env python3
"""
Extract ChatGPT chats using Selenium with Edge WebDriver.
Selenium uses the real Edge browser, which may bypass Cloudflare detection.
Uses the original Edge profile for authentication.
"""

import os
import time
import json
import re
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

OUTPUT_DIR = Path(__file__).parent / "chatgpt_exports"
EDGE_PROFILE = os.path.expanduser("~/Library/Application Support/Microsoft Edge")
CHATGPT_URL = "https://chatgpt.com"


def sanitize_filename(name):
    name = re.sub(r'[^\w\s\-]', '', name).strip()
    name = re.sub(r'[\s]+', '_', name)
    return (name or "untitled")[:100]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("ChatGPT Extractor via Selenium + Edge")
    print("=" * 60)

    edge_opts = Options()
    edge_opts.add_argument("--disable-blink-features=AutomationControlled")
    edge_opts.add_argument("--no-first-run")
    edge_opts.add_argument("--no-default-browser-check")
    edge_opts.add_argument("--user-data-dir=" + EDGE_PROFILE)
    edge_opts.add_argument("--profile-directory=Default")
    edge_opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    edge_opts.add_experimental_option("useAutomationExtension", False)

    # Try to suppress automation info bar
    edge_opts.add_argument("--disable-infobars")

    print("\nLaunching Edge via Selenium...")
    driver = webdriver.Edge(options=edge_opts)

    # Execute CDP command to remove webdriver flag
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = { runtime: {} };
        """
    })

    print(f"Navigating to {CHATGPT_URL}...")
    driver.get(CHATGPT_URL)

    # Wait for Cloudflare to clear
    print("Waiting for page to load (Cloudflare challenge if any)...")
    for i in range(60):
        time.sleep(2)
        url = driver.current_url
        title = driver.title
        if "__cf_chl" not in url and "challenge" not in url.lower():
            print(f"  Cloudflare cleared! URL: {url}, Title: {title}")
            break
        if i % 10 == 0:
            print(f"  Still waiting... ({i*2}s) URL: {url[:80]}")
    else:
        print("  Cloudflare did not clear after 120s")
        driver.save_screenshot(str(OUTPUT_DIR / "selenium_cf_stuck.png"))
        with open(OUTPUT_DIR / "selenium_cf_stuck.html", "w") as f:
            f.write(driver.page_source)
        print("  Debug files saved.")
        driver.quit()
        return

    time.sleep(5)

    # Check if logged in
    url = driver.current_url
    print(f"Current URL: {url}")
    print(f"Title: {driver.title}")

    if "auth" in url.lower() or "login" in url.lower():
        print("Not logged in. Saving debug info...")
        driver.save_screenshot(str(OUTPUT_DIR / "selenium_login.png"))
        with open(OUTPUT_DIR / "selenium_login.html", "w") as f:
            f.write(driver.page_source)
        driver.quit()
        return

    # Save initial screenshot
    driver.save_screenshot(str(OUTPUT_DIR / "selenium_loaded.png"))
    print("Screenshot saved.")

    # Extract chat list from sidebar
    print("\nExtracting chat list from sidebar...")

    # Scroll sidebar to load all chats
    try:
        nav = driver.find_element(By.CSS_SELECTOR, "nav")
        for _ in range(50):
            driver.execute_script("arguments[0].scrollBy(0, 1000)", nav)
            time.sleep(0.3)
    except Exception:
        print("  Could not find nav element for scrolling")

    # Find chat links
    chats = []
    seen_ids = set()

    selectors = [
        "nav ol li a",
        "nav a[href*='/c/']",
        "nav a[href*='/g/']",
        "a[href*='/c/']",
        "a[href*='/g/']",
        "[data-testid='history-item'] a",
        "nav a[href]",
    ]

    for selector in selectors:
        try:
            links = driver.find_elements(By.CSS_SELECTOR, selector)
            if not links:
                continue
            for link in links:
                try:
                    href = link.get_attribute("href") or ""
                    text = link.text.strip()
                    if not href:
                        continue
                    if "/c/" in href or "/g/" in href:
                        chat_id = href.split("/")[-1].split("?")[0]
                        if chat_id in seen_ids:
                            continue
                        seen_ids.add(chat_id)
                        full_url = href if href.startswith("http") else f"https://chatgpt.com{href}"
                        chats.append({
                            "title": text or f"chat_{chat_id[:8]}",
                            "url": full_url,
                            "chat_id": chat_id,
                        })
                except Exception:
                    continue
            if chats:
                break
        except Exception:
            continue

    print(f"Found {len(chats)} chats.")

    if not chats:
        print("No chats found. Saving debug info...")
        driver.save_screenshot(str(OUTPUT_DIR / "selenium_no_chats.png"))
        with open(OUTPUT_DIR / "selenium_no_chats.html", "w") as f:
            f.write(driver.page_source)
        # Also try to get all visible text
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            with open(OUTPUT_DIR / "selenium_body_text.txt", "w") as f:
                f.write(body_text)
            print(f"Body text saved ({len(body_text)} chars)")
        except Exception:
            pass
        driver.quit()
        return

    # Save chat index
    index_path = OUTPUT_DIR / "chat_index.json"
    index_path.write_text(json.dumps(chats, indent=2, ensure_ascii=False))
    print(f"Chat index saved to {index_path}")

    # Extract each conversation
    print(f"\nExtracting {len(chats)} conversations...")
    all_conversations = []

    for i, chat in enumerate(chats):
        print(f"  [{i+1}/{len(chats)}] {chat['title'][:50]}...", end=" ", flush=True)
        try:
            driver.get(chat["url"])
            time.sleep(4)

            # Extract messages
            messages = []
            try:
                articles = driver.find_elements(By.CSS_SELECTOR, "article")
                for article in articles:
                    try:
                        text = article.text.strip()
                        if text and len(text) > 2:
                            aria_label = article.get_attribute("aria-label") or ""
                            role = "unknown"
                            if "user" in aria_label.lower():
                                role = "user"
                            elif "assistant" in aria_label.lower():
                                role = "assistant"
                            messages.append({"role": role, "content": text})
                    except Exception:
                        continue
            except Exception:
                pass

            if not messages:
                # Fallback: try main content
                try:
                    main = driver.find_element(By.CSS_SELECTOR, "main")
                    if main:
                        messages.append({"role": "raw", "content": main.text})
                except Exception:
                    pass

            conversation = {
                "title": chat["title"],
                "url": chat["url"],
                "chat_id": chat["chat_id"],
                "messages": messages,
                "message_count": len(messages),
            }
            all_conversations.append(conversation)

            # Save markdown
            safe_name = sanitize_filename(chat["title"])
            md_path = OUTPUT_DIR / f"{i+1:04d}_{safe_name}.md"
            md_lines = [
                f"# {chat['title']}\n",
                f"URL: {chat['url']}\n",
                f"Chat ID: {chat['chat_id']}\n",
                f"Messages: {len(messages)}\n",
                "---\n",
            ]
            for msg in messages:
                md_lines.append(f"\n## [{msg['role'].upper()}]\n")
                md_lines.append(msg["content"])
                md_lines.append("")
            md_path.write_text("\n".join(md_lines))

            print(f"({len(messages)} messages)")
        except Exception as e:
            print(f"ERROR: {e}")
            all_conversations.append({
                "title": chat["title"],
                "url": chat["url"],
                "chat_id": chat["chat_id"],
                "messages": [],
                "message_count": 0,
                "error": str(e),
            })

    # Save all as JSON
    all_json = OUTPUT_DIR / "all_chats.json"
    all_json.write_text(json.dumps(all_conversations, indent=2, ensure_ascii=False))

    print(f"\n{'=' * 60}")
    print(f"Extraction complete!")
    print(f"  Total chats: {len(all_conversations)}")
    print(f"  Total messages: {sum(c.get('message_count', 0) for c in all_conversations)}")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}")

    driver.quit()


if __name__ == "__main__":
    main()
