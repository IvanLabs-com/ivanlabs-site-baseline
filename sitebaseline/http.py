"""Small stdlib HTTP helpers shared by the checks."""

import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 ivanlabs-site-baseline"
)


def fetch_status(url, follow=True, timeout=15):
    """Return (status_code, final_or_location_url). 0 on network error."""
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    handlers = [] if follow else [_NoRedirect()]
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.geturl()
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location", "") if exc.headers else ""
        return exc.code, location
    except Exception:
        return 0, ""


def check_urls(urls, expect=200, follow=True, workers=8):
    """Fetch *urls* in parallel; return [(status, url)] for non-*expect* results."""
    failures = []

    def one(url):
        code, _ = fetch_status(url, follow=follow)
        if code != expect:
            failures.append((code, url))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, urls))
    return sorted(failures)
