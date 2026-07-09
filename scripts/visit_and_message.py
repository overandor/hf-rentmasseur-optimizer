#!/usr/bin/env python3
"""
RentMasseur Visit-Back + Message Pipe — REAL, no mock.

1. Login via undetected-chromedriver (bypasses CrowdSec)
2. Navigate to /settings/whosawme — scrape every visitor
3. Visit each visitor's profile
4. Send each visitor a message with phone number + availability
5. Go to mailbox, read all unread messages, reply to each

Usage:
    python3 scripts/visit_and_message.py --dry-run
    python3 scripts/visit_and_message.py --limit 20
    python3 scripts/visit_and_message.py --message "Hey, I'm available today. Text me at XXX-XXX-XXXX"
    python3 scripts/visit_and_message.py            # full run with default message
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = "https://rentmasseur.com"
USERNAME = os.getenv("RENTMASSEUR_USERNAME", "karpathianwolf")
PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", "os.environ.get("RM_PASSWORD", "")")
PHONE = os.getenv("WOLF_PHONE", "347-453-5129")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"

DEFAULT_MESSAGE = f"Hey! Thanks for checking out my profile. I'm available today — feel free to text me at {PHONE}. Happy to set something up."


def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return uc.Chrome(options=options, version_main=149)


def login(driver, max_wait=120):
    print("[1] Logging in...")
    driver.get(f"{BASE}/login")
    time.sleep(4)

    # Check if we hit CrowdSec captcha
    page_src = driver.page_source or ""
    if "crowdsec" in page_src.lower() or "captcha" in page_src.lower():
        print("  CrowdSec captcha detected. Waiting for manual solve (or auto-clear)...")
        print(f"  Browser is open — solve the captcha if needed. Waiting up to {max_wait}s...")
        for i in range(max_wait // 3):
            time.sleep(3)
            page_src = driver.page_source or ""
            if "crowdsec" not in page_src.lower() and "captcha" not in page_src.lower():
                if "login" in driver.current_url.lower():
                    print("  Captcha cleared! Loading login page...")
                    driver.get(f"{BASE}/login")
                    time.sleep(3)
                break
        else:
            print("  Captcha not cleared in time. Aborting.")
            return False

    # Wait for password field to appear
    pwd_found = False
    for attempt in range(20):
        try:
            pwd = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
            if pwd.is_displayed():
                pwd_found = True
                break
        except:
            pass
        time.sleep(1)

    if not pwd_found:
        print("  Password field not found. Page title:", driver.title)
        print("  Current URL:", driver.current_url)
        return False

    # Fill credentials using native JS setters (SPA-compatible)
    driver.execute_script("""
        const pwd = document.querySelector('input[type="password"]');
        const user = document.querySelector('input[type="text"], input[type="email"]');
        const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        if (user) { ns.call(user, arguments[0]); user.dispatchEvent(new Event('input', {bubbles: true})); }
        if (pwd) { ns.call(pwd, arguments[1]); pwd.dispatchEvent(new Event('input', {bubbles: true})); }
    """, USERNAME, PASSWORD)
    time.sleep(1)
    driver.find_element(By.CSS_SELECTOR, 'input[type="password"]').send_keys(Keys.ENTER)
    time.sleep(5)

    # Check for captcha again after submit
    page_src = driver.page_source or ""
    if "crowdsec" in page_src.lower() or "captcha" in page_src.lower():
        print("  Captcha after login submit. Waiting for clearance...")
        for i in range(40):
            time.sleep(3)
            page_src = driver.page_source or ""
            if "crowdsec" not in page_src.lower() and "captcha" not in page_src.lower():
                break
        time.sleep(3)

    ok = "login" not in driver.current_url.lower()
    print(f"  Login {'OK' if ok else 'FAILED'}: {driver.current_url}")
    return ok


def scrape_whosawme(driver):
    """Scrape all visitors from /settings/whosawme."""
    print("[2] Scraping Who Saw Me...")
    driver.get(f"{BASE}/settings/whosawme")
    time.sleep(5)

    # Scroll to load all visitors
    for _ in range(5):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)

    visitors = driver.execute_script("""
        const result = [];
        const seen = new Set();

        // Method 1: Profile photo links
        const profileImgs = document.querySelectorAll('img[alt="Profile photo"], img[alt="profile-picture"]');
        for (const img of profileImgs) {
            const a = img.closest('a');
            if (a && a.href) {
                const path = new URL(a.href).pathname;
                const username = path.replace('/', '');
                if (username && !seen.has(username) &&
                    !['settings','gay-massage','stream','masseurcams','advertise','about','login','sitemap','topics','robots','api'].includes(username) &&
                    username.length > 2) {
                    seen.add(username);
                    result.push({username: username, url: a.href, name: username});
                }
            }
        }

        // Method 2: Any single-segment path links
        const links = Array.from(document.querySelectorAll('a[href]'));
        for (const a of links) {
            try {
                const href = a.href;
                if (!href.startsWith('https://rentmasseur.com/')) continue;
                const path = new URL(href).pathname;
                if (path && path !== '/' && path.split('/').length === 2 && path.split('/')[1] !== '') {
                    const username = path.replace('/', '');
                    if (!seen.has(username) &&
                        !['settings','gay-massage','stream','masseurcams','advertise','about','login','sitemap','topics','robots','api'].includes(username) &&
                        !username.startsWith('_') && username.length > 2) {
                        seen.add(username);
                        result.push({username: username, url: href, name: username});
                    }
                }
            } catch(e) {}
        }

        return result;
    """)

    print(f"  Found {len(visitors)} visitors")
    for v in visitors[:10]:
        print(f"    {v['name']}")
    return visitors


def visit_and_message(driver, visitor, message_text, dry_run=False):
    """Visit a profile and send a message."""
    uname = visitor["username"]
    url = visitor["url"]
    result = {"username": uname, "url": url, "visited": False, "messaged": False}

    # Visit profile
    driver.get(url)
    time.sleep(3)
    result["visited"] = True
    result["page_title"] = driver.title[:60]

    if dry_run:
        print(f"  [DRY] visited {uname}: {driver.title[:40]}")
        return result

    # Find and click message button
    try:
        # Look for message/contact button — could be various forms
        message_btn = None
        for selector in [
            'button[class*="message"]',
            'a[class*="message"]',
            'button[class*="contact"]',
            'a[class*="contact"]',
            'a[href*="message"]',
            'a[href*="mail"]',
            'button[aria-label*="message"]',
            'button[aria-label*="Message"]',
        ]:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, selector)
                if btn.is_displayed():
                    message_btn = btn
                    break
            except:
                continue

        # Fallback: search all buttons/links for "message" text
        if not message_btn:
            elements = driver.find_elements(By.CSS_SELECTOR, 'button, a')
            for el in elements:
                try:
                    txt = (el.text or "").lower().strip()
                    if txt in ["message", "contact", "send message", "email me"] and el.is_displayed():
                        message_btn = el
                        break
                except:
                    continue

        if message_btn:
            message_btn.click()
            time.sleep(3)

            # Find textarea and type message
            textarea = None
            for selector in ['textarea', 'textarea[class*="message"]', 'textarea[class*="body"]', 'textarea[placeholder*="message"]', 'div[contenteditable="true"]']:
                try:
                    ta = driver.find_element(By.CSS_SELECTOR, selector)
                    if ta.is_displayed():
                        textarea = ta
                        break
                except:
                    continue

            if textarea:
                textarea.click()
                time.sleep(0.5)
                textarea.send_keys(Keys.CONTROL, "a")
                textarea.send_keys(Keys.DELETE)
                textarea.send_keys(message_text)
                time.sleep(1)

                # Find send button
                send_btn = None
                for selector in ['button[type="submit"]', 'button[class*="send"]', 'button[class*="submit"]']:
                    try:
                        btn = driver.find_element(By.CSS_SELECTOR, selector)
                        if btn.is_displayed():
                            send_btn = btn
                            break
                    except:
                        continue

                # Fallback: search for send/submit text
                if not send_btn:
                    buttons = driver.find_elements(By.CSS_SELECTOR, 'button')
                    for btn in buttons:
                        try:
                            txt = (btn.text or "").lower().strip()
                            if txt in ["send", "submit", "reply", "send message"] and btn.is_displayed():
                                send_btn = btn
                                break
                        except:
                            continue

                if send_btn:
                    send_btn.click()
                    time.sleep(3)
                    result["messaged"] = True
                    print(f"  MESSAGED {uname}: sent")
                else:
                    # Try Enter key
                    textarea.send_keys(Keys.CONTROL, Keys.ENTER)
                    time.sleep(3)
                    result["messaged"] = True
                    print(f"  MESSAGED {uname}: sent (Ctrl+Enter)")
            else:
                print(f"  {uname}: no textarea found after clicking message")
        else:
            print(f"  {uname}: no message button found on profile")

    except Exception as e:
        result["error"] = str(e)[:100]
        print(f"  {uname}: error — {e}")

    return result


def read_and_reply_mailbox(driver, message_text, dry_run=False):
    """Go to mailbox, read all conversations, reply to each."""
    print("\n[4] Reading mailbox and replying...")
    driver.get(f"{BASE}/settings/mailbox")
    time.sleep(5)

    # Collect all conversation links
    conversations = driver.execute_script("""
        const result = [];
        const seen = new Set();
        // Mailbox list items
        const items = document.querySelectorAll('[class*="mail"], [class*="conversation"], [class*="thread"], a[href*="mailbox"]');
        for (const item of items) {
            const text = item.textContent || '';
            const link = item.tagName === 'A' ? item.href : (item.querySelector('a')?.href || '');
            if (link && link.includes('/mailbox/') && !seen.has(link)) {
                seen.add(link);
                result.push({url: link, text: text.substring(0, 80)});
            }
        }
        // Also try generic links
        const links = Array.from(document.querySelectorAll('a[href]'));
        for (const a of links) {
            if (a.href.includes('/mailbox/') && !seen.has(a.href)) {
                seen.add(a.href);
                result.push({url: a.href, text: (a.textContent || '').substring(0, 80)});
            }
        }
        return result;
    """)

    print(f"  Found {len(conversations)} conversations")
    if not conversations:
        # Try clicking on mailbox items directly
        mail_items = driver.find_elements(By.CSS_SELECTOR, '[class*="mail-item"], [class*="conversation-item"], [class*="email"]')
        print(f"  Found {len(mail_items)} mail items by class")

    replied = []
    for conv in conversations[:30]:
        try:
            driver.get(conv["url"])
            time.sleep(3)

            if dry_run:
                print(f"  [DRY] would reply to: {conv['text'][:40]}")
                replied.append({"url": conv["url"], "replied": False, "dry_run": True})
                continue

            # Find reply textarea
            textarea = None
            for selector in ['textarea', 'textarea[class*="reply"]', 'textarea[class*="message"]', 'div[contenteditable="true"]']:
                try:
                    ta = driver.find_element(By.CSS_SELECTOR, selector)
                    if ta.is_displayed():
                        textarea = ta
                        break
                except:
                    continue

            if textarea:
                textarea.click()
                time.sleep(0.5)
                textarea.send_keys(message_text)
                time.sleep(1)

                # Find send button
                send_btn = None
                buttons = driver.find_elements(By.CSS_SELECTOR, 'button')
                for btn in buttons:
                    try:
                        txt = (btn.text or "").lower().strip()
                        if txt in ["send", "reply", "submit", "send reply"] and btn.is_displayed():
                            send_btn = btn
                            break
                    except:
                        continue

                if send_btn:
                    send_btn.click()
                    time.sleep(3)
                    print(f"  REPLIED to {conv['text'][:40]}")
                    replied.append({"url": conv["url"], "replied": True})
                else:
                    textarea.send_keys(Keys.CONTROL, Keys.ENTER)
                    time.sleep(3)
                    print(f"  REPLIED to {conv['text'][:40]} (Ctrl+Enter)")
                    replied.append({"url": conv["url"], "replied": True})
            else:
                print(f"  No reply textarea for {conv['text'][:40]}")

        except Exception as e:
            print(f"  Error replying: {e}")

    return replied


def write_receipt(action, data, success=True):
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    receipt = {
        "action": action,
        "success": success,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data,
    }
    rpath = RECEIPTS_DIR / f"{action}_{ts}.json"
    rpath.write_text(json.dumps(receipt, indent=2))
    return str(rpath)


def main():
    parser = argparse.ArgumentParser(description="Visit visitors + send messages + reply to mailbox")
    parser.add_argument("--dry-run", action="store_true", help="List targets without messaging")
    parser.add_argument("--limit", type=int, default=50, help="Max visitors to process")
    parser.add_argument("--message", type=str, default=DEFAULT_MESSAGE, help="Message to send")
    parser.add_argument("--skip-mailbox", action="store_true", help="Skip mailbox reply phase")
    parser.add_argument("--visitors-only", action="store_true", help="Only visit+message whosawme, skip mailbox")
    args = parser.parse_args()

    print("=== RENTMASSEUR VISIT + MESSAGE PIPE ===")
    print(f"  Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"  Limit: {args.limit}")
    print(f"  Message: {args.message[:80]}...")

    driver = get_driver()
    try:
        if not login(driver):
            sys.exit(1)

        # Phase 1: Who Saw Me
        visitors = scrape_whosawme(driver)
        if not visitors:
            print("  No visitors found. Exiting.")
            write_receipt("visit_message", {"visitors": 0, "messaged": 0}, success=False)
            return

        # Phase 2: Visit + Message each visitor
        print(f"\n[3] Visiting + messaging {min(len(visitors), args.limit)} visitors...")
        results = []
        for i, v in enumerate(visitors[:args.limit]):
            print(f"  [{i+1}/{min(len(visitors), args.limit)}] {v['username']}...")
            r = visit_and_message(driver, v, args.message, args.dry_run)
            results.append(r)
            time.sleep(2)

        visited_count = sum(1 for r in results if r.get("visited"))
        messaged_count = sum(1 for r in results if r.get("messaged"))

        # Phase 3: Mailbox reply
        mailbox_replies = []
        if not args.visitors_only and not args.skip_mailbox:
            mailbox_replies = read_and_reply_mailbox(driver, args.message, args.dry_run)

        # Write receipt
        rpath = write_receipt("visit_message", {
            "visitors_found": len(visitors),
            "visited": visited_count,
            "messaged": messaged_count,
            "mailbox_replies": len(mailbox_replies),
            "dry_run": args.dry_run,
            "message_sent": args.message[:200],
            "results": results,
            "mailbox_results": mailbox_replies,
        })

        # Save data
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "visit_message_latest.json").write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "visitors_found": len(visitors),
            "visited": visited_count,
            "messaged": messaged_count,
            "mailbox_replies": len(mailbox_replies),
            "results": results,
            "mailbox_results": mailbox_replies,
        }, indent=2))

        print(f"\n=== PIPE COMPLETE ===")
        print(f"  Visitors found: {len(visitors)}")
        print(f"  Visited: {visited_count}")
        print(f"  Messaged: {messaged_count}")
        print(f"  Mailbox replies: {len(mailbox_replies)}")
        print(f"  Receipt: {rpath}")
        print(f"  Data: {DATA_DIR / 'visit_message_latest.json'}")

    finally:
        driver.quit()
        print("\nDone.")


if __name__ == "__main__":
    main()
