"""Small stdlib HTTP helpers shared by the checks.

Only absolute http(s) URLs are ever fetched, and redirects are only followed to
http(s) URLs — so a hostile sitemap, page or server cannot point the tool at
``file://`` paths or other URL schemes that ``urllib`` would otherwise open.
"""

import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 ivanlabs-site-baseline"
)

WEB_SCHEMES = ("http", "https")

# The sitemaps.org limit for one uncompressed sitemap file; nothing legitimate
# this tool downloads is larger, so anything bigger is refused.
MAX_BODY_BYTES = 50 * 1024 * 1024


def is_web_url(url):
    """True for an absolute http(s) URL with a host — the only kind this tool fetches."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() in WEB_SCHEMES and bool(parts.hostname)


def host_of(url):
    """Lower-case hostname of *url* ('' if it has none)."""
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Report a redirect instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _WebOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but only to http(s) URLs (urllib also allows ftp://)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_web_url(newurl):
            return None  # urllib then raises HTTPError with the redirect status
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener(follow):
    return urllib.request.build_opener(_WebOnlyRedirect() if follow else _NoRedirect())


def fetch_status(url, follow=True, timeout=15):
    """Return (status_code, final_or_location_url).

    Status 0 means the request could not be made: a network or TLS error, an
    invalid URL, or a URL that is not http(s), which is never fetched.
    """
    if not is_web_url(url):
        return 0, ""
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    try:
        with _opener(follow).open(req, timeout=timeout) as resp:
            return resp.status, resp.geturl()
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location", "") if exc.headers else ""
        return exc.code, location
    # Any other failure to complete the request (DNS, TLS, timeout, invalid
    # URL) is reported as status 0 rather than aborting the whole run.
    except Exception:  # noqa: BLE001
        return 0, ""


def fetch_text(url, timeout=20, limit=None):
    """GET an http(s) URL and return ``(final_url, text)``.

    Raises ValueError for a non-http(s) URL or a body larger than *limit*
    bytes (default MAX_BODY_BYTES); network errors propagate to the caller.
    """
    if limit is None:
        limit = MAX_BODY_BYTES
    if not is_web_url(url):
        raise ValueError(f"refusing to fetch a non-http(s) URL: {url!r}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with _opener(True).open(req, timeout=timeout) as resp:
        body = resp.read(limit + 1)
        final_url = resp.geturl()
    if len(body) > limit:
        raise ValueError(f"response is larger than {limit} bytes: {url!r}")
    return final_url, body.decode("utf-8", errors="ignore")


def check_urls(urls, expect=200, follow=True, workers=8):
    """Fetch *urls* in parallel; return [(status, url)] for non-*expect* results."""
    failures = []

    def one(url):
        code, _ = fetch_status(url, follow=follow)
        if code != expect:
            failures.append((code or 0, url))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, urls))
    return sorted(failures)
