"""Link audit for a built static site directory.

Walks every .html file, collects every href/src, resolves internal targets
against the filesystem, and reports per-page internal/external counts plus
any broken internal targets. Optionally live-checks external URLs.
"""

import os
import sys
from html.parser import HTMLParser
from urllib.parse import urlparse, unquote

from .http import check_urls

SKIP_SCHEMES = ("#", "mailto:", "tel:", "data:", "javascript:")


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self._chrome = []  # header/footer/nav nesting

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("header", "footer", "nav"):
            self._chrome.append(tag)
        for key in ("href", "src"):
            if a.get(key):
                self.refs.append((a[key], bool(self._chrome)))

    def handle_endtag(self, tag):
        if tag in ("header", "footer", "nav") and self._chrome:
            self._chrome.pop()


def _target_exists(root, path):
    p = unquote(path.split("#")[0].split("?")[0]).lstrip("/")
    if p == "":
        return True
    fs = os.path.join(root, p)
    return (
        os.path.isfile(fs)
        or os.path.isfile(os.path.join(fs, "index.html"))
        or os.path.isfile(fs + "/index.html")
    )


def audit(root, site_hosts, check_external=False):
    """Audit the built site at *root*. Returns an exit code (0 = clean)."""
    pages = []
    for r, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".html"):
                pages.append(os.path.join(r, name))
    if not pages:
        print(f"error: no .html files under {root}", file=sys.stderr)
        return 2

    internal = {}   # path -> first source page
    external = set()
    rows = []

    for page in pages:
        parser = _LinkParser()
        with open(page, encoding="utf-8", errors="ignore") as fh:
            parser.feed(fh.read())
        n_int = n_ext = 0
        for ref, _chrome in parser.refs:
            if ref.startswith(SKIP_SCHEMES):
                continue
            u = urlparse(ref)
            if u.scheme in ("http", "https"):
                host = u.netloc.lower()
                if any(host == h or host.endswith("." + h) for h in site_hosts):
                    internal.setdefault(u.path or "/", page)
                    n_int += 1
                else:
                    external.add(ref.split("#")[0])
                    n_ext += 1
            else:
                internal.setdefault(ref, page)
                n_int += 1
        rows.append((os.path.relpath(page, root), n_int, n_ext))

    broken = [(t, src) for t, src in sorted(internal.items()) if not _target_exists(root, t)]

    print(f"pages scanned:           {len(pages)}")
    print(f"unique internal targets: {len(internal)}")
    print(f"unique external URLs:    {len(external)}")
    print(f"broken internal targets: {len(broken)}")
    for target, src in broken:
        print(f"  BROKEN {target}  (first seen in {os.path.relpath(src, root)})")

    exit_code = 1 if broken else 0

    if check_external and external:
        print(f"\nlive-checking {len(external)} external URLs ...")
        failures = check_urls(sorted(external))
        for code, url in failures:
            print(f"  {code} {url}")
        print(f"external failures: {len(failures)}")
        if failures:
            exit_code = 1

    return exit_code
