# ivanlabs-site-baseline

**Validation toolkit for static sites: link integrity, structured-data health, redirect maps, and live sitemap checks. Pure Python, zero dependencies.**

These are the scripts [IvanLabs](https://ivanlabs.com) uses in production to validate its own platform — extracted from real use, not built as a demo. They implement the mechanical layers of the [pre-migration baseline](https://ivanlabs.com/blog/pre-migration-baseline-what-to-capture/) and the post-deploy validation described in the [platform migration checklist](https://ivanlabs.com/blog/platform-migration-checklist/): the checks that catch broken links, corrupted JSON-LD, and mis-mapped redirects *before* search engines and answer engines find them.

## Install

```bash
pip install .
# or run without installing:
python -m sitebaseline --help
```

Python ≥ 3.9, standard library only.

## Commands

### `links` — link audit of a built site

Walks every `.html` file in a build directory, resolves every internal `href`/`src` against the filesystem, and reports broken targets. Optionally live-checks every external URL.

```bash
site-baseline links public/ --host example.com
site-baseline links public/ --host example.com --check-external
```

### `schema` — JSON-LD health check

Extracts every `application/ld+json` block, verifies it parses, and scans all string values for HTML-entity artifacts (`&#x2F;`, `&amp;`, …) — the classic symptom of template auto-escaping leaking into `<script>` content, where browsers do **not** entity-decode. Also flags `Person`/`Organization` nodes missing `sameAs`.

```bash
site-baseline schema public/
```

### `redirects` — redirect-map verification

Given a file of `source target` pairs, verifies each source answers with a **single-hop permanent redirect** (301/308) to exactly the mapped target, and that the target returns 200. Chains, temporary redirects, and mis-targets — the redirect failures that quietly destroy search visibility during migrations — all fail loudly.

```bash
site-baseline redirects examples/redirects.txt --base https://example.com
```

```text
# examples/redirects.txt — relative paths resolve against --base
/old-section/page/   /new-section/page/
/legacy-topic/       https://example.com/topics/new-topic/
```

### `live` — sitemap-wide 200 check

Fetches a sitemap (or sitemap index, recursively) and verifies every `<loc>` returns 200. The fastest "did the deploy break anything crawlers know about" signal.

```bash
site-baseline live https://example.com/sitemap_index.xml
```

## Exit codes

`0` clean · `1` findings · `2` usage/input error — so every command drops straight into CI:

```yaml
- run: site-baseline links public/ --host example.com
- run: site-baseline schema public/
```

## Why these checks

Migrations and redesigns rarely fail loudly. They fail as a 4% redirect-mapping error rate, a template that silently lost its structured data, an entity-escaped URL inside JSON-LD that every browser renders fine and every parser reads as garbage. Each command here exists because that failure happened somewhere real. The reasoning is documented in the [Migrations & Redesign Risk](https://ivanlabs.com/topics/migrations-redesign-risk/) field notes.

## License

MIT © [Ivan Popov](https://ivanlabs.com/about/), IvanLabs
