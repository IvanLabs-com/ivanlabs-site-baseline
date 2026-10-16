"""Live URL verification from a sitemap or URL list.

Fetches a sitemap (index or urlset), extracts every <loc>, and verifies each
returns HTTP 200 — the fastest possible "did the deploy break anything
crawlers know about" check.

Sitemap content is treated as untrusted input. Only http(s) URLs are fetched,
and by default only URLs on the sitemap's own host — the sitemaps.org rule —
so a hostile or compromised sitemap cannot steer the run to local files or to
other machines. Anything skipped is reported as a finding instead.
"""

import html
import re
import sys

from .http import check_urls, fetch_text, host_of, is_web_url
from .output import safe

LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def _collect(root_url, allow_cross_host):
    """Walk the sitemap and any nested indexes (iteratively, each fetched once).

    Returns ``(page_urls, skipped)``, where *skipped* is a list of
    ``(reason, url)`` for <loc> values that were not followed.
    """
    final_url, body = fetch_text(root_url)
    hosts = {host_of(root_url), host_of(final_url)}
    seen = {root_url, final_url}
    pages, skipped = [], []
    pending = [body]
    while pending:
        body = pending.pop()
        is_index = "<sitemapindex" in body
        for raw in LOC_RE.findall(body):
            loc = html.unescape(raw)  # sitemaps entity-escape '&' as '&amp;'
            if not is_web_url(loc):
                skipped.append(("not an http(s) URL", loc))
            elif not allow_cross_host and host_of(loc) not in hosts:
                skipped.append(("different host", loc))
            elif not is_index:
                pages.append(loc)
            elif loc not in seen:
                seen.add(loc)
                pending.append(fetch_text(loc)[1])
    return pages, skipped


def verify(sitemap_url, allow_cross_host=False):
    """Check every URL in the sitemap (recursing into indexes). Exit code 0 = all 200."""
    if not is_web_url(sitemap_url):
        print(f"error: not an http(s) URL: {safe(sitemap_url)}", file=sys.stderr)
        return 2
    try:
        pages, skipped = _collect(sitemap_url, allow_cross_host)
    # Network, TLS or size errors anywhere in the sitemap tree end the run cleanly.
    except Exception as exc:  # noqa: BLE001
        print(f"error: could not fetch sitemap: {safe(exc)}", file=sys.stderr)
        return 2
    urls = sorted(set(pages))
    skipped = sorted(set(skipped))
    if not urls and not skipped:
        print("error: sitemap contained no URLs", file=sys.stderr)
        return 2

    print(f"checking {len(urls)} URLs from {safe(sitemap_url)} ...")
    failures = check_urls(urls)
    for code, url in failures:
        print(f"  {code} {safe(url)}")
    print(f"{len(urls) - len(failures)}/{len(urls)} OK")

    if skipped:
        print(f"\nnot fetched: {len(skipped)}")
        for reason, url in skipped:
            print(f"  SKIPPED ({reason}) {safe(url)}")
        if any(reason == "different host" for reason, _ in skipped):
            print("  (sitemaps may only list URLs on their own host; "
                  "pass --allow-cross-host to check them anyway)")
    return 1 if (failures or skipped) else 0
