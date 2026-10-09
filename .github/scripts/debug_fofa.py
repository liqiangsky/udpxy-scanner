import os
import re
import asyncio
import json
from pathlib import Path

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


async def save_debug_page(page):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    title = await page.title()
    url = page.url
    html = await page.content()
    text = await page.evaluate("() => document.body.innerText")

    meta = {
        "url": url,
        "title": title,
        "html_length": len(html),
        "text_length": len(text),
        "contains_verification": any(
            kw in text.lower()
            for kw in [
                "just a moment",
                "验证",
                "checking your browser",
                "access denied",
                "cloudflare",
                "security check",
                "please wait",
                "captcha",
                "robot",
            ]
        ),
        "text_sample": text[:2000],
        "html_sample": html[:2000],
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


async def inspect_selectors(page):
    selectors = [
        "body",
        "#app",
        "#root",
        ".list-cell",
        ".result-item",
        "td",
        "a[href*=':']",
        "[class*=host]",
        "[class*=ip]",
        "[class*=result]",
    ]
    result = {}
    for sel in selectors:
        try:
            els = await page.query_selector_all(sel)
            result[sel] = len(els)
        except Exception as e:
            result[sel] = f"ERR: {e}"
    return result


async def main():
    print("[INFO] FOFA debug script start")
    print(f"[INFO] URL: {FOFA_URL}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        try:
            await page.goto(FOFA_URL, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            meta = await save_debug_page(page)
            selector_summary = await inspect_selectors(page)

            print("\n[INFO] PAGE INFO")
            print(f"- current_url: {page.url}")
            print(f"- title: {meta['title']}")
            print(f"- html_length: {meta['html_length']}")
            print(f"- text_length: {meta['text_length']}")
            print(f"- contains_verification: {meta['contains_verification']}")

            print("\n[INFO] SELECTOR SUMMARY")
            for key, value in selector_summary.items():
                print(f"- {key}: {value}")

            print("\n[INFO] TEXT SAMPLE (first 2000 chars)")
            print(repr(meta["text_sample"]))

            print("\n[INFO] HTML SAMPLE (first 1000 chars)")
            print(meta["html_sample"][:1000])

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


if __name__ == "__main__":
    asyncio.run(main())
