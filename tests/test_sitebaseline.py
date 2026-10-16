"""Tests for site-baseline. Standard library only; network access stays on 127.0.0.1.

Run from the repository root:

    python3 -m unittest discover -s tests -v
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from unittest import mock

from sitebaseline import __version__, http, links, live, redirects, schema
from sitebaseline.__main__ import main
from sitebaseline.output import safe

# --------------------------------------------------------------- test server --


class _Handler(BaseHTTPRequestHandler):
    routes: ClassVar[dict] = {}      # path -> (status, headers, body)
    requested: ClassVar[list] = []   # every path the server was asked for, in order

    def do_GET(self):
        type(self).requested.append(self.path)
        status, headers, body = self.routes.get(self.path, (404, {}, b"not found"))
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


SERVER = None
BASE = ""
_ENV = mock.patch.dict(os.environ, {"no_proxy": "*", "NO_PROXY": "*"})


def setUpModule():
    global SERVER, BASE
    _ENV.start()  # keep requests to the local test server away from any proxy
    SERVER = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    BASE = f"http://127.0.0.1:{SERVER.server_address[1]}"
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()


def tearDownModule():
    SERVER.shutdown()
    SERVER.server_close()
    _ENV.stop()


def route(path, body=b"", status=200, **headers):
    if isinstance(body, str):
        body = body.encode()
    _Handler.routes[path] = (status, headers, body)


def run(func, *args, **kwargs):
    """Call *func*, returning (result, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        result = func(*args, **kwargs)
    return result, out.getvalue(), err.getvalue()


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        _Handler.routes = {}
        _Handler.requested = []
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)


# --------------------------------------------------------------------- tests --


class SafeOutputTest(unittest.TestCase):
    def test_escapes_terminal_control_sequences(self):
        self.assertEqual(safe("a\x1b]0;title\x07b"), "a\\x1b]0;title\\x07b")
        self.assertEqual(safe("x\ry\x7f\x9b"), "x\\x0dy\\x7f\\x9b")

    def test_escapes_bidi_overrides(self):
        self.assertEqual(safe("abc\u202edef"), "abc\\u202edef")

    def test_leaves_ordinary_text_alone(self):
        self.assertEqual(safe("Ωmega ✓ https://example.com/a?b=1"), "Ωmega ✓ https://example.com/a?b=1")


class IsWebUrlTest(unittest.TestCase):
    def test_accepts_absolute_http_urls(self):
        for url in ("http://example.com", "https://example.com/a?b", "HTTPS://Example.com/"):
            with self.subTest(url=url):
                self.assertTrue(http.is_web_url(url))

    def test_rejects_everything_else(self):
        for url in ("file:///etc/passwd", "ftp://example.com/x", "data:text/plain,x",
                    "javascript:alert(1)", "/relative/path", "https://", "http:///nohost", ""):
            with self.subTest(url=url):
                self.assertFalse(http.is_web_url(url))


class FetchTest(ServerTestCase):
    def test_returns_status_and_reports_redirects_without_following(self):
        route("/ok", "fine")
        route("/moved", status=301, Location="/ok")
        self.assertEqual(http.fetch_status(BASE + "/ok"), (200, BASE + "/ok"))
        self.assertEqual(http.fetch_status(BASE + "/moved", follow=False), (301, "/ok"))

    def test_never_follows_a_redirect_to_a_non_web_url(self):
        route("/to-ftp", status=302, Location="ftp://127.0.0.1:1/x")
        self.assertEqual(http.fetch_status(BASE + "/to-ftp"), (302, "ftp://127.0.0.1:1/x"))

    def test_refuses_file_urls(self):
        with tempfile.NamedTemporaryFile() as fh:
            self.assertEqual(http.fetch_status(Path(fh.name).as_uri()), (0, ""))
            with self.assertRaises(ValueError):
                http.fetch_text(Path(fh.name).as_uri())

    def test_refuses_bodies_over_the_size_limit(self):
        route("/big.xml", b"x" * 2048)
        with self.assertRaises(ValueError):
            http.fetch_text(BASE + "/big.xml", limit=1024)
        self.assertEqual(http.fetch_text(BASE + "/big.xml", limit=4096)[1], "x" * 2048)


class LiveTest(ServerTestCase):
    def sitemap_tree(self):
        local = self.tmp / "local.xml"
        local.write_text(f"<urlset><url><loc>{BASE}/from-local-file</loc></url></urlset>")
        other_host = BASE.replace("127.0.0.1", "localhost")
        route("/index.xml", (
            "<sitemapindex>"
            f"<sitemap><loc>{local.as_uri()}</loc></sitemap>"
            f"<sitemap><loc>{other_host}/other.xml</loc></sitemap>"
            f"<sitemap><loc>{BASE}/pages.xml</loc></sitemap>"
            "</sitemapindex>"
        ))
        route("/pages.xml", (
            "<urlset>"
            f"<url><loc>{BASE}/a</loc></url>"
            f"<url><loc>{BASE}/q?x=1&amp;y=2</loc></url>"
            f"<url><loc>{BASE}/gone</loc></url>"
            "</urlset>"
        ))
        route("/other.xml", f"<urlset><url><loc>{other_host}/a</loc></url></urlset>")
        route("/a", "page")
        route("/q?x=1&y=2", "page")

    def test_only_same_host_http_urls_are_fetched(self):
        self.sitemap_tree()
        code, out, _ = run(live.verify, BASE + "/index.xml")
        self.assertEqual(code, 1)
        self.assertNotIn("/from-local-file", _Handler.requested)
        self.assertNotIn("/other.xml", _Handler.requested)
        self.assertIn("SKIPPED (not an http(s) URL) file://", out)
        self.assertIn("SKIPPED (different host)", out)
        self.assertIn(f"404 {BASE}/gone", out)
        self.assertIn("2/3 OK", out)

    def test_entity_escaped_ampersands_are_decoded(self):
        self.sitemap_tree()
        run(live.verify, BASE + "/index.xml")
        self.assertIn("/q?x=1&y=2", _Handler.requested)

    def test_cross_host_urls_can_be_allowed_explicitly(self):
        self.sitemap_tree()
        run(live.verify, BASE + "/index.xml", allow_cross_host=True)
        self.assertIn("/other.xml", _Handler.requested)
        self.assertNotIn("/from-local-file", _Handler.requested)

    def test_rejects_non_web_sitemap_url(self):
        code, _, err = run(live.verify, "file:///etc/passwd")
        self.assertEqual(code, 2)
        self.assertIn("not an http(s) URL", err)

    def test_oversized_sitemap_is_an_error(self):
        route("/huge.xml", "<urlset>" + " " * 4096 + "</urlset>")
        with mock.patch.object(http, "MAX_BODY_BYTES", 1024):
            code, _, err = run(live.verify, BASE + "/huge.xml")
        self.assertEqual(code, 2)
        self.assertIn("larger than 1024 bytes", err)

    def test_control_characters_in_urls_are_escaped(self):
        route("/s.xml", f"<urlset><url><loc>{BASE}/x\x1b]0;pwned\x07</loc></url></urlset>")
        _, out, _ = run(live.verify, BASE + "/s.xml")
        self.assertNotIn("\x1b", out)
        self.assertIn("\\x1b]0;pwned\\x07", out)


class LinksTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "public"
        (Path(tmp.name) / "secret.txt").write_text("outside the site")
        files = {
            "index.html": (
                '<a href="/about/">a</a> <a href="blog/">b</a> <a href="missing.html">m</a>'
                '<script src="//cdn.example.org/x.js"></script> <a href="MAILTO:me@example.com">e</a>'
                '<a href="htps://typo.example.com">t</a> <a href="#top">top</a> <a href="?page=2">p</a>'
                '<a href="https://www.example.com/about/">abs</a> <a href="/bad\x1b[31m">c</a>'
            ),
            "about/index.html": "<p>about</p>",
            "blog/index.html": (
                '<a href="post.html">p</a> <a href="../about/">a</a> <a href="img/missing.png">i</a>'
                '<a href="/%2e%2e/secret.txt">escape</a> <a href="../../../secret.txt">escape</a>'
            ),
            "blog/post.html": "<p>post</p>",
        }
        for rel, body in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)

    def broken(self, out):
        return {line.split()[1] for line in out.splitlines() if line.strip().startswith("BROKEN")}

    def test_resolves_links_like_a_browser(self):
        code, out, _ = run(links.audit, str(self.root), ["example.com"])
        self.assertEqual(code, 1)
        self.assertEqual(self.broken(out), {
            "/missing.html", "/blog/img/missing.png", "/secret.txt", "htps://typo.example.com",
            "/bad\\x1b[31m",
        })
        self.assertIn("unique external URLs:    1", out)

    def test_links_never_resolve_outside_the_site_root(self):
        self.assertEqual(links._site_path("/%2e%2e/secret.txt", "/"), "/secret.txt")
        self.assertEqual(links._site_path("../../../secret.txt", "/blog"), "/secret.txt")
        self.assertFalse(links._target_exists(str(self.root), "/secret.txt"))

    def test_control_characters_in_links_are_escaped(self):
        _, out, _ = run(links.audit, str(self.root), ["example.com"])
        self.assertNotIn("\x1b", out)


class SchemaTest(unittest.TestCase):
    def audit_html(self, html):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        Path(tmp.name, "index.html").write_text(html)
        return run(schema.audit, tmp.name)

    @staticmethod
    def ld(doc):
        return f'<script type="application/ld+json">{doc}</script>'

    def test_clean_structured_data_passes(self):
        code, out, _ = self.audit_html(self.ld(json.dumps(
            {"@type": "Organization", "name": "IvanLabs", "sameAs": ["https://example.com/x"]})))
        self.assertEqual(code, 0)
        self.assertIn("entity types: Organization×1", out)

    def test_deep_nesting_is_a_parse_error_not_a_crash(self):
        code, out, _ = self.audit_html(self.ld("[" * 100000 + "]" * 100000))
        self.assertEqual(code, 1)
        self.assertIn("nested too deeply", out)

    def test_entity_artifacts_inside_arrays_are_found(self):
        doc = {"@type": "Person", "name": "Ivan", "sameAs": ["https:&#x2F;&#x2F;example.com"]}
        code, out, _ = self.audit_html(self.ld(json.dumps(doc)))
        self.assertEqual(code, 1)
        self.assertIn("ESCAPED index.html [sameAs]: https:&#x2F;&#x2F;example.com", out)

    def test_invalid_json_is_reported(self):
        code, out, _ = self.audit_html(self.ld("{not json"))
        self.assertEqual(code, 1)
        self.assertIn("INVALID index.html", out)

    def test_control_characters_in_values_are_escaped(self):
        doc = {"@type": "Thing", "name": "a &amp; b \x1b[2J"}
        _, out, _ = self.audit_html(self.ld(json.dumps(doc)))
        self.assertIn("ESCAPED index.html [name]: a &amp; b \\x1b[2J", out)


class RedirectsTest(ServerTestCase):
    def map_file(self, text):
        path = self.tmp / "redirects.txt"
        path.write_text(text)
        return str(path)

    def test_verifies_single_hop_permanent_redirects(self):
        route("/old", status=301, Location="/new")
        route("/new", "new page")
        route("/temp", status=302, Location="/new")
        route("/chain", status=301, Location="/old")
        path = self.map_file(
            "# source target\n/old /new\n/temp /new\n/chain /new\nfile:///etc/passwd /new\n")
        code, out, err = run(redirects.verify, path, BASE)
        self.assertEqual(code, 1)
        self.assertIn(f"OK   {BASE}/old -> 301 {BASE}/new (target 200)", out)
        self.assertIn(f"FAIL {BASE}/temp -> 302", out)
        self.assertIn(f"FAIL {BASE}/chain -> 301 {BASE}/old", out)
        self.assertIn("1/3 mappings correct", out)
        self.assertIn("only http(s) URLs can be checked", err)

    def test_base_must_be_a_web_url(self):
        code, _, err = run(redirects.verify, self.map_file("/a /b\n"), "example.com")
        self.assertEqual(code, 2)
        self.assertIn("--base must be an http(s) URL", err)


class CliTest(unittest.TestCase):
    def test_version(self):
        proc = subprocess.run([sys.executable, "-m", "sitebaseline", "--version"],
                              capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), f"site-baseline {__version__}")

    def test_live_refuses_a_file_url(self):
        code, _, _ = run(main, ["live", "file:///etc/passwd"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
