"""Structured-data (JSON-LD) health check for a built static site.

Extracts every application/ld+json block, verifies it parses as JSON, and
scans all string values for HTML-entity artifacts (``&#x2F;``, ``&amp;``,
``&#x27;`` ...) — the classic symptom of template auto-escaping leaking into
script content, where browsers do NOT entity-decode. Also summarizes entity
types and flags Person/Organization nodes missing ``sameAs``.
"""

import json
import os
import re
import sys

from .output import safe

BLOCK_RE = re.compile(
    r"<script[^>]*type=[\"']?application/ld\+json[\"']?[^>]*>(.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)
ENTITY_RE = re.compile(r"&(#x?[0-9a-fA-F]+|amp|lt|gt|quot|apos);")


def _scan_strings(doc, hits, page):
    """Record string values that contain HTML entities, in document order.

    Strings inside arrays (e.g. ``sameAs`` URL lists) are reported under the
    array's key. Iterative, so deeply nested input cannot exhaust the stack.
    """
    stack = [iter([(None, doc)])]
    while stack:
        try:
            key, value = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if isinstance(value, str):
            if key is not None and ENTITY_RE.search(value):
                hits.append((page, key, value[:80]))
        elif isinstance(value, dict):
            stack.append(iter(value.items()))
        elif isinstance(value, list):
            stack.append((key, item) for item in value)


def _nodes(doc):
    if isinstance(doc, dict):
        graph = doc.get("@graph")
        if isinstance(graph, list):
            yield from graph
        else:
            yield doc
    elif isinstance(doc, list):
        yield from doc


def audit(root):
    """Validate JSON-LD across the built site at *root*. Returns exit code."""
    pages = []
    for r, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".html"):
                pages.append(os.path.join(r, name))
    if not pages:
        print(f"error: no .html files under {safe(root)}", file=sys.stderr)
        return 2

    blocks = 0
    parse_errors = []
    entity_hits = []
    types = {}
    missing_sameas = []

    for page in pages:
        rel = os.path.relpath(page, root)
        with open(page, encoding="utf-8", errors="ignore") as fh:
            html = fh.read()
        for match in BLOCK_RE.findall(html):
            blocks += 1
            try:
                doc = json.loads(match)
            except ValueError as exc:
                parse_errors.append((rel, str(exc)))
                continue
            except RecursionError:
                parse_errors.append((rel, "nested too deeply to parse"))
                continue
            _scan_strings(doc, entity_hits, rel)
            for node in _nodes(doc):
                if not isinstance(node, dict):
                    continue
                t = node.get("@type")
                if isinstance(t, str):
                    types[t] = types.get(t, 0) + 1
                if t in ("Person", "Organization") and not node.get("sameAs"):
                    missing_sameas.append((rel, t))

    print(f"pages scanned:   {len(pages)}")
    print(f"JSON-LD blocks:  {blocks}")
    print(f"parse errors:    {len(parse_errors)}")
    for rel, err in parse_errors:
        print(f"  INVALID {safe(rel)}: {safe(err)}")
    print(f"entity-escape artifacts in string values: {len(entity_hits)}")
    for rel, key, val in entity_hits[:20]:
        print(f"  ESCAPED {safe(rel)} [{safe(key)}]: {safe(val)}")
    if missing_sameas:
        seen = sorted(set(missing_sameas))
        print(f"Person/Organization nodes without sameAs: {len(seen)}")
        for rel, t in seen[:10]:
            print(f"  NO-SAMEAS {safe(t)} on {safe(rel)}")
    if types:
        print("entity types: " + ", ".join(f"{safe(k)}×{v}" for k, v in sorted(types.items())))

    return 1 if (parse_errors or entity_hits) else 0
