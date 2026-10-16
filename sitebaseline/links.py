"""Link audit for a built static site directory.

Walks every .html file, collects every href/src, resolves internal targets
against the filesystem, and reports per-page internal/external counts plus
any broken internal targets. Optionally live-checks external URLs.

Links are resolved the way a browser resolves them: relative links from the
page's own folder, root-relative links from the site root. Percent-decoding
happens before ``..`` is collapsed, and ``..`` stops at the site root, so no
link can point the audit at files outside the build directory.
"""

import os
import posixpath
import sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

from .http import check_urls
from .output import safe

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


def _site_path(path, page_dir):
    """Resolve a link path to a normalized, site-absolute path ('/a/b.html')."""
    path = unquote(path)
    if not path.startswith("/"):
        path = posixpath.join(page_dir, path)
    resolved = "/" + posixpath.normpath(path).lstrip("/")
    if path.endswith("/") and resolved != "/":
        resolved += "/"
    return resolved


def _target_exists(root, site_path):
    rel = site_path.strip("/")
    if rel == "":
        return True
    fs = os.path.join(root, *rel.split("/"))
    return os.path.isfile(fs) or os.path.isfile(os.path.join(fs, "index.html"))


def audit(root, site_hosts, check_external=False):
    """Audit the built site at *root*. Returns an exit code (0 = clean)."""
    pages = []
    for r, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".html"):
                pages.append(os.path.join(r, name))
    if not pages:
        print(f"error: no .html files under {safe(root)}", file=sys.stderr)
        return 2

    internal = {}      # site path -> first source page
    unsupported = {}   # link with an unknown URL scheme -> first source page
    external = set()
    rows = []

    for page in pages:
        page_rel = os.path.relpath(page, root).replace(os.sep, "/")
        page_dir = "/" + posixpath.dirname(page_rel)
        parser = _LinkParser()
        with open(page, encoding="utf-8", errors="ignore") as fh:
            parser.feed(fh.read())
        n_int = n_ext = 0
        for raw, _chrome in parser.refs:
            ref = raw.strip()
            if not ref or ref.lower().startswith(SKIP_SCHEMES):
                continue
            u = urlparse(ref)
            scheme = u.scheme.lower()
            if scheme in ("http", "https") or (not scheme and u.netloc):
                host = (u.hostname or "").lower()
                if any(host == h or host.endswith("." + h) for h in site_hosts):
                    internal.setdefault(_site_path(u.path or "/", "/"), page)
                    n_int += 1
                else:
                    url = ref if scheme else "https:" + ref  # protocol-relative
                    external.add(url.split("#")[0])
                    n_ext += 1
            elif scheme:
                unsupported.setdefault(ref, page)  # e.g. a typo such as 'htps://'
                n_int += 1
            else:
                if u.path:  # a bare '?query' points back at the page itself
                    internal.setdefault(_site_path(u.path, page_dir), page)
                n_int += 1
        rows.append((page_rel, n_int, n_ext))

    broken = [(t, src) for t, src in sorted(internal.items()) if not _target_exists(root, t)]
    broken += sorted(unsupported.items())

    print(f"pages scanned:           {len(pages)}")
    print(f"unique internal targets: {len(internal)}")
    print(f"unique external URLs:    {len(external)}")
    print(f"broken internal targets: {len(broken)}")
    for target, src in broken:
        note = "  [unsupported URL scheme]" if target in unsupported else ""
        print(f"  BROKEN {safe(target)}  (first seen in {safe(os.path.relpath(src, root))}){note}")

    exit_code = 1 if broken else 0

    if check_external and external:
        print(f"\nlive-checking {len(external)} external URLs ...")
        failures = check_urls(sorted(external))
        for code, url in failures:
            print(f"  {code} {safe(url)}")
        print(f"external failures: {len(failures)}")
        if failures:
            exit_code = 1

    return exit_code
