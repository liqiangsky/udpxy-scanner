import os
import re
import json
from pathlib import Path
from datetime import datetime

import cloudscraper


REPO_ROOT = Path(__file__).resolve().parents[2]
DEBUG_DIR = REPO_ROOT / ".github" / "debug"
OUTPUT_HTML = DEBUG_DIR / "fofa_debug_page.html"
OUTPUT_TEXT = DEBUG_DIR / "fofa_debug_page.txt"
OUTPUT_JSON = DEBUG_DIR / "fofa_debug_meta.json"

FOFA_QBASE64 = os.getenv(
    "FOFA_QBASE64",
    "Y291bnRyeT0iQ04iICYmIHVkcHh5ICYmIENvbnRlbnQtVHlwZTogYXBwbGljYXRpb24vb2N0ZXQtc3RyZWFt",
)
FOFA_URL = f"https://fofa.so/result?qbase64={FOFA_QBASE64}"


def is_verification_page(text: str, html: str) -> bool:
    """Check whether FOFA returned a Cloudflare verification page."""
    lower = (text or "").lower()
    html_lower = (html or "").lower()

    markers = [
        "just a moment",
        "performing security verification",
        "checking your browser",
        "access denied",
        "cloudflare",
        "security check",
        "captcha",
        "please wait",
        "verify you are not a bot",
        "ray id",
        "browser verification",
        "challenge-platform",
    ]

    if any(marker in lower for marker in markers):
        return True
    if any(marker in html_lower for marker in markers):
        return True
    return False


def save_debug_page(html: str, text: str, url: str):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    verification = is_verification_page(text, html)
    has_results = bool(re.search(r"host|ip|title|port", text, re.I))

    meta = {
        "url": url,
        "timestamp": datetime.utcnow().isoformat(),
        "html_length": len(html),
        "text_length": len(text),
        "contains_verification": verification,
        "has_results": has_results,
        "text_sample": text[:3500],
        "html_sample": html[:3500],
    }

    OUTPUT_HTML.write_text(html, encoding="utf-8")
    OUTPUT_TEXT.write_text(text, encoding="utf-8")
    OUTPUT_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return meta


def main():
    print("[INFO] FOFA debug script start (cloudscraper version)")
    print(f"[INFO] URL: {FOFA_URL}")
    print(f"[INFO] Timestamp: {datetime.utcnow().isoformat()}")

    try:
        scraper = cloudscraper.create_scraper(
            browser={
                "browser": "chrome",
                "platform": "windows",
                "desktop": True,
            }
        )

        print("\n[INFO] Sending request with cloudscraper...")
        response = scraper.get(
            FOFA_URL,
            timeout=60,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
                "Referer": "https://fofa.so/",
            },
        )

        response.raise_for_status()
        html = response.text
        url = response.url

        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

        print(f"[OK] Response status: {response.status_code}")
        print(f"[OK] Response URL: {url}")
        print(f"[OK] HTML length: {len(html)}")
        print(f"[OK] Text length: {len(text)}")

        meta = save_debug_page(html, text, url)

        print("\n[INFO] PAGE INFO")
        print(f"- url: {meta['url']}")
        print(f"- html_length: {meta['html_length']}")
        print(f"- text_length: {meta['text_length']}")
        print(f"- contains_verification: {meta['contains_verification']}")
        print(f"- has_results: {meta['has_results']}")

        print("\n[INFO] TEXT SAMPLE (first 2000 chars)")
        print(meta["text_sample"][:2000])

        print("\n[INFO] HTML SAMPLE (first 1000 chars)")
        print(meta["html_sample"][:1000])

        if meta["contains_verification"]:
            print("\n[WARN] Cloudflare verification page detected")
        else:
            print("\n[OK] Page appears to be real content")

        print(f"\n[INFO] debug files saved to: {DEBUG_DIR}")
        print(f"- {OUTPUT_HTML}")
        print(f"- {OUTPUT_TEXT}")
        print(f"- {OUTPUT_JSON}")

    except Exception as e:
        print(f"[ERROR] Request failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
