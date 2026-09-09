"""Live URL verification from a sitemap or URL list.

Fetches a sitemap (index or urlset), extracts every <loc>, and verifies each
returns HTTP 200 — the fastest possible "did the deploy break anything
crawlers know about" check.
"""

import re
import sys
import urllib.request

from .http import UA, check_urls

LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _collect(sitemap_url, seen):
    if sitemap_url in seen:
        return []
    seen.add(sitemap_url)
    body = _fetch(sitemap_url)
    locs = LOC_RE.findall(body)
    if "<sitemapindex" in body:
        urls = []
        for child in locs:
            urls.extend(_collect(child, seen))
        return urls
    return locs


def verify(sitemap_url):
    """Check every URL in the sitemap (recursing into indexes). Exit code 0 = all 200."""
    try:
        urls = sorted(set(_collect(sitemap_url, set())))
    except Exception as exc:
        print(f"error: could not fetch sitemap: {exc}", file=sys.stderr)
        return 2
    if not urls:
        print("error: sitemap contained no URLs", file=sys.stderr)
        return 2

    print(f"checking {len(urls)} URLs from {sitemap_url} ...")
    failures = check_urls(urls)
    for code, url in failures:
        print(f"  {code} {url}")
    print(f"{len(urls) - len(failures)}/{len(urls)} OK")
    return 1 if failures else 0
