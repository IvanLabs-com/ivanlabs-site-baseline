"""Redirect-map verification against a live site.

Takes a mapping file of ``source target`` pairs (whitespace-separated, one per
line, ``#`` comments allowed; relative paths are resolved against --base) and
verifies each source answers with a SINGLE permanent redirect (301/308) whose
Location matches the mapped target, and that the target itself returns 200.

Chained, temporary, or mis-targeted redirects are exactly the migration
failures this exists to catch before search engines find them.
"""

import sys
from urllib.parse import urljoin

from .http import fetch_status


def _load_map(path, base):
    pairs = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 2:
                print(f"warning: {path}:{lineno}: expected 'source target', got: {raw.rstrip()}",
                      file=sys.stderr)
                continue
            src, dst = (urljoin(base + "/", p) if not p.startswith("http") else p for p in parts)
            pairs.append((src, dst))
    return pairs


def verify(map_path, base):
    """Verify every mapping. Returns exit code (0 = all correct)."""
    base = base.rstrip("/")
    pairs = _load_map(map_path, base)
    if not pairs:
        print("error: empty redirect map", file=sys.stderr)
        return 2

    failures = 0
    for src, dst in pairs:
        code, location = fetch_status(src, follow=False)
        location = urljoin(src, location) if location else ""
        ok_hop = code in (301, 308) and location.rstrip("/") == dst.rstrip("/")
        final_code, _ = fetch_status(dst, follow=True)
        ok_dst = final_code == 200
        status = "OK  " if (ok_hop and ok_dst) else "FAIL"
        if not (ok_hop and ok_dst):
            failures += 1
        print(f"{status} {src} -> {code} {location or '-'} (target {final_code})")

    print(f"\n{len(pairs) - failures}/{len(pairs)} mappings correct")
    return 1 if failures else 0
