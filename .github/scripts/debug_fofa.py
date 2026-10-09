import os
import re
import json
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright


REPO_ROOT = Path(__file__).resolve().parents[2]
DEBUG_DIR = REPO_ROOT / ".github" / "debug"
OUTPUT_HTML = DEBUG_DIR / "fofa_debug_page.html"
OUTPUT_TEXT = DEBUG_DIR / "fofa_debug_page.txt"
OUTPUT_JSON = DEBUG_DIR / "fofa_debug_meta.json"
OUTPUT_PNG = DEBUG_DIR / "fofa_debug_page.png"

FOFA_QBASE64 = os.getenv(
    "FOFA_QBASE64",
    "Y291bnRyeT0iQ04iICYmIHVkcHh5ICYmIENvbnRlbnQtVHlwZTogYXBwbGljYXRpb24vb2N0ZXQtc3RyZWFt",
)
FOFA_URL = f"https://fofa.so/result?qbase64={FOFA_QBASE64}"


def is_verification_page(text: str, html: str) -> bool:
    """Check if page is Cloudflare verification"""
    lower = (text or "").lower()
    html_lower = (html or "").lower()
    
    markers = [
        "just a moment",
        "performing security verification",
        "checking your browser",
        "cloudflare",
        "verify you are not a bot",
        "ray id",
    ]
    
    return any(m in lower or m in html_lower for m in markers)


async def save_debug_page(page):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    title = await page.title()
    url = page.url
    html = await page.content()
    text = await page.evaluate("() => document.body.innerText")

    verification = is_verification_page(text, html)

    meta = {
        "url": url,
        "title": title,
        "timestamp": datetime.utcnow().isoformat(),
        "html_length": len(html),
        "text_length": len(text),
        "contains_verification": verification,
        "text_sample": text[:3500],
        "html_sample": html[:3500],
    }

    OUTPUT_HTML.write_text(html, encoding="utf-8")
    OUTPUT_TEXT.write_text(text, encoding="utf-8")
    OUTPUT_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        await page.screenshot(path=str(OUTPUT_PNG), full_page=True)
        print(f"[OK] screenshot saved: {OUTPUT_PNG}")
    except Exception as e:
        print(f"[WARN] screenshot failed: {e}")

    return meta


async def main():
    print("[INFO] FOFA debug script start (playwright + anti-detection)")
    print(f"[INFO] URL: {FOFA_URL}")
    print(f"[INFO] Timestamp: {datetime.utcnow().isoformat()}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-web-resources",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            ignore_https_errors=True,
        )

        # Anti-detection: hide automation markers
        await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        Object.defineProperty(navigator, 'permissions', { get: () => ({ query: () => Promise.resolve({ state: 'granted' }) }) });
        window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        try:
            print("\n[INFO] Navigating to FOFA...")
            await page.goto(FOFA_URL, timeout=120000, wait_until="domcontentloaded")
            
            print("[INFO] Waiting for Cloudflare verification (15s)...")
            await page.wait_for_timeout(15000)
            
            # Try to detect if verification passed
            text_sample = await page.evaluate("() => document.body.innerText")
            
            if "performing security verification" in text_sample.lower() or "just a moment" in text_sample.lower():
                print("[WARN] Still on Cloudflare verification page, waiting more...")
                await page.wait_for_timeout(10000)

            meta = await save_debug_page(page)

            print("\n[INFO] PAGE INFO")
            print(f"- url: {meta['url']}")
            print(f"- title: {meta['title']}")
            print(f"- html_length: {meta['html_length']}")
            print(f"- text_length: {meta['text_length']}")
            print(f"- contains_verification: {meta['contains_verification']}")

            print("\n[INFO] TEXT SAMPLE (first 2000 chars)")
            print(meta["text_sample"][:2000])

            if meta["contains_verification"]:
                print("\n[WARN] Cloudflare verification page still present")
            else:
                print("\n[OK] Got real FOFA content!")

            print(f"\n[INFO] debug files saved to: {DEBUG_DIR}")
            print(f"- {OUTPUT_HTML}")
            print(f"- {OUTPUT_TEXT}")
            print(f"- {OUTPUT_JSON}")
            print(f"- {OUTPUT_PNG}")

        except Exception as e:
            print(f"[ERROR] failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await context.close()
            await browser.close()


import asyncio
if __name__ == "__main__":
    asyncio.run(main())
