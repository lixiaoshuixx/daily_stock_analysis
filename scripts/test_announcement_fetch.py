#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone test: fetch announcement content from cninfo (no LLM).
Verifies PDF/HTML download and text extraction for 600892 sample URLs.
"""
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.restructuring_service import _fetch_announcement_content

# Sample cninfo detail URLs for 600892 (from announcements list)
TEST_URLS = [
    "http://www.cninfo.com.cn/new/disclosure/detail?stockCode=600892&announcementId=1224902197&orgId=gssh0600892&announcementTime=2025-12-27",  # 债务豁免
    "http://www.cninfo.com.cn/new/disclosure/detail?stockCode=600892&announcementId=1224987761&orgId=gssh0600892&announcementTime=2026-02-28",  # 减持计划
]

def main():
    print("Testing announcement content fetch (cninfo PDF/HTML)...")
    for i, url in enumerate(TEST_URLS, 1):
        print(f"\n--- Test {i}: {url.split('announcementId=')[1].split('&')[0]} ---")
        text = _fetch_announcement_content(url)
        if text:
            print(f"OK: got {len(text)} chars")
            print("Preview (first 400 chars):", text[:400].replace("\n", " ") + "...")
        else:
            print("FAIL: empty content")
    print("\nDone.")

if __name__ == "__main__":
    main()
